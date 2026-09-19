# Host Perimeter Defense: UFW Firewall and Fail2ban

Securing inbound network access and preventing automated brute-force credential stuffing.

---

## 1. Uncomplicated Firewall (UFW) Protocol

UFW acts as an iptables/nftables front-end on Ubuntu.

### Baseline Invariant Rules
Default policy must be to deny all incoming traffic and allow all outgoing traffic.

```bash
# 1. Set baseline policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 2. Allow SSH (Port 22) - MUST BE EXECUTED BEFORE ENABLING
sudo ufw allow 22/tcp comment 'OpenSSH access'

# 3. Allow Web traffic (HTTP 80, HTTPS 443)
sudo ufw allow 80/tcp comment 'Nginx HTTP / Certbot ACME challenge'
sudo ufw allow 443/tcp comment 'Nginx HTTPS'

# 4. Enable firewall safely
sudo ufw --force enable
sudo ufw status verbose
```

### Prohibited Actions
* Never expose application backend ports directly to the internet (e.g. FastAPI on `8000`, Meilisearch on `7700`, Vite dev on `5173`). All internal services must bind exclusively to `127.0.0.1` or UNIX domain sockets, routed through Nginx reverse proxy.

---

## 2. Fail2ban Intrusion Prevention (`/etc/fail2ban/jail.local`)

Fail2ban monitors authentication log files (`/var/log/auth.log`) and updates firewall rules to block IPs exhibiting malicious behavior.

### Installation & Hardened Configuration
```bash
sudo apt update && sudo apt install -y fail2ban
```

Create `/etc/fail2ban/jail.local`:
```ini
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
banaction = ufw

[sshd]
enabled = true
port = 22
mode = aggressive
logpath = %(sshd_log)s
backend = systemd
```

### Service Verification
```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

### DigitalOcean Recovery Console Contingency
If an operator is locked out due to an erroneous UFW rule or aggressive fail2ban trigger, use the cloud provider's out-of-band VNC/Web console (DigitalOcean Droplet Console / AWS EC2 Serial Console), authenticate using local root/sudo credentials, and disable or repair UFW (`ufw disable`).
