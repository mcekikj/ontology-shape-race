"""Render the article's featured image: one claim, three ontologies.

The three panels are not decorative. Each draws the real two-hop neighbourhood
of claim C-31020 as it exists in that ontology, read from the committed graph
files - so the picture a reader sees is the difference the article measures.

Output: figures/upload/cover-dark.png, cover-light.png
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
from graph import Graph  # noqa: E402

OUT = Path(__file__).resolve().parent / "upload"
S = 3                                    # supersampling
W, H = 1400 * S, 787 * S                 # Medium's featured ratio

THEMES = {
    "dark":  dict(bg="#0f1626", panel="#161f33", rule="#26324a",
                  ink="#eef2f8", dim="#8ea0bd", card="#1b2540"),
    "light": dict(bg="#fbfaf7", panel="#ffffff", rule="#c3ccdb",
                  ink="#16202f", dim="#66748c", card="#eef2f8"),
}
ACCENT = {"flat": "#c2703d", "normalized": "#7b6cd9", "shaped": "#17a06b"}


def font(size, bold=False):
    for name in ("HelveticaNeue.ttc", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(f"/System/Library/Fonts/{name}",
                                      size * S, index=1 if bold else 0)
        except OSError:
            continue
    return ImageFont.load_default(size * S)


def neighbourhood(variant, depth=2):
    """The real subgraph around claim C-31020, out to `depth` hops."""
    g = Graph.load(ROOT / "data" / f"ontology-{variant}.json")
    seed = g.find_nodes("C-31020")["nodes"][0]["id"]
    seen, frontier, edges = {seed}, [seed], []
    for _ in range(depth):
        nxt = []
        for node in frontier:
            for n in g.traverse(node)["neighbours"]:
                edges.append((node, n["node_id"], n["edge_type"]))
                if n["node_id"] not in seen:
                    seen.add(n["node_id"])
                    nxt.append(n["node_id"])
        frontier = nxt
    kinds = {n: g.nodes[n]["type"] for n in seen}
    return seed, seen, edges, kinds


def layout(seed, nodes, edges, cx, cy, radius):
    """Concentric rings by hop distance from the seed."""
    dist, queue = {seed: 0}, [seed]
    adj = {}
    for a, b, _ in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    while queue:
        cur = queue.pop(0)
        for nb in adj.get(cur, ()):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                queue.append(nb)
    rings = {}
    for n in nodes:
        rings.setdefault(dist.get(n, 2), []).append(n)
    pos = {}
    for ring, members in rings.items():
        if ring == 0:
            pos[members[0]] = (cx, cy)
            continue
        r = radius * (0.52 if ring == 1 else 1.0)
        members.sort()
        for i, n in enumerate(members):
            a = -math.pi / 2 + 2 * math.pi * i / max(len(members), 1)
            pos[n] = (cx + r * math.cos(a), cy + r * math.sin(a))
    return pos


def draw(theme_name):
    t = THEMES[theme_name]
    img = Image.new("RGB", (W, H), t["bg"])
    d = ImageDraw.Draw(img, "RGBA")

    pad, gap = 54 * S, 26 * S
    top, panel_h = 214 * S, 404 * S
    panel_w = (W - 2 * pad - 2 * gap) // 3

    d.text((pad, 62 * S), "Your Agent Is Not Confused,", font=font(46, True),
           fill=t["ink"])
    d.text((pad, 118 * S), "Your Ontology Is", font=font(46, True),
           fill=ACCENT["shaped"])
    sub = "One claim, three ontologies, one agent - measured on Azure"
    bb = d.textbbox((0, 0), sub, font=font(21))
    d.text((W - pad - (bb[2] - bb[0]), 132 * S), sub, font=font(21),
           fill=t["dim"])

    captions = {
        "flat": ("flat", "everything buried in properties"),
        "normalized": ("normalized", "everything a vertex, nothing named"),
        "shaped": ("shaped", "typed, and one hop away"),
    }

    for i, variant in enumerate(("flat", "normalized", "shaped")):
        x0 = pad + i * (panel_w + gap)
        d.rounded_rectangle([x0, top, x0 + panel_w, top + panel_h],
                            radius=14 * S, fill=t["panel"],
                            outline=t["rule"], width=2 * S)

        seed, nodes, edges, kinds = neighbourhood(variant)
        pos = layout(seed, nodes, edges, x0 + panel_w / 2,
                     top + panel_h / 2 + 8 * S, panel_w * 0.35)
        accent = ACCENT[variant]

        for a, b, _ in edges:
            if a in pos and b in pos:
                d.line([pos[a], pos[b]], fill=t["rule"], width=2 * S)
        for n in nodes:
            if n not in pos:
                continue
            x, y = pos[n]
            is_seed = n == seed
            r = (13 if is_seed else 7) * S
            if kinds.get(n) in ("Attribute", "Relation"):
                r = 5 * S
            fill = accent if is_seed else (
                t["card"] if kinds.get(n) in ("Attribute", "Relation")
                else accent + "aa")
            d.ellipse([x - r, y - r, x + r, y + r], fill=fill,
                      outline=accent if is_seed else t["rule"],
                      width=(3 if is_seed else 1) * S)

        name, note = captions[variant]
        d.text((x0 + 22 * S, top + panel_h - 74 * S), name,
               font=font(25, True), fill=accent)
        d.text((x0 + 22 * S, top + panel_h - 40 * S), note,
               font=font(17), fill=t["dim"])
        d.text((x0 + panel_w - 22 * S -
                d.textlength(f"{len(nodes)} vertices", font=font(17)),
                top + panel_h - 40 * S),
               f"{len(nodes)} vertices", font=font(17), fill=t["dim"])

    y = top + panel_h + 52 * S
    d.line([pad, y, W - pad, y], fill=t["rule"], width=2 * S)
    line = ("g.V().hasLabel('policy').count()  ->  0   0   75")
    d.text((pad, y + 26 * S), line, font=font(27, True), fill=t["ink"])
    tail = "same facts, same database, three schemas"
    bb = d.textbbox((0, 0), tail, font=font(20))
    d.text((W - pad - (bb[2] - bb[0]), y + 31 * S), tail, font=font(20),
           fill=t["dim"])

    out = OUT / f"cover-{theme_name}.png"
    OUT.mkdir(exist_ok=True)
    img.resize((W // S, H // S), Image.LANCZOS).save(out)
    print(f"{out.name}: {W // S}x{H // S}")


if __name__ == "__main__":
    for name in THEMES:
        draw(name)
