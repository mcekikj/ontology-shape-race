"""Offline proof that the tool surface suffices on every ablation variant.

Same contract as smoke_test.py: walk each graph using ONLY the four public
tools, scripted by hand, and assert the oracle answer is reachable. No
model, no network.

The one addition is translation. The anonymised variants have renamed
their vocabulary, so the scripted walk translates its type and edge names
through the mapping committed inside each graph file - which is precisely
the position the agent is in: the structure is intact, but nothing answers
to its domain name any more. If these walks pass, a wrong campaign answer
on an anonymised graph means the MODEL could not cope with the renamed
world, not that the world lost a road.

The claim-holder-city check matters most here: it proves the two-hop route
(filed_against, then held_by) survives in shaped-minus and shaped-bare
after their shortcut is removed - reachability was the thing the transform
was proven not to remove, and this walks it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from graph import Graph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VARIANTS = ["shaped", "shaped-minus", "shaped-anon", "shaped-bare"]


class Walker:
    """The four tools plus a vocabulary translation layer."""

    def __init__(self, variant: str):
        payload = json.loads(
            (DATA_DIR / f"ontology-{variant}.json").read_text(
                encoding="utf-8"))
        self.graph = Graph(payload)
        mapping = payload.get("mapping", {})
        self.types = mapping.get("types", {})
        self.edges = mapping.get("edges", {})
        self.has_shortcut = variant in ("shaped", "shaped-anon")

    def t(self, name: str) -> str:
        return self.types.get(name, name)

    def e(self, name: str) -> str:
        return self.edges.get(name, name)

    def claim_node(self, number: str) -> str:
        hits = self.graph.find_nodes(number, node_type=self.t("claim"))
        return hits["nodes"][0]["id"]

    def follow(self, node_id: str, kind: str, direction: str = "out") -> str:
        found = self.graph.traverse(node_id, self.e(kind), direction)
        return found["neighbours"][0]["node_id"]

    def prop(self, node_id: str, key: str):
        return self.graph.get_node(node_id)["props"].get(key)


def answer_status(w: Walker, number: str):
    return w.prop(w.claim_node(number), "status")


def answer_adjuster(w: Walker, number: str):
    return w.prop(w.follow(w.claim_node(number), "assessed_by"), "name")


def answer_holder_city(w: Walker, number: str):
    """The shortcut's home turf - and the -minus variants' longer road."""
    claim = w.claim_node(number)
    if w.has_shortcut:
        holder = w.follow(claim, "held_by")
    else:
        policy = w.follow(claim, "filed_against")
        holder = w.follow(policy, "held_by")
    return w.prop(holder, "city")


def main() -> int:
    questions = json.loads(
        (DATA_DIR / "questions.json").read_text(encoding="utf-8"))
    by_template = {}
    for q in questions:
        by_template.setdefault(q["template"], []).append(q)
    checks = [("claim-status", answer_status),
              ("claim-adjuster", answer_adjuster),
              ("claim-holder-city", answer_holder_city)]
    failed = False
    for variant in VARIANTS:
        w = Walker(variant)
        for template, solver in checks:
            for q in by_template[template][:2]:
                number = (q["question"].split("claim ")[1]
                          .split("?")[0].split()[0])
                got = solver(w, number)
                ok = str(got) == str(q["answer"])
                verdict = "ok" if ok else f"FAIL got {got!r} " \
                                          f"want {q['answer']!r}"
                print(f"{variant:>13} {q['id']} {template}: {verdict}")
                failed |= not ok
    print("SMOKE:", "FAIL" if failed else "ALL PATHS REACHABLE")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
