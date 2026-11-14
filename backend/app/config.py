"""Paths and settings. Reads the repo-root .env into os.environ without overriding values already set."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = DATA / "cache"
MEDIA = CACHE / "media"
TOOLKIT = DATA / "toolkit"
KIT = TOOLKIT / "costar-hackathon-kit"
CONTRACTS = ROOT / "contracts"
FIXTURES = CONTRACTS / "fixtures"
SHORTLIST = CACHE / "shortlist.json"
BUILDINGS = CACHE / "buildings"

FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def demo_mode() -> bool:
    """DEMO_MODE=1: read only from data/cache/, never touch the network, fail loudly on a miss."""
    return os.environ.get("DEMO_MODE", "0").strip() == "1"


def secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is not set in .env")
    return value
