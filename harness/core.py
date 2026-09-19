"""Harness Core Orchestrator for Deterministic Change Intelligence.

Coordinates structural discovery, blast-radius calculation, structured change manifests,
change-surface validation, tiered execution budgets, and cross-artifact contract checks.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.tools import DeploymentTools
from harness.policy import PolicyEngine
from harness.graph import DeploymentDependencyGraph
from harness.discovery import discover_repository
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestValidationError
from harness.impact import ImpactAnalyzer, ManifestIncompleteError
from harness.context_builder import ContextBuilder
from harness.contracts import CrossArtifactContractEngine


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
        self.tools = DeploymentTools(self.secrets, self.state, self.manifest_registry)

        # Dynamic Discovery & Intelligence
        self.graph = discover_repository(self.repo_root)
        self.impact_analyzer = ImpactAnalyzer(self.graph)
        self.context_builder = ContextBuilder(self.repo_root, self.graph)
        self.contract_engine = CrossArtifactContractEngine(self.repo_root, self.graph)

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
        """Submits, validates impact against discovered dependencies, and freezes a ChangeManifest."""
        self.record_step(token_count=100)
        self.refresh_graph()

        # 1. Register candidate manifest
        manifest = self.manifest_registry.submit_manifest(
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
            raise err

        return manifest

    def amend_change_manifest(
        self,
        manifest_id: str,
        new_targets: Optional[List[str]] = None,
        new_dependencies: Optional[List[str]] = None,
        amendment_reason: str = ""
    ) -> ChangeManifest:
        """Amends an existing manifest. Automatically invalidates any prior HITL approvals."""
        self.record_step(token_count=50)
        self.refresh_graph()
        manifest = self.manifest_registry.amend_manifest(
            manifest_id=manifest_id,
            new_targets=new_targets,
            new_dependencies=new_dependencies,
            amendment_reason=amendment_reason
        )

        # Re-verify impact
        valid, err = self.impact_analyzer.verify_manifest_impact(manifest)
        if not valid and err:
            raise err

        return manifest

    def record_step(self, token_count: int = 150):
        self.current_turns += 1
        self.consumed_tokens += token_count
        if self.current_turns > self.max_turns:
            raise HarnessExecutionBudgetExceeded(f"Step budget of {self.max_turns} turns exceeded.")
        if self.consumed_tokens > self.max_tokens:
            raise HarnessExecutionBudgetExceeded(f"Token budget of {self.max_tokens} tokens exceeded.")

    def execute_plan_step(self, tool_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Validates safety invariants before executing any tool."""
        self.record_step()

        # 1. Audit text payloads for raw secrets
        for k, v in kwargs.items():
            if isinstance(v, str):
                self.policy.inspect_for_raw_secrets(v)
                self.policy.validate_command_safety(v)

        # 2. Route to tiered tool contract
        if not hasattr(self.tools, tool_name):
            raise AttributeError(f"Tool '{tool_name}' is not recognized in tiered contracts.")

        tool_method = getattr(self.tools, tool_name)
        result = tool_method(**kwargs)

        # 3. Mask any accidental output leaks
        if isinstance(result, dict):
            for k, v in result.items():
                if isinstance(v, str):
                    result[k] = self.secrets.mask_text(v)

        return result
