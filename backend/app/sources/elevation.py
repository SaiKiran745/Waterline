"""USGS Elevation Point Query Service (public, no key). Not a door threshold: ground in front of it.

Vertical datum NAVD 88 (EPQS interpolates 3DEP; docs/DATA_NOTES.md section 9). Overall RMSE 0.53 m (USGS FAQ).
"""
import time

import httpx

from app.sources.cache import cached_json

URL = "https://epqs.nationalmap.gov/v1/json"


def ground_elevation_ft(lat: float, lng: float) -> float | None:
    params = {"x": lng, "y": lat, "wkid": 4326, "units": "Feet", "includeDate": "false"}

    def send():
        """Up to 3 tries; a non-JSON or error answer is returned as status 599 so it is never cached."""
        for i in range(3):
            try:
                r = httpx.get(URL, params=params, timeout=httpx.Timeout(45.0, connect=15.0))
                if r.status_code == 200:
                    return 200, r.json()
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(2 + 3 * i)
        return 599, None
    rec = cached_json("usgs", "GET", URL, send, params=params)
    value = (rec["response"] or {}).get("value") if rec["status"] == 200 else None
    return round(float(value), 2) if isinstance(value, (int, float)) else None
