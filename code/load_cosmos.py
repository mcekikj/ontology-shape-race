"""Load the three ontologies into Azure Cosmos DB for Apache Gremlin.

The generator writes JSON; this script materialises it into three Gremlin
graph containers, one per ontology. Those containers are what the agent
traverses during the measured campaigns and what the portal's graph explorer
draws, so what you query is exactly what was measured.

Every load verifies its own result: vertex and edge counts must match the
source JSON, or the load reports a mismatch rather than leaving you to
discover a half-built graph later.

Usage:
  set -a && source .env && set +a
  python load_cosmos.py                # all three
  python load_cosmos.py --shapes flat  # just one
  python load_cosmos.py --verify       # count vertices/edges, load nothing

Environment: COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_KEY.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATABASE = "ontologies"
SHAPES = ["flat", "normalized", "shaped",
          # article 4: the winner taken apart - see build_ablations.py
          "shaped-minus", "shaped-anon", "shaped-bare"]
WAVE = 10           # concurrent in-flight requests. Cosmos takes one
                    # traversal per request - multi-statement scripts are
                    # rejected - so throughput comes from concurrency, but
                    # serverless has a throughput ceiling and a 60s request
                    # timeout: bursts of 40 queue behind it and time out.
PACE = 0.15         # seconds between waves, for the same reason


def literal(value) -> str:
    """Render a Python value as a Gremlin literal.

    Values are stored verbatim, including the flat graph's long JSON-blob
    properties. An earlier version truncated them so the portal's explorer
    stayed tidy, which quietly made the Cosmos copy differ from the measured
    JSON - equivalence_check.py caught it. Fidelity beats tidiness: the
    largest property here is about 1,200 characters, far inside Cosmos's
    limits, and a wall of JSON on a policyholder node is exactly what the flat
    ontology looks like.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    text = (text.replace("\\", "\\\\").replace("'", "\\'")
                .replace("\n", " ").replace("\r", " "))
    return f"'{text}'"


def cosmos_id(node_id: str) -> str:
    """Cosmos item ids may not contain '#', which the normalized ontology uses
    to name attribute nodes (`policy:PL-009#premium`). Swapping it for '~'
    keeps ids unique and readable; the untouched original is stored on every
    vertex as `source_id` so the mapping back to the JSON is explicit rather
    than folklore."""
    return node_id.replace("#", "~")


def vertex_statements(graph: dict) -> list:
    """One addV per node. `pk` is the partition key; label is the node type."""
    out = []
    for node_id, rec in graph["nodes"].items():
        parts = [f"g.addV('{rec['type']}')",
                 f".property('id', {literal(cosmos_id(node_id))})",
                 f".property('pk', {literal(rec['type'])})",
                 f".property('source_id', {literal(node_id)})"]
        for key, value in rec["props"].items():
            parts.append(f".property('{key}', {literal(value)})")
        out.append("".join(parts))
    return out


def edge_statements(graph: dict) -> list:
    out = []
    for edge in graph["edges"]:
        stmt = (f"g.V({literal(cosmos_id(edge['src']))})"
                f".addE('{edge['type']}')")
        for key, value in edge.get("props", {}).items():
            stmt += f".property('{key}', {literal(value)})"
        stmt += f".to(g.V({literal(cosmos_id(edge['dst']))}))"
        out.append(stmt)
    return out


def submit_with_retry(client, query: str, attempts: int = 5):
    """Serverless Cosmos throttles under load and the odd request times out.
    A transient failure must not abandon a half-built graph, so each statement
    gets a few backed-off retries before the load is allowed to fail."""
    for attempt in range(attempts):
        try:
            return client.submitAsync(query).result().all().result()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def run(client, statements, label: str) -> None:
    """Submit in waves, retrying transient failures, so the graph is either
    complete or the load fails loudly - never quietly partial."""
    total = len(statements)
    for i in range(0, total, WAVE):
        chunk = statements[i:i + WAVE]
        futures = []
        for query in chunk:
            try:
                futures.append((query, client.submitAsync(query)))
            except Exception:
                futures.append((query, None))
        for query, future in futures:
            try:
                if future is None:
                    raise RuntimeError("submit failed")
                future.result().all().result()
            except Exception:
                submit_with_retry(client, query)
        done = min(i + WAVE, total)
        print(f"\r  {label}: {done}/{total}", end="", file=sys.stderr,
              flush=True)
        time.sleep(PACE)
    print(file=sys.stderr)


def connect(shape: str):
    import os
    from gremlin_python.driver import client as gremlin_client
    from gremlin_python.driver import serializer

    endpoint = os.environ.get("COSMOS_GREMLIN_ENDPOINT", "")
    key = os.environ.get("COSMOS_GREMLIN_KEY", "")
    if not endpoint or not key:
        raise SystemExit("set COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_KEY")
    return gremlin_client.Client(
        endpoint, "g",
        username=f"/dbs/{DATABASE}/colls/{shape}",
        password=key,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def clear(client) -> None:
    """Empty the graph in bounded batches.

    `g.V().drop()` on a few thousand vertices exceeds Cosmos's 60 second
    request timeout and leaves the graph half-dropped, which is worse than
    not trying. Dropping in slices keeps every request small."""
    while True:
        remaining = client.submit("g.V().count()").all().result()[0]
        if not remaining:
            return
        client.submit("g.V().limit(200).drop()").all().result()
        time.sleep(0.1)


def graph_counts(client) -> tuple:
    """Vertex and edge counts, as two requests: Cosmos rejects a list
    expression like [a, b] with 'Non-constant List expressions are not
    supported'."""
    vertices = client.submit("g.V().count()").all().result()[0]
    edges = client.submit("g.E().count()").all().result()[0]
    return vertices, edges


def load(shape: str) -> bool:
    graph = json.loads(
        (DATA_DIR / f"ontology-{shape}.json").read_text(encoding="utf-8"))
    client = connect(shape)
    try:
        print(f"{shape}: clearing", file=sys.stderr)
        clear(client)
        run(client, vertex_statements(graph), f"{shape} vertices")
        run(client, edge_statements(graph), f"{shape} edges")
        counts = graph_counts(client)
        expected = (len(graph["nodes"]), len(graph["edges"]))
        ok = counts == expected
        print(f"{shape}: loaded {counts[0]} vertices, {counts[1]} edges "
              f"(source has {expected[0]}, {expected[1]})"
              f"{'  OK' if ok else '  MISMATCH'}")
        return ok
    finally:
        client.close()


def verify(shape: str) -> bool:
    graph = json.loads(
        (DATA_DIR / f"ontology-{shape}.json").read_text(encoding="utf-8"))
    client = connect(shape)
    try:
        counts = graph_counts(client)
        expected = (len(graph["nodes"]), len(graph["edges"]))
        ok = counts == expected
        print(f"{shape:>10}: cosmos {counts[0]:>5} vertices {counts[1]:>5} "
              f"edges | source {expected[0]:>5} {expected[1]:>5}  "
              f"{'OK' if ok else 'MISMATCH'}")
        return ok
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shapes", default=",".join(SHAPES))
    parser.add_argument("--verify", action="store_true",
                        help="count what is in Cosmos, load nothing")
    args = parser.parse_args()
    shapes = [s.strip() for s in args.shapes.split(",") if s.strip()]
    for shape in shapes:
        if shape not in SHAPES:
            raise SystemExit(f"unknown shape {shape!r}")
    # A graph that does not match its source must fail loudly: every campaign
    # number downstream assumes the store holds exactly what the generator
    # produced.
    results = [(verify if args.verify else load)(shape) for shape in shapes]
    if not all(results):
        raise SystemExit("one or more graphs do not match the source data")


if __name__ == "__main__":
    main()
