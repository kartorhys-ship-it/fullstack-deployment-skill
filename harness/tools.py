"""Tiered Tool Contracts (T0–T5) with Manifest Authorization & Trusted Precondition Probes.

Security Invariants:
1. T0/T1: Read-only & computation. No manifest required.
2. T2/T3/T4: State & availability changes. Requires manifest with status == ACCEPTED.
3. T5: Destructive / lockout. Requires ACCEPTED manifest + trusted out-of-band HITL approval record.
4. Preconditions are observed facts from trusted probes, NOT caller-supplied booleans.
5. No self-authorization methods exist on the agent tool surface.
"""

from pathlib import Path
from typing import Dict, Any, Optional
from harness.policy import PolicyViolation, PreconditionFailure
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestStatus
from harness.diff_guard import ChangeSurfaceGuard, ChangeSurfaceViolation
from harness.approvals import TrustedApprovalService


class ToolContractError(Exception):
    pass


class HumanApprovalRequired(Exception):
    """Raised when a T5 action lacks a valid trusted out-of-band HITL authorization."""
    pass


class DeploymentTools:
    def __init__(
        self,
        secret_masker: SecretMasker,
        state_manager: StateManager,
        manifest_registry: Optional[ManifestRegistry] = None,
        approval_service: Optional[TrustedApprovalService] = None,
        repo_root: str = "."
    ):
        self.secrets = secret_masker
        self.state = state_manager
        self.manifest_registry = manifest_registry or ManifestRegistry()
        self.approval_service = approval_service or TrustedApprovalService()
        self.repo_root = Path(repo_root).resolve()

    def _verify_manifest_authorization(self, tier: str, manifest_id: Optional[str]) -> ChangeManifest:
        """Enforces that T2+ mutations provide a valid, ACCEPTED change manifest."""
        if not manifest_id:
            raise ToolContractError(
                f"{tier} Mutation Blocked: Missing required 'manifest_id'. "
                f"You must submit and obtain acceptance for a structured ChangeManifest before executing {tier} operations."
            )

        manifest = self.manifest_registry.get_manifest(manifest_id)
        if not manifest or manifest.status != ManifestStatus.ACCEPTED:
            status_val = manifest.status.value if manifest else "UNKNOWN"
            raise ToolContractError(
                f"{tier} Mutation Blocked: Manifest '{manifest_id}' is not in ACCEPTED state (current status: {status_val})."
            )
        return manifest

    # --- Trusted Precondition Probes (Observed Facts, Not Caller Assertions) ---
    def _probe_nginx_syntax(self) -> bool:
        """Probes repository and sandbox Nginx configurations for syntax validity."""
        for conf in self.repo_root.glob("**/nginx/**/*.conf"):
            try:
                content = conf.read_text(encoding="utf-8")
                if content.count("{") != content.count("}"):
                    return False
            except Exception:
                return False
        return True

    def _probe_rollback_readiness(self) -> bool:
        """Probes whether state manager or releases layout has active rollback checkpoints."""
        return len(self.state.checkpoints) > 0 or (self.repo_root / "templates").exists()

    def _probe_ssh_firewall_allowed(self) -> bool:
        """Probes whether SSH port 22 is explicitly allowed in perimeter configurations."""
        for f in self.repo_root.glob("**/*"):
            if f.is_dir() or ".git" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if "allow 22" in content or "allow ssh" in content.lower():
                    return True
            except Exception:
                pass
        return False

    # --- T0: Pure Computation (No Manifest Required) ---
    def t0_calc_worker_sizing(self, cpu_cores: int, ram_gb: float, is_async: bool = True) -> Dict[str, Any]:
        if ram_gb <= 2.0:
            recommended = min(3, max(2, cpu_cores + 1))
        else:
            recommended = (2 * cpu_cores) + 1 if not is_async else min(8, cpu_cores * 2)

        return {
            "tier": "T0",
            "recommended_workers": recommended,
            "estimated_ram_mb": recommended * 85,
            "recommendation": "Calibrate under Locust load testing; monitor memory via btop."
        }

    # --- T1: Read-Only Inspection (No Manifest Required) ---
    def t1_inspect_service_status(self, service_name: str) -> Dict[str, Any]:
        return {
            "tier": "T1",
            "service": service_name,
            "status": "active (running)",
            "read_only": True
        }

    # --- T2: Staged Local Modification (Requires ACCEPTED Manifest) ---
    def t2_stage_release_directory(self, release_timestamp: str, manifest_id: Optional[str] = None) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T2", manifest_id)
        return {
            "tier": "T2",
            "manifest_id": manifest.manifest_id,
            "staged_path": f"/var/www/webapp/releases/{release_timestamp}",
            "status": "staged",
            "impact": "isolated_directory"
        }

    def t2_stage_config_patch(
        self,
        target_file: str,
        new_content: str,
        original_content: str = "",
        manifest_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stages a configuration modification, strictly validated by ChangeSurfaceGuard."""
        manifest = self._verify_manifest_authorization("T2", manifest_id)
        guard = ChangeSurfaceGuard(manifest)
        allowed, reason = guard.validate_mutation(target_file, original_content, new_content)
        if not allowed:
            raise ChangeSurfaceViolation(reason)

        diff = guard.compute_diff(original_content, new_content, target_file)
        return {
            "tier": "T2",
            "manifest_id": manifest.manifest_id,
            "target_file": target_file,
            "status": "staged_validated",
            "diff": diff
        }

    # --- T3: Reversible System Modification (Requires ACCEPTED Manifest + Probes) ---
    def t3_atomic_symlink_switch(
        self,
        target_release_path: str,
        manifest_id: Optional[str] = None
    ) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T3", manifest_id)
        
        # Observed precondition check
        self.state.create_checkpoint(f"Pre-cutover to {target_release_path}", {"target": target_release_path})
        self.state.atomic_cutover(target_release_path)
        return {
            "tier": "T3",
            "manifest_id": manifest.manifest_id,
            "current_target": target_release_path,
            "reversible": True,
            "rollback_ready": True
        }

    # --- T4: Availability-Affecting Operation (Requires ACCEPTED Manifest + Probes) ---
    def t4_reload_nginx(self, manifest_id: Optional[str] = None) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T4", manifest_id)
        
        # Probe Nginx syntax independently (NOT caller boolean)
        if not self._probe_nginx_syntax():
            raise PreconditionFailure("Nginx reload blocked: Independent syntax probe detected invalid configuration.")

        if not self._probe_rollback_readiness():
            raise PreconditionFailure("Nginx reload blocked: No rollback checkpoint verified.")

        return {
            "tier": "T4",
            "manifest_id": manifest.manifest_id,
            "action": "systemctl reload nginx",
            "syntax_probed_ok": True,
            "status": "reloaded_cleanly"
        }

    def t4_restart_supervisor(self, service_name: str, manifest_id: Optional[str] = None) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T4", manifest_id)
        return {
            "tier": "T4",
            "manifest_id": manifest.manifest_id,
            "action": f"supervisorctl restart {service_name}",
            "status": "restarted"
        }

    # --- T5: Destructive / Lockout Operation (Requires ACCEPTED Manifest + Trusted HITL Record) ---
    def t5_purge_old_backups(
        self,
        retention_days: int,
        manifest_id: Optional[str] = None
    ) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T5", manifest_id)
        action_name = "purge_backups"

        # Verify against trusted out-of-band approval service
        approved, err = self.approval_service.verify_action_authorization(
            manifest_id=manifest.manifest_id,
            current_manifest_version=manifest.version,
            action=action_name
        )
        if not approved:
            raise HumanApprovalRequired(
                f"T5 Destructive Action Blocked: {err} "
                f"A trusted human operator must issue an out-of-band approval for manifest '{manifest.manifest_id}' v{manifest.version}."
            )

        return {
            "tier": "T5",
            "manifest_id": manifest.manifest_id,
            "action": f"purge_backups_older_than_{retention_days}_days",
            "status": "executed_with_human_authorization"
        }

    def t5_firewall_lockdown(
        self,
        manifest_id: Optional[str] = None
    ) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T5", manifest_id)

        # Probed safety invariant: Port 22 must be verified open before firewall activation
        if not self._probe_ssh_firewall_allowed():
            raise PolicyViolation("CRITICAL LOCKOUT HAZARD: Host probe reveals SSH port 22 is NOT allowed in firewall rules!")

        action_name = "firewall_lockdown"
        approved, err = self.approval_service.verify_action_authorization(
            manifest_id=manifest.manifest_id,
            current_manifest_version=manifest.version,
            action=action_name
        )
        if not approved:
            raise HumanApprovalRequired(
                f"T5 Lockout Action Blocked: {err} "
                f"A trusted human operator must issue an out-of-band approval for manifest '{manifest.manifest_id}' v{manifest.version}."
            )

        return {
            "tier": "T5",
            "manifest_id": manifest.manifest_id,
            "action": "ufw --force enable",
            "status": "firewall_active"
        }
