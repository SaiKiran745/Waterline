"""Human corrections to surveyed assets (AGENTS.md section 10, behaviour 6).

The survey output (assets.json) is never edited. Corrections are an append-only log in
data/cache/buildings/<id>/corrections.json, applied on read by `apply()`, so a correction survives a re-survey
and can be undone by removing its record. Every correction is also written to the agent's memory
(app.agent.memory) so the agent can apply the same correction to similar assets and say so.
"""
import json
import uuid
from datetime import datetime, timezone

from app.config import BUILDINGS
from app.loss import model as loss_model
from app.sources.cache import write_json

PATCHABLE = {"label", "category", "height_ft_low", "height_ft_high", "room"}
CATEGORIES = {"electrical", "it", "hvac", "inventory", "equipment", "furniture", "finishes", "other"}


class CorrectionError(ValueError):
    pass


def _path(bid: str):
    return BUILDINGS / bid / "corrections.json"


def load(bid: str) -> list[dict]:
    p = _path(bid)
    return json.loads(p.read_text()) if p.exists() else []


def _patched(asset: dict, changes: dict, rec: dict) -> dict:
    a = {**asset, **changes}
    if "category" in changes:
        va = loss_model.asset_assumption(a["category"])
        a.update(value_usd_low=va["low"], value_usd_high=va["high"], value_basis=va["id"])
    if {"height_ft_low", "height_ft_high"} & changes.keys():
        a["confidence"] = 1.0
    who = "a human reviewer" if rec["by"] == "human" else f"the agent, applying correction {rec['propagated_from']}"
    a["evidence"] = (f"{asset['evidence']} Corrected by {who}: "
                     + "; ".join(f"{k} {asset.get(k)!r} -> {v!r}" for k, v in changes.items())
                     + (f" ({rec['note']})" if rec.get("note") else "") + ".")
    a["source"] = "human" if rec["by"] == "human" else "human-propagated"
    return a


def apply(bid: str, assets: list[dict]) -> list[dict]:
    out = {a["id"]: a for a in assets}
    for rec in load(bid):
        if rec["asset_id"] not in out:
            continue
        if rec["action"] == "delete":
            del out[rec["asset_id"]]
        else:
            out[rec["asset_id"]] = _patched(out[rec["asset_id"]], rec["changes"], rec)
    return list(out.values())


def _validate_changes(asset: dict, changes: dict) -> dict:
    bad = set(changes) - PATCHABLE
    if bad:
        raise CorrectionError(f"cannot change {sorted(bad)}; allowed: {sorted(PATCHABLE)}")
    if not changes:
        raise CorrectionError("no changes given")
    c = dict(changes)
    for k in ("height_ft_low", "height_ft_high"):
        if k in c:
            try:
                c[k] = round(float(c[k]), 2)
            except (TypeError, ValueError):
                raise CorrectionError(f"{k} must be a number")
            if not 0 <= c[k] <= 30:
                raise CorrectionError(f"{k} must be between 0 and 30 ft")
    lo = c.get("height_ft_low", asset["height_ft_low"])
    hi = c.get("height_ft_high", asset["height_ft_high"])
    if lo > hi:
        raise CorrectionError(f"height_ft_low {lo} is above height_ft_high {hi}")
    if "category" in c and c["category"] not in CATEGORIES:
        raise CorrectionError(f"category must be one of {sorted(CATEGORIES)}")
    for k in ("label", "room"):
        if k in c and (not isinstance(c[k], str) or not c[k].strip()):
            raise CorrectionError(f"{k} must be a non-empty string")
    return c


def record(bid: str, current: list[dict], asset_id: str, action: str, changes: dict | None = None,
           note: str | None = None, by: str = "human", propagated_from: str | None = None) -> dict:
    """Validate and append one correction. `current` is the asset list with earlier corrections applied."""
    asset = next((a for a in current if a["id"] == asset_id), None)
    if asset is None:
        raise KeyError(asset_id)
    rec = {"id": f"corr-{uuid.uuid4().hex[:8]}", "ts": datetime.now(timezone.utc).isoformat(), "building_id": bid,
           "asset_id": asset_id, "action": action, "by": by, "note": (note or "").strip()[:500] or None,
           "propagated_from": propagated_from,
           "before": {k: asset.get(k) for k in ("label", "category", "room", "height_ft_low", "height_ft_high",
                                                 "confidence", "value_basis")}}
    if action == "patch":
        rec["changes"] = _validate_changes(asset, changes or {})
        from app.buildings import validate          # the corrected asset must still match contracts/
        try:
            validate("asset", _patched(asset, rec["changes"], rec))
        except Exception as e:                       # jsonschema.ValidationError
            raise CorrectionError(f"corrected asset would not match the Asset contract: {str(e).splitlines()[0]}")
    elif action != "delete":
        raise CorrectionError(f"unknown action {action}")
    log = load(bid)
    log.append(rec)
    write_json(_path(bid), log)
    from app.agent import memory
    memory.record_correction(rec, asset)
    return rec


def similar(assets: list[dict], asset: dict) -> list[dict]:
    """Assets the same correction plausibly applies to: same category and a shared label word (agent tool)."""
    words = {w for w in asset["label"].lower().replace("-", " ").split() if len(w) > 3}
    return [a for a in assets if a["id"] != asset["id"] and a["category"] == asset["category"]
            and words & set(a["label"].lower().replace("-", " ").split())]
