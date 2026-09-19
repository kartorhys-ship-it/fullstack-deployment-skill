# Modular GitHub Actions CI/CD & Least-Privilege Sudoers

Automating testing, security scanning, packaging, and zero-downtime deployment.

---

## 1. Modular CI Gates

Before any deployment workflow can trigger, code merged to `main` must pass automated quality gates:
1. **Linting & Formatting**: `ruff check`, `black --check`, `eslint`, `prettier --check`.
2. **Software Composition Analysis (SCA)**:
   - Python: `pip-audit`
   - Frontend: `pnpm audit --prod`
3. **Static Application Security Testing (SAST)**:
   - Python: `bandit -r backend/ -lll`
4. **End-to-End & Integration Testing**:
   - Integration: Live Meilisearch service running in GitHub Actions container.
   - E2E: `playwright test`.
5. **Dynamic Application Security Testing (DAST)**:
   - Scheduled OWASP ZAP baseline / full scan against staging environment.

---

## 2. Least-Privilege Visudo for CI/CD Automation

The deployment runner connects via SSH as user `deployer`. Automation must never have unrestricted `ALL=(ALL) NOPASSWD: ALL` root privileges.

### Hardened Visudo Drop-In (`/etc/sudoers.d/github-deployer`)
```sudoers
# /etc/sudoers.d/github-deployer
# Strictly whitelist only commands required for graceful deployment restarts

deployer ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
deployer ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl reread
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl update
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl restart webapp
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl status webapp
deployer ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart meilisearch
```

### Safety Precondition:
Always validate syntax before installing sudoers drop-ins:
```bash
visudo -cf /etc/sudoers.d/github-deployer
```
A syntax error in any `/etc/sudoers.d/` file can break `sudo` host-wide.
