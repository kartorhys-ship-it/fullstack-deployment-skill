#!/usr/bin/env bash
# /var/www/webapp/infrastructure/scripts/gunicorn_start.sh
set -euo pipefail

NAME="webapp"
PROJECT_DIR="/var/www/webapp/current/backend"
VENV_DIR="/var/www/webapp/current/backend/.venv"
SOCKET="/var/www/webapp/shared/run/gunicorn.sock"
USER="deployer"
GROUP="www-data"
NUM_WORKERS=3
WORKER_CLASS="uvicorn.workers.UvicornWorker"
TIMEOUT=60
LOG_DIR="/var/www/webapp/shared/logs"

cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"

mkdir -p "$(dirname "$SOCKET")" "$LOG_DIR"
chown -R "$USER:$GROUP" "$(dirname "$SOCKET")" "$LOG_DIR"

exec gunicorn main:app \
    --name "$NAME" \
    --workers "$NUM_WORKERS" \
    --worker-class "$WORKER_CLASS" \
    --user "$USER" \
    --group "$GROUP" \
    --bind "unix:$SOCKET" \
    --timeout "$TIMEOUT" \
    --log-level info \
    --access-logfile "$LOG_DIR/gunicorn_access.log" \
    --error-logfile "$LOG_DIR/gunicorn_error.log"
