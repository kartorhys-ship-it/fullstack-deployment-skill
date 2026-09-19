# Node.js/pnpm Runtimes and Supervisord Process Supervision

Managing long-running application daemons with automatic restarts, zombie process prevention, and log redirection.

---

## 1. Node.js & pnpm Setup on Ubuntu

Never install Node via outdated distro repositories (`apt install nodejs` often installs obsolete versions). Use NodeSource or nvm/pnpm standalone.

```bash
# Recommended: Standalone pnpm which manages Node versions automatically
curl -fsSL https://get.pnpm.io/install.sh | sh -
source ~/.bashrc
pnpm env use --global 20

# Validate versions
node --version
pnpm --version
```

---

## 2. Supervisord Configuration (`/etc/supervisor/conf.d/webapp.conf`)

Supervisord monitors backend processes, automatically restarting them upon uncaught exceptions or kernel termination.

### Zombie Process Prevention Invariants
When Supervisord stops or restarts a program, child worker processes (e.g. Uvicorn worker forks spawned by Gunicorn) can become orphaned "zombies" if signals are sent only to the parent process.
* **Invariant**: Must specify `stopasgroup=true` and `killasgroup=true`.
* **Invariant**: Must send `stopsignal=QUIT` (graceful worker shutdown).

```ini
[program:webapp]
command=/var/www/webapp/current/infrastructure/scripts/gunicorn_start.sh
directory=/var/www/webapp/current/backend
user=deployer
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/www/webapp/shared/logs/supervisor_webapp.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopsignal=QUIT
stopasgroup=true
killasgroup=true
environment=PATH="/var/www/webapp/current/backend/.venv/bin:%(ENV_PATH)s"
```

### Preconditions for Supervisor Reload
Before executing reload commands:
1. Validate syntax of all configs:
   ```bash
   supervisorctl reread
   ```
2. Apply changes:
   ```bash
   supervisorctl update
   ```
3. Verify process status is `RUNNING`:
   ```bash
   supervisorctl status webapp
   ```
