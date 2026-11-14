"""Matterport mutation guard and DEMO_MODE cache behaviour."""
import pytest

from app.sources import cache, matterport


@pytest.mark.parametrize("doc", [
    "mutation { patchModel(id: \"x\") { id } }",
    "  # leading comment\n mutation Archive { updateModelState(id: \"x\", state: inactive) { id } }",
    "query A { model(id: \"x\") { id } }\nmutation B { addMattertag { id } }",
    "MUTATION { x }",
    "subscription { events { id } }",
])
def test_mutations_refused(doc):
    with pytest.raises(matterport.MutationRefused):
        matterport.assert_read_only(doc)


@pytest.mark.parametrize("doc", [
    "query { model(id: \"x\") { id } }",
    "{ model(id: \"mutation\") { id } }",
    "query($id: ID!) { model(id: $id) { mutationLike: name } }  # mutation in a comment",
])
def test_queries_allowed(doc):
    matterport.assert_read_only(doc)


def test_graphql_refuses_before_any_request(monkeypatch):
    monkeypatch.setattr(matterport, "_send", lambda *a: pytest.fail("network must not be touched"))
    with pytest.raises(matterport.MutationRefused):
        matterport.graphql("mutation { x }")


def test_demo_mode_miss_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr(cache, "HTTP_CACHE", tmp_path)
    with pytest.raises(cache.CacheMiss):
        cache.cached_json("x", "GET", "https://example.invalid", lambda: pytest.fail("no network in DEMO_MODE"))
    with pytest.raises(cache.CacheMiss):
        cache.cached_file(tmp_path / "missing.jpg", lambda: pytest.fail("no network in DEMO_MODE"))


def test_cache_hit_needs_no_network(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "HTTP_CACHE", tmp_path)
    monkeypatch.setenv("DEMO_MODE", "0")
    first = cache.cached_json("x", "GET", "https://example.invalid", lambda: (200, {"v": 1}), params={"a": 1})
    monkeypatch.setenv("DEMO_MODE", "1")
    again = cache.cached_json("x", "GET", "https://example.invalid", lambda: pytest.fail("cached"), params={"a": 1})
    assert first["response"] == again["response"] == {"v": 1}
