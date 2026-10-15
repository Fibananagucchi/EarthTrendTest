"""Tests for the variable registry, offline data and summaries (no Earth Engine needed)."""

import numpy as np
import pytest

import demo_data
from geoai_engine import map_bounds
import llm_summary
import nasa_variables as nv
import regions
import trends


def test_registry_is_consistent():
    for key, v in nv.VARIABLES.items():
        assert v.key == key
        assert v.start_year <= v.last_year
        assert v.rate in (None, "per_hour", "per_second", "per_8day")
        assert len(v.palette) == 5
        assert key in demo_data._SYNTH, f"no synthetic model for {key}"
    assert nv.get("precipitation").monthly_factor(2024, 2) == pytest.approx(24 * 29)   # leap-year February


def test_presets_and_stories_reference_real_keys():
    for pk, var_key, start, _ in regions.EXAMPLES:
        assert pk in regions.PRESETS and var_key in nv.VARIABLES
    for s in regions.STORIES:
        assert s["variable"] in nv.VARIABLES
        assert all(k in regions.PRESETS for k in s["regions"])


@pytest.mark.parametrize("key", list(nv.VARIABLES))
def test_synthetic_series_are_analysable(key):
    df = demo_data.synthetic_series(key, 49.4, 32.0, 2005, 2024)
    var = nv.get(key)
    lo, hi = demo_data._SYNTH[key][4]
    assert lo is None or df["value"].min() >= lo
    assert hi is None or df["value"].max() <= hi
    r = trends.analyze_trend(df, relative_change=var.relative_change)
    assert r.direction != "insufficient data"
    assert np.isfinite(r.p_value)


def test_synthetic_trends_differ_between_places():
    dirs = {trends.analyze_trend(demo_data.synthetic_series("ndvi_modis", lat, lon, 2001, 2025)).tendency
            for lat, lon in [(49.4, 32.0), (-7.2, -55.5), (36.8, 109.5), (10, 10), (60, -100)]}
    assert {"rising", "falling"} <= dirs


def test_change_layers_from_synthetic_cube():
    import change_maps
    cube = demo_data.synthetic_cube("lst_day", map_bounds(47.0, 34.0, 50), 2001, 2025)
    assert cube["stack"].shape == (25, 60, 60)
    L = change_maps.build_change_layers(cube, "lst_day")
    assert [f["year"] for f in L["frames"]] == list(range(2001, 2026))
    assert all(f["url"].startswith("data:image/png;base64,") for f in L["frames"])
    assert L["before"]["label"] == "2001–2005" and L["after"]["label"] == "2021–2025"
    assert L["trend"]["share_rising"] > 0 and L["trend"]["share_falling"] > 0     # both directions on one map
    assert L["synthetic"] and len(L["series"]) == 25
    assert L["value_legend"]["vmin"] < L["value_legend"]["vmax"]


def test_map_area_follows_the_chosen_area():
    import change_maps
    from geoai_engine import change_bounds, grid_shape
    ndvi, grace = nv.get("ndvi_modis"), nv.get("water_storage")
    small = change_bounds(dict(lat=47.0, lon=34.0, radius_km=5), ndvi)
    big = change_bounds(dict(lat=47.0, lon=34.0, radius_km=50), ndvi)
    assert (small[3] - small[1]) * 111.32 == pytest.approx(2 * 5 * 1.03, rel=1e-6)     # the circle's box
    assert (big[3] - big[1]) == pytest.approx(10 * (small[3] - small[1]), rel=1e-6)      # scales with the radius
    tiny = change_bounds(dict(lat=47.0, lon=34.0, radius_km=2), grace)                   # 55 km GRACE pixels
    assert (tiny[3] - tiny[1]) * 111.32 == pytest.approx(2 * 2 * 1.03, rel=1e-6)        # still just the area
    # a long drawn outline gets a long map, not a square
    ring = [[34.0, 47.0], [35.0, 47.0], [35.0, 47.1], [34.0, 47.1]]
    wide = change_bounds(dict(lat=47.05, lon=34.5, radius_km=5, polygon=ring), ndvi)
    assert wide[0] < 34.0 and wide[2] > 35.0 and wide[1] < 47.0 and wide[3] > 47.1
    rows, cols = grid_shape(wide, 200)
    assert cols == 200 and rows < 60
    # stats and colours cover only the area; the land around it is faded
    region = dict(lat=47.0, lon=34.0, radius_km=20, polygon=None)
    cube = demo_data.synthetic_cube("lst_day", change_bounds(region, nv.get("lst_day")), 2001, 2025)
    inside = change_maps.area_mask(cube["bounds"], cube["stack"].shape[1:], region)
    assert 0.7 < inside.mean() < 0.78                        # circle in its box: pi/4 / 1.03^2 ~ 0.74
    L = change_maps.build_change_layers(cube, "lst_day", region=region)
    assert L["area_share"] == pytest.approx(inside.mean())
    assert L["series"][0] == pytest.approx(float(np.nanmean(cube["stack"][0][inside])))
    import base64, io
    from PIL import Image
    png = Image.open(io.BytesIO(base64.b64decode(L["frames"][0]["url"].split(",", 1)[1])))
    alpha = np.asarray(png.convert("RGBA"))[..., 3]
    assert (alpha[~inside] == 0).all() and (alpha[inside] > 0).all()   # nothing is drawn outside the area
    poly = dict(lat=47.05, lon=34.5, polygon=ring)
    assert change_maps.area_mask(wide, grid_shape(wide, 200), poly).mean() > 0.6


def test_centered_variables_get_a_symmetric_scale():
    import change_maps
    L = change_maps.build_change_layers(demo_data.synthetic_cube("water_storage", map_bounds(29.8, 75.8, 300), 2002, 2024), "water_storage")
    assert L["value_legend"]["vmin"] == pytest.approx(-L["value_legend"]["vmax"])


def test_cube_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(demo_data, "CUBES_PATH", tmp_path / "cubes.npz")
    demo_data._load_cubes.cache_clear()
    try:
        cube = demo_data.synthetic_cube("ndvi_modis", map_bounds(36.8, 109.5, 40), 2001, 2025)
        cube["stack"][:, 0, 0] = np.nan                                        # e.g. a water pixel
        demo_data.save_cubes({("loess_plateau", "ndvi_modis"): cube})
        back = demo_data.cached_cube("loess_plateau", "ndvi_modis", 2005, 2025)
        assert back["years"] == list(range(2005, 2026))
        assert np.isnan(back["stack"][:, 0, 0]).all()
        assert np.nanmax(np.abs(back["stack"] - cube["stack"][4:])) < 1e-4     # 16-bit quantisation error
        assert demo_data.cached_cube("loess_plateau", "lst_day", 2001, 2025) is None
    finally:
        demo_data._load_cubes.cache_clear()


def test_offline_series_prefers_cache_for_presets(monkeypatch):
    import pandas as pd
    fake = pd.DataFrame({"preset": "loess_plateau", "variable": "ndvi_modis",
                         "date": pd.date_range("2001-01-15", periods=240, freq="MS"),
                         "value": 0.4, "source": "NASA via Google Earth Engine (test)", "retrieved": "2026-09-25"})
    monkeypatch.setattr(demo_data, "load_cache", lambda: fake)
    got = demo_data.offline_series("ndvi_modis", regions.region_dict("loess_plateau"), 2005, 2010)
    assert got["source"].iloc[0].startswith("NASA") and got["date"].dt.year.between(2005, 2010).all()
    moved = dict(regions.region_dict("loess_plateau"), preset=None)
    assert demo_data.offline_series("ndvi_modis", moved, 2005, 2010)["source"].iloc[0] == demo_data.SYNTHETIC_LABEL


def test_offline_series_without_cache_file(monkeypatch, tmp_path):
    monkeypatch.setattr(demo_data, "CACHE_PATH", tmp_path / "missing.csv.gz")
    demo_data.load_cache.cache_clear()
    try:
        got = demo_data.offline_series("ndvi_modis", regions.region_dict("loess_plateau"), 2005, 2010)
        assert got["source"].iloc[0] == demo_data.SYNTHETIC_LABEL
        assert demo_data.cache_summary().empty
    finally:
        demo_data.load_cache.cache_clear()


def test_template_summaries_state_the_verdict():
    var = nv.get("ndvi_modis")
    rising = trends.analyze_trend(demo_data.synthetic_series("ndvi_modis", 36.8, 109.5, 2001, 2025))
    text = llm_summary.template_summary(rising, var, "Test place")
    for section in ("What we looked at", "Where", "What we found", "How sure are we?"):
        assert section in text
    assert text.startswith("### Yes — the land is getting greener")
    flat = demo_data.synthetic_series("ndvi_modis", 36.8, 109.5, 2001, 2025).assign(value=0.4)
    flat["value"] += np.random.default_rng(0).normal(0, 0.05, len(flat))
    ns = trends.analyze_trend(flat)
    assert llm_summary.headline(ns, var, "Test place").startswith("No clear change in Test place")


def test_plain_language_helpers():
    import plain
    assert plain.confidence(0.0001, 0.05)[0] == 4
    assert plain.confidence(0.03, 0.05)[0] == 2
    assert plain.confidence(0.03, 0.01)[0] == 1            # stricter test -> only "maybe"
    assert plain.confidence(0.5, 0.05)[0] == 0
    assert "about 1 time in 50" in plain.chance_text(0.02)
    assert "less than 1 time in 1,000" in plain.chance_text(0.0001)
    for v in nv.VARIABLES.values():
        assert v.plain and v.question.endswith("?") and v.up_phrase and v.down_phrase and v.explain


@pytest.mark.parametrize("x,expected", [(0.00655, "0.00655"), (0.163, "0.163"), (-3.194, "-3.19"),
                                        (1234.5, "1,234"), (0.00021, "0.00021"), (0, "0"), (12.34, "12.3")])
def test_number_formatting(x, expected):
    assert llm_summary.fmt(x) == expected
