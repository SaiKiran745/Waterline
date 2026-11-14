"""Spot-check table for a surveyed building (BUILD_PROMPTS Phase 3A step 8).

    python -m app.survey.spotcheck building-h [--n 10] [--sheet out.jpg]

Prints 10 assets spread across the confidence range, with label, height range, how the height was obtained,
confidence and image reference. Optional --sheet draws each asset's box on its source face for human review
(the sheet is a local file, never committed or served).
"""
import argparse
import json
import re

from PIL import Image, ImageDraw

from app.config import BUILDINGS, MEDIA


def pick(assets: list[dict], n: int) -> list[dict]:
    s = sorted(assets, key=lambda a: a["confidence"])
    if len(s) <= n:
        return s
    return [s[round(i * (len(s) - 1) / (n - 1))] for i in range(n)]


def main(bid: str, n: int, sheet: str | None) -> None:
    assets = json.loads((BUILDINGS / bid / "assets.json").read_text())
    rows = pick(assets, n)
    print(f"| # | Room | Asset | Category | Lowest vulnerable part (ft) | How | Confidence | Looks | Image |")
    print("|---|---|---|---|---|---|---|---|---|")
    for i, a in enumerate(rows, 1):
        how = "mesh" if "measured from mesh" in a["evidence"] else "estimate"
        print(f"| {i} | {a['room']} | {a['label']} | {a['category']} | {a['height_ft_low']:.2f}-{a['height_ft_high']:.2f} | {how} "
              f"| {a['confidence']:.2f} | {len(a['observations'])} | `{a['image_ref'].split('/panos/')[1]}` |")
    if sheet:
        T = 360
        out = Image.new("RGB", (5 * T, ((len(rows) + 4) // 5) * (T + 40)), "white")
        for i, a in enumerate(rows):
            m = re.match(r"/media/[^/]+/panos/([^/]+)/face(\d)\.jpg#box=(\d+),(\d+),(\d+),(\d+)", a["image_ref"])
            pano, face, y0, x0, y1, x1 = m.group(1), int(m.group(2)), *map(int, m.groups()[2:])
            im = Image.open(MEDIA / bid / "panos" / pano / f"face{face}.jpg").convert("RGB").resize((T, T))
            d = ImageDraw.Draw(im)
            d.rectangle([x0 * T / 1000, y0 * T / 1000, x1 * T / 1000, y1 * T / 1000], outline=(255, 0, 0), width=3)
            c = out
            c.paste(im, ((i % 5) * T, (i // 5) * (T + 40)))
            ImageDraw.Draw(c).text(((i % 5) * T + 4, (i // 5) * (T + 40) + T + 4),
                                   f"{i + 1}. {a['label'][:40]}\n{a['height_ft_low']:.1f}-{a['height_ft_high']:.1f} ft  conf {a['confidence']:.2f}",
                                   fill=(0, 0, 0))
        out.save(sheet, quality=85)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("building")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--sheet")
    a = ap.parse_args()
    main(a.building, a.n, a.sheet)
