#!/usr/bin/env bash
# /var/www/webapp/infrastructure/scripts/monthly_cleanup.sh
# Routine disk hygiene: journald logs, apt cache, old rotated nginx logs
set -euo pipefail

echo "Starting monthly maintenance cleanup..."

# 1. Vacuum systemd journal logs to retain max 500MB
sudo journalctl --vacuum-size=500M

# 2. Clean apt package cache
sudo apt-get autoremove -y
sudo apt-get clean

# 3. Clean temporary files
sudo find /tmp -type f -atime +10 -delete

echo "Monthly cleanup successfully finished."
