"""
Trend Detective — NASA Space Apps 2026: "Be An Earth System Trend Detective!"

Is our planet changing where you care about? Pick a place on the globe, pick what to look
at (greenness, heat, water, snow, lights…), and get a plain answer backed by NASA data:
what is changing, where, how much, and whether it is a real (statistically significant) change.
"""

import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import change_maps
import demo_data
import examples_strip
import geoai_engine
import llm_summary
import map_component
import nasa_variables as nv
import plain
import regions
import trends
import ui_theme as ui
from plain import fmt, fmt_p

st.set_page_config(page_title="Trend Detective", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")

try:  # Streamlit Cloud: copy secrets into the environment (no-op locally)
    for _k in ("GEE_PROJECT", "GEE_SERVICE_ACCOUNT_JSON", "GEE_CREDENTIALS", "GROQ_API_KEY", "GROQ_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

st.markdown(ui.CSS, unsafe_allow_html=True)

if geoai_engine.EE_STATUS == "not initialized":
    with st.spinner("Connecting to NASA data (Google Earth Engine)…"):
        geoai_engine.init_gee()
gee_live = geoai_engine.EE_IS_ACTIVE
if gee_live:
    geoai_engine.warm_night_tiles()          # night maps of every year, made in the background (instant year menu)
groq_ok = llm_summary.llm_available()

VIEWS = {"trend": "✅  The answer", "compare": "⚖️  Compare places",
         "scan": "🔍  What else is changing here?", "method": "📘  How it works"}
OFFLINE_NOTE = "Couldn't reach live NASA data right now, so you're seeing saved or simulated data instead."


# ─────────────────────────────────────────────
# State & callbacks
# ─────────────────────────────────────────────

def preset_region(key: str) -> dict:
    r = regions.region_dict(key)
    r["area_km2"] = geoai_engine.region_area_km2(r)
    return r


def default_years(var: nv.Variable, span: int = 25) -> tuple:
    return max(var.start_year, var.last_year - span + 1), var.last_year


def clamp_years(var: nv.Variable, years=None):
    s, e = years or st.session_state.years
    s, e = max(s, var.start_year), min(e, var.last_year)
    if e - s < trends.MIN_YEARS - 1:
        s, e = default_years(var)
    st.session_state.years = (s, e)


def init_state():
    v0 = nv.get("ndvi_modis")
    defaults = dict(
        region=preset_region("loess_plateau"), var_key=v0.key, last_var=v0.key, years=default_years(v0),
        alpha=0.05, last_alpha=0.05, view="trend", last_view="trend", map_ack=None,
        change_req=None, change_request=False,
        cmp_list=[], cmp_results=None, cmp_story=None, cmp_autorun=False,
        scan_results=None, ai_summaries={}, mode_hint=None,
        topic=v0.group, last_topic=v0.group, example_active=None, night_year=None,
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def set_variable(key: str, start_year: int | None = None):
    var = nv.get(key)
    st.session_state.var_key = key
    st.session_state.last_var = key
    st.session_state.topic = st.session_state.last_topic = var.group
    clamp_years(var, (max(start_year, var.start_year), var.last_year) if start_year else None)


def inspect_radius(var: nv.Variable) -> float:
    """Region radius used when a pixel of the map layers is clicked: about one data pixel."""
    return round(max(0.5, var.pixel_m * 0.75 / 1000), 1)


def preset_variable(preset: str) -> tuple:
    for pk, vk, start, _ in regions.EXAMPLES:
        if pk == preset:
            return vk, start
    for s in regions.STORIES:
        if preset in s["regions"]:
            return s["variable"], s["start_year"]
    return None, None


def on_map_event():
    apply_map_event(map_component.read_event("globe"))


def apply_map_event(ev: dict | None):
    """Update the investigation from a globe event (click, example pin, drawn area, radius, compare pin, watch)."""
    if not ev:
        return
    st.session_state.map_ack = ev.get("nonce")
    kind = ev.get("type")
    reg = st.session_state.region
    if kind in ("pick", "polygon", "radius"):
        st.session_state.example_active = None
    if kind == "pick":
        lat, lon = float(ev["lat"]), float(ev["lon"])
        km = inspect_radius(nv.get(st.session_state.last_var)) if ev.get("inspect") else reg["radius_km"]
        st.session_state.region = dict(name=ev.get("name") or f"{lat:.3f}, {lon:.3f}", lat=lat, lon=lon,
                                       radius_km=km, polygon=None, preset=None, area_km2=math.pi * km ** 2,
                                       within_change=bool(ev.get("inspect")))
        if st.session_state.view == "method":
            st.session_state.view = st.session_state.last_view = "trend"
    elif kind == "preset":
        st.session_state.region = preset_region(ev["key"])
        default_var, default_start = preset_variable(ev["key"])
        var_key = ev.get("variable") or default_var
        if var_key:
            set_variable(var_key, ev.get("start_year") or default_start)
        st.session_state.view = st.session_state.last_view = "trend"
        st.session_state.change_request = True            # examples play their time-lapse straight away
    elif kind == "polygon":
        ring = [list(map(float, p)) for p in ev["coords"]]
        lat = sum(p[1] for p in ring) / len(ring)
        lon = sum(p[0] for p in ring) / len(ring)
        area = geoai_engine.region_area_km2({"polygon": ring})
        st.session_state.region = dict(name=f"Drawn area · {area:,.1f} km²", lat=lat, lon=lon, radius_km=reg["radius_km"],
                                       polygon=ring, preset=None, area_km2=area)
    elif kind == "radius":
        km = float(ev["km"])
        new = dict(reg, radius_km=km, area_km2=math.pi * km ** 2, within_change=False)
        if reg.get("preset") and abs(regions.PRESETS[reg["preset"]]["radius_km"] - km) > 1e-6:
            new["preset"] = None                     # saved example data no longer matches
        st.session_state.region = new
    elif kind == "compare_add":
        if len(st.session_state.cmp_list) < 6:
            st.session_state.cmp_list = st.session_state.cmp_list + [dict(
                name=ev.get("name") or "Place", lat=float(ev["lat"]), lon=float(ev["lon"]),
                radius_km=reg["radius_km"] if not reg.get("polygon") else 10.0, preset=None)]
        st.session_state.cmp_results = None
        st.session_state.cmp_story = None
        st.session_state.view = st.session_state.last_view = "compare"
    elif kind == "show_change":
        st.session_state.change_request = True
    elif kind == "night_year":
        st.session_state.night_year = int(ev["year"])


def restore_if_none(key: str, last_key: str):
    if st.session_state[key] is None:
        st.session_state[key] = st.session_state[last_key]
    else:
        st.session_state[last_key] = st.session_state[key]


def on_var_change():
    restore_if_none("var_key", "last_var")
    set_variable(st.session_state.var_key)
    st.session_state.example_active = None


def on_topic_change():
    restore_if_none("topic", "last_topic")
    topic = st.session_state.topic
    if nv.get(st.session_state.var_key).group != topic:
        first = next(k for k, v in nv.VARIABLES.items() if v.group == topic)
        set_variable(first)
        st.session_state.example_active = None



def load_story(story_key: str):
    story = next(s for s in regions.STORIES if s["key"] == story_key)
    set_variable(story["variable"], story["start_year"])
    st.session_state.cmp_list = [dict(name=regions.PRESETS[k]["name"], lat=regions.PRESETS[k]["lat"],
                                      lon=regions.PRESETS[k]["lon"], radius_km=regions.PRESETS[k]["radius_km"], preset=k)
                                 for k in story["regions"]]
    st.session_state.cmp_story = story_key
    st.session_state.cmp_results = None
    st.session_state.cmp_autorun = True
    st.session_state.view = st.session_state.last_view = "compare"
    st.session_state.mode_hint = dict(mode="compare", token=time.time())



def open_example(i: int):
    ex = regions.LANDING_EXAMPLES[i]
    st.session_state.example_active = i
    if ex["kind"] == "compare":
        load_story(ex["story"])
        return
    st.session_state.region = preset_region(ex["preset"])
    set_variable(ex["variable"], ex["start"])
    st.session_state.view = st.session_state.last_view = "trend"
    st.session_state.change_request = True                # show the change on the map right away


def on_example():
    ev = examples_strip.read_open("examples")
    if ev is not None:
        open_example(int(ev["i"]))


def add_current_to_compare():
    reg = st.session_state.region
    if len(st.session_state.cmp_list) < 6:
        st.session_state.cmp_list = st.session_state.cmp_list + [dict(
            name=reg.get("name") or "Place", lat=reg["lat"], lon=reg["lon"],
            radius_km=reg["radius_km"], preset=reg.get("preset") if not reg.get("polygon") else None)]
    st.session_state.cmp_results = None


def remove_compare(i: int):
    lst = list(st.session_state.cmp_list)
    lst.pop(i)
    st.session_state.cmp_list = lst
    st.session_state.cmp_results = None
    st.session_state.cmp_story = None


def clear_compare():
    st.session_state.cmp_list = []
    st.session_state.cmp_results = None
    st.session_state.cmp_story = None


def open_variable(key: str):
    set_variable(key)
    st.session_state.view = st.session_state.last_view = "trend"


init_state()
# lets headless tests (tests/test_app_offline.py) simulate clicks inside the custom components
if "_inject_map_event" in st.session_state:
    apply_map_event(st.session_state.pop("_inject_map_event"))
if "_inject_example" in st.session_state:
    open_example(st.session_state.pop("_inject_example"))


# ─────────────────────────────────────────────
# Data access (cached) and analysis
# ─────────────────────────────────────────────

def poly_tuple(region):
    poly = region.get("polygon")
    return tuple(tuple(round(c, 6) for c in p) for p in poly) if poly else None


@st.cache_data(show_spinner=False, ttl=12 * 3600, max_entries=400)
def fetch_series(var_key, lat, lon, radius_km, polygon, preset, start, end, live):
    """(dataframe, error or None). Falls back to offline data on any Earth Engine error."""
    region = dict(lat=lat, lon=lon, radius_km=radius_km,
                  polygon=[list(p) for p in polygon] if polygon else None, preset=preset)
    err = None
    if live:
        try:
            return geoai_engine.get_monthly_series(var_key, region, start, end), None
        except Exception as e:
            err = f"{OFFLINE_NOTE} (Earth Engine: {str(e)[:120]})"
    return demo_data.offline_series(var_key, region, start, end), err


def analyze(var_key, region, start, end, alpha):
    var = nv.get(var_key)
    df, err = fetch_series(var_key, round(region["lat"], 5), round(region["lon"], 5), region["radius_km"],
                           poly_tuple(region), region.get("preset"), start, end, gee_live)
    res = trends.analyze_trend(df, alpha=alpha, variable=var.name, units=var.units, relative_change=var.relative_change)
    return df, res, err


@st.cache_data(show_spinner=False, ttl=6 * 3600, max_entries=40)
def fetch_cube(var_key, bounds, preset, start, end, live):
    """Yearly maps of the area — ONE Earth Engine request — or the offline cube. Returns (cube, error)."""
    err = None
    if live:
        try:
            return geoai_engine.get_change_cube(var_key, bounds, start, end), None
        except Exception as e:
            err = f"{OFFLINE_NOTE} (Earth Engine: {str(e)[:120]})"
    return demo_data.offline_cube(var_key, dict(preset=preset, polygon=None), bounds, start, end), err


@st.cache_data(show_spinner=False, ttl=6 * 3600, max_entries=40)
def change_layers(var_key, lat, lon, radius_km, polygon, preset, start, end, alpha, live):
    """Time-lapse frames, before/after and per-pixel trend of the chosen area, computed locally from the cube."""
    region = dict(lat=lat, lon=lon, radius_km=radius_km, polygon=[list(p) for p in polygon] if polygon else None)
    bounds = tuple(geoai_engine.change_bounds(region, nv.get(var_key)))
    cube, err = fetch_cube(var_key, bounds, preset, start, end, live)
    layers = change_maps.build_change_layers(cube, var_key, alpha, region)
    v = nv.get(var_key)
    layers.update(var_short=v.short, var_plain=v.plain, up_word=v.up_word, down_word=v.down_word, area=region)
    if math.sqrt(geoai_engine.region_area_km2(region)) < 2 * v.pixel_m / 1000:
        layers["area_note"] = (f"ℹ️ This data comes in {nv.fmt_distance(v.pixel_m)} squares, bigger than your area, "
                               "so your area shows only one or a few of them.")
    return layers, err


def night_basemap() -> dict:
    """Night background for the globe: yearly VIIRS lights of the chosen year from Earth Engine,
    else NASA Black Marble 2012 / 2016."""
    if gee_live:
        years = list(geoai_engine.NIGHT_YEARS)
        year = st.session_state.night_year if st.session_state.night_year in years else years[-1]
        try:
            tiles = geoai_engine.night_map_tiles([year])
            return dict(live=True, years=years, year=year, tiles={str(y): t for y, t in tiles.items()})
        except Exception:
            pass
    years = [2012, 2016]
    return dict(live=False, years=years, year=st.session_state.night_year if st.session_state.night_year in years else 2016)


def is_synthetic(df) -> bool:
    return "source" in df and df["source"].astype(str).str.startswith("Synthetic").any()


def source_of(df) -> str:
    return str(df["source"].iloc[0]) if "source" in df and len(df) else ""


def data_kind(df) -> str:
    return "simulated" if is_synthetic(df) else ("saved NASA data" if "cached" in source_of(df) else "live NASA data")


# ─────────────────────────────────────────────
# Presentation helpers
# ─────────────────────────────────────────────

def dir_color(var: nv.Variable, r: trends.TrendResult) -> str:
    if not r.significant:
        return ui.NS_COLOR
    return "#" + (var.palette[3] if r.tendency == "rising" else var.palette[1])


def place_name(region: dict) -> str:
    return region.get("name") or f"{region['lat']:.3f}, {region['lon']:.3f}"


def question_for(var: nv.Variable, place: str) -> str:
    return f"{var.question.rstrip('?')} in {place}?"


PLOTLY_CONFIG = {"displayModeBar": False}


def trend_figure(df, r, var):
    monthly = trends.to_monthly(df)
    ann = trends.annual_means(monthly)
    col = dir_color(var, r)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly["date"], y=monthly["value"], name="Each month", mode="lines",
        line=dict(color=ui.rgba(ui.ACCENT, 0.5), width=1.2),
        hovertemplate="%{x|%b %Y}: %{y:.4g} " + var.units + "<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ann["date"], y=ann["value"], name="Yearly average", mode="markers",
        marker=dict(size=10, color=ui.TEXT, line=dict(color=ui.BG, width=2)),
        hovertemplate="%{x|%Y}: %{y:.4g} " + var.units + "<extra></extra>",
    ))
    if r.direction != "insufficient data":
        xs = pd.date_range(monthly["date"].min(), monthly["date"].max(), periods=60)
        tx = trends.decimal_year(xs)
        if np.isfinite(r.slope_ci_low) and np.isfinite(r.slope_ci_high):
            a, b = r.trend_line(tx, r.slope_ci_low), r.trend_line(tx, r.slope_ci_high)
            fig.add_trace(go.Scatter(x=xs, y=np.maximum(a, b), line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=xs, y=np.minimum(a, b), fill="tonexty", line=dict(width=0), hoverinfo="skip",
                                     fillcolor=ui.rgba(col, 0.2), name="Likely range of the direction"))
        fig.add_trace(go.Scatter(
            x=xs, y=r.trend_line(tx), mode="lines", hoverinfo="skip",
            name="Overall direction (trend)" + ("" if r.significant else " — not clear"),
            line=dict(color=col, width=4, dash="solid" if r.significant else "dash"),
        ))
    fig.update_layout(title="What the satellite saw, month by month", height=380,
                      yaxis_title=f"{var.plain} ({var.units})", hovermode="x unified",
                      legend=dict(orientation="h", y=-0.14, bgcolor="rgba(0,0,0,0)"), **ui.PLOTLY)
    return fig


def anomaly_figure(df, r, var):
    ds = trends.deseasonalize(trends.to_monthly(df))
    fig = go.Figure(go.Bar(x=ds["date"], y=ds["anomaly"],
                           marker_color=np.where(ds["anomaly"] >= 0, "#" + var.palette[3], "#" + var.palette[1]),
                           hovertemplate="%{x|%b %Y}: %{y:+.3g} " + var.units + "<extra></extra>"))
    if r.direction != "insufficient data":
        xs = pd.date_range(ds["date"].min(), ds["date"].max(), periods=60)
        fig.add_trace(go.Scatter(x=xs, y=r.trend_line(trends.decimal_year(xs)) - r.mean_level, mode="lines",
                                 line=dict(color=ui.TEXT, width=3, dash="solid" if r.significant else "dash")))
    fig.update_layout(title="Each month compared with a normal month (seasons removed)", height=280, showlegend=False,
                      bargap=0, yaxis_title=var.units, **ui.PLOTLY)
    return fig


def seasonal_figure(df, var):
    m = trends.to_monthly(df)
    first, last = m["year"].min(), m["year"].max()
    half = (first + last) // 2
    fig = go.Figure()
    for label, sel, color in [(f"{first}–{half}", m["year"] <= half, ui.MUTED), (f"{half + 1}–{last}", m["year"] > half, ui.ACCENT)]:
        c = m[sel].groupby("month")["value"].mean()
        fig.add_trace(go.Scatter(x=[pd.Timestamp(2000, i, 1).strftime("%b") for i in c.index], y=c.values,
                                 name=label, mode="lines+markers", line=dict(color=color, width=3)))
    fig.update_layout(title="A typical year: early years vs recent years", height=280, yaxis_title=var.units,
                      legend=dict(orientation="h", y=-0.2), **ui.PLOTLY)
    return fig


def sparkline(df, r, color):
    ann = trends.annual_means(trends.to_monthly(df))
    fig = go.Figure(go.Scatter(x=ann["year"], y=ann["value"], mode="markers", marker=dict(size=5, color="#AEB5C8"),
                               hovertemplate="%{x}: %{y:.3g}<extra></extra>"))
    if r.direction != "insufficient data":
        xs = np.linspace(ann["year"].min(), ann["year"].max(), 20)
        fig.add_trace(go.Scatter(x=xs, y=r.trend_line(xs + 0.5), mode="lines", hoverinfo="skip",
                                 line=dict(color=color, width=3, dash="solid" if r.significant else "dash")))
    fig.update_layout(height=100, showlegend=False, margin=dict(t=4, b=4, l=4, r=4),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# ─────────────────────────────────────────────
# Current selection
# ─────────────────────────────────────────────

region = st.session_state.region
var = nv.get(st.session_state.var_key or st.session_state.last_var)
clamp_years(var)
y0, y1 = st.session_state.years
alpha = st.session_state.alpha or st.session_state.last_alpha
place = place_name(region)

# "Watch it change" (globe button or an example): fetch the yearly maps before the globe renders so they appear right away
if st.session_state.change_request:
    st.session_state.change_request = False
    req = dict(var=var.key, lat=round(region["lat"], 5), lon=round(region["lon"], 5), radius=region["radius_km"],
               polygon=poly_tuple(region), years=(y0, y1),
               preset=region.get("preset") if not region.get("polygon") else None)
    with st.spinner(f"Getting {len(range(y0, y1 + 1))} years of NASA maps for {place}…"
                    + (" This dataset takes about 15 seconds." if var.pixel_m < 100 or var.key == "snow_cover" else "")):
        change_layers(req["var"], req["lat"], req["lon"], req["radius"], req["polygon"], req["preset"],
                      y0, y1, alpha, gee_live)
    st.session_state.change_req = req


def change_for_map():
    """
    Map layers while they still match the chosen variable, years and area (strictness updates them instantly).
    A new place, radius or outline hides them until "Watch it change" is pressed again; inspecting a spot
    inside them keeps them.
    """
    req = st.session_state.change_req
    if not req or req["var"] != var.key or req["years"] != (y0, y1):
        return None, None
    same_area = (req["lat"], req["lon"], req["radius"], req["polygon"]) == (
        round(region["lat"], 5), round(region["lon"], 5), region["radius_km"], poly_tuple(region))
    if not same_area and not region.get("within_change"):
        return None, None
    return change_layers(req["var"], req["lat"], req["lon"], req["radius"], req["polygon"], req["preset"],
                         y0, y1, alpha, gee_live)


change_data, change_err = change_for_map()


# ─────────────────────────────────────────────
# Top bar, welcome, examples
# ─────────────────────────────────────────────

with st.container(key="topbar"):
    top_l, top_r = st.columns([6, 1.15], vertical_alignment="center")
top_l.markdown(ui.top_bar(gee_live, groq_ok), unsafe_allow_html=True)
with top_r.popover("❔ Help", width="stretch"):
    st.markdown("""
**1 · Pick a place** — click anywhere on the globe, search for a city or region (🔍), draw an exact area (⬠),
or open one of the examples.

**2 · Pick what to look at** — choose a topic (plants, heat, water, snow, people), then a measurement.

**3 · Read the answer** — *Yes / Maybe / No clear change*, how sure we are, and how much it changed.

**🎬 Watch it change** — a time-lapse, a before/after slider and a map of where it is really changing.
Click any coloured spot to see that spot's own answer.

**⚖️ Compare places** — press ⚖ on the globe, then click two or more places.

**Globe** — drag to rotate, scroll to zoom (on a phone: two fingers), ⌂ flies back to your place,
🌃 / 🛰 switch the background map, and the year menu next to them picks its year (e.g. Kakhovka in 2021 vs 2025).
With 🛰, the satellite photo follows the time-lapse year.
""")

if not gee_live:
    st.markdown('<div class="td-banner">🧪 <b>Demo mode.</b> The examples use real NASA data saved with this app. '
                'Other places you click show <b>simulated</b> data (clearly marked). To explore any place on Earth with '
                'live NASA data, connect Google Earth Engine — see the README.</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 1 · Pick a place: examples + globe
# ─────────────────────────────────────────────

st.markdown(ui.step_header(1, "Pick a place", "open an example, or click anywhere on the globe"), unsafe_allow_html=True)
example_items = []
for ex in regions.LANDING_EXAMPLES:
    ev = nv.get(ex["variable"])
    example_items.append(dict(icon="⚖️" if ex["kind"] == "compare" else ev.icon, label=ex["label"],
                              what=ev.plain, context=ex["context"], compare=ex["kind"] == "compare"))
examples_strip.examples_strip(example_items, st.session_state.example_active, key="examples", on_open=on_example)

preset_vars = {k: preset_variable(k)[0] for k in regions.PRESETS}
map_data = dict(
    region=dict(name=place, lat=region["lat"], lon=region["lon"], radius_km=region["radius_km"],
                polygon=region.get("polygon"), area_km2=region.get("area_km2") or 0),
    presets=[dict(key=k, name=p["name"], lat=p["lat"], lon=p["lon"], variable=preset_vars[k])
             for k, p in regions.PRESETS.items()],
    cases=[],
    compare=[dict(name=c["name"], lat=c["lat"], lon=c["lon"], radius_km=c["radius_km"],
                  color=ui.REGION_COLORS[i % len(ui.REGION_COLORS)], label=chr(65 + i))
             for i, c in enumerate(st.session_state.cmp_list)],
    change=change_data,
    mode_hint=st.session_state.mode_hint,
    night=night_basemap(),
    inspect_km=inspect_radius(var),
    ack=st.session_state.map_ack,
    height=560,
)
map_component.explorer_map(map_data, key="globe", on_event=on_map_event)
if change_err:
    st.info(change_err)


# ─────────────────────────────────────────────
# ② What to look at
# ─────────────────────────────────────────────

with st.container(key="inv_bar"):
    st.markdown(ui.step_header(2, "What do you want to look at?", "pick a topic, then a measurement"),
                unsafe_allow_html=True)
    st.segmented_control("Topic", nv.GROUPS, key="topic", on_change=on_topic_change, label_visibility="collapsed",
                         format_func=lambda g: f"{nv.TOPIC_ICONS[g]} {g}")
    topic_vars = [k for k, v in nv.VARIABLES.items() if v.group == (st.session_state.topic or var.group)]
    st.pills("Measurement", topic_vars, key="var_key", on_change=on_var_change,
             format_func=lambda k: f"{nv.get(k).icon} {nv.get(k).plain}", label_visibility="collapsed")
    st.markdown(f'<div class="td-question">❓ {ui.esc(var.question)} <span>— {ui.esc(var.explain)} '
                f'Measured by {ui.esc(var.mission)} ({ui.esc(var.agency)}) since {var.start_year}.</span></div>',
                unsafe_allow_html=True)
    c1, c3 = st.columns([4.2, 1.2], vertical_alignment="bottom")
    c1.slider("Which years?", var.start_year, var.last_year, key="years",
              help="More years make it easier to tell a real change from normal ups and downs.")
    with c3.popover("⚙️ Advanced", width="stretch"):
        st.segmented_control("How strict should the test be?", [0.01, 0.05, 0.1], key="alpha",
                             format_func=lambda a: {0.01: "Very strict", 0.05: "Standard", 0.1: "Relaxed"}[a],
                             on_change=restore_if_none, args=("alpha", "last_alpha"),
                             help="Scientists usually use 'Standard' (a 1-in-20 chance of a false alarm, α = 0.05). "
                                  "'Very strict' is α = 0.01, 'Relaxed' is α = 0.10.")
        st.markdown('<div style="height:0.6rem"></div>', unsafe_allow_html=True)
        st.caption("The maps always cover the area you picked. Change its size with the ⌀ slider on the globe, "
                   "or draw your own outline with ⬠.")
    notes = []
    if y1 - y0 + 1 < trends.SHORT_RECORD_YEARS:
        notes.append(f"⚠️ Only {y1 - y0 + 1} years selected — slow changes are easy to miss. Use more years if you can.")
    if change_data:
        tr = change_data["trend"]
        notes.append(f"🗺️ On the map: {len(change_data['years'])} years of maps ({change_data['years'][0]}–"
                     f"{change_data['years'][-1]}). {tr['share_rising']:.0%} of your area is clearly {var.up_word}, "
                     f"{tr['share_falling']:.0%} clearly {var.down_word}.")
        if change_data.get("area_note"):
            notes.append(change_data["area_note"])
    else:
        notes.append("🎬 To see it change on the map, press “Watch it change” under the globe.")
    if notes:
        st.caption(" · ".join(notes))

st.markdown(f"""<div class="td-headline">{ui.step_header(3, "The answer", "")}
  <div class="t">{var.icon} {ui.esc(question_for(var, place))} <span>· {y0}–{y1}</span></div>
  <div class="s">📍 {region['lat']:.3f}°, {region['lon']:.3f}° · {'drawn area · ' + format(region.get('area_km2', 0), ',.1f') + ' km²'
      if region.get('polygon') else f"within {region['radius_km']:g} km"} · data: {ui.esc(var.mission)} ({ui.esc(var.agency)})</div></div>""",
            unsafe_allow_html=True)

with st.container(key="view_sel"):
    st.segmented_control("View", list(VIEWS), key="view", format_func=VIEWS.get, label_visibility="collapsed",
                         on_change=restore_if_none, args=("view", "last_view"))
view = st.session_state.view or st.session_state.last_view


# ══════════════════════════════════════════════
# VIEW · The answer
# ══════════════════════════════════════════════

def render_trend():
    with st.spinner(f"Looking at {var.plain.lower()} in {place} ({var.mission})…"
                    + (f" {var.notes}" if "minute" in var.notes else "")):
        df, res, err = analyze(var.key, region, y0, y1, alpha)
    if err:
        st.info(err)
    col = dir_color(var, res)
    title, label = plain.answer(res, var)
    level, _ = plain.confidence(res.p_value, alpha)
    context = regions.PRESETS[region["preset"]]["blurb"] if region.get("preset") else ""
    st.markdown(f"""
    <div class="td-answer" style="border-color:{ui.rgba(col, 0.55)};background:linear-gradient(120deg,{ui.rgba(col, 0.16)},rgba(12,15,24,0.78) 60%)">
      <div><div class="q">{ui.esc(var.question)} · {res.first_year}–{res.last_year}</div>
        <div class="a" style="color:{col}">{ui.esc(title)}</div>
        <div class="s">{ui.esc(llm_summary.headline(res, var, place))}</div></div>
      <div class="td-sure"><div class="k">How sure are we?</div>{ui.confidence_dots(level, col)}
        <div class="l">{ui.esc(label)}</div><div class="c">{ui.esc(plain.chance_text(res.p_value))}</div></div>
    </div>""", unsafe_allow_html=True)

    if res.direction != "insufficient data":
        big, meaning = plain.how_much(res, var)
        share, steady = plain.consistency(res, var)
        noise = res.change_vs_variability
        st.markdown(ui.facts_row([
            ui.fact("📏 How much", big, meaning if res.significant else f"{meaning} — but it could be chance",
                    plain.per_decade(res, var), col),
            ui.fact("📈 How steady", share, "of year-to-year comparisons went the same way",
                    "A coin toss gives about 50% — closer to 100% means steadier."),
            ui.fact("🎢 Compared with normal swings", f"{fmt(noise)}×" if noise is not None else "–",
                    "the normal year-to-year ups and downs", plain.noise_text(res)),
        ]), unsafe_allow_html=True)

    st.plotly_chart(trend_figure(df, res, var), width="stretch", config=PLOTLY_CONFIG)
    st.caption(("⚠️ Simulated data — " if is_synthetic(df) else "") +
               "The thin line is each month (it goes up and down with the seasons). White dots are yearly averages. "
               "The thick line is the overall direction — dashed when there is no clear change. "
               f"Source: {source_of(df)}.")

    left, right = st.columns([1.45, 1], gap="large")
    with left, st.container(key="glass_summary"):
        st.markdown('<div class="td-label">🗒️ In plain words</div>', unsafe_allow_html=True)
        ai_key = (var.key, place, y0, y1, alpha, round(res.slope, 9) if np.isfinite(res.slope) else None)
        ai = st.session_state.ai_summaries.get(ai_key)
        summary_md = ai[0] if ai else llm_summary.template_summary(res, var, place, context)
        st.markdown(summary_md)
        if ai:
            st.caption(f"Written by {ai[1]} from the computed numbers only — double-check before sharing.")
        elif groq_ok and st.button("✨ Explain it with AI", key="ai_trend"):
            with st.spinner("Writing…"):
                st.session_state.ai_summaries[ai_key] = llm_summary.generate_trend_summary(res, var, place, context)
            st.rerun()
    with right, st.container(key="glass_side"):
        st.markdown('<div class="td-label">📅 Compare two years</div>', unsafe_allow_html=True)
        ann = trends.annual_means(trends.to_monthly(df))
        if len(ann) >= 2:
            yrs = ann["year"].tolist()
            b1, b2 = st.columns(2)
            ya = b1.selectbox("From", yrs, index=0, key="yy_a")
            yb = b2.selectbox("To", yrs, index=len(yrs) - 1, key="yy_b")
            va = float(ann.loc[ann["year"] == ya, "value"].iloc[0])
            vb = float(ann.loc[ann["year"] == yb, "value"].iloc[0])
            st.markdown(ui.kpi(f"{ya} → {yb}", f"{fmt(vb - va, True)} {ui.esc(var.units)}",
                               f"{fmt(va)} → {fmt(vb)}. Careful: any two single years can differ by chance — "
                               "that's why the answer above uses every month of every year."),
                        unsafe_allow_html=True)
        if res.warnings or var.notes:
            st.markdown('<div class="td-label" style="margin-top:0.9rem">🧭 Good to know</div>', unsafe_allow_html=True)
            for w in res.warnings + ([var.notes] if var.notes else []):
                st.markdown(f'<div class="td-note">{ui.esc(w)}</div>', unsafe_allow_html=True)
        out = trends.to_monthly(df)[["date", "value"]].copy()
        if res.direction != "insufficient data":
            out["trend_line"] = res.trend_line(trends.decimal_year(out["date"]))
        d1, d2 = st.columns(2)
        d1.download_button("⬇ Data (CSV)", out.to_csv(index=False), file_name=f"trend_{var.key}_{y0}-{y1}.csv",
                           mime="text/csv", width="stretch")
        d2.download_button("⬇ Summary", summary_md + "\n\n---\n" + llm_summary.facts_block(res, var, place, context),
                           file_name=f"trend_{var.key}_summary.md", mime="text/markdown", width="stretch")

    with st.expander("🔬 For experts: statistics, extra charts and method"):
        a1, a2 = st.columns(2)
        a1.plotly_chart(anomaly_figure(df, res, var), width="stretch", config=PLOTLY_CONFIG)
        a2.plotly_chart(seasonal_figure(df, var), width="stretch", config=PLOTLY_CONFIG)
        rows = {
            "Verdict": f"{res.direction} ({res.strength}) at α = {alpha}",
            "Method": res.method,
            "Observations": f"{res.n_obs} monthly means over {res.n_years} years ({res.first_year}–{res.last_year})",
            "Mann-Kendall S / Var(S) / Z": f"{fmt(res.mk_s)} / {fmt(res.mk_var)} / {fmt(res.mk_z)}",
            "Covariance correction applied": "yes" if res.covariance_corrected else "no",
            "p-value (two-sided)": fmt_p(res.p_value),
            "Kendall's tau": fmt(res.tau),
            "Sen's slope (per year)": f"{fmt(res.slope, True)} {var.units}",
            f"{int(round(res.ci_level * 100))}% CI of slope": f"{fmt(res.slope_ci_low, True)} … {fmt(res.slope_ci_high, True)}",
            "Total change": llm_summary.change_text(res, var),
            "Change ÷ year-to-year variability": fmt(res.change_vs_variability),
            "Linear regression slope (deseasonalized)": f"{fmt(res.ols_slope, True)} {var.units}/yr",
            "Linear regression p (autocorrelation-adjusted)": fmt_p(res.ols_p_value),
            "Linear regression R²": fmt(res.ols_r2),
            "Lag-1 autocorrelation of residuals": fmt(res.lag1_autocorr),
            "Data": f"{var.name} · {var.collection} · ~{nv.fmt_distance(var.pixel_m)} pixels · {data_kind(df)}",
        }
        st.dataframe(pd.DataFrame(rows.items(), columns=["Statistic", "Value"]), hide_index=True, width="stretch")


# ══════════════════════════════════════════════
# VIEW · Compare places
# ══════════════════════════════════════════════

def render_compare():
    st.markdown('<div class="td-label" style="margin-top:0.6rem">Does the same thing happen everywhere? Try one of these:</div>',
                unsafe_allow_html=True)
    cols = st.columns(len(regions.STORIES))
    for c, s in zip(cols, regions.STORIES):
        with c, st.container(key=f"glass_story_{s['key']}"):
            active = st.session_state.cmp_story == s["key"]
            st.markdown(f"**{nv.get(s['variable']).icon} {ui.esc(s['title'])}**  \n"
                        f"<span style='color:{ui.AMBER};font-size:0.8rem'>📍 {ui.esc(s.get('places', ''))}</span>",
                        unsafe_allow_html=True)
            st.caption(s["question"])
            st.button("✓ Showing" if active else "▶ Compare", key=f"story_{s['key']}", width="stretch",
                      type="secondary" if active else "primary", on_click=load_story, args=(s["key"],))

    with st.container(key="glass_cmp"):
        t1, t2 = st.columns([3, 1.2], vertical_alignment="center")
        t1.markdown(f'<div class="td-label">Places being compared · {ui.esc(var.plain)} · {y0}–{y1}</div>'
                    '<div style="font-size:0.85rem;color:#8A93A8">To add places: press ⚖ on the globe, then click places. '
                    'Or add the place you are looking at now.</div>', unsafe_allow_html=True)
        t2.button("➕ Add current place", width="stretch", on_click=add_current_to_compare)
        lst = st.session_state.cmp_list
        if not lst:
            st.markdown('<div class="td-empty">No places yet — pick one of the comparisons above, or press ⚖ on the globe '
                        'and click two or more places.</div>', unsafe_allow_html=True)
        for i, c in enumerate(lst):
            with st.container(key=f"row_cmp_{i}"):              # stays one row on phones
                r1, r2 = st.columns([12, 1], vertical_alignment="center")
            color = ui.REGION_COLORS[i % len(ui.REGION_COLORS)]
            r1.markdown(f'<span class="td-badge" style="background:{color};color:#05060A;border:none">{chr(65 + i)}</span> '
                        f'&nbsp;<b>{ui.esc(c["name"])}</b> <span style="color:#8A93A8;font-size:0.82rem">· '
                        f'{c["lat"]:.2f}°, {c["lon"]:.2f}° · within {c["radius_km"]:g} km</span>', unsafe_allow_html=True)
            r2.button("✕", key=f"rm_{i}", on_click=remove_compare, args=(i,), help="Remove")
        b1, b2 = st.columns([3, 1])
        run = b1.button(f"⚖️  Compare {len(lst)} places", type="primary", width="stretch", disabled=len(lst) < 2)
        b2.button("Clear", width="stretch", on_click=clear_compare, disabled=not lst)

    if (run or st.session_state.cmp_autorun) and len(st.session_state.cmp_list) >= 2:
        st.session_state.cmp_autorun = False
        items = []
        with st.spinner(f"Looking at {var.plain.lower()} in {len(st.session_state.cmp_list)} places…"):
            for c in st.session_state.cmp_list:
                reg_c = dict(name=c["name"], lat=c["lat"], lon=c["lon"], radius_km=c["radius_km"],
                             polygon=None, preset=c.get("preset"))
                dfc, rc, errc = analyze(var.key, reg_c, y0, y1, alpha)
                items.append(dict(region=reg_c, df=dfc, res=rc, err=errc))
        st.session_state.cmp_results = dict(var=var.key, years=(y0, y1), alpha=alpha, items=items,
                                            story=st.session_state.cmp_story)

    cr = st.session_state.cmp_results
    if not cr:
        return
    if (cr["var"], cr["years"], cr["alpha"]) != (var.key, (y0, y1), alpha):
        st.info("You changed what to look at or the years — press Compare again to update.")
    cvar = nv.get(cr["var"])
    items = cr["items"]
    if any(it["err"] for it in items):
        st.info(OFFLINE_NOTE)
    rows = [(it["region"]["name"], it["res"]) for it in items]
    ups = [p for p, r in rows if r.significant and r.tendency == "rising"]
    downs = [p for p, r in rows if r.significant and r.tendency == "falling"]
    if ups and downs:
        st.markdown(f"""<div class="td-answer" style="grid-template-columns:1fr;border-color:{ui.rgba(ui.AMBER, 0.55)};
            background:linear-gradient(120deg,{ui.rgba(ui.AMBER, 0.14)},rgba(12,15,24,0.78) 60%)">
            <div><div class="q">{ui.esc(cvar.question)}</div>
            <div class="a" style="color:{ui.AMBER}">⇅ It depends where you look!</div>
            <div class="s">In <b>{ui.esc(', '.join(ups))}</b> {ui.esc(cvar.up_phrase)}; in <b>{ui.esc(', '.join(downs))}</b>
            {ui.esc(cvar.down_phrase)}. Both are clear, real changes.</div></div></div>""", unsafe_allow_html=True)

    cards = []
    for i, it in enumerate(items):
        r = it["res"]
        title, label = plain.answer(r, cvar)
        big, meaning = plain.how_much(r, cvar)
        color = ui.REGION_COLORS[i % len(ui.REGION_COLORS)]
        cards.append(ui.fact(f"<span class='td-badge' style='background:{color};color:#05060A;border:none'>{chr(65 + i)}</span> "
                             f"{ui.esc(it['region']['name'][:48])}",
                             ui.esc(title.replace('Yes — ', '').capitalize()), f"{big} {meaning}",
                             f"{label} · {data_kind(it['df'])}", dir_color(cvar, r)))
    st.markdown(ui.facts_row(cards), unsafe_allow_html=True)

    g1, g2 = st.columns([1.7, 1], gap="large")
    with g1:
        fig = go.Figure()
        for i, it in enumerate(items):
            r, color = it["res"], ui.REGION_COLORS[i % len(ui.REGION_COLORS)]
            ann = trends.annual_means(trends.to_monthly(it["df"]))
            base = r.mean_level if np.isfinite(r.mean_level) else ann["value"].mean()
            name = f"{chr(65 + i)} · {it['region']['name']}"
            fig.add_trace(go.Scatter(x=ann["year"], y=ann["value"] - base, mode="markers", name=name, legendgroup=name,
                                     marker=dict(size=8, color=color)))
            if r.direction != "insufficient data":
                xs = np.linspace(ann["year"].min(), ann["year"].max(), 30)
                fig.add_trace(go.Scatter(x=xs, y=r.trend_line(xs + 0.5) - base, mode="lines", showlegend=False,
                                         legendgroup=name, hoverinfo="skip",
                                         line=dict(color=color, width=3.5, dash="solid" if r.significant else "dash")))
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.25)")
        fig.update_layout(title="Each place compared with its own average", height=360,
                          yaxis_title=f"Difference ({cvar.units})", legend=dict(orientation="h", y=-0.15), **ui.PLOTLY)
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    with g2:
        fig2 = go.Figure(go.Bar(
            y=[chr(65 + i) for i in range(len(items))], x=[it["res"].slope * 10 for it in items], orientation="h",
            marker_color=[ui.REGION_COLORS[i % len(ui.REGION_COLORS)] for i in range(len(items))],
            error_x=dict(type="data", array=[(it["res"].slope_ci_high - it["res"].slope) * 10 for it in items],
                         arrayminus=[(it["res"].slope - it["res"].slope_ci_low) * 10 for it in items],
                         color=ui.MUTED, thickness=1.5),
            hovertemplate="%{y}: %{x:.3g} " + cvar.units + " per 10 years<extra></extra>"))
        fig2.add_vline(x=0, line_color="rgba(255,255,255,0.35)")
        fig2.update_layout(title="Change every 10 years (with likely range)", height=360,
                           xaxis_title=f"{cvar.units} per 10 years", **ui.PLOTLY)
        fig2.update_yaxes(autorange="reversed")
        st.plotly_chart(fig2, width="stretch", config=PLOTLY_CONFIG)

    story = next((s for s in regions.STORIES if s["key"] == cr.get("story")), None)
    if story and story["variable"] == cr["var"]:
        st.markdown(f'<div class="td-note"><b>What we found when we checked this (Sept 2026):</b> {ui.esc(story["finding"])}</div>',
                    unsafe_allow_html=True)
    with st.container(key="glass_cmp_summary"):
        st.markdown('<div class="td-label">🗒️ In plain words</div>', unsafe_allow_html=True)
        key = ("cmp", cr["var"], cr["years"], tuple((p, round(r.slope, 9) if np.isfinite(r.slope) else None) for p, r in rows))
        ai = st.session_state.ai_summaries.get(key)
        st.markdown(ai[0] if ai else llm_summary.template_comparison(rows, cvar))
        if not ai and groq_ok and st.button("✨ Explain it with AI", key="ai_cmp"):
            with st.spinner("Writing…"):
                st.session_state.ai_summaries[key] = llm_summary.generate_comparison_summary(
                    rows, cvar, story["question"] if story else "")
            st.rerun()


# ══════════════════════════════════════════════
# VIEW · What else is changing here?
# ══════════════════════════════════════════════

def render_scan():
    with st.container(key="glass_scan"):
        s1, s2, s3 = st.columns([3, 1.4, 1.2], vertical_alignment="center")
        s1.markdown(f'<div class="td-label">Check everything at once for {ui.esc(place)}</div>'
                    f'<div style="font-size:0.86rem;color:#8A93A8">We ask every question — greener? hotter? wetter? '
                    f'more snow? more lights? — for {y0}–{y1} and show which ones have a clear answer.</div>',
                    unsafe_allow_html=True)
        include_slow = s2.toggle("Include slow, detailed data", value=False,
                                 help="The 30 m and 3-hourly datasets can take about a minute each.")
        run = s3.button("🔍  Check everything", type="primary", width="stretch")
    params = (place, round(region["lat"], 4), round(region["lon"], 4), region["radius_km"], poly_tuple(region),
              y0, y1, alpha, include_slow, gee_live)
    if run:
        keys = [k for k, v in nv.VARIABLES.items() if include_slow or not (v.preprocess or k == "soil_moisture_smap")]
        reg_now = dict(region)
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()

        def job(k):
            add_script_run_ctx(threading.current_thread(), ctx)
            v = nv.get(k)
            a, b = max(y0, v.start_year), min(y1, v.last_year)
            if b - a + 1 < trends.MIN_YEARS:
                return k, None, None, f"no data for {y0}–{y1}"
            return (k, *analyze(k, reg_now, a, b, alpha))

        prog = st.progress(0.0, text="Checking NASA data…")
        out = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(job, k) for k in keys]
            for i, f in enumerate(futures, 1):
                out.append(f.result())
                prog.progress(i / len(keys), text=f"Checked {i}/{len(keys)} · {nv.get(out[-1][0]).plain}")
        prog.empty()
        st.session_state.scan_results = (params, out)

    sr = st.session_state.scan_results
    if not sr:
        st.markdown('<div class="td-empty" style="margin-top:1rem">Press <b>🔍 Check everything</b> to find out what '
                    'is changing here.</div>', unsafe_allow_html=True)
        return
    sparams, out = sr
    if sparams != params:
        st.info("You moved to another place or changed the settings — press Check everything to update.")
    ok = [(k, d, r, e) for k, d, r, e in out if r is not None and r.direction != "insufficient data"]
    q = trends.benjamini_hochberg([r.p_value for _, _, r, _ in ok])
    summary_rows = []
    for (k, d, r, e), qv in zip(ok, q):
        v = nv.get(k)
        sig = bool(qv < sparams[7])
        big, meaning = plain.how_much(r, v)
        answer_txt = (v.up_phrase if r.tendency == "rising" else v.down_phrase) if sig else "no clear change"
        summary_rows.append(dict(variable=v.plain, icon=v.icon, answer=answer_txt, big=big, meaning=meaning,
                                 direction=r.tendency if sig else "no clear change", significant_fdr=sig,
                                 rate=llm_summary.rate_text(r, v), change=llm_summary.change_text(r, v), q=fmt_p(qv)))
    with st.container(key="glass_scan_summary"):
        st.markdown(llm_summary.template_scan(summary_rows, sparams[0]))

    order = sorted(range(len(ok)), key=lambda i: (not summary_rows[i]["significant_fdr"], q[i]))
    ncol = 3
    for start in range(0, len(order), ncol):
        cols = st.columns(ncol)
        for c, idx in zip(cols, order[start:start + ncol]):
            k, d, r, e = ok[idx]
            v, qv, sig = nv.get(k), q[idx], summary_rows[idx]["significant_fdr"]
            color = ("#" + (v.palette[3] if r.tendency == "rising" else v.palette[1])) if sig else ui.NS_COLOR
            label = (("▲ " + v.up_word) if r.tendency == "rising" else ("▼ " + v.down_word)) if sig else "● no clear change"
            with c, st.container(key=f"glass_scan_{k}"):
                st.markdown(f"""<div class="td-scan-card" style="border:none;background:none;padding:0">
                  <div class="h"><div><div class="n">{v.icon} {ui.esc(v.plain)}</div>
                  <div class="m">{ui.esc(v.question)}</div></div>{ui.badge(label, color)}</div>
                  <div class="r">{ui.esc(summary_rows[idx]['big'])} {ui.esc(summary_rows[idx]['meaning'])}</div></div>""",
                            unsafe_allow_html=True)
                st.plotly_chart(sparkline(d, r, color), width="stretch", config=PLOTLY_CONFIG, key=f"spark_{k}")
                st.button("See the answer →", key=f"open_{k}", width="stretch", on_click=open_variable, args=(k,))
    skipped = [(k, e) for k, d, r, e in out if r is None or r.direction == "insufficient data"]
    if skipped:
        st.caption("Not checked: " + "; ".join(f"{nv.get(k).plain} ({e or 'not enough data'})" for k, e in skipped))
    table = pd.DataFrame([{
        "Question": nv.get(k).question, "Measurement": nv.get(k).name, "Mission": nv.get(k).mission,
        "Years": f"{r.first_year}–{r.last_year}", "Answer": summary_rows[i]["answer"],
        "Rate / yr": f"{fmt(r.slope, True)} {nv.get(k).units}", "Total change": llm_summary.change_text(r, nv.get(k)),
        "p": fmt_p(r.p_value), "q (FDR)": fmt_p(qv), "Data": data_kind(d),
    } for i, ((k, d, r, e), qv) in enumerate(zip(ok, q))])
    st.download_button("⬇ Download results (CSV)", table.to_csv(index=False), file_name="trend_scan.csv", mime="text/csv")


# ══════════════════════════════════════════════
# VIEW · How it works
# ══════════════════════════════════════════════

def render_method():
    m1, m2 = st.columns([1.2, 1], gap="large")
    with m1:
        st.markdown("### How Trend Detective works")
        st.markdown("""
**1 · Satellites measure the same place again and again.** NASA satellites have photographed every spot on Earth
every few days for more than 20 years. For your place we take one average for every month.

**2 · Seasons are not a trend.** Summer is always greener and hotter than winter. So we only ever compare
January with January, July with July — across the years.

**3 · Is it a real change, or just luck?** Imagine flipping a coin every year: "was this year higher than an earlier
year?" With no real change you'd get about half heads, half tails. If later years win almost every time, luck
becomes a very unlikely explanation. That is what the *Mann-Kendall test* measures, and what "How sure are we?" shows.
Neighbouring months are alike (a wet March is often followed by a wet April), and our test corrects for that so it
doesn't cry wolf.

**4 · How much?** We take the typical change per year — the middle of all the year-to-year changes, so one strange
year can't distort it — and add it up over the whole period.

**5 · Where?** *Watch it change* downloads a small map for every year around your place, in one go. You can play them
as a time-lapse, compare the first and last years, or see which spots are really changing.

**6 · What "real change" does not mean.** It tells you *that* something changed, not *why*. A dam breaking or a
forest fire shows up as a change too — look at the chart to see if it was sudden or slow.
""")
        with st.expander("🔬 For scientists: the exact methods"):
            st.markdown("""
- **Monthly series:** region means per month computed server-side in Google Earth Engine; HLS scenes Fmask-masked
  (cloud, shadow, snow).
- **Significance:** seasonal Mann-Kendall test (Hirsch, Slack & Smith 1982) with the Hirsch & Slack (1984)
  covariance correction for dependence between months. The textbook seasonal test flagged 12–25 % of trend-free,
  autocorrelated series at α = 0.05 in our simulations; the corrected test stays ≤ 5 % (see `tests/test_trends.py`).
- **Magnitude:** seasonal Sen's slope with a distribution-free confidence interval (Gilbert 1987); OLS on
  deseasonalized anomalies with a lag-1 effective-sample-size p-value as a cross-check.
- **Maps:** one Earth Engine `computePixels` request returns yearly means on a 200 × 200 Web-Mercator grid; per-pixel
  Sen's slope and Mann-Kendall on annual values.
- **Many tests at once:** the "check everything" view uses Benjamini-Hochberg false-discovery-rate q-values.
- **References:** Hirsch, Slack & Smith (1982) *WRR* 18(1) · Hirsch & Slack (1984) *WRR* 20(6) · Sen (1968) *JASA* 63 ·
  Gilbert (1987) · Benjamini & Hochberg (1995) *JRSS B* 57 · Rodell et al. (2018) *Nature* 557.
""")
    with m2:
        st.markdown("### Words you might see")
        st.markdown('<dl class="td-gloss">' + "".join(f"<dt>{ui.esc(t)}</dt><dd>{ui.esc(d)}</dd>" for t, d in plain.GLOSSARY)
                    + "</dl>", unsafe_allow_html=True)
    st.markdown("### The NASA data behind it")
    st.dataframe(pd.DataFrame([{
        "What it shows": f"{v.icon} {v.plain}", "Question": v.question, "Satellite / model": v.mission,
        "Agency": v.agency, "Detail (pixel)": nv.fmt_distance(v.pixel_m), "Years": f"{v.start_year}–{v.last_year}",
        "Earth Engine ID": v.collection,
    } for v in nv.VARIABLES.values()]), hide_index=True, width="stretch")


{"trend": render_trend, "compare": render_compare, "scan": render_scan, "method": render_method}[view]()

st.markdown('<div class="td-foot">Trend Detective · NASA Space Apps Challenge 2026 · data: NASA / JAXA / NOAA / DLR via '
            'Google Earth Engine · night lights: VIIRS (NASA/NOAA, EOG) · basemaps © NASA GIBS, Sentinel-2 cloudless by EOX, Esri, OpenStreetMap</div>', unsafe_allow_html=True)
