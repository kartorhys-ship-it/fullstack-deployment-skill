"""
Tiered Tool Contracts (T0–T5) with Policy & Precondition Enforcements
"""
from typing import Dict, Any, Optional
from harness.policy import PolicyEngine, PolicyViolation, PreconditionFailure
from harness.secrets import SecretMasker
from harness.state import StateManager

class ToolContractError(Exception):
    pass

class HumanApprovalRequired(Exception):
    """Raised when a T5 action requires explicit Human-in-the-Loop authorization."""
    pass

class DeploymentTools:
    def __init__(self, secret_masker: SecretMasker, state_manager: StateManager):
        self.secrets = secret_masker
        self.state = state_manager
        self.hitl_approvals = set()

    # --- T0: Pure Computation ---
    def t0_calc_worker_sizing(self, cpu_cores: int, ram_gb: float, is_async: bool = True) -> Dict[str, Any]:
        """
        Calculates recommended worker baseline with memory constraints.
        Heuristic: async workloads on 1-2GB VPS should use 2-3 workers regardless of core count.
        """
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

    # --- T1: Read-Only Inspection ---
    def t1_inspect_service_status(self, service_name: str) -> Dict[str, Any]:
        """Read-only safe operation. Inspects service state without modifying host."""
        return {
            "tier": "T1",
            "service": service_name,
            "status": "active (running)",
            "read_only": True
        }

    # --- T2: Staged Local Modification ---
    def t2_stage_release_directory(self, release_timestamp: str) -> Dict[str, Any]:
        """Prepares a staged release directory. Does not alter production symlink."""
        return {
            "tier": "T2",
            "staged_path": f"/var/www/webapp/releases/{release_timestamp}",
            "status": "staged",
            "impact": "isolated_directory"
        }

    # --- T3: Reversible System Modification ---
    def t3_atomic_symlink_switch(self, target_release_path: str, preconditions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Swaps current symlink to target release.
        Requires checkpointing and preconditions. Reversible via rollback.
        """
        PolicyEngine.verify_atomic_cutover_preconditions(preconditions)
        self.state.create_checkpoint(f"Pre-cutover to {target_release_path}", {"target": target_release_path})
        self.state.atomic_cutover(target_release_path)
        return {
            "tier": "T3",
            "current_target": target_release_path,
            "reversible": True,
            "rollback_ready": True
        }

    # --- T4: Availability-Affecting Operation ---
    def t4_reload_nginx(self, preconditions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Issues graceful reload to Nginx.
        Requires passing nginx_configuration_valid precondition.
        """
        PolicyEngine.verify_nginx_reload_preconditions(preconditions)
        return {
            "tier": "T4",
            "action": "systemctl reload nginx",
            "preconditions_verified": True,
            "status": "reloaded_cleanly"
        }

    def t4_restart_supervisor(self, service_name: str, config_reread: bool) -> Dict[str, Any]:
        """Restarts supervised service after verifying configuration reread."""
        if not config_reread:
            raise PreconditionFailure("Supervisor restart requires 'supervisorctl reread' to have succeeded.")
        return {
            "tier": "T4",
            "action": f"supervisorctl restart {service_name}",
            "status": "restarted"
        }

    # --- T5: Destructive / Lockout Operation (HITL Boundary) ---
    def authorize_t5_action(self, approval_token: str):
        """Authorizes a pending T5 action via human operator input."""
        self.hitl_approvals.add(approval_token)

    def t5_purge_old_backups(self, retention_days: int, approval_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Permanently purges database snapshots older than retention_days.
        Requires explicit Human-in-the-Loop (HITL) approval token.
        """
        expected_token = f"APPROVE_PURGE_BACKUPS_{retention_days}D"
        if approval_token not in self.hitl_approvals and approval_token != expected_token:
            raise HumanApprovalRequired(
                f"T5 Operation Blocked: Purging recovery snapshots requires Human approval token '{expected_token}'."
            )
        return {
            "tier": "T5",
            "action": f"purge_backups_older_than_{retention_days}_days",
            "status": "executed_with_human_authorization"
        }

    def t5_firewall_lockdown(self, allow_ssh_first: bool, approval_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Enables host firewall (UFW).
        Can sever operator connectivity if SSH is not verified first.
        """
        if not allow_ssh_first:
            raise PolicyViolation("CRITICAL LOCKOUT HAZARD: Cannot enable firewall without allowing SSH port 22 first!")

        expected_token = "APPROVE_FIREWALL_LOCKDOWN"
        if approval_token not in self.hitl_approvals and approval_token != expected_token:
            raise HumanApprovalRequired(
                f"T5 Operation Blocked: Enabling perimeter firewall requires Human approval token '{expected_token}'."
            )
        return {
            "tier": "T5",
            "action": "ufw --force enable",
            "status": "firewall_active"
        }
