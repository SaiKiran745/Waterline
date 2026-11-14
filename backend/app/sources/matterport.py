"""Matterport Model API client: read-only, server-side only.

Auth (developers.matterport.com/api): HTTP Basic, Token ID as username (MATTERPORT_API_KEY),
Token Secret as password (MATTERPORT_API_TOKEN). The token pair has admin rights over the account,
so this client refuses any GraphQL mutation or subscription before a request is built.
Skybox and mesh URLs are signed and expire about 5 minutes after the query: download them at once.
"""
import re
import time

import httpx

from app.config import secret
from app.sources.cache import cached_file, cached_json

GRAPH_URL = "https://api.matterport.com/api/models/graph"


class MutationRefused(ValueError):
    """The query contains a mutation or subscription operation."""


class GraphQLError(RuntimeError):
    pass


def _strip_strings_and_comments(doc: str) -> str:
    doc = re.sub(r'"""[\s\S]*?"""', '""', doc)
    doc = re.sub(r'"(?:\\.|[^"\\])*"', '""', doc)
    return re.sub(r"#[^\n]*", "", doc)


def assert_read_only(doc: str) -> None:
    """Refuse documents with a top-level `mutation` or `subscription` operation."""
    text = _strip_strings_and_comments(doc)
    depth = 0
    for match in re.finditer(r"[{}]|[_A-Za-z][_0-9A-Za-z]*", text):
        tok = match.group(0)
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth -= 1
        elif depth == 0 and tok.lower() in ("mutation", "subscription"):
            raise MutationRefused("Matterport client is read-only: mutations and subscriptions are refused")


def _send(query: str, variables: dict | None):
    def go():
        auth = (secret("MATTERPORT_API_KEY"), secret("MATTERPORT_API_TOKEN"))
        for attempt in range(5):
            r = httpx.post(GRAPH_URL, auth=auth, json={"query": query, "variables": variables or {}}, timeout=120)
            if r.status_code != 429:
                break
            time.sleep(2 ** attempt)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"_non_json": r.text[:2000]}
    return go


def graphql(query: str, variables: dict | None = None, *, refresh: bool = False) -> dict:
    """Run a read-only query. Returns `data`. Raises GraphQLError on HTTP or GraphQL errors."""
    assert_read_only(query)
    body = {"query": query, "variables": variables or {}}
    rec = cached_json("matterport", "POST", GRAPH_URL, _send(query, variables), body=body, refresh=refresh)
    resp = rec["response"] if isinstance(rec["response"], dict) else {}
    if rec["status"] != 200 or resp.get("errors"):
        msgs = [e.get("message", "")[:200] for e in resp.get("errors") or []] or [str(resp)[:200]]
        raise GraphQLError(f"Matterport HTTP {rec['status']}: {msgs}")
    return resp["data"]


def download(url: str, dest):
    """Download a signed asset URL to dest (skipped if already cached)."""
    def fetch():
        r = httpx.get(url, timeout=300, follow_redirects=True)
        r.raise_for_status()
        return r.content
    return cached_file(dest, fetch)
