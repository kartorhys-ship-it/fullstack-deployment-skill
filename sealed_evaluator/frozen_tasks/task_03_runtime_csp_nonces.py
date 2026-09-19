"""
Sealed Frozen Evaluation Task 03: Dynamic CSP Nonces & SPA Soft-404 Avoidance
Evaluates cryptographic nonce generation per response and correct SPA fallback routing.
"""

TASK_PROMPT = """
Configure Nginx and the web application to enforce strict Content Security Policy using
per-response nonces for scripts, while hosting a Vite React Single Page Application that
must not suffer from soft-404 JSON parsing bugs on deep routes.
"""

def evaluate(agent_response: str) -> dict:
    checks = {
        "dynamic_nonce_per_request": "nonce" in agent_response.lower() and ("request" in agent_response.lower() or "random" in agent_response.lower()),
        "csp_header_format": "Content-Security-Policy" in agent_response and "'nonce-" in agent_response,
        "spa_try_files": "try_files $uri $uri/ /index.html" in agent_response,
        "api_location_separate": "location /api/" in agent_response,
        "api_does_not_fallback_to_html": "proxy_pass" in agent_response and ("/api/" in agent_response),
        "nosniff_header": "X-Content-Type-Options" in agent_response
    }
    
    score = sum(1 for v in checks.values() if v) / len(checks)
    passed = score >= 0.83
    safety_violation = "unsafe-inline" in agent_response and "script-src" in agent_response and "'nonce-" not in agent_response
    
    return {
        "task_id": "frozen_03_runtime_csp_nonces",
        "passed": passed and not safety_violation,
        "score": score,
        "safety_violation": safety_violation
    }
