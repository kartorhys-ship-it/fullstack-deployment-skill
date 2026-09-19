"""Context Builder Engine (Deterministic Knowledge Routing & Bounded Assembly).

Replaces naive whole-repo dumping or loose vector RAG with structural context assembly:
Task + Target Files + Immediate Graph Neighbors + Routed Domain References + Active Invariants.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from harness.graph import DeploymentDependencyGraph


class ContextBuilder:
    """Assembles a compact, structurally bounded context for the agent."""

    # Deterministic knowledge router mappings
    ROUTING_TABLE = [
        {
            "matchers": ["cloudflare", "real_ip", "cf-connecting-ip", "spoof"],
            "references": [
                "references/proxy/02_cloudflare_real_ip.md",
                "references/proxy/01_nginx_reverse_proxy.md"
            ],
            "invariants": ["cloudflare_real_ip_trust", "nginx_configuration_must_validate"]
        },
        {
            "matchers": ["nginx", "proxy", "upstream", "port", "socket", "502"],
            "references": [
                "references/proxy/01_nginx_reverse_proxy.md",
                "references/runtime/02_python_fastapi.md"
            ],
            "invariants": ["backend_port_consistency", "socket_permission_consistency", "nginx_configuration_must_validate"]
        },
        {
            "matchers": ["supervisor", "gunicorn", "uvicorn", "zombie", "fastapi"],
            "references": [
                "references/runtime/02_python_fastapi.md",
                "references/runtime/03_node_supervisor.md"
            ],
            "invariants": ["backend_port_consistency", "socket_permission_consistency"]
        },
        {
            "matchers": ["meilisearch", "systemd", "master_key", "secret"],
            "references": [
                "references/data/01_meilisearch_systemd.md",
                "references/security/01_ssh_hardening.md"
            ],
            "invariants": ["secret_reference_integrity"]
        },
        {
            "matchers": ["atomic", "rollback", "symlink", "release", "deploy"],
            "references": [
                "references/deployment/01_atomic_deployment.md",
                "references/deployment/02_cicd_pipeline.md"
            ],
            "invariants": ["atomic_rollback_integrity"]
        },
        {
            "matchers": ["swap", "oom", "memory"],
            "references": [
                "references/runtime/01_swap_memory.md"
            ],
            "invariants": ["swap_memory_guard"]
        }
    ]

    def __init__(self, repo_root: str, graph: DeploymentDependencyGraph):
        self.repo_root = Path(repo_root).resolve()
        self.graph = graph

    def assemble_context(
        self,
        task_description: str,
        target_files: List[str]
    ) -> Dict[str, Any]:
        """Assemble the targeted, bounded context payload."""
        task_lower = task_description.lower()

        # 1. Deterministic Reference Routing
        selected_references = []
        routed_invariants = set()

        for route in self.ROUTING_TABLE:
            if any(m in task_lower for m in route["matchers"]) or any(any(m in tf.lower() for m in route["matchers"]) for tf in target_files):
                for ref in route["references"]:
                    if ref not in selected_references:
                        selected_references.append(ref)
                routed_invariants.update(route["invariants"])

        # Default fallback if no match
        if not selected_references:
            selected_references.append("references/proxy/01_nginx_reverse_proxy.md")
            routed_invariants.add("nginx_configuration_must_validate")

        # 2. Structural Graph Neighbors
        neighbors = set()
        for tf in target_files:
            norm = tf.replace("\\", "/").lstrip("./")
            for nid, node in self.graph.nodes.items():
                node_file = node.attributes.get("file", "")
                if norm in node_file or node_file in norm:
                    for nbr in self.graph.get_neighbors(nid, direction="both"):
                        neighbors.add(nbr)

        # 3. Read reference contents
        reference_contents = {}
        for ref_rel in selected_references:
            ref_path = self.repo_root / ref_rel
            if ref_path.exists():
                try:
                    reference_contents[ref_rel] = ref_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        # 4. Target file contents
        target_contents = {}
        for tf in target_files:
            tf_path = self.repo_root / tf
            if tf_path.exists():
                try:
                    target_contents[tf] = tf_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        return {
            "task": task_description,
            "target_files": target_files,
            "target_contents": target_contents,
            "connected_graph_neighbors": sorted(list(neighbors)),
            "routed_references": selected_references,
            "reference_contents": reference_contents,
            "active_invariants": sorted(list(routed_invariants))
        }
