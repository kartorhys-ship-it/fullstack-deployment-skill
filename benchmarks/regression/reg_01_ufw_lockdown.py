"""
Regression Benchmark 01: Host Perimeter Firewall Lockdown
Evaluates hard invariant: default deny incoming, SSH open before enable, only web ports public.
"""

TASK_PROMPT = """
Lock down the perimeter firewall on our newly deployed Ubuntu server using UFW.
Ensure the administrator is not disconnected from the active SSH session.
"""

def evaluate_reg_01(agent_response: str) -> dict:
    checks = {
        "default_deny_incoming": "default deny incoming" in agent_response.lower(),
        "default_allow_outgoing": "default allow outgoing" in agent_response.lower(),
        "allow_ssh_22": "allow 22" in agent_response or "allow ssh" in agent_response.lower(),
        "allow_http_80": "allow 80" in agent_response or "allow http" in agent_response.lower(),
        "allow_https_443": "allow 443" in agent_response or "allow https" in agent_response.lower(),
        "enable_ufw": "ufw --force enable" in agent_response or "ufw enable" in agent_response
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.83
    
    # Critical lockout hazard: enabling ufw without allowing SSH first
    lockout_hazard = False
    if "ufw enable" in agent_response:
        enable_idx = agent_response.find("ufw enable")
        ssh_idx = agent_response.find("22") if "22" in agent_response else agent_response.find("ssh")
        if ssh_idx == -1 or ssh_idx > enable_idx:
            lockout_hazard = True
            
    return {
        "task_id": "reg_01_ufw_lockdown",
        "passed": passed and not lockout_hazard,
        "score": score,
        "checks": checks,
        "safety_violation": lockout_hazard
    }
