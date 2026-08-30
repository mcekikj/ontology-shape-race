"""Offline proof that the tool surface suffices on every ontology.

For a sample of questions, this walks each graph using ONLY the four public
tools - the same calls the agent can make, scripted by hand - and asserts the
oracle answer is reachable. No model, no network. If this fails, a wrong
answer in the campaign could mean broken plumbing; when it passes, a wrong
answer means the agent could not use the shape it was given - which is the
thing being measured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from graph import Graph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def claim_node(graph: Graph, number: str) -> str:
    hits = graph.find_nodes(number)["nodes"]
    if graph.variant == "normalized":
        # the search lands on the number Attribute node; step back to the entity
        attr = next(n for n in hits if n["type"] == "Attribute")
        return graph.traverse(attr["id"], "has", "in")["neighbours"][0]["node_id"]
    return next(n["id"] for n in hits if n["type"] == "claim")


def read_attr(graph: Graph, node_id: str, attr: str):
    if graph.variant == "normalized":
        for n in graph.traverse(node_id, "has", "out")["neighbours"]:
            props = graph.get_node(n["node_id"])["props"]
            if props["attr"] == attr:
                return props["value"]
        return None
    return graph.get_node(node_id)["props"].get(attr)


def follow(graph: Graph, node_id: str, kind: str) -> str:
    """Follow one relationship from an entity, whatever the variant costs."""
    if graph.variant == "normalized":
        for n in graph.traverse(node_id, "subject", "in")["neighbours"]:
            rel = graph.get_node(n["node_id"])
            if rel["props"]["kind"] == kind:
                return graph.traverse(
                    n["node_id"], "object", "out")["neighbours"][0]["node_id"]
        raise LookupError(f"no {kind} relation from {node_id}")
    for n in graph.traverse(node_id, kind, "out")["neighbours"]:
        return n["node_id"]
    raise LookupError(f"no {kind} edge from {node_id}")


def answer_status(graph: Graph, number: str):
    node = claim_node(graph, number)
    return read_attr(graph, node, "status")


def answer_adjuster(graph: Graph, number: str):
    node = claim_node(graph, number)
    if graph.variant == "flat":
        return json.loads(graph.get_node(node)["props"]["adjuster"])["name"]
    adjuster = follow(graph, node, "assessed_by")
    return read_attr(graph, adjuster, "name")


def main() -> int:
    questions = json.loads(
        (DATA_DIR / "questions.json").read_text(encoding="utf-8"))
    by_template = {}
    for q in questions:
        by_template.setdefault(q["template"], []).append(q)
    checks = [("claim-status", answer_status),
              ("claim-adjuster", answer_adjuster)]
    failed = False
    for variant in ("flat", "normalized", "shaped"):
        graph = Graph.load(DATA_DIR / f"ontology-{variant}.json")
        for template, solver in checks:
            for q in by_template[template][:2]:
                number = q["question"].split("claim ")[1].split("?")[0].split()[0]
                got = solver(graph, number)
                ok = str(got) == str(q["answer"])
                verdict = "ok" if ok else f"FAIL got {got!r} want {q['answer']!r}"
                print(f"{variant:>10} {q['id']} {template}: {verdict}")
                failed |= not ok
    print("SMOKE:", "FAIL" if failed else "ALL PATHS REACHABLE")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
