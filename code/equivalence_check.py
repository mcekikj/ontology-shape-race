"""Does the backing store change what the agent sees? Check, do not assume.

The campaigns measure an agent whose four tools query Cosmos DB for Apache
Gremlin. The same three graphs can also be read straight from the JSON the
generator emits. If the two implementations answer every tool call
identically, then the engine underneath is not shaping the answers the agent
sees - so a difference between ontologies is a difference of design, not of
query planning. That is the claim the article makes, and this is its evidence.

The comparison replays REAL tool calls: every call the agent actually made
during the published campaigns is re-issued against both implementations and
the responses are compared field by field.

Usage:
  set -a && source .env && set +a
  python equivalence_check.py                  # sample of real calls
  python equivalence_check.py --all            # every recorded call (slow)
  python equivalence_check.py --shapes shaped
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from graph import Graph, dispatch
from graph_cosmos import CosmosGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
SHAPES = ["flat", "normalized", "shaped"]
SAMPLE = 120
SEED = 20260829


def recorded_calls(variant: str) -> list:
    """Every tool call the agent made against this shape, deduplicated."""
    seen, calls = set(), []
    for path in sorted(RESULTS_DIR.glob("runs-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record["variant"] != variant:
                continue
            for step in record["steps"]:
                key = (step["tool"], json.dumps(step["arguments"],
                                                sort_keys=True))
                if key not in seen:
                    seen.add(key)
                    calls.append((step["tool"], step["arguments"]))
    return calls


def normalise(payload):
    """Order within a result list is an implementation detail; content is not.
    Sort neighbour and node lists so the comparison is about what the agent can
    learn, not about which order two engines happened to return it in."""
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            if key in ("nodes", "neighbours", "edges") and isinstance(value, list):
                out[key] = sorted(
                    (normalise(v) for v in value),
                    key=lambda v: json.dumps(v, sort_keys=True))
            else:
                out[key] = normalise(value)
        return out
    if isinstance(payload, list):
        return [normalise(v) for v in payload]
    return payload


def compare_shape(variant: str, limit: int) -> tuple:
    local = Graph.load(DATA_DIR / f"ontology-{variant}.json")
    remote = CosmosGraph(variant)
    calls = recorded_calls(variant)
    if limit and len(calls) > limit:
        random.Random(SEED).shuffle(calls)
        calls = calls[:limit]
    mismatches = []
    try:
        for i, (tool, arguments) in enumerate(calls, 1):
            a = normalise(dispatch(local, tool, arguments))
            b = normalise(dispatch(remote, tool, arguments))
            if a != b:
                mismatches.append((tool, arguments, a, b))
            print(f"\r  {variant}: {i}/{len(calls)} calls, "
                  f"{len(mismatches)} mismatched", end="", file=sys.stderr,
                  flush=True)
    finally:
        remote.close()
    print(file=sys.stderr)
    return len(calls), mismatches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shapes", default=",".join(SHAPES))
    parser.add_argument("--all", action="store_true",
                        help="replay every recorded call, not a sample")
    args = parser.parse_args()
    limit = 0 if args.all else SAMPLE

    total, failed = 0, 0
    for variant in [s.strip() for s in args.shapes.split(",") if s.strip()]:
        count, mismatches = compare_shape(variant, limit)
        total += count
        failed += len(mismatches)
        status = "IDENTICAL" if not mismatches else f"{len(mismatches)} DIFFER"
        print(f"{variant:>10}: {count} real tool calls replayed - {status}")
        for tool, arguments, a, b in mismatches[:3]:
            print(f"    {tool}({json.dumps(arguments)})")
            print(f"      json  : {json.dumps(a)[:150]}")
            print(f"      cosmos: {json.dumps(b)[:150]}")

    print(f"\n{total} tool calls replayed against both implementations; "
          f"{failed} differed")
    if failed:
        print("The backing store IS a variable. The article's claim that it is "
              "not does not hold - investigate before publishing.")
    else:
        print("The four tools return identical answers from local JSON and "
              "from Cosmos DB. The agent cannot tell which store it is "
              "reading, so the store is not a variable in the experiment.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
