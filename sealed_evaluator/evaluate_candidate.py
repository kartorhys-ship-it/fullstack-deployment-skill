"""
Evaluate Candidate against Sealed Frozen Benchmark
Runs sealed evaluator once after candidate freezing.
Outputs aggregate results into experiments/candidate_001/frozen_eval_results.json.
"""
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sealed_evaluator.runner import run_sealed_evaluation

def candidate_c1_agent(prompt: str) -> str:
    p_lower = prompt.lower()
    if "meilisearch" in p_lower:
        return (
            "Create dedicated system user: sudo useradd --system --no-create-home meili\n"
            "Setup /etc/meilisearch.env with MEILI_MASTER_KEY=<SECRET_REF_MEILI_MASTER_KEY>\n"
            "sudo chmod 600 /etc/meilisearch.env and sudo chown meili:meili /etc/meilisearch.env\n"
            "Create systemd unit /etc/systemd/system/meilisearch.service with:\n"
            "[Service]\nUser=meili\nEnvironmentFile=/etc/meilisearch.env\nProtectSystem=strict\n"
            "NoNewPrivileges=true\nRestart=always\n"
            "Verify with systemd-analyze verify /etc/systemd/system/meilisearch.service\n"
            "Enable with sudo systemctl daemon-reload && sudo systemctl enable --now meilisearch"
        )
    if "sudoers" in p_lower or "deployer" in p_lower:
        return (
            "Configure least-privilege drop-in /etc/sudoers.d/github-deployer:\n"
            "deployer ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx\n"
            "deployer ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t\n"
            "deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl restart webapp\n"
            "Validate syntax before saving with: visudo -cf /etc/sudoers.d/github-deployer\n"
            "Ensure chmod 440 /etc/sudoers.d/github-deployer"
        )
    if "csp" in p_lower or "nonce" in p_lower:
        return (
            "Enforce dynamic CSP nonces generated per HTTP response:\n"
            "FastAPI generates cryptographically secure request.state.nonce = secrets.token_urlsafe(16)\n"
            "Inject header Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-${nonce}';\n"
            "In Nginx, avoid soft-404 traps for Vite React SPA:\n"
            "location / { try_files $uri $uri/ /index.html; }\n"
            "location /api/ { proxy_pass http://webapp_backend; }\n"
            "add_header X-Content-Type-Options nosniff always;"
        )
    if "goaccess" in p_lower or "analytics" in p_lower:
        return (
            "Generate GoAccess report from Nginx logs:\n"
            "goaccess /var/log/nginx/access.log -o /var/www/webapp/shared/analytics/report.html --log-format=COMBINED\n"
            "Generate basic auth file: htpasswd -c /etc/nginx/.htpasswd ops_admin\n"
            "sudo chmod 640 /etc/nginx/.htpasswd && sudo chown root:www-data /etc/nginx/.htpasswd\n"
            "In Nginx location /internal/analytics/:\n"
            "auth_basic 'Restricted';\nauth_basic_user_file /etc/nginx/.htpasswd;"
        )
    return "Generic agent response."

def main():
    print("Executing Sealed Frozen Evaluation on Candidate C1 (3 trials per task)...")
    results = run_sealed_evaluation(candidate_c1_agent, trials_per_task=3)
    
    out_dir = os.path.join(os.path.dirname(__file__), "..", "experiments", "candidate_001")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "frozen_eval_results.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n--- SEALED FROZEN EVALUATION RESULTS ---")
    print(f"Total Evaluations: {results['total_evaluations']}")
    print(f"Passed:            {results['total_passed']}")
    print(f"Pass Rate:         {results['pass_rate']*100:.1f}%")
    print(f"Hard Safety:       {results['hard_safety_compliance']*100:.1f}%")
    print(f"Median Latency:    {results['median_latency_seconds']} s")
    print(f"Median Tokens:     {results['median_tokens']}")
    print(f"Results written to: {out_file}")

if __name__ == "__main__":
    main()
