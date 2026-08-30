"""The tool surface: four typed traversal tools, identical for every ontology.

This is the experiment's control. The agent gets the same four signatures no
matter which graph is loaded; what differs is only what each shape gives back.
Results are capped so a badly shaped graph pays its fan-out cost in extra tool
calls rather than in one giant response - which is how real tool budgets work.

No SDK imports here; the module is plain data and runs offline, tests and all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

FIND_CAP = 20
TRAVERSE_CAP = 30


class Graph:
    def __init__(self, payload: dict):
        self.variant = payload["variant"]
        self.nodes: Dict[str, dict] = payload["nodes"]
        self.out_edges: Dict[str, List[dict]] = {}
        self.in_edges: Dict[str, List[dict]] = {}
        for edge in payload["edges"]:
            self.out_edges.setdefault(edge["src"], []).append(edge)
            self.in_edges.setdefault(edge["dst"], []).append(edge)

    @classmethod
    def load(cls, path: Path) -> "Graph":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def label(self, node_id: str) -> str:
        props = self.nodes[node_id]["props"]
        for key in ("name", "number", "attr", "kind", "entity_type"):
            if key in props:
                value = props[key]
                if key == "attr":
                    return f"{props['attr']}={props.get('value')}"
                return str(value)
        return node_id

    # ------------------------------------------------------------- tools ----

    def find_nodes(self, query: str, node_type: str = "") -> dict:
        """Substring search over node properties (case-insensitive)."""
        needle = query.lower()
        hits = []
        for node_id, rec in self.nodes.items():
            if node_type and rec["type"] != node_type:
                continue
            haystack = json.dumps(rec["props"]).lower()
            if needle in haystack or needle in node_id.lower():
                hits.append({"id": node_id, "type": rec["type"],
                             "label": self.label(node_id)})
        # Sorted by id before the cap is applied. When more than FIND_CAP
        # nodes match, this is what decides which ones the agent gets to see,
        # so the order must be defined rather than inherited from dict
        # insertion - CosmosGraph.find_nodes sorts identically, and
        # equivalence_check.py would fail if either side drifted.
        hits.sort(key=lambda h: h["id"])
        return {"total_matches": len(hits), "returned": len(hits[:FIND_CAP]),
                "nodes": hits[:FIND_CAP]}

    def get_node(self, node_id: str) -> dict:
        rec = self.nodes.get(node_id)
        if rec is None:
            return {"error": f"no node with id {node_id!r}"}
        return {"id": node_id, "type": rec["type"], "props": rec["props"]}

    def traverse(self, node_id: str, edge_type: str = "",
                 direction: str = "any") -> dict:
        if node_id not in self.nodes:
            return {"error": f"no node with id {node_id!r}"}
        hits = []
        if direction in ("out", "any"):
            for edge in self.out_edges.get(node_id, []):
                if edge_type and edge["type"] != edge_type:
                    continue
                hits.append({"edge_type": edge["type"], "direction": "out",
                             "node_id": edge["dst"],
                             "node_type": self.nodes[edge["dst"]]["type"],
                             "label": self.label(edge["dst"])})
        if direction in ("in", "any"):
            for edge in self.in_edges.get(node_id, []):
                if edge_type and edge["type"] != edge_type:
                    continue
                hits.append({"edge_type": edge["type"], "direction": "in",
                             "node_id": edge["src"],
                             "node_type": self.nodes[edge["src"]]["type"],
                             "label": self.label(edge["src"])})
        return {"total_neighbours": len(hits),
                "returned": len(hits[:TRAVERSE_CAP]),
                "neighbours": hits[:TRAVERSE_CAP]}

    def describe_edges(self, node_id: str) -> dict:
        """What can be walked from here - edge types with directions and counts."""
        if node_id not in self.nodes:
            return {"error": f"no node with id {node_id!r}"}
        summary = {}
        for edge in self.out_edges.get(node_id, []):
            key = (edge["type"], "out")
            summary[key] = summary.get(key, 0) + 1
        for edge in self.in_edges.get(node_id, []):
            key = (edge["type"], "in")
            summary[key] = summary.get(key, 0) + 1
        return {"edges": [{"edge_type": t, "direction": d, "count": n}
                          for (t, d), n in sorted(summary.items())]}


TOOL_SPECS = [
    {
        "name": "find_nodes",
        "description": "Search the graph for nodes whose properties or id "
                       "contain the query string. Optionally filter by node "
                       "type. Returns at most 20 matches with the total count.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "node_type": {"type": "string",
                              "description": "optional exact node type filter"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_node",
        "description": "Read one node: its type and all of its properties.",
        "parameters": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
    },
    {
        "name": "traverse",
        "description": "List a node's neighbours. Optionally restrict to one "
                       "edge type and a direction (out, in, any). Returns at "
                       "most 30 neighbours with the total count.",
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "edge_type": {"type": "string"},
                "direction": {"type": "string", "enum": ["out", "in", "any"]},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "describe_edges",
        "description": "Summarise which edge types leave and enter a node, "
                       "with counts - use before traversing an unknown node.",
        "parameters": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
    },
]


def dispatch(graph: Graph, name: str, arguments: dict) -> dict:
    handlers = {
        "find_nodes": lambda: graph.find_nodes(
            arguments["query"], arguments.get("node_type", "")),
        "get_node": lambda: graph.get_node(arguments["node_id"]),
        "traverse": lambda: graph.traverse(
            arguments["node_id"], arguments.get("edge_type", ""),
            arguments.get("direction", "any")),
        "describe_edges": lambda: graph.describe_edges(arguments["node_id"]),
    }
    if name not in handlers:
        return {"error": f"unknown tool {name!r}"}
    try:
        return handlers[name]()
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        return {"error": f"bad arguments for {name}: {e}"}
