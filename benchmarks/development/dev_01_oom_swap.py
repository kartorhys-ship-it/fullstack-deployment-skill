"""
Development Benchmark 01: OOM Crash Prevention & Swap Provisioning
Evaluates agent's ability to diagnose memory exhaustion and safely configure swap.
"""

TASK_PROMPT = """
Our 2GB RAM Ubuntu 24.04 droplet crashes during 'pnpm build' with exit code 137 (Killed).
Inspect system state, diagnose the root cause, and implement a permanent swap memory solution
following production security standards.
"""

def evaluate_dev_01(agent_response: str) -> dict:
    checks = {
        "diagnosed_oom": any(term in agent_response.lower() for term in ["oom", "out of memory", "killed", "137", "ram"]),
        "sized_appropriately": any(sz in agent_response for sz in ["2G", "4G", "2048", "4096"]),
        "secure_permissions": "chmod 600" in agent_response or "0600" in agent_response,
        "formatted_swap": "mkswap" in agent_response,
        "activated_swap": "swapon" in agent_response,
        "persisted_fstab": "/etc/fstab" in agent_response and "swap" in agent_response,
        "swappiness_tuned": "swappiness" in agent_response.lower()
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.85
    
    return {
        "task_id": "dev_01_oom_swap",
        "passed": passed,
        "score": score,
        "checks": checks,
        "safety_violation": "chmod 777" in agent_response or "chmod 666" in agent_response
    }
