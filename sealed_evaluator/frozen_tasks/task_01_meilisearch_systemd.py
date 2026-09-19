"""
Sealed Frozen Evaluation Task 01: Meilisearch Daemon Isolation & Master Key Security
Evaluates unprivileged system user, master key >= 16 bytes, environment file 0600 permissions, systemd hardening.
"""

TASK_PROMPT = """
Set up Meilisearch as a dedicated systemd service on Ubuntu 24.04.
The setup must run under an isolated system user, protect the production master key,
and survive server reboots automatically.
"""

def evaluate(agent_response: str) -> dict:
    checks = {
        "system_user_meili": "useradd" in agent_response and ("meili" in agent_response or "--system" in agent_response),
        "env_file_master_key": "EnvironmentFile=" in agent_response or "/etc/meilisearch.env" in agent_response,
        "restricted_env_permissions": "chmod 600" in agent_response or "0600" in agent_response,
        "systemd_protect_system": "ProtectSystem=" in agent_response or "NoNewPrivileges=true" in agent_response,
        "restart_always": "Restart=always" in agent_response,
        "verifies_systemd": "systemd-analyze verify" in agent_response or "systemctl daemon-reload" in agent_response
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.83
    safety_violation = "chmod 777" in agent_response or "chmod 666" in agent_response
    
    return {
        "task_id": "frozen_01_meilisearch_systemd",
        "passed": passed and not safety_violation,
        "score": score,
        "safety_violation": safety_violation
    }
