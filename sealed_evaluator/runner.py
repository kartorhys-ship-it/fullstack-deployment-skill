"""
Sealed Evaluator Runner
Executes frozen evaluation tasks in isolation without leaking task diagnostics or prompts.
"""
import time
import os
import sys
import statistics
from typing import Callable, Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sealed_evaluator.frozen_tasks.task_01_meilisearch_systemd import TASK_PROMPT as P1, evaluate as E1
from sealed_evaluator.frozen_tasks.task_02_least_privilege_visudo import TASK_PROMPT as P2, evaluate as E2
from sealed_evaluator.frozen_tasks.task_03_runtime_csp_nonces import TASK_PROMPT as P3, evaluate as E3
from sealed_evaluator.frozen_tasks.task_04_goaccess_auth_gateway import TASK_PROMPT as P4, evaluate as E4

TASKS = [
    (P1, E1),
    (P2, E2),
    (P3, E3),
    (P4, E4)
]

def run_sealed_evaluation(agent_fn: Callable[[str], str], trials_per_task: int = 3) -> Dict[str, Any]:
    """
    Executes sealed frozen evaluation.
    Returns ONLY aggregate statistics to prevent leakage.
    """
    total_runs = 0
    total_passed = 0
    safety_violations = 0
    latencies = []
    token_counts = []

    for prompt, eval_fn in TASKS:
        for _ in range(trials_per_task):
            t0 = time.time()
            response = agent_fn(prompt)
            duration = time.time() - t0
            latencies.append(duration)
            
            # Approximate token count (words * 1.3)
            tokens = int(len(response.split()) * 1.33)
            token_counts.append(tokens)

            res = eval_fn(response)
            total_runs += 1
            if res.get("passed", False):
                total_passed += 1
            if res.get("safety_violation", False):
                safety_violations += 1

    pass_rate = round(total_passed / total_runs, 4) if total_runs else 0.0
    safety_rate = round((total_runs - safety_violations) / total_runs, 4) if total_runs else 1.0

    return {
        "suite": "sealed_frozen_eval",
        "total_evaluations": total_runs,
        "total_passed": total_passed,
        "pass_rate": pass_rate,
        "hard_safety_compliance": safety_rate,
        "safety_violations_count": safety_violations,
        "median_latency_seconds": round(statistics.median(latencies), 3) if latencies else 0.0,
        "median_tokens": int(statistics.median(token_counts)) if token_counts else 0
    }

if __name__ == "__main__":
    print("Sealed evaluator runner loaded. Sealed suite contains 4 isolated benchmark tasks.")
