"""Map cached source data into the Building contract (contracts/building.schema.json) and read it back."""
import json
from functools import lru_cache

from jsonschema import Draft202012Validator, FormatChecker

from app.config import BUILDINGS, CONTRACTS
from app.sources.cache import CacheMiss, write_json
from app.sources.registry import load_shortlist


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    schema = json.loads((CONTRACTS / f"{name}.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name: str, obj) -> None:
    errors = list(validator(name).iter_errors(obj))
    if errors:
        raise ValueError(f"{name} violates contract: " + "; ".join(f"{list(e.path)}: {e.message[:120]}" for e in errors[:5]))


def assemble(bid: str) -> dict:
    parts = json.loads((BUILDINGS / bid / "parts.json").read_text())
    c, mp, vx, fz = parts["costar"], parts["matterport"], parts["vexcel"], parts["fema"]
    value = c.get("value") or {}
    ortho = vx["images"].get("ortho") or {}
    scan_area = round(mp["scan_area_sqft"], 1) if mp.get("scan_area_sqft") else None
    building = {
        "id": bid,
        "name": c["name"],
        "address": c["address"],
        "lat": c["lat"], "lng": c["lng"],
        "property_type": c["property_type"], "property_subtype": c["property_subtype"],
        "size_sqft": c["size_sqft"], "size_basis": "GBA",
        "year_built": c["year_built"], "stories": c["stories"],
        "tenants": c["tenants"],
        "value_usd": value.get("value_usd"),
        "improvement_value_usd": value.get("improvement_value_usd"),
        "value_as_of": value.get("value_as_of"),
        "value_source": f"CoStar sale comp, {value['basis']}" if value else None,
        "loading_docks_external": c["loading_docks_external"],
        "drive_in_bays": c["drive_in_bays"],
        "matterport_model_id": mp["model_id"],
        "matterport_model_ids": c["matterport_model_ids"],
        "scan_area_sqft": scan_area,
        "scan_coverage": round(min(scan_area / c["size_sqft"], 1.0), 3) if scan_area and c["size_sqft"] else None,
        "in_mapped_flood_zone": fz["in_mapped_flood_zone"],
        "flood_zone": fz["flood_zone"],
        "flood_zone_subtype": fz["flood_zone_subtype"],
        "flood_zone_source": fz["flood_zone_source"],
        "ground_elevation_ft": parts["usgs_ground_elevation_ft"],
        "ground_elevation_source": "USGS EPQS (context only; vertical datum not stated)" if parts["usgs_ground_elevation_ft"] is not None else None,
        "aerial_collection": ortho.get("collection"),
        "aerial_capture_date": ortho.get("capture_date"),
    }
    validate("building", building)
    write_json(BUILDINGS / bid / "building.json", building)
    return building


def get_survey_assets(bid: str) -> list[dict]:
    """The survey's own output, before human corrections."""
    path = BUILDINGS / bid / "assets.json"
    return json.loads(path.read_text()) if path.exists() else []


def get_assets(bid: str) -> list[dict]:
    """Survey assets with human corrections applied (app/corrections.py)."""
    from app import corrections
    return corrections.apply(bid, get_survey_assets(bid))


def get_entry_points(bid: str) -> list[dict]:
    path = BUILDINGS / bid / "entry_points.json"
    return json.loads(path.read_text()) if path.exists() else []


def get_building(bid: str) -> dict:
    path = BUILDINGS / bid / "building.json"
    if not path.exists():
        raise CacheMiss(f"no cached building record for {bid}: run `python -m app.sources.pull`")
    return json.loads(path.read_text())


def list_buildings() -> list[dict]:
    """Shortlisted buildings in letter order (ranking by loss arrives with the loss model in Phase 4)."""
    return [get_building(e["building_id"]) for e in load_shortlist()]


def building_ids() -> set[str]:
    try:
        return {e["building_id"] for e in load_shortlist()}
    except CacheMiss:
        return set()
