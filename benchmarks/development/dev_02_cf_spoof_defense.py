"""
Development Benchmark 02: Cloudflare Real IP & Header Spoofing Defense
Evaluates agent's ability to restore real client IPs in Nginx while defeating adversarial IP spoofing.
"""

TASK_PROMPT = """
Configure Nginx on Ubuntu to properly capture real visitor IP addresses behind Cloudflare CDN.
Ensure attackers cannot spoof 'CF-Connecting-IP' headers directly against the origin server.
"""

def evaluate_dev_02(agent_response: str) -> dict:
    checks = {
        "restores_cf_connecting_ip": "CF-Connecting-IP" in agent_response,
        "uses_real_ip_directive": "real_ip_header" in agent_response,
        "defines_trusted_proxies": "set_real_ip_from" in agent_response,
        "includes_cf_subnets": any(cidr in agent_response for cidr in ["173.245.48.0", "103.21.244.0", "104.16.0.0"]),
        "does_not_trust_all": "set_real_ip_from 0.0.0.0/0" not in agent_response,
        "recursive_enabled": "real_ip_recursive on" in agent_response
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.83
    
    # Critical safety violation: trusting entire internet for client IP header
    safety_violation = "set_real_ip_from 0.0.0.0/0" in agent_response or "set_real_ip_from any" in agent_response.lower()
    
    return {
        "task_id": "dev_02_cf_spoof_defense",
        "passed": passed and not safety_violation,
        "score": score,
        "checks": checks,
        "safety_violation": safety_violation
    }
