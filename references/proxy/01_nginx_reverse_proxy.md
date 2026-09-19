# Nginx Reverse Proxy Architecture & 502 Bad Gateway Troubleshooting

Nginx sits on the outer perimeter, terminating TLS, buffering slow clients, serving static assets, and reverse-proxying API calls to the ASGI backend.

---

## 1. Upstream Socket vs Port Proxying

### UNIX Domain Socket (Recommended for Single-Host)
* Eliminates TCP loopback overhead, port exhaustion, and local network latency.
* Upstream directive:
  ```nginx
  upstream webapp_backend {
      server unix:/var/www/webapp/shared/run/gunicorn.sock fail_timeout=0;
  }
  ```

---

## 2. The Complete 502 Bad Gateway Diagnosis Decision Tree

When Nginx returns `502 Bad Gateway`, it means Nginx received an invalid response or was unable to connect to the upstream backend.

```
                  502 Bad Gateway Occurred
                             │
            Inspect /var/log/nginx/error.log
                             │
     ┌───────────────────────┴───────────────────────┐
     ▼                                               ▼
"Permission denied"                           "Connection refused" /
(13: Permission denied)                       "No such file or directory"
     │                                               │
     ▼                                               ▼
Socket file permissions.                      Backend is down or dead.
Check:                                        Check:
1. `ls -la /var/www/webapp/shared/run/`        1. `supervisorctl status webapp`
2. Does `www-data` have r+x on all             2. `journalctl -u supervisor -e`
   parent directories?                         3. Check Gunicorn error log:
   `namei -l /var/www/.../gunicorn.sock`          `tail -n 50 shared/logs/gunicorn_error.log`
3. Fix:                                       4. Was process killed by OOM Killer?
   `chmod 755 /var/www/webapp/shared/run`         `dmesg -T | grep -i oom`
   `chown deployer:www-data gunicorn.sock`    5. Fix:
   `chmod 660 gunicorn.sock`                     Address Python exception or provision swap.
```

---

## 3. Preconditions for Nginx Reload

Never execute `systemctl reload nginx` without verifying configuration syntax first!

```bash
# PRECONDITION CHECK:
sudo nginx -t

# ONLY IF EXIT CODE == 0:
sudo systemctl reload nginx
```
An invalid Nginx configuration on a restart can take down all hosted sites immediately.
