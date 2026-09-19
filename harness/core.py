"""
Harness Core Orchestrator
Enforces execution budgets, turns, and deterministic gates between LLM reasoning and system execution.
"""
from typing import Dict, Any, Optional, Callable
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.tools import DeploymentTools
from harness.policy import PolicyEngine, PolicyViolation, PreconditionFailure

class HarnessExecutionBudgetExceeded(Exception):
    pass

class DeploymentHarness:
    def __init__(self, max_turns: int = 10, max_tokens: int = 15000):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.current_turns = 0
        self.consumed_tokens = 0

        self.secrets = SecretMasker()
        self.state = StateManager()
        self.tools = DeploymentTools(self.secrets, self.state)
        self.policy = PolicyEngine()

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
