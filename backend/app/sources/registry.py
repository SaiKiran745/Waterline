"""The shortlist (data/cache/shortlist.json, git-ignored): letter -> CoStar property and Matterport model."""
import json

from app.config import SHORTLIST
from app.sources.cache import CacheMiss


def load_shortlist() -> list[dict]:
    if not SHORTLIST.exists():
        raise CacheMiss(f"{SHORTLIST} is missing: run `python -m app.sources.shortlist` first")
    return sorted(json.loads(SHORTLIST.read_text()), key=lambda e: e["letter"])
