"""Turn the raw campaign records into the numbers the article quotes.

Every figure printed here is computed from results/runs-*.jsonl; nothing is
hand-entered. Prices are the verified Azure retail rates for the two
deployments used (captured 2026-08-29, GlobalStandard, Sweden Central).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

RESULTS = Path(__file__).resolve().parent.parent / "results"
VARIANTS = ["flat", "normalized", "shaped"]
BANDS = ["L", "M", "H", "U"]

# A find_nodes or traverse response that found nothing serialises to about 48
# characters ({"total_matches": 0, "returned": 0, "nodes": []}); the smallest
# response carrying an actual hit is comfortably over 90. Sixty sits in that
# gap and is the cheapest way to ask "did this call come back empty?" without
# re-parsing every recorded payload.
EMPTY_RESULT_CHARS = 60

# verified 2026-08-29 from the Azure Retail Prices API, per 1M tokens
PRICES = {
    "agent-small": {"model": "gpt-5.4-nano", "in": 0.20, "out": 1.25},
    "agent-large": {"model": "gpt-5.5", "in": 5.00, "out": 30.00},
}


def load():
    rows = []
    for path in sorted(RESULTS.glob("runs-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def warn_about_duplicates(rows) -> None:
    """Every (deployment, variant, question, pass) should appear exactly once.

    A campaign that died half way and was restarted leaves a partial file
    beside a complete one, and since this script reads every runs-*.jsonl it
    would quietly average the same episodes twice. That is the one failure
    mode capable of silently corrupting every number here, so it is checked
    rather than assumed.
    """
    seen = defaultdict(int)
    for r in rows:
        seen[(r.get("store", "json"), r["deployment"], r["variant"],
              r["question_id"], r["run"])] += 1
    dupes = {k: n for k, n in seen.items() if n > 1}
    if not dupes:
        return
    print(f"WARNING: {len(dupes)} episode(s) appear more than once in "
          f"results/runs-*.jsonl.")
    print("  This usually means a restarted campaign left a partial file "
          "behind. Numbers below are unreliable until it is removed.")
    for key, n in list(dupes.items())[:5]:
        print(f"    {key} x{n}")


def cost_per_100(rows) -> float:
    """The article quotes cost per hundred questions throughout, so the
    conversion lives here rather than being rewritten at each call site."""
    return cost(rows) / len(rows) * 100


def cost(rows) -> float:
    total = 0.0
    for r in rows:
        p = PRICES.get(r["deployment"])
        if not p:
            continue
        total += r["input_tokens"] / 1e6 * p["in"]
        total += r["output_tokens"] / 1e6 * p["out"]
    return total


def failure_split(rows):
    """On answerable questions, how does a shape fail? The distinction that
    matters: a false refusal is the graph hiding a fact it contains."""
    answerable = [r for r in rows if r["band"] != "U"]
    correct = sum(r["correct"] for r in answerable)
    gave_up = sum(1 for r in answerable if r["answer"] is None)
    refused = sum(1 for r in answerable
                  if not r["correct"] and r["answer"]
                  and "NOT_MODELED" in r["answer"].upper())
    wrong = len(answerable) - correct - gave_up - refused
    return {"n": len(answerable), "correct": correct, "false_refusal": refused,
            "wrong": wrong, "gave_up": gave_up}


def section(title):
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def main() -> None:
    rows = load()
    if not rows:
        print("no results yet - run run_experiment.py first")
        return
    warn_about_duplicates(rows)
    by_campaign = defaultdict(list)
    for r in rows:
        by_campaign[(r.get("store", "json"), r["deployment"])].append(r)

    for (store, deployment), drows in sorted(by_campaign.items()):
        runs = sorted({r["run"] for r in drows})
        model = PRICES.get(deployment, {}).get("model", "unknown model - "
                                               "add it to PRICES for costs")
        where = ("Cosmos DB for Gremlin" if store == "cosmos"
                 else "committed JSON files")
        section(f"{deployment} ({model}) reading {where} - "
                f"{len(drows)} episodes, runs {runs}")

        print(f"{'metric':<34} " + "".join(f"{v:>13}" for v in VARIANTS))
        print("-" * 74)
        rowsets = {v: [r for r in drows if r["variant"] == v] for v in VARIANTS}

        def line(label, fn, fmt="{:>13.3f}"):
            print(f"{label:<34} " + "".join(
                fmt.format(fn(rowsets[v])) if rowsets[v] else f"{'-':>13}"
                for v in VARIANTS))

        line("accuracy, all bands", lambda rs: mean(r["correct"] for r in rs))
        for band in BANDS:
            line(f"  accuracy, band {band}",
                 lambda rs, b=band: mean([r["correct"] for r in rs
                                          if r["band"] == b] or [float("nan")]))
        line("mean tool calls", lambda rs: mean(r["tool_calls"] for r in rs),
             "{:>13.2f}")
        line("mean tokens per question",
             lambda rs: mean(r["input_tokens"] + r["output_tokens"]
                             for r in rs), "{:>13.0f}")
        line("step-cap hits", lambda rs: sum(r["hit_step_cap"] for r in rs),
             "{:>13.0f}")
        line("cost per 100 questions, USD",
             cost_per_100, "{:>13.3f}")

        if len(runs) > 1:
            print(f"\n{'run-to-run accuracy':<34} " +
                  "".join(f"{v:>13}" for v in VARIANTS))
            for k in runs:
                print(f"  run {k:<30} " + "".join(
                    f"{mean([r['correct'] for r in rowsets[v] if r['run'] == k]):>13.3f}"
                    for v in VARIANTS))
            print(f"  {'spread (noise floor)':<32} " + "".join(
                f"{max(p) - min(p):>13.3f}" for p in
                [[mean([r['correct'] for r in rowsets[v] if r['run'] == k])
                  for k in runs] for v in VARIANTS]))

        print(f"\n{'how it fails (answerable only)':<34} " +
              "".join(f"{v:>13}" for v in VARIANTS))
        splits = {v: failure_split(rowsets[v]) for v in VARIANTS if rowsets[v]}
        for key in ("n", "correct", "false_refusal", "wrong", "gave_up"):
            print(f"  {key:<32} " + "".join(
                f"{splits[v][key]:>13}" if v in splits else f"{'-':>13}"
                for v in VARIANTS))

    stores = sorted({r.get("store", "json") for r in rows})
    primary = "cosmos" if "cosmos" in stores else stores[0]
    section(f"crossover, ANSWERABLE questions only (bands L/M/H) - {primary}")
    print("  Unanswerable questions are excluded so that correct refusals\n"
          "  cannot flatter a shape that is merely biased toward refusing.\n")
    answerable = [r for r in rows
                  if r["band"] != "U" and r.get("store", "json") == primary]
    for deployment in ("agent-small", "agent-large"):
        for variant in VARIANTS:
            rs = [r for r in answerable if r["deployment"] == deployment
                  and r["variant"] == variant]
            if not rs:
                continue
            label = f"{'small' if deployment.endswith('small') else 'large'} / {variant}"
            print(f"  {label:<22} n={len(rs):>3}  "
                  f"accuracy={mean(r['correct'] for r in rs):.3f}  "
                  f"cost/100q=${cost_per_100(rs):.3f}")

    small_shaped = [r for r in answerable if r["deployment"] == "agent-small"
                    and r["variant"] == "shaped"]
    large_flat = [r for r in answerable if r["deployment"] == "agent-large"
                  and r["variant"] == "flat"]
    small_flat = [r for r in answerable if r["deployment"] == "agent-small"
                  and r["variant"] == "flat"]
    if large_flat and small_shaped:
        print(f"\n  buying past a bad shape:  large/flat is "
              f"{cost_per_100(large_flat) / cost_per_100(small_shaped):.1f}x "
              f"the cost of small/shaped,")
        print(f"  and {cost_per_100(large_flat) / cost_per_100(small_flat):.1f}x"
              f" the cost of running the same small model on that flat graph.")

    section(f"the article's inline figures - {primary} campaign")
    of_primary = [r for r in rows if r.get("store", "json") == primary]
    small = [r for r in of_primary if r["deployment"] == "agent-small"]
    large = [r for r in of_primary if r["deployment"] == "agent-large"]

    print("  per-template accuracy and mean tool calls, small model")
    print("  (accuracy is correct/episodes, where episodes = questions x passes):")
    templates = sorted({r["template"] for r in small},
                       key=lambda t: (next(r["band"] for r in small
                                           if r["template"] == t), t))
    print(f"    {'template':<24} {'band':<5} " +
          "".join(f"{v:>18}" for v in VARIANTS))
    for t in templates:
        cells = []
        for v in VARIANTS:
            sel = [r for r in small
                   if r["template"] == t and r["variant"] == v]
            if sel:
                acc = sum(r["correct"] for r in sel)
                calls = mean(r["tool_calls"] for r in sel)
                cells.append(f"{acc:>6}/{len(sel):<3} {calls:>5.2f}call")
            else:
                cells.append(f"{'-':>18}")
        band = next(r["band"] for r in small if r["template"] == t)
        print(f"    {t:<24} {band:<5} " + "".join(cells))

    buried = ["policy-premium", "provider-specialty"]
    n_buried = len({r["question_id"] for r in small
                    if r["template"] in buried})
    print(f"\n  questions about entities the flat shape buries "
          f"(no node of their own): {n_buried}")
    for deployment, drows in (("small", small), ("large", large)):
        rs = [r for r in drows if r["variant"] == "flat"
              and r["template"] in buried]
        if rs:
            print(f"    {deployment:<6} flat: {sum(r['correct'] for r in rs)}"
                  f"/{len(rs)} episodes correct")

    print("\n  flat, failing 'policy-premium' episodes: did an UNFILTERED\n"
          "  search hand the agent the containing node, unrecognised?")
    failing = [r for r in small if r["variant"] == "flat"
               and r["template"] == "policy-premium" and not r["correct"]]
    found = sum(1 for r in failing for s in r["steps"]
                if s["tool"] == "find_nodes"
                and not s["arguments"].get("node_type")
                and s["result_chars"] >= EMPTY_RESULT_CHARS)
    opened = sum(1 for r in failing for s in r["steps"]
                 if s["tool"] == "get_node"
                 and str(s["arguments"].get("node_id", "")).startswith(
                     "policyholder:"))
    print(f"    {len(failing)} failing episodes; unfiltered searches that "
          f"returned the container: {found}; get_node calls on it: {opened}")

    print("\n  cost per 100 CORRECT answers, small model (all bands):")
    for v in VARIANTS:
        rs = [r for r in small if r["variant"] == v]
        acc = mean(r["correct"] for r in rs)
        print(f"    {v:<12} ${cost_per_100(rs) / acc:.4f}")

    print("\n  normalized cost relative to shaped, small model:")
    for band in ("L", "M"):
        ratios = {}
        for v in ("normalized", "shaped"):
            rs = [r for r in small if r["variant"] == v and r["band"] == band]
            ratios[v] = (mean(r["input_tokens"] + r["output_tokens"]
                              for r in rs),
                         mean(r["tool_calls"] for r in rs))
        print(f"    band {band}: tokens "
              f"{ratios['normalized'][0] / ratios['shaped'][0]:.1f}x, "
              f"tool calls {ratios['normalized'][1] / ratios['shaped'][1]:.1f}x")

    print("\n  first tool call returned nothing (entry-point quality):")
    for deployment, drows in (("small", small), ("large", large)):
        if not drows:
            continue
        cells = []
        for v in VARIANTS:
            rs = [r for r in drows if r["variant"] == v and r["steps"]]
            empty = sum(1 for r in rs if r["steps"][0]["result_chars"] < EMPTY_RESULT_CHARS)
            cells.append(f"{v} {empty}/{len(rs)} ({empty / len(rs):.0%})")
        print(f"    {deployment:<6} " + "   ".join(cells))

    print("\n  traverse calls requesting an edge type the graph does not have")
    print("  (the instrument limitation section VI discloses):")
    edge_types = {}
    for variant in VARIANTS:
        graph = json.loads(
            (RESULTS.parent / "data" / f"ontology-{variant}.json")
            .read_text(encoding="utf-8"))
        edge_types[variant] = {e["type"] for e in graph["edges"]}
    bad_calls = {v: 0 for v in VARIANTS}
    tainted_refusals = {v: 0 for v in VARIANTS}
    for r in of_primary:
        bad = sum(1 for s in r["steps"]
                  if s["tool"] == "traverse"
                  and s["arguments"].get("edge_type")
                  and s["arguments"]["edge_type"]
                  not in edge_types[r["variant"]])
        bad_calls[r["variant"]] += bad
        if (bad and r["band"] != "U" and not r["correct"] and r["answer"]
                and "NOT_MODELED" in r["answer"].upper()):
            tainted_refusals[r["variant"]] += 1
    total = sum(bad_calls.values())
    print(f"    total {total}: " + "  ".join(
        f"{v} {bad_calls[v]}" for v in VARIANTS))
    print("    false refusals containing at least one such call: " + "  ".join(
        f"{v} {tainted_refusals[v]}" for v in VARIANTS))

    print("\n  per-band run-to-run spread (the band-level noise floors):")
    runs_here = sorted({r["run"] for r in small})
    if len(runs_here) > 1:
        for band in BANDS:
            cells = []
            for v in VARIANTS:
                per = [mean([r["correct"] for r in small
                             if r["variant"] == v and r["band"] == band
                             and r["run"] == k]) for k in runs_here]
                cells.append(f"{v} {max(per) - min(per):.3f}")
            print(f"    band {band}: " + "   ".join(cells))

    busiest = max(of_primary, key=lambda r: r["tool_calls"])
    print(f"\n  busiest episode: {busiest['tool_calls']} tool calls "
          f"({busiest['question_id']}, {busiest['variant']}, "
          f"{busiest['deployment']}) inside a {16}-turn budget")

    print("\n  latency, reported only to show it is not usable:")
    for v in VARIANTS:
        runs = sorted({r["run"] for r in small})
        per_q = [mean([r["latency_s"] for r in small
                       if r["variant"] == v and r["run"] == k]) for k in runs]
        per_c = [mean([r["latency_s"] / r["tool_calls"] for r in small
                       if r["variant"] == v and r["run"] == k and r["tool_calls"]])
                 for k in runs]
        print(f"    {v:<12} per question " +
              " ".join(f"{p:6.2f}s" for p in per_q) +
              "   per call " + " ".join(f"{p:.2f}s" for p in per_c))

    if len(stores) > 1:
        section("same experiment, two backing stores")
        print("  Does the store change the finding? Accuracy per shape, "
              "small model, all bands.\n")
        print(f"  {'store':<10} " + "".join(f"{v:>13}" for v in VARIANTS))
        for store in stores:
            rs = [r for r in rows if r.get("store", "json") == store
                  and r["deployment"] == "agent-small"]
            if not rs:
                continue
            print(f"  {store:<10} " + "".join(
                f"{mean([x['correct'] for x in rs if x['variant'] == v]):>13.3f}"
                if [x for x in rs if x["variant"] == v] else f"{'-':>13}"
                for v in VARIANTS))

    section("campaign totals, by store")
    for store in stores:
        rs = [r for r in rows if r.get("store", "json") == store]
        ti = sum(r["input_tokens"] for r in rs)
        to = sum(r["output_tokens"] for r in rs)
        label = ("Cosmos DB (measured)" if store == "cosmos"
                 else "generator's files (cross-check)")
        print(f"  {label:<32} {len(rs):>4} episodes  "
              f"{ti + to:>10,} tokens  ${cost(rs):>6.2f}")
        for deployment in sorted({r["deployment"] for r in rs}):
            drs = [r for r in rs if r["deployment"] == deployment]
            print(f"    {deployment:<30} {len(drs):>4} episodes  "
                  f"{sum(r['input_tokens'] + r['output_tokens'] for r in drs):>10,}"
                  f" tokens  ${cost(drs):>6.2f}")

    section("all campaigns pooled (not an article figure)")
    print(f"  episodes: {len(rows)}")
    print(f"  input tokens:  {sum(r['input_tokens'] for r in rows):,}")
    print(f"  output tokens: {sum(r['output_tokens'] for r in rows):,}")
    print(f"  measured cost: ${cost(rows):.2f}")
    print(f"  small campaign only: {len(small)} episodes, "
          f"{sum(r['input_tokens'] + r['output_tokens'] for r in small):,} "
          f"tokens, ${cost(small):.2f}")


if __name__ == "__main__":
    main()
