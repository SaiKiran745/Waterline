"""Pick the demo shortlist and write data/cache/shortlist.json (git-ignored: it holds CoStar ids).

    python -m app.sources.shortlist            # print the table and write the shortlist
    python -m app.sources.shortlist --dry-run  # print only

Rules (human decision, 2026-11-14):
  single-storey Houston retail/industrial/flex (every scan is on the ground floor),
  assessor improvement value present (structure loss needs it; no placeholders),
  best scan coverage (scan areaFloor / CoStar GBA), aiming for 40% or more,
  at least 2 outside the FEMA 1% annual-chance area, including the 96-position industrial
  building if it qualifies. Buildings are referred to by letter in committed files.
"""
import math
import sys

from app.config import SHORTLIST
from app.sources import costar, fema, matterport
from app.sources.cache import write_json

MIN_POSITIONS = 8
MAX_GEO_DIST_M = 150
MIN_COVERAGE = 0.40
MAX_COVERAGE = 1.10          # above this the scan likely includes outdoor or double-counted area
TARGET_COUNT = 8
MIN_OUTSIDE = 2
MUST_CONSIDER_POSITIONS = 96  # "the 96-position industrial one"

MODEL_FRAGMENT = """{ id state dimensions(units: imperial) { areaFloor } locations { id }
  assets { meshes { resolution status } } geocoordinates { latitude longitude } }"""


def model_facts(model_ids: list[str]) -> dict[str, dict]:
    facts = {}
    for i in range(0, len(model_ids), 10):
        batch = model_ids[i:i + 10]
        q = "query {\n" + "\n".join(f'  m{j}: model(id: "{mid}") {MODEL_FRAGMENT}' for j, mid in enumerate(batch)) + "\n}"
        data = matterport.graphql(q)
        for j, mid in enumerate(batch):
            m = data.get(f"m{j}") or {}
            g = m.get("geocoordinates") or {}
            facts[mid] = {"area_sqft": (m.get("dimensions") or {}).get("areaFloor"),
                          "positions": len(m.get("locations") or []),
                          "mesh": any(x["status"] == "available" for x in (m.get("assets") or {}).get("meshes") or []),
                          "geo": (g.get("latitude"), g.get("longitude"))}
    return facts


def dist_m(a, b) -> float | None:
    if None in (*a, *b):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def build_table() -> list[dict]:
    cands = costar.houston_ground_floor_candidates()
    values = costar.assessor_values(c["id"] for c in cands)
    facts = model_facts([m for c in cands for m in c["models"]])
    # A model attached to several CoStar properties (for example one scan filed on every building of a park)
    # cannot be tied to one building, so it is not used.
    owners: dict[str, int] = {}
    for c in cands:
        for mid in c["models"]:
            owners[mid] = owners.get(mid, 0) + 1
    rows = []
    for c in cands:
        usable = []
        for mid in c["models"]:
            f = facts[mid]
            d = dist_m((c["lat"], c["lng"]), f["geo"])
            if owners[mid] > 1:
                continue
            if f["positions"] >= MIN_POSITIONS and f["mesh"] and f["area_sqft"] and d is not None and d <= MAX_GEO_DIST_M:
                usable.append((mid, f, d))
        if not usable:
            continue
        mid, f, d = max(usable, key=lambda t: t[1]["area_sqft"])
        cov = f["area_sqft"] / c["gba"] if c["gba"] else None
        rows.append({"costar_property_id": c["id"], "type": c["type"], "gba": c["gba"], "model": mid,
                     "positions": f["positions"], "scan_area_sqft": round(f["area_sqft"]), "coverage": cov,
                     "geo_dist_m": round(d), "value": values.get(c["id"]), "lat": c["lat"], "lng": c["lng"]})
    for r in rows:
        if r["value"]:
            r["fema"] = fema.flood_zone(r["lat"], r["lng"])
    return rows


def select(rows: list[dict]) -> list[dict]:
    ok = [r for r in rows if r["value"] and r["coverage"] and MIN_COVERAGE <= r["coverage"] <= MAX_COVERAGE]
    inside = sorted([r for r in ok if r["fema"]["in_mapped_flood_zone"]], key=lambda r: -r["coverage"])
    outside = sorted([r for r in ok if r["fema"]["in_mapped_flood_zone"] is False], key=lambda r: -r["coverage"])
    must = [r for r in outside if r["type"] == "Industrial" and r["positions"] == MUST_CONSIDER_POSITIONS]
    picked = must + [r for r in outside if r not in must][:max(0, MIN_OUTSIDE - len(must))]
    for r in inside + [r for r in outside if r not in picked]:   # then every in-zone qualifier, then best coverage
        if len(picked) >= TARGET_COUNT:
            break
        if r not in picked:
            picked.append(r)
    picked.sort(key=lambda r: (not r["fema"]["in_mapped_flood_zone"], -r["coverage"]))
    for letter, r in zip("ABCDEFGH", picked):
        r["letter"] = letter
    return picked


def main() -> None:
    rows = build_table()
    with_value = [r for r in rows if r["value"]]
    print(f"usable single-storey candidates: {len(rows)} | with assessor improvement value: {len(with_value)}")
    print(f"{'type':14s} {'sfha':5s} {'cov':>5s} {'pos':>4s} value")
    for r in sorted(with_value, key=lambda r: -(r["coverage"] or 0)):
        print(f"{r['type']:14s} {str(r['fema']['in_mapped_flood_zone']):5s} {r['coverage']:5.0%} {r['positions']:4d} "
              f"{r['value']['value_as_of']}")
    picked = select(rows)
    print(f"\npicked {len(picked)}:")
    for r in picked:
        print(f"  {r['letter']} {r['type']:14s} sfha={r['fema']['in_mapped_flood_zone']!s:5s} zone={r['fema']['flood_zone']} "
              f"cov={r['coverage']:.0%} pos={r['positions']}")
    if "--dry-run" not in sys.argv:
        out = [{"letter": r["letter"], "building_id": str(r["costar_property_id"]),
                "costar_property_id": r["costar_property_id"], "matterport_model_id": r["model"],
                "type": r["type"], "positions": r["positions"], "scan_area_sqft": r["scan_area_sqft"],
                "gba": r["gba"], "coverage": round(r["coverage"], 3), "in_mapped_flood_zone": r["fema"]["in_mapped_flood_zone"],
                "flood_zone": r["fema"]["flood_zone"], "lat": r["lat"], "lng": r["lng"]} for r in picked]
        write_json(SHORTLIST, out)
        print(f"wrote {SHORTLIST}")


if __name__ == "__main__":
    main()
