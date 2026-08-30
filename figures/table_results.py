"""Render the section IV results table as a PNG for Medium.

Same design family as the previous articles' tables. Hyphens only. Every
value, the answerable-episode denominator and which column is marked as
best are all computed from results/runs-*.jsonl, so a re-run of the campaign
re-renders a correct table rather than a stale one.

Prices come from code/analyze.py so the figure and the article's numbers can
never drift apart.

Output: figures/upload/table-ontology-results.png
"""

import json
import sys
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
from analyze import cost_per_100  # noqa: E402  - one source of truth

RESULTS = Path(__file__).resolve().parent.parent / "results"
VARIANTS = ["flat", "normalized", "shaped"]


STORE = "cosmos"   # the measured campaigns; runs-2026*.jsonl are the JSON
                   # cross-check and must never be averaged in with them


def load():
    rows = []
    for path in sorted(RESULTS.glob("runs-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if (r["deployment"] == "agent-small"
                        and r.get("store", "json") == STORE):
                    rows.append(r)
    if not rows:
        raise SystemExit(f"no {STORE} results found in {RESULTS}")
    return rows


rows = load()
by = {v: [r for r in rows if r["variant"] == v] for v in VARIANTS}
runs = sorted({r["run"] for r in rows})


def acc(rs, band=None):
    sel = [r for r in rs if band is None or r["band"] == band]
    return mean(r["correct"] for r in sel)


def spread(rs):
    per = [mean([r["correct"] for r in rs if r["run"] == k]) for k in runs]
    return max(per) - min(per)


HEADER = ("Same facts, three shapes", "flat", "normalized", "shaped")
ROWS = [
    ("Accuracy, all bands",
     *[f"{acc(by[v]):.3f}" for v in VARIANTS]),
    ("   band L - single lookup",
     *[f"{acc(by[v], 'L'):.3f}" for v in VARIANTS]),
    ("   band M - two to three hops",
     *[f"{acc(by[v], 'M'):.3f}" for v in VARIANTS]),
    ("   band H - long path or aggregation",
     *[f"{acc(by[v], 'H'):.3f}" for v in VARIANTS]),
    ("   band U - correctly refused",
     *[f"{acc(by[v], 'U'):.3f}" for v in VARIANTS]),
    ("Refused a question it could answer",
     *[f"{sum(1 for r in by[v] if r['band'] != 'U' and not r['correct'] and r['answer'] and 'NOT_MODELED' in r['answer'].upper())}"
       f" of {sum(1 for r in by[v] if r['band'] != 'U')}" for v in VARIANTS]),
    ("Mean tool calls per question",
     *[f"{mean(r['tool_calls'] for r in by[v]):.2f}" for v in VARIANTS]),
    ("Mean tokens per question",
     *[f"{mean(r['input_tokens'] + r['output_tokens'] for r in by[v]):,.0f}"
       for v in VARIANTS]),
    ("Ran out of turns",
     *[str(sum(r["hit_step_cap"] for r in by[v])) for v in VARIANTS]),
    ("Cost per 100 questions",
     *[f"${cost_per_100(by[v]):.3f}" for v in VARIANTS]),
    ("Run-to-run spread (noise floor)",
     *[f"{spread(by[v]):.3f}" for v in VARIANTS]),
]
HILITE = {0, 5}

W = 1400
MARGIN = 24
COLS = [560, 264, 264, 264]
ALIGN = ["left", "right", "right", "right"]
ROW_H, PAD_X = 66, 20

INK = "#1a1a1a"
HEADER_BG = "#243447"
ZEBRA = "#f4f6f8"
RULE = "#d9dde2"
HILITE_BG = "#eaf2fb"
WIN = "#0e6b3d"


def font(size, bold=False):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size,
                                  index=1 if bold else 0)
    except OSError:
        return ImageFont.load_default(size)


F_BODY, F_HEAD = font(24), font(24, bold=True)

H = 2 * MARGIN + (len(ROWS) + 1) * ROW_H
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)

x_pos = [MARGIN]
for w in COLS[:-1]:
    x_pos.append(x_pos[-1] + w)


def put(text, col, y, f, colour):
    ty = y + (ROW_H - 28) // 2
    if ALIGN[col] == "right":
        tw = d.textlength(text, font=f)
        d.text((x_pos[col] + COLS[col] - PAD_X - tw, ty), text, font=f,
               fill=colour)
    else:
        d.text((x_pos[col] + PAD_X, ty), text, font=f, fill=colour)


y = MARGIN
d.rounded_rectangle([MARGIN, y, W - MARGIN, y + ROW_H], radius=8,
                    fill=HEADER_BG)
for i, cell in enumerate(HEADER):
    put(cell, i, y, F_HEAD, "white")
y += ROW_H

# Green marks the best OUTCOME, and only on outcome rows. The resource rows
# (calls, tokens, steps, cost, spread) are deliberately left uncoloured: the
# flat shape is cheapest partly because it gives up early, so "lowest" there
# is not "best" and colouring it would say something the data does not.
# Rows 0-4 are accuracies (highest wins); row 5 counts false refusals (fewest
# wins). Computed from the data so a re-run cannot mislabel the winner.
OUTCOME_ROWS = {0: max, 1: max, 2: max, 3: max, 4: max, 5: min}
BEST = {}
for _row, _pick in OUTCOME_ROWS.items():
    _vals = [float(ROWS[_row][i + 1].split()[0]) for i in range(3)]
    _win = _pick(_vals)
    # every column that ties for best is marked, matching the article's table
    BEST[_row] = {i + 1 for i, v in enumerate(_vals) if v == _win}

for r, row in enumerate(ROWS):
    if r in HILITE:
        d.rectangle([MARGIN, y, W - MARGIN, y + ROW_H], fill=HILITE_BG)
    elif r % 2 == 1:
        d.rectangle([MARGIN, y, W - MARGIN, y + ROW_H], fill=ZEBRA)
    for i, cell in enumerate(row):
        winners = BEST.get(r, set())
        bold = (i in winners) or (i == 0 and r in HILITE)
        colour = WIN if (i in winners and i) else INK
        put(cell, i, y, F_HEAD if bold else F_BODY, colour)
    y += ROW_H
    d.line([MARGIN, y, W - MARGIN, y], fill=RULE, width=1)

out = Path(__file__).parent / "upload" / "table-ontology-results.png"
out.parent.mkdir(exist_ok=True)
img.save(out)
print(f"{out.name}: {W}x{H}  ({len(rows)} episodes, runs {runs})")
