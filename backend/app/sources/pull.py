"""Pull and cache everything for the shortlist, then build Building records.

    python -m app.sources.pull              # all shortlisted buildings
    python -m app.sources.pull A C          # only these letters
    DEMO_MODE=1 python -m app.sources.pull  # cache only; fails loudly on any miss

Per building: CoStar record, current tenants, assessor value; FEMA zone; USGS elevation (context only);
Matterport floors, rooms, every scan position and its 2k skybox faces, the 50k OBJ mesh;
Vexcel parcel and footprint, overhead (ortho) and angled (oblique) imagery.
Signed Matterport URLs expire about 5 minutes after the query, so panoramas are queried in chunks
and each chunk is downloaded at once.
"""
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from app.config import BUILDINGS, CACHE, MEDIA, demo_mode
from app.sources import costar, elevation, fema, matterport, vexcel
from app.sources.cache import write_json
from app.sources.registry import load_shortlist

MIN_FREE_BYTES = 1_000_000_000
PANO_CHUNK = 10
FACES = 6

OVERVIEW_Q = """query($id: ID!) { model(id: $id) {
  id state created
  dimensions(units: imperial) { areaFloor }
  geocoordinates { latitude longitude }
  floors { id label sequence }
  rooms { id label floor { id } classifications { label confidence } ceiling(units: imperial) { maxHeight } }
  locations { id label floor { id } room { id } position { x y z } neighbors }
  panoLocations { id label anchor { id } position { x y z } rotation { x y z w } resolutions }
  assets { meshes { format resolution status filename }
           textures { quality resolution textures status } }
} }"""
SKYBOX_Q = """query($id: ID!, $ids: [String!]) { model(id: $id) {
  panoLocations(ids: $ids) { id skybox(resolution: "2k") { status children } } } }"""
MESH_Q = """query($id: ID!) { model(id: $id) { assets { meshes(resolutions: ["50k"]) { filename url } } } }"""


def check_disk() -> None:
    free = shutil.disk_usage(CACHE.parent).free
    if free < MIN_FREE_BYTES and not demo_mode():
        raise SystemExit(f"Stopping: only {free / 1e9:.2f} GB free on disk (need {MIN_FREE_BYTES / 1e9:.0f} GB)")


def obj_texture_status(path: Path) -> dict:
    counts = {"v": 0, "vt": 0, "f": 0, "mtllib": 0, "usemtl": 0}
    with open(path, errors="replace") as fh:
        for line in fh:
            key = line.split(" ", 1)[0]
            if key in counts:
                counts[key] += 1
    return {"vertices": counts["v"], "faces": counts["f"], "has_uv": counts["vt"] > 0,
            "has_materials": counts["mtllib"] + counts["usemtl"] > 0}


def pull_costar(entries: list[dict]) -> dict[int, dict]:
    ids = [e["costar_property_id"] for e in entries]
    records = costar.property_records(ids)
    tenants = costar.current_tenants(ids)
    values = costar.assessor_values(ids)
    out = {}
    for pid in ids:
        rec = records[pid]
        write_json(CACHE / "costar" / "property" / f"{pid}.json", rec)
        blk = costar.type_block(rec)
        names = list(dict.fromkeys(t["name"] for t in tenants.get(pid, []) if t.get("name")))
        out[pid] = {
            "name": rec.get("buildingName"), "address": costar.address(rec),
            "lat": rec["primaryAddress"]["latitude"], "lng": rec["primaryAddress"]["longitude"],
            "property_type": costar.decode("PropertyType", rec.get("propertyType")),
            "property_subtype": costar.decode("PropertySubtype", rec.get("propertySubtype")),
            "size_sqft": rec.get("grossBuildingAreaSquareFeet"), "year_built": costar.year_built(rec),
            "stories": rec.get("numStoriesAboveGrade"), "tenants": names,
            "current_tenancies": len(tenants.get(pid, [])),
            "loading_docks_external": blk.get("numExternalLoadingDocks"),
            "drive_in_bays": (blk.get("driveInBays") or {}).get("numDriveInBays"),
            "matterport_model_ids": costar.matterport_model_ids(rec),
            "value": values.get(pid),
        }
    return out


def pull_matterport(bid: str, model_id: str) -> dict:
    ov = matterport.graphql(OVERVIEW_Q, {"id": model_id})["model"]
    media = MEDIA / bid
    panos = ov.get("panoLocations") or []

    def face_path(pano_id, i):
        return media / "panos" / pano_id / f"face{i}.jpg"

    missing = [p["id"] for p in panos if not all(face_path(p["id"], i).exists() for i in range(FACES))]
    for k in range(0, len(missing), PANO_CHUNK):
        chunk = missing[k:k + PANO_CHUNK]
        data = matterport.graphql(SKYBOX_Q, {"id": model_id, "ids": chunk}, refresh=True)
        jobs = []
        for p in data["model"]["panoLocations"]:
            children = (p.get("skybox") or {}).get("children") or []
            jobs += [(url, face_path(p["id"], i)) for i, url in enumerate(children[:FACES])]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda job: matterport.download(*job), jobs))
        print(f"    panoramas {min(k + PANO_CHUNK, len(missing))}/{len(missing)}", flush=True)

    mesh_path = media / "mesh" / "mesh_50k.obj"
    if not mesh_path.exists():
        mesh = matterport.graphql(MESH_Q, {"id": model_id}, refresh=True)["model"]["assets"]["meshes"][0]
        matterport.download(mesh["url"], mesh_path)
    complete = [p for p in panos if all(face_path(p["id"], i).exists() for i in range(FACES))]
    assets = ov.get("assets") or {}
    return {
        "model_id": model_id, "state": ov.get("state"),
        "scan_area_sqft": (ov.get("dimensions") or {}).get("areaFloor"),
        "geocoordinates": ov.get("geocoordinates"),
        "floors": ov.get("floors") or [], "rooms": ov.get("rooms") or [],
        "locations": ov.get("locations") or [],
        "panos": [{"id": p["id"], "location_id": (p.get("anchor") or {}).get("id"), "position": p.get("position"),
                   "rotation": p.get("rotation"),
                   "faces": [f"/media/{bid}/panos/{p['id']}/face{i}.jpg" for i in range(FACES)]} for p in complete],
        "panos_listed": len(panos), "panos_complete": len(complete),
        "mesh": {"url": f"/media/{bid}/mesh/mesh_50k.obj", "bytes": mesh_path.stat().st_size,
                 **obj_texture_status(mesh_path)},
        "meshes_listed": assets.get("meshes") or [], "textures_listed": assets.get("textures") or [],
    }


def capture_date(xmp: dict) -> str | None:
    raw = xmp.get("last-capture-date")
    try:
        return datetime.strptime(raw, "%a %b %d %H:%M:%S UTC %Y").date().isoformat() if raw else None
    except ValueError:
        return None


def pull_vexcel(bid: str, lat: float, lng: float) -> dict:
    media = MEDIA / bid / "aerial"
    pe = vexcel.property_extract(lat, lng)
    parcel_wkt, footprint = None, None
    if pe["status"] == 200 and pe["response"].get("features"):
        feat = pe["response"]["features"][0]
        parcel_wkt = vexcel.geojson_to_wkt(feat["geometry"])
        structs = feat["properties"].get("structures") or []
        prim = ([s for s in structs if s.get("primary-structure")] or structs or [None])[0]
        if prim:
            footprint = {"area_sqft": prim.get("footprint.area"), "wkt": prim.get("footprint.wkt")}
    area = parcel_wkt or vexcel.point_wkt(lat, lng)
    images = {}
    ortho = vexcel.ortho(area, media / "ortho.jpg")
    images["ortho"] = vexcel.read_xmp(ortho)
    newest, dirs = vexcel.newest_oblique_directions(vexcel.oblique_coverage(area))
    for d in dirs:
        img = vexcel.oblique(area, d, media / f"{d}.jpg")
        images[d] = vexcel.read_xmp(img)
    return {
        "parcel_found": parcel_wkt is not None, "parcel_wkt": parcel_wkt, "footprint": footprint,
        "images": {k: {"url": f"/media/{bid}/aerial/{k}.jpg", "meta_url": f"/media/{bid}/aerial/{k}.meta.json",
                       "collection": v.get("collection"), "capture_date": capture_date(v),
                       "min_gsd_m": v.get("min-gsd"), "max_gsd_m": v.get("max-gsd")} for k, v in images.items()},
        "oblique_capture_date": newest[:10] if newest else None,
    }


def main(letters: list[str]) -> None:
    from app.buildings import assemble   # local import: buildings imports registry
    entries = [e for e in load_shortlist() if not letters or e["letter"] in letters]
    print(f"pulling {len(entries)} building(s); DEMO_MODE={'1' if demo_mode() else '0'}")
    co = pull_costar(entries)
    report = []
    for e in entries:
        bid, pid = e["building_id"], e["costar_property_id"]
        print(f"  {e['letter']}: CoStar ok; FEMA, USGS, Matterport, Vexcel...", flush=True)
        check_disk()
        c = co[pid]
        flood = fema.flood_zone(c["lat"], c["lng"])
        elev = elevation.ground_elevation_ft(c["lat"], c["lng"])
        mp = pull_matterport(bid, e["matterport_model_id"])
        vx = pull_vexcel(bid, c["lat"], c["lng"])
        parts = {"letter": e["letter"], "costar": c, "fema": flood, "usgs_ground_elevation_ft": elev,
                 "matterport": mp, "vexcel": vx}
        write_json(BUILDINGS / bid / "parts.json", parts)
        write_json(MEDIA / bid / "manifest.json", {
            "building_id": bid, "mesh": mp["mesh"], "panos": mp["panos"], "floors": mp["floors"],
            "rooms": mp["rooms"], "locations": mp["locations"], "aerial": vx["images"],
            "notes": ["face0 of each skybox was observed to be the up face; the order of faces 1-5 is not documented",
                      "mesh units consistent with metres, z up, floor near z = 0 (observed on one model)"]})
        building = assemble(bid)
        report.append({"letter": e["letter"], "type": c["property_type"], "positions": len(mp["locations"]),
                       "panos": f"{mp['panos_complete']}/{mp['panos_listed']}",
                       "mesh_kb": mp["mesh"]["bytes"] // 1024, "mesh_uv": mp["mesh"]["has_uv"],
                       "aerial": len(vx["images"]), "parcel": vx["parcel_found"],
                       "value": building["improvement_value_usd"] is not None,
                       "fema": f"{building['flood_zone']}{' (1%)' if building['in_mapped_flood_zone'] else ''}",
                       "coverage": round(building["scan_area_sqft"] / building["size_sqft"], 2)})
        print(f"  {e['letter']}: done {report[-1]}", flush=True)
    write_json(CACHE / "pull_report.json", report)


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]])
