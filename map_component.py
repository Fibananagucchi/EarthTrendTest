"""
Trend Detective — interactive globe (MapLibre GL JS) as a Streamlit v2 custom component.

Python -> JS (data): region, preset pins, case files, comparison pins, change layers
(time-lapse frames, before/after, per-pixel trend — see change_maps.py).
JS -> Python (trigger "event"):
    {"type": "pick", lat, lon, name}          click on the map / search result
    {"type": "preset", key, variable}         click on a case-file pin or list entry
    {"type": "polygon", coords}               finished drawing an area
    {"type": "radius", km}                    region radius slider
    {"type": "compare_add", lat, lon, name}   click in compare mode
The map instance survives Streamlit reruns: the JS function is re-invoked with
new data on the same element and only updates sources/layers.
"""

import streamlit as st

MAPLIBRE_VERSION = "5.24.0"

CSS = """
.tdm-root { position: relative; width: 100%; height: var(--tdm-h, 600px); border-radius: 18px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08); background: #05060A;
  box-shadow: 0 30px 80px -30px rgba(124,156,255,0.25); font-family: 'Inter', system-ui, sans-serif; }
.tdm-stage { position: absolute; inset: 0; }
.tdm-map { position: absolute; inset: 0; }
.tdm-glass { background: rgba(9,11,19,0.74); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.09); border-radius: 14px; color: #EDEFF7; }
.tdm-search { position: absolute; top: 14px; left: 14px; width: min(340px, calc(100% - 28px)); z-index: 5; }
.tdm-search input { width: 100%; box-sizing: border-box; padding: 11px 14px 11px 38px; font-size: 14px; color: #EDEFF7;
  background: transparent; border: none; outline: none; font-family: inherit; }
.tdm-search .ico { position: absolute; left: 13px; top: 10px; opacity: 0.6; font-size: 15px; }
.tdm-results { border-top: 1px solid rgba(255,255,255,0.07); max-height: 230px; overflow-y: auto; }
.tdm-results div { padding: 9px 14px; font-size: 13px; cursor: pointer; color: #C9CEDD; line-height: 1.35; }
.tdm-results div:hover, .tdm-results div.sel { background: rgba(124,156,255,0.14); color: #fff; }
.tdm-tools { position: absolute; top: 74px; left: 14px; display: flex; flex-direction: column; gap: 4px; padding: 5px; z-index: 4; }
.tdm-tools button, .tdm-seg button, .tdm-btn { all: unset; cursor: pointer; border-radius: 10px; color: #AEB5C8;
  font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 6px; transition: all .15s ease; }
.tdm-tools button { width: 38px; height: 38px; font-size: 17px; position: relative; }
.tdm-tools button:hover, .tdm-seg button:hover, .tdm-btn:hover { background: rgba(255,255,255,0.07); color: #fff; }
.tdm-tools button.on { background: linear-gradient(135deg, #7C9CFF, #B38CFF); color: #05060A; }
.tdm-tools button .tip { position: absolute; left: 46px; white-space: nowrap; font-size: 12px; padding: 5px 9px;
  background: rgba(9,11,19,0.92); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; color: #EDEFF7;
  opacity: 0; pointer-events: none; transition: opacity .15s; }
.tdm-tools button:hover .tip { opacity: 1; }
.tdm-right { position: absolute; top: 14px; right: 14px; display: flex; flex-direction: column; gap: 8px; align-items: flex-end; z-index: 4; }
.tdm-seg { display: flex; gap: 2px; padding: 4px; }
.tdm-baserow { display: flex; gap: 6px; align-items: stretch; }
.tdm-year { appearance: none; -webkit-appearance: none; cursor: pointer; font: 600 13px 'Inter', sans-serif; color: #EDEFF7;
  padding: 0 26px 0 11px; outline: none; background-image: linear-gradient(45deg, transparent 50%, #AEB5C8 50%), linear-gradient(135deg, #AEB5C8 50%, transparent 50%);
  background-position: calc(100% - 13px) 50%, calc(100% - 8px) 50%; background-size: 5px 5px; background-repeat: no-repeat; }
.tdm-year option { background: #0C0F18; color: #EDEFF7; }
.tdm-seg button { padding: 7px 11px; }
.tdm-seg button.on { background: rgba(124,156,255,0.2); color: #fff; }
.tdm-layer { position: absolute; top: 110px; right: 14px; z-index: 4; padding: 10px 12px 12px; width: 296px; box-sizing: border-box;
  max-height: calc(100% - 124px); overflow-y: auto; overflow-x: hidden; }
.tdm-layer .grad { height: 10px; border-radius: 6px; margin: 4px 0 5px; }
.tdm-layer .rng { display: flex; justify-content: space-between; font: 11px 'JetBrains Mono', monospace; color: #AEB5C8; }
.tdm-layer .sub { font-size: 11.5px; color: #8A93A8; margin-top: 3px; line-height: 1.4; }
.tdm-layer .sub b { color: #EDEFF7; }
.tdm-layer .lbl { font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: #8A93A8; font-weight: 700; margin: 10px 0 4px; }
.tdm-layer .shares { display: flex; gap: 12px; font-size: 12px; color: #C9CEDD; }
.tdm-layer .shares b { font: 600 17px 'JetBrains Mono', monospace; display: block; }
.tdm-layer input[type=range] { width: 100%; accent-color: #7C9CFF; margin: 6px 0 2px; }
.tdm-layer .synthetic { margin-top: 7px; font-size: 11px; color: #FFB547; }
.tdm-tabs { display: flex; gap: 3px; margin-bottom: 10px; background: rgba(255,255,255,0.04); border-radius: 10px; padding: 3px; }
.tdm-tabs button { all: unset; flex: 1 1 auto; min-width: 0; text-align: center; cursor: pointer; font-size: 11.5px; padding: 7px 5px; border-radius: 8px; color: #AEB5C8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tdm-tabs button:hover { color: #fff; background: rgba(255,255,255,0.06); }
.tdm-tabs button.on { background: linear-gradient(135deg, #7C9CFF, #B38CFF); color: #05060A; font-weight: 600; }
.tdm-player { display: flex; align-items: center; gap: 12px; }
.tdm-play { all: unset; cursor: pointer; width: 38px; height: 38px; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #7C9CFF, #B38CFF); color: #05060A; font-size: 14px; font-weight: 700; box-shadow: 0 6px 20px -6px rgba(124,156,255,0.9); }
.tdm-yr { font: 800 28px 'Sora', 'Inter', sans-serif; color: #EDEFF7; line-height: 1; letter-spacing: -0.02em; }
.tdm-spark { width: 100%; height: 46px; margin-top: 8px; display: block; }
.tdm-chips { display: flex; gap: 4px; margin-top: 4px; }
.tdm-chips button { all: unset; cursor: pointer; font-size: 11.5px; padding: 3px 9px; border-radius: 99px; border: 1px solid rgba(255,255,255,0.12); color: #AEB5C8; }
.tdm-chips button.on { border-color: #7C9CFF; color: #fff; background: rgba(124,156,255,0.18); }
.tdm-ba { display: flex; justify-content: space-between; font: 600 12px 'JetBrains Mono', monospace; color: #EDEFF7; margin-top: 2px; }
.tdm-wide { all: unset; cursor: pointer; display: block; text-align: center; margin-top: 6px; padding: 7px; border-radius: 9px; font-size: 12.5px;
  border: 1px solid rgba(255,255,255,0.12); color: #EDEFF7; }
.tdm-wide:hover { border-color: #7C9CFF; }
.tdm-sep { height: 1px; background: rgba(255,255,255,0.08); margin: 11px 0 8px; }
.tdm-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: #8A93A8; margin-top: 8px; }
.tdm-row input[type=range] { flex: 1; margin: 0; }
.tdm-row label { display: flex; align-items: center; gap: 4px; cursor: pointer; white-space: nowrap; }
.tdm-bigyear { position: absolute; top: 18px; left: 50%; transform: translateX(-50%); z-index: 3; pointer-events: none; display: none;
  font: 800 52px 'Sora', 'Inter', sans-serif; color: rgba(237,239,247,0.95); letter-spacing: -0.03em; text-shadow: 0 6px 30px rgba(0,0,0,0.85); }
.tdm-bigyear small { display: block; text-align: center; font: 600 12px 'Inter', sans-serif; letter-spacing: .12em; text-transform: uppercase; color: #C9CEDD; }
.tdm-cases { position: absolute; left: 14px; bottom: 14px; width: 290px; max-height: calc(100% - 250px); display: flex; flex-direction: column; z-index: 4; }
.tdm-cases .hd { padding: 11px 14px 8px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #8A93A8; font-weight: 600;
  display: flex; justify-content: space-between; cursor: pointer; }
.tdm-cases .list { overflow-y: auto; padding: 0 6px 6px; }
.tdm-cases.closed .list { display: none; }
.tdm-case { padding: 8px 9px; border-radius: 10px; cursor: pointer; display: flex; gap: 9px; align-items: flex-start; }
.tdm-case:hover { background: rgba(124,156,255,0.12); }
.tdm-case .ic { font-size: 18px; line-height: 1.2; }
.tdm-case .nm { font-size: 13px; color: #EDEFF7; font-weight: 600; line-height: 1.3; }
.tdm-case .sb { font-size: 11.5px; color: #8A93A8; line-height: 1.35; margin-top: 2px; }
.tdm-chip { position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%); padding: 10px 16px; z-index: 4;
  display: flex; align-items: center; gap: 14px; max-width: calc(100% - 640px); min-width: 330px; box-sizing: border-box; }
.tdm-chip .pin { font-size: 16px; }
.tdm-chip .who { min-width: 0; flex: 1; }
.tdm-chip .nm { font-size: 13.5px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }
.tdm-chip .co { font: 11px 'JetBrains Mono', monospace; color: #8A93A8; }
.tdm-chip .rad { display: flex; align-items: center; gap: 8px; font: 12px 'JetBrains Mono', monospace; color: #C9CEDD; white-space: nowrap; }
.tdm-chip input[type=range] { width: 120px; accent-color: #7C9CFF; }
.tdm-watch { all: unset; cursor: pointer; white-space: nowrap; font: 600 12.5px 'Inter', sans-serif; color: #05060A;
  padding: 8px 13px; border-radius: 10px; background: linear-gradient(135deg, #7C9CFF, #B38CFF);
  box-shadow: 0 6px 18px -8px rgba(124,156,255,0.9); }
.tdm-watch:hover { filter: brightness(1.08); }
.tdm-busy { width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(124,156,255,0.25); border-top-color: #7C9CFF;
  animation: tdmspin .8s linear infinite; display: none; }
.tdm-root.busy .tdm-busy { display: block; }
@keyframes tdmspin { to { transform: rotate(360deg); } }
.tdm-hint { position: absolute; top: 72px; left: 50%; transform: translateX(-50%); padding: 9px 16px; font-size: 13px; z-index: 3;
  color: #EDEFF7; transition: opacity .6s; pointer-events: none; white-space: nowrap; }
.tdm-hint.gone { opacity: 0; }
.tdm-finish { all: unset; position: absolute; top: 74px; left: 66px; z-index: 5; display: none; cursor: pointer; padding: 9px 14px;
  border-radius: 10px; font: 600 13px 'Inter', sans-serif; color: #05060A; background: linear-gradient(135deg, #FFB547, #FFD08A);
  box-shadow: 0 6px 18px -8px rgba(255,181,71,0.9); }
.tdm-pin { width: 14px; height: 14px; border-radius: 50%; background: #FFB547; border: 2px solid #05060A; cursor: pointer;
  box-shadow: 0 0 0 4px rgba(255,181,71,0.25), 0 0 18px rgba(255,181,71,0.8); }
.tdm-pin .lb { position: absolute; left: 18px; top: -5px; white-space: nowrap; font-size: 12px; padding: 4px 8px; border-radius: 7px;
  background: rgba(9,11,19,0.9); border: 1px solid rgba(255,255,255,0.1); color: #EDEFF7; opacity: 0; pointer-events: none; transition: opacity .15s; }
.tdm-pin:hover .lb { opacity: 1; }
.tdm-center { width: 16px; height: 16px; border-radius: 50%; background: #7C9CFF; border: 2px solid #fff; pointer-events: none; }
.tdm-center::after { content: ''; position: absolute; inset: -12px; border-radius: 50%; border: 2px solid #7C9CFF; animation: tdmpulse 1.8s ease-out infinite; }
@keyframes tdmpulse { from { transform: scale(0.3); opacity: 1; } to { transform: scale(1.6); opacity: 0; } }
.tdm-cmp { min-width: 22px; height: 22px; border-radius: 11px; font: 700 12px 'Inter', sans-serif; color: #05060A;
  display: flex; align-items: center; justify-content: center; border: 2px solid #05060A; padding: 0 4px; box-sizing: border-box; }
.tdm-root .maplibregl-ctrl-attrib { background: rgba(5,6,10,0.6) !important; color: #6B7389; font-size: 10px; }
.tdm-root .maplibregl-ctrl-attrib a { color: #8A93A8; }
.tdm-root .maplibregl-ctrl-group { background: rgba(9,11,19,0.74) !important; border: 1px solid rgba(255,255,255,0.09); box-shadow: none !important; }
.tdm-root .maplibregl-ctrl-group button span { filter: invert(1) opacity(0.75); }
.tdm-root .maplibregl-ctrl-bottom-right { bottom: 4px; right: 4px; }
@media (hover: none) { .tdm-tools button .tip, .tdm-pin .lb { display: none; } }
@media (max-width: 900px) {
  .tdm-cases { display: none; }
  .tdm-bigyear { font-size: 34px; top: 64px; }
  .tdm-chip { max-width: calc(100% - 28px); min-width: 0; left: 14px; transform: none; right: 14px; }
  .tdm-layer { width: 266px; max-height: calc(100% - 196px); }
  .tdm-tabs button { font-size: 10.5px; padding: 7px 2px; }
}
/* phones: the map on top, the place bar and the change panel below it (nothing covers the map) */
@media (max-width: 640px) {
  .tdm-root { height: auto; overflow: visible; background: transparent; border: none; box-shadow: none; border-radius: 0;
    display: flex; flex-direction: column; }
  .tdm-chip { order: 1; }
  .tdm-layer { order: 2; }
  .tdm-stage { position: relative; height: min(var(--tdm-h, 600px), 62vh); min-height: 340px; overflow: hidden;
    border-radius: 16px; border: 1px solid rgba(255,255,255,0.08); background: #05060A; }
  .tdm-search { top: 10px; left: 10px; width: calc(100% - 20px); }
  .tdm-search input { font-size: 16px; padding: 10px 12px 10px 36px; }
  .tdm-tools { top: 60px; left: 10px; padding: 4px; }
  .tdm-tools button { width: 36px; height: 36px; font-size: 16px; }
  .tdm-right { top: 60px; right: 10px; flex-direction: row; gap: 6px; }
  .tdm-seg { padding: 3px; }
  .tdm-seg button { padding: 6px 9px; font-size: 15px; }
  .tdm-seg button .t { display: none; }
  .tdm-year { font-size: 12.5px; padding: 0 22px 0 8px; background-position: calc(100% - 11px) 50%, calc(100% - 6px) 50%; }
  .tdm-finish { top: 60px; left: 58px; }
  .tdm-hint { top: auto; bottom: 12px; font-size: 12.5px; white-space: normal; text-align: center; width: max-content; max-width: calc(100% - 90px); }
  .tdm-bigyear { top: 104px; font-size: 30px; }
  .tdm-chip { position: relative; left: auto; right: auto; bottom: auto; transform: none; max-width: none; margin-top: 8px;
    flex-wrap: wrap; gap: 8px 10px; padding: 10px 12px; }
  .tdm-chip .nm { max-width: none; }
  .tdm-chip .who { flex: 1 1 calc(100% - 50px); }
  .tdm-watch { flex: 1 1 auto; text-align: center; padding: 10px 12px; font-size: 14px; }
  .tdm-chip .rad { flex: 1 1 130px; }
  .tdm-chip input[type=range] { width: auto; flex: 1; min-width: 0; }
  .tdm-layer { position: relative; top: auto; right: auto; width: auto; max-height: none; margin-top: 8px; }
  .tdm-tabs button { font-size: 12px; padding: 8px 4px; }
}
"""

JS = r"""
const ML_VERSION = "__MLV__";
const ML_JS = `https://cdn.jsdelivr.net/npm/maplibre-gl@${ML_VERSION}/dist/maplibre-gl.js`;
const ML_CSS = `https://cdn.jsdelivr.net/npm/maplibre-gl@${ML_VERSION}/dist/maplibre-gl.css`;
const ACCENT = '#7C9CFF';
const TOUCH = !!(window.matchMedia && matchMedia('(pointer: coarse)').matches);   // phones and tablets
const TAP = TOUCH ? 'Tap' : 'Click';

function loadMapLibre() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  if (!window.__tdmLoading) {
    window.__tdmLoading = new Promise((resolve, reject) => {
      if (!document.querySelector('link[data-tdm-ml]')) {
        const l = document.createElement('link');
        l.rel = 'stylesheet'; l.href = ML_CSS; l.dataset.tdmMl = '1';
        document.head.appendChild(l);
      }
      const s = document.createElement('script');
      s.src = ML_JS; s.onload = () => resolve(window.maplibregl); s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  return window.__tdmLoading;
}

const ESRI = (svc) => [`https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`];
// Satellite: Sentinel-2 cloudless, a cloud-free 10 m mosaic of one whole year, 2016-2025 (Esri's photos are
// older in many places, e.g. they still show the Kakhovka Reservoir full of water after it drained in 2023).
const SAT_YEARS = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
const s2Tiles = (y) => [`https://tiles.maps.eox.at/wmts/1.0.0/${y === 2016 ? 's2cloudless' : 's2cloudless-' + y}_3857/default/g/{z}/{y}/{x}.jpg`];
// Night without Earth Engine: NASA Black Marble, only published for 2012 and 2016.
const blackMarble = (y) => [`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/${y}-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png`];

// ── background years ─────────────────────────────────────────────────────
// Satellite photos exist for 2016-2025. Night: yearly VIIRS lights from Earth Engine (Python sends tiles for the
// chosen year and for every year of the time-lapse on the map), or NASA Black Marble 2012 / 2016 without it.
// The satellite photo follows the time-lapse / before-after year (every photo year it can show is loaded, hidden,
// so the switch is instant); the night map stays on the year chosen in the menu (yearly night maps differ too much
// to play as a time-lapse).
const nearest = (y, ys) => ys.reduce((b, v) => (Math.abs(v - y) < Math.abs(b - y) ? v : b), ys[0]);
const satYearFor = (y) => Math.min(Math.max(y, SAT_YEARS[0]), SAT_YEARS[SAT_YEARS.length - 1]);
const S2_ATTR = '<a href="https://s2maps.eu" target="_blank">Sentinel-2 cloudless</a> by EOX IT Services GmbH '
              + '(contains modified Copernicus Sentinel data)';
// at night, up close, a darkened ("moonlit") photo of the same year replaces the 1 km land/water background
const NIGHT_PHOTO_OPACITY = ['interpolate', ['linear'], ['zoom'], 7.5, 0, 9.5, 1];

function nightYears(S) {
  const n = S.data.night || {};
  return n.live ? Object.keys(n.tiles || {}).map(Number).sort((a, b) => a - b) : (n.years || [2016]);
}

function yearLayers(S) {
  // the background layers of the current map, each showing one year of one kind
  const n = S.data.night || {}, L = [];
  if (S.basemap === 'satellite') {
    SAT_YEARS.forEach(y => L.push({ id: `sat-${y}`, kind: 'photo', year: y, full: 1 }));
  } else if (n.live) {
    const ys = nightYears(S);
    ys.forEach(y => L.push({ id: `nbg-${y}`, kind: 'night', year: y, full: 1 }));
    [...new Set(ys.map(satYearFor))].forEach(y => L.push({ id: `nsat-${y}`, kind: 'nightphoto', year: y, full: NIGHT_PHOTO_OPACITY }));
    ys.forEach(y => L.push({ id: `nl-${y}`, kind: 'night', year: y, full: 0.95 }));
  } else {
    nightYears(S).forEach(y => L.push({ id: `bm-${y}`, kind: 'night', year: y, full: 1 }));
  }
  return L;
}

const shownYear = (S, kind) => (kind === 'photo' ? S.satYear : kind === 'nightphoto' ? satYearFor(S.nightYear) : S.nightYear);

function layerState(S, l) {
  const cur = shownYear(S, l.kind) === l.year, ch = S.data.change;
  const needed = l.kind === 'photo' && !!ch && ch.years.some(y => satYearFor(y) === l.year);
  return { visibility: cur || needed ? 'visible' : 'none', opacity: cur ? l.full : 0 };
}
const stateKey = (st) => st.visibility + '|' + JSON.stringify(st.opacity);

function buildStyle(S) {
  // background layers (one per year) + labels; region, comparison and change layers are added in addLayers()
  const n = S.data.night || {};
  const sources = {
    labels: { type: 'raster', tileSize: 256, maxzoom: 16, tiles: ESRI('Canvas/World_Dark_Gray_Reference') },
  };
  const layers = [];
  yearLayers(S).forEach(l => {
    const st = layerState(S, l), y = l.year;
    let src, zoom = {}, paint = {};
    if (l.id.startsWith('sat-')) {
      src = { maxzoom: 15, tiles: s2Tiles(y), attribution: S2_ATTR };
      paint = { 'raster-brightness-max': 0.92 };
    } else if (l.id.startsWith('nbg-')) {
      src = { maxzoom: 10, tiles: [n.tiles[y].bg], attribution: 'Land and water: NASA MODIS (MOD13A3)' };
      zoom = { maxzoom: 9.5 };
    } else if (l.id.startsWith('nsat-')) {
      src = { maxzoom: 15, tiles: s2Tiles(y), attribution: S2_ATTR };
      zoom = { minzoom: 7 };
      paint = { 'raster-brightness-max': 0.3, 'raster-saturation': -0.5 };
    } else if (l.id.startsWith('nl-')) {
      src = { maxzoom: 10, tiles: [n.tiles[y].lights],
              attribution: 'VIIRS night lights (NASA/NOAA Suomi NPP, Earth Observation Group) via Google Earth Engine' };
    } else {
      src = { maxzoom: 8, tiles: blackMarble(y), attribution: 'NASA Black Marble (VIIRS) via GIBS' };
      paint = { 'raster-saturation': 0.1 };
    }
    sources[l.id] = { type: 'raster', tileSize: 256, ...src };
    layers.push({ id: l.id, type: 'raster', source: l.id, ...zoom, layout: { visibility: st.visibility },
                  paint: { ...paint, 'raster-opacity': st.opacity, 'raster-fade-duration': 0 } });
    S.lstate[l.id] = stateKey(st);
  });
  if (S.basemap !== 'satellite' && !n.live) {
    // Black Marble is only 500 m: a dark street map fades in when zooming in
    sources.dark = { type: 'raster', tileSize: 256, maxzoom: 16, tiles: ESRI('Canvas/World_Dark_Gray_Base'),
                     attribution: 'Esri, HERE, Garmin, © OpenStreetMap contributors' };
    layers.push({ id: 'base-dark', type: 'raster', source: 'dark', minzoom: 6,
                  paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 6.5, 0, 8.5, 0.9] } });
  }
  return { version: 8, sources, layers };
}

function baseKey(S) {
  const n = S.data.night || {};
  if (S.basemap === 'satellite') return 'sat';
  return n.live ? 'night|' + nightYears(S).map(y => n.tiles[y].lights + ' ' + n.tiles[y].bg).join('|') : 'blackmarble';
}

function applyBase(S) {
  // rebuilds the style only when the set of background layers changed (the 'style.load' handler re-adds the rest)
  const key = baseKey(S);
  if (key === S.baseKey || !S.map) return;
  S.baseKey = key;
  S.lstate = {};
  S.map.setStyle(buildStyle(S));
}

function showYears(S) {
  // show the current year of each background layer; keep the other years a time-lapse needs loaded but hidden
  const m = S.map;
  if (!m) return;
  yearLayers(S).forEach(l => {
    if (!m.getLayer(l.id)) return;
    const st = layerState(S, l), key = stateKey(st);
    if (S.lstate[l.id] === key) return;
    S.lstate[l.id] = key;
    m.setLayoutProperty(l.id, 'visibility', st.visibility);
    m.setPaintProperty(l.id, 'raster-opacity', st.opacity);
  });
  const sel = S.root.querySelector('.tdm-year');
  const cur = S.basemap === 'satellite' ? S.satYear : (S.nightWanted || S.nightYear);
  if (sel && +sel.value !== cur) sel.value = cur;
}

function followYear(S, y) {
  // the satellite photo shows the year the time-lapse (or before/after) is on
  const sat = satYearFor(y);
  if (sat === S.satYear) return;
  S.satYear = sat;
  showYears(S);
}

function renderYears(S) {
  const sel = S.root.querySelector('.tdm-year'), n = S.data.night || {};
  const years = S.basemap === 'satellite' ? SAT_YEARS : (n.years || [2016]);
  const cur = S.basemap === 'satellite' ? S.satYear : (S.nightWanted || S.nightYear);
  sel.innerHTML = [...years].reverse().map(y => `<option value="${y}" ${y === cur ? 'selected' : ''}>${y}</option>`).join('');
  sel.title = S.basemap === 'satellite' ? 'Year of the satellite photo' : 'Year of the night lights';
}

// ── geometry helpers ─────────────────────────────────────────────────────
function circle(lat, lon, km, n = 96) {
  const R = 6371.0088, d = km / R, la = lat * Math.PI / 180, lo = lon * Math.PI / 180, pts = [];
  for (let i = 0; i <= n; i++) {
    const b = 2 * Math.PI * i / n;
    const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b));
    const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2));
    pts.push([lo2 * 180 / Math.PI, la2 * 180 / Math.PI]);
  }
  return pts;
}
function regionRing(r) {
  if (r.polygon && r.polygon.length >= 3) return [...r.polygon, r.polygon[0]];
  return circle(r.lat, r.lon, r.radius_km);
}
const fc = (features) => ({ type: 'FeatureCollection', features });
const poly = (ring, props = {}) => ({ type: 'Feature', properties: props, geometry: { type: 'Polygon', coordinates: [ring] } });
function ringBounds(ring) {
  let w = 180, s = 90, e = -180, n = -90;
  ring.forEach(([x, y]) => { w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); });
  return [[w, s], [e, n]];
}
const kmFromSlider = (v) => Math.round(0.5 * Math.pow(600, v / 100) * 10) / 10;
const sliderFromKm = (km) => Math.round(100 * Math.log(km / 0.5) / Math.log(600));
const fmtKm = (km) => km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km)} km`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function setGeo(map, id, data) {
  const src = map.getSource(id);
  if (src) src.setData(data); else map.addSource(id, { type: 'geojson', data });
}

async function reverseName(lat, lon) {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 2500);
    const r = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=8&accept-language=en`, { signal: ctl.signal });
    clearTimeout(t);
    const j = await r.json();
    if (j && j.address) {
      const a = j.address;
      const place = a.city || a.town || a.village || a.county || a.state_district || a.state || a.region;
      const country = a.country;
      if (place && country) return `Near ${place}, ${country}`;
      if (j.display_name) return j.display_name.split(',').slice(0, 2).join(',');
    }
  } catch (e) { /* offline or rate-limited */ }
  return null;
}

// ── component ────────────────────────────────────────────────────────────
export default function (component) {
  const { data, parentElement } = component;
  let S = parentElement.__tdm;
  if (!S) {
    S = parentElement.__tdm = { data, emit: null, mode: 'pick', basemap: 'night', globe: true, draft: [],
                                 opacity: 0.85, satYear: SAT_YEARS[SAT_YEARS.length - 1], nightYear: (data.night || {}).year || 2016,
                                 baseKey: null, lstate: {}, nightWanted: null, changeKey: null, chMode: 'timelapse', frame: 0, speed: 1, blend: 0.5, sigOnly: false, playing: false, timer: null, urls: {}, regionKey: null, compareKey: null, presetKey: null,
                                 markers: { presets: [], compare: [] }, loaded: false, pending: null };
    buildDom(S, parentElement);
  }
  S.data = data;
  S.emit = (type, payload) => {
    parentElement.querySelector('.tdm-root').classList.add('busy');
    component.setTriggerValue('event', Object.assign({ type, nonce: Date.now() + Math.random() }, payload));
  };
  S.root.style.setProperty('--tdm-h', `${data.height || 600}px`);
  if (!S.map) {
    loadMapLibre().then(() => initMap(S)).catch(err => {
      S.root.querySelector('.tdm-map').innerHTML =
        `<div style="padding:40px;color:#FFB547;font:14px Inter,sans-serif">Map library could not be loaded (${esc(err)}). Check your internet connection.</div>`;
    });
  } else if (S.loaded) {
    sync(S);
  }
  return undefined;
}

function buildDom(S, parent) {
  const root = document.createElement('div');
  root.className = 'tdm-root';
  root.innerHTML = `
    <div class="tdm-stage">
    <div class="tdm-map"></div>
    <div class="tdm-search tdm-glass"><span class="ico">🔍</span>
      <input type="text" placeholder="Search any place on Earth…" autocomplete="off"/>
      <div class="tdm-results"></div></div>
    <div class="tdm-tools tdm-glass">
      <button data-mode="pick" class="on">◎<span class="tip">Investigate: click anywhere</span></button>
      <button data-mode="draw">⬠<span class="tip">Draw an area (double-click to finish)</span></button>
      <button data-mode="compare">⚖<span class="tip">Compare: click to add regions</span></button>
      <button data-act="home">⌂<span class="tip">Fly to the current region</span></button>
    </div>
    <div class="tdm-right">
      <div class="tdm-baserow">
        <div class="tdm-seg tdm-glass" data-group="basemap">
          <button data-basemap="night" class="on" title="City lights at night">🌃<span class="t"> Night</span></button><button data-basemap="satellite" title="Cloud-free satellite photo (Sentinel-2, 10 m)">🛰<span class="t"> Satellite</span></button>
        </div>
        <select class="tdm-year tdm-glass" title="Year of the background map"></select>
      </div>
      <div class="tdm-seg tdm-glass" data-group="proj">
        <button data-proj="globe" class="on" title="Globe">🌐<span class="t"> Globe</span></button><button data-proj="flat" title="Flat map">▭<span class="t"> Flat</span></button>
      </div>
    </div>
    <div class="tdm-cases tdm-glass"><div class="hd"><span>✨ Try an example</span><span class="tg">▾</span></div><div class="list"></div></div>
    <button class="tdm-finish">✓ Finish area</button>
    <div class="tdm-hint tdm-glass">👆 ${TAP} anywhere on Earth to investigate it</div>
    <div class="tdm-bigyear"></div>
    </div>
    <div class="tdm-layer tdm-glass" style="display:none"></div>
    <div class="tdm-chip tdm-glass">
      <span class="pin">📍</span>
      <div class="who"><div class="nm"></div><div class="co"></div></div>
      <div class="tdm-busy"></div>
      <button class="tdm-watch" title="Show the change on this map: time-lapse, before/after and trend">🎬 Watch it change</button>
      <div class="rad"><span>⌀</span><input type="range" min="0" max="100" step="1"/><span class="rv"></span></div>
    </div>`;
  parent.appendChild(root);
  S.root = root;
  if (window.ResizeObserver) new ResizeObserver(() => S.map && S.map.resize()).observe(root.querySelector('.tdm-stage'));
  root.querySelector('.tdm-finish').onclick = () => finishDraw(S);

  // tools
  root.querySelectorAll('.tdm-tools button[data-mode]').forEach(b => b.onclick = () => setMode(S, b.dataset.mode));
  root.querySelector('.tdm-tools button[data-act=home]').onclick = () => flyToRegion(S, true);
  root.querySelectorAll('[data-basemap]').forEach(b => b.onclick = () => {
    if (S.basemap === b.dataset.basemap) return;
    S.basemap = b.dataset.basemap;
    root.querySelectorAll('[data-basemap]').forEach(x => x.classList.toggle('on', x === b));
    renderYears(S);
    applyBase(S);
  });
  root.querySelector('.tdm-year').onchange = (ev) => {
    const y = +ev.target.value;
    const jump = () => {                       // with a time-lapse on the map, go to that year too
      const ch = S.data.change, i = ch ? ch.frames.findIndex(f => f.year === y) : -1;
      if (i >= 0 && S.chMode === 'timelapse') { stopPlay(S); S.frame = i; showChange(S); updatePlayer(S); }
    };
    if (S.basemap === 'satellite') { S.satYear = satYearFor(y); showYears(S); jump(); return; }
    if (nightYears(S).includes(y)) { S.nightYear = y; showYears(S); return; }
    S.nightWanted = y;                         // not made yet: Earth Engine makes it on the Python side
    S.emit('night_year', { year: y });
  };
  root.querySelectorAll('[data-proj]').forEach(b => b.onclick = () => {
    S.globe = b.dataset.proj === 'globe';
    root.querySelectorAll('[data-proj]').forEach(x => x.classList.toggle('on', x === b));
    applyProjection(S);
  });
  root.querySelector('.tdm-cases .hd').onclick = () => {
    const c = root.querySelector('.tdm-cases'); c.classList.toggle('closed');
    c.querySelector('.tg').textContent = c.classList.contains('closed') ? '▸' : '▾';
  };

  // radius slider
  const rng = root.querySelector('.tdm-chip input[type=range]');
  rng.oninput = () => {
    const km = kmFromSlider(+rng.value);
    root.querySelector('.tdm-chip .rv').textContent = fmtKm(km);
    const r = S.data.region;
    if (!r.polygon) drawRegion(S, { ...r, radius_km: km });
  };
  rng.onchange = () => S.emit('radius', { km: kmFromSlider(+rng.value) });
  root.querySelector('.tdm-watch').onclick = () => { hideHint(S); S.emit('show_change', {}); };

  // search
  const input = root.querySelector('.tdm-search input'), results = root.querySelector('.tdm-results');
  let timer = null, found = [];
  const choose = (f) => {
    results.innerHTML = ''; input.value = f.name.split(',').slice(0, 2).join(',');
    const lat = +f.lat, lon = +f.lon;
    S.pending = { lat, lon };
    if (S.data.change) { removeChange(S); S.changeKey = null; }   // a new place: its own time-lapse replaces the old one
    drawRegion(S, { ...S.data.region, lat, lon, polygon: null });
    S.map.flyTo({ center: [lon, lat], zoom: Math.max(S.map.getZoom(), zoomFor(S.data.region.radius_km)), duration: 1800, essential: true });
    S.emit('pick', { lat, lon, name: f.name.split(',').slice(0, 2).join(',').trim() });
    hideHint(S);
  };
  const coord = (q) => { const m = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/); return m ? { lat: +m[1], lon: +m[2] } : null; };
  input.oninput = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3 || coord(q)) { results.innerHTML = ''; return; }
    timer = setTimeout(async () => {
      try {
        const r = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=5&accept-language=en`);
        found = (await r.json()).map(x => ({ name: x.display_name, lat: x.lat, lon: x.lon }));
        results.innerHTML = found.map((f, i) => `<div data-i="${i}">${esc(f.name)}</div>`).join('');
        results.querySelectorAll('div').forEach(d => d.onclick = () => choose(found[+d.dataset.i]));
      } catch (e) { results.innerHTML = '<div>Search unavailable offline — type “lat, lon”</div>'; }
    }, 380);
  };
  input.onkeydown = (e) => {
    if (e.key !== 'Enter') return;
    const c = coord(input.value);
    if (c) choose({ name: `${c.lat.toFixed(4)}, ${c.lon.toFixed(4)}`, lat: c.lat, lon: c.lon });
    else if (found.length) choose(found[0]);
  };
  document.addEventListener('keydown', (e) => {
    if (S.mode !== 'draw') return;
    if (e.key === 'Escape') { S.draft = []; drawDraft(S); }
    if (e.key === 'Enter') finishDraw(S);
  });
}

function zoomFor(km) { return Math.max(2, Math.min(15, 14 - Math.log2(Math.max(km, 0.3) / 0.35))); }

function hideHint(S) { S.root.querySelector('.tdm-hint').classList.add('gone'); }

function setMode(S, mode) {
  S.mode = mode;
  S.root.querySelectorAll('.tdm-tools button[data-mode]').forEach(b => b.classList.toggle('on', b.dataset.mode === mode));
  const hint = S.root.querySelector('.tdm-hint');
  const msg = { pick: `◎ ${TAP} anywhere to investigate that place`,
                draw: TOUCH ? '⬠ Tap to add corners, then press ✓ Finish area'
                            : '⬠ Click to add corners · double-click, Enter or ✓ Finish · Esc to cancel',
                compare: `⚖ ${TAP} places to add them to the comparison` }[mode];
  hint.textContent = msg; hint.classList.remove('gone');
  clearTimeout(S.hintTimer); S.hintTimer = setTimeout(() => hideHint(S), 4000);
  S.map.getCanvas().style.cursor = mode === 'pick' ? 'crosshair' : mode === 'draw' ? 'copy' : 'cell';
  if (mode === 'draw') S.map.doubleClickZoom.disable(); else { S.map.doubleClickZoom.enable(); S.draft = []; }
  drawDraft(S);
}

function applyProjection(S) {
  try { S.map.setProjection({ type: S.globe ? 'globe' : 'mercator' }); } catch (e) { }
  try {
    S.map.setSky({ 'sky-color': '#05060A', 'horizon-color': '#1d2550', 'fog-color': '#05060A',
                   'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0] });
  } catch (e) { }
}

function initMap(S) {
  const r = S.data.region;
  const map = new maplibregl.Map({
    container: S.root.querySelector('.tdm-map'), style: buildStyle(S),
    center: [r.lon, r.lat * 0.6], zoom: 1.3, attributionControl: { compact: true },
    maxPitch: 70, fadeDuration: 150,
    cooperativeGestures: TOUCH,               // on phones one finger scrolls the page, two fingers move the map
  });
  S.map = map;
  S.baseKey = baseKey(S);
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
  map.on('style.load', () => {
    applyProjection(S);
    S.compareKey = null;                       // sources were wiped by setStyle
    if (S.changeKey) { S.changeKey = null; S.restoreChange = true; }
    addLayers(S);
    if (!S.loaded) {
      S.loaded = true;
      setTimeout(() => flyToRegion(S, true), 400);
    }
  });
  const foldCredits = () => {             // phones: keep the map credits folded into the (i) button
    const at = S.root.querySelector('.maplibregl-ctrl-attrib');
    if (at && narrow(S)) { at.classList.remove('maplibregl-compact-show'); at.removeAttribute('open'); }
  };
  map.on('load', foldCredits);
  map.on('style.load', () => map.once('idle', foldCredits));   // a new background re-opens them
  map.on('click', (e) => onClick(S, e));
  map.on('dblclick', (e) => { if (S.mode === 'draw') { e.preventDefault(); finishDraw(S); } });
  map.getCanvas().style.cursor = 'crosshair';
}

function addLayers(S) {
  const map = S.map;
  setGeo(map, 'region', fc([]));
  setGeo(map, 'compare', fc([]));
  setGeo(map, 'draft', fc([]));
  if (!map.getLayer('compare-fill')) {
    map.addLayer({ id: 'compare-fill', type: 'fill', source: 'compare', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.18 } });
    map.addLayer({ id: 'compare-line', type: 'line', source: 'compare', paint: { 'line-color': ['get', 'color'], 'line-width': 2 } });
    map.addLayer({ id: 'region-fill', type: 'fill', source: 'region', paint: { 'fill-color': ACCENT, 'fill-opacity': 0.08 } });
    map.addLayer({ id: 'region-glow', type: 'line', source: 'region', paint: { 'line-color': ACCENT, 'line-width': 8, 'line-opacity': 0.18, 'line-blur': 4 } });
    map.addLayer({ id: 'region-line', type: 'line', source: 'region', paint: { 'line-color': '#C7D3FF', 'line-width': 1.8, 'line-dasharray': [2, 1.4] } });
    map.addLayer({ id: 'draft-line', type: 'line', source: 'draft', paint: { 'line-color': '#FFB547', 'line-width': 2.2 } });
    map.addLayer({ id: 'draft-pts', type: 'circle', source: 'draft', filter: ['==', '$type', 'Point'],
                   paint: { 'circle-radius': 4.5, 'circle-color': '#FFB547', 'circle-stroke-color': '#05060A', 'circle-stroke-width': 1.5 } });
    map.addLayer({ id: 'labels', type: 'raster', source: 'labels', paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0.55, 6, 0.95] } });
  }
  sync(S);
}

function sync(S) {
  const root = S.root; root.classList.remove('busy');
  const d = S.data, r = d.region;
  // background map: a night year asked for in the menu may have arrived from Python
  const ny = nightYears(S);
  if (S.nightWanted && ny.includes(S.nightWanted)) { S.nightYear = S.nightWanted; S.nightWanted = null; }
  if (!ny.includes(S.nightYear)) S.nightYear = nearest(S.nightYear || (d.night || {}).year || 2016, ny);
  renderYears(S);
  applyBase(S);
  // region chip
  root.querySelector('.tdm-chip .nm').textContent = r.name || 'Selected location';
  root.querySelector('.tdm-chip .co').textContent =
    `${r.lat.toFixed(3)}°, ${r.lon.toFixed(3)}° · ${r.polygon ? 'drawn outline · ' + (r.area_km2 || 0).toFixed(1) + ' km²' : 'radius ' + fmtKm(r.radius_km)}`;
  const rng = root.querySelector('.tdm-chip input[type=range]');
  rng.value = sliderFromKm(r.radius_km); rng.disabled = !!r.polygon;
  root.querySelector('.tdm-chip .rv').textContent = r.polygon ? '—' : fmtKm(r.radius_km);

  drawRegion(S, r);
  syncChange(S);
  syncCompare(S);
  syncPresets(S);
  if (d.mode_hint && d.mode_hint.token !== S.modeToken) {
    S.modeToken = d.mode_hint.token;
    setMode(S, d.mode_hint.mode);
    if (d.mode_hint.mode === 'compare' && (d.compare || []).length) fitCompare(S);
  }
  const key = JSON.stringify([r.lat, r.lon, r.radius_km, r.polygon]);
  if (key !== S.regionKey) {
    const first = S.regionKey === null;
    S.regionKey = key;
    // after a click the user already looks where they want: only fly in from a far-out (globe) view
    const fromClick = S.clickedAt && Date.now() - S.clickedAt < 30000;
    S.clickedAt = 0;
    const justFitChange = S.fittedChangeAt && Date.now() - S.fittedChangeAt < 2500;
    if (!first && !justFitChange && !(fromClick && S.map.getZoom() >= 4.5)) flyToRegion(S, false);
  }
}

function drawRegion(S, r) {
  if (!S.map || !S.map.getSource('region')) return;
  S.map.getSource('region').setData(fc([poly(regionRing(r))]));
  if (!S.centerMarker) {
    const el = document.createElement('div'); el.className = 'tdm-center';
    S.centerMarker = new maplibregl.Marker({ element: el }).setLngLat([r.lon, r.lat]).addTo(S.map);
  } else S.centerMarker.setLngLat([r.lon, r.lat]);
}

function narrow(S) { return S.root.clientWidth < 640; }

function viewPadding(S) {
  return narrow(S) ? { top: 56, bottom: 44, left: 56, right: 16 } : { top: 90, bottom: 110, left: 80, right: 270 };
}

function flyToRegion(S, force) {
  const map = S.map, r = S.data.region;
  if (!map) return;
  const b = ringBounds(regionRing(r));
  const cam = map.cameraForBounds(b, { padding: viewPadding(S) }) || map.cameraForBounds(b, { padding: 20 });
  if (!cam) return;
  const z = Math.min(cam.zoom, 14);
  const visible = map.getBounds().contains([r.lon, r.lat]);
  if (!force && visible && Math.abs(map.getZoom() - z) < 1.3) return;   // already looking at it
  map.flyTo({ center: cam.center, zoom: z, duration: force ? 2600 : 1600, curve: 1.6, essential: true });
}

function onClick(S, e) {
  const { lng, lat } = e.lngLat;
  hideHint(S);
  S.clickedAt = Date.now();
  if (S.mode === 'draw') { S.draft.push([lng, lat]); drawDraft(S); return; }
  if (S.mode === 'compare') {
    reverseName(lat, lng).then(name => S.emit('compare_add', { lat, lon: lng, name: name || `${lat.toFixed(3)}, ${lng.toFixed(3)}` }));
    return;
  }
  // a click on the trend layer inspects that pixel: Python shrinks the region to about the data's pixel size
  const ch = S.data.change;
  const inspect = !!(ch && !S.hideOverlay && inArea(ch.area, lng, lat));
  if (ch && !inspect) { removeChange(S); S.changeKey = null; }   // a new place: its own time-lapse replaces the old one
  drawRegion(S, { ...S.data.region, lat, lon: lng, polygon: null, radius_km: inspect ? (S.data.inspect_km || 1) : S.data.region.radius_km });
  S.root.querySelector('.tdm-chip .nm').textContent = inspect ? 'Inspecting pixel…' : 'Locating…';
  S.root.classList.add('busy');
  reverseName(lat, lng).then(name => S.emit('pick', { lat, lon: lng, inspect,
    name: (inspect ? 'Pixel · ' : '') + (name || `${lat.toFixed(3)}, ${lng.toFixed(3)}`) }));
}

// is a point inside the area the map layers were made for (circle or drawn outline)?
function inArea(a, lng, lat) {
  if (!a) return false;
  if (a.polygon && a.polygon.length >= 3) {
    let inside = false;
    for (let i = 0, j = a.polygon.length - 1; i < a.polygon.length; j = i++) {
      const [xi, yi] = a.polygon[i], [xj, yj] = a.polygon[j];
      if ((yi > lat) !== (yj > lat) && lng < xi + (lat - yi) * (xj - xi) / (yj - yi)) inside = !inside;
    }
    return inside;
  }
  const rad = Math.PI / 180, dLat = (lat - a.lat) * rad, dLon = (lng - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(Math.min(h, 1))) <= a.radius_km;
}

function drawDraft(S) {
  if (!S.map || !S.map.getSource('draft')) return;
  const pts = S.draft;
  const feats = pts.map(p => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: p } }));
  if (pts.length >= 2) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: pts.length >= 3 ? [...pts, pts[0]] : pts } });
  S.map.getSource('draft').setData(fc(feats));
  S.root.querySelector('.tdm-finish').style.display = S.mode === 'draw' && pts.length >= 3 ? 'block' : 'none';
}

function finishDraw(S) {
  // a double-click also fires two clicks: drop near-duplicate consecutive corners
  const coords = S.draft.filter((p, i, a) => i === 0 || Math.hypot(p[0] - a[i - 1][0], p[1] - a[i - 1][1]) > 1e-7);
  if (coords.length < 3) return;
  S.draft = []; drawDraft(S);
  drawRegion(S, { ...S.data.region, polygon: coords, lat: coords.reduce((a, p) => a + p[1], 0) / coords.length,
                  lon: coords.reduce((a, p) => a + p[0], 0) / coords.length });
  S.emit('polygon', { coords });
  setMode(S, 'pick');
}

// ── change layers: time-lapse / before-after / trend, all from one data cube ──
const fmtNum = (v) => {
  if (v === null || v === undefined || !isFinite(v)) return '–';
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  if (a >= 1) return v.toFixed(2);
  if (a === 0) return '0';
  return String(+v.toPrecision(2));
};
const signed = (v) => (v > 0 ? '+' : '') + fmtNum(v);
const gradCss = (p) => `linear-gradient(90deg,${p.map(c => '#' + c).join(',')})`;

function layerPadding(S) {
  // keep the data area clear of the floating panels that are actually visible at this width
  if (narrow(S)) return { top: 56, bottom: 30, left: 56, right: 16 };
  const cases = getComputedStyle(S.root.querySelector('.tdm-cases')).display !== 'none';
  return { top: 50, bottom: 80, left: cases ? 320 : 64, right: 316 };
}

function stopPlay(S) { clearTimeout(S.timer); S.timer = null; S.playing = false; }

function setImg(S, id, url) {
  if (S.urls[id] === url) return;
  S.urls[id] = url;
  S.map.getSource(id).updateImage({ url });
}

function addChangeSources(S, ch) {
  const map = S.map, [w, s, e, n] = ch.bounds, coordinates = [[w, n], [e, n], [e, s], [w, s]];
  for (const id of ['chg-a', 'chg-b']) {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    map.addSource(id, { type: 'image', url: ch.frames[0].url, coordinates });
    map.addLayer({ id, type: 'raster', source: id,
                   paint: { 'raster-opacity': 0, 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } }, 'compare-fill');
    S.urls[id] = ch.frames[0].url;
  }
}

function removeChange(S) {
  stopPlay(S);
  for (const id of ['chg-a', 'chg-b']) {
    if (S.map.getLayer(id)) S.map.removeLayer(id);
    if (S.map.getSource(id)) S.map.removeSource(id);
  }
  S.urls = {};
  showYears(S);                                      // stop preloading background years
  S.root.querySelector('.tdm-layer').style.display = 'none';
  S.root.querySelector('.tdm-bigyear').style.display = 'none';
}

function syncChange(S) {
  const ch = S.data.change;
  const key = ch ? [ch.var, ch.bounds.join(','), ch.years.join(','), ch.frames[0].url.length, ch.trend.url_all.length].join('|') : null;
  if (key === S.changeKey) return;
  const restoring = S.restoreChange; S.restoreChange = false;
  S.changeKey = key;
  if (!ch) { removeChange(S); return; }
  const wasPlaying = S.playing;
  stopPlay(S);
  addChangeSources(S, ch);
  showYears(S);
  if (restoring && wasPlaying) S.timer = setTimeout(() => play(S), 300);   // a new background keeps it playing
  if (!restoring) {                                   // brand-new layers: show them and start the time-lapse
    ch.frames.forEach(f => { const im = new Image(); im.src = f.url; });      // warm up image decoding
    S.chMode = 'timelapse'; S.frame = 0; S.hideOverlay = false;
    hideHint(S);
    const [w, s, e, n] = ch.bounds;
    S.map.fitBounds([[w, s], [e, n]], { padding: layerPadding(S), duration: 1600, maxZoom: 13 });
    S.fittedChangeAt = Date.now();                    // the region fly-to must not override this view
    S.timer = setTimeout(() => play(S), 1700);
  }
  renderPanel(S);
  showChange(S);
}

function showChange(S) {
  const map = S.map, ch = S.data.change;
  if (!ch || !map.getSource('chg-a')) return;
  const op = S.hideOverlay ? 0 : S.opacity, big = S.root.querySelector('.tdm-bigyear');
  big.style.display = 'none';
  if (S.chMode === 'timelapse') {
    const f = ch.frames[S.frame];
    followYear(S, f.year);
    setImg(S, 'chg-a', f.url);
    map.setPaintProperty('chg-a', 'raster-opacity', op);
    map.setPaintProperty('chg-b', 'raster-opacity', 0);
    big.innerHTML = `${f.year}<small>${esc(ch.var_plain)}</small>`;
    big.style.display = S.hideOverlay ? 'none' : 'block';
  } else if (S.chMode === 'beforeafter') {
    followYear(S, S.blend < 0.5 ? ch.years[0] : ch.years[ch.years.length - 1]);
    setImg(S, 'chg-a', ch.before.url);
    setImg(S, 'chg-b', ch.after.url);
    map.setPaintProperty('chg-a', 'raster-opacity', op);
    map.setPaintProperty('chg-b', 'raster-opacity', op * S.blend);
    big.innerHTML = `${S.blend < 0.5 ? ch.before.label : ch.after.label}<small>${S.blend < 0.5 ? 'before' : 'after'}</small>`;
    big.style.display = S.hideOverlay ? 'none' : 'block';
  } else {
    setImg(S, 'chg-a', S.sigOnly ? ch.trend.url_sig : ch.trend.url_all);
    map.setPaintProperty('chg-a', 'raster-opacity', op);
    map.setPaintProperty('chg-b', 'raster-opacity', 0);
  }
}

function play(S) {
  const ch = S.data.change;
  stopPlay(S);
  if (!ch || S.chMode !== 'timelapse') return;
  S.playing = true;
  updatePlayer(S);
  const step = () => {
    if (!S.playing) return;
    S.frame = (S.frame + 1) % ch.frames.length;
    showChange(S); updatePlayer(S);
    const hold = S.frame === ch.frames.length - 1 ? 1900 : 800;     // pause on the last year
    S.timer = setTimeout(step, hold / S.speed);
  };
  S.timer = setTimeout(step, 800 / S.speed);
}

function sparkSvg(ch, i) {
  const vals = ch.series, n = vals.length, W = 260, H = 46, pad = 5;
  const ok = vals.filter(v => v !== null);
  if (!ok.length) return '';
  const lo = Math.min(...ok), hi = Math.max(...ok), span = (hi - lo) || 1;
  const X = k => pad + k * (W - 2 * pad) / Math.max(n - 1, 1), Y = v => H - pad - (v - lo) / span * (H - 2 * pad);
  const pts = vals.map((v, k) => v === null ? null : `${X(k).toFixed(1)},${Y(v).toFixed(1)}`).filter(Boolean).join(' ');
  const cur = vals[i];
  const marker = cur !== null
    ? `<line x1="${X(i)}" x2="${X(i)}" y1="0" y2="${H}" stroke="rgba(255,181,71,0.35)"/><circle cx="${X(i)}" cy="${Y(cur)}" r="3.8" fill="#FFB547"/>`
    : '';
  return `<svg class="tdm-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">` +
    `<polyline points="${pts}" fill="none" stroke="#7C9CFF" stroke-width="1.8" vector-effect="non-scaling-stroke"/>${marker}</svg>`;
}

function updatePlayer(S) {
  const ch = S.data.change, p = S.root.querySelector('.tdm-layer');
  if (!ch || S.chMode !== 'timelapse') return;
  const f = ch.frames[S.frame], v = ch.series[S.frame];
  const yr = p.querySelector('.tdm-yr'); if (yr) yr.textContent = f.year;
  const sb = p.querySelector('.tdm-frame'); if (sb) sb.innerHTML = `your area: <b>${fmtNum(v)}</b> ${esc(ch.units)}`;
  const sc = p.querySelector('.tdm-scrub'); if (sc) sc.value = S.frame;
  const sp = p.querySelector('.tdm-sparkwrap'); if (sp) sp.innerHTML = sparkSvg(ch, S.frame);
  const pb = p.querySelector('.tdm-play'); if (pb) pb.textContent = S.playing ? '❚❚' : '▶';
}

function animateBlend(S, target) {
  const start = S.blend, t0 = performance.now(), dur = 900;
  const tick = (now) => {
    const k = Math.min((now - t0) / dur, 1), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    S.blend = start + (target - start) * e;
    showChange(S);
    const r = S.root.querySelector('.tdm-blend'); if (r) r.value = Math.round(S.blend * 100);
    if (k < 1 && S.chMode === 'beforeafter') requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function renderPanel(S) {
  const ch = S.data.change, panel = S.root.querySelector('.tdm-layer');
  if (!ch) { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  const tab = (m, label) => `<button data-cm="${m}" class="${S.chMode === m ? 'on' : ''}">${label}</button>`;
  const vl = ch.value_legend, tr = ch.trend;
  let body = '';
  if (S.chMode === 'timelapse') {
    body = `<div class="tdm-player"><button class="tdm-play" title="Play / pause">${S.playing ? '❚❚' : '▶'}</button>
        <div><div class="tdm-yr">${ch.frames[S.frame].year}</div><div class="sub tdm-frame"></div></div></div>
      <div class="tdm-sparkwrap">${sparkSvg(ch, S.frame)}</div>
      <input class="tdm-scrub" type="range" min="0" max="${ch.frames.length - 1}" value="${S.frame}" title="Drag through the years"/>
      <div class="tdm-chips">${[0.5, 1, 2].map(v => `<button data-sp="${v}" class="${S.speed === v ? 'on' : ''}">${v}×</button>`).join('')}</div>
      <div class="sub" style="margin-top:8px">Each frame is one year's average. Watch how the colours shift.</div>`;
  } else if (S.chMode === 'beforeafter') {
    body = `<div class="tdm-ba"><span>◀ ${esc(ch.before.label)}</span><span>${esc(ch.after.label)} ▶</span></div>
      <input class="tdm-blend" type="range" min="0" max="100" value="${Math.round(S.blend * 100)}" title="Slide between before and after"/>
      <button class="tdm-wide tdm-flip">⇄ Flip between before and after</button>
      <div class="sub" style="margin-top:8px">Slide to compare the first years with the last years.<br>Average change over the area: <b>${signed(ch.change_mean)} ${esc(ch.units)}</b></div>`;
  } else {
    body = `<div class="shares">
        <div><b style="color:#${tr.palette[3]}">${Math.round(tr.share_rising * 100)}%</b>${esc(ch.up_word)}</div>
        <div><b style="color:#${tr.palette[1]}">${Math.round(tr.share_falling * 100)}%</b>${esc(ch.down_word)}</div>
        <div><b>${Math.round((1 - tr.share_rising - tr.share_falling) * 100)}%</b>no clear change</div></div>
      <div class="sub">Where your area is really changing (${ch.years[0]}–${ch.years[ch.years.length - 1]}): every pixel gets its own yes/no test.</div>
      <label class="tdm-row" style="margin-top:6px;color:#C9CEDD"><input type="checkbox" class="tdm-sig" ${S.sigOnly ? 'checked' : ''} style="accent-color:#7C9CFF"/> significant pixels only</label>`;
  }
  const legend = S.chMode === 'trend'
    ? `<div class="lbl">Rate of change · ${esc(tr.units)}</div><div class="grad" style="background:${gradCss(tr.palette)}"></div>
       <div class="rng"><span>${signed(tr.vmin)}</span><span>0</span><span>${signed(tr.vmax)}</span></div><div class="sub">${esc(ch.down_word)} ← → ${esc(ch.up_word)}</div>`
    : `<div class="lbl">${esc(ch.var_plain)} · yearly ${ch.units.includes('/year') ? 'total' : 'average'}</div><div class="grad" style="background:${gradCss(vl.palette)}"></div>
       <div class="rng"><span>${fmtNum(vl.vmin)}</span><span>${esc(vl.units)}</span><span>${fmtNum(vl.vmax)}</span></div>`;
  panel.innerHTML = `<div class="tdm-tabs">${tab('timelapse', '▶ Time-lapse')}${tab('beforeafter', '⇄ Before/after')}${tab('trend', '📍 Where')}</div>
    ${body}<div class="tdm-sep"></div>${legend}
    <div class="tdm-row"><span>Opacity</span><input class="tdm-op" type="range" min="0" max="100" value="${Math.round(S.opacity * 100)}"/>
      <label><input type="checkbox" class="tdm-show" ${S.hideOverlay ? '' : 'checked'} style="accent-color:#7C9CFF"/> show</label></div>
    ${ch.synthetic ? '<div class="synthetic">⚠ Synthetic example (Earth Engine offline)</div>' : ''}
    <div class="sub" style="margin-top:7px">💡 ${TAP} any spot on the colours to get the answer for just that spot.</div>`;
  updatePlayer(S);

  panel.querySelectorAll('[data-cm]').forEach(b => b.onclick = () => {
    if (S.chMode === b.dataset.cm) return;
    stopPlay(S); S.chMode = b.dataset.cm; renderPanel(S); showChange(S);
  });
  const q = (sel) => panel.querySelector(sel);
  if (q('.tdm-play')) q('.tdm-play').onclick = () => { if (S.playing) { stopPlay(S); updatePlayer(S); } else play(S); };
  if (q('.tdm-scrub')) q('.tdm-scrub').oninput = (ev) => { stopPlay(S); S.frame = +ev.target.value; showChange(S); updatePlayer(S); };
  panel.querySelectorAll('[data-sp]').forEach(b => b.onclick = () => {
    S.speed = +b.dataset.sp;
    panel.querySelectorAll('[data-sp]').forEach(x => x.classList.toggle('on', x === b));
  });
  if (q('.tdm-blend')) q('.tdm-blend').oninput = (ev) => { S.blend = +ev.target.value / 100; showChange(S); };
  if (q('.tdm-flip')) q('.tdm-flip').onclick = () => animateBlend(S, S.blend < 0.5 ? 1 : 0);
  if (q('.tdm-sig')) q('.tdm-sig').onchange = (ev) => { S.sigOnly = ev.target.checked; showChange(S); };
  q('.tdm-op').oninput = (ev) => { S.opacity = +ev.target.value / 100; showChange(S); };
  q('.tdm-show').onchange = (ev) => { S.hideOverlay = !ev.target.checked; showChange(S); };
}

function syncCompare(S) {
  const map = S.map, cmp = S.data.compare || [];
  const key = JSON.stringify(cmp);
  if (key === S.compareKey) return;
  S.compareKey = key;
  map.getSource('compare').setData(fc(cmp.map(c => poly(circle(c.lat, c.lon, c.radius_km), { color: c.color }))));
  S.markers.compare.forEach(m => m.remove());
  S.markers.compare = cmp.map(c => {
    const el = document.createElement('div'); el.className = 'tdm-cmp';
    el.style.background = c.color; el.textContent = c.label; el.title = c.name;
    return new maplibregl.Marker({ element: el }).setLngLat([c.lon, c.lat]).addTo(map);
  });
}

function fitCompare(S) {
  const cmp = S.data.compare || [];
  if (!cmp.length) return;
  // spherical midpoint of all pins; far-apart pins (other side of the Earth) get a whole-globe view instead of zoom ~0
  let x = 0, y = 0, z = 0;
  cmp.forEach(c => { const la = c.lat * Math.PI / 180, lo = c.lon * Math.PI / 180;
                     x += Math.cos(la) * Math.cos(lo); y += Math.cos(la) * Math.sin(lo); z += Math.sin(la); });
  const center = [Math.atan2(y, x) * 180 / Math.PI, Math.atan2(z, Math.hypot(x, y)) * 180 / Math.PI];
  const ring = cmp.flatMap(c => circle(c.lat, c.lon, c.radius_km, 8));
  const cam = S.map.cameraForBounds(ringBounds(ring), { padding: viewPadding(S) });
  const lonSpan = ringBounds(ring)[1][0] - ringBounds(ring)[0][0];
  const zoom = (!cam || lonSpan > 100) ? 1.5 : Math.max(1.5, Math.min(cam.zoom, 8));
  S.map.flyTo({ center: lonSpan > 100 || !cam ? center : cam.center, zoom, duration: 1800, essential: true });
}

function syncPresets(S) {
  const d = S.data, key = JSON.stringify([d.presets, d.cases]);
  if (key === S.presetKey) return;
  S.presetKey = key;
  S.markers.presets.forEach(m => m.remove());
  S.markers.presets = (d.presets || []).map(p => {
    const el = document.createElement('div'); el.className = 'tdm-pin';
    el.innerHTML = `<span class="lb">🗂 ${esc(p.name)}</span>`;
    el.onclick = (ev) => { ev.stopPropagation(); S.emit('preset', { key: p.key, variable: p.variable || null }); };
    return new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(S.map);
  });
  S.root.querySelector('.tdm-cases').style.display = (d.cases || []).length ? '' : 'none';
  const list = S.root.querySelector('.tdm-cases .list');
  list.innerHTML = (d.cases || []).map((c, i) => `
    <div class="tdm-case" data-i="${i}"><div class="ic">${esc(c.icon)}</div>
      <div><div class="nm">${esc(c.title)}</div><div class="sb">${esc(c.subtitle)}</div></div></div>`).join('');
  list.querySelectorAll('.tdm-case').forEach(el => el.onclick = () => {
    const c = d.cases[+el.dataset.i];
    S.emit('preset', { key: c.preset, variable: c.variable, start_year: c.start_year });
  });
}
""".replace("__MLV__", MAPLIBRE_VERSION)

def _register():
    return st.components.v2.component("trend_detective_globe", css=CSS, js=JS, isolate_styles=False)


_MAP = _register()


def explorer_map(data: dict, key: str, on_event):
    """Mount the globe. `on_event` runs (as a Streamlit callback) whenever the map emits an event."""
    global _MAP
    try:
        return _MAP(data=data, key=key, on_event_change=on_event)
    except Exception as e:     # ValueError on Streamlit 1.5x, StreamlitAPIException on newer versions
        # A fresh Streamlit runtime (e.g. streamlit.testing.AppTest) starts with an empty
        # component registry while this module stays imported: register again and retry.
        if "not registered" not in str(e):
            raise
        _MAP = _register()
        return _MAP(data=data, key=key, on_event_change=on_event)


def read_event(key: str):
    """Inside the callback: the payload of the event that triggered it."""
    val = st.session_state.get(key)
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("event")
    return getattr(val, "event", None)
