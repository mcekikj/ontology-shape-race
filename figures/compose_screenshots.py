"""Stitch raw portal captures into the article's three screenshot figures.

Take the six captures described in article/screenshot-guide.md, drop them in
figures/raw/, and run this. Each capture is scaled to fit its slot, so they do
not need to be the same size or aspect. Missing files are reported and their
figure is skipped, so the screenshots can be taken in more than one sitting.

Output: figures/upload/screenshot-*.png
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
RAW, OUT = HERE / "raw", HERE / "upload"
W = 1400
BG, PANEL, RULE, INK, DIM = "#fbfaf7", "#ffffff", "#dfe5ee", "#16202f", "#66748c"
ACCENT = {"flat": "#c2703d", "normalized": "#7b6cd9", "shaped": "#17a06b"}


def font(size, bold=False):
    for name in ("HelveticaNeue.ttc", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(f"/System/Library/Fonts/{name}", size,
                                      index=1 if bold else 0)
        except OSError:
            continue
    return ImageFont.load_default(size)


def wrap(note, width, size=18):
    """Break a note into lines that fit `width`, measured in the real font."""
    if not note:
        return []
    f, lines, line = font(size), [], ""
    for word in note.split():
        trial = f"{line} {word}".strip()
        if f.getlength(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def draw_note(d, lines, x, y, size=18):
    for i, line in enumerate(lines):
        d.text((x, y + i * (size + 8)), line, font=font(size), fill=DIM)


def load(name):
    path = RAW / name
    if not path.exists():
        return None
    im = Image.open(path).convert("RGB")
    return im


def scaled(im, box_w, box_h):
    r = min(box_w / im.width, box_h / im.height)
    return im.resize((max(int(im.width * r), 1), max(int(im.height * r), 1)),
                     Image.LANCZOS)


def frame(d, box, label, colour):
    d.rounded_rectangle(box, radius=10, fill=PANEL, outline=RULE, width=2)
    if label:
        d.text((box[0] + 16, box[1] + 12), label, font=font(21, True),
               fill=colour)


def stacked(files, title, note, out_name, slot_h=190,
            side_by_side=False):
    """Three captures stacked vertically, each labelled - used for S1."""
    ims = {k: load(v) for k, v in files.items()}
    missing = [v for k, v in files.items() if ims[k] is None]
    if missing:
        print(f"skipped {out_name}: missing {', '.join(missing)}")
        return
    pad, gap, head = 26, 18, 74
    lines = wrap(note, W - 2 * pad)
    note_h = 26 * len(lines) + 8 if lines else 0
    if side_by_side:
        col = (W - 2 * pad - 2 * gap) // 3
        h = head + slot_h + pad + note_h
        img = Image.new("RGB", (W, h), BG)
        d = ImageDraw.Draw(img)
        d.text((pad, 24), title, font=font(25, True), fill=INK)
        for i, (name, im) in enumerate(ims.items()):
            x = pad + i * (col + gap)
            box = [x, head, x + col, head + slot_h]
            frame(d, box, name, ACCENT[name])
            art = scaled(im, col - 26, slot_h - 62)
            img.paste(art, (x + (col - art.width) // 2, head + 48))
        y = head + slot_h
    else:
        h = head + len(ims) * (slot_h + gap) - gap + pad + note_h
        img = Image.new("RGB", (W, h), BG)
        d = ImageDraw.Draw(img)
        d.text((pad, 24), title, font=font(25, True), fill=INK)
        y = head
        for name, im in ims.items():
            box = [pad, y, W - pad, y + slot_h]
            frame(d, box, name, ACCENT[name])
            art = scaled(im, W - 2 * pad - 190, slot_h - 24)
            img.paste(art, (pad + 176, y + (slot_h - art.height) // 2))
            y += slot_h + gap
    draw_note(d, lines, pad, y + 6)
    OUT.mkdir(exist_ok=True)
    img.save(OUT / out_name)
    print(f"{out_name}: {W}x{h}")


def rules(gray):
    """x of the Data Explorer's vertical pane dividers, found not assumed.

    The portal draws each pane boundary as a full-height 1px rule, so a
    column that is dark down the whole of a mid-height band is a divider.
    Reading them off the capture means the crop survives a different window
    width or a collapsed tree - no pixel offsets are baked in here.
    """
    h = gray.shape[0]
    band = gray[h // 2 - 120:h // 2 + 120]
    dark = (band < 240).sum(axis=0)
    xs, out = np.where(dark > band.shape[0] * 0.8)[0], []
    for x in xs:
        if not out or x - out[-1] > 4:
            out.append(int(x))
    return out


def results_band(gray, x):
    """(top, bottom) of the results area, from the pane divider at column x.

    A divider is drawn only where the results area is, so the longest
    unbroken dark run down that column is exactly the pane's vertical
    extent. That keeps the query bar, the tab strip and the query-history
    dropdown out of the crop without knowing where any of them sit.
    """
    dark = gray[:, x] < 240
    best, run, start = (0, 0), 0, 0
    for i, on in enumerate(dark):
        if on:
            start = i if run == 0 else start
            run += 1
            best = (start, run) if run > best[1] else best
        else:
            run = 0
    return best[0], best[0] + best[1]


def ink_rows(gray, x0, x1, top, bot, pad=12, floor=2):
    """The rows inside top:bot that carry ink, across columns x0:x1.

    `floor` is how many dark pixels make a row count as inked. Raise it
    above the number of vertical borders crossing the region, or an empty
    table below the last row reads as content and survives the crop.
    """
    rows = np.where((gray[top:bot, x0:x1] < 242).sum(axis=1) > floor)[0]
    if not len(rows):
        return top, bot
    return max(top + int(rows[0]) - pad, 0), min(top + int(rows[-1]) + pad,
                                                 bot)


def panes(files, title, note, out_name, captions):
    """One row per schema: the graph pane beside its properties panel.

    Used for S2. Each capture is cut at its own detected dividers, so the
    drawing pane and the panel keep a constant width across the three rows
    and therefore a constant scale - the rows are comparable by eye, which
    is the entire point of the figure. Only the vertical extent varies, and
    it varies because the schemas genuinely differ in size.
    """
    ims = {k: load(v) for k, v in files.items()}
    missing = [v for k, v in files.items() if ims[k] is None]
    if missing:
        print(f"skipped {out_name}: missing {', '.join(missing)}")
        return

    rows = {}
    for name, im in ims.items():
        gray = np.asarray(im.convert("L"), dtype=int)
        graph_x0, panel_x0 = rules(gray)[-2:]
        band = results_band(gray, graph_x0)
        # one y-range for both panes, so they keep the alignment they had
        top, bot = ink_rows(gray, graph_x0, im.width, *band)
        rows[name] = (im.crop((graph_x0, top, panel_x0, bot)),
                      im.crop((panel_x0, top, im.width, bot)))

    src_w = max(g.width + p.width for g, p in rows.values())
    pad, gap, head, hdr = 26, 20, 74, 52
    lines = wrap(note, W - 2 * pad)
    note_h = 26 * len(lines) if lines else 0
    art_w = W - 2 * pad - 24
    scale = art_w / src_w

    heights = {}
    for name, (g, p) in rows.items():
        heights[name] = int(max(g.height, p.height) * scale)
    stack = sum(hdr + heights[n] + 20 for n in rows) + gap * (len(rows) - 1)
    note_y = head + stack + 16
    h = note_y + note_h + pad

    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    d.text((pad, 24), title, font=font(25, True), fill=INK)

    y = head
    for name, (g, p) in rows.items():
        box_h = hdr + heights[name] + 20
        d.rounded_rectangle([pad, y, W - pad, y + box_h], radius=10,
                            fill=PANEL, outline=RULE, width=2)
        d.text((pad + 16, y + 13), name, font=font(20, True),
               fill=ACCENT[name])
        d.text((pad + 130, y + 15), captions[name], font=font(16), fill=DIM)
        x = pad + 12
        for part in (g, p):
            art = part.resize((max(int(part.width * scale), 1),
                               max(int(part.height * scale), 1)),
                              Image.LANCZOS)
            img.paste(art, (x, y + hdr))
            x += art.width
        y += box_h + gap

    draw_note(d, lines, pad, note_y)
    OUT.mkdir(exist_ok=True)
    img.save(OUT / out_name)
    print(f"{out_name}: {W}x{h}")


def single(file, title, note, out_name, trim=False):
    im = load(file)
    if im is None:
        print(f"skipped {out_name}: missing {file}")
        return
    if trim:
        # Drop the dead space under the last table row. The navigation rail
        # stays: it shows the reader where in the portal this page lives.
        # The floor clears the table container's own vertical borders, which
        # otherwise make every empty row below the data look inked.
        gray = np.asarray(im.convert("L"), dtype=int)
        rail = rules(gray)[0]
        # Measure the last inked row in the content pane only - the rail's
        # own menu runs the full height and would defeat the trim. The floor
        # clears the table container's two vertical borders.
        _, bot = ink_rows(gray, rail + 24, im.width, 0, im.height, pad=18,
                          floor=10)
        # Then slide down to the next gap in the rail, so the cut falls
        # between two menu entries instead of through one.
        while bot < im.height and (gray[bot, :rail] < 242).sum() > 2:
            bot += 1
        im = im.crop((0, 0, im.width, min(bot + 6, im.height)))
    pad, head = 26, 74
    lines = wrap(note, W - 2 * pad)
    note_h = 26 * len(lines) + 8 if lines else 0
    art = scaled(im, W - 2 * pad - 24, 520)
    h = head + art.height + 34 + pad + note_h
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    d.text((pad, 24), title, font=font(25, True), fill=INK)
    box = [pad, head, W - pad, head + art.height + 24]
    d.rounded_rectangle(box, radius=10, fill=PANEL, outline=RULE, width=2)
    img.paste(art, ((W - art.width) // 2, head + 12))
    draw_note(d, lines, pad, box[3] + 12)
    OUT.mkdir(exist_ok=True)
    img.save(OUT / out_name)
    print(f"{out_name}: {W}x{h}")


if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    stacked({"flat": "s1-flat.png", "normalized": "s1-normalized.png",
             "shaped": "s1-shaped.png"},
            "g.V().groupCount().by(label) - the same query, three schemas",
            "Two labels, three meta-labels, or the domain in its own words - "
            "captured in the Cosmos DB Data Explorer.",
            "screenshot-s1-vocabularies.png", slot_h=430, side_by_side=True)
    panes({"flat": "s2-flat.png", "normalized": "s2-normalized.png",
           "shaped": "s2-shaped.png"},
          "Claim C-31020 and its neighbours, as each schema stores it",
          "Same claim, same database, three distances. Read the flat "
          "properties panel: the adjuster and the policy are in there as "
          "text, which is why the agent cannot walk to them.",
          "screenshot-s2-neighbourhoods.png",
          {"flat": "g.V().has('number', 'C-31020')   ->   1 neighbour, on "
                   "one nameless related edge",
           "normalized": "g.V().has('value', 'C-31020').in('has')   ->   8 "
                         "neighbours: 6 attributes, 2 relations",
           "shaped": "g.V().has('number', 'C-31020')   ->   3 neighbours, on "
                     "named edges: filed_against, assessed_by, held_by"})
    single("s3-deployments.png",
           "The whole compute footprint: two model deployments",
           "One Microsoft Foundry resource, one small model and one large, "
           "both Global Standard, both declared in code/infra.bicep.",
           "screenshot-s3-deployments.png", trim=True)
