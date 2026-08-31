"""Render the article's featured image: the same facts, three ontologies.

Every panel draws a real subgraph read from the committed graph files - the
neighbourhood of the same three claims, as each schema actually stores them.
Nothing is stylised into existence: flat looks sparse because it is sparse,
normalized looks shattered because every fact is its own vertex, and shaped
looks organised because its vertices carry types and its edges carry names.

Each schema gets its own visual language, matching what it does to the data:

  flat        fat rounded cards with text ruled inside them - the structure
              is present, dissolved into properties
  normalized  many small vertices of one uniform colour - everything
              addressable, nothing distinguishable
  shaped      vertices coloured and sized by type - the domain, visible

Output: figures/upload/cover-dark.png, cover-light.png
"""

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
from graph import Graph  # noqa: E402

OUT = Path(__file__).resolve().parent / "upload"
S = 3
W, H = 1400 * S, 787 * S
SEEDS = ["C-31020", "C-31004", "C-31041"]

THEMES = {
    "dark": dict(bg="#0d1420", panel="#141d2e", rule="#243046",
                 ink="#eef2f8", dim="#8ea0bd", edge=(120, 140, 175),
                 card="#1d2740"),
    "light": dict(bg="#fbfaf7", panel="#ffffff", rule="#dfe5ee",
                  ink="#16202f", dim="#66748c", edge=(150, 163, 186),
                  card="#eaeff7"),
}
ACCENT = {"flat": (203, 116, 61), "normalized": (124, 108, 217),
          "shaped": (23, 160, 107)}
# the shaped panel's palette, one hue per domain type
TYPE_HUES = {
    "claim": (23, 160, 107), "policy": (56, 145, 214),
    "policyholder": (226, 168, 62), "coverage": (129, 191, 106),
    "adjuster": (206, 106, 148), "payment": (100, 196, 190),
    "provider": (232, 132, 92), "region": (150, 160, 190),
}


def font(size, bold=False):
    for name in ("HelveticaNeue.ttc", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(f"/System/Library/Fonts/{name}",
                                      size * S, index=1 if bold else 0)
        except OSError:
            continue
    return ImageFont.load_default(size * S)


SHAPE_TUNING = {                 # depth, node cap, layout spread
    "flat": (2, 70, 2.15),       # few, fat cards - keep them well apart
    "normalized": (2, 96, 0.82), # many small vertices - let them cluster
    "shaped": (2, 70, 0.95),
}


def subgraph(variant, depth=2, cap=70):
    """The induced subgraph around the seed claims, as this schema stores it."""
    g = Graph.load(ROOT / "data" / f"ontology-{variant}.json")
    seen, frontier = set(), []
    for number in SEEDS:
        hits = g.find_nodes(number)["nodes"]
        if hits:
            seen.add(hits[0]["id"])
            frontier.append(hits[0]["id"])
    roots = set(frontier)
    for _ in range(depth):
        nxt = []
        for node in frontier:
            for n in g.traverse(node)["neighbours"]:
                if n["node_id"] not in seen and len(seen) < cap:
                    seen.add(n["node_id"])
                    nxt.append(n["node_id"])
        frontier = nxt
    edges = [(a, b) for a in seen for n in g.traverse(a)["neighbours"]
             if (b := n["node_id"]) in seen and a < b]
    kinds = {n: g.nodes[n]["type"] for n in seen}
    return roots, sorted(seen), sorted(set(edges)), kinds


def spring(nodes, edges, w, h, seed=7, rounds=420, spread=1.0):
    """A small force-directed layout - organic, and stable for a fixed seed."""
    rng = random.Random(seed)
    pos = {n: [rng.uniform(0.25, 0.75) * w, rng.uniform(0.25, 0.75) * h]
           for n in nodes}
    if not nodes:
        return pos
    k = math.sqrt(w * h / max(len(nodes), 1)) * 0.62 * spread
    adj = {n: set() for n in nodes}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    for step in range(rounds):
        temp = (1 - step / rounds) ** 1.5 * k * 0.14
        disp = {n: [0.0, 0.0] for n in nodes}
        for i, a in enumerate(nodes):           # repulsion
            for b in nodes[i + 1:]:
                dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                d2 = dx * dx + dy * dy or 0.01
                f = k * k / d2
                disp[a][0] += dx * f
                disp[a][1] += dy * f
                disp[b][0] -= dx * f
                disp[b][1] -= dy * f
        for a, b in edges:                      # attraction
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) or 0.01
            f = d / k
            disp[a][0] -= dx / d * f * k * 0.5
            disp[a][1] -= dy / d * f * k * 0.5
            disp[b][0] += dx / d * f * k * 0.5
            disp[b][1] += dy / d * f * k * 0.5
        for n in nodes:                         # gentle pull to centre
            disp[n][0] += (w / 2 - pos[n][0]) * 0.012
            disp[n][1] += (h / 2 - pos[n][1]) * 0.012
            dx, dy = disp[n]
            d = math.hypot(dx, dy) or 0.01
            pos[n][0] += dx / d * min(d, temp)
            pos[n][1] += dy / d * min(d, temp)
    return pos


def components(nodes, edges):
    """Connected components, largest first."""
    adj = {n: set() for n in nodes}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, out = set(), []
    for n in nodes:
        if n in seen:
            continue
        comp, queue = set(), [n]
        seen.add(n)
        while queue:
            cur = queue.pop()
            comp.add(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        out.append(sorted(comp))
    return sorted(out, key=len, reverse=True)


def pack(nodes, edges, w, h, spread):
    """Lay out each connected component on its own, then distribute the
    components across the panel. Without this the springs let disconnected
    pieces drift together, which reads as a rendering fault rather than as
    the sparse graph it actually is."""
    comps = components(nodes, edges)
    # Each component gets floor area in proportion to its size, shelf-packed.
    # A fixed grid would squeeze one dominant component into a quarter of the
    # panel while three tiny ones took the rest.
    weights = [math.sqrt(len(c)) for c in comps]
    total = sum(weights)
    shelves, shelf, used = [], [], 0.0
    for comp, weight in zip(comps, weights):
        share = weight / total
        if used + share > 0.62 and shelf:
            shelves.append(shelf)
            shelf, used = [], 0.0
        shelf.append((comp, share))
        used += share
    if shelf:
        shelves.append(shelf)

    pos, y0 = {}, 0.0
    for shelf in shelves:
        band = sum(share for _, share in shelf)
        row_h = h * (band / (sum(sh for s_ in shelves for _, sh in s_)))
        x0 = 0.0
        for i, (comp, share) in enumerate(shelf):
            cell_w = w * share / band
            sub = [(a, b) for a, b in edges if a in comp and b in comp]
            local = spring(comp, sub, cell_w, row_h, seed=7 + i, spread=spread)
            local = fit(local, cell_w, row_h,
                        margin=min(cell_w, row_h) * 0.16)
            for n, (x, y) in local.items():
                pos[n] = (x0 + x, y0 + y)
            x0 += cell_w
        y0 += row_h
    return pos


def fit(pos, w, h, margin):
    if not pos:
        return pos
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    sx = (w - 2 * margin) / max(max(xs) - min(xs), 1)
    sy = (h - 2 * margin) / max(max(ys) - min(ys), 1)
    s = min(sx, sy)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return {n: (w / 2 + (p[0] - cx) * s, h / 2 + (p[1] - cy) * s)
            for n, p in pos.items()}


def panel(variant, size, theme):
    """Draw one schema's subgraph onto its own transparent layer."""
    w, h = size
    depth, cap, spread = SHAPE_TUNING[variant]
    roots, nodes, edges, kinds = subgraph(variant, depth, cap)
    pos = pack(nodes, edges, w, h, spread)

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    accent = ACCENT[variant]

    for a, b in edges:                                   # edges first
        d.line([pos[a], pos[b]], fill=theme["edge"] + (110,), width=2 * S)

    deg = {n: 0 for n in nodes}
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1

    for n in nodes:
        x, y = pos[n]
        kind = kinds[n]

        if variant == "flat":
            # a fat card with ruled lines: the structure, dissolved into text
            bw = (66 if n in roots else 54) * S
            bh = (46 if n in roots else 39) * S
            box = [x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2]
            gd.rounded_rectangle(box, radius=9 * S, fill=accent + (70,))
            d.rounded_rectangle(box, radius=9 * S, fill=theme["card"],
                                outline=accent + (255,), width=2 * S)
            for i in range(4):
                ly = box[1] + (10 + i * 8) * S
                lw = bw * (0.68 if i % 2 else 0.5)
                d.line([x - lw / 2, ly, x + lw / 2, ly],
                       fill=accent + (120 if i else 190,), width=2 * S)
            continue

        if variant == "normalized":
            # uniform, undifferentiated - everything is a vertex, nothing named
            r = (9 if n in roots else 6) * S
            col = accent if kind == "Resource" else (
                tuple(int(c * 0.55 + 90) for c in accent))
            gd.ellipse([x - r * 2.4, y - r * 2.4, x + r * 2.4, y + r * 2.4],
                       fill=col + (46,))
            d.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,))
            continue

        # shaped: coloured and sized by domain type
        col = TYPE_HUES.get(kind, accent)
        r = (7 + min(deg[n], 6) * 1.5) * S
        if n in roots:
            r = 15 * S
        gd.ellipse([x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2],
                   fill=col + (58,))
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,),
                  outline=(255, 255, 255, 70), width=1 * S)

    glow = glow.filter(ImageFilter.GaussianBlur(11 * S))
    out = Image.alpha_composite(glow, layer)
    return out, len(nodes)


def draw(theme_name):
    t = THEMES[theme_name]
    img = Image.new("RGB", (W, H), t["bg"])
    d = ImageDraw.Draw(img)

    pad, gap = 54 * S, 26 * S
    top, panel_h = 208 * S, 486 * S
    panel_w = (W - 2 * pad - 2 * gap) // 3

    d.text((pad, 74 * S), "Your Agent Is Not Confused,",
           font=font(48, True), fill=t["ink"])
    d.text((pad, 132 * S), "Your Ontology Is", font=font(48, True),
           fill="#17a06b")

    captions = {
        "flat": ("flat", "buried in properties"),
        "normalized": ("normalized", "everything a vertex, nothing named"),
        "shaped": ("shaped", "typed, named, one hop away"),
    }

    for i, variant in enumerate(("flat", "normalized", "shaped")):
        x0 = pad + i * (panel_w + gap)
        d.rounded_rectangle([x0, top, x0 + panel_w, top + panel_h],
                            radius=16 * S, fill=t["panel"],
                            outline=t["rule"], width=2 * S)

        art, _ = panel(variant, (panel_w, panel_h - 86 * S), t)
        img.paste(art, (x0, top), art)

        name, note = captions[variant]
        d.text((x0 + 26 * S, top + panel_h - 68 * S), name,
               font=font(27, True), fill="#%02x%02x%02x" % ACCENT[variant])
        d.text((x0 + 26 * S, top + panel_h - 34 * S), note,
               font=font(18), fill=t["dim"])

    OUT.mkdir(exist_ok=True)
    out = OUT / f"cover-{theme_name}.png"
    img.resize((W // S, H // S), Image.LANCZOS).save(out)
    print(f"{out.name}: {W // S}x{H // S}")


if __name__ == "__main__":
    for name in THEMES:
        draw(name)
