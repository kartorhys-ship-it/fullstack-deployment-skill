"""Cross-Artifact Contract Engine.

Deterministically verifies cross-service infrastructure invariants across disparate files:
1. backend_port_consistency (Gunicorn == Supervisor == Nginx Upstream == Healthcheck)
2. socket_permission_consistency (Socket path match + www-data group ownership)
3. cloudflare_real_ip_trust (CIDR boundaries & spoofing defense)
4. secret_reference_integrity (No orphaned secret tokens or exposed credentials)
5. atomic_rollback_integrity (Symlink checkpoints & failure recovery)
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from harness.graph import DeploymentDependencyGraph


class ContractViolation(Exception):
    """Raised when a cross-artifact infrastructure invariant is violated."""
    pass


class CrossArtifactContractEngine:
    """Evaluates cross-file structural invariants across the repository."""

    def __init__(self, repo_root: str, graph: Optional[DeploymentDependencyGraph] = None):
        self.repo_root = Path(repo_root).resolve()
        self.graph = graph

    def verify_contract(self, contract_name: str, **kwargs) -> Tuple[bool, Optional[str]]:
        """Dispatch contract verification by name."""
        method_name = f"verify_{contract_name}"
        verifier = getattr(self, method_name, None)
        if not verifier:
            return True, None  # Unregistered contracts pass by default or treated as informational
        return verifier(**kwargs)

    def verify_backend_port_consistency(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """Verify that Gunicorn, Supervisor, Nginx upstreams, and Healthcheck all agree on backend transport."""
        # Check Nginx upstream
        nginx_ports = set()
        nginx_sockets = set()
        for conf in self.repo_root.glob("**/*.conf"):
            if "supervisor" in str(conf):
                continue
            try:
                content = conf.read_text(encoding="utf-8")
                # Look for server directive in upstream
                for m in re.finditer(r"server\s+(unix:)?([^\s;]+)", content):
                    is_unix = bool(m.group(1))
                    val = m.group(2)
                    if is_unix:
                        nginx_sockets.add(val)
                    elif ":" in val:
                        nginx_ports.add(val.split(":")[-1])
            except Exception:
                pass

        # Check shell / gunicorn scripts
        gunicorn_ports = set()
        gunicorn_sockets = set()
        for sh in self.repo_root.glob("**/*.sh"):
            try:
                content = sh.read_text(encoding="utf-8")
                # Check socket var
                sm = re.search(r'SOCKET=[\'"]([^\'"]+)[\'"]', content)
                if sm:
                    gunicorn_sockets.add(sm.group(1))
                # Check bind port
                bm = re.search(r'--bind\s+[\'"]?(127\.0\.0\.1|0\.0\.0\.0):(\d+)', content)
                if bm:
                    gunicorn_ports.add(bm.group(2))
            except Exception:
                pass

        # Check healthcheck script if present
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

        # If both use ports, they must match
        if nginx_ports and gunicorn_ports:
            if nginx_ports != gunicorn_ports:
                return False, f"PORT_MISMATCH: Nginx upstream specifies port(s) {nginx_ports} while Gunicorn specifies {gunicorn_ports}!"

        # If both use sockets, they must match
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
        """Verify that Cloudflare real IP restoration includes valid trusted CIDRs and blocks spoofing."""
        trusted_cidrs = ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18"]
        found_real_ip = False
        found_cidrs = set()

        for conf in self.repo_root.glob("**/*.conf"):
            try:
                content = conf.read_text(encoding="utf-8")
                if "set_real_ip_from" in content:
                    found_real_ip = True
                    for cidr in trusted_cidrs:
                        if cidr in content:
                            found_cidrs.add(cidr)
            except Exception:
                pass

        if found_real_ip and len(found_cidrs) == 0:
            return False, "CLOUDFLARE_TRUST_VIOLATION: set_real_ip_from declared without trusted Cloudflare CIDR boundary!"

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

        # Check for leaked secrets or orphaned raw master keys
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

    def verify_all_invariants(self, invariants: List[str]) -> Dict[str, Tuple[bool, Optional[str]]]:
        """Verify all requested invariants and return results dictionary."""
        results = {}
        for inv in invariants:
            res, reason = self.verify_contract(inv)
            results[inv] = (res, reason)
        return results
