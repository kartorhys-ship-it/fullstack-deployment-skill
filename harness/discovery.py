"""Repository Structural Discovery Engine.

Dynamically scans repository configurations (Nginx, Supervisor, Systemd, Shell scripts,
environment files, and CI/CD workflows) to discover concrete infrastructure facts
and build an explainable DeploymentDependencyGraph with provenance.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from harness.graph import DeploymentDependencyGraph, EdgeEvidence


class InfrastructureScanner:
    """Scans repository files and extracts observable infrastructure relationships."""

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()
        self.graph = DeploymentDependencyGraph()

    def scan(self) -> DeploymentDependencyGraph:
        """Execute all extractors across the repository tree."""
        # 1. Scan Nginx configs
        self._scan_nginx_configs()
        # 2. Scan Supervisor configs
        self._scan_supervisor_configs()
        # 3. Scan Systemd unit files
        self._scan_systemd_units()
        # 4. Scan Shell deployment scripts
        self._scan_shell_scripts()
        # 5. Scan Environment files
        self._scan_env_files()
        # 6. Load declared external topology (infra_manifest.yml if present)
        self._load_declared_manifest()

        return self.graph

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _scan_nginx_configs(self):
        for conf_path in self.repo_root.glob("**/*.conf"):
            rel_file = self._relative_path(conf_path)
            # Skip non-nginx supervisor configs
            if "supervisor" in rel_file:
                continue

            try:
                lines = conf_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            current_upstream = None
            for idx, line in enumerate(lines, 1):
                raw_line = line.strip()
                if raw_line.startswith("#"):
                    continue

                # Upstream definition: upstream <name> {
                upstream_m = re.match(r"upstream\s+([a-zA-Z0-9_\-]+)\s*\{", raw_line)
                if upstream_m:
                    current_upstream = upstream_m.group(1)
                    self.graph.add_node(f"nginx:upstream:{current_upstream}", "nginx_upstream", {"file": rel_file, "line": idx})

                if current_upstream and raw_line.startswith("server "):
                    # server unix:/path/to/sock or server 127.0.0.1:8000;
                    srv_m = re.search(r"server\s+(unix:)?([^\s;]+)", raw_line)
                    if srv_m:
                        is_unix = bool(srv_m.group(1))
                        target = srv_m.group(2)
                        target_node = f"socket:{target}" if is_unix else f"endpoint:{target}"
                        self.graph.add_node(target_node, "socket" if is_unix else "endpoint")
                        self.graph.add_edge(
                            source=f"nginx:upstream:{current_upstream}",
                            relation="forwards_to",
                            target=target_node,
                            origin="discovered",
                            evidence=EdgeEvidence(
                                file=rel_file,
                                line=idx,
                                extractor="nginx_upstream_server",
                                detail=raw_line
                            )
                        )

                if "}" in raw_line and current_upstream:
                    current_upstream = None

                # Listen directive: listen 80; listen 443 ssl;
                listen_m = re.search(r"listen\s+(\d+)", raw_line)
                if listen_m:
                    port = listen_m.group(1)
                    port_node = f"port:{port}"
                    self.graph.add_node(port_node, "port")
                    self.graph.add_edge(
                        source=f"config:{rel_file}",
                        relation="listens_on",
                        target=port_node,
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="nginx_listen", detail=raw_line)
                    )

                # Proxy pass: proxy_pass http://webapp_backend; or proxy_pass http://127.0.0.1:8000;
                proxy_m = re.search(r"proxy_pass\s+https?://([a-zA-Z0-9_\-.:]+);?", raw_line)
                if proxy_m:
                    dest = proxy_m.group(1)
                    if ":" in dest:
                        target_node = f"endpoint:{dest}"
                    else:
                        target_node = f"nginx:upstream:{dest}"
                    self.graph.add_edge(
                        source=f"config:{rel_file}",
                        relation="proxies_to",
                        target=target_node,
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="nginx_proxy_pass", detail=raw_line)
                    )

    def _scan_supervisor_configs(self):
        for conf_path in self.repo_root.glob("**/supervisor/**/*.conf"):
            rel_file = self._relative_path(conf_path)
            try:
                lines = conf_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            current_program = None
            for idx, line in enumerate(lines, 1):
                raw_line = line.strip()
                if raw_line.startswith("#") or raw_line.startswith(";"):
                    continue

                prog_m = re.match(r"\[program:([a-zA-Z0-9_\-]+)\]", raw_line)
                if prog_m:
                    current_program = prog_m.group(1)
                    self.graph.add_node(f"service:{current_program}", "supervisor_program", {"file": rel_file, "line": idx})

                if current_program and raw_line.startswith("command="):
                    cmd = raw_line.split("=", 1)[1].strip()
                    # Check if command runs a script
                    script_m = re.search(r"(/?[a-zA-Z0-9_\-./]+\.sh)", cmd)
                    if script_m:
                        script_target = f"script:{Path(script_m.group(1)).name}"
                        self.graph.add_edge(
                            source=f"service:{current_program}",
                            relation="executes",
                            target=script_target,
                            origin="discovered",
                            evidence=EdgeEvidence(file=rel_file, line=idx, extractor="supervisor_command", detail=cmd)
                        )
                    # Check if command binds to port directly
                    port_m = re.search(r":(\d{2,5})", cmd)
                    if port_m:
                        self.graph.add_edge(
                            source=f"service:{current_program}",
                            relation="binds_to",
                            target=f"port:{port_m.group(1)}",
                            origin="discovered",
                            evidence=EdgeEvidence(file=rel_file, line=idx, extractor="supervisor_port", detail=cmd)
                        )

                if current_program and raw_line.startswith("user="):
                    usr = raw_line.split("=", 1)[1].strip()
                    self.graph.add_edge(
                        source=f"service:{current_program}",
                        relation="runs_as",
                        target=f"user:{usr}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="supervisor_user", detail=usr)
                    )

    def _scan_systemd_units(self):
        for service_path in self.repo_root.glob("**/*.service"):
            rel_file = self._relative_path(service_path)
            service_name = service_path.stem
            service_node = f"systemd:{service_name}"
            self.graph.add_node(service_node, "systemd_service", {"file": rel_file})

            try:
                lines = service_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines, 1):
                raw_line = line.strip()
                if raw_line.startswith("#"):
                    continue

                if raw_line.startswith("User="):
                    usr = raw_line.split("=", 1)[1].strip()
                    self.graph.add_edge(
                        source=service_node,
                        relation="runs_as",
                        target=f"user:{usr}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="systemd_user", detail=usr)
                    )

                if raw_line.startswith("EnvironmentFile="):
                    env_f = raw_line.split("=", 1)[1].strip()
                    self.graph.add_edge(
                        source=service_node,
                        relation="reads_env",
                        target=f"env_file:{Path(env_f).name}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="systemd_env_file", detail=env_f)
                    )

                if raw_line.startswith("ExecStart="):
                    exec_cmd = raw_line.split("=", 1)[1].strip()
                    self.graph.add_edge(
                        source=service_node,
                        relation="executes_binary",
                        target=f"binary:{Path(exec_cmd.split()[0]).name}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="systemd_exec_start", detail=exec_cmd)
                    )

    def _scan_shell_scripts(self):
        for sh_path in self.repo_root.glob("**/*.sh"):
            rel_file = self._relative_path(sh_path)
            script_node = f"script:{sh_path.name}"
            self.graph.add_node(script_node, "shell_script", {"file": rel_file})

            try:
                lines = sh_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines, 1):
                raw_line = line.strip()
                if raw_line.startswith("#"):
                    continue

                # Socket assignment: SOCKET="/var/www/.../gunicorn.sock"
                sock_m = re.search(r'SOCKET=[\'"]([^\'"]+)[\'"]', raw_line)
                if sock_m:
                    sock_target = sock_m.group(1)
                    self.graph.add_edge(
                        source=script_node,
                        relation="binds_to",
                        target=f"socket:{sock_target}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="shell_socket_var", detail=raw_line)
                    )

                # Port / Bind parameter: --bind "unix:$SOCKET" or --bind "127.0.0.1:8000" or -b 0.0.0.0:8000
                bind_m = re.search(r'--bind\s+[\'"]?(unix:)?([^\s\'"]+)', raw_line)
                if bind_m:
                    is_unix = bool(bind_m.group(1))
                    val = bind_m.group(2)
                    if not is_unix and ":" in val:
                        port = val.split(":")[-1]
                        self.graph.add_edge(
                            source=script_node,
                            relation="binds_to",
                            target=f"port:{port}",
                            origin="discovered",
                            evidence=EdgeEvidence(file=rel_file, line=idx, extractor="gunicorn_bind_port", detail=raw_line)
                        )

                # User / Group chown: chown -R "$USER:$GROUP"
                chown_m = re.search(r'chown\s+.*[\'"]?([a-zA-Z0-9_\-]+):([a-zA-Z0-9_\-]+)[\'"]?', raw_line)
                if chown_m:
                    u, g = chown_m.group(1), chown_m.group(2)
                    self.graph.add_edge(
                        source=script_node,
                        relation="chowns_socket_group",
                        target=f"group:{g}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="shell_chown", detail=raw_line)
                    )

    def _scan_env_files(self):
        for env_path in self.repo_root.glob("**/*env*"):
            if env_path.is_dir():
                continue
            rel_file = self._relative_path(env_path)
            try:
                lines = env_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines, 1):
                raw_line = line.strip()
                if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
                    continue

                k, v = raw_line.split("=", 1)
                k, v = k.strip(), v.strip()

                if "SECRET_REF_" in v:
                    ref_m = re.search(r"<SECRET_REF_[A-Z0-9_]+>", v)
                    if ref_m:
                        secret_node = f"secret:{ref_m.group(0)}"
                        self.graph.add_node(secret_node, "secret_reference")
                        self.graph.add_edge(
                            source=f"config:{rel_file}",
                            relation="references_secret",
                            target=secret_node,
                            origin="discovered",
                            evidence=EdgeEvidence(file=rel_file, line=idx, extractor="env_secret_ref", detail=k)
                        )

                if k in ("PORT", "BACKEND_PORT", "SERVER_PORT") and v.isdigit():
                    self.graph.add_edge(
                        source=f"config:{rel_file}",
                        relation="defines_port",
                        target=f"port:{v}",
                        origin="discovered",
                        evidence=EdgeEvidence(file=rel_file, line=idx, extractor="env_port", detail=raw_line)
                    )

    def _load_declared_manifest(self):
        """Loads infra_manifest.yml if present, recording declared external topology."""
        manifest_file = self.repo_root / "infra_manifest.yml"
        if not manifest_file.exists():
            return

        try:
            content = manifest_file.read_text(encoding="utf-8")
            # Try yaml if available, otherwise parse simple structure
            try:
                import yaml
                data = yaml.safe_load(content) or {}
            except ImportError:
                data = json.loads(content) if content.strip().startswith("{") else {}
        except Exception:
            return

        ext_deps = data.get("external_dependencies", [])
        for dep in ext_deps:
            dep_id = dep.get("id")
            dep_type = dep.get("type", "external")
            targets = dep.get("targets", [])
            relation = dep.get("relation", "routes_to")

            self.graph.add_node(f"external:{dep_id}", dep_type, dep)
            for tgt in targets:
                self.graph.add_edge(
                    source=f"external:{dep_id}",
                    relation=relation,
                    target=tgt,
                    origin="declared",
                    evidence=EdgeEvidence(
                        file="infra_manifest.yml",
                        line=1,
                        extractor="manifest_external_dependency",
                        detail=f"Declared {dep_type} {dep_id}"
                    )
                )


def discover_repository(repo_root: str) -> DeploymentDependencyGraph:
    """Convenience entry point for full repository structural discovery."""
    scanner = InfrastructureScanner(repo_root)
    return scanner.scan()
