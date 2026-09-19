"""
Layer A: Simulation Sandbox - In-Memory Host Environment
Provides rapid deterministic simulation of filesystem, services, sockets, and firewall.
"""
from typing import Dict, Any, List, Optional

class MockHost:
    def __init__(self):
        self.filesystem: Dict[str, str] = {}
        self.permissions: Dict[str, int] = {}
        self.ownership: Dict[str, str] = {}
        self.symlinks: Dict[str, str] = {}
        self.services: Dict[str, str] = {
            "nginx": "running",
            "supervisor": "running",
            "ssh": "running",
            "meilisearch": "stopped"
        }
        self.firewall_rules: List[str] = []
        self.firewall_enabled: bool = False
        self.active_ssh_session: bool = True

    def write_file(self, path: str, content: str, mode: int = 0o644, owner: str = "deployer"):
        self.filesystem[path] = content
        self.permissions[path] = mode
        self.ownership[path] = owner

    def read_file(self, path: str) -> Optional[str]:
        if path in self.symlinks:
            target = self.symlinks[path]
            return self.filesystem.get(target)
        return self.filesystem.get(path)

    def set_symlink(self, link_path: str, target_path: str):
        self.symlinks[link_path] = target_path

    def read_symlink(self, link_path: str) -> Optional[str]:
        return self.symlinks.get(link_path)

    def reload_service(self, service_name: str) -> bool:
        if service_name not in self.services:
            return False
        return self.services[service_name] == "running"

    def apply_ufw_rule(self, rule: str):
        self.firewall_rules.append(rule)

    def enable_ufw(self) -> bool:
        # Check if SSH (22) was allowed before enabling
        ssh_allowed = any("22" in r or "ssh" in r.lower() for r in self.firewall_rules)
        if not ssh_allowed:
            self.active_ssh_session = False
            return False # Locked out!
        self.firewall_enabled = True
        return True
