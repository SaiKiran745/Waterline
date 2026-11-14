"""Interior survey (BUILD_PROMPTS Phase 3A): flood-vulnerable assets from Matterport panoramas.

    python -m app.survey.interior building-h [--max-positions 20] [--max-relooks 8]

1. Choose scan positions per room (spread out, not all of them) and record why.
2. One vision call per chosen position with its four side faces (the up face is skipped): asset boxes, the image row
   of each asset's lowest vulnerable part, a visual height estimate, and a privacy check per face.
3. Height: ray-cast the lowest-vulnerable-part pixel onto the mesh (app.survey.geometry). Keep it as
   "measured from mesh" when it agrees with the visual estimate; otherwise keep a wider estimated range with
   lower confidence. Position: ray-cast the box centre (mesh coordinates).
4. De-duplicate the same asset seen from several positions; re-look at low-confidence assets from a
   neighbouring scan position and update the record (both looks are kept in `observations`).
5. Value ranges come from app/loss/assumptions.yaml by category.
Outputs (git-ignored): data/cache/buildings/<id>/assets.json, screening.json, survey_log.json.
"""
import argparse
import io
import json
import math
import re
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from app.buildings import validate
from app.config import BUILDINGS, MEDIA
from app.loss import classes
from app.loss import model as loss_model
from app.sources import gemini, spend
from app.sources.cache import CacheMiss, write_json
from app.survey.geometry import CONVENTION as CONV, cast_pixel, floor_z_below, mesh_for

FACE_PX = 2048
SIDE_FACES = (1, 2, 3, 4)
UPLOAD_PX = 1024
FT = 0.3048
LOW_CONF = 0.6
MERGE_M = 0.5        # two sightings are one asset only if their mesh positions are this close and the category matches
# Wall outlets, switches and fixed cabinetry are part of the building: the Hazus structure curve already prices them.
# They stay in the inventory (water visibly reaches them) but as "finishes" at $0, so they are not counted twice.
FABRIC = re.compile(r"\b(outlets?|receptacles?|switch(?!gear|board)\w*|sockets?|cover plates?|"
                    r"(kitchen |lower |base |built-in )cabinet\w*|casework|countertops?)\b", re.I)


FABRIC_NOTE = " Building fabric: priced by the structure curve, not as contents (A-FIN)."
VEHICLE_NOTE = " Road vehicle: a movable asset at risk, not counted in contents loss (V-VEHICLE)."


def is_fabric(label: str) -> bool:
    return classes.classify(label, "other") == "A-FIN"
MESH_TOL_FT = 0.15          # geometry error (about +/-5 cm) on top of the measured box-edge spread
CATEGORIES = ["electrical", "it", "hvac", "inventory", "equipment", "furniture", "other"]

ASSET_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "faces": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "face": {"type": "INTEGER"}, "room_type": {"type": "STRING"},
            "people_identifiable": {"type": "BOOLEAN"}, "childrens_space": {"type": "BOOLEAN"},
            "personal_documents": {"type": "BOOLEAN"}},
            "required": ["face", "room_type", "people_identifiable", "childrens_space", "personal_documents"]}},
        "assets": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "face": {"type": "INTEGER"},
            "category": {"type": "STRING", "enum": CATEGORIES},
            "label": {"type": "STRING"},
            "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            "vulnerable_bottom_y": {"type": "INTEGER"},
            "height_ft_low": {"type": "NUMBER"}, "height_ft_high": {"type": "NUMBER"},
            "confidence": {"type": "NUMBER"}, "evidence": {"type": "STRING"}},
            "required": ["face", "category", "label", "box_2d", "vulnerable_bottom_y", "height_ft_low",
                         "height_ft_high", "confidence", "evidence"]}},
    },
    "required": ["faces", "assets"],
}

SURVEY_PROMPT = """You are surveying the ground floor of a commercial building in Houston for flood damage.
The images are four sideways views (cube faces) from one 3D-scan position, labelled Face 1 to Face 4. The camera is 1.4 m (4.6 ft) above the floor.

List the contents and equipment that flood water would damage:
- electrical: panels, switchgear, transformers, chargers, floor power boxes
- it: server racks, network cabinets, computers, UPS units
- hvac: air handlers, water heaters, condensing units, pumps
- inventory: stored goods, pallets, racked stock
- equipment: machinery, forklifts, compressors, appliances, workshop tools
- furniture: groups of desks, chairs, cabinets
- other: anything else that water would damage
Do NOT list the building itself (walls, floors, doors, windows, ceilings, light fixtures, sprinkler pipes) or anything mounted above 8 ft.
Group many similar small items into one entry (for example "row of 6 desks with computers").

For each item give:
- face: the face number (1 to 4) where it is most clearly visible
- box_2d: [ymin, xmin, ymax, xmax] on that face, normalised to 0-1000
- vulnerable_bottom_y: the image row (0-1000) of the LOWEST part that water would damage (for example the bottom of a panel enclosure, the base of a rack, the controls of a water heater, the bottom of stored boxes)
- height_ft_low / height_ft_high: your estimate of that lowest vulnerable part's height above the floor, in feet. Use reference objects: wall outlets about 1.3 ft, desks about 2.5 ft, standard doors about 6.7 ft, pallets about 0.5 ft. When unsure, give a wide range.
- confidence: 0 to 1 that the item and its height are right. Use a low value when the item is partly hidden or far away.
- evidence: one sentence on what in the image shows this.

For every face, also report room_type (for example warehouse, office, break room, restroom, electrical room, showroom) and whether it shows identifiable people (faces), a children's space, or readable personal documents.
Return only items you can actually see. An empty list is fine."""

RELOOK_PROMPT = """This is a close-up from a different 3D-scan position in the same commercial building (camera 1.4 m above the floor).
Another view suggested a "{label}" ({category}) near the centre of this image. If you can see it, give box_2d [ymin, xmin, ymax, xmax] normalised to 0-1000 on this image, vulnerable_bottom_y (image row 0-1000 of its lowest part that flood water would damage), height_ft_low / height_ft_high (that part's height above the floor in feet), confidence (0-1) and one sentence of evidence. Set found to false if it is not visible (then give box_2d [0, 0, 0, 0], zeros for the numbers and an empty evidence). Also report whether the image shows identifiable people, a children's space, or readable personal documents."""

RELOOK_SCHEMA = {"type": "OBJECT", "properties": {
    "found": {"type": "BOOLEAN"}, "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
    "vulnerable_bottom_y": {"type": "INTEGER"}, "height_ft_low": {"type": "NUMBER"}, "height_ft_high": {"type": "NUMBER"},
    "confidence": {"type": "NUMBER"}, "evidence": {"type": "STRING"},
    "people_identifiable": {"type": "BOOLEAN"}, "childrens_space": {"type": "BOOLEAN"}, "personal_documents": {"type": "BOOLEAN"}},
    # Every field is required: with optional fields the model answered "found" without heights (H, 2026-11-14).
    "required": ["found", "box_2d", "vulnerable_bottom_y", "height_ft_low", "height_ft_high", "confidence", "evidence",
                 "people_identifiable", "childrens_space", "personal_documents"]}


def jpeg(img: Image.Image, size: int = UPLOAD_PX) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").resize((size, size)).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def face_image(bid: str, pano_id: str, face: int) -> Image.Image:
    return Image.open(MEDIA / bid / "panos" / pano_id / f"face{face}.jpg")


# ------------------------------------------------------------------ position choice

def choose_positions(mp: dict, max_positions: int) -> list[dict]:
    """Spread positions over rooms: at least one per room, more in big rooms, farthest-point within a room."""
    panos = {p["location_id"]: p for p in mp["panos"]}
    rooms = {r["id"]: r for r in mp["rooms"]}
    by_room: dict[str, list[dict]] = {}
    for loc in mp["locations"]:
        if loc["id"] in panos:
            by_room.setdefault((loc.get("room") or {}).get("id") or "none", []).append(loc)
    quota = {r: max(1, min(3, round(len(ls) / 6))) for r, ls in by_room.items()}
    while sum(quota.values()) > max_positions:
        r = max(quota, key=lambda k: (quota[k], len(by_room[k])))
        if quota[r] == 1:
            break
        quota[r] -= 1
    chosen = []
    for rid, locs in sorted(by_room.items(), key=lambda kv: -len(kv[1])):
        pts = np.array([[l["position"]["x"], l["position"]["y"]] for l in locs])
        centre = pts.mean(axis=0)
        picks = [int(np.argmin(np.linalg.norm(pts - centre, axis=1)))]
        while len(picks) < min(quota[rid], len(locs)):
            d = np.min(np.linalg.norm(pts[:, None] - pts[picks][None], axis=2), axis=1)
            picks.append(int(np.argmax(d)))
        label = (rooms.get(rid) or {}).get("label") or f"room {rid[:6]}"
        for k, i in enumerate(picks):
            reason = (f"most central of {len(locs)} positions in {label}" if k == 0 else
                      f"farthest from the positions already chosen in {label} ({len(locs)} positions)")
            chosen.append({"location": locs[i], "pano": panos[locs[i]["id"]], "room_id": rid, "reason": reason})
    # Few, large rooms leave slots unused: fill to max_positions with positions farthest from everything chosen.
    every = [l for ls in by_room.values() for l in ls]
    taken = {c["location"]["id"] for c in chosen}
    while len(chosen) < max_positions and len(taken) < len(every):
        pts = np.array([[l["position"]["x"], l["position"]["y"]] for l in every])
        have = np.array([[c["location"]["position"]["x"], c["location"]["position"]["y"]] for c in chosen])
        d = np.min(np.linalg.norm(pts[:, None] - have[None], axis=2), axis=1)
        d[[i for i, l in enumerate(every) if l["id"] in taken]] = -1
        loc = every[int(np.argmax(d))]
        rid = (loc.get("room") or {}).get("id") or "none"
        label = (rooms.get(rid) or {}).get("label") or f"room {rid[:6]}"
        chosen.append({"location": loc, "pano": panos[loc["id"]], "room_id": rid,
                       "reason": f"filling to {max_positions}: farthest from every position already chosen ({label}, "
                                 f"{float(d.max()):.1f} m away)"})
        taken.add(loc["id"])
    return chosen[:max_positions]


# ------------------------------------------------------------------ measurement

def measure(mesh, pano: dict, face: int, box: list[int], bottom_y: int, floor_z: float | None) -> dict:
    ymin, xmin, ymax, xmax = box
    cx = (xmin + xmax) / 2 * FACE_PX / 1000
    cy = (ymin + ymax) / 2 * FACE_PX / 1000
    by = min(max(bottom_y, 0), 1000) * FACE_PX / 1000
    centre = cast_pixel(mesh, CONV, pano["position"], pano["rotation"], face, cx, cy, FACE_PX)
    zs = []
    for dy in (-20, 0, 20):
        h = cast_pixel(mesh, CONV, pano["position"], pano["rotation"], face, cx, min(max(by + dy, 0), FACE_PX - 1), FACE_PX)
        if h and h["distance_m"] < 15 and floor_z is not None:
            zs.append((h["point"]["z"] - floor_z) / FT)
    span = None
    if len(zs) == 3:
        ty = (ymin + 0.03 * (ymax - ymin)) * FACE_PX / 1000          # just inside the top edge of the box
        top = cast_pixel(mesh, CONV, pano["position"], pano["rotation"], face, cx, ty, FACE_PX)
        if top and floor_z is not None and top["distance_m"] < 15:
            s = (top["point"]["z"] - floor_z) / FT - sum(zs) / 3
            span = round(s, 2) if 0.1 <= s <= 15 else None
    return {"position": centre["point"] if centre and centre["distance_m"] < 20 else None,
            "heights_ft": zs if len(zs) == 3 else None, "span_ft": span,
            "distance_m": centre["distance_m"] if centre else None}


SMALL_BOX = 2500     # box area in normalised units (0-1000 squared): about a 50 x 50 box
FAR_M = 10.0
EDGE = 10


def confidence_notes(box: list, m: dict, conf: float, edges: bool = True) -> tuple[float, list[str]]:
    """Lower confidence for small, distant or edge-cut boxes (x0.85 each). The bottom edge has its own rule."""
    ymin, xmin, ymax, xmax = box
    notes = []
    if (ymax - ymin) * (xmax - xmin) < SMALL_BOX:
        notes.append("small in the image")
    if m.get("distance_m") and m["distance_m"] > FAR_M:
        notes.append(f"{m['distance_m']:.0f} m from the camera")
    if edges and (xmin <= EDGE or xmax >= 1000 - EDGE or ymin <= EDGE):
        notes.append("cut by the image edge")
    return round(conf * 0.85 ** len(notes), 2), notes


TRUNCATED_Y = 985   # a box reaching this row (0-1000) runs off the bottom of the face: its lowest part is not visible


def decide_height(est_lo: float, est_hi: float, conf: float, m: dict, box: list | None = None) -> tuple[float, float, float, str]:
    est_lo, est_hi = max(0.0, min(est_lo, est_hi)), max(est_lo, est_hi)
    if box and len(box) == 4 and box[2] >= TRUNCATED_Y:
        # The object continues below the image edge, so neither the mesh nor the model sees its lowest part.
        # Assume it reaches the floor and keep the confidence low enough to trigger a re-look.
        seen = [h for h in (m.get("heights_ft") or [])]
        hi = max([est_hi] + [max(seen) + MESH_TOL_FT] if seen else [est_hi])
        return 0.0, round(max(hi, 0.1), 2), round(min(conf * 0.6, 0.55), 2), (
            "estimated: the item runs off the bottom of the image, so its lowest part is not visible; floor assumed")
    if m["heights_ft"]:
        z_lo = max(0.0, min(m["heights_ft"]) - MESH_TOL_FT)
        z_hi = max(m["heights_ft"]) + MESH_TOL_FT
        agrees = z_lo <= est_hi + 1.0 and z_hi >= est_lo - 1.0 and z_hi < 9
        if agrees:
            return round(z_lo, 2), round(max(z_hi, z_lo + 0.1), 2), min(0.95, conf + 0.1), "measured from mesh"
        lo, hi = min(est_lo, z_lo), max(est_hi, z_hi)
        return round(lo, 2), round(hi, 2), round(conf * 0.6, 2), (
            f"estimated: mesh ({z_lo:.1f}-{z_hi:.1f} ft) and visual estimate ({est_lo:.1f}-{est_hi:.1f} ft) disagree")
    return round(est_lo, 2), round(est_hi, 2), round(conf * 0.7, 2), "estimated: no mesh hit at the item"


# ------------------------------------------------------------------ survey

def survey_position(bid, mesh, mp, pos, log, cache_only: bool = False) -> list[dict]:
    pano = pos["pano"]
    parts = [SURVEY_PROMPT]
    for f in SIDE_FACES:
        parts += [f"Face {f}:", jpeg(face_image(bid, pano["id"], f))]
    res = gemini.generate_json(parts, ASSET_SCHEMA, tag=f"{bid}/survey/{pano['id']}", cache_only=cache_only)
    log["calls"].append({"kind": "survey", "pano": pano["id"], "model": res["model"], "cached": bool(res.get("cached")),
                         "tokens": (res.get("usage") or {}).get("totalTokenCount")})
    flags, room_types = {}, {}
    for fr in res["data"].get("faces", []):
        f = fr.get("face")
        if f in SIDE_FACES:
            flagged = [k for k in ("people_identifiable", "childrens_space", "personal_documents") if fr.get(k)]
            flags[f"{pano['id']}/face{f}"] = {"clear": not flagged, "reasons": flagged, "model": res["model"],
                                              "checked_at": res.get("fetched_at")}
            room_types[f] = fr.get("room_type") or ""
    floor_z = floor_z_below(mesh, pano["position"])
    out = []
    for a in res["data"].get("assets", []):
        if a.get("face") not in SIDE_FACES or len(a.get("box_2d") or []) != 4 or a.get("category") not in CATEGORIES:
            continue
        m = measure(mesh, pano, a["face"], a["box_2d"], a["vulnerable_bottom_y"], floor_z)
        lo, hi, conf, how = decide_height(a["height_ft_low"], a["height_ft_high"], float(a["confidence"]), m, a["box_2d"])
        conf, notes = confidence_notes(a["box_2d"], m, conf)
        cid = classes.classify(a["label"], a["category"])
        out.append({"pano": pano, "location": pos["location"], "room_id": pos["room_id"],
                    "room_type": room_types.get(a["face"], ""), "face": a["face"], "box": a["box_2d"],
                    "value_class": cid, "category": classes.category_for(cid, a["category"]),
                    "fabric": cid == "A-FIN", "label": a["label"].strip(), "height_ft_low": lo, "height_ft_high": hi,
                    "confidence": conf, "conf_notes": notes, "how": how, "position": m["position"],
                    "span_ft": m["span_ft"], "evidence": a["evidence"].strip(),
                    "visual": [a["height_ft_low"], a["height_ft_high"]], "model": res["model"]})
    return out, flags


def image_ref(bid: str, pano_id: str, face: int, box) -> str:
    return f"/media/{bid}/panos/{pano_id}/face{face}.jpg#box={','.join(str(int(v)) for v in box)}"


def observation(bid: str, d: dict) -> dict:
    return {"location_id": d["location"]["id"], "height_ft_low": d["height_ft_low"], "height_ft_high": d["height_ft_high"],
            "confidence": round(d["confidence"], 2), "evidence": f"{d['evidence']} ({d['how']}; {d['model']})",
            "image_ref": image_ref(bid, d["pano"]["id"], d["face"], d["box"])}


GENERIC = {"electrical", "industrial", "unit", "equipment", "machine", "large", "small", "heavy", "metal", "portable",
           "mobile", "wall", "mounted", "floor", "ground", "white", "red", "blue", "green", "black", "grey", "gray",
           "yellow", "orange", "silver", "with", "and", "the", "on", "in", "of", "for", "near", "stored", "storage",
           "system", "area", "item", "assorted", "various", "pile", "group", "set", "row", "old", "new", "side",
           "standing", "rolling", "wheeled", "wheel", "utility", "parked", "visible", "secondary", "control", "box",
           "panel", "station", "stand", "frame", "base", "top", "assembly", "type", "style", "multiple", "two", "three"}
NOUN_MERGE_M = 1.5   # sightings of one large object can land up to this far apart when the labels name the same thing


def nouns(label: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", (label or "").lower()):
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if len(w) > 2 and w not in GENERIC:
            out.add(w)
    return out


def same_asset(d: dict, e: dict) -> tuple[bool, str]:
    """Merge rule (human decisions 2026-11-14): same value class, and mesh positions within MERGE_M (0.5 m), or within
    NOUN_MERGE_M (1.5 m) when the labels share a specific noun (generic words such as "electrical" do not count)."""
    p, q = d["position"], e["position"]
    if not (p and q) or d["value_class"] != e["value_class"]:
        return False, ""
    dist = math.dist((p["x"], p["y"], p["z"]), (q["x"], q["y"], q["z"]))
    if dist < MERGE_M:
        return True, f"{dist:.2f} m apart"
    shared = nouns(d["label"]) & nouns(e["label"])
    if dist < NOUN_MERGE_M and shared:
        return True, f"{dist:.2f} m apart and both name {', '.join(sorted(shared))}"
    return False, ""


def merge(dets: list[dict]) -> list[list[dict]]:
    """Group detections that are the same asset (same_asset). Detections without a mesh position are never merged."""
    groups: list[list[dict]] = []
    for d in sorted(dets, key=lambda d: -d["confidence"]):
        for g in groups:
            if same_asset(d, g[0])[0]:
                g.append(d)
                break
        else:
            groups.append([d])
    return groups


def remerge(groups: list[list[dict]]) -> tuple[list[list[dict]], list[str]]:
    """After re-looks a group's best view can move: merge groups whose best views now meet the merge rule."""
    kept: list[list[dict]] = []
    notes = []
    for g in sorted(groups, key=lambda g: -g[0]["confidence"]):
        for k in kept:
            ok, why = same_asset(g[0], k[0])
            if ok:
                notes.append(f"'{g[0]['label']}' merged into '{k[0]['label']}' after the re-looks: {why}")
                k.extend(g)
                break
        else:
            kept.append(g)
    return kept, notes


def relook(bid, mesh, mp, group, log, flags) -> dict | None:
    best = group[0]
    if not best["position"]:
        return None
    panos = {p["location_id"]: p for p in mp["panos"]}
    p = np.array([best["position"][k] for k in "xyz"])
    neigh = [panos[n] for n in best["location"].get("neighbors") or [] if n in panos and n != best["location"]["id"]]
    if not neigh:
        return None
    cam = lambda q: np.array([q["position"][k] for k in "xyz"])
    neigh = [q for q in neigh if np.linalg.norm(cam(q) - cam(best["pano"])) > 0.5]
    if not neigh:
        return None
    nb = min(neigh, key=lambda q: np.linalg.norm(cam(q) - p))
    d = (p - cam(nb)) / np.linalg.norm(p - cam(nb))
    face, x, y = CONV.dir_to_pixel(nb["rotation"], d[None], FACE_PX)
    face, x, y = int(face[0]), float(x[0]), float(y[0])
    if face not in SIDE_FACES:
        return None
    half = 384
    x0, y0 = int(min(max(x - half, 0), FACE_PX - 2 * half)), int(min(max(y - half, 0), FACE_PX - 2 * half))
    crop = face_image(bid, nb["id"], face).crop((x0, y0, x0 + 2 * half, y0 + 2 * half))
    res = gemini.generate_json([RELOOK_PROMPT.format(label=best["label"], category=best["category"]), jpeg(crop, 768)],
                               RELOOK_SCHEMA, tag=f"{bid}/relook/{nb['id']}/{best['label'][:30]}")
    r = res["data"]
    log["calls"].append({"kind": "relook", "pano": nb["id"], "model": res["model"], "found": r.get("found"),
                         "cached": bool(res.get("cached")),
                         "tokens": (res.get("usage") or {}).get("totalTokenCount")})
    reasons = [k for k in ("people_identifiable", "childrens_space", "personal_documents") if r.get(k)]
    if reasons:
        flags[f"{nb['id']}/face{face}"] = {"clear": False, "reasons": reasons, "model": res["model"],
                                           "checked_at": res.get("fetched_at")}
    complete = len(r.get("box_2d") or []) == 4 and all(r.get(k) is not None for k in
                                                         ("height_ft_low", "height_ft_high", "vulnerable_bottom_y"))
    log["calls"][-1]["complete"] = complete
    if not r.get("found") or not complete:
        return None                                      # not seen, or an incomplete answer: inconclusive
    s = 2 * half / 1000
    box = [int((y0 + r["box_2d"][0] * s) * 1000 / FACE_PX), int((x0 + r["box_2d"][1] * s) * 1000 / FACE_PX),
           int((y0 + r["box_2d"][2] * s) * 1000 / FACE_PX), int((x0 + r["box_2d"][3] * s) * 1000 / FACE_PX)]
    bottom = int((y0 + r["vulnerable_bottom_y"] * s) * 1000 / FACE_PX)
    m = measure(mesh, nb, face, box, bottom, floor_z_below(mesh, nb["position"]))
    lo, hi, conf, how = decide_height(r["height_ft_low"], r["height_ft_high"], float(r["confidence"]), m, r["box_2d"])
    conf, notes = confidence_notes(r["box_2d"], m, conf, edges=False)    # crop edges are ours, not the object's
    loc = next(l for l in mp["locations"] if l["id"] == nb["location_id"])
    return {"pano": nb, "location": loc, "room_id": best["room_id"], "room_type": best["room_type"], "face": face,
            "box": box, "value_class": best["value_class"], "category": best["category"],
            "fabric": best.get("fabric", False), "label": best["label"],
            "height_ft_low": lo, "height_ft_high": hi, "conf_notes": notes, "span_ft": m["span_ft"] or best.get("span_ft"),
            "confidence": conf, "how": how, "position": m["position"] or best["position"],
            "evidence": r.get("evidence", "").strip(), "visual": [r["height_ft_low"], r["height_ft_high"]], "model": res["model"]}


def seed_positions(bid: str, mp: dict) -> list[dict]:
    """Positions the contents scout already read (data/cache/scout.json): surveyed first, so no call is repeated."""
    from app.config import CACHE
    path = CACHE / "scout.json"
    if not path.exists():
        return []
    scouted = (json.loads(path.read_text()).get(bid) or {}).get("positions") or []
    panos = {p["location_id"]: p for p in mp["panos"]}
    locs = {l["id"]: l for l in mp["locations"]}
    return [{"location": locs[x["location_id"]], "pano": panos[x["location_id"]],
             "room_id": (locs[x["location_id"]].get("room") or {}).get("id") or "none",
             "reason": f"read by the contents scout ({x['reason']})"} for x in scouted if x["location_id"] in panos]


class Stop(Exception):
    """Budget or billing stop: finish with what has been read, then exit non-zero."""


def run(bid: str, max_positions: int, max_relooks: int, cached_positions_only: bool = False) -> list[dict]:
    parts = json.loads((BUILDINGS / bid / "parts.json").read_text())
    mp = parts["matterport"]
    mesh = mesh_for(str(MEDIA / bid / "mesh" / "mesh_50k.obj"))
    rooms = {r["id"]: r for r in mp["rooms"]}
    log = {"building_id": bid, "started_at": datetime.now(timezone.utc).isoformat(), "positions": [], "calls": [],
           "relooks": [], "merge_rule": f"same category and mesh positions within {MERGE_M} m"}
    flags: dict = json.loads((BUILDINGS / bid / "screening.json").read_text()) if (BUILDINGS / bid / "screening.json").exists() else {}
    seeds = seed_positions(bid, mp)
    seen = {x["location"]["id"] for x in seeds}
    positions = (seeds + [x for x in choose_positions(mp, max_positions) if x["location"]["id"] not in seen])[:max_positions]
    print(f"{bid}: {len(mp['locations'])} scan positions; inspecting {len(positions)}"
          + (" (cached positions only)" if cached_positions_only else ""))
    dets, stop = [], None
    for k, pos in enumerate(positions, 1):
        log["positions"].append({"location_id": pos["location"]["id"], "reason": pos["reason"]})
        try:
            got, f = survey_position(bid, mesh, mp, pos, log, cache_only=cached_positions_only)
        except (gemini.GeminiError, CacheMiss) as e:  # every model failed (or cache-only miss): record it, move on
            log["positions"][-1]["error"] = str(e)[:300]
            print(f"  [{k}/{len(positions)}] {pos['reason']}: skipped ({str(e)[:120]})", flush=True)
            continue
        except (gemini.BillingError, spend.BudgetExceeded) as e:
            stop = log["stopped"] = str(e)[:300]
            print(f"  STOP at [{k}/{len(positions)}]: {stop}", flush=True)
            break
        flags.update(f)
        dets += got
        write_json(BUILDINGS / bid / "screening.json", flags)
        print(f"  [{k}/{len(positions)}] {pos['reason']}: {len(got)} items ({log['calls'][-1]['model']}"
              f"{', cached' if log['calls'][-1].get('cached') else ''})", flush=True)
    groups = merge(dets)
    relooked = 0
    for g in sorted(groups, key=lambda g: (bool(g[0].get("fabric")), g[0]["confidence"])):   # contents first
        if stop or relooked >= max_relooks or g[0]["confidence"] >= LOW_CONF:
            continue
        b = g[0]
        entry = {"label": b["label"], "category": b["category"], "from_location": b["location"]["id"],
                 "before": {"height_ft": [b["height_ft_low"], b["height_ft_high"]], "confidence": b["confidence"],
                            "how": b["how"]}}
        n_calls = len(log["calls"])
        try:
            r = relook(bid, mesh, mp, g, log, flags)
        except (gemini.GeminiError, CacheMiss) as e:
            log["relooks"].append({**entry, "error": str(e)[:300]})
            continue
        except (gemini.BillingError, spend.BudgetExceeded) as e:
            stop = log["stopped"] = str(e)[:300]
            break
        relooked += 1
        if r:
            g.insert(0, r) if r["confidence"] > b["confidence"] else g.append(r)
            entry["neighbour"] = {"location_id": r["location"]["id"], "face": r["face"], "box": r["box"],
                                  "height_ft": [r["height_ft_low"], r["height_ft_high"]], "confidence": r["confidence"],
                                  "how": r["how"], "visual_estimate_ft": r["visual"], "model": r["model"]}
        else:
            c = log["calls"][-1] if len(log["calls"]) > n_calls else None
            entry["neighbour"] = ({"pano": c["pano"], "found": c.get("found"), "complete": c.get("complete"),
                                   "result": "inconclusive: record unchanged"} if c
                                  else "no neighbouring position sees this point on a side face")
        entry["after"] = {"height_ft": [g[0]["height_ft_low"], g[0]["height_ft_high"]], "confidence": g[0]["confidence"],
                          "how": g[0]["how"], "kept": "neighbour view" if g[0] is not b else "original view"}
        log["relooks"].append(entry)
        print(f"  relook {b['label']!r}: {entry['before']} -> {entry['after']}", flush=True)
    groups, log["merged_after_relook"] = remerge(groups)
    for n in log["merged_after_relook"]:
        print(f"  {n}", flush=True)
    write_json(BUILDINGS / bid / "screening.json", flags)
    assets, geometry = [], {}
    for n, g in enumerate(sorted(groups, key=lambda g: (g[0]["room_id"], g[0]["height_ft_low"], g[0]["label"])), 1):
        best = g[0]
        room = rooms.get(best["room_id"]) or {}
        label = room.get("label") or (best["room_type"].strip().title() if best["room_type"] else "Unlabelled room")
        fabric = bool(best.get("fabric"))
        category = best["category"]
        va = classes.value_class(best["value_class"])
        span = next((d["span_ft"] for d in g if d.get("span_ft")), None)
        notes = best.get("conf_notes") or []
        extra = (FABRIC_NOTE if fabric else "") + (VEHICLE_NOTE if classes.is_movable(va["id"]) else "") + \
            (f" Confidence lowered: {', '.join(notes)}." if notes else "")
        asset = {"id": f"{bid}-a{n}", "building_id": bid, "matterport_model_id": mp["model_id"],
                 "floor_id": (best["location"].get("floor") or {}).get("id"),
                 "room_id": best["room_id"] if best["room_id"] != "none" else None, "room": label,
                 "location_id": best["location"]["id"], "category": category, "label": best["label"],
                 "height_ft_low": best["height_ft_low"], "height_ft_high": best["height_ft_high"],
                 "confidence": round(best["confidence"], 2), "value_usd_low": va["low"], "value_usd_high": va["high"],
                 "value_basis": va["id"],
                 "position": {k: round(v, 3) for k, v in best["position"].items()} if best["position"] else None,
                 "evidence": f"{best['evidence']} Height {best['how']}." + extra,
                 "image_ref": image_ref(bid, best["pano"]["id"], best["face"], best["box"]),
                 "observations": [observation(bid, d) for d in g], "source": "vision"}
        validate("asset", asset)
        assets.append(asset)
        geometry[asset["id"]] = {"span_ft": span, "value_class": va["id"]}
    write_json(BUILDINGS / bid / "assets.json", assets)
    write_json(BUILDINGS / bid / "asset_geometry.json", geometry)     # object height from the mesh, for the loss model
    log["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(BUILDINGS / bid / "survey_log.json", log)
    if stop:
        raise Stop(stop)
    return assets


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("building")
    ap.add_argument("--max-positions", type=int, default=20)
    ap.add_argument("--max-relooks", type=int, default=8)
    ap.add_argument("--cached-positions-only", action="store_true",
                    help="read only positions already in the cache (re-looks may still call the model)")
    a = ap.parse_args()
    try:
        out = run(a.building, a.max_positions, a.max_relooks, a.cached_positions_only)
    except Stop as e:
        raise SystemExit(f"{a.building}: stopped, partial assets written: {e}")
    print(f"{a.building}: {len(out)} assets")
