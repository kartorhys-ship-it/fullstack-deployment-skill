# Self-Hosted Meilisearch & Hardened Systemd Service

Deploying and isolating Meilisearch as a dedicated system daemon on Ubuntu.

---

## 1. Dedicated Unprivileged System User

Never execute Meilisearch as `root` or `deployer`. Create an unprivileged system user with no login shell and no home directory:

```bash
# Create system user
sudo useradd --system --no-create-home --user-group meili

# Setup database & configuration directory
sudo mkdir -p /var/lib/meilisearch/data /var/lib/meilisearch/dumps /var/lib/meilisearch/snapshots
sudo chown -R meili:meili /var/lib/meilisearch
sudo chmod 750 /var/lib/meilisearch
```

---

## 2. Master Key Security & Environment File

Meilisearch v1.x requires a master key of at least **16 bytes**.
Generate a cryptographically secure key:
```bash
openssl rand -base64 32
```

Store the key in `/etc/meilisearch.env` (accessible ONLY by `meili`):
```ini
# /etc/meilisearch.env
MEILI_ENV="production"
MEILI_DB_PATH="/var/lib/meilisearch/data"
MEILI_DUMPS_PATH="/var/lib/meilisearch/dumps"
MEILI_SNAPSHOTS_PATH="/var/lib/meilisearch/snapshots"
MEILI_HTTP_ADDR="127.0.0.1:7700"
MEILI_MASTER_KEY="<SECRET_REF_MEILI_MASTER_KEY>"
MEILI_NO_ANALYTICS=true
```

Set strict permissions:
```bash
sudo chown meili:meili /etc/meilisearch.env
sudo chmod 600 /etc/meilisearch.env
```

---

## 3. Hardened Systemd Service (`/etc/systemd/system/meilisearch.service`)

```ini
[Unit]
Description=Meilisearch Full-Text Search Engine
After=network.target

[Service]
Type=simple
User=meili
Group=meili
EnvironmentFile=/etc/meilisearch.env
ExecStart=/usr/local/bin/meilisearch
Restart=always
RestartSec=5s

# Security hardening directives
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/meilisearch
PrivateTmp=true
NoNewPrivileges=true
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
```

### Verification Preconditions:
```bash
# Lint service unit
systemd-analyze verify /etc/systemd/system/meilisearch.service

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable --now meilisearch
sudo systemctl status meilisearch

# Test health check locally
curl -s http://127.0.0.1:7700/health | grep -q 'available'
```

---

## 4. Automated Daily Snapshot Cron

Create `/etc/cron.daily/meilisearch-snapshot`:
```bash
#!/usr/bin/env bash
set -euo pipefail
source /etc/meilisearch.env
curl -s -X POST "http://127.0.0.1:7700/snapshots" \
  -H "Authorization: Bearer $MEILI_MASTER_KEY" > /dev/null
```
chmod 700 /etc/cron.daily/meilisearch-snapshot
