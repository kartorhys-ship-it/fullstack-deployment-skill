# Python Virtual Environments & Gunicorn/Uvicorn Architecture

Production execution patterns for FastAPI / ASGI applications using Gunicorn as the process supervisor and Uvicorn workers for asynchronous event handling.

---

## 1. Virtual Environment Isolation (PEP 668 Compliance)

Ubuntu 24.04 and 22.04 enforce PEP 668. Never run `pip install` globally or using `sudo`.

```bash
# In release directory:
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

---

## 2. Gunicorn + Uvicorn Worker Model

For ASGI applications (FastAPI), Gunicorn acts as a master process manager managing HTTP sockets, signals, and worker life cycles, while `uvicorn.workers.UvicornWorker` executes the async Python code.

### Sizing Heuristic vs Real Calibrations
* *Initial Upper Bound*: `workers = (2 * CPU_CORES) + 1`
* *Memory Constraints*: Each Python worker consumes between 60MB and 150MB of RAM depending on dependencies.
  - On a 1GB/2GB VPS, running `(2*2)+1 = 5` workers might consume up to 750MB RAM, leaving inadequate space for Nginx, Meilisearch, and OS cache.
  - Recommended starting baseline for 1GB–2GB VPS: **2 to 3 workers**.
  - Calibrate under Locust load testing, observing RAM/CPU via `btop`.

### Production Runner Script (`infrastructure/scripts/gunicorn_start.sh`)
```bash
#!/usr/bin/env bash
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

# Ensure socket & log directories exist with appropriate ownership
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
```

### Safety Invariants
1. Permissions on the UNIX socket directory must allow group `www-data` to read and write, or Nginx will return `502 Bad Gateway (13: Permission denied)`.
2. Master process must execute under unprivileged user `deployer` and group `www-data`.
