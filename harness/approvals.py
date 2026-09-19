"""Trusted Out-of-Band Human-in-the-Loop (HITL) Approval Service Prototype.

Separates human authorization from the agent tool surface.
Approvals are tamper-identifying records issued by an authenticated operator identity,
bound to an exact manifest_id, manifest_version, action, and canonical argument parameters,
with tamper-evident hashing and expiration.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any


class ApprovalExpiredError(Exception):
    pass


class ApprovalNotFoundError(Exception):
    pass


class ParameterSubstitutionError(Exception):
    pass


def canonical_action_hash(action: str, arguments: Optional[Dict[str, Any]] = None) -> str:
    """Computes a deterministic canonical SHA256 hash of an action and its arguments.
    
    Prevents parameter substitution attacks where an operator approves one set of arguments
    (e.g., retention_days=90) but the agent executes with different arguments (e.g., retention_days=1).
    """
    clean_args = arguments or {}
    payload = {
        "action": action.strip(),
        "arguments": clean_args
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    manifest_id: str
    manifest_version: int
    action: str
    action_hash: str
    operator_identity: str
    timestamp: float
    expires_at: float
    signature_hash: str

    def is_valid(
        self,
        current_manifest_version: int,
        expected_action_hash: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        if time.time() > self.expires_at:
            return False, f"Approval '{self.approval_id}' has expired (expired at {self.expires_at})."
        if self.manifest_version != current_manifest_version:
            return False, (
                f"Approval version mismatch: Approval was granted for manifest v{self.manifest_version}, "
                f"but manifest is now v{current_manifest_version}. Scope expansion invalidates prior approval."
            )
        if expected_action_hash and self.action_hash != expected_action_hash:
            return False, (
                f"PARAMETER_SUBSTITUTION_DETECTED: Executed action arguments do not match approved arguments. "
                f"Expected hash '{expected_action_hash}', approved hash '{self.action_hash}'."
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
        arguments: Optional[Dict[str, Any]] = None,
        duration_seconds: float = 3600.0
    ) -> ApprovalRecord:
        """Invoked exclusively by a trusted human operator/UI, not the AI agent."""
        if not operator_identity or not operator_identity.strip():
            raise ValueError("Operator identity required for HITL authorization.")

        now = time.time()
        expires = now + duration_seconds
        act_hash = canonical_action_hash(action, arguments)
        payload = f"{manifest_id}:{manifest_version}:{action}:{act_hash}:{operator_identity}:{now}"
        sig = hashlib.sha256(payload.encode()).hexdigest()
        approval_id = f"appr_{sig[:12]}"

        record = ApprovalRecord(
            approval_id=approval_id,
            manifest_id=manifest_id,
            manifest_version=manifest_version,
            action=action,
            action_hash=act_hash,
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
        action: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Verifies if an active, unexpired approval exists for this exact action, version, AND arguments."""
        key = f"{manifest_id}:{action}"
        record = self._approvals.get(key)
        if not record:
            return False, f"No trusted HITL approval record found for action '{action}' on manifest '{manifest_id}'."

        expected_hash = canonical_action_hash(action, arguments)
        return record.is_valid(current_manifest_version, expected_action_hash=expected_hash)

    def revoke_approval(self, manifest_id: str, action: Optional[str] = None):
        """Revokes approvals for a manifest."""
        if action:
            self._approvals.pop(f"{manifest_id}:{action}", None)
        else:
            keys_to_del = [k for k in self._approvals if k.startswith(f"{manifest_id}:")]
            for k in keys_to_del:
                del self._approvals[k]
