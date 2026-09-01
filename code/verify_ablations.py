"""Prove the ablation variants are transforms of the winner, not redesigns.

Four checks, and the experiment is invalid unless all pass:

1. DETERMINISM. Each committed ablation file regenerates byte-identically
   from the committed shaped graph. No hand edits can hide.

2. INVERTIBILITY. Deanonymizing shaped-anon reproduces shaped's nodes and
   edges exactly; deanonymizing shaped-bare reproduces shaped-minus. The
   anonymisation is a bijection - the graphs differ in language only.

3. GEOMETRY. shaped-minus is shaped with precisely the 90 derived edges
   removed and nothing else touched: same nodes object, and its edge list
   equals shaped's non-derived edges. No ablation variant carries a
   derived flag on any surviving edge in the -minus/-bare cases.

4. LOSSLESSNESS. Every variant reconstructs the same canonical fact set as
   the raw data - through the inverse mapping where the vocabulary is
   anonymised, because reconstruction is defined over the domain
   vocabulary. Removing derived edges cannot cost a fact (article 3's
   reconstructor already ignored them); this check proves it anyway.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from build_ablations import ABLATIONS, deanonymize, load_shaped
from build_ontologies import reconstruct_shaped
from generate_facts import canonical_facts

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> dict:
    return json.loads(
        (DATA_DIR / f"ontology-{name}.json").read_text(encoding="utf-8"))


def content(graph: dict) -> tuple:
    """nodes and edges only - the variant label is naming, not content."""
    return (graph["nodes"],
            sorted(graph["edges"], key=lambda e: json.dumps(e, sort_keys=True)))


def main() -> int:
    failed = False
    shaped = load_shaped()

    # 1. determinism: committed files match a fresh transform, byte level
    for name, transform in ABLATIONS.items():
        fresh = transform(shaped)
        fresh["variant"] = name
        rendered = json.dumps(fresh, indent=1, sort_keys=True) + "\n"
        committed = (DATA_DIR / f"ontology-{name}.json").read_text(
            encoding="utf-8")
        if rendered != committed:
            failed = True
            print(f"determinism: FAIL - {name} does not regenerate "
                  f"byte-identically")
        else:
            print(f"determinism: {name} regenerates byte-identically")

    # 2. invertibility: the anonymisation round-trips
    minus, anon, bare = (load(n) for n in
                         ("shaped-minus", "shaped-anon", "shaped-bare"))
    for label, anonymised, original in (("shaped-anon -> shaped", anon,
                                         shaped),
                                        ("shaped-bare -> shaped-minus", bare,
                                         minus)):
        if content(deanonymize(anonymised)) == content(original):
            print(f"invertibility: {label} - exact")
        else:
            failed = True
            print(f"invertibility: FAIL - {label} does not round-trip")

    # 3. geometry: -minus is shaped less exactly the derived edges
    derived = [e for e in shaped["edges"] if e["props"].get("derived")]
    kept = [e for e in shaped["edges"] if not e["props"].get("derived")]
    if minus["nodes"] != shaped["nodes"]:
        failed = True
        print("geometry: FAIL - shaped-minus touched the nodes")
    elif content(minus)[1] != content({"nodes": {}, "edges": kept})[1]:
        failed = True
        print("geometry: FAIL - shaped-minus edges are not shaped's "
              "non-derived edges")
    else:
        print(f"geometry: shaped-minus = shaped - {len(derived)} derived "
              f"edges, nodes untouched")
    for name, graph in (("shaped-minus", minus), ("shaped-bare", bare)):
        leftover = [e for e in graph["edges"] if e["props"].get("derived")]
        if leftover:
            failed = True
            print(f"geometry: FAIL - {name} still carries "
                  f"{len(leftover)} derived edges")

    # 4. losslessness, through the inverse mapping where needed
    data = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    truth = canonical_facts(data)
    print(f"canonical facts: {len(truth)}")
    for name, graph in (("shaped-minus", minus),
                        ("shaped-anon", deanonymize(anon)),
                        ("shaped-bare", deanonymize(bare))):
        rebuilt = reconstruct_shaped(graph)
        missing, invented = truth - rebuilt, rebuilt - truth
        if missing or invented:
            failed = True
            print(f"{name}: FAIL - {len(missing)} facts missing, "
                  f"{len(invented)} invented")
        else:
            print(f"{name}: lossless - all {len(rebuilt)} facts "
                  f"reconstructed")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
