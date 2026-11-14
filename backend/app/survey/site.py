"""Site scout: where flood water gets in, from the Vexcel aerial images (AGENTS.md section 10, site-scout).

    python -m app.survey.site building-e [--cache-only]

One Gemini call per building sees all five views at once (ortho + four obliques), so it can de-duplicate a door
that shows in two views. For each ground-level opening on the main building it returns the view where it is
clearest, a box in that view, and where it sits on the ortho (which is georeferenced, so every opening gets a map
position). Openings are ranked by how easily water enters: grade-level drive-in doors and personnel doors first,
then ramps, then dock-high doors. The counts are cross-checked against CoStar's drive-in and dock counts.
Ground elevation stays context only (human decision D6), so threshold_elevation_ft is null.
Writes data/cache/buildings/<id>/entry_points.json and site_log.json.
"""
import argparse
import io
import json
import re
from datetime import datetime, timezone

from PIL import Image

from app.buildings import get_building, validate
from app.config import BUILDINGS, MEDIA
from app.sources import gemini
from app.sources.cache import write_json

VIEWS = ("ortho", "oblique-north", "oblique-south", "oblique-east", "oblique-west")
UPLOAD_PX = 1536
KIND_ORDER = {"drive_in": 0, "door": 1, "garage": 2, "ramp": 3, "other": 4, "dock": 5}
WHY = {"drive_in": "grade-level drive-in door: wide and at ground level, so water walks straight in",
       "door": "personnel door at grade: the threshold is the only barrier",
       "garage": "grade-level garage door",
       "ramp": "ramp sloping toward the building: channels water to the opening",
       "other": "other opening near grade",
       "dock": "dock-high door: the floor sits about 4 ft above the truck apron, so water must rise first"}

PROMPT = """You are a flood engineer scouting a commercial building in Houston from aerial imagery.
The images are five views of the same site: "ortho" (straight down, north is up) and four obliques named by
their direction. The main building is the large building in the centre of the ortho; ignore neighbouring buildings.

List every ground-level opening on the main building where flood water could get in: personnel doors at grade,
grade-level drive-in (roll-up) doors, dock-high loading doors (raised floor, truck apron below), ramps sloping
toward a door, garage doors. Count each physical opening ONCE even if it shows in several views.
For each opening give:
- kind: drive_in, door, dock, ramp, garage or other
- view: the view where it is clearest (one of: ortho, oblique-north, oblique-south, oblique-east, oblique-west)
- box_2d: [ymin, xmin, ymax, xmax] in that view, normalised 0-1000
- ortho_point: [y, x] of where the opening is on the ortho (the building edge), normalised 0-1000
- side: which side of the building it is on (north, south, east or west)
- confidence: 0 to 1
- evidence: one sentence on what in the image shows this (for example "roll-up door at pavement level, no dock plate")
Also report drive_in_count and dock_count for the main building, and say if any view does not show the building."""

SCHEMA = {"type": "OBJECT", "properties": {
    "openings": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "kind": {"type": "STRING", "enum": ["drive_in", "door", "dock", "ramp", "garage", "other"]},
        "view": {"type": "STRING", "enum": list(VIEWS)},
        "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "ortho_point": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "side": {"type": "STRING", "enum": ["north", "south", "east", "west"]},
        "confidence": {"type": "NUMBER"}, "evidence": {"type": "STRING"}},
        "required": ["kind", "view", "box_2d", "ortho_point", "side", "confidence", "evidence"]}},
    "drive_in_count": {"type": "INTEGER"}, "dock_count": {"type": "INTEGER"},
    "views_without_building": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["openings", "drive_in_count", "dock_count", "views_without_building"]}


def _jpeg(path) -> tuple[bytes, tuple[int, int]]:
    im = Image.open(path).convert("RGB")
    size = im.size
    im.thumbnail((UPLOAD_PX, UPLOAD_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue(), size


def _ortho_lnglat(bid: str, y: float, x: float) -> tuple[float | None, float | None]:
    """Ortho pixel (normalised 0-1000) to lat/lng by linear interpolation in its WGS84 bounding box."""
    meta = json.loads((MEDIA / bid / "aerial" / "ortho.meta.json").read_text())
    nums = [float(v) for v in re.findall(r"-?\d+\.\d+", (meta.get("xmp") or {}).get("geometry", ""))]
    if len(nums) < 8:
        return None, None
    lngs, lats = nums[0::2], nums[1::2]
    lng = min(lngs) + (max(lngs) - min(lngs)) * x / 1000
    lat = max(lats) - (max(lats) - min(lats)) * y / 1000
    return round(lat, 7), round(lng, 7)


def scout(bid: str, cache_only: bool = False) -> tuple[list[dict], dict]:
    b = get_building(bid)
    views = [v for v in VIEWS if (MEDIA / bid / "aerial" / f"{v}.jpg").exists()]   # Vexcel may lack a direction
    parts, sizes = [PROMPT.replace("five views", f"{len(views)} views")], {}
    for v in views:
        data, sizes[v] = _jpeg(MEDIA / bid / "aerial" / f"{v}.jpg")
        parts += [f"View {v}:", data]
    res = gemini.generate_json(parts, SCHEMA, tag=f"{bid}/site", cache_only=cache_only)
    r = res["data"]
    rows = []
    for o in r.get("openings", []):
        box, pt = o.get("box_2d") or [], o.get("ortho_point") or []
        if o.get("view") not in sizes or len(box) != 4:
            continue
        w, h = sizes[o["view"]]
        lat, lng = _ortho_lnglat(bid, *pt) if len(pt) == 2 else (None, None)
        rows.append({"kind": o["kind"], "view": o["view"], "side": o.get("side"), "lat": lat, "lng": lng,
                     "image_xy": [round((box[1] + box[3]) / 2 * w / 1000), round((box[0] + box[2]) / 2 * h / 1000)],
                     "confidence": float(o.get("confidence") or 0), "evidence": (o.get("evidence") or "").strip()})
    rows.sort(key=lambda o: (KIND_ORDER.get(o["kind"], 9), -o["confidence"]))
    found = {"drive_in": sum(1 for o in rows if o["kind"] == "drive_in"),
             "dock": sum(1 for o in rows if o["kind"] == "dock")}
    costar = {"drive_in": b.get("drive_in_bays"), "dock": b.get("loading_docks_external")}
    check = {}
    for k in ("drive_in", "dock"):
        if costar[k] is None:
            check[k] = f"CoStar has no {k.replace('_', '-')} count; images show {found[k]}"
        elif costar[k] == found[k]:
            check[k] = f"matches CoStar ({costar[k]})"
        else:
            check[k] = f"images show {found[k]}, CoStar says {costar[k]}"
    eps = []
    for n, o in enumerate(rows, 1):
        note = check.get(o["kind"])
        ep = {"id": f"{bid}-ep{n}", "building_id": bid, "kind": o["kind"], "lat": o["lat"], "lng": o["lng"],
              "image_ref": f"/media/{bid}/aerial/{o['view']}.jpg", "image_kind": o["view"], "image_xy": o["image_xy"],
              "threshold_elevation_ft": None, "elevation_source": None,
              "confidence": round(min(o["confidence"], 0.95), 2),
              "evidence": f"{o['evidence']} Rank {n}: {WHY.get(o['kind'], '')}; {o['side']} side."
                          + (f" {k_note}" if (k_note := (f"Count check: {note}." if note else "")) else "")}
        validate("entry_point", ep)
        eps.append(ep)
    log = {"building_id": bid, "at": datetime.now(timezone.utc).isoformat(), "model": res["model"],
           "cached": bool(res.get("cached")), "views": views, "model_counts":
           {"drive_in": r.get("drive_in_count"), "dock": r.get("dock_count")}, "listed_counts": found,
           "costar_counts": costar, "count_check": check, "views_without_building": r.get("views_without_building"),
           "ranking_rule": "drive-in and personnel doors at grade first, then ramps, then dock-high doors; "
                           "then by confidence"}
    write_json(BUILDINGS / bid / "entry_points.json", eps)
    write_json(BUILDINGS / bid / "site_log.json", log)
    return eps, log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("buildings", nargs="+")
    ap.add_argument("--cache-only", action="store_true")
    a = ap.parse_args()
    for bid in a.buildings:
        eps, log = scout(bid, a.cache_only)
        print(f"{bid}: {len(eps)} entry points; {log['count_check']}; cached={log['cached']}")
        for e in eps:
            print(f"   {e['id']} {e['kind']:<8} {e['image_kind']:<14} conf {e['confidence']:.2f} "
                  f"{'(map)' if e['lat'] else '(no map pos)'} {e['evidence'][:110]}")
