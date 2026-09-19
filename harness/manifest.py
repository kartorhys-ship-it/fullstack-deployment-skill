"""Transactional Change Manifest Protocol & State Machine.

Defines the ManifestStatus lifecycle, canonical path validation, and transactional
amendments to ensure failed impact checks never leave behind usable authorization.
"""

import hashlib
import time
import json
import re
from enum import Enum
from pathlib import Path, PurePosixPath
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple


class ManifestStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    ACCEPTED = "ACCEPTED"
    AMENDING = "AMENDING"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ManifestValidationError(Exception):
    """Raised when a proposed change manifest violates schema or invariants."""
    pass


class PathTraversalViolation(ManifestValidationError):
    """Raised when a path traversal sequence or illegal boundary escape is detected."""
    pass


def canonicalize_path(path_str: str) -> str:
    """Validates and canonicalizes a relative target file path across both Windows and POSIX hosts.

    Security Invariants:
    1. Rejects empty or whitespace-only paths.
    2. Normalizes all backslashes to forward slashes before any parsing.
    3. Rejects leading slashes (POSIX root, Windows root, and UNC network shares).
    4. Rejects Windows drive-letter absolute paths (e.g., C:/, D:/).
    5. Rejects any traversal sequences ('..') in path components.
    6. Always returns a clean, relative POSIX path string.
    """
    if not path_str or not isinstance(path_str, str) or not path_str.strip():
        raise ManifestValidationError("Target file path cannot be empty.")

    # Normalize separators upfront
    clean = path_str.strip().replace("\\", "/")

    # Reject leading slashes (POSIX absolute paths, UNC network roots)
    if clean.startswith("/"):
        raise PathTraversalViolation(f"Absolute or root paths not permitted in manifest targets: '{path_str}'. Must be relative.")

    # Reject Windows drive letters (e.g. C:, D:)
    if re.match(r"^[A-Za-z]:", clean):
        raise PathTraversalViolation(f"Drive-letter absolute paths not permitted in manifest targets: '{path_str}'. Must be relative.")

    # Parse with PurePosixPath to inspect components independently of host OS
    p = PurePosixPath(clean)
    if ".." in p.parts:
        raise PathTraversalViolation(f"Path traversal '..' prohibited in target: '{path_str}'.")

    # Reconstruct normalized posix string without leading ./
    norm = str(p)
    while norm.startswith("./"):
        norm = norm[2:]

    if not norm or norm == ".":
        raise ManifestValidationError(f"Invalid empty or root target path: '{path_str}'.")

    return norm


@dataclass
class ChangeManifest:
    manifest_id: str
    version: int
    intent: str
    targets: List[str]                  # Canonical file paths strictly
    expected_dependencies: List[str]    # Graph dependency nodes (services, endpoints)
    invariants: List[str]
    verification: List[str]
    rollback: Dict[str, Any]
    status: ManifestStatus = ManifestStatus.PENDING_VALIDATION
    full_rewrite: bool = False
    rewrite_justification: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    rejection_reason: Optional[str] = None
    amendment_history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        return self.status == ManifestStatus.ACCEPTED

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def to_yaml(self) -> str:
        """Render clean, human-readable YAML audit representation."""
        lines = ["change_manifest:"]
        lines.append(f"  manifest_id: {self.manifest_id}")
        lines.append(f"  version: {self.version}")
        lines.append(f"  status: {self.status.value}")
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
        return "\n".join(lines)


class ManifestRegistry:
    """In-memory transactional registry governing active change manifests."""

    def __init__(self):
        self._manifests: Dict[str, ChangeManifest] = {}
        self._amendment_staging: Dict[str, ChangeManifest] = {}
        self._counter = 0

    def create_pending_manifest(
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
        """Validates inputs and creates a manifest in PENDING_VALIDATION state.

        Does not authorize execution until impact validation succeeds and accept_manifest is called.
        """
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

        # Canonicalize target paths strictly
        canonical_targets = []
        for t in targets:
            c = canonicalize_path(t)
            if c not in canonical_targets:
                canonical_targets.append(c)

        self._counter += 1
        date_str = time.strftime("%Y%m%d")
        seed = f"{intent}:{sorted(canonical_targets)}:{time.time()}"
        m_hash = hashlib.sha256(seed.encode()).hexdigest()[:8]
        manifest_id = f"chg_{date_str}_{self._counter:03d}_{m_hash}"

        manifest = ChangeManifest(
            manifest_id=manifest_id,
            version=1,
            intent=intent.strip(),
            targets=canonical_targets,
            expected_dependencies=expected_dependencies or [],
            invariants=invariants,
            verification=verification,
            rollback=rollback,
            full_rewrite=full_rewrite,
            rewrite_justification=rewrite_justification,
            status=ManifestStatus.PENDING_VALIDATION
        )

        self._manifests[manifest_id] = manifest
        return manifest

    def accept_manifest(self, manifest_id: str) -> ChangeManifest:
        """Transitions manifest from PENDING_VALIDATION to ACCEPTED."""
        manifest = self._manifests.get(manifest_id)
        if not manifest:
            raise ManifestValidationError(f"Manifest '{manifest_id}' not found.")
        if manifest.status != ManifestStatus.PENDING_VALIDATION:
            raise ManifestValidationError(f"Cannot accept manifest in status '{manifest.status.value}'.")

        manifest.status = ManifestStatus.ACCEPTED
        return manifest

    def reject_manifest(self, manifest_id: str, reason: str) -> ChangeManifest:
        """Transitions manifest to REJECTED."""
        manifest = self._manifests.get(manifest_id)
        if manifest:
            manifest.status = ManifestStatus.REJECTED
            manifest.rejection_reason = reason
        return manifest

    def stage_amendment(
        self,
        manifest_id: str,
        new_targets: Optional[List[str]] = None,
        new_dependencies: Optional[List[str]] = None,
        new_invariants: Optional[List[str]] = None,
        amendment_reason: str = ""
    ) -> ChangeManifest:
        """Creates an isolated transactional candidate clone in AMENDING state.

        The existing ACCEPTED manifest remains intact until commit_amendment is called!
        """
        current = self.get_manifest(manifest_id)
        if not current or current.status != ManifestStatus.ACCEPTED:
            raise ManifestValidationError(f"Cannot amend manifest '{manifest_id}': not currently ACCEPTED.")

        if not amendment_reason or len(amendment_reason.strip()) < 5:
            raise ManifestValidationError("Amending a manifest requires an explicit 'amendment_reason'.")

        # Create candidate clone
        candidate_targets = list(current.targets)
        if new_targets:
            for nt in new_targets:
                c = canonicalize_path(nt)
                if c not in candidate_targets:
                    candidate_targets.append(c)

        candidate_deps = list(current.expected_dependencies)
        if new_dependencies:
            for nd in new_dependencies:
                if nd not in candidate_deps:
                    candidate_deps.append(nd)

        candidate_invs = list(current.invariants)
        if new_invariants:
            for ni in new_invariants:
                if ni not in candidate_invs:
                    candidate_invs.append(ni)

        candidate = ChangeManifest(
            manifest_id=current.manifest_id,
            version=current.version + 1,
            intent=current.intent,
            targets=candidate_targets,
            expected_dependencies=candidate_deps,
            invariants=candidate_invs,
            verification=list(current.verification),
            rollback=dict(current.rollback),
            full_rewrite=current.full_rewrite,
            rewrite_justification=current.rewrite_justification,
            status=ManifestStatus.AMENDING,
            amendment_history=list(current.amendment_history)
        )

        record = {
            "from_version": current.version,
            "to_version": candidate.version,
            "timestamp": time.time(),
            "reason": amendment_reason,
            "previous_targets": list(current.targets),
            "added_targets": [t for t in candidate_targets if t not in current.targets]
        }
        candidate.amendment_history.append(record)

        self._amendment_staging[manifest_id] = candidate
        return candidate

    def commit_amendment(self, manifest_id: str) -> ChangeManifest:
        """Replaces current accepted manifest with verified candidate."""
        candidate = self._amendment_staging.pop(manifest_id, None)
        if not candidate:
            raise ManifestValidationError(f"No staged amendment found for manifest '{manifest_id}'.")

        candidate.status = ManifestStatus.ACCEPTED
        self._manifests[manifest_id] = candidate
        return candidate

    def rollback_amendment(self, manifest_id: str, reason: str):
        """Discards candidate amendment upon validation failure, leaving existing manifest intact."""
        self._amendment_staging.pop(manifest_id, None)

    def has_staged_amendment(self, manifest_id: str) -> bool:
        """Returns True if a candidate amendment is currently in staging, False otherwise."""
        return manifest_id in self._amendment_staging

    def get_staged_amendment(self, manifest_id: str) -> Optional[ChangeManifest]:
        """Returns candidate staged amendment if currently in AMENDING state, or None."""
        return self._amendment_staging.get(manifest_id)

    def get_manifest(self, manifest_id: str) -> Optional[ChangeManifest]:
        return self._manifests.get(manifest_id)

