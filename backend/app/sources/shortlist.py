"""Pick the demo shortlist and write data/cache/shortlist.json (git-ignored: it maps slugs to CoStar ids).

    python -m app.sources.shortlist            # revise the shortlist under the current rules and write it
    python -m app.sources.shortlist --dry-run  # print only

Rules (human decisions, 2026-11-14):
  - single-storey Houston retail/industrial/flex, so every scan is on the ground floor
  - no children's spaces (day care, school and similar subtypes)
  - assessor improvement value present, and its value per sq ft within VALUE_BAND of the candidate-pool
    median (structure loss scales with it, so an implausible value would distort the ranking)
  - scan coverage (scan areaFloor / CoStar GBA, capped at 100%) of 40% or more, best first
  - scans attached to more than one CoStar property are not used
  - at least MIN_OUTSIDE buildings outside the FEMA 1% annual-chance area
  - replacements prefer a named current tenant
Retained buildings keep their letter; replacements take the freed letters. API ids are slugs ("building-a").
The CoStar property id stays in this git-ignored mapping and never leaves the server.
"""
import math
import statistics
import sys

from app.config import SHORTLIST
from app.sources import costar, fema, matterport
from app.sources.cache import write_json

MIN_POSITIONS = 8
MAX_GEO_DIST_M = 150
MIN_COVERAGE = 0.40
TARGET_COUNT = 8
MIN_OUTSIDE = 3
VALUE_BAND = (0.4, 2.5)     # x the pool median improvement value per sq ft
CHILD_SUBTYPE_WORDS = ("daycare", "school", "child", "nursery", "kindergarten", "preschool")
LETTERS = "ABCDEFGH"

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
    ids = [c["id"] for c in cands]
    values = costar.assessor_values(ids)
    records = costar.property_records(ids)
    tenants = costar.current_tenants(ids)
    facts = model_facts([m for c in cands for m in c["models"]])
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
        if not usable or not c["gba"]:
            continue
        mid, f, d = max(usable, key=lambda t: t[1]["area_sqft"])
        v = values.get(c["id"])
        rows.append({"costar_property_id": c["id"], "type": c["type"],
                     "subtype": costar.decode("PropertySubtype", records[c["id"]].get("propertySubtype")),
                     "gba": c["gba"], "model": mid, "positions": f["positions"],
                     "scan_area_sqft": round(f["area_sqft"]), "coverage_raw": f["area_sqft"] / c["gba"],
                     "coverage": min(f["area_sqft"] / c["gba"], 1.0), "geo_dist_m": round(d), "value": v,
                     "value_per_sqft": v["improvement_value_usd"] / c["gba"] if v else None,
                     "named_tenants": len({t["name"] for t in tenants[c["id"]] if t.get("name")}),
                     "lat": c["lat"], "lng": c["lng"]})
    for r in rows:
        if r["value"]:
            r["fema"] = fema.flood_zone(r["lat"], r["lng"])
    return rows


def eligible(rows: list[dict]) -> tuple[list[dict], float]:
    valued = [r for r in rows if r["value"]]
    median = statistics.median(r["value_per_sqft"] for r in valued)
    lo, hi = VALUE_BAND[0] * median, VALUE_BAND[1] * median
    ok = [r for r in valued
          if r["coverage"] >= MIN_COVERAGE
          and lo <= r["value_per_sqft"] <= hi
          and not any(w in (r["subtype"] or "").lower() for w in CHILD_SUBTYPE_WORDS)]
    return ok, median


def revise(rows: list[dict], current: list[dict]) -> list[dict]:
    ok, _ = eligible(rows)
    by_id = {r["costar_property_id"]: r for r in ok}
    picked = {e["letter"]: by_id[e["costar_property_id"]] for e in current if e["costar_property_id"] in by_id}
    pool = sorted([r for r in ok if r not in picked.values()],
                  key=lambda r: (r["named_tenants"] == 0, -r["coverage"]))
    for letter in LETTERS[:TARGET_COUNT]:
        if letter in picked or not pool:
            continue
        outside = sum(1 for r in picked.values() if r["fema"]["in_mapped_flood_zone"] is False)
        free = sum(1 for x in LETTERS[:TARGET_COUNT] if x not in picked)
        need_outside = outside + free <= MIN_OUTSIDE
        choice = next((r for r in pool if not need_outside or r["fema"]["in_mapped_flood_zone"] is False), None)
        if choice:
            picked[letter] = choice
            pool.remove(choice)
    return [dict(r, letter=k) for k, r in sorted(picked.items())]


def main() -> None:
    rows = build_table()
    ok, median = eligible(rows)
    current = []
    if SHORTLIST.exists():
        import json
        current = json.loads(SHORTLIST.read_text())
    print(f"usable candidates {len(rows)} | eligible {len(ok)} | pool median improvement value ${median:.0f}/sq ft "
          f"(band ${VALUE_BAND[0] * median:.0f}-{VALUE_BAND[1] * median:.0f})")
    for e in current:
        r = next((x for x in rows if x["costar_property_id"] == e["costar_property_id"]), None)
        why = "kept" if r in ok else "dropped: " + ", ".join(filter(None, [
            "children's space" if r and any(w in (r["subtype"] or "").lower() for w in CHILD_SUBTYPE_WORDS) else "",
            f"value ${r['value_per_sqft']:.0f}/sq ft outside band" if r and r["value_per_sqft"] is not None and not (
                VALUE_BAND[0] * median <= r["value_per_sqft"] <= VALUE_BAND[1] * median) else ""]))
        print(f"  {e['letter']}: {why}")
    picked = revise(rows, current)
    print(f"\npicked {len(picked)}:")
    for r in picked:
        print(f"  {r['letter']} {r['subtype'] or r['type']:30s} sfha={r['fema']['in_mapped_flood_zone']!s:5s} "
              f"cov={r['coverage']:.0%}{' (capped from %.0f%%)' % (100 * r['coverage_raw']) if r['coverage_raw'] > 1 else ''} "
              f"pos={r['positions']} tenants={r['named_tenants']} ${r['value_per_sqft']:.0f}/sq ft")
    if "--dry-run" not in sys.argv:
        out = [{"letter": r["letter"], "building_id": f"building-{r['letter'].lower()}",
                "costar_property_id": r["costar_property_id"], "matterport_model_id": r["model"],
                "type": r["type"], "subtype": r["subtype"], "positions": r["positions"],
                "scan_area_sqft": r["scan_area_sqft"], "gba": r["gba"], "coverage": round(r["coverage"], 3),
                "coverage_raw": round(r["coverage_raw"], 3), "named_tenants": r["named_tenants"],
                "value_per_sqft": round(r["value_per_sqft"], 1),
                "in_mapped_flood_zone": r["fema"]["in_mapped_flood_zone"], "flood_zone": r["fema"]["flood_zone"],
                "lat": r["lat"], "lng": r["lng"]} for r in picked]
        write_json(SHORTLIST, out)
        print(f"wrote {SHORTLIST}")


if __name__ == "__main__":
    main()
