"""Trusted Out-of-Band Human-in-the-Loop (HITL) Approval Service.

Separates human authorization from the agent tool surface.
Approvals are tamper-evident records issued by an authenticated operator identity,
bound to an exact manifest_id and manifest_version, with cryptographic hashing and expiry.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any


class ApprovalExpiredError(Exception):
    pass


class ApprovalNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    manifest_id: str
    manifest_version: int
    action: str
    operator_identity: str
    timestamp: float
    expires_at: float
    signature_hash: str

    def is_valid(self, current_manifest_version: int) -> Tuple[bool, Optional[str]]:
        if time.time() > self.expires_at:
            return False, f"Approval '{self.approval_id}' has expired (expired at {self.expires_at})."
        if self.manifest_version != current_manifest_version:
            return False, (
                f"Approval version mismatch: Approval was granted for manifest v{self.manifest_version}, "
                f"but manifest is now v{current_manifest_version}. Scope expansion invalidates prior approval."
            )
        return True, None


class TrustedApprovalService:
    """Out-of-band authority managing human operator approvals.

    NOT accessible from the agent callable tool surface.
    """

    def __init__(self):
        self._approvals: Dict[str, ApprovalRecord] = {}

    def grant_approval(
        self,
        manifest_id: str,
        manifest_version: int,
        action: str,
        operator_identity: str,
        duration_seconds: float = 3600.0
    ) -> ApprovalRecord:
        """Invoked exclusively by a trusted human operator/UI, not the AI agent."""
        if not operator_identity or not operator_identity.strip():
            raise ValueError("Operator identity required for HITL authorization.")

        now = time.time()
        expires = now + duration_seconds
        payload = f"{manifest_id}:{manifest_version}:{action}:{operator_identity}:{now}"
        sig = hashlib.sha256(payload.encode()).hexdigest()
        approval_id = f"appr_{sig[:12]}"

        record = ApprovalRecord(
            approval_id=approval_id,
            manifest_id=manifest_id,
            manifest_version=manifest_version,
            action=action,
            operator_identity=operator_identity.strip(),
            timestamp=now,
            expires_at=expires,
            signature_hash=sig
        )

        key = f"{manifest_id}:{action}"
        self._approvals[key] = record
        return record

    def verify_action_authorization(
        self,
        manifest_id: str,
        current_manifest_version: int,
        action: str
    ) -> Tuple[bool, Optional[str]]:
        """Verifies if an active, unexpired approval exists for this exact action and version."""
        key = f"{manifest_id}:{action}"
        record = self._approvals.get(key)
        if not record:
            return False, f"No trusted HITL approval record found for action '{action}' on manifest '{manifest_id}'."

        return record.is_valid(current_manifest_version)

    def revoke_approval(self, manifest_id: str, action: Optional[str] = None):
        """Revokes approvals for a manifest."""
        if action:
            self._approvals.pop(f"{manifest_id}:{action}", None)
        else:
            keys_to_del = [k for k in self._approvals if k.startswith(f"{manifest_id}:")]
            for k in keys_to_del:
                del self._approvals[k]
