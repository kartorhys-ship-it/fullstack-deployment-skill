"""Change Impact Analysis & Blast Radius Engine.

Computes the blast radius of proposed infrastructure changes across the
DeploymentDependencyGraph and verifies the declared vs. discovered impact gap.
"""

from typing import Dict, List, Set, Tuple, Optional, Any
from harness.graph import DeploymentDependencyGraph, Edge
from harness.manifest import ChangeManifest


class ManifestIncompleteError(Exception):
    """Raised when a ChangeManifest omits discoverable infrastructure dependencies."""

    def __init__(self, declared_targets: List[str], missing_dependents: List[str], explanations: Dict[str, str]):
        self.declared_targets = declared_targets
        self.missing_dependents = missing_dependents
        self.explanations = explanations
        msg = (
            f"MANIFEST_INCOMPLETE: The proposed change omits {len(missing_dependents)} structurally "
            f"connected artifact(s). Declared targets: {declared_targets}. "
            f"Discovered unannounced dependencies: {missing_dependents}. "
            f"Details: {explanations}. Action: Amend manifest before proceeding."
        )
        super().__init__(msg)


class ImpactAnalyzer:
    """Analyzes the blast radius of target changes and compares declared vs. discovered impact."""

    def __init__(self, graph: DeploymentDependencyGraph):
        self.graph = graph

    def compute_blast_radius(self, target_files_or_nodes: List[str], max_depth: int = 3) -> Dict[str, Any]:
        """Compute the full blast radius around target artifacts with complete edge evidence."""
        # Normalize start nodes
        start_nodes = set()
        for item in target_files_or_nodes:
            norm = item.replace("\\", "/").lstrip("./")
            # If item matches a known node directly
            if norm in self.graph.nodes:
                start_nodes.add(norm)
            else:
                # Find nodes associated with this file
                matched = False
                for nid, node in self.graph.nodes.items():
                    node_file = node.attributes.get("file", "")
                    if node_file and (norm in node_file or node_file in norm):
                        start_nodes.add(nid)
                        matched = True
                    elif nid.endswith(norm):
                        start_nodes.add(nid)
                        matched = True
                if not matched:
                    # Add as generic config file node
                    self.graph.add_node(f"config:{norm}", "config_file", {"file": norm})
                    start_nodes.add(f"config:{norm}")

        visited_nodes, traversed_edges = self.graph.traverse(list(start_nodes), max_depth=max_depth)

        # Collect affected files from nodes and edge evidence
        affected_files: Set[str] = set()
        file_evidence: Dict[str, List[Dict[str, Any]]] = {}

        for nid in visited_nodes:
            node = self.graph.nodes.get(nid)
            if node and "file" in node.attributes:
                fpath = node.attributes["file"]
                affected_files.add(fpath)
                file_evidence.setdefault(fpath, []).append({
                    "node": nid,
                    "reason": f"Directly declared by node {nid}"
                })

        for edge in traversed_edges:
            if edge.evidence and edge.evidence.file:
                fpath = edge.evidence.file
                affected_files.add(fpath)
                file_evidence.setdefault(fpath, []).append({
                    "edge": edge.explain(),
                    "relation": edge.relation,
                    "reason": f"Connected via {edge.relation} from {edge.source} to {edge.target}"
                })

        return {
            "start_nodes": list(start_nodes),
            "visited_nodes": list(visited_nodes),
            "affected_files": sorted(list(affected_files)),
            "file_evidence": file_evidence,
            "traversed_edges": [e.to_dict() for e in traversed_edges]
        }

    def verify_manifest_impact(self, manifest: ChangeManifest) -> Tuple[bool, Optional[ManifestIncompleteError]]:
        """Compares declared manifest targets against discovered blast radius.

        Fails closed with ManifestIncompleteError if the change touches shared resources
        (e.g. backend port/socket) without including all dependent artifacts.
        """
        radius = self.compute_blast_radius(manifest.targets, max_depth=3)
        discovered_files = radius["affected_files"]

        # Canonical declared file targets strictly
        declared_file_targets = set(t.replace("\\", "/").lstrip("./") for t in manifest.targets)

        # Check if any declared target failed structural discovery parsing
        if hasattr(self.graph, "health") and self.graph.health and self.graph.health.parse_failures:
            failed_targets = []
            for fail in self.graph.health.parse_failures:
                f_norm = fail.get("file", "").replace("\\", "/").lstrip("./")
                if f_norm in declared_file_targets:
                    failed_targets.append(f"{f_norm} (Error: {fail.get('error')})")
            if failed_targets:
                err = ManifestIncompleteError(
                    declared_targets=manifest.targets,
                    missing_dependents=failed_targets,
                    explanations={"discovery_parse_failures": "; ".join(failed_targets)}
                )
                return False, err

        missing = []
        explanations = {}

        for f in discovered_files:
            norm_f = f.replace("\\", "/").lstrip("./")
            # Exact path matching strictly (no substring bleed)
            if norm_f not in declared_file_targets:
                missing.append(norm_f)
                ev = radius["file_evidence"].get(f, [])
                reasons = [e.get("reason", "Structural dependency") for e in ev]
                explanations[norm_f] = "; ".join(reasons)

        if missing:
            err = ManifestIncompleteError(
                declared_targets=manifest.targets,
                missing_dependents=missing,
                explanations=explanations
            )
            return False, err

        return True, None
