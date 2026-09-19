#!/usr/bin/env bash
# Layer B: Native Linux Validation Script
# Tests real Ubuntu 24.04 binaries: nginx -t, sshd -t, visudo -cf, systemd-analyze verify
set -euo pipefail

echo "=========================================================="
echo " Starting Layer B: Native Linux Verification (Ubuntu 24.04)"
echo "=========================================================="

FAILED=0

# 1. Test Nginx Configuration Syntax
echo -n "[1/4] Verifying Nginx configuration syntax (nginx -t)... "
cp /app/templates/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
# Generate self-signed mock cert for test if needed
mkdir -p /etc/letsencrypt/live/example.com
openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
  -keyout /etc/letsencrypt/live/example.com/privkey.pem \
  -out /etc/letsencrypt/live/example.com/fullchain.pem \
  -subj "/CN=example.com" 2>/dev/null || true
touch /etc/nginx/.htpasswd
cp /app/templates/nginx/fullstack-app.conf /etc/nginx/sites-available/webapp.conf
ln -sfn /etc/nginx/sites-available/webapp.conf /etc/nginx/sites-enabled/webapp.conf
rm -f /etc/nginx/sites-enabled/default

if nginx -t 2>/dev/null; then
    echo "PASSED (nginx -t returned 0)"
else
    echo "FAILED"
    nginx -t
    FAILED=1
fi

# 2. Test SSH Daemon Syntax
echo -n "[2/4] Verifying OpenSSH daemon syntax (sshd -t)... "
cat << 'EOF' > /etc/ssh/sshd_config.d/99-hardened.conf
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
EOF

if sshd -t; then
    echo "PASSED (sshd -t returned 0)"
else
    echo "FAILED"
    sshd -t
    FAILED=1
fi

# 3. Test Sudoers Syntax (visudo -cf)
echo -n "[3/4] Verifying sudoers drop-in syntax (visudo -cf)... "
cat << 'EOF' > /etc/sudoers.d/github-deployer
deployer ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
deployer ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl reread
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl update
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl restart webapp
deployer ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl status webapp
EOF
chmod 440 /etc/sudoers.d/github-deployer

if visudo -cf /etc/sudoers.d/github-deployer; then
    echo "PASSED (visudo -cf returned 0)"
else
    echo "FAILED"
    visudo -cf /etc/sudoers.d/github-deployer
    FAILED=1
fi

# 4. Test Systemd Unit File Syntax
echo -n "[4/4] Verifying Systemd Meilisearch unit syntax... "
cp /app/templates/systemd/meilisearch.service /etc/systemd/system/meilisearch.service
touch /etc/meilisearch.env /usr/local/bin/meilisearch
chmod +x /usr/local/bin/meilisearch

if systemd-analyze verify /etc/systemd/system/meilisearch.service 2>&1 | grep -q 'error'; then
    echo "FAILED"
    systemd-analyze verify /etc/systemd/system/meilisearch.service
    FAILED=1
else
    echo "PASSED (systemd unit syntax valid)"
fi

echo "=========================================================="
if [ $FAILED -eq 0 ]; then
    echo " ALL NATIVE LINUX VERIFICATIONS PASSED CLEANLY (4/4)"
    exit 0
else
    echo " NATIVE VERIFICATION ENCOUNTERED ERRORS"
    exit 1
fi
