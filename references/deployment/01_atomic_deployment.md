# Zero-Downtime Atomic Deployments & Automated Rollbacks

Achieving seamless production cutovers with instant recovery on failure using the releases directory pattern.

---

## 1. Directory Structure

```text
/var/www/webapp/
├── current -> /var/www/webapp/releases/20260919_120000   (Symlink to active release)
├── previous -> /var/www/webapp/releases/20260919_110000  (Symlink to previous release)
├── shared/                                              (Persistent state)
│   ├── .env
│   ├── run/
│   │   └── gunicorn.sock
│   └── logs/
│       ├── gunicorn_access.log
│       ├── gunicorn_error.log
│       └── supervisor_webapp.log
└── releases/
    ├── 20260919_110000/                                 (Previous release)
    └── 20260919_120000/                                 (Current release)
```

---

## 2. The Deployment State Machine

```
              BUILD & TEST ARTIFACTS
                        │
                        ▼
             CREATE NEW RELEASE DIR
          (/var/www/webapp/releases/<TS>)
                        │
                        ▼
             SYNC CODE & DEPENDENCIES
                        │
                        ▼
            LINK SHARED .ENV & LOGS
                        │
                        ▼
         PRE-CUTOVER SYNTAX & INTEGRITY CHECK
                        │
       Pass ────────────┴──────────── Fail
        │                             │
        ▼                             ▼
   RECORD PREVIOUS              ABORT DEPLOYMENT
   (link previous)              (delete staged release)
        │
        ▼
   ATOMIC SYMLINK CUTOVER
   (ln -sfn ... current)
        │
        ▼
   GRACEFUL RESTART (T4)
   (supervisorctl restart)
   (nginx -t && reload)
        │
        ▼
   POST-DEPLOY HEALTH CHECK
  (curl http://127.0.0.1/api/health)
        │
  Pass ─┴─ Fail
   │        │
   ▼        ▼
SUCCESS   AUTOMATIC ROLLBACK:
(Prune    1. Relink current -> previous
stale)    2. Graceful reload services
          3. Verify previous health
          4. Raise incident alert
```

---

## 3. Atomic Symlink Switch & Rollback Commands

In Linux, `ln -sfn` provides an atomic directory pointer swap:
```bash
# Atomic switch to new release
ln -sfn "/var/www/webapp/releases/$NEW_TIMESTAMP" /var/www/webapp/current

# If health check fails, execute instant rollback:
echo "Health check failed! Executing immediate rollback to previous release..."
ln -sfn "/var/www/webapp/releases/$PREVIOUS_TIMESTAMP" /var/www/webapp/current
sudo supervisorctl restart webapp
sudo nginx -t && sudo systemctl reload nginx
```
