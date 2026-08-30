"""Prove the experiment's central rule: three shapes, one truth.

Two independent checks run here.

1. RECONSTRUCTION. Each ontology is walked back into the canonical fact set
   and compared to the fact set of the raw data. If a variant added, dropped
   or blurred a fact, the difference is printed and this exits non-zero.

2. REDUNDANT EDGES. Reconstruction alone has a blind spot: it only sees the
   structures its reconstructor reads. The flat graph's `related` edges and
   the shaped graph's derived `held_by` shortcuts carry no fact of their own -
   both re-express facts stored elsewhere - so reconstruction ignores them,
   and a corrupted or missing shortcut would pass unnoticed while the agent
   traverses it every day. This check verifies each of those edges against the
   facts it claims to re-express.

The experiment is invalid unless both pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from build_ontologies import BUILDERS
from generate_facts import canonical_facts

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_graph(name: str) -> dict:
    return json.loads(
        (DATA_DIR / f"ontology-{name}.json").read_text(encoding="utf-8"))


def holder_of_claim(truth: set) -> dict:
    """claim id -> policyholder id, derived from the raw facts alone."""
    claim_policy = {eid: value for etype, eid, attr, value in truth
                    if etype == "claim" and attr == "filed_against"}
    policy_holder = {eid: value for etype, eid, attr, value in truth
                     if etype == "policy" and attr == "held_by"}
    return {claim: policy_holder[policy]
            for claim, policy in claim_policy.items()}


def check_redundant_edges(truth: set) -> list:
    """Verify edges that carry no fact of their own but that agents walk."""
    problems = []
    expected = holder_of_claim(truth)

    # flat: every `related` edge must join a policyholder to a claim filed
    # against one of that holder's policies, and every claim must have one.
    flat = load_graph("flat")
    related = [e for e in flat["edges"] if e["type"] == "related"]
    seen = set()
    for edge in related:
        holder = edge["src"].split(":", 1)[1]
        claim = edge["dst"].split(":", 1)[1]
        seen.add(claim)
        if expected.get(claim) != holder:
            problems.append(
                f"flat: `related` edge joins {holder} to claim {claim}, "
                f"but that claim belongs to {expected.get(claim)}")
    for claim in expected:
        if claim not in seen:
            problems.append(f"flat: claim {claim} has no `related` edge")
    if len(related) != len(expected):
        problems.append(f"flat: {len(related)} `related` edges for "
                        f"{len(expected)} claims")

    # shaped: every derived `held_by` edge must be the claim-to-holder
    # shortcut, and every claim must have exactly one.
    shaped = load_graph("shaped")
    derived = [e for e in shaped["edges"] if e["props"].get("derived")]
    seen = set()
    for edge in derived:
        claim = edge["src"].split(":", 1)[1]
        holder = edge["dst"].split(":", 1)[1]
        if edge["type"] != "held_by":
            problems.append(f"shaped: unexpected derived edge type "
                            f"{edge['type']!r}")
        if claim in seen:
            problems.append(f"shaped: claim {claim} has more than one shortcut")
        seen.add(claim)
        if expected.get(claim) != holder:
            problems.append(
                f"shaped: derived shortcut sends claim {claim} to {holder}, "
                f"but that claim belongs to {expected.get(claim)}")
    for claim in expected:
        if claim not in seen:
            problems.append(f"shaped: claim {claim} has no derived shortcut")
    return problems


def main() -> int:
    data = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    truth = canonical_facts(data)
    print(f"canonical facts: {len(truth)}")
    failed = False

    for name, (_, reconstruct) in BUILDERS.items():
        rebuilt = reconstruct(load_graph(name))
        missing = truth - rebuilt
        invented = rebuilt - truth
        if missing or invented:
            failed = True
            print(f"{name}: FAIL - {len(missing)} facts missing, "
                  f"{len(invented)} facts invented")
            for fact in sorted(missing)[:5]:
                print(f"  missing:  {fact}")
            for fact in sorted(invented)[:5]:
                print(f"  invented: {fact}")
        else:
            print(f"{name}: lossless - all {len(rebuilt)} facts reconstructed")

    problems = check_redundant_edges(truth)
    if problems:
        failed = True
        print(f"redundant edges: FAIL - {len(problems)} problem(s)")
        for problem in problems[:8]:
            print(f"  {problem}")
    else:
        print("redundant edges: flat `related` and shaped derived shortcuts "
              "all agree with the facts they re-express")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
