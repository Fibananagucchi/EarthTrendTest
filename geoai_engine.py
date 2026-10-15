"""
Trend Detective — NASA data access through Google Earth Engine.

  get_monthly_series()  "what / how much": one region-averaged monthly series
  get_change_cube()     "where / over time": yearly maps of the chosen area in ONE request

Both work for every variable in nasa_variables.VARIABLES. When GEE is not
available the app switches to demo_data (cached NASA data / synthetic data).
"""

from __future__ import annotations

import json
import math
import os
import re
import time

import ee
import numpy as np
import pandas as pd
import requests

import nasa_variables as nv

EE_IS_ACTIVE = False
EE_STATUS = "not initialized"


# ─────────────────────────────────────────────
# Earth Engine initialisation (never interactive)
# ─────────────────────────────────────────────

def init_gee(project: str | None = None) -> bool:
    """
    Initialise Earth Engine from, in order:
      1. GEE_SERVICE_ACCOUNT_JSON (service-account key, e.g. Streamlit Cloud secrets)
      2. GEE_CREDENTIALS (contents of ~/.config/earthengine/credentials)
      3. credentials already on disk (after `python auth.py`)
    Never opens a browser, so it is safe to call from a web server.
    """
    global EE_IS_ACTIVE, EE_STATUS
    project = project or os.environ.get("GEE_PROJECT")
    try:
        sa_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON")
        if sa_json:
            info = json.loads(sa_json)
            creds = ee.ServiceAccountCredentials(info["client_email"], key_data=sa_json)
            ee.Initialize(creds, project=project or info.get("project_id"))
        else:
            user_creds = os.environ.get("GEE_CREDENTIALS")
            if user_creds:
                path = os.path.expanduser("~/.config/earthengine/credentials")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(user_creds)
            if not project:
                raise RuntimeError("GEE_PROJECT is not set (add it to .env)")
            ee.Initialize(project=project)
        EE_IS_ACTIVE = True
        EE_STATUS = f"connected (project {project})"
    except Exception as e:
        EE_IS_ACTIVE = False
        EE_STATUS = f"offline: {str(e).splitlines()[0][:160]}"
    return EE_IS_ACTIVE


# ─────────────────────────────────────────────
# Geocoding
# ─────────────────────────────────────────────

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_coordinates(text: str):
    """'49.44, 31.99' -> (49.44, 31.99); None if the text is not a lat/lon pair."""
    m = _COORD_RE.match(text or "")
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def get_coordinates_by_address(address: str):
    """Place name -> (lat, lon, display name) via OpenStreetMap Nominatim."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            headers={"User-Agent": "TrendDetective-SpaceApps2026/1.0"},
            params={"q": address, "format": "json", "limit": 1},
            timeout=8,
        )
        if r.status_code == 200 and r.json():
            d = r.json()[0]
            return float(d["lat"]), float(d["lon"]), d["display_name"]
    except Exception:
        pass
    return None, None, None


# ─────────────────────────────────────────────
# Regions
# ─────────────────────────────────────────────

def region_geometry(region: dict) -> ee.Geometry:
    """
    region = {"lat", "lon", "radius_km", "polygon": [[lon, lat], ...] | None}
    A drawn polygon wins; otherwise a circle of radius_km around the point.
    """
    poly = region.get("polygon")
    if poly and len(poly) >= 3:
        return ee.Geometry.Polygon([poly])
    return ee.Geometry.Point([region["lon"], region["lat"]]).buffer(region.get("radius_km", 1.0) * 1000)


def region_area_km2(region: dict) -> float:
    poly = region.get("polygon")
    if poly and len(poly) >= 3:
        lat0 = sum(p[1] for p in poly) / len(poly)
        lon0 = sum(p[0] for p in poly) / len(poly)
        R = 6371.0088
        xy = [(math.radians(lon - lon0) * R * math.cos(math.radians(lat0)),
               math.radians(lat - lat0) * R) for lon, lat in poly]
        return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))) / 2
    return math.pi * region.get("radius_km", 1.0) ** 2


# ─────────────────────────────────────────────
# Collections -> single band "v" in native (unscaled) units
# ─────────────────────────────────────────────

def _hls(geom, start, end, index: str) -> ee.ImageCollection:
    """HLS Landsat (L30) + Sentinel-2 (S30) merged, Fmask-masked, NDVI or NDBI as band 'v'."""
    def prep(nir, red, swir):
        def f(img):
            fm = img.select("Fmask")
            # Fmask bits: 1 cloud, 2 adjacent to cloud/shadow, 3 cloud shadow, 4 snow/ice
            clear = fm.bitwiseAnd((1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)).eq(0)
            if index == "ndvi":
                v = img.normalizedDifference([nir, red])
            else:
                v = img.normalizedDifference([swir, nir])
            return v.rename("v").updateMask(clear).copyProperties(img, ["system:time_start"])
        return f

    base = lambda cid: (ee.ImageCollection(cid).filterBounds(geom).filterDate(start, end)
                        .filter(ee.Filter.lt("CLOUD_COVERAGE", 80)))
    l30 = base("NASA/HLS/HLSL30/v002").map(prep("B5", "B4", "B6"))
    s30 = base("NASA/HLS/HLSS30/v002").map(prep("B8A", "B4", "B11"))
    return l30.merge(s30)


def _collection(var: nv.Variable, geom, start, end) -> ee.ImageCollection:
    if var.preprocess == "hls_ndvi":
        return _hls(geom, start, end, "ndvi")
    if var.preprocess == "hls_ndbi":
        return _hls(geom, start, end, "ndbi")
    col = (ee.ImageCollection(var.collection).filterDate(start, end)
           .filterBounds(geom).select([var.band], ["v"]))
    if var.valid_range:
        lo, hi = var.valid_range
        col = col.map(lambda img: img.updateMask(img.gte(lo).And(img.lte(hi))))
    return col


def _empty() -> ee.Image:
    return ee.Image.constant(0).rename("v").updateMask(ee.Image.constant(0))


_RETRYABLE = ("Too many concurrent aggregations", "Computation timed out", "Too Many Requests", "429")


def _get_info_with_retry(obj, attempts: int = 4):
    for k in range(attempts):
        try:
            return obj.getInfo()
        except ee.EEException as e:
            if k == attempts - 1 or not any(s in str(e) for s in _RETRYABLE):
                raise
            time.sleep(2 * 2 ** k)


def _reduce_scale(var: nv.Variable, area_km2: float) -> float:
    """Native pixel size, coarsened for very large regions so requests stay fast."""
    target_pixels = 250_000
    auto = math.sqrt(area_km2 * 1e6 / target_pixels)
    return max(var.pixel_m, auto)


# ─────────────────────────────────────────────
# "What / how much": monthly regional time series
# ─────────────────────────────────────────────

def get_monthly_series(var_key: str, region: dict, start_year: int, end_year: int) -> pd.DataFrame:
    """
    Region-averaged monthly series, converted to the variable's display units.
    Columns: date, value, n_images, source. Raises if GEE is not available.
    """
    if not EE_IS_ACTIVE:
        raise RuntimeError("Google Earth Engine is not connected")
    var = nv.get(var_key)
    start_year = max(start_year, var.start_year)
    end_year = min(end_year, var.last_year)
    geom = region_geometry(region)
    if math.sqrt(region_area_km2(region)) * 1000 < var.pixel_m:
        # region smaller than one data pixel (e.g. 2 km circle in 55 km GRACE): average the
        # pixels within one pixel-width instead, so a single masked (water/coast) pixel cannot
        # blank the whole series
        geom = ee.Geometry.Point([region["lon"], region["lat"]]).buffer(var.pixel_m)
    scale = _reduce_scale(var, region_area_km2(region))
    col = _collection(var, geom, f"{start_year}-01-01", f"{end_year + 1}-01-01")
    n_months = (end_year - start_year + 1) * 12
    t0 = ee.Date.fromYMD(start_year, 1, 1)

    def per_month(i):
        s = t0.advance(i, "month")
        sub = col.filterDate(s, s.advance(1, "month"))
        img = ee.Image(ee.Algorithms.If(sub.size().gt(0), sub.mean(), _empty()))
        val = img.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=scale,
            maxPixels=1e9, bestEffort=True, tileScale=4,
        ).get("v")
        return ee.Feature(None, {"date": s.format("YYYY-MM-dd"), "value": val, "n": sub.size()})

    # Scene-level collections (HLS) and large regions spawn many parallel aggregations;
    # ask for fewer months per request so GEE's concurrent-aggregation limit is not exceeded.
    area = region_area_km2(region)
    if var.preprocess:
        chunk = 12
    elif area * 1e6 / scale ** 2 < 20_000:       # coarse data (e.g. GRACE, FLDAS): few pixels, cheap months
        chunk = 120
    elif area > 20000:
        chunk = 6
    elif area > 2000:
        chunk = 24
    else:
        chunk = 120
    rows = []
    for first in range(0, n_months, chunk):
        last = min(first + chunk, n_months) - 1
        fc = ee.FeatureCollection(ee.List.sequence(first, last).map(per_month))
        rows += [f["properties"] for f in _get_info_with_retry(fc)["features"]]
    df = pd.DataFrame(rows).rename(columns={"n": "n_images"})
    df["date"] = pd.to_datetime(df["date"]) + pd.Timedelta(days=14)
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    df["value"] = df["value"].astype(float) * var.scale + var.offset
    if var.rate:
        df["value"] *= [var.monthly_factor(d.year, d.month) for d in df["date"]]
    df["source"] = f"NASA via Google Earth Engine ({var.collection})"
    return df[["date", "value", "n_images", "source"]]


# ─────────────────────────────────────────────
# "Where" and "over time": one data cube for all map layers
# ─────────────────────────────────────────────

def map_bounds(lat: float, lon: float, radius_km: float):
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.05))
    return [lon - dlon, max(lat - dlat, -85.0), lon + dlon, min(lat + dlat, 85.0)]


MAP_MARGIN = 0.03        # just enough that the edge of the area is not cut off
MAP_MAX_HALF_KM = 1500


def change_bounds(region: dict, var: nv.Variable | None = None) -> list[float]:
    """
    [w, s, e, n] of the map layers: the box around the chosen circle or drawn outline.
    The layers are transparent outside the area itself (change_maps.area_mask).
    """
    poly = region.get("polygon")
    if poly:
        lons, lats = [p[0] for p in poly], [p[1] for p in poly]
        lat0, lon0 = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        km_per_deg_lon = 111.32 * max(math.cos(math.radians(lat0)), 0.05)
        half_x = (max(lons) - min(lons)) / 2 * km_per_deg_lon
        half_y = (max(lats) - min(lats)) / 2 * 111.32
    else:
        lat0, lon0 = region["lat"], region["lon"]
        half_x = half_y = float(region["radius_km"])
    half_x = min(max(half_x, 0.05) * (1 + MAP_MARGIN), MAP_MAX_HALF_KM)
    half_y = min(max(half_y, 0.05) * (1 + MAP_MARGIN), MAP_MAX_HALF_KM)
    w, _, e, _ = map_bounds(lat0, lon0, half_x)
    _, s, _, n = map_bounds(lat0, lon0, half_y)
    return [w, s, e, n]


# Yearly VIIRS night lights (Earth Observation Group, from the NASA/NOAA Suomi NPP Day/Night Band);
# "average_masked" has fires, aurora and dark background removed.
NIGHT_YEARS = tuple(range(2013, 2026))


def _tiles(image: ee.Image) -> str:
    return image.getMapId({})["tile_fetcher"].url_format


_TILE_CACHE: dict = {}
_TILE_TTL = 6 * 3600          # Earth Engine map tiles stay valid for hours


def night_map_tiles(years) -> dict:
    """
    {year: {"lights": url, "bg": url}} for the given years.
    New years are made in parallel (about 1 s each); known ones come from a 6-hour cache.
    """
    from concurrent.futures import ThreadPoolExecutor

    def one(job):
        kind, year = job
        hit = _TILE_CACHE.get(job)
        if hit and time.time() - hit[1] < _TILE_TTL:
            return job, hit[0]
        url = night_lights_tiles(year) if kind == "lights" else night_background_tiles(year)
        _TILE_CACHE[job] = (url, time.time())
        return job, url

    jobs = [(kind, int(y)) for y in sorted(set(years)) for kind in ("lights", "bg")]
    with ThreadPoolExecutor(max_workers=6) as pool:
        got = dict(pool.map(one, jobs))
    return {y: {"lights": got[("lights", y)], "bg": got[("bg", y)]} for y in sorted({j[1] for j in jobs})}


_WARMING = False


def warm_night_tiles():
    """Once per server: make every night-map year in the background, so picking a year in the menu is quick."""
    global _WARMING
    if _WARMING or not EE_IS_ACTIVE:
        return
    _WARMING = True

    def run():
        try:
            night_map_tiles(NIGHT_YEARS)
        except Exception:
            pass                        # made later, on demand

    import threading
    threading.Thread(target=run, daemon=True).start()


def night_background_tiles(year: int) -> str:
    """
    Dark navy land and near-black water, the look of NASA's Black Marble, with the water of that year:
    water reflects almost no near-infrared light, so a low yearly median of MODIS NIR (MOD13A3, 1 km) is
    water (e.g. the Kakhovka Reservoir is water in 2021 and land in 2024). Oceans have no MOD13A3 data -> water.
    """
    if not EE_IS_ACTIVE:
        raise RuntimeError("Google Earth Engine is not connected")
    nir = (ee.ImageCollection("MODIS/061/MOD13A3").filterDate(f"{year}-01-01", f"{year + 1}-01-01")
           .select("sur_refl_b02").median())
    water = nir.unmask(0).lt(900)                                  # NIR reflectance < 0.09
    sea = ee.Image.constant([3, 4, 10]).visualize(min=0, max=255)
    land = ee.Image.constant([15, 17, 32]).visualize(min=0, max=255).updateMask(water.Not())
    return _tiles(sea.blend(land))


def night_lights_tiles(year: int) -> str:
    """The lights of one year, transparent elsewhere: small gold-white lights like Black Marble, no halos."""
    if not EE_IS_ACTIVE:
        raise RuntimeError("Google Earth Engine is not connected")
    cid = "NOAA/VIIRS/DNB/ANNUAL_V22" if year >= 2022 else "NOAA/VIIRS/DNB/ANNUAL_V21"
    img = ee.ImageCollection(cid).filterDate(f"{year}-01-01", f"{year + 1}-01-01").first().select("average_masked")
    level = img.max(0.1).log10()                                  # radiance spans 4 orders of magnitude
    alpha = level.subtract(0.25).divide(0.75).clamp(0, 1)           # below ~2 nW/cm²/sr: invisible, no speckles
    lights = level.visualize(min=0.35, max=1.9, palette=["a8823f", "e8c27a", "fff0c8", "ffffff"])
    return _tiles(lights.updateMask(alpha))


def _mercator(lon: float, lat: float) -> tuple[float, float]:
    r = 6378137.0
    return r * math.radians(lon), r * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def grid_shape(bounds, size: int) -> tuple[int, int]:
    """(rows, cols) of a Web-Mercator grid over bounds with square cells, longest side = size."""
    w, s, e, n = bounds
    x0, y0 = _mercator(w, s)
    x1, y1 = _mercator(e, n)
    aspect = (x1 - x0) / max(y1 - y0, 1e-9)
    if aspect >= 1:
        return max(8, round(size / aspect)), size
    return size, max(8, round(size * aspect))


def get_change_cube(var_key: str, bounds, start_year: int, end_year: int, size: int = 200) -> dict:
    """
    One Earth Engine request -> the yearly mean of the variable on a grid over bounds
    [w, s, e, n] (Web Mercator, so it overlays the web map exactly; see change_bounds).
    Every map layer — time-lapse frames, before/after, per-pixel trend — is computed
    from this cube locally (change_maps.py) instead of asking Earth Engine for each one.

    Returns {"years", "stack" (years x rows x cols, NaN = no data), "bounds" [w, s, e, n], "units", "source"}.
    Flux variables are annual totals (e.g. mm/year).
    """
    if not EE_IS_ACTIVE:
        raise RuntimeError("Google Earth Engine is not connected")
    var = nv.get(var_key)
    start_year = max(start_year, var.start_year)
    end_year = min(end_year, var.last_year)
    years = list(range(start_year, end_year + 1))
    w, s, e, n = bounds
    rows, cols = grid_shape(bounds, size)
    x0, y0 = _mercator(w, s)
    x1, y1 = _mercator(e, n)
    box = ee.Geometry.Rectangle([w, s, e, n], None, False)
    col = _collection(var, box, f"{start_year}-01-01", f"{end_year + 1}-01-01")

    nodata = -9999.0
    bands = []
    for y in years:
        sub = col.filterDate(f"{y}-01-01", f"{y + 1}-01-01")
        img = ee.Image(ee.Algorithms.If(sub.size().gt(0), sub.mean(), _empty()))
        img = img.multiply(var.scale).add(var.offset).multiply(var.annual_factor)
        bands.append(img.rename(f"y{y}").unmask(nodata).float())

    request = {
        "expression": ee.Image.cat(bands),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": cols, "height": rows},
            "affineTransform": {"scaleX": (x1 - x0) / cols, "shearX": 0, "translateX": x0,
                                "shearY": 0, "scaleY": -(y1 - y0) / rows, "translateY": y1},
            "crsCode": "EPSG:3857",
        },
    }
    for attempt in range(4):
        try:
            arr = ee.data.computePixels(request)
            break
        except ee.EEException as ex:
            if attempt == 3 or not any(m in str(ex) for m in _RETRYABLE):
                raise
            time.sleep(2 * 2 ** attempt)
    stack = np.stack([arr[f"y{y}"] for y in years]).astype("float32")
    stack[stack == nodata] = np.nan
    return {"years": years, "stack": stack, "bounds": [float(b) for b in bounds], "units": var.map_units,
            "source": f"NASA via Google Earth Engine ({var.collection})"}
