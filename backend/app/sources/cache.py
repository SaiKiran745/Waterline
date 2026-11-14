"""Request-keyed cache for every external call.

JSON responses go to data/cache/http/<source>/<key>.json, keyed by method, URL, params and body.
Secrets are never part of the key or the stored record: callers pass them only in headers or auth.
Binary downloads go to an explicit path (for example under data/cache/media/).
With DEMO_MODE=1 nothing is fetched: a missing entry raises CacheMiss.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import CACHE, demo_mode

HTTP_CACHE = CACHE / "http"


class CacheMiss(RuntimeError):
    """Raised in DEMO_MODE when a response is not in the cache."""


def request_key(method: str, url: str, params: dict | None = None, body: Any = None) -> str:
    canonical = json.dumps({"m": method.upper(), "u": url, "p": params or {}, "b": body}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def cached_json(source: str, method: str, url: str, send: Callable[[], tuple[int, Any]], *,
                params: dict | None = None, body: Any = None, refresh: bool = False) -> dict:
    """Return {"status": int, "response": Any}. `send` performs the real call and returns (status, parsed body).

    refresh=True skips reading the cache (used for responses holding short-lived signed URLs) but still writes it.
    In DEMO_MODE refresh is ignored and only the cache is read.
    """
    path = HTTP_CACHE / source / f"{request_key(method, url, params, body)}.json"
    if path.exists() and (not refresh or demo_mode()):
        return json.loads(path.read_text())
    if demo_mode():
        raise CacheMiss(f"DEMO_MODE=1: no cached response for {source} {method} {url} (key {path.stem})")
    status, parsed = send()
    record = {"source": source, "method": method.upper(), "url": url, "params": params, "body": body,
              "status": status, "fetched_at": datetime.now(timezone.utc).isoformat(), "response": parsed}
    if status < 500 and status != 429:
        _atomic_write(path, json.dumps(record).encode())
    return record


def cached_file(dest: Path, fetch: Callable[[], bytes]) -> Path:
    """Download once to `dest`. In DEMO_MODE a missing file raises CacheMiss."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    if demo_mode():
        raise CacheMiss(f"DEMO_MODE=1: missing cached file {dest}")
    _atomic_write(dest, fetch())
    return dest


def write_json(path: Path, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, indent=1, default=str).encode())
