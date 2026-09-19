# Security Headers, Dynamic CSP Nonces, and SPA Soft-404 Avoidance

Hardening HTTP responses at the reverse proxy layer while accommodating modern Single Page Applications (SPA).

---

## 1. HTTP Security Headers Snippet (`/etc/nginx/snippets/security-headers.conf`)

Include these headers across all server blocks:

```nginx
# Prevent MIME-type sniffing
add_header X-Content-Type-Options "nosniff" always;

# Defend against clickjacking (deny iframe embedding)
add_header X-Frame-Options "DENY" always;

# Control referrer leakage
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# Restrict browser features
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;

# HTTP Strict Transport Security (HSTS) - 1 year with subdomains and preload
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

---

## 2. Dynamic Content Security Policy (CSP) Nonce Handling

A static CSP header in Nginx with `'unsafe-inline'` defeats script injection protection. Real CSP nonces must be cryptographically random per HTTP response.

### Architectural Flow:
1. Nginx or FastAPI backend generates a cryptographically random nonce per request.
2. If backend renders HTML:
   - FastAPI generates `$request_id` or `base64(urandom(16))` as `request.state.csp_nonce`.
   - Injects nonce into script tags: `<script nonce="{{ csp_nonce }}">...</script>`.
   - Injects header: `Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{{ csp_nonce }}'; ...`
3. If static SPA (Vite/React):
   - For purely static builds without SSR, use strict hash-based (`'sha256-...'`) or host-based CSP:
     ```nginx
     add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://api.yourdomain.com;" always;
     ```

---

## 3. Eliminating SPA Soft-404 Traps

In client-side routed SPAs (React Router / Vue Router), requesting deep paths like `/dashboard/analytics` directly from the browser will return a 404 from Nginx unless fallback routing is configured.

### Correct Nginx SPA Routing
```nginx
location / {
    root /var/www/webapp/current/frontend/dist;
    index index.html;
    try_files $uri $uri/ /index.html;
}

# API endpoints must NOT fallback to index.html (which causes soft-404 JSON parsing errors)
location /api/ {
    proxy_pass http://webapp_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```
If an API endpoint does not exist, it will properly return HTTP `404 Not Found` with JSON error payload, not an HTML page.
