# Web Analytics with GoAccess & System Log Retention

Real-time log analytics without privacy-invasive client JavaScript, secured behind HTTP Basic Authentication.

---

## 1. GoAccess Real-Time HTML Dashboard

GoAccess parses Nginx access logs and compiles interactive visual dashboards.

### Installation
```bash
sudo apt update && sudo apt install -y goaccess apache2-utils
```

### Automated HTML Report Generation via Cron
Create an hourly cron job (`/etc/cron.hourly/update-goaccess`):
```bash
#!/usr/bin/env bash
set -euo pipefail

LOG_FILES="/var/log/nginx/access.log"
OUT_FILE="/var/www/webapp/shared/analytics/report.html"

mkdir -p "$(dirname "$OUT_FILE")"
zcat -f /var/log/nginx/access.log*.gz $LOG_FILES 2>/dev/null | \
goaccess - \
  --log-format=COMBINED \
  --real-time-html=false \
  -o "$OUT_FILE"
```
chmod 755 /etc/cron.hourly/update-goaccess

---

## 2. Securing Analytics with HTTP Basic Auth & Nginx

Never expose system analytics publicly.

```bash
# Generate password file (restricted to www-data)
sudo htpasswd -c /etc/nginx/.htpasswd admin
sudo chmod 640 /etc/nginx/.htpasswd
sudo chown root:www-data /etc/nginx/.htpasswd
```

Nginx location block:
```nginx
location /internal/analytics/ {
    alias /var/www/webapp/shared/analytics/;
    index report.html;
    auth_basic "Authorized Operations Personnel Only";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

---

## 3. Log Retention & Journald Control

Prevent disks from filling up with unconstrained logs:
1. **Nginx Logrotate** (`/etc/logrotate.d/nginx`):
   - Keep 14 days of logs, compressed with `gzip`, delayed compression `delaycompress`.
2. **Systemd Journald Size Cap** (`/etc/systemd/journald.conf`):
   ```ini
   [Journal]
   SystemMaxUse=500M
   RuntimeMaxUse=100M
   ```
   Apply: `sudo systemctl restart systemd-journald`
