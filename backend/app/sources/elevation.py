"""USGS Elevation Point Query Service (public, no key). Context only: not a door threshold."""
import httpx

from app.sources.cache import cached_json

URL = "https://epqs.nationalmap.gov/v1/json"


def ground_elevation_ft(lat: float, lng: float) -> float | None:
    params = {"x": lng, "y": lat, "wkid": 4326, "units": "Feet", "includeDate": "false"}

    def send():
        r = httpx.get(URL, params=params, timeout=120)
        return r.status_code, r.json()
    rec = cached_json("usgs", "GET", URL, send, params=params)
    value = (rec["response"] or {}).get("value") if rec["status"] == 200 else None
    return round(float(value), 1) if isinstance(value, (int, float)) else None
