"""build_strip.py -- the lineup card: every door's capture side by side, one image (Build 2.5, the game notes' picture).

Source:        the per-door PNGs — out/keeping-score-hr-by-year-<door>.png here, plus the anchor's PNG in the W5 repo.
Analysis:      this script (Pillow). Missing doors are skipped and named; rerun as screenshots land.
Presentation:  out/keeping-score-hr-by-year-strip.png — copy to the site's assets/ when all six are in.

    py viz/build_strip.py
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
ANCHOR = HERE.parent.parent / "wax_baseball_w5_datasource" / "workbooks" / "keeping-score-hr-by-year.png"
DOORS = [  # inning order
    ("Tableau Cloud", ANCHOR),
    ("Looker Studio", OUT / "keeping-score-hr-by-year-looker-studio.png"),
    ("Tableau Next", OUT / "keeping-score-hr-by-year-tn.png"),
    ("Streamlit in Snowflake", OUT / "keeping-score-hr-by-year-streamlit.png"),
    ("Databricks AI/BI", OUT / "keeping-score-hr-by-year-databricks.png"),
    ("Claude artifact", OUT / "keeping-score-hr-by-year-artifact.png"),
]
TILE_W, PAD, LABEL_H = 600, 24, 40
PAPER, INK, MUTED = "#FAFAF7", "#1A1A1A", "#6B6B6B"


def main() -> None:
    have = [(name, p) for name, p in DOORS if p.exists()]
    missing = [name for name, p in DOORS if not p.exists()]
    if not have:
        raise SystemExit("no captures yet")
    try:
        font = ImageFont.truetype("consola.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    tiles = []
    for name, p in have:
        im = Image.open(p).convert("RGB")
        im = im.resize((TILE_W, round(im.height * TILE_W / im.width)))
        tiles.append((name, im))
    tile_h = max(im.height for _, im in tiles)
    cols = min(3, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    W = PAD + cols * (TILE_W + PAD)
    H = PAD + rows * (tile_h + LABEL_H + PAD)
    strip = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(strip)
    for i, (name, im) in enumerate(tiles):
        x = PAD + (i % cols) * (TILE_W + PAD)
        y = PAD + (i // cols) * (tile_h + LABEL_H + PAD)
        d.text((x, y), name.upper(), fill=MUTED, font=font)
        strip.paste(im, (x, y + LABEL_H))
        d.rectangle([x, y + LABEL_H, x + TILE_W - 1, y + LABEL_H + im.height - 1], outline="#E4E1D8")
    out = OUT / "keeping-score-hr-by-year-strip.png"
    strip.save(out)
    print(f"  strip: {len(tiles)} of {len(DOORS)} doors -> {out.name} ({strip.width}x{strip.height})")
    if missing:
        print(f"  missing: {', '.join(missing)}")


if __name__ == "__main__":
    main()
