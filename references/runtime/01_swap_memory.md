# Swap Memory Provisioning for OOM Prevention

Memory exhaustion is the #1 cause of catastrophic build failures (e.g. `pnpm build`, TypeScript compilation) and silent backend process crashes on entry-level VPS instances (1GB–2GB RAM).

---

## 1. The OOM (Out Of Memory) Killer Problem

When memory allocations exceed available physical RAM, the Linux kernel invokes the OOM Killer to abruptly terminate the highest memory-consuming process (frequently Gunicorn, Python, or Node.js).
Symptoms:
* Build abruptly reports `Killed` or `Exit code 137`.
* Nginx returns `502 Bad Gateway` because the backend worker was killed.
* System logs (`journalctl -xe` or `dmesg -T`) record `Out of memory: Killed process`.

---

## 2. Swap Provisioning Formula & Safe Procedure

### Sizing Heuristic
* **Host RAM <= 2GB**: Provision **2GB to 4GB** swap.
* **Host RAM 2GB–8GB**: Provision **4GB** swap.
* **Host RAM > 8GB**: Provision **4GB–8GB** swap.

### Automated Provisioning Script
```bash
# Verify existing swap
if [ $(swapon --show | wc -l) -le 1 ]; then
    echo "No active swap detected. Provisioning 4GB swapfile..."
    
    # 1. Allocate space safely (fallocate is fast; fallback to dd if unsupported)
    sudo fallocate -l 4G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
    
    # 2. Secure file permissions (MUST be 0600 - root read/write only)
    sudo chmod 600 /swapfile
    
    # 3. Format as Linux swap area
    sudo mkswap /swapfile
    
    # 4. Activate swap
    sudo swapon /swapfile
    
    # 5. Persist across reboots in /etc/fstab
    if ! grep -q "/swapfile" /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    
    # 6. Tune swappiness (default 60; set to 10 for servers to prioritize RAM)
    sudo sysctl vm.swappiness=10
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.d/99-swap.conf
    
    echo "Swap provisioning complete."
else
    echo "Swap already configured:"
    swapon --show
fi
```

### Safety Invariants
1. Permissions on `/swapfile` MUST be `0600`. Permissive settings allow unprivileged users to read raw kernel/memory dumps.
2. Verify available disk space before allocating: ensure host has at least `swap_size + 3GB` free root partition space.
