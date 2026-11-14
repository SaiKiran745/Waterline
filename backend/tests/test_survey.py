"""Survey height decision and Gemini client cache behaviour."""
import pytest

from app.sources import cache, gemini
from app.survey.interior import decide_height


def test_mesh_height_used_when_it_agrees_with_visual_estimate():
    lo, hi, conf, how = decide_height(3.0, 4.5, 0.7, {"heights_ft": [3.4, 3.5, 3.6]})
    assert how == "measured from mesh" and lo == pytest.approx(3.25) and hi == pytest.approx(3.75) and conf == pytest.approx(0.8)


def test_disagreement_widens_range_and_lowers_confidence():
    lo, hi, conf, how = decide_height(0.0, 0.5, 0.8, {"heights_ft": [5.0, 5.2, 5.4]})
    assert how.startswith("estimated") and lo == 0.0 and hi >= 5.5 and conf < 0.8


def test_no_mesh_hit_falls_back_to_estimate():
    lo, hi, conf, how = decide_height(2.0, 1.0, 0.5, {"heights_ft": None})
    assert (lo, hi) == (1.0, 2.0) and conf == pytest.approx(0.35) and "no mesh hit" in how


def test_gemini_demo_mode_miss_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr(gemini, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gemini.httpx, "post", lambda *a, **k: pytest.fail("no network in DEMO_MODE"))
    with pytest.raises(cache.CacheMiss):
        gemini.generate_json(["hello", b"\xff\xd8fake"], {"type": "OBJECT"}, tag="t")


def test_building_fabric_is_not_priced_as_contents():
    from app.survey.interior import is_fabric
    for label in ("wall power outlet", "wall electrical outlets", "wall-mounted electrical outlet box",
                  "light switch", "kitchen lower cabinet base", "duplex receptacle"):
        assert is_fabric(label), label
    for label in ("wall-mounted electrical subpanel and disconnect equipment", "main switchgear",
                  "ground-mounted electrical cabinet unit", "server rack", "row of 6 desks", "filing cabinets"):
        assert not is_fabric(label), label
