"""Deployment Dependency Graph (Directed Multi-Graph with Provenance Evidence).

Supports cyclic dependencies, multi-edges between nodes, and full explainability
(source, relation, target, origin, file, line, extractor) for every relationship.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple


@dataclass(frozen=True)
class EdgeEvidence:
    file: str
    line: int
    extractor: str
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "file": self.file,
            "line": self.line,
            "extractor": self.extractor
        }
        if self.detail:
            data["detail"] = self.detail
        return data


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    origin: str  # "discovered" or "declared"
    evidence: Optional[EdgeEvidence] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "origin": self.origin,
            "evidence": self.evidence.to_dict() if self.evidence else None
        }

    def explain(self) -> str:
        ev_str = f" [{self.evidence.file}:{self.evidence.line} via {self.evidence.extractor}]" if self.evidence else ""
        return f"{self.source} --{self.relation}--> {self.target} (origin: {self.origin}){ev_str}"


@dataclass
class Node:
    id: str
    node_type: str  # "service", "config_file", "port", "socket", "secret_ref", "user", "external"
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_type": self.node_type,
            "attributes": self.attributes
        }


class DeploymentDependencyGraph:
    """Directed Multi-Graph for Infrastructure with Provenance."""

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._adj_outgoing: Dict[str, List[Edge]] = {}
        self._adj_incoming: Dict[str, List[Edge]] = {}

    def add_node(self, node_id: str, node_type: str, attributes: Optional[Dict[str, Any]] = None) -> Node:
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(id=node_id, node_type=node_type, attributes=attributes or {})
            self._adj_outgoing[node_id] = []
            self._adj_incoming[node_id] = []
        else:
            if attributes:
                self.nodes[node_id].attributes.update(attributes)
        return self.nodes[node_id]

    def add_edge(
        self,
        source: str,
        relation: str,
        target: str,
        origin: str = "discovered",
        evidence: Optional[EdgeEvidence] = None
    ) -> Edge:
        # Ensure nodes exist
        if source not in self.nodes:
            self.add_node(source, node_type="unknown")
        if target not in self.nodes:
            self.add_node(target, node_type="unknown")

        edge = Edge(source=source, relation=relation, target=target, origin=origin, evidence=evidence)
        self.edges.append(edge)
        self._adj_outgoing[source].append(edge)
        self._adj_incoming[target].append(edge)
        return edge

    def get_outgoing(self, node_id: str) -> List[Edge]:
        return self._adj_outgoing.get(node_id, [])

    def get_incoming(self, node_id: str) -> List[Edge]:
        return self._adj_incoming.get(node_id, [])

    def get_neighbors(self, node_id: str, direction: str = "both") -> Set[str]:
        neighbors = set()
        if direction in ("outgoing", "both"):
            for e in self.get_outgoing(node_id):
                neighbors.add(e.target)
        if direction in ("incoming", "both"):
            for e in self.get_incoming(node_id):
                neighbors.add(e.source)
        return neighbors

    def find_edges(self, source: Optional[str] = None, target: Optional[str] = None, relation: Optional[str] = None) -> List[Edge]:
        results = []
        pool = self.edges
        if source and source in self._adj_outgoing:
            pool = self._adj_outgoing[source]
        for e in pool:
            if source and e.source != source:
                continue
            if target and e.target != target:
                continue
            if relation and e.relation != relation:
                continue
            results.append(e)
        return results

    def traverse(self, start_nodes: List[str], max_depth: int = 4) -> Tuple[Set[str], List[Edge]]:
        """Traverse the graph bidirectionally to gather connected components with complete edge paths."""
        visited_nodes: Set[str] = set(start_nodes)
        traversed_edges: List[Edge] = []
        frontier: Set[str] = set(start_nodes)

        for _ in range(max_depth):
            next_frontier: Set[str] = set()
            for current in frontier:
                # outgoing
                for e in self.get_outgoing(current):
                    if e not in traversed_edges:
                        traversed_edges.append(e)
                    if e.target not in visited_nodes:
                        visited_nodes.add(e.target)
                        next_frontier.add(e.target)
                # incoming
                for e in self.get_incoming(current):
                    if e not in traversed_edges:
                        traversed_edges.append(e)
                    if e.source not in visited_nodes:
                        visited_nodes.add(e.source)
                        next_frontier.add(e.source)
            if not next_frontier:
                break
            frontier = next_frontier

        return visited_nodes, traversed_edges

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges]
        }
