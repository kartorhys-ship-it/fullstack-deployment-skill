# Cloudflare CDN & Trusted Real-IP Restoration

When using Cloudflare as a reverse proxy/CDN, all incoming connections to Nginx originate from Cloudflare's edge IP addresses. Without proper configuration, rate limiters, fail2ban, and audit logs will see only Cloudflare IPs.

---

## 1. The Real-IP Spoofing Vulnerability

If Nginx naively trusts `CF-Connecting-IP` or `X-Forwarded-For` from ANY client:
* An attacker sending a direct HTTP request to your server's public IP can forge:
  ```http
  CF-Connecting-IP: 1.1.1.1
  ```
* Nginx would log the attacker as `1.1.1.1`, bypassing IP rate limits and poisoning audit logs.

### Hard Security Invariant: Trusted CIDR Boundary
Nginx must trust `CF-Connecting-IP` **exclusively** when the TCP connection originates from a known, published Cloudflare IP subnet.

---

## 2. Production Nginx Configuration (`/etc/nginx/conf.d/cloudflare.conf`)

Include Cloudflare's published CIDR blocks in `/etc/nginx/conf.d/cloudflare.conf`:

```nginx
# Cloudflare IPv4
set_real_ip_from 173.245.48.0/20;
set_real_ip_from 103.21.244.0/22;
set_real_ip_from 103.22.200.0/22;
set_real_ip_from 103.31.4.0/22;
set_real_ip_from 141.101.64.0/18;
set_real_ip_from 108.162.192.0/18;
set_real_ip_from 190.93.240.0/20;
set_real_ip_from 188.114.96.0/20;
set_real_ip_from 197.234.240.0/22;
set_real_ip_from 198.41.128.0/17;
set_real_ip_from 162.158.0.0/15;
set_real_ip_from 104.16.0.0/13;
set_real_ip_from 104.24.0.0/14;
set_real_ip_from 172.64.0.0/13;
set_real_ip_from 131.0.72.0/22;

# Cloudflare IPv6
set_real_ip_from 2400:cb00::/32;
set_real_ip_from 2606:4700::/32;
set_real_ip_from 2803:f800::/32;
set_real_ip_from 2405:b500::/32;
set_real_ip_from 2405:8100::/32;
set_real_ip_from 2a06:98c0::/29;
set_real_ip_from 2c0f:f248::/32;

# Tell Nginx to use the CF-Connecting-IP header sent by trusted proxies
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
```

### Verification Against Adversarial Spoofing
1. Request from trusted Cloudflare IP (`173.245.48.10`) with `CF-Connecting-IP: 203.0.113.19` -> Nginx `$remote_addr` resolves to `203.0.113.19` (ACCEPTED).
2. Direct request from untrusted IP (`198.51.100.5`) with `CF-Connecting-IP: 203.0.113.19` -> Nginx `$remote_addr` remains `198.51.100.5` (SPOOFING DEFEATED).
