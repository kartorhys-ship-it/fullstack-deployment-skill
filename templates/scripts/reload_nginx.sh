#!/usr/bin/env bash
# /var/www/webapp/infrastructure/scripts/reload_nginx.sh
# Validates Nginx configuration syntax before issuing a reload signal
set -euo pipefail

echo "Testing Nginx configuration syntax..."
if sudo nginx -t; then
    echo "Configuration valid. Reloading Nginx daemon..."
    sudo systemctl reload nginx
    echo "Nginx successfully reloaded."
else
    echo "ERROR: Nginx configuration test failed! Aborting reload to protect availability." >&2
    exit 1
fi
