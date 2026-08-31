"""Stitch raw portal captures into the article's three screenshot figures.

Take the six captures described in article/screenshot-guide.md, drop them in
figures/raw/, and run this. Each capture is scaled to fit its slot, so they do
not need to be the same size or aspect. Missing files are reported and their
figure is skipped, so the screenshots can be taken in more than one sitting.

Output: figures/upload/screenshot-*.png
"""

from pathlib import Path

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
    if side_by_side:
        col = (W - 2 * pad - 2 * gap) // 3
        h = head + slot_h + pad + (34 if note else 0)
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
        h = head + len(ims) * (slot_h + gap) - gap + pad + (34 if note else 0)
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
    if note:
        d.text((pad, y + 4), note, font=font(18), fill=DIM)
    OUT.mkdir(exist_ok=True)
    img.save(OUT / out_name)
    print(f"{out_name}: {W}x{h}")


def sidebyside(files, title, note, out_name, slot_h=430):
    """Three captures across, each labelled - used for S2."""
    ims = {k: load(v) for k, v in files.items()}
    missing = [v for k, v in files.items() if ims[k] is None]
    if missing:
        print(f"skipped {out_name}: missing {', '.join(missing)}")
        return
    pad, gap, head = 26, 18, 74
    col = (W - 2 * pad - 2 * gap) // 3
    h = head + slot_h + pad + (34 if note else 0)
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    d.text((pad, 24), title, font=font(25, True), fill=INK)
    for i, (name, im) in enumerate(ims.items()):
        x = pad + i * (col + gap)
        box = [x, head, x + col, head + slot_h]
        frame(d, box, name, ACCENT[name])
        art = scaled(im, col - 24, slot_h - 58)
        img.paste(art, (x + (col - art.width) // 2, head + 46))
    if note:
        d.text((pad, head + slot_h + 10), note, font=font(18), fill=DIM)
    OUT.mkdir(exist_ok=True)
    img.save(OUT / out_name)
    print(f"{out_name}: {W}x{h}")


def single(file, title, note, out_name):
    im = load(file)
    if im is None:
        print(f"skipped {out_name}: missing {file}")
        return
    pad, head = 26, 74
    art = scaled(im, W - 2 * pad - 24, 520)
    h = head + art.height + 34 + pad + (34 if note else 0)
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    d.text((pad, 24), title, font=font(25, True), fill=INK)
    box = [pad, head, W - pad, head + art.height + 24]
    d.rounded_rectangle(box, radius=10, fill=PANEL, outline=RULE, width=2)
    img.paste(art, ((W - art.width) // 2, head + 12))
    if note:
        d.text((pad, box[3] + 12), note, font=font(18), fill=DIM)
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
    sidebyside({"flat": "s2-flat.png", "normalized": "s2-normalized.png",
                "shaped": "s2-shaped.png"},
               "Claim C-31020 and its neighbours, as each schema stores it",
               "The same fact at three different distances, drawn by the "
               "Data Explorer's graph view.",
               "screenshot-s2-neighbourhoods.png")
    single("s3-deployments.png",
           "The whole compute footprint: two model deployments",
           "One Microsoft Foundry resource, one small model and one large, "
           "both Global Standard.",
           "screenshot-s3-deployments.png")
