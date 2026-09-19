"""Change Manifest Protocol & Structured State Management.

Defines the ChangeManifest schema, validation logic, cryptographic/session manifest_id
issuance, scope amendment tracking, and HITL authorization lifecycle.
"""

import hashlib
import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


class ManifestValidationError(Exception):
    """Raised when a proposed change manifest violates schema or invariants."""
    pass


@dataclass
class ChangeManifest:
    manifest_id: str
    version: int
    intent: str
    targets: List[str]
    expected_dependencies: List[str]
    invariants: List[str]
    verification: List[str]
    rollback: Dict[str, Any]
    full_rewrite: bool = False
    rewrite_justification: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    frozen: bool = False
    hitl_approved: bool = False
    amendment_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_yaml(self) -> str:
        """Render clean, human-readable YAML audit representation."""
        lines = ["change_manifest:"]
        lines.append(f"  manifest_id: {self.manifest_id}")
        lines.append(f"  version: {self.version}")
        lines.append(f"  intent: \"{self.intent}\"")
        lines.append("  targets:")
        for t in self.targets:
            lines.append(f"    - {t}")
        lines.append("  expected_dependencies:")
        for d in self.expected_dependencies:
            lines.append(f"    - {d}")
        lines.append("  invariants:")
        for inv in self.invariants:
            lines.append(f"    - {inv}")
        lines.append("  verification:")
        for v in self.verification:
            lines.append(f"    - {v}")
        lines.append(f"  rollback: {json.dumps(self.rollback)}")
        lines.append(f"  full_rewrite: {str(self.full_rewrite).lower()}")
        if self.rewrite_justification:
            lines.append(f"  rewrite_justification: \"{self.rewrite_justification}\"")
        lines.append(f"  hitl_approved: {str(self.hitl_approved).lower()}")
        return "\n".join(lines)


class ManifestRegistry:
    """In-memory registry governing active change manifests."""

    def __init__(self):
        self._manifests: Dict[str, ChangeManifest] = {}
        self._counter = 0

    def submit_manifest(
        self,
        intent: str,
        targets: List[str],
        expected_dependencies: List[str],
        invariants: List[str],
        verification: List[str],
        rollback: Dict[str, Any],
        full_rewrite: bool = False,
        rewrite_justification: Optional[str] = None
    ) -> ChangeManifest:
        """Validate, register, and freeze a new structured Change Manifest."""
        # 1. Validation
        if not intent or not intent.strip():
            raise ManifestValidationError("Change manifest requires a non-empty 'intent'.")
        if not targets or not isinstance(targets, list):
            raise ManifestValidationError("Change manifest requires at least one target in 'targets'.")
        if not invariants or not isinstance(invariants, list):
            raise ManifestValidationError("Change manifest requires non-empty 'invariants'.")
        if not verification or not isinstance(verification, list):
            raise ManifestValidationError("Change manifest requires non-empty 'verification'.")
        if not rollback or not isinstance(rollback, dict):
            raise ManifestValidationError("Change manifest requires a valid 'rollback' specification.")

        if full_rewrite and (not rewrite_justification or len(rewrite_justification.strip()) < 10):
            raise ManifestValidationError(
                "Full-file rewrite declared without adequate 'rewrite_justification'. "
                "Prefer the smallest semantically complete change."
            )

        # Normalize paths
        norm_targets = [t.replace("\\", "/").lstrip("./") for t in targets]

        self._counter += 1
        date_str = time.strftime("%Y%m%d")
        seed = f"{intent}:{sorted(norm_targets)}:{time.time()}"
        m_hash = hashlib.sha256(seed.encode()).hexdigest()[:8]
        manifest_id = f"chg_{date_str}_{self._counter:03d}_{m_hash}"

        manifest = ChangeManifest(
            manifest_id=manifest_id,
            version=1,
            intent=intent.strip(),
            targets=norm_targets,
            expected_dependencies=expected_dependencies or [],
            invariants=invariants,
            verification=verification,
            rollback=rollback,
            full_rewrite=full_rewrite,
            rewrite_justification=rewrite_justification,
            frozen=True
        )

        self._manifests[manifest_id] = manifest
        return manifest

    def amend_manifest(
        self,
        manifest_id: str,
        new_targets: Optional[List[str]] = None,
        new_dependencies: Optional[List[str]] = None,
        amendment_reason: str = ""
    ) -> ChangeManifest:
        """Amend an existing manifest. Automatically invalidates any previous HITL authorizations."""
        manifest = self.get_manifest(manifest_id)
        if not manifest:
            raise ManifestValidationError(f"Manifest '{manifest_id}' not found.")

        if not amendment_reason or len(amendment_reason.strip()) < 5:
            raise ManifestValidationError("Amending a manifest requires an explicit 'amendment_reason'.")

        # Record history
        record = {
            "from_version": manifest.version,
            "timestamp": time.time(),
            "reason": amendment_reason,
            "previous_targets": list(manifest.targets),
            "previous_dependencies": list(manifest.expected_dependencies)
        }
        manifest.amendment_history.append(record)

        if new_targets:
            for nt in new_targets:
                norm = nt.replace("\\", "/").lstrip("./")
                if norm not in manifest.targets:
                    manifest.targets.append(norm)

        if new_dependencies:
            for nd in new_dependencies:
                if nd not in manifest.expected_dependencies:
                    manifest.expected_dependencies.append(nd)

        manifest.version += 1

        # CRITICAL INVARIANT: Scope expansion invalidates prior HITL approvals
        manifest.hitl_approved = False

        return manifest

    def grant_hitl_approval(self, manifest_id: str) -> ChangeManifest:
        manifest = self.get_manifest(manifest_id)
        if not manifest:
            raise ManifestValidationError(f"Manifest '{manifest_id}' not found.")
        manifest.hitl_approved = True
        return manifest

    def get_manifest(self, manifest_id: str) -> Optional[ChangeManifest]:
        return self._manifests.get(manifest_id)
