"""Tiered Tool Contracts (T0–T5) with Manifest Gating & Precondition Enforcement.

Invariant:
- T0/T1: Read-only & computation. No manifest required.
- T2/T3/T4: Staged, state, & availability changes. Valid accepted manifest_id required.
- T5: Destructive / lockout. Valid manifest_id + valid HITL approval required.
- Manifest amendment invalidates prior HITL approvals.
"""

from typing import Dict, Any, Optional
from harness.policy import PolicyEngine, PolicyViolation, PreconditionFailure
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestValidationError
from harness.diff_guard import ChangeSurfaceGuard, ChangeSurfaceViolation


class ToolContractError(Exception):
    pass


class HumanApprovalRequired(Exception):
    """Raised when a T5 action requires explicit Human-in-the-Loop authorization."""
    pass


class DeploymentTools:
    def __init__(
        self,
        secret_masker: SecretMasker,
        state_manager: StateManager,
        manifest_registry: Optional[ManifestRegistry] = None
    ):
        self.secrets = secret_masker
        self.state = state_manager
        self.manifest_registry = manifest_registry or ManifestRegistry()
        self.hitl_approvals = set()

    def _verify_manifest_authorization(self, tier: str, manifest_id: Optional[str]) -> ChangeManifest:
        """Enforces that T2+ mutations provide a valid, accepted change manifest."""
        if not manifest_id:
            raise ToolContractError(
                f"{tier} Mutation Blocked: Missing required 'manifest_id'. "
                f"You must submit and freeze a structured ChangeManifest before executing {tier} operations."
            )

        manifest = self.manifest_registry.get_manifest(manifest_id)
        if not manifest or not manifest.frozen:
            raise ToolContractError(
                f"{tier} Mutation Blocked: Manifest '{manifest_id}' is not recognized or not frozen."
            )
        return manifest

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

    # --- T2: Staged Local Modification (Manifest Required) ---
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

    # --- T3: Reversible System Modification (Manifest Required) ---
    def t3_atomic_symlink_switch(
        self,
        target_release_path: str,
        preconditions: Dict[str, Any],
        manifest_id: Optional[str] = None
    ) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T3", manifest_id)
        PolicyEngine.verify_atomic_cutover_preconditions(preconditions)
        self.state.create_checkpoint(f"Pre-cutover to {target_release_path}", {"target": target_release_path})
        self.state.atomic_cutover(target_release_path)
        return {
            "tier": "T3",
            "manifest_id": manifest.manifest_id,
            "current_target": target_release_path,
            "reversible": True,
            "rollback_ready": True
        }

    # --- T4: Availability-Affecting Operation (Manifest Required) ---
    def t4_reload_nginx(self, preconditions: Dict[str, Any], manifest_id: Optional[str] = None) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T4", manifest_id)
        PolicyEngine.verify_nginx_reload_preconditions(preconditions)
        return {
            "tier": "T4",
            "manifest_id": manifest.manifest_id,
            "action": "systemctl reload nginx",
            "preconditions_verified": True,
            "status": "reloaded_cleanly"
        }

    def t4_restart_supervisor(self, service_name: str, config_reread: bool, manifest_id: Optional[str] = None) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T4", manifest_id)
        if not config_reread:
            raise PreconditionFailure("Supervisor restart requires 'supervisorctl reread' to have succeeded.")
        return {
            "tier": "T4",
            "manifest_id": manifest.manifest_id,
            "action": f"supervisorctl restart {service_name}",
            "status": "restarted"
        }

    # --- T5: Destructive / Lockout Operation (Manifest + HITL Required) ---
    def authorize_t5_action(self, approval_token: str, manifest_id: Optional[str] = None):
        """Authorizes a pending T5 action via human operator input."""
        self.hitl_approvals.add(approval_token)
        if manifest_id and self.manifest_registry:
            self.manifest_registry.grant_hitl_approval(manifest_id)

    def t5_purge_old_backups(
        self,
        retention_days: int,
        manifest_id: Optional[str] = None,
        approval_token: Optional[str] = None
    ) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T5", manifest_id)
        expected_token = f"APPROVE_PURGE_BACKUPS_{retention_days}D"

        # Check HITL approval on both token and manifest
        token_approved = (approval_token in self.hitl_approvals or approval_token == expected_token)
        if not token_approved or not manifest.hitl_approved:
            raise HumanApprovalRequired(
                f"T5 Operation Blocked: Purging recovery snapshots requires Human approval for manifest '{manifest.manifest_id}' "
                f"with token '{expected_token}'."
            )

        return {
            "tier": "T5",
            "manifest_id": manifest.manifest_id,
            "action": f"purge_backups_older_than_{retention_days}_days",
            "status": "executed_with_human_authorization"
        }

    def t5_firewall_lockdown(
        self,
        allow_ssh_first: bool,
        manifest_id: Optional[str] = None,
        approval_token: Optional[str] = None
    ) -> Dict[str, Any]:
        manifest = self._verify_manifest_authorization("T5", manifest_id)
        if not allow_ssh_first:
            raise PolicyViolation("CRITICAL LOCKOUT HAZARD: Cannot enable firewall without allowing SSH port 22 first!")

        expected_token = "APPROVE_FIREWALL_LOCKDOWN"
        token_approved = (approval_token in self.hitl_approvals or approval_token == expected_token)
        if not token_approved or not manifest.hitl_approved:
            raise HumanApprovalRequired(
                f"T5 Operation Blocked: Enabling perimeter firewall requires Human approval for manifest '{manifest.manifest_id}' "
                f"with token '{expected_token}'."
            )

        return {
            "tier": "T5",
            "manifest_id": manifest.manifest_id,
            "action": "ufw --force enable",
            "status": "firewall_active"
        }
