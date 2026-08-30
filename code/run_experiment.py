"""Run the full campaign: every ontology x every question, repeated.

Usage:
  python run_experiment.py --deployment agent-small --runs 3
  python run_experiment.py --deployment agent-small --store json --runs 1

The tools read from Cosmos DB for Apache Gremlin by default - the campaigns
the article reports ran against those live graphs. `--store json` reads the
committed JSON files instead, which is how the cross-check campaign was run.
Every result record carries the store it used, so the two never mix.

Environment: ONTOLOGY_AGENTS_ENDPOINT, and AZURE_OPENAI_API_KEY or az login.

Every run writes one JSONL line per (variant, question): the full tool-call
trace, token counts, latency, the extracted answer and the oracle verdict.
Records are flushed as they complete and the file is append-only, so an
interrupted campaign loses nothing: point --resume at the file and it skips
what is already recorded and finishes the rest. analyze.py reads whatever has
accumulated.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agent import client_from_env, run_question, score
from graph import Graph
from graph_cosmos import CosmosGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
VARIANTS = ["flat", "normalized", "shaped"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", required=True,
                        help="Foundry model deployment name")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--bands", default="L,M,H,U")
    parser.add_argument("--pace", type=float, default=0.3,
                        help="seconds between questions")
    parser.add_argument("--resume", type=Path, default=None,
                        help="continue an interrupted campaign: append to this "
                             "results file and skip episodes it already has")
    parser.add_argument("--store", choices=["cosmos", "json"], default="cosmos",
                        help="where the four tools read the graph from: the "
                             "Cosmos DB for Gremlin graphs (default) or the "
                             "committed JSON files")
    args = parser.parse_args()

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    bands = {b.strip() for b in args.bands.split(",") if b.strip()}
    questions = [q for q in json.loads(
        (DATA_DIR / "questions.json").read_text(encoding="utf-8"))
        if q["band"] in bands]
    if args.store == "cosmos":
        graphs = {v: CosmosGraph(v) for v in variants}
    else:
        graphs = {v: Graph.load(DATA_DIR / f"ontology-{v}.json")
                  for v in variants}
    client = client_from_env()

    RESULTS_DIR.mkdir(exist_ok=True)
    done = set()
    if args.resume:
        out_path = args.resume
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["run"], r["variant"], r["question_id"]))
        print(f"resuming {out_path}: {len(done)} episodes already recorded")
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = RESULTS_DIR / f"runs-{args.store}-{stamp}.jsonl"
    print(f"writing {out_path}")

    total = args.runs * len(variants) * len(questions)
    completed = len(done)
    with out_path.open("a", encoding="utf-8") as out:
        for run_no in range(1, args.runs + 1):
            for variant in variants:
                for question in questions:
                    if (run_no, variant, question["id"]) in done:
                        continue
                    result = run_question(client, args.deployment,
                                          graphs[variant], question)
                    correct = score(question, result.answer)
                    record = result.to_dict()
                    record.update({
                        "store": args.store,
                        "run": run_no, "band": question["band"],
                        "template": question["template"],
                        "expected": question["answer"], "correct": correct,
                        "utc": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                    })
                    out.write(json.dumps(record) + "\n")
                    out.flush()
                    completed += 1
                    verdict = "ok " if correct else "MISS"
                    print(f"[{completed:3d}/{total}] run{run_no} {variant:>10} "
                          f"{question['id']}  {verdict} "
                          f"calls={record['tool_calls']:2d} "
                          f"tok={record['input_tokens'] + record['output_tokens']}")
                    time.sleep(args.pace)
    print(f"done: {out_path}")
    for graph in graphs.values():
        if hasattr(graph, "close"):
            graph.close()


if __name__ == "__main__":
    main()
