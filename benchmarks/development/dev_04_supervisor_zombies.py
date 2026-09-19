"""
Development Benchmark 04: Supervisor Zombie Process Prevention
Evaluates agent's ability to prevent orphaned zombie workers during backend restarts.
"""

TASK_PROMPT = """
Whenever we restart our Gunicorn/Uvicorn backend via Supervisord, orphaned worker processes
are left behind consuming RAM, resulting in port conflicts and memory leaks.
Provide a production Supervisord configuration that prevents zombie child processes.
"""

def evaluate_dev_04(agent_response: str) -> dict:
    checks = {
        "stopsignal_quit": "stopsignal=QUIT" in agent_response,
        "stopasgroup_true": "stopasgroup=true" in agent_response.lower(),
        "killasgroup_true": "killasgroup=true" in agent_response.lower(),
        "unprivileged_user": "user=deployer" in agent_response or "user=www-data" in agent_response,
        "autostart_autorestart": "autorestart=true" in agent_response.lower(),
        "log_rotation": "maxbytes" in agent_response.lower()
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.83
    
    safety_violation = "user=root" in agent_response.lower()
    
    return {
        "task_id": "dev_04_supervisor_zombies",
        "passed": passed and not safety_violation,
        "score": score,
        "checks": checks,
        "safety_violation": safety_violation
    }
