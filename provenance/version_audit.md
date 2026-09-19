# Upstream Knowledge & Version Normalization Audit

This document details the fidelity and compatibility audit performed on the deployment material extracted from Imad Saddik's 10.4-hour course and handbook against modern production environments (Ubuntu 24.04 LTS Noble Numbat and Ubuntu 22.04 LTS Jammy Jellyfish).

---

## 1. Operating System: Ubuntu 22.04 vs 24.04 LTS

| Component / Subsystem | Course / Handbook Baseline (Ubuntu 22.04) | Audited Target (Ubuntu 24.04 LTS) | Adaptation in This Skill |
| :--- | :--- | :--- | :--- |
| **Python Environment** | Global or user `pip install` allowed | PEP 668: `EXTERNALLY-MANAGED` blocks direct `pip install` | Mandatory Python virtual environments (`venv`) or `pipx` for CLI tools. Explicitly validated in harness. |
| **OpenSSH Server** | Standard `sshd_config` directives | Ubuntu 24.04 uses systemd socket activation for ssh (`ssh.socket` / `ssh.service`) | Skill documents and validates both `systemctl restart ssh` and `systemctl reload ssh.socket` compatibility. |
| **AppArmor / Security** | Standard AppArmor profiles | Ubuntu 24.04 restricts unprivileged user namespaces | Meilisearch and webapp systemd units configured with `NoNewPrivileges=true` and explicit user boundaries. |

---

## 2. Nginx Reverse Proxy Modernization

* **HTTP/2 Syntax Deprecation & Distro Compatibility**:
  - *Context*: Nginx 1.25.1 introduced the standalone `http2 on;` directive and deprecated the `listen ... http2` parameter.
  - *Distro Reality Check*: The default package repository in **Ubuntu 24.04 LTS (Noble Numbat)** provides **Nginx 1.24.0**, which does NOT support `http2 on;` and will fail validation (`nginx -t`) with `unknown directive "http2"`.
  - *Normalized Invariant*: To guarantee out-of-the-box syntax compatibility across stock Ubuntu LTS distributions (Ubuntu 22.04 LTS and 24.04 LTS) without requiring external mainline PPAs, production templates use:
    ```nginx
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    ```
* **Cloudflare Real-IP Restoration**:
  - *Critical Security Invariant*: Trusting `CF-Connecting-IP` without restricting `set_real_ip_from` to Cloudflare's exact public IP blocks allows malicious clients to spoof any arbitrary IP in requests directly to the origin.
  - *Normalized Directive*: Explicit inclusion of Cloudflare IPv4 (`173.245.48.0/20`, `103.21.244.0/22`, etc.) and IPv6 subnets, coupled with `real_ip_header CF-Connecting-IP;`.

---

## 3. Worker Sizing Heuristics vs Absolute Rules

* *Course Rule of Thumb*: Gunicorn workers = `(2 * CPU cores) + 1`.
* *Engineering Audit Correction*:
  - On a 1GB–2GB RAM VPS, running 5 workers (`(2 * 2) + 1`) for a memory-intensive FastAPI application can quickly trigger the Linux OOM (Out Of Memory) killer.
  - For asynchronous I/O frameworks (FastAPI on Uvicorn workers), worker scaling is I/O-bound rather than purely CPU-bound.
  - *Normalized Guidance*: Treat `(2 * CPU) + 1` as an upper-bound initial estimate; mandate swapfile memory provisioning (2GB–4GB) and calibrate worker count via Locust load testing while observing memory thresholds via `btop`.

---

## 4. Meilisearch v1.x Invariants

* **Master Key Length**: Meilisearch v1.x strictly requires a master key of at least **16 bytes**. Keys under 16 bytes will fail to start the engine.
* **System Isolation**: Meilisearch runs under a dedicated unprivileged system user (`meili:meili`) with its database directory in `/var/lib/meilisearch` (permissions `0750`).
* **Environment Sourcing**: The master key is passed via `/etc/meilisearch.env` (permissions `0600` owned by `meili:meili`), never hard-coded in the systemd service file or CLI flags visible in `ps aux`.

---

## 5. Summary of Resolutions

All templates and reference guides in this repository incorporate these verified, modern invariants. Every extracted pattern has been normalized to run cleanly on modern production Linux hosts.
