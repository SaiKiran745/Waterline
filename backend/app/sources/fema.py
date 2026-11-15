"""FEMA National Flood Hazard Layer (public ArcGIS REST, no key). -9999 means no value."""
import time
from datetime import datetime, timezone

import httpx

from app.sources.cache import cached_json

BASE = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"


def _point_query(layer: int, lat: float, lng: float, fields: str) -> dict:
    url = f"{BASE}/{layer}/query"
    params = {"geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "false", "f": "json"}

    def send():
        r = httpx.get(url, params=params, timeout=120)
        return r.status_code, r.json()
    rec = cached_json("fema", "GET", url, send, params=params)
    feats = (rec["response"] or {}).get("features") or []
    return feats[0]["attributes"] if feats else {}


def flood_zone(lat: float, lng: float) -> dict:
    """Layer 28 Flood Hazard Zones + layer 3 FIRM panel. Returns contract-ready fields."""
    z = _point_query(28, lat, lng, "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DFIRM_ID")
    p = _point_query(3, lat, lng, "DFIRM_ID,FIRM_PAN,EFF_DATE")
    eff = p.get("EFF_DATE")
    eff_s = datetime.fromtimestamp(eff / 1000, tz=timezone.utc).date().isoformat() if eff else None
    sfha = z.get("SFHA_TF")
    return {
        "in_mapped_flood_zone": None if sfha is None else sfha == "T",
        "flood_zone": z.get("FLD_ZONE"),
        "flood_zone_subtype": z.get("ZONE_SUBTY") or None,
        "flood_zone_source": (f"FEMA NFHL, panel {p.get('FIRM_PAN')}, effective {eff_s}" if p else "FEMA NFHL") if z else None,
    }


def nearby(layer: int, lat: float, lng: float, fields: str, distance_m: float) -> list[dict]:
    """Features of an NFHL layer within distance_m of a point, with geometry in WGS84 (cached)."""
    url = f"{BASE}/{layer}/query"
    params = {"geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "distance": distance_m, "units": "esriSRUnit_Meter",
              "outFields": fields, "returnGeometry": "true", "outSR": 4326, "f": "json"}

    def send():
        """Up to 3 tries; a non-JSON or error answer is returned as status 599 so it is never cached."""
        for i in range(3):
            try:
                r = httpx.get(url, params=params, timeout=180)
                if r.status_code == 200:
                    return 200, r.json()
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(2 + 3 * i)
        return 599, None
    rec = cached_json("fema", "GET", url, send, params=params)
    return (rec["response"] or {}).get("features") or [] if rec["status"] == 200 else []
