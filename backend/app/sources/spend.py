"""Gemini spend ledger and hard budget (data/cache/spend.json).

Prices are the published Standard-tier rates, per 1M tokens, checked 2026-11-14 at
https://aistudio.google.com/docs/pricing (redirected from ai.google.dev/gemini-api/docs/pricing):
gemini-3.6-flash input $0.75, output $3.75 "including thinking tokens", valid through 2026-12-31.
Text and image input share one price. A model without a price here is refused, so spend is never unknown.

- record(): prices one billed response (prompt tokens at the input rate; candidates + thoughts at the output rate).
- check(): before a call, refuses (BudgetExceeded) if total + the costliest call so far would pass the budget.
- Agent (LangChain) calls must report through record() too, so one ledger covers vision and the orchestrator.
"""
import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import CACHE

LEDGER = CACHE / "spend.json"
PRICES_PER_M = {"gemini-3.6-flash": {"input": 0.75, "output": 3.75},          # valid to 2026-12-31
                "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50}}     # no date condition listed
PRICE_SOURCE = "https://aistudio.google.com/docs/pricing (Standard tier, checked 2026-11-14)"
DEFAULT_BUDGET_USD = 3.0
DEFAULT_WARN_USD = None
FIRST_CALL_ESTIMATE_USD = 0.02     # used by check() until a real call has been priced


class BudgetExceeded(RuntimeError):
    pass


def budget() -> float:
    return float(os.environ.get("GEMINI_BUDGET_USD") or DEFAULT_BUDGET_USD)


def warn_at() -> float | None:
    v = os.environ.get("GEMINI_WARN_USD")
    return float(v) if v else DEFAULT_WARN_USD


@contextmanager
def _locked():
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _read() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"started_at": datetime.now(timezone.utc).isoformat(), "budget_usd": budget(),
            "prices_per_million_tokens": PRICES_PER_M, "price_source": PRICE_SOURCE,
            "note": "Starts at the 2026-11-14 credit top-up; earlier calls were paid from the previous credits.",
            "total_usd": 0.0, "calls": []}


def _write(d: dict) -> None:
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    tmp.replace(LEDGER)


def cost(model: str, usage: dict) -> float:
    if model not in PRICES_PER_M:
        raise BudgetExceeded(f"no published price recorded for {model}: add it to spend.PRICES_PER_M first")
    p = PRICES_PER_M[model]
    out = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    return (usage.get("promptTokenCount") or 0) * p["input"] / 1e6 + out * p["output"] / 1e6


def check(tag: str, model: str | None = None) -> None:
    if model is not None and model not in PRICES_PER_M:
        raise BudgetExceeded(f"no published price recorded for {model}")
    with _locked():
        d = _read()
    worst = max((c["cost_usd"] for c in d["calls"]), default=FIRST_CALL_ESTIMATE_USD)
    if d["total_usd"] + worst > budget():
        raise BudgetExceeded(f"{tag}: spend ${d['total_usd']:.4f} + next call up to ${worst:.4f} "
                             f"would pass the ${budget():.2f} budget; ask before continuing")


def record(tag: str, model: str, usage: dict) -> float:
    c = cost(model, usage)
    with _locked():
        d = _read()
        d["calls"].append({"ts": datetime.now(timezone.utc).isoformat(), "tag": tag, "model": model,
                           "prompt_tokens": usage.get("promptTokenCount") or 0,
                           "output_tokens": usage.get("candidatesTokenCount") or 0,
                           "thoughts_tokens": usage.get("thoughtsTokenCount") or 0,
                           "cost_usd": round(c, 6)})
        before = d["total_usd"]
        d["total_usd"] = round(d["total_usd"] + c, 6)
        d["budget_usd"] = budget()
        w = warn_at()
        crossed = (w is not None and before < w <= d["total_usd"]
                   and (d.get("warned_at") or {}).get("warn_usd") != w)   # a new warning level warns again
        if crossed:
            d["warned_at"] = {"ts": datetime.now(timezone.utc).isoformat(), "total_usd": d["total_usd"], "warn_usd": w}
        _write(d)
    if crossed:
        import sys
        print(f"WARNING: Gemini spend ${d['total_usd']:.2f} passed the ${w:.2f} warning level "
              f"(budget ${budget():.2f})", file=sys.stderr, flush=True)
    return c


def summary() -> dict:
    d = _read()
    return {"total_usd": d["total_usd"], "budget_usd": d["budget_usd"], "calls": len(d["calls"])}
