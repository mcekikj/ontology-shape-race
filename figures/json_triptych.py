"""Render the article's Figure 2: the same policy, as raw data, in each shape.

The excerpts are extracted at render time from the committed ontology files -
the same files load_cosmos.py loads into Cosmos, so what is drawn is what the
agent traversed - and they show the entity the article's trace block features:
policy P-7009 (PL-009), the one the flat graph buried inside policyholder
PH-05's blob.

Output: figures/upload/json-triptych.png
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DATA = Path(__file__).resolve().parent.parent / "data"


def excerpt_flat() -> str:
    g = json.loads((DATA / "ontology-flat.json").read_text(encoding="utf-8"))
    node = g["nodes"]["policyholder:PH-05"]
    pols = json.loads(node["props"]["policies"])
    pol = next(p for p in pols if p["number"] == "P-7009")
    shown = {k: pol[k] for k in ("id", "number", "product", "premium")}
    shown["coverages"] = f"[... {len(pol['coverages'])} embedded ...]"
    lines = ['"policyholder:PH-05": {',
             '  "type": "policyholder",',
             '  "props": {',
             f'    "name": "{node["props"]["name"]}",',
             f'    "city": "{node["props"]["city"]}",',
             '    "policies": "[ ...JSON string...']
    for k, v in shown.items():
        rendered = json.dumps(v) if not isinstance(v, str) or k != "coverages" \
            else v
        lines.append(f'      {k}: {rendered}')
    lines += ['    ...]"', '  }', '}', '',
              'edges: only  policyholder --related--> claim',
              '(a policy is not a node; it cannot be',
              ' found, only stumbled upon)']
    return "\n".join(lines)


def excerpt_shaped() -> str:
    g = json.loads((DATA / "ontology-shaped.json").read_text(encoding="utf-8"))
    node = g["nodes"]["policy:PL-009"]
    lines = ['"policy:PL-009": {',
             '  "type": "policy",',
             '  "props": {']
    for k, v in node["props"].items():
        lines.append(f'    "{k}": {json.dumps(v)},')
    lines[-1] = lines[-1].rstrip(",")
    lines += ['  }', '}', '']
    for e in g["edges"]:
        if e["src"] == "policy:PL-009" or e["dst"] == "policy:PL-009":
            derived = "  (derived)" if e["props"].get("derived") else ""
            lines.append(f'{e["src"]} --{e["type"]}--> {e["dst"]}{derived}')
            if len(lines) > 14:
                break
    lines.append("...")
    return "\n".join(lines)


def excerpt_normalized() -> str:
    g = json.loads((DATA / "ontology-normalized.json")
                   .read_text(encoding="utf-8"))
    lines = ['"policy:PL-009": {', '   "type": "Resource",',
             '   "props": {"entity_type": "policy"}}', '']
    for attr in ("number", "premium"):
        aid = f"policy:PL-009#{attr}"
        props = g["nodes"][aid]["props"]
        lines.append(f'"{aid}": {{')
        lines.append('   "type": "Attribute",')
        lines.append(f'   "props": {{"attr": "{props["attr"]}",')
        lines.append(f'             "value": {json.dumps(props["value"])}}}}}')
    rel = "rel:policy:PL-009:held_by:policyholder:PH-05"
    lines += ['', f'"{rel}":',
              '   {"type": "Relation",',
              '    "props": {"kind": "held_by"}}',
              '', 'edges: has / subject / object only',
              '(the premium is two hops from the policy,',
              ' which is itself two hops from anything)']
    return "\n".join(lines)


PANELS = [
    ("flat - buried in a blob", excerpt_flat(), "#8a5a2c"),
    ("normalized - exploded into vertices", excerpt_normalized(), "#6a5acd"),
    ("shaped - typed and addressable", excerpt_shaped(), "#0e6b3d"),
]

W, PANEL_PAD, MARGIN = 1400, 18, 20
COL_W = (W - 2 * MARGIN - 2 * PANEL_PAD) // 3
FONT = "/System/Library/Fonts/Menlo.ttc"
title_f = ImageFont.truetype(FONT, 21, index=1)
body_f = ImageFont.truetype(FONT, 15)
LINE_H = 22

max_lines = max(len(p[1].splitlines()) for p in PANELS)
H = 90 + max_lines * LINE_H + 40

img = Image.new("RGB", (W, H), "#fdfbf7")
d = ImageDraw.Draw(img)
d.text((MARGIN, 18), "The same policy - P-7009, premium 750 - in all three shapes",
       font=ImageFont.truetype(FONT, 24, index=1), fill="#1a1a1a")

for i, (title, text, colour) in enumerate(PANELS):
    x = MARGIN + i * (COL_W + PANEL_PAD)
    d.rounded_rectangle([x, 62, x + COL_W, H - 16], radius=10,
                        fill="white", outline="#d9dde2", width=2)
    d.text((x + 14, 74), title, font=title_f, fill=colour)
    y = 74 + 34
    for line in text.splitlines():
        d.text((x + 14, y), line[:56], font=body_f, fill="#2a2a2a")
        y += LINE_H

out = Path(__file__).parent / "upload" / "json-triptych.png"
out.parent.mkdir(exist_ok=True)
img.save(out)
print(f"{out.name}: {W}x{H}")
