"""Harness Core Orchestrator for Deterministic Change Intelligence.

Coordinates structural discovery, blast-radius calculation, structured change manifests,
change-surface validation, execution gating with contract enforcement, and tiered budgets.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.tools import DeploymentTools, ToolContractError
from harness.policy import PolicyEngine
from harness.graph import DeploymentDependencyGraph
from harness.discovery import discover_repository
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestValidationError, ManifestStatus
from harness.impact import ImpactAnalyzer, ManifestIncompleteError
from harness.context_builder import ContextBuilder
from harness.contracts import CrossArtifactContractEngine, ContractViolation
from harness.approvals import TrustedApprovalService


class HarnessExecutionBudgetExceeded(Exception):
    pass


class DeploymentHarness:
    def __init__(self, repo_root: str = ".", max_turns: int = 15, max_tokens: int = 25000):
        self.repo_root = str(Path(repo_root).resolve())
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.current_turns = 0
        self.consumed_tokens = 0

        self.secrets = SecretMasker()
        self.state = StateManager()
        self.policy = PolicyEngine()
        self.manifest_registry = ManifestRegistry()
        self.approval_service = TrustedApprovalService()
        self.tools = DeploymentTools(
            self.secrets,
            self.state,
            self.manifest_registry,
            self.approval_service,
            repo_root=self.repo_root
        )

        # Dynamic Discovery & Intelligence
        self.graph = discover_repository(self.repo_root)
        self.impact_analyzer = ImpactAnalyzer(self.graph)
        self.context_builder = ContextBuilder(self.repo_root, self.graph)
        self.contract_engine = CrossArtifactContractEngine(self.repo_root, self.graph)

        # Agent-facing capability gateway facade
        self.gateway = AgentToolGateway(self)

    def refresh_graph(self):
        """Re-scans the repository to ensure graph reflects actual filesystem truth."""
        self.graph = discover_repository(self.repo_root)
        self.impact_analyzer = ImpactAnalyzer(self.graph)
        self.context_builder = ContextBuilder(self.repo_root, self.graph)
        self.contract_engine = CrossArtifactContractEngine(self.repo_root, self.graph)

    def assemble_agent_context(self, task: str, target_files: List[str]) -> Dict[str, Any]:
        """Builds structurally bounded context for the agent."""
        self.refresh_graph()
        return self.context_builder.assemble_context(task, target_files)

    def submit_change_manifest(
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
        """Transactionally submits, validates, and accepts a ChangeManifest.

        If impact analysis or contracts fail, manifest is marked REJECTED and discarded.
        """
        self.record_step(token_count=100)
        self.refresh_graph()

        # 1. Create manifest in PENDING_VALIDATION state
        manifest = self.manifest_registry.create_pending_manifest(
            intent=intent,
            targets=targets,
            expected_dependencies=expected_dependencies,
            invariants=invariants,
            verification=verification,
            rollback=rollback,
            full_rewrite=full_rewrite,
            rewrite_justification=rewrite_justification
        )

        # 2. Check Declared vs. Discovered Impact Gap
        valid, err = self.impact_analyzer.verify_manifest_impact(manifest)
        if not valid and err:
            self.manifest_registry.reject_manifest(manifest.manifest_id, str(err))
            raise err

        # 3. Fail-closed contract check
        for inv in invariants:
            res, rsn = self.contract_engine.verify_contract(inv)
            if not res:
                self.manifest_registry.reject_manifest(manifest.manifest_id, f"Contract failure: {rsn}")
                raise ContractViolation(f"Manifest rejected due to contract failure on '{inv}': {rsn}")

        # 4. Accept manifest
        return self.manifest_registry.accept_manifest(manifest.manifest_id)

    def amend_change_manifest(
        self,
        manifest_id: str,
        new_targets: Optional[List[str]] = None,
        new_dependencies: Optional[List[str]] = None,
        amendment_reason: str = ""
    ) -> ChangeManifest:
        """Transactionally amends an existing manifest.

        Clones candidate; if impact validation fails, rolls back amendment leaving original intact!
        """
        self.record_step(token_count=50)
        self.refresh_graph()

        # 1. Stage candidate clone in AMENDING state
        candidate = self.manifest_registry.stage_amendment(
            manifest_id=manifest_id,
            new_targets=new_targets,
            new_dependencies=new_dependencies,
            amendment_reason=amendment_reason
        )

        # 2. Verify candidate impact
        valid, err = self.impact_analyzer.verify_manifest_impact(candidate)
        if not valid and err:
            self.manifest_registry.rollback_amendment(manifest_id, str(err))
            raise err

        # 3. Commit amendment
        accepted = self.manifest_registry.commit_amendment(manifest_id)
        return accepted

    def record_step(self, token_count: int = 150):
        self.current_turns += 1
        self.consumed_tokens += token_count
        if self.current_turns > self.max_turns:
            raise HarnessExecutionBudgetExceeded(f"Step budget of {self.max_turns} turns exceeded.")
        if self.consumed_tokens > self.max_tokens:
            raise HarnessExecutionBudgetExceeded(f"Token budget of {self.max_tokens} tokens exceeded.")

    def execute_plan_step(self, tool_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Validates safety invariants, manifest state, and contracts before executing any tool."""
        self.record_step()

        # 1. Audit text payloads for raw secrets and dangerous commands
        for k, v in kwargs.items():
            if isinstance(v, str):
                self.policy.inspect_for_raw_secrets(v)
                self.policy.validate_command_safety(v)

        # 2. Enforcement Gate: For T3, T4, T5 tools, actively verify manifest invariants
        if any(tool_name.startswith(prefix) for prefix in ("t3_", "t4_", "t5_")):
            manifest_id = kwargs.get("manifest_id")
            if not manifest_id:
                raise ToolContractError(f"Operation '{tool_name}' blocked: Missing required 'manifest_id'.")

            manifest = self.manifest_registry.get_manifest(manifest_id)
            if not manifest or manifest.status != ManifestStatus.ACCEPTED:
                raise ToolContractError(
                    f"Operation '{tool_name}' blocked: Manifest '{manifest_id}' is not in ACCEPTED state."
                )

            # Actively enforce contracts before mutation
            self.contract_engine.verify_all_invariants(manifest.invariants)

        # 3. Route to tiered tool contract
        if not hasattr(self.tools, tool_name):
            raise AttributeError(f"Tool '{tool_name}' is not recognized in tiered contracts.")

        tool_method = getattr(self.tools, tool_name)
        result = tool_method(**kwargs)

        # 4. Mask any accidental output leaks
        if isinstance(result, dict):
            for k, v in result.items():
                if isinstance(v, str):
                    result[k] = self.secrets.mask_text(v)

        return result


class AgentToolGateway:
    """Agent-facing capability facade.
    
    The agent LLM interacts ONLY with this gateway. Enforces capability security:
    1. Direct access to internal tools, approval service, state manager, and manifest registry is blocked.
    2. All operations route strictly through harness execution budgets, safety inspection, and contract gates.
    """

    def __init__(self, harness: DeploymentHarness):
        self._harness = harness

    def submit_manifest(self, **kwargs) -> ChangeManifest:
        """Submits a structured ChangeManifest through the transactional harness gate."""
        return self._harness.submit_change_manifest(**kwargs)

    def amend_manifest(
        self,
        manifest_id: str,
        added_targets: List[str],
        added_invariants: Optional[List[str]] = None
    ) -> ChangeManifest:
        """Amends an existing manifest, recalculating blast radius and invalidating prior approvals."""
        return self._harness.amend_change_manifest(manifest_id, added_targets, added_invariants)

    def assemble_context(self, task: str, target_files: List[str]) -> Dict[str, Any]:
        """Assembles structurally bounded context with graph neighbors and invariant rules."""
        return self._harness.assemble_agent_context(task, target_files)

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Executes a tiered tool operation with mandatory contract enforcement and policy inspection."""
        return self._harness.execute_plan_step(tool_name, kwargs)

    def get_manifest_status(self, manifest_id: str) -> Optional[str]:
        """Returns current lifecycle status of a manifest."""
        m = self._harness.manifest_registry.get_manifest(manifest_id)
        return m.status.value if m else None

