"""Turn the ablation campaign's records into the numbers article 4 quotes.

Reads only receipts. The campaign records carry a variant field, so this
script selects the four ablation cells and computes every figure the
results section needs - the 2x2 grid, the per-band grids, the shortcut's
home-turf isolation, the failure split, the costs - and then scores the
five registered predictions of docs/predictions.md, wrong ones included.

Reference values for P3 (the article-3 normalized per-run range) are
computed from the same results directory, never quoted from memory.

Nothing is hand-entered; prices are the verified Azure retail rates.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from analyze import (BANDS, cost, failure_split, load, section,
                     warn_about_duplicates)

CELLS = ["shaped", "shaped-minus", "shaped-anon", "shaped-bare"]
GRID = [("shaped", "shaped-minus"), ("shaped-anon", "shaped-bare")]
ROW_LABELS = ["domain vocabulary", "anonymous"]
COL_LABELS = ["shortcuts kept", "shortcuts removed"]
HOME_TURF = "claim-holder-city"      # the one template held_by compresses


def acc(rows) -> float:
    return sum(r["correct"] for r in rows) / len(rows) if rows else float("nan")


def by_variant(rows):
    out = defaultdict(list)
    for r in rows:
        out[r["variant"]].append(r)
    return out


def run_accs(rows) -> list:
    runs = defaultdict(list)
    for r in rows:
        runs[r["run"]].append(r["correct"])
    return sorted(sum(v) / len(v) for v in runs.values())


def spread(rows) -> float:
    accs = run_accs(rows)
    return max(accs) - min(accs) if accs else float("nan")


def grid(rowsets, select, fmt="{:.3f}"):
    print(f"{'':22}{COL_LABELS[0]:>18}{COL_LABELS[1]:>19}")
    for label, (a, b) in zip(ROW_LABELS, GRID):
        va = fmt.format(select(rowsets[a])) if rowsets[a] else "-"
        vb = fmt.format(select(rowsets[b])) if rowsets[b] else "-"
        print(f"{label:22}{va:>18}{vb:>19}")


def verdict(ok: bool | None) -> str:
    if ok is None:
        return "UNSETTLED"
    return "CONFIRMED" if ok else "REFUTED"


def main() -> None:
    rows = load()
    cosmos = [r for r in rows if r.get("store") == "cosmos"]

    small = [r for r in cosmos if r["deployment"] == "agent-small"
             and r["variant"] in CELLS and r["utc"] >= "2026-09-01"]
    large = [r for r in cosmos if r["deployment"] == "agent-large"
             and r["variant"] in CELLS and r["utc"] >= "2026-09-01"]
    # The dedupe guard runs on THIS campaign's selection: the fresh shaped
    # runs legitimately share (variant, question, run) keys with article 3's,
    # so checking across campaigns would always cry wolf.
    warn_about_duplicates(small + large)
    sv, lv = by_variant(small), by_variant(large)

    counts = {v: len(sv.get(v, [])) for v in CELLS}
    complete = all(n == 120 for n in counts.values())
    section(f"ablation campaign - small model "
            f"({sum(counts.values())}/480 episodes"
            f"{'' if complete else ' - INCOMPLETE, numbers provisional'})")
    for v in CELLS:
        rs = sv.get(v, [])
        if not rs:
            continue
        accs = ", ".join(f"{a:.3f}" for a in run_accs(rs))
        print(f"  {v:13} {len(rs):3} ep  runs [{accs}]  "
              f"overall {acc(rs):.3f}")

    section("the 2x2 - overall accuracy, small model")
    grid(sv, acc)

    section("the 2x2 per band, small model")
    for band in BANDS:
        print(f"\nband {band}:")
        grid({v: [r for r in sv.get(v, []) if r["band"] == band]
              for v in CELLS}, acc)

    section(f"the shortcut's home turf - {HOME_TURF}")
    grid({v: [r for r in sv.get(v, []) if r["template"] == HOME_TURF]
          for v in CELLS}, acc)
    print("\nevery other answerable template:")
    grid({v: [r for r in sv.get(v, [])
              if r["template"] != HOME_TURF and r["band"] != "U"]
          for v in CELLS}, acc)

    section("failure split on answerable questions, small model")
    print(f"{'variant':14}{'n':>5}{'correct':>9}{'false_ref':>11}"
          f"{'wrong':>7}{'gave_up':>9}")
    for v in CELLS:
        if not sv.get(v):
            continue
        f = failure_split(sv[v])
        print(f"{v:14}{f['n']:>5}{f['correct']:>9}{f['false_refusal']:>11}"
              f"{f['wrong']:>7}{f['gave_up']:>9}")

    section("effort and cost, small model")
    print(f"{'variant':14}{'tool_calls':>11}{'tokens/ep':>11}{'cost':>9}")
    for v in CELLS:
        rs = sv.get(v, [])
        if not rs:
            continue
        calls = mean(r["tool_calls"] for r in rs)
        toks = mean(r["input_tokens"] + r["output_tokens"] for r in rs)
        print(f"{v:14}{calls:>11.2f}{toks:>11.0f}{cost(rs):>9.3f}")

    if lv:
        section(f"large-model crossover ({sum(len(v) for v in lv.values())}"
                f"/160 episodes)")
        grid(lv, acc)
        for v in CELLS:
            if lv.get(v):
                print(f"  {v:13} answerable acc "
                      f"{acc([r for r in lv[v] if r['band'] != 'U']):.3f}  "
                      f"cost ${cost(lv[v]):.2f}")

    # ------------------------------------------------- the predictions ----
    section("scoring docs/predictions.md")
    if not complete:
        print("campaign incomplete - predictions are NOT scored on partial "
              "data.\n")
        return

    # P1: vocabulary loss > geometry loss, overall, small model
    d_vocab = acc(sv["shaped"]) - acc(sv["shaped-anon"])
    d_geom = acc(sv["shaped"]) - acc(sv["shaped-minus"])
    print(f"P1 vocabulary loss {d_vocab:+.3f} vs geometry loss "
          f"{d_geom:+.3f}: {verdict(d_vocab > d_geom)}")

    # P2: shaped-minus loses on the home-turf template, holds elsewhere.
    # "within noise" = within shaped's own run spread on the same rows.
    home_s = acc([r for r in sv["shaped"] if r["template"] == HOME_TURF])
    home_m = acc([r for r in sv["shaped-minus"]
                  if r["template"] == HOME_TURF])
    rest_s = acc([r for r in sv["shaped"]
                  if r["template"] != HOME_TURF and r["band"] != "U"])
    rest_m = acc([r for r in sv["shaped-minus"]
                  if r["template"] != HOME_TURF and r["band"] != "U"])
    noise = max(spread(sv["shaped"]), spread(sv["shaped-minus"]))
    p2 = (home_s - home_m > noise) and (abs(rest_s - rest_m) <= noise)
    print(f"P2 home turf {home_s:.3f}->{home_m:.3f}, elsewhere "
          f"{rest_s:.3f}->{rest_m:.3f}, noise {noise:.3f}: {verdict(p2)}")

    # P3: shaped-bare lands inside article-3 normalized's per-run range
    norm3 = [r for r in cosmos if r["deployment"] == "agent-small"
             and r["variant"] == "normalized"]
    lo, hi = min(run_accs(norm3)), max(run_accs(norm3))
    bare = acc(sv["shaped-bare"])
    print(f"P3 shaped-bare {bare:.3f} vs normalized per-run range "
          f"[{lo:.3f}, {hi:.3f}]: {verdict(lo <= bare <= hi)}")

    # P4: large model converges - every cell within shaped's large-model
    # result on answerable bands (single runs, so 'noise' borrows the
    # small campaign's largest run spread)
    if all(lv.get(v) for v in CELLS):
        tol = max(spread(sv[v]) for v in CELLS)
        ans = {v: acc([r for r in lv[v] if r["band"] != "U"]) for v in CELLS}
        p4 = all(abs(ans[v] - ans["shaped"]) <= tol for v in CELLS)
        print(f"P4 large answerable {', '.join(f'{v} {a:.3f}' for v, a in ans.items())}"
              f" (tol {tol:.3f}): {verdict(p4)}")
    else:
        print("P4: large campaign not yet run - UNSETTLED")

    # P5: anonymised variants false-refuse more than shaped
    fr = {v: failure_split(sv[v])["false_refusal"] for v in CELLS}
    p5 = fr["shaped-anon"] > fr["shaped"] and fr["shaped-bare"] > fr["shaped"]
    print(f"P5 false refusals {fr}: {verdict(p5)}")


if __name__ == "__main__":
    main()
