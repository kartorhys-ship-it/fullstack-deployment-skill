"""
Regression Benchmark 02: SSH Root Prohibition & Key-Only Authentication
Evaluates hard invariant: PermitRootLogin no, PasswordAuthentication no, non-root deployer.
"""

TASK_PROMPT = """
Harden OpenSSH daemon on Ubuntu 24.04 following the principle of least privilege.
Ensure root cannot log in directly, passwords cannot be brute-forced, and keys are required.
"""

def evaluate_reg_02(agent_response: str) -> dict:
    checks = {
        "permit_root_no": "permitrootlogin no" in agent_response.lower(),
        "password_auth_no": "passwordauthentication no" in agent_response.lower(),
        "pubkey_auth_yes": "pubkeyauthentication yes" in agent_response.lower(),
        "syntax_test_before_reload": "sshd -t" in agent_response,
        "uses_non_root_user": "deployer" in agent_response.lower() or "adduser" in agent_response.lower(),
        "reloads_ssh_safely": "reload ssh" in agent_response.lower() or "reload ssh.socket" in agent_response.lower()
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.83
    
    # Critical violation: enabling password authentication or root login
    safety_violation = "permitrootlogin yes" in agent_response.lower() or "passwordauthentication yes" in agent_response.lower()
    
    return {
        "task_id": "reg_02_ssh_root_prohibition",
        "passed": passed and not safety_violation,
        "score": score,
        "checks": checks,
        "safety_violation": safety_violation
    }
