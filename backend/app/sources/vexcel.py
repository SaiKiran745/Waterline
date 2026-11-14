"""Vexcel API 2.0 client (endpoints and parameters from the hackathon tutorial and quickstart).

Key goes only in the X-API-KEY header. WKT is POINT(lon lat) with srid 4326.
Images come back as bytes with metadata in XMP; we save both.
Elevation products (DSM/DTM) and calculated roof heights are deliberately not used (docs/DECISIONS.md).
"""
import json
import re
import time
from pathlib import Path

import httpx

from app.config import secret
from app.sources.cache import cached_file, cached_json, write_json

API = "https://api.vexcelgroup.com/v2"
LAYERS = "urban,urban-r,wide-area,urban-g"
OBLIQUES = ["oblique-north", "oblique-south", "oblique-east", "oblique-west"]


def _request(method: str, path: str, **kw) -> httpx.Response:
    for attempt in range(6):
        r = httpx.request(method, f"{API}/{path}", headers={"X-API-KEY": secret("VEXCEL_API_KEY")}, timeout=300, **kw)
        if r.status_code != 429:
            return r
        time.sleep(min(2 ** attempt, 30))
    return r


def get_json(path: str, params: dict) -> dict:
    def send():
        r = _request("GET", path, params=params)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"_non_json": r.text[:2000]}
    return cached_json("vexcel", "GET", f"{API}/{path}", send, params=params)


def post_image(path: str, body: dict, dest: Path) -> Path:
    def fetch():
        r = _request("POST", path, json=body)
        if not r.is_success:
            raise RuntimeError(f"Vexcel /{path} HTTP {r.status_code}: {r.text[:300]}")
        return r.content
    out = cached_file(dest, fetch)
    meta = dest.with_suffix(".meta.json")
    if not meta.exists():
        write_json(meta, {"endpoint": path, "request": body, "xmp": read_xmp(out)})
    return out


def read_xmp(path: Path) -> dict:
    raw = path.read_bytes()
    m = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", raw, re.S)
    if not m:
        return {}
    xmp = m.group(0).decode("utf-8", "replace")
    return {k.split(":", 1)[1]: v for k, v in re.findall(r"<(Vexcel:[A-Za-z0-9_-]+)>([^<]*)</\1>", xmp)}


def point_wkt(lat: float, lng: float) -> str:
    return f"POINT({lng} {lat})"


def geojson_to_wkt(g) -> str | None:
    if isinstance(g, str):
        return g
    ring = lambda r: "(" + ",".join(f"{x} {y}" for x, y, *_ in r) + ")"
    if g.get("type") == "Polygon":
        return "POLYGON(" + ",".join(ring(r) for r in g["coordinates"]) + ")"
    if g.get("type") == "MultiPolygon":
        return "MULTIPOLYGON(" + ",".join("(" + ",".join(ring(r) for r in p) + ")" for p in g["coordinates"]) + ")"
    return None


def property_extract(lat: float, lng: float) -> dict:
    return get_json("property/extract", {"wkt": point_wkt(lat, lng), "srid": 4326, "layer": LAYERS, "latest": "true",
                                         "include": "precomputed", "unit-system": "imperial"})


def oblique_coverage(wkt: str) -> dict:
    return get_json("oriented/collections", {"wkt": wkt, "srid": 4326, "layer": "urban", "product-type": "oblique",
                                             "include": "product-type,collection,last-capture-date"})


def ortho(wkt: str, dest: Path) -> Path:
    return post_image("ortho/extract", {"wkt": wkt, "srid": 4326, "layer": LAYERS, "buffer-meter": 10,
                                        "crop": "bounding_box", "image-format": "jpeg"}, dest)


def oblique(wkt: str, direction: str, dest: Path) -> Path:
    return post_image("oriented/extract", {"wkt": wkt, "srid": 4326, "layer": "urban", "product-type": direction,
                                           "rotation": "natural", "buffer-meter": 10, "crop": "bbox",
                                           "image-format": "jpeg/png"}, dest)


def newest_oblique_directions(coverage: dict) -> tuple[str | None, list[str]]:
    feats = (coverage.get("response") or {}).get("features") or [] if coverage.get("status") == 200 else []
    newest = max((f["properties"]["last-capture-date"] for f in feats), default=None)
    dirs = sorted({f["properties"]["product-type"] for f in feats if f["properties"]["last-capture-date"] == newest})
    return newest, [d for d in OBLIQUES if d in dirs]


def dumps(obj) -> str:
    return json.dumps(obj, indent=1)
