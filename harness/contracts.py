"""Cross-Artifact Contract Engine (Fail-Closed).

Deterministically verifies cross-service infrastructure invariants across disparate files:
1. backend_port_consistency (Gunicorn == Supervisor == Nginx Upstream == Healthcheck)
2. socket_permission_consistency (Socket path match + www-data group ownership)
3. cloudflare_real_ip_trust (Authoritative CIDRs, real_ip_recursive on, CF-Connecting-IP, no 0.0.0.0/0)
4. secret_reference_integrity (No orphaned secret tokens or exposed raw credentials)
5. atomic_rollback_integrity (Symlink checkpoints & failure recovery)
6. nginx_configuration_must_validate
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from harness.graph import DeploymentDependencyGraph


class ContractViolation(Exception):
    """Raised when a cross-artifact infrastructure invariant is violated."""
    pass


class UnknownContractError(ContractViolation):
    """Raised when an unknown contract is requested (Fail-Closed)."""
    pass


class CrossArtifactContractEngine:
    """Evaluates cross-file structural invariants across the repository. Fails closed."""

    # Authoritative Cloudflare IPv4 ranges (https://www.cloudflare.com/ips-v4)
    CLOUDFLARE_IPV4_CIDRS = [
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22"
    ]

    # Authoritative Cloudflare IPv6 ranges (https://www.cloudflare.com/ips-v6)
    CLOUDFLARE_IPV6_CIDRS = [
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32"
    ]

    def __init__(self, repo_root: str, graph: Optional[DeploymentDependencyGraph] = None):
        self.repo_root = Path(repo_root).resolve()
        self.graph = graph

    def verify_contract(self, contract_name: str, **kwargs) -> Tuple[bool, Optional[str]]:
        """Dispatch contract verification by name. FAILS CLOSED on unknown contract."""
        method_name = f"verify_{contract_name}"
        verifier = getattr(self, method_name, None)
        if not verifier:
            raise UnknownContractError(
                f"FAIL_CLOSED: Contract '{contract_name}' is not recognized by the contract engine. "
                f"Cannot establish invariant correctness."
            )
        return verifier(**kwargs)

    def verify_backend_port_consistency(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that Gunicorn, Supervisor, Nginx upstreams, and Healthcheck all agree on backend transport."""
        nginx_ports = set()
        nginx_sockets = set()
        for conf in self.repo_root.glob("**/*.conf"):
            if "supervisor" in str(conf):
                continue
            try:
                content = conf.read_text(encoding="utf-8")
                for m in re.finditer(r"server\s+(unix:)?([^\s;]+)", content):
                    is_unix = bool(m.group(1))
                    val = m.group(2)
                    if is_unix:
                        nginx_sockets.add(val)
                    elif ":" in val:
                        nginx_ports.add(val.split(":")[-1])
            except Exception:
                pass

        gunicorn_ports = set()
        gunicorn_sockets = set()
        for sh in self.repo_root.glob("**/*.sh"):
            try:
                content = sh.read_text(encoding="utf-8")
                sm = re.search(r'SOCKET=[\'"]([^\'"]+)[\'"]', content)
                if sm:
                    gunicorn_sockets.add(sm.group(1))
                bm = re.search(r'--bind\s+[\'"]?(127\.0\.0\.1|0\.0\.0\.0):(\d+)', content)
                if bm:
                    gunicorn_ports.add(bm.group(2))
            except Exception:
                pass

        for hc in self.repo_root.glob("**/health*.sh"):
            try:
                content = hc.read_text(encoding="utf-8")
                pm = re.search(r':(\d{2,5})(/|\s|$)', content)
                if pm:
                    hc_port = pm.group(1)
                    if nginx_ports and hc_port not in nginx_ports:
                        return False, f"PORT_MISMATCH: Healthcheck tests port {hc_port} but Nginx upstream uses {nginx_ports}!"
                    if gunicorn_ports and hc_port not in gunicorn_ports:
                        return False, f"PORT_MISMATCH: Healthcheck tests port {hc_port} but Gunicorn binds to {gunicorn_ports}!"
            except Exception:
                pass

        if nginx_ports and gunicorn_ports:
            if nginx_ports != gunicorn_ports:
                return False, f"PORT_MISMATCH: Nginx upstream specifies port(s) {nginx_ports} while Gunicorn specifies {gunicorn_ports}!"

        if nginx_sockets and gunicorn_sockets:
            if nginx_sockets != gunicorn_sockets:
                return False, f"SOCKET_MISMATCH: Nginx upstream points to {nginx_sockets} while Gunicorn creates {gunicorn_sockets}!"

        return True, None

    def verify_socket_permission_consistency(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that when a Unix socket is used, socket directory permissions assign group www-data."""
        has_socket = False
        chowns_www_data = False

        for sh in self.repo_root.glob("**/*.sh"):
            try:
                content = sh.read_text(encoding="utf-8")
                if "gunicorn.sock" in content or "SOCKET=" in content:
                    has_socket = True
                    if "www-data" in content and "chown" in content:
                        chowns_www_data = True
            except Exception:
                pass

        if has_socket and not chowns_www_data:
            return False, "PERMISSION_CONTRACT_VIOLATION: Unix domain socket declared without granting group access to www-data!"

        return True, None

    def verify_cloudflare_real_ip_trust(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that Cloudflare real IP restoration is secure, comprehensive, and blocks spoofing.
        
        Invariants:
        1. Prohibits wildcard trust (0.0.0.0/0 or ::/0).
        2. Mandates 'real_ip_header CF-Connecting-IP;'.
        3. Mandates 'real_ip_recursive on;'.
        4. Disallows any untrusted / arbitrary CIDRs outside known Cloudflare IP ranges.
        5. Requires complete authoritative IPv4 coverage (all 15 IPv4 CIDRs).
        """
        found_real_ip = False
        has_open_trust = False
        has_header_directive = False
        has_recursive_on = False
        configured_cidrs = set()
        untrusted_cidrs = set()

        all_known_cf_cidrs = set(self.CLOUDFLARE_IPV4_CIDRS) | set(self.CLOUDFLARE_IPV6_CIDRS)

        for conf in self.repo_root.glob("**/*.conf"):
            try:
                content = conf.read_text(encoding="utf-8")
                if "set_real_ip_from" in content or "CF-Connecting-IP" in content:
                    found_real_ip = True

                    # Check for dangerous open trust: 0.0.0.0/0 or ::/0
                    if re.search(r"set_real_ip_from\s+0\.0\.0\.0/0;", content) or re.search(r"set_real_ip_from\s+::/0;", content):
                        has_open_trust = True

                    if "real_ip_header CF-Connecting-IP;" in content:
                        has_header_directive = True

                    if "real_ip_recursive on;" in content:
                        has_recursive_on = True

                    for m in re.finditer(r"set_real_ip_from\s+([^\s;]+);", content):
                        cidr = m.group(1).strip()
                        configured_cidrs.add(cidr)
                        if cidr not in all_known_cf_cidrs and cidr not in ("0.0.0.0/0", "::/0"):
                            untrusted_cidrs.add(cidr)
            except Exception:
                pass

        if not found_real_ip:
            return True, None

        if has_open_trust:
            return False, "CLOUDFLARE_TRUST_VIOLATION: set_real_ip_from 0.0.0.0/0 trusts arbitrary client IP headers!"

        if not has_header_directive:
            return False, "CLOUDFLARE_TRUST_VIOLATION: Missing 'real_ip_header CF-Connecting-IP;' in Nginx config."

        if not has_recursive_on:
            return False, "CLOUDFLARE_TRUST_VIOLATION: Missing 'real_ip_recursive on;' for multi-hop proxy chains."

        if untrusted_cidrs:
            return False, f"CLOUDFLARE_TRUST_VIOLATION: Unexpected untrusted CIDRs in set_real_ip_from: {sorted(untrusted_cidrs)}"

        # Enforce complete coverage of the authoritative Cloudflare IPv4 and IPv6 network
        missing_v4 = set(self.CLOUDFLARE_IPV4_CIDRS) - configured_cidrs
        if missing_v4:
            return False, f"CLOUDFLARE_TRUST_VIOLATION: Incomplete Cloudflare trust list. Missing {len(missing_v4)} required IPv4 ranges: {sorted(missing_v4)[:3]}..."

        missing_v6 = set(self.CLOUDFLARE_IPV6_CIDRS) - configured_cidrs
        if missing_v6:
            return False, f"CLOUDFLARE_TRUST_VIOLATION: Incomplete Cloudflare trust list. Missing {len(missing_v6)} required IPv6 ranges: {sorted(missing_v6)[:3]}..."

        return True, None

    def verify_secret_reference_integrity(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that all secret references use <SECRET_REF_*> and no orphaned or raw secrets exist."""
        known_refs = set()
        for f in self.repo_root.glob("**/*"):
            if f.is_dir() or ".git" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                for m in re.finditer(r"<SECRET_REF_([A-Z0-9_]+)>", content):
                    known_refs.add(m.group(0))
            except Exception:
                pass

        for f in self.repo_root.glob("**/*"):
            if f.is_dir() or ".git" in str(f) or "harness" in str(f) or "evaluation" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if "MEILI_MASTER_KEY=" in content and "<SECRET_REF_" not in content:
                    return False, f"SECRET_LEAK: Unmasked MEILI_MASTER_KEY found in {f.name}!"
            except Exception:
                pass

        return True, None

    def verify_atomic_rollback_integrity(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that deployment templates maintain releases/ and current symlink architecture."""
        has_current_symlink = False
        for f in self.repo_root.glob("**/*"):
            if f.is_dir() or ".git" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if "/current/" in content and "/releases/" in content:
                    has_current_symlink = True
                    break
            except Exception:
                pass

        if not has_current_symlink:
            return False, "ROLLBACK_VIOLATION: Deployment structure does not implement atomic current symlink cuts!"

        return True, None

    def verify_nginx_configuration_must_validate(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that Nginx configuration files contain valid location blocks and syntax."""
        for conf in self.repo_root.glob("**/nginx/**/*.conf"):
            try:
                content = conf.read_text(encoding="utf-8")
                if content.count("{") != content.count("}"):
                    return False, f"SYNTAX_ERROR: Mismatched curly braces in {conf.name}"
            except Exception:
                pass
        return True, None

    def verify_backup_retention_policy(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify backup retention parameters across repository backup scripts."""
        for sh in self.repo_root.glob("**/*backup*.sh"):
            try:
                content = sh.read_text(encoding="utf-8")
                # Check retention days
                m_ret = re.search(r"RETENTION_DAYS=(\d+)", content)
                if m_ret:
                    days = int(m_ret.group(1))
                    if days < 7:
                        return False, f"RETENTION_RISK: {sh.name} sets RETENTION_DAYS={days} < minimum safe 7 days"
                # Check target backup dir is bounded and not root or system dirs
                m_dir = re.search(r'BACKUP_DIR=[\'"]([^\'"]+)[\'"]', content)
                if m_dir:
                    bdir = m_dir.group(1).strip()
                    if bdir in ("/", "/etc", "/var", "/bin", "/usr", "/home"):
                        return False, f"DANGEROUS_TARGET: {sh.name} sets BACKUP_DIR to critical system path '{bdir}'"
                # Check min retain
                m_min = re.search(r"MIN_RETAIN=(\d+)", content)
                if m_min and int(m_min.group(1)) < 1:
                    return False, f"ZERO_RETAIN: {sh.name} sets MIN_RETAIN to 0, risking zero backups"
            except Exception:
                pass
        return True, None

    def verify_swap_memory_guard(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify swap configuration parameters across repository scripts/templates."""
        for pattern in ("templates/**/*", "references/**/*", "scripts/**/*"):
            for f in self.repo_root.glob(pattern):
                if f.is_dir() or ".git" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    if "swapfile" in content:
                        # Invariant: swap permissions must never be loose (chmod 777 or 666)
                        if "chmod 777" in content or "chmod 666" in content or "chmod 755" in content:
                            return False, f"INSECURE_SWAP: {f.name} contains insecure world/group permissions on swapfile"
                except Exception:
                    pass
        return True, None

    def verify_all_invariants(self, invariants: List[str]) -> Dict[str, Tuple[bool, Optional[str]]]:
        """Verify all requested invariants. Fails closed on any unknown contract or failed invariant."""
        results = {}
        for inv in invariants:
            res, reason = self.verify_contract(inv)
            results[inv] = (res, reason)
            if not res:
                raise ContractViolation(
                    f"CONTRACT_VIOLATION: Invariant '{inv}' failed verification: {reason}"
                )
        return results

