"""
Trend Detective — offline / demo data.

When Google Earth Engine is not available the app still works:

1. Preset regions -> real NASA series cached in data/demo_cache.csv.gz
   (built by scripts/build_demo_cache.py while GEE was online).
2. Any other place -> deterministic synthetic series with a realistic seasonal
   cycle, autocorrelated noise, data gaps and a location-dependent trend
   (rising in some places, falling in others), clearly labelled as synthetic.
3. Map layers offline -> cached real yearly maps (data/demo_cubes.npz) for the
   case files, a synthetic yearly-map cube elsewhere; both go through change_maps.py.
"""

from __future__ import annotations

import hashlib
import warnings
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

import nasa_variables as nv
import trends

CACHE_PATH = Path(__file__).parent / "data" / "demo_cache.csv.gz"
SYNTHETIC_LABEL = "Synthetic demo data (not a measurement)"


# ─────────────────────────────────────────────
# 1. Cached real series
# ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_cache() -> pd.DataFrame:
    if not CACHE_PATH.exists():
        return pd.DataFrame({"preset": pd.Series(dtype=str), "variable": pd.Series(dtype=str),
                             "date": pd.Series(dtype="datetime64[ns]"), "value": pd.Series(dtype=float),
                             "source": pd.Series(dtype=str), "retrieved": pd.Series(dtype=str)})
    return pd.read_csv(CACHE_PATH, parse_dates=["date"])


def cached_series(var_key: str, preset: str, start_year: int, end_year: int) -> pd.DataFrame | None:
    c = load_cache()
    sel = c[(c["preset"] == preset) & (c["variable"] == var_key)
            & (c["date"].dt.year >= start_year) & (c["date"].dt.year <= end_year)]
    if sel.empty:
        return None
    out = sel[["date", "value", "source"]].copy()
    retrieved = sel["retrieved"].iloc[0]
    out["source"] = f"{sel['source'].iloc[0]} — cached {retrieved}"
    return out.reset_index(drop=True)


def cache_summary() -> pd.DataFrame:
    c = load_cache()
    if c.empty:
        return c
    return c.groupby(["preset", "variable"]).agg(
        first=("date", "min"), last=("date", "max"), n=("value", "size"), source=("source", "first"),
    ).reset_index()


# ─────────────────────────────────────────────
# 2. Synthetic series
# ─────────────────────────────────────────────

# level, seasonal amplitude, noise sd, typical |trend| per year, clip range
_SYNTH = {
    "ndvi_modis":         (0.45, 0.20, 0.030, 0.006, (-0.1, 0.95)),
    "evi_modis":          (0.30, 0.13, 0.020, 0.004, (-0.1, 0.90)),
    "ndvi_hls":           (0.45, 0.22, 0.050, 0.006, (-0.2, 0.95)),
    "ndbi_hls":           (-0.05, 0.08, 0.040, 0.004, (-0.6, 0.5)),
    "lst_day":            (16.0, 13.0, 1.500, 0.060, (-40, 70)),
    "lst_night":          (4.0, 10.0, 1.200, 0.050, (-45, 40)),
    "air_temp":           (9.0, 11.0, 1.000, 0.040, (-45, 45)),
    "precipitation":      (55.0, 20.0, 18.00, 0.600, (0, None)),
    "soil_moisture":      (0.30, 0.06, 0.020, 0.0015, (0.02, 0.6)),
    "soil_moisture_smap": (0.28, 0.06, 0.020, 0.0015, (0.02, 0.6)),
    "evapotranspiration": (45.0, 40.0, 6.000, 0.400, (0, None)),
    "water_storage":      (0.0, 6.0, 3.000, 1.000, (None, None)),
    "water_storage_gldas": (90.0, 5.0, 2.000, 0.800, (0, None)),
    "groundwater_gldas":  (70.0, 2.0, 1.500, 0.700, (0, None)),
    "snow_cover":         (45.0, 45.0, 8.000, 0.400, (0, 100)),
    "night_lights":       (8.0, 1.0, 0.800, 0.250, (0, None)),
}


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _trend_factor(var_key: str, lat: float, lon: float) -> float:
    """Smooth, location-dependent value in [-1, 1]: neighbouring places trend alike, distant ones may not."""
    phase = (_seed(var_key) % 628) / 100.0
    return math.sin(math.radians(lat) * 7.0 + math.radians(lon) * 3.0 + phase)


def synthetic_series(var_key: str, lat: float, lon: float, start_year: int, end_year: int) -> pd.DataFrame:
    var = nv.get(var_key)
    level, amp, noise, trend_scale, (lo, hi) = _SYNTH[var_key]
    rng = np.random.default_rng(_seed(var_key, round(lat, 2), round(lon, 2)))
    dates = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS") + pd.Timedelta(days=14)
    t_years = np.arange(len(dates)) / 12.0
    phase = 0 if lat >= 0 else 6
    season = np.cos(2 * np.pi * ((dates.month - 7 + phase) % 12) / 12)     # +1 at local mid-summer
    trend = trend_scale * _trend_factor(var_key, lat, lon)

    e = np.zeros(len(dates))
    for i in range(1, len(dates)):
        e[i] = 0.5 * e[i - 1] + rng.normal(0, noise)

    if var_key == "snow_cover":
        winter = np.clip(-season, 0, None)
        y = np.clip(level + amp * -season + trend * (t_years - t_years.mean()) + e, 0, 100) * (winter > 0.2)
    else:
        y = level + amp * season + trend * (t_years - t_years.mean()) + e

    y = np.clip(y, lo, hi)
    df = pd.DataFrame({"date": dates, "value": y})
    # gaps: cloudy/dark winter months for optical & night-light sensors
    if var.kind == "satellite" and var_key not in ("water_storage", "precipitation"):
        winter_gap = (season < -0.6) & (rng.random(len(df)) < 0.35)
        df = df[~winter_gap]
    df["source"] = SYNTHETIC_LABEL
    return df.reset_index(drop=True)


def offline_series(var_key: str, region: dict, start_year: int, end_year: int) -> pd.DataFrame:
    """Cached real data for untouched preset regions, synthetic data elsewhere."""
    var = nv.get(var_key)
    start_year = max(start_year, var.start_year)
    end_year = min(end_year, var.last_year)
    preset = region.get("preset")
    if preset and not region.get("polygon"):
        cached = cached_series(var_key, preset, start_year, end_year)
        if cached is not None and len(cached):
            return cached
    return synthetic_series(var_key, region["lat"], region["lon"], start_year, end_year)


# ─────────────────────────────────────────────
# 3. Map cubes (yearly maps around a place) for time-lapse / before-after / trend layers
# ─────────────────────────────────────────────

CUBES_PATH = Path(__file__).parent / "data" / "demo_cubes.npz"


def _cube_key(preset: str, var_key: str) -> str:
    return f"{preset}__{var_key}"


@lru_cache(maxsize=1)
def _load_cubes():
    if not CUBES_PATH.exists():
        return None
    return np.load(CUBES_PATH, allow_pickle=False)


def _downsample(stack: np.ndarray, max_size: int) -> np.ndarray:
    """Block-average (NaN-aware) so the grid is at most max_size pixels wide — keeps the offline file small."""
    f = int(np.ceil(max(stack.shape[1:]) / max_size))
    if f <= 1:
        return stack
    t, h, w = stack.shape
    h2, w2 = h // f * f, w // f * f
    blocks = stack[:, :h2, :w2].reshape(t, h2 // f, f, w2 // f, f)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(blocks, axis=(2, 4))


def save_cubes(cubes: dict, max_size: int = 100):
    """cubes: {(preset, var_key): cube}. Stored as uint16 (65535 = no data) with a per-cube value range."""
    arrays = {}
    for (preset, var_key), cube in cubes.items():
        st = _downsample(np.asarray(cube["stack"], float), max_size)
        lo, hi = float(np.nanmin(st)), float(np.nanmax(st))
        q = np.full(st.shape, 65535, np.uint16)
        ok = np.isfinite(st)
        q[ok] = np.round((st[ok] - lo) / ((hi - lo) or 1.0) * 65534).astype(np.uint16)
        k = _cube_key(preset, var_key)
        arrays[k + "__q"] = q
        arrays[k + "__meta"] = np.array([lo, hi, *cube["bounds"]], float)
        arrays[k + "__years"] = np.asarray(cube["years"], int)
        arrays[k + "__source"] = np.array(str(cube.get("source", "")).split(" — cached")[0])
    CUBES_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CUBES_PATH, **arrays)
    _load_cubes.cache_clear()


def cached_cube(preset: str, var_key: str, start_year: int, end_year: int) -> dict | None:
    data = _load_cubes()
    k = _cube_key(preset, var_key)
    if data is None or k + "__q" not in data.files:
        return None
    q, meta, years = data[k + "__q"], data[k + "__meta"], data[k + "__years"]
    lo, hi, bounds = meta[0], meta[1], list(meta[2:6])
    stack = np.where(q == 65535, np.nan, lo + q.astype(float) / 65534 * ((hi - lo) or 1.0))
    sel = (years >= start_year) & (years <= end_year)
    if sel.sum() < trends.MIN_YEARS:
        return None
    return {"years": years[sel].tolist(), "stack": stack[sel], "bounds": bounds, "units": nv.get(var_key).map_units,
            "source": f"{data[k + '__source']} — cached"}


def synthetic_cube(var_key: str, bounds, start_year: int, end_year: int, n: int = 60) -> dict:
    """Yearly maps over bounds [w, s, e, n] with a smooth trend field that rises in one part and falls in another."""
    var = nv.get(var_key)
    level, amp, noise, trend_scale, (lo, hi) = _SYNTH[var_key]
    start_year = max(start_year, var.start_year)
    end_year = min(end_year, var.last_year)
    years = np.arange(start_year, end_year + 1)
    from geoai_engine import grid_shape          # pure-python helper, no GEE call
    bounds = [float(b) for b in bounds]
    lat, lon = (bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2
    rows, cols = grid_shape(bounds, n)
    X, Y = np.meshgrid(np.linspace(-1, 1, cols) * cols / n, np.linspace(1, -1, rows) * rows / n)
    phase = (_seed(var_key, round(lat, 1), round(lon, 1)) % 628) / 100.0
    field = np.sin(1.6 * X + phase) * np.cos(1.1 * Y - phase / 2) + 0.35 * X
    trend = trend_scale * 1.4 * field
    texture = 0.15 * amp * np.sin(5 * X + 2 * phase) * np.cos(4 * Y)          # static spatial pattern
    rng = np.random.default_rng(_seed("grid", var_key, round(lat, 2), round(lon, 2)))
    stack = (level + texture[None] + trend[None] * (years - years.mean())[:, None, None]
             + rng.normal(0, noise * 0.35, (len(years), rows, cols)))
    stack = np.clip(stack, lo, hi)
    if var.rate:
        stack = stack * 12.0                       # monthly totals -> annual totals
    return {"years": years.tolist(), "stack": stack, "bounds": bounds, "units": var.map_units,
            "source": SYNTHETIC_LABEL}


def offline_cube(var_key: str, region: dict, bounds, start_year: int, end_year: int) -> dict:
    """Cached real cube for untouched preset regions, synthetic elsewhere."""
    var = nv.get(var_key)
    start_year, end_year = max(start_year, var.start_year), min(end_year, var.last_year)
    preset = region.get("preset")
    if preset and not region.get("polygon"):
        cube = cached_cube(preset, var_key, start_year, end_year)
        if cube is not None:
            return cube
    return synthetic_cube(var_key, bounds, start_year, end_year)
