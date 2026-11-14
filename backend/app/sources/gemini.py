"""Gemini vision client (REST generateContent). Key only in the x-goog-api-key header, never in a URL or log.

- Model: GEMINI_MODEL, then GEMINI_FALLBACK_MODELS, used only on 503 / 5xx / timeout (overload, not refusal).
- 429: waits for the server's RetryInfo delay when given (else exponential backoff); a delay over MAX_WAIT_S
  means a spent quota, so that model is skipped until it resets. The quota id and limit are logged.
- Connection resets and other transport errors: retried twice with backoff, then the next model.
- Every response is cached by (prompt, schema, image hashes, model list); images themselves are not stored.
- Every attempt is appended to data/cache/gemini_calls.jsonl (model, status, latency) for rate-limit reporting.
"""
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import httpx

from app.config import CACHE, demo_mode, secret
from app.sources.cache import CacheMiss, write_json

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CALL_LOG = CACHE / "gemini_calls.jsonl"
CACHE_DIR = CACHE / "http" / "gemini"


DEADLINE_S = 180           # wall-clock limit per attempt (httpx's timeout is per read, not per request)
COOLDOWN_S = 600           # skip a model for this long after a timeout or 5xx
MAX_WAIT_S = 90            # a 429 asking for a longer wait means the quota is spent: move to the next model
_cooldown: dict[str, float] = {}
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


class GeminiError(RuntimeError):
    pass


def _post(url: str, headers: dict, body: dict) -> httpx.Response:
    fut = _pool.submit(httpx.post, url, headers=headers, json=body, timeout=httpx.Timeout(DEADLINE_S, connect=20))
    try:
        return fut.result(timeout=DEADLINE_S)
    except concurrent.futures.TimeoutError:
        raise httpx.TimeoutException("wall-clock deadline exceeded")


def models() -> list[str]:
    first = os.environ.get("GEMINI_MODEL", "").strip()
    rest = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
    return [m for m in [first] + rest if m]


def _log(**kw) -> None:
    CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CALL_LOG, "a") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **kw}) + "\n")


def _retry_delay(body: dict) -> float | None:
    for d in (body.get("error") or {}).get("details") or []:
        if "retryDelay" in d:
            m = re.match(r"([\d.]+)s", str(d["retryDelay"]))
            if m:
                return float(m.group(1))
    return None


def _quota(body: dict) -> list[dict]:
    """The QuotaFailure violations of a 429 (quota id, metric, limit value): no secrets in them."""
    out = []
    for d in (body.get("error") or {}).get("details") or []:
        for v in d.get("violations") or []:
            out.append({k: v.get(k) for k in ("quotaMetric", "quotaId", "quotaValue", "quotaDimensions") if k in v})
    return out


def generate_json(prompt_parts: list, schema: dict, *, tag: str, thinking: str = "low") -> dict:
    """prompt_parts: list of str (text) or bytes (JPEG). Returns {"data": parsed JSON, "model": model used, ...}."""
    img_hashes = [hashlib.sha256(p).hexdigest() for p in prompt_parts if isinstance(p, bytes)]
    texts = [p for p in prompt_parts if isinstance(p, str)]
    key = hashlib.sha256(json.dumps({"t": texts, "i": img_hashes, "s": schema, "m": models(), "k": thinking},
                                    sort_keys=True).encode()).hexdigest()[:32]
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return {**json.loads(path.read_text()), "cached": True}
    if demo_mode():
        raise CacheMiss(f"DEMO_MODE=1: no cached Gemini response for {tag} (key {key})")
    parts = [{"text": p} if isinstance(p, str) else {"inline_data": {"mime_type": "image/jpeg",
                                                                      "data": base64.b64encode(p).decode()}}
             for p in prompt_parts]
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                                 "thinkingConfig": {"thinkingLevel": thinking}}}
    headers = {"x-goog-api-key": secret("GEMINI_API_KEY")}
    errors = []
    candidates = [m for m in models() if _cooldown.get(m, 0) < time.time()] or models()[-1:]
    for model in candidates:
        for attempt in range(4):
            t0 = time.time()
            try:
                r = _post(URL.format(model=model), headers, body)
            except httpx.TimeoutException:
                _log(tag=tag, model=model, status="timeout", latency_s=round(time.time() - t0, 1))
                errors.append(f"{model}: timeout")
                _cooldown[model] = time.time() + COOLDOWN_S
                break                                    # overloaded: next model
            except httpx.TransportError as e:            # connection reset / dropped: retry, then next model
                _log(tag=tag, model=model, status="transport", error=type(e).__name__,
                     latency_s=round(time.time() - t0, 1))
                errors.append(f"{model}: {type(e).__name__}")
                if attempt < 2:
                    time.sleep(5 * 2 ** attempt)
                    continue
                break
            latency = round(time.time() - t0, 1)
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 429:
                wait = _retry_delay(j) or min(60, 5 * 2 ** attempt)
                _log(tag=tag, model=model, status=429, latency_s=latency, retry_after_s=wait, quota=_quota(j))
                if wait > MAX_WAIT_S:                    # quota exhausted (e.g. daily): skip this model until it resets
                    errors.append(f"{model}: 429 quota, retry in {wait:.0f}s")
                    _cooldown[model] = time.time() + wait
                    break
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                _log(tag=tag, model=model, status=r.status_code, latency_s=latency)
                errors.append(f"{model}: {r.status_code}")
                if attempt < 1:
                    time.sleep(8)
                    continue
                _cooldown[model] = time.time() + COOLDOWN_S
                break                                    # still overloaded: next model
            _log(tag=tag, model=model, status=r.status_code, latency_s=latency,
                 tokens=(j.get("usageMetadata") or {}).get("totalTokenCount"))
            if r.status_code != 200:
                raise GeminiError(f"{model} HTTP {r.status_code}: {str((j or {}).get('error'))[:300]}")
            cand = (j.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
            try:
                data = json.loads(text)
            except ValueError:
                errors.append(f"{model}: unparseable JSON ({cand.get('finishReason')})")
                break
            out = {"data": data, "model": model, "tag": tag, "usage": j.get("usageMetadata"),
                   "finish_reason": cand.get("finishReason"), "fetched_at": datetime.now(timezone.utc).isoformat()}
            write_json(path, out)
            return out
    raise GeminiError(f"all models failed for {tag}: {errors}")
