"""
Trend Detective — map layers of change, all built from ONE data cube.

A cube is the yearly mean of a variable on a grid over the chosen area
({"years", "stack" [years x rows x cols], "bounds" [w, s, e, n], ...}), fetched with a
single Earth Engine request (geoai_engine.get_change_cube) or loaded offline (demo_data).
From it we make, locally and in about a second:

  • time-lapse   one coloured frame per year, same colour scale for every year
  • before/after mean of the first vs the last few years
  • trend        per-pixel Sen's slope, with a Mann-Kendall significance mask

Pure numpy; images are PNG data URLs that the globe (map_component.py) shows directly.
"""

from __future__ import annotations

import warnings

import numpy as np
from folium.utilities import image_to_url

import nasa_variables as nv
import trends


def _rgb(palette):
    return np.array([[int(c[i:i + 2], 16) for i in (0, 2, 4)] for c in palette], float) / 255.0


def colorize(values: np.ndarray, vmin: float, vmax: float, palette, alpha) -> np.ndarray:
    """2-D array -> RGBA floats with a linear palette; NaN cells are transparent."""
    cols = _rgb(palette)
    span = (vmax - vmin) or 1e-12
    x = np.nan_to_num(np.clip((values - vmin) / span, 0, 1), nan=0.0)
    pos = x * (len(cols) - 1)
    i = np.clip(np.floor(pos).astype(int), 0, len(cols) - 2)
    f = (pos - i)[..., None]
    rgb = cols[i] * (1 - f) + cols[i + 1] * f
    a = np.where(np.isfinite(values), alpha, 0.0)
    return np.concatenate([rgb, np.broadcast_to(a, values.shape)[..., None]], axis=-1)


def png(rgba: np.ndarray) -> str:
    # hand folium uint8: given floats it rescales every channel by the image's own maximum,
    # which shifts the colours and turns semi-transparent pixels opaque
    return image_to_url(np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8))


def value_range(stack: np.ndarray, centered: bool) -> tuple[float, float]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        lo, hi = np.nanpercentile(stack, [2, 98])
    if not np.isfinite(lo):
        return 0.0, 1.0
    if centered:
        m = max(abs(lo), abs(hi)) or 1.0
        return -m, m
    if hi - lo < 1e-9:
        hi = lo + 1e-9
    return float(lo), float(hi)


OUTSIDE_DIM = 0.0        # layers show only the chosen area; the land around it stays untouched


def _haversine_km(lat, lon, lat0, lon0):
    p1, p2 = np.radians(lat), np.radians(lat0)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon0 - lon) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _in_polygon(x, y, ring) -> np.ndarray:
    """Even-odd ray casting, vectorised over the grid."""
    inside = np.zeros(x.shape, bool)
    pts = [tuple(p) for p in ring]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        crosses = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (x < x_at)
    return inside


def area_mask(bounds, shape, region: dict | None) -> np.ndarray:
    """True for the grid cells whose centre lies in the chosen circle or drawn outline."""
    rows, cols = shape
    if not region:
        return np.ones(shape, bool)
    w, s, e, n = bounds
    merc = lambda lat: np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    lon = w + (np.arange(cols) + 0.5) / cols * (e - w)
    y = merc(n) - (np.arange(rows) + 0.5) / rows * (merc(n) - merc(s))
    lat = np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)
    LON, LAT = np.meshgrid(lon, lat)
    if region.get("polygon"):
        inside = _in_polygon(LON, LAT, region["polygon"])
    else:
        inside = _haversine_km(LAT, LON, region["lat"], region["lon"]) <= region["radius_km"]
    if not inside.any():                       # area smaller than one grid cell: the cell under its centre
        d = _haversine_km(LAT, LON, region["lat"], region["lon"])
        inside.flat[int(np.argmin(d))] = True
    return inside


def build_change_layers(cube: dict, var_key: str, alpha: float = 0.05, region: dict | None = None) -> dict:
    """Map layers of the cube; with a region, layers and stats cover only that area (transparent outside)."""
    var = nv.get(var_key)
    years = [int(y) for y in cube["years"]]
    stack = np.asarray(cube["stack"], float)
    n = len(years)
    inside = area_mask(cube["bounds"], stack.shape[1:], region)
    dim = np.where(inside, 1.0, OUTSIDE_DIM)
    ins = stack[:, inside]                      # years x cells in the area
    lo, hi = value_range(ins if np.isfinite(ins).sum() >= 4 else stack, var.centered)
    seq = list(var.seq_palette)
    valid_any = np.isfinite(stack).any(axis=0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        frames = [dict(year=y, url=png(colorize(stack[k], lo, hi, seq, 0.88 * dim))) for k, y in enumerate(years)]
        series = [float(np.nanmean(ins[k])) if np.isfinite(ins[k]).any() else None for k in range(n)]

        k = max(1, min(5, n // 4))
        early, late = np.nanmean(stack[:k], axis=0), np.nanmean(stack[-k:], axis=0)
        label = (lambda a, b: f"{a}–{b}" if a != b else str(a))
        before = dict(label=label(years[0], years[k - 1]), url=png(colorize(early, lo, hi, seq, 0.88 * dim)))
        after = dict(label=label(years[-k], years[-1]), url=png(colorize(late, lo, hi, seq, 0.88 * dim)))
        diff = (late - early)[inside]
        change_mean = float(np.nanmean(diff)) if np.isfinite(diff).any() else None

    g = trends.mann_kendall_grid(stack, np.array(years, float), alpha)
    slope, sig = g["slope"], g["significant"] & valid_any
    finite = np.isfinite(slope)
    ref = finite & inside if (finite & inside).any() else finite
    lim = float(np.nanpercentile(np.abs(slope[ref]), 98)) if ref.any() else 1.0
    lim = lim or 1e-9
    div = list(var.palette)
    trend_all = png(colorize(slope, -lim, lim, div, np.where(sig, 0.9, 0.5) * dim))
    trend_sig = png(colorize(np.where(sig, slope, np.nan), -lim, lim, div, 0.9 * dim))
    n_valid = max(int((finite & inside).sum()), 1)
    share_up = float((sig & inside & (g["z"] > 0)).sum() / n_valid)
    share_down = float((sig & inside & (g["z"] < 0)).sum() / n_valid)

    return dict(
        bounds=[float(b) for b in cube["bounds"]], years=years, source=cube.get("source", ""),
        synthetic=str(cube.get("source", "")).startswith("Synthetic"),
        var=var_key, units=var.map_units, area_share=float(inside.mean()),
        frames=frames, series=series,
        before=before, after=after, change_mean=change_mean,
        value_legend=dict(palette=seq, vmin=lo, vmax=hi, units=var.map_units),
        trend=dict(url_all=trend_all, url_sig=trend_sig, palette=div, vmin=-lim, vmax=lim,
                   units=f"{var.map_units}/yr", share_rising=share_up, share_falling=share_down),
    )
