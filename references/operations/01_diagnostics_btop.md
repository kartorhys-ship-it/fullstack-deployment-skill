# Host Diagnostics & Resource Monitoring with btop

Real-time terminal-based observability for CPU, memory, disks, and network processes.

---

## 1. btop Deployment & Operational Utility

Unlike standard `top` or `htop`, `btop` provides clear visualization of memory breakdown (cached, active, swap), per-core CPU loads, process tree hierarchies, and I/O disk saturation.

### Installation
```bash
sudo apt update && sudo apt install -y btop
```

### Diagnostic Triage Workflows
1. **Identifying Zombie / Orphaned Workers**:
   - Press `p` to sort by PID or search for `gunicorn` / `python`.
   - Verify that all worker processes roll under a single parent PID managed by Supervisord.
2. **Monitoring Memory Pressure**:
   - Inspect the Memory box. If `Available` memory drops below 200MB and `Swap` usage spikes, the host is nearing OOM.
3. **Investigating High Disk I/O Wait**:
   - Check the Disk IO graph. Heavy write spikes often correlate with unindexed Meilisearch bulk imports or unrotated log growth.
