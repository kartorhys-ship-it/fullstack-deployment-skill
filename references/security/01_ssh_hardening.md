# SSH Hardening and User Privilege Separation

This guide covers the initial server hardening protocol for Ubuntu 24.04/22.04 LTS servers.

---

## 1. Principle of Least Privilege: Non-Root Deployer

Never operate production services directly as `root`. Direct root logins over SSH expose the host to brute-force attacks and risk catastrophic inadvertent commands (`rm -rf`).

### Provisioning Steps
```bash
# 1. Create dedicated administrative user
adduser --gecos "" deployer
usermod -aG sudo deployer

# 2. Provision SSH key directory with strict permissions
mkdir -p /home/deployer/.ssh
chmod 700 /home/deployer/.ssh

# 3. Add administrator's ED25519 public key
cat << 'EOF' >> /home/deployer/.ssh/authorized_keys
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... admin@workstation
EOF
chmod 600 /home/deployer/.ssh/authorized_keys
chown -R deployer:deployer /home/deployer/.ssh
```

---

## 2. OpenSSH Daemon Hardening (`/etc/ssh/sshd_config.d/99-hardened.conf`)

Ubuntu 22.04/24.04 supports modular SSH configuration drop-ins in `/etc/ssh/sshd_config.d/`.

```ini
# /etc/ssh/sshd_config.d/99-hardened.conf
# Enforce modern, secure SSH parameters

# 1. Disable root login completely
PermitRootLogin no

# 2. Disable password authentication (keys only)
PasswordAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes

# 3. Restrict authentication methods and algorithms
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 3

# 4. Idle timeout enforcement
ClientAliveInterval 300
ClientAliveCountMax 2
```

### Verification & Reload Safety Preconditions
Before restarting the SSH daemon or socket:
1. Validate syntax:
   ```bash
   sshd -t
   ```
2. Only reload if syntax test returns exit code 0:
   ```bash
   sudo systemctl reload ssh || sudo systemctl reload ssh.socket
   ```
3. **CRITICAL INVARIANT**: Keep the current SSH session active while initiating a new terminal session to confirm successful key authentication before disconnecting!
