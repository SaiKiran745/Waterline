"""Central estimate and 80% interval by simulation (contracts v1.3; judge feedback 2026-11-14).

The old low-high sums add every item's low value (with the top of its height range) or every item's high value (with
the bottom): a worst-case interval far wider than any likely outcome. Here each uncertain input is drawn instead,
4,000 times with a fixed seed, and the 10th, 50th and 90th percentiles are reported. The old sums stay as extreme
bounds (X-EXTREME-BOUNDS) in the assumptions list only.

- Value (C-MC-VALUE): lognormal per item, value_usd_low and value_usd_high as its 10th and 90th percentiles. Items of
  one value class share part of their error (C-MC-CLASS-CORR, correlation rho between log-values).
- Height (C-MC-HEIGHT): the lowest vulnerable point is uniform within [height_ft_low, height_ft_high], per item.
- Structure (C-MC-STRUCT): the Hazus damage % sits at the same relative place between the low and high curves at
  every depth within one draw, independent of contents.
- Every draw is evaluated at every depth (common random numbers): each draw's loss never falls as depth rises, so
  neither do its percentiles. Draws are keyed by asset id, value class and building id, never by list position, so
  correcting or deleting one asset does not reshuffle the others.

Measured (no dollar assumption): how many items the water reaches at each step and the threshold depths come from
the item heights alone (mesh where it resolves the item, otherwise the visual estimate).

Standard method: the Hazus 6.1 default contents and inventory functions for the occupancy, applied to the same
simulated item values (like for like), shown beside Waterline's figure and never used in it.
"""
import math
import zlib
from functools import lru_cache

import numpy as np

from app.loss import model

Z90 = 1.2815515655446004          # standard normal 90th percentile
NOT_CONTENTS = ("A-FIN", "V-VEHICLE")
CRITICAL_SYSTEMS = {"electrical": "electrical gear", "it": "IT equipment"}
SAME_BAND = (0.8, 1.25)            # "about the same" when ours / standard is within this band


def _param(aid: str, key: str):
    return model.assumption_by_id(aid)[key]


def draws() -> int:
    return int(_param("C-MC-DRAWS", "draws"))


def rho() -> float:
    return float(_param("C-MC-CLASS-CORR", "rho"))


def _rng(key: str, salt: int) -> np.random.Generator:
    return np.random.default_rng([int(_param("C-MC-DRAWS", "seed")), zlib.crc32(key.encode()), salt])


@lru_cache(maxsize=4096)
def _normal(key: str) -> np.ndarray:
    z = _rng(key, 0).standard_normal(draws())
    z.flags.writeable = False
    return z


@lru_cache(maxsize=4096)
def _uniform(key: str) -> np.ndarray:
    u = _rng(key, 1).random(draws())
    u.flags.writeable = False
    return u


def _phi(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.array([math.erf(x / math.sqrt(2.0)) for x in z]))


@lru_cache(maxsize=4096)
def _value_col(asset_id: str, value_basis: str, lo: float, hi: float) -> np.ndarray:
    n = draws()
    if hi <= 0:
        col = np.zeros(n)
    elif hi <= lo:
        col = np.full(n, float(lo))
    else:
        r = rho()
        z = math.sqrt(r) * _normal(f"class:{value_basis}") + math.sqrt(1.0 - r) * _normal(f"value:{asset_id}")
        if lo <= 0:
            col = hi * _phi(z)
        else:
            mu, s = (math.log(lo) + math.log(hi)) / 2.0, (math.log(hi) - math.log(lo)) / (2.0 * Z90)
            col = np.exp(mu + s * z)
    col.flags.writeable = False
    return col


def _height_col(asset_id: str, lo: float, hi: float) -> np.ndarray:
    return lo + _uniform(f"height:{asset_id}") * max(hi - lo, 0.0)


def is_contents(a: dict) -> bool:
    return a["value_basis"] not in NOT_CONTENTS


class Draws:
    """The simulated inputs for one building's assets: values V and lowest points H (draws x assets)."""

    def __init__(self, building: dict, assets: list[dict], structure_fn=None):
        self.building, self.assets = building, assets
        n = draws()
        spans = model._spans(assets)
        self.crit = np.array([model.critical_ft(a, spans.get(a["id"])) for a in assets]) if assets else np.zeros(0)
        self.V = (np.column_stack([_value_col(a["id"], a["value_basis"], float(a["value_usd_low"]), float(a["value_usd_high"]))
                                   for a in assets]) if assets else np.zeros((n, 0)))
        self.H = (np.column_stack([_height_col(a["id"], float(a["height_ft_low"]), float(a["height_ft_high"])) for a in assets])
                  if assets else np.zeros((n, 0)))
        self.u = _uniform(f"structure:{building.get('id')}")
        self.structure_fn = structure_fn or (lambda d: model.structure_loss(building, d)[:2])

    def contents(self, depth: float) -> np.ndarray:
        """Loss per draw and asset at a depth (draws x assets)."""
        if depth <= 0 or not self.assets:
            return np.zeros(self.V.shape)
        return self.V * np.clip((depth - self.H) / self.crit, 0.0, 1.0)

    def structure(self, depth: float) -> np.ndarray:
        lo, hi = self.structure_fn(depth)
        return lo + self.u * (hi - lo)

    def standard(self, depth: float) -> np.ndarray | None:
        """Hazus-style contents loss per draw: the Hazus default % at this depth times the same simulated values."""
        pct = standard_pct(self.building, self.assets, depth)
        return None if pct is None else self.V @ pct


def standard_functions(building: dict) -> dict | None:
    occ = model.occupancy_for(building)
    std = model.curves().get("standard_contents", {}).get("occupancies", {})
    return std.get(occ) if occ else None


def standard_pct(building: dict, assets: list[dict], depth: float) -> np.ndarray | None:
    f = standard_functions(building)
    if f is None:
        return None
    if depth <= 0:
        return np.zeros(len(assets))
    def at(kind):
        c = f[kind]
        return float(np.interp(min(depth, c["depth_ft"][-1]), c["depth_ft"], c["pct"])) / 100.0
    pc, pi = at("contents"), at("inventory")
    return np.array([(pi if a["category"] == "inventory" else pc) if is_contents(a) else 0.0 for a in assets])


def sig(x: float, digits: int = 3) -> int:
    """Round a simulated dollar figure to 3 significant figures: the simulation is not precise to the dollar."""
    if x <= 0:
        return 0
    return int(round(x, -int(math.floor(math.log10(x))) + digits - 1))


def pct3(x: np.ndarray) -> tuple[float, float, float]:
    p = np.percentile(x, [10, 50, 90])
    return float(p[0]), float(p[1]), float(p[2])


def _clamp(p: tuple[float, float, float], lo: float, hi: float) -> tuple[float, float, float]:
    return tuple(min(max(x, lo), hi) for x in p)


def summarise(d: Draws, depth: float, top_n: int = 5, clamp: bool = True) -> dict:
    """Median and 80% interval for contents, structure and total at one depth, each asset's expected loss, the top
    contributors, and the standard-method figure (raw floats; callers round for display).

    clamp: keep each percentile inside the extreme bounds. Where one item with a fixed height drives the loss, its
    true 10th percentile is exactly the low bound and 4,000 draws land within about 1% either side of it; the clamp
    removes that sampling noise (tested: raw percentiles are never more than 3% outside)."""
    m = d.contents(depth)
    c = m.sum(axis=1) if m.size else np.zeros(draws())
    s = d.structure(depth)
    expected = m.mean(axis=0) if m.size else np.zeros(0)
    total_expected = float(expected.sum())
    order = np.argsort(-expected, kind="stable")[:top_n] if expected.size else []
    top = [{"asset_id": d.assets[i]["id"], "expected_loss_usd": float(expected[i]),
            "share": float(expected[i] / total_expected) if total_expected > 0 else 0.0}
           for i in order if expected[i] > 0]
    std = d.standard(depth)
    out = {"contents": pct3(c), "structure": pct3(s), "total": pct3(c + s), "expected": expected, "top": top,
           "standard": pct3(std) if std is not None else None}
    if clamp:
        c_lo, c_hi = model.contents_loss(d.assets, depth)
        s_lo, s_hi = d.structure_fn(depth)
        out["contents"] = _clamp(out["contents"], c_lo, c_hi)
        out["structure"] = _clamp(out["structure"], s_lo, s_hi)
        out["total"] = _clamp(out["total"], c_lo + s_lo, c_hi + s_hi)
    return out


def contents_value(assets: list[dict]) -> tuple[int, int, int]:
    """Simulated total replacement value of the contents items: (10th percentile, median, 90th percentile)."""
    items = contents_items(assets)
    if not items:
        return 0, 0, 0
    v = np.column_stack([_value_col(a["id"], a["value_basis"], float(a["value_usd_low"]), float(a["value_usd_high"]))
                         for a in items]).sum(axis=1)
    lo, med, hi = pct3(v)
    return sig(lo), sig(med), sig(hi)


def expected_by_asset(building: dict, assets: list[dict], depth: float) -> dict:
    """Each asset's expected (mean) loss at a depth, rounded like every simulated figure; zero entries left out."""
    d = Draws(building, assets)
    m = d.contents(depth)
    return {a["id"]: sig(float(x)) for a, x in zip(assets, m.mean(axis=0) if m.size else []) if x > 0}


# ---------------------------------------------------------------- measured: no dollar assumption

def contents_items(assets: list[dict]) -> list[dict]:
    return [a for a in assets if is_contents(a)]


def in_water(assets: list[dict], depth: float) -> dict:
    """How many contents items the water reaches at a depth: count_low = water above the top of the item's height
    range (certainly reached), count_high = above the bottom (possibly reached). From item heights only."""
    items = contents_items(assets)
    n = len(items)
    lo = sum(1 for a in items if depth > 0 and depth >= a["height_ft_high"])
    hi = sum(1 for a in items if depth > 0 and depth >= a["height_ft_low"])
    return {"of": n, "count_low": lo, "count_high": hi,
            "share_low": round(lo / n, 3) if n else 0.0, "share_high": round(hi / n, 3) if n else 0.0}


def _kth(values: list[float], share: float) -> float | None:
    if not values:
        return None
    k = max(1, math.ceil(share * len(values)))
    return round(sorted(values)[k - 1], 2)


def thresholds(assets: list[dict]) -> dict:
    """Depths at which the water first reaches an item, half of them, 80% of them, and each critical system.
    Each is [earliest, latest]: earliest uses the bottom of each item's height range, latest the top."""
    items = contents_items(assets)
    measured = sum(1 for a in items if "measured from mesh" in (a.get("evidence") or ""))

    def band(share, group):
        a, b = _kth([x["height_ft_low"] for x in group], share), _kth([x["height_ft_high"] for x in group], share)
        return None if a is None else [a, b]

    systems = []
    for cat, name in CRITICAL_SYSTEMS.items():
        group = [a for a in items if a["category"] == cat]
        systems.append({"system": cat, "name": name, "items": len(group),
                        "first_reached_ft": band(1e-9, group)})
    return {"contents_items": len(items), "heights_from_mesh": measured, "heights_estimated": len(items) - measured,
            "first_loss_ft": band(1e-9, items), "half_items_ft": band(0.5, items), "most_items_ft": band(0.8, items),
            "critical_systems": systems}


# ---------------------------------------------------------------- standard-method comparison

def verdict(ours: float, standard: float) -> tuple[str, float | None]:
    if standard <= 0:
        return ("higher" if ours > 0 else "about the same"), None
    r = ours / standard
    return ("lower" if r < SAME_BAND[0] else "higher" if r > SAME_BAND[1] else "about the same"), round(r, 2)


def standard_method(building: dict, assets: list[dict], rows: list[dict]) -> dict | None:
    """The Hazus-style comparison block: citation, value basis, the figures at 1, 2, 4 and 6 ft, and plain sentences."""
    f = standard_functions(building)
    if f is None:
        return None
    occ = model.occupancy_for(building)
    std = model.curves()["standard_contents"]
    at = {r["depth_ft"]: r for r in rows}
    compare = []
    for dep in (1.0, 2.0, 4.0, 6.0):
        r = at.get(dep)
        if r is None:
            continue
        v, ratio = verdict(r["loss_usd_median"], r["standard_contents_usd_median"])
        compare.append({"depth_ft": dep, "ours_median_usd": r["loss_usd_median"],
                        "standard_median_usd": r["standard_contents_usd_median"], "ratio": ratio, "verdict": v})
    items = contents_items(assets)
    value = sum(math.sqrt(a["value_usd_low"] * a["value_usd_high"]) if a["value_usd_low"] > 0 else a["value_usd_high"] / 2
                for a in items)
    low_value = sum(math.sqrt(a["value_usd_low"] * a["value_usd_high"]) if a["value_usd_low"] > 0 else a["value_usd_high"] / 2
                    for a in items if a["height_ft_low"] < 1.0)
    share_low = low_value / value if value else 0.0
    words = "; ".join(f"at {c['depth_ft']:g} ft ours is {c['verdict']}"
                      + (f" ({c['ratio']:.1f} times)" if c["ratio"] is not None and c["verdict"] != "about the same" else "")
                      for c in compare)
    c_fn, i_fn = f["contents"], f["inventory"]
    return {
        "method": f"Hazus 6.1 default contents and inventory depth-damage functions for {occ}",
        "functions": [{"kind": k, "function_id": v["function_id"], "description": v["description"], "source": v["source"],
                       "pct_at_1_2_4_6_ft": [v["pct"][1], v["pct"][2], v["pct"][4], v["pct"][6]]} for k, v in f.items()],
        "citation": std["source"],
        "source_url": std["source_url"],
        "value_basis": "The same simulated item values as Waterline's contents loss (like for like): the Hazus "
                       "inventory function for stock, the contents function for everything else; road vehicles and "
                       "building fabric are excluded from both.",
        "compare": compare,
        "statement": (f"Against the Hazus-style figure on the same item values, {words}." if compare else ""),
        "why_shapes_differ": (
            f"Hazus applies a building-average percentage from the first inch of water ({c_fn['pct'][1]:g}% of contents "
            f"and {i_fn['pct'][1]:g}% of inventory at 1 ft for {occ}) and never reaches 100% "
            f"({c_fn['pct'][8]:g}% and {i_fn['pct'][8]:g}% at 8 ft), because a building's contents include things stored "
            f"above the water. Waterline prices only the items the survey saw, each from its own lowest vulnerable "
            f"point: nothing is lost until the water reaches an item, and an item is a total loss once the water is its "
            f"critical height above that point. In this building {share_low:.0%} of the surveyed contents value (at "
            f"the middle of each range) sits in items whose lowest vulnerable part may be below 1 ft."),
        "share_of_value_below_1ft": round(share_low, 3),
    }


# ---------------------------------------------------------------- extreme bounds (the old sums)

def extreme_entry(building: dict, assets: list[dict], depth: float, s_lo: float, s_hi: float) -> dict:
    c_lo, c_hi = model.contents_loss(assets, depth)
    return {"id": "X-EXTREME-BOUNDS",
            "text": (f"Extreme bounds at {depth:g} ft, for reference only: every item at the low end of its value range "
                     f"and the top of its height range gives contents ${c_lo:,.0f}, structure ${s_lo:,.0f}, total "
                     f"${c_lo + s_lo:,.0f}; every item at the high end and the bottom gives contents ${c_hi:,.0f}, "
                     f"structure ${s_hi:,.0f}, total ${c_hi + s_hi:,.0f}. Both are far less likely than the 80% "
                     f"interval, because items do not all err the same way."),
            "source": "Waterline method: the sums reported as the range before contracts v1.3", "placeholder": False}


def method_entries() -> list[dict]:
    return [model.as_entry(model.assumption_by_id(i)) for i in ("C-MC-VALUE", "C-MC-CLASS-CORR", "C-MC-HEIGHT",
                                                                 "C-MC-STRUCT", "C-MC-DRAWS")]
