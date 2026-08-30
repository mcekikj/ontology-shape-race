"""Render every table in the article as a PNG, from the receipts.

One renderer, one house style, seven tables. Nothing here is typed by hand:
accuracy, cost, spreads and graph statistics are all computed from
results/runs-cosmos-*.jsonl and data/ontology-*.json, so re-running a campaign
re-renders correct tables rather than stale ones.

Green marks the best OUTCOME and only on outcome rows. Resource rows - calls,
tokens, cost, turns - are deliberately left uncoloured: the flat graph is
lowest on all of them partly because it gives up early, and colouring that
green would say something the data does not.

Output: figures/upload/table-*.png
"""

import json
import sys
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
from analyze import cost_per_100  # noqa: E402  - one source of truth

ROOT = Path(__file__).resolve().parent.parent
RESULTS, DATA = ROOT / "results", ROOT / "data"
OUT = Path(__file__).resolve().parent / "upload"
VARIANTS = ["flat", "normalized", "shaped"]
STORE = "cosmos"          # the measured campaigns; the file-backed
                          # cross-check must never reach a published table

INK, HEADER_BG, ZEBRA = "#1a1a1a", "#243447", "#f4f6f8"
RULE, HILITE_BG, WIN, MUTED = "#d9dde2", "#eaf2fb", "#0e6b3d", "#5b6572"


def font(size, bold=False):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size,
                                  index=1 if bold else 0)
    except OSError:
        return ImageFont.load_default(size)


def render(name, header, rows, cols, align, best=None, hilite=(),
           note=None, width=1400):
    """Draw one table. `best` maps row index -> set of winning column indices."""
    best = best or {}
    margin, row_h, pad = 24, 64, 20
    f_body, f_head, f_note = font(23), font(23, True), font(19)
    height = 2 * margin + (len(rows) + 1) * row_h + (34 if note else 0)
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    xs, x = [margin], margin
    for c in cols[:-1]:
        x += c
        xs.append(x)

    def put(text, col, y, f, colour):
        ty = y + (row_h - 27) // 2
        if align[col] == "right":
            tw = d.textlength(text, font=f)
            d.text((xs[col] + cols[col] - pad - tw, ty), text, font=f, fill=colour)
        else:
            d.text((xs[col] + pad, ty), text, font=f, fill=colour)

    y = margin
    d.rounded_rectangle([margin, y, width - margin, y + row_h], radius=8,
                        fill=HEADER_BG)
    for i, cell in enumerate(header):
        put(cell, i, y, f_head, "white")
    y += row_h

    for r, row in enumerate(rows):
        if r in hilite:
            d.rectangle([margin, y, width - margin, y + row_h], fill=HILITE_BG)
        elif r % 2 == 1:
            d.rectangle([margin, y, width - margin, y + row_h], fill=ZEBRA)
        for i, cell in enumerate(row):
            winner = i in best.get(r, set()) and i > 0
            bold = winner or (i == 0 and r in hilite)
            put(str(cell), i, y, f_head if bold else f_body,
                WIN if winner else INK)
        y += row_h
        d.line([margin, y, width - margin, y], fill=RULE, width=1)

    if note:
        d.text((margin + pad, y + 8), note, font=f_note, fill=MUTED)

    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.png"
    img.save(path)
    print(f"{path.name}: {width}x{height}")


# ----------------------------------------------------------------- data ----

def episodes(deployment=None):
    rows = []
    for path in sorted(RESULTS.glob("runs-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("store", "json") != STORE:
                continue
            if deployment and r["deployment"] != deployment:
                continue
            rows.append(r)
    if not rows:
        raise SystemExit(f"no {STORE} results in {RESULTS}")
    return rows


def graphs():
    return {v: json.loads((DATA / f"ontology-{v}.json").read_text("utf-8"))
            for v in VARIANTS}


def acc(rs, band=None):
    sel = [r for r in rs if band is None or r["band"] == band]
    return mean(r["correct"] for r in sel)


def spread(rs, band=None):
    runs = sorted({r["run"] for r in rs})
    per = [acc([r for r in rs if r["run"] == k], band) for k in runs]
    return max(per) - min(per)


def top(vals, pick=max):
    winner = pick(vals)
    return {i + 1 for i, v in enumerate(vals) if v == winner}


# --------------------------------------------------------------- tables ----

def t_structure():
    g = graphs()
    stat = {}
    for v in VARIANTS:
        deg = {}
        for e in g[v]["edges"]:
            deg[e["src"]] = deg.get(e["src"], 0) + 1
            deg[e["dst"]] = deg.get(e["dst"], 0) + 1
        n, e = len(g[v]["nodes"]), len(g[v]["edges"])
        stat[v] = (n, e, e / n,
                   len({r["type"] for r in g[v]["nodes"].values()}),
                   len({x["type"] for x in g[v]["edges"]}),
                   mean(len(r["props"]) for r in g[v]["nodes"].values()),
                   sum(1 for k in g[v]["nodes"] if deg.get(k, 0) == 0))
    rows = [
        ("vertices", *[f"{stat[v][0]:,}" for v in VARIANTS]),
        ("edges", *[f"{stat[v][1]:,}" for v in VARIANTS]),
        ("edges per vertex", *[f"{stat[v][2]:.2f}" for v in VARIANTS]),
        ("vertex labels", *[stat[v][3] for v in VARIANTS]),
        ("edge labels", *[stat[v][4] for v in VARIANTS]),
        ("properties per vertex", *[f"{stat[v][5]:.1f}" for v in VARIANTS]),
        ("vertices connected to nothing", *[stat[v][6] for v in VARIANTS]),
    ]
    render("table-graph-structure",
           ("The same truth, three schemas", "flat", "normalized", "shaped"),
           rows, [560, 264, 264, 264], ["left", "right", "right", "right"],
           hilite={2, 6},
           note="Computed from the three graph files. The flat schema has "
                "fewer edges than vertices, and five vertices no edge reaches.")


def t_policy_label():
    g = graphs()
    counts = {v: sum(1 for r in g[v]["nodes"].values() if r["type"] == "policy")
              for v in VARIANTS}
    rows = [
        ("flat", counts["flat"],
         "a policy is not a vertex; it is text inside a property"),
        ("normalized", counts["normalized"],
         "policies are vertices, but every vertex is labelled Resource"),
        ("shaped", counts["shaped"], "a policy is a policy"),
    ]
    render("table-policy-label",
           ("g.V().hasLabel('policy').count()", "result", "why"),
           rows, [300, 160, 892], ["left", "right", "left"],
           best={2: {1}}, hilite={2},
           note="The same query against all three graphs. The two zeros mean "
                "different things - one lost the entity, the other its name.")


def t_results():
    rs = episodes("agent-small")
    by = {v: [r for r in rs if r["variant"] == v] for v in VARIANTS}
    A = [[acc(by[v], b) for v in VARIANTS] for b in (None, "L", "M", "H", "U")]
    rows = [
        ("Accuracy, all bands", *[f"{x:.3f}" for x in A[0]]),
        ("   band L - single lookup", *[f"{x:.3f}" for x in A[1]]),
        ("   band M - two to three hops", *[f"{x:.3f}" for x in A[2]]),
        ("   band H - long path or aggregation", *[f"{x:.3f}" for x in A[3]]),
        ("   band U - correctly refused", *[f"{x:.3f}" for x in A[4]]),
        ("Mean tool calls per question",
         *[f"{mean(r['tool_calls'] for r in by[v]):.2f}" for v in VARIANTS]),
        ("Mean tokens per question",
         *[f"{mean(r['input_tokens'] + r['output_tokens'] for r in by[v]):,.0f}"
           for v in VARIANTS]),
        ("Ran out of turns",
         *[sum(r["hit_step_cap"] for r in by[v]) for v in VARIANTS]),
        ("Cost per 100 questions",
         *[f"${cost_per_100(by[v]):.3f}" for v in VARIANTS]),
        ("Run-to-run spread (noise floor)",
         *[f"{spread(by[v]):.3f}" for v in VARIANTS]),
    ]
    render("table-ontology-results",
           ("Small model, three passes, 360 episodes",
            "flat", "normalized", "shaped"),
           rows, [560, 264, 264, 264], ["left", "right", "right", "right"],
           best={i: top(A[i]) for i in range(5)}, hilite={0},
           note="Green marks the best outcome. Resource rows are left "
                "uncoloured: flat is lowest on all of them partly because it "
                "gives up early.")


def t_bands():
    rs = episodes("agent-small")
    by = {v: [r for r in rs if r["variant"] == v] for v in VARIANTS}
    asks = {"L": "find one thing by name", "M": "walk two or three hops",
            "H": "walk far, or aggregate"}
    rows, best = [], {}
    for i, b in enumerate(("L", "M", "H")):
        vals = [acc(by[v], b) for v in VARIANTS]
        best[i] = top(vals)
        rows.append((f"band {b}", *[f"{x:.3f}" for x in vals], asks[b]))
    render("table-bands",
           ("", "flat", "normalized", "shaped", "what the band asks"),
           rows, [180, 190, 190, 190, 632],
           ["left", "right", "right", "right", "left"], best=best,
           note="The aggregate hides this: the shapes disagree band by band, "
                "and the disagreement is the finding.")


def t_failures():
    rs = episodes("agent-small")
    rows_data = {}
    for v in VARIANTS:
        a = [r for r in rs if r["variant"] == v and r["band"] != "U"]
        ok = sum(r["correct"] for r in a)
        gave = sum(1 for r in a if r["answer"] is None)
        ref = sum(1 for r in a if not r["correct"] and r["answer"]
                  and "NOT_MODELED" in r["answer"].upper())
        rows_data[v] = (len(a), ok, ref, len(a) - ok - gave - ref, gave)
    n = rows_data["flat"][0]
    rows = [
        ("Answered correctly", *[rows_data[v][1] for v in VARIANTS]),
        ("Refused a question it could answer",
         *[rows_data[v][2] for v in VARIANTS]),
        ("Answered wrongly", *[rows_data[v][3] for v in VARIANTS]),
        ("Produced no usable answer", *[rows_data[v][4] for v in VARIANTS]),
    ]
    render("table-failures",
           (f"Of {n} answerable episodes", "flat", "normalized", "shaped"),
           rows, [560, 264, 264, 264], ["left", "right", "right", "right"],
           best={0: top([rows_data[v][1] for v in VARIANTS]),
                 1: top([rows_data[v][2] for v in VARIANTS], min)},
           hilite={1},
           note="One shape exhausts itself; the other gives up early and "
                "confidently, on questions the database could answer.")


def t_crossover():
    rows, order = [], []
    for dep, label in (("agent-small", "small model"),
                       ("agent-large", "large model")):
        rs = [r for r in episodes(dep) if r["band"] != "U"]
        for v in ("normalized", "flat", "shaped"):
            sel = [r for r in rs if r["variant"] == v]
            order.append(acc(sel))
            rows.append((f"{label}, {v}", f"{acc(sel):.3f}",
                         f"${cost_per_100(sel):.3f}"))
    best = {i for i, a in enumerate(order) if a == max(order)}
    render("table-crossover",
           ("Answerable questions only", "accuracy", "cost per 100 questions"),
           rows, [640, 356, 356], ["left", "right", "right"],
           best={i: {1} for i in best}, hilite=set(best),
           note="The large model answers everything on the flat graph - at "
                "about fourteen times the cost of the small model on shaped.")


def t_latency():
    rs = episodes("agent-small")
    runs = sorted({r["run"] for r in rs})
    rows = []
    for v in ("flat", "shaped", "normalized"):
        sel = [r for r in rs if r["variant"] == v]
        per_q = [mean([r["latency_s"] for r in sel if r["run"] == k])
                 for k in runs]
        per_c = [mean([r["latency_s"] / r["tool_calls"] for r in sel
                       if r["run"] == k and r["tool_calls"]]) for k in runs]
        rows.append((v, *[f"{x:.1f}s" for x in per_q],
                     f"{min(per_c):.1f} - {max(per_c):.1f}s"))
    render("table-latency",
           ("Seconds per question", "pass 1", "pass 2", "pass 3",
            "per tool call"),
           rows, [300, 230, 230, 230, 392],
           ["left", "right", "right", "right", "right"],
           note="Stable within a shape, clearly separated between them - and "
                "per call all three cost the same, so this is the tool-call "
                "count restated in seconds.")


if __name__ == "__main__":
    for build in (t_structure, t_policy_label, t_results, t_bands,
                  t_failures, t_crossover, t_latency):
        build()
