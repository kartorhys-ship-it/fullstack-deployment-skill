"""Change Surface Guard & Blast Radius Boundary Verifier.

Compares actual file modifications and diffs against the accepted ChangeManifest.
Intercepts unexpected file modifications, unannounced full-file rewrites,
and accidental deletions of security headers or SSL configurations.
"""

import difflib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from harness.manifest import ChangeManifest


class ChangeSurfaceViolation(Exception):
    """Raised when an actual file mutation violates the accepted ChangeManifest boundaries."""
    pass


class ChangeSurfaceGuard:
    """Verifies that actual staged edits conform strictly to the accepted ChangeManifest."""

    def __init__(self, manifest: ChangeManifest):
        self.manifest = manifest

    def validate_mutation(
        self,
        target_file: str,
        original_content: str,
        new_content: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate a proposed file modification against the manifest boundaries."""
        norm_target = target_file.replace("\\", "/").lstrip("./")

        # 1. Exact canonical target authorization check
        canonical_declared = {t.replace("\\", "/").lstrip("./") for t in self.manifest.targets}
        if norm_target not in canonical_declared:
            reason = (
                f"CHANGE_SURFACE_VIOLATION: Attempted mutation of unauthorized file '{norm_target}'. "
                f"Declared manifest targets: {sorted(list(canonical_declared))}. "
                f"Action: Submit an amended manifest to expand target scope."
            )
            return False, reason

        # If identical content, allowed as no-op
        if original_content == new_content:
            return True, None

        # 2. Full-file rewrite check
        if not self.manifest.full_rewrite:
            orig_lines = original_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            matcher = difflib.SequenceMatcher(None, orig_lines, new_lines)
            similarity = matcher.ratio()

            # If the file had substantial content and is completely replaced (similarity < 0.20)
            if len(orig_lines) > 20 and similarity < 0.20:
                reason = (
                    f"CHANGE_SURFACE_VIOLATION: Unannounced full-file rewrite on '{norm_target}' "
                    f"(similarity: {similarity:.1%}). Manifest declared 'full_rewrite=False'. "
                    f"Prefer surgical block edits or justify full rewrite in manifest."
                )
                return False, reason

        # 3. Critical Invariant Preservation Check (Nginx specific)
        if "nginx" in norm_target or norm_target.endswith(".conf"):
            # Check security headers inclusion preservation
            if "snippets/security-headers.conf" in original_content and "snippets/security-headers.conf" not in new_content:
                return False, "CHANGE_SURFACE_VIOLATION: Proposed edit silently deleted security headers include!"

            # Check SSL certificate preservation
            if "ssl_certificate" in original_content and "ssl_certificate" not in new_content:
                return False, "CHANGE_SURFACE_VIOLATION: Proposed edit silently deleted SSL certificate directives!"

            # Check Cloudflare real-IP preservation if previously present
            if "set_real_ip_from" in original_content and "set_real_ip_from" not in new_content:
                return False, "CHANGE_SURFACE_VIOLATION: Proposed edit silently deleted Cloudflare real-IP configuration!"

        return True, None

    def compute_diff(self, original_content: str, new_content: str, filename: str) -> str:
        """Generate unified diff representation for audit logs."""
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}"
        )
        return "".join(diff)
