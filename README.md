# Trend Detective

**Is our planet changing where you care about?** Pick a place on a 3D globe, pick what to look at (plants, heat, rain, soil water, snow or city lights), and get a plain answer backed by 25 years of NASA satellite data. You can also watch the change happen on the map, year by year.

*NASA Space Apps Challenge 2026 — "Be An Earth System Trend Detective!"*

---

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

It works straight away in **demo mode**: the example places on the globe use real NASA data that ships with the app. To explore *any* place on Earth with live NASA data, [connect Google Earth Engine](#connect-live-nasa-data).

## How to use it

1. **Pick a place.** Click anywhere on the globe, search for a city or region, draw an area, or open one of the 11 **examples** (8 places and 3 comparisons; also as orange pins on the globe).
2. **Pick what to look at.** For example, 🌿 *Plant greenness* asks "Is the land getting greener?", 🌡️ *Air temperature* asks "Is the air getting warmer?", and 💧 *All water stored* asks "Is the region gaining or losing water?"
3. **Get the answer.**
   - **The answer card** says *Yes / Maybe / No clear change* and shows **how sure** we are, **how much** it changed, and **how steady** the change was.
   - **🎬 Watch it change** (under the globe) plays a **time-lapse** on the globe. It also offers a **before/after** slider and a **📍 Where** map of the spots that are really changing. The maps cover only the area you picked; picking a new place, size or outline clears them until you press the button again. Click any coloured spot to get the answer for just that spot.
   - **⚖️ Compare places** shows whether the same thing happens everywhere. Often it doesn't!
   - **🔍 What else is changing here?** checks every measurement for your place at once.
   - **📘 How it works** explains the method in plain words, with a glossary.

**On a phone** the app works too: the globe sits on top and its controls below it. Move and zoom the globe with two fingers (one finger scrolls the page), and when drawing an area, tap the corners and then **✓ Finish area**.

Every screen keeps the technical details (p-values, Sen's slope, test statistics) in a **"For experts"** section, so nothing is hidden, but nobody has to read it to understand the answer.

---

## The challenge, answered

| Challenge question | Where in the app | How it is answered |
|---|---|---|
| **What** is changing? | 🔍 *What else is changing here?* | The same test for all 16 NASA measurements at one place, with a stricter correction because many things are tested at once |
| **Where** is it changing? | 🎬 *Watch it change* on the globe, ⚖️ *Compare places* | Yearly maps shown only inside the area you picked, circle or drawn outline (time-lapse, before/after, per-pixel "where" map), plus side-by-side places, which often move in opposite directions |
| **How much** is it changing? | ✅ *The answer* | Total change since the first year (e.g. "42% greener since 2001"), change per 10 years, and a comparison with normal year-to-year ups and downs |
| Is it **significant**? | everywhere | "How sure are we?" meter based on the seasonal Mann-Kendall test with the Hirsch–Slack correction |

## What we found (real NASA data, checked 28 Sep 2026)

| Place | Measurement | Change | Real change? |
|---|---|---|---|
| Loess Plateau, China (tree planting) | Daytime ground temperature | **−3.0 °C** since 2001 | yes (p < 0.001) |
| Amazon deforestation front, Brazil | Daytime ground temperature | **+1.5 °C** since 2001 | yes (p < 0.001) |
| Loess Plateau, China | Plant greenness | **+42%** since 2001 | yes (p < 0.001) |
| Punjab & Haryana, India | All water stored (GRACE) | **−4.4 cm per year** | yes (p < 0.001) |
| Lake Victoria basin | All water stored (GRACE) | **+3.3 cm per year** | yes (p < 0.001) |
| Former Kakhovka Reservoir bed, Ukraine | Plant greenness | −0.05 (open water) → 0.49 after the June 2023 dam breach | yes (p = 0.03) — a sudden event, not a slow trend |

**Same cause, opposite effect.** Plants cool the ground by moving water into the air. Where trees were planted (China), daytime ground temperature fell. Where forest was cut (Brazil), it rose. The *Compare places* view opens with this example.

---

## Connect live NASA data

The app reads NASA data through **Google Earth Engine** (free for research and education).

1. Create a Google Cloud project with the Earth Engine API enabled ([instructions](https://developers.google.com/earth-engine/guides/access)).
2. Copy `.env.example` to `.env` and set `GEE_PROJECT=your-project-id`.
3. Run `python auth.py` once to log in, then restart the app.

Optional: add a free [Groq](https://console.groq.com) key as `GROQ_API_KEY` in `.env` for AI-written explanations (✨ *Explain it with AI*). Without it, the app writes the explanations from a built-in template.

## NASA data used

| What it shows | Satellite / model | Agency | Detail | Years |
|---|---|---|---|---|
| 🌿 Plant greenness (NDVI), 🌳 plant growth (EVI) | Terra MODIS `MOD13A3` | NASA | 1 km | 2000– |
| 🌾 Plant greenness, 🏙️ buildings & bare ground — 30 m | Harmonized Landsat Sentinel-2 (HLS) | NASA | 30 m | 2014– |
| ☀️🌙 Ground temperature, day and night | Terra MODIS `MOD11A2` | NASA | 1 km | 2001– |
| 🌡️ Air temperature, 💧 soil wetness | FLDAS Noah land model | NASA GSFC | 11 km | 1982– |
| 🌧️ Rain & snowfall | GPM IMERG V07 | NASA / JAXA | 11 km | 1998–2025 |
| 🛰️ Soil wetness (satellite) | SMAP Level-4 | NASA | 11 km | 2016– |
| 💨 Water rising from land & plants | Terra MODIS `MOD16A2GF` | NASA | 500 m | 2001–2025 |
| 🌊 All water stored, incl. underground | GRACE / GRACE-FO | NASA / DLR / GFZ | ~300 km | 2002–2024 |
| 🗺️ All water stored (sharper), 🚰 groundwater | GLDAS-2.2 Catchment land model with GRACE data assimilation | NASA GSFC | 28 km (model) | 2003– |
| ❄️ Snow cover | Terra MODIS `MOD10A1` | NASA | 500 m | 2001– |
| 💡 Lights at night | Suomi NPP VIIRS | NASA / NOAA | 463 m | 2014– |

Base maps, each with a year menu on the globe:
- **🌃 Night:** yearly VIIRS night lights 2013–2025 (Earth Observation Group, from the NASA/NOAA Suomi NPP Day/Night Band), drawn by Google Earth Engine in the style of NASA's Black Marble (dark navy land, black water, small gold-white lights). Everything under the lights shows the same year: water is detected from that year's MODIS near-infrared (MOD13A3), and up close a darkened satellite photo of that year fades in, so e.g. the drained Kakhovka Reservoir is water in 2021 and land in 2025. Without Earth Engine: NASA Black Marble 2012 or 2016 via NASA GIBS.
- **🛰 Satellite:** cloud-free satellite photos of 2016–2025 from [Sentinel-2 cloudless](https://s2maps.eu) by EOX IT Services GmbH (contains modified Copernicus Sentinel data; 2016 CC BY 4.0, later years CC BY-NC-SA 4.0). For example, Kakhovka shows a full reservoir in 2021 and the overgrown lake bed in 2025. While a time-lapse plays, the satellite photo follows its year (years before 2016 use the 2016 photo), and picking a year in the menu moves the time-lapse to that year. The night map stays on the year you pick: yearly night maps differ too much to play as a time-lapse.
- Esri Dark Gray Canvas and labels. No keys are needed.

---

## For developers and judges

### Method

1. **Monthly series:** region means per month, computed in Earth Engine. HLS scenes are cloud-, shadow- and snow-masked first.
2. **Significance:** the seasonal Mann-Kendall test compares January only with January, July only with July, and so on, so seasons can't masquerade as a trend. It is non-parametric and handles missing months.
3. **Hirsch & Slack (1984) correction:** neighbouring months are correlated. In our simulations the textbook seasonal test flagged **12–25%** of trend-free series as "significant" at α = 0.05. The corrected test stays at **≤ 5%** (checked in [tests/test_trends.py](tests/test_trends.py)).
4. **Magnitude:** seasonal Sen's slope (the median of all same-month year-to-year slopes) with a distribution-free confidence interval. A linear regression on deseasonalized anomalies, with an autocorrelation-adjusted p-value, is the cross-check.
5. **Maps:** one Earth Engine `computePixels` request returns yearly means on a 200 × 200 grid (about 3 s for 25 years of MODIS). The time-lapse, before/after and per-pixel trend (Sen + Mann-Kendall) are computed from it locally.
6. **Many tests at once:** "check everything" uses Benjamini–Hochberg false-discovery-rate q-values.

**Why 25 years and not 5?** With 5 yearly values, even a perfectly steady series can't get below p = 0.028. In simulations, a modest trend is detected only 20–40% of the time over 6 years, but 93–100% of the time over 10 years.

**Limitations.** A significant trend means the change is unlikely to be chance *in this record*. It does not identify the cause. Sudden events (a dam breach) show up as changes but are steps, not slow trends. GRACE's ~300 km footprint can't resolve small places. The sharper GLDAS water measurements (28 km) get their detail from a land model guided by GRACE; where groundwater is pumped heavily they show a smaller loss than GRACE (NW India: about −8 vs −44 cm per 10 years), so GRACE stays the reference for how much water a region is losing.

### Manual setup and tests

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
python -m pytest -q
```

The 53 tests do three things:
- check the statistics against SciPy and an independent loop implementation of Hirsch–Slack;
- check the false-alarm rate on simulated data;
- run the whole app headless in demo mode, including simulated globe clicks.

They pass on Streamlit 1.58 and 1.64.

**Offline data:** `data/demo_cache.csv.gz` holds 164 real monthly series and `data/demo_cubes.npz` holds 22 yearly map cubes. To rebuild them while online, run `python scripts/build_demo_cache.py` (`--missing-only` resumes, `--cubes-only`, `--synthetic`).

### Project layout

| File | Purpose |
|---|---|
| [app.py](app.py) | Streamlit app: examples, globe, answer, compare, "check everything" and how-it-works views |
| [map_component.py](map_component.py) | Interactive 3D globe (MapLibre GL custom component): click, search, draw, compare pins, time-lapse player |
| [plain.py](plain.py) | Plain-language answers: yes/maybe/no, "how sure", "how much", glossary |
| [trends.py](trends.py) | Statistics: seasonal Mann-Kendall + Hirsch–Slack, Sen's slope, OLS cross-check, Benjamini–Hochberg, per-pixel test |
| [nasa_variables.py](nasa_variables.py) | Catalog of NASA measurements: dataset IDs, units, plain names and questions |
| [geoai_engine.py](geoai_engine.py) | Earth Engine access: monthly series and yearly map cubes |
| [change_maps.py](change_maps.py) | Turns a map cube into time-lapse frames, before/after images and the "where" map |
| [demo_data.py](demo_data.py) | Offline data: saved NASA series and maps, plus a clearly labelled synthetic fallback |
| [llm_summary.py](llm_summary.py) | Plain-language explanations (template, or Groq llama-3.3-70b) |
| [regions.py](regions.py) | Example places and comparisons (checked against real data) |
| [ui_theme.py](ui_theme.py) | Visual design: CSS, chart theme, HTML building blocks |
| [examples_strip.py](examples_strip.py) | The row of example tiles above the globe |
| [auth.py](auth.py) | One-time Earth Engine login on a new computer |
| [scripts/build_demo_cache.py](scripts/build_demo_cache.py) | Builds the offline data |
| [tests/](tests/) | Statistics, offline data and headless app tests |

### References

- Hirsch, Slack & Smith (1982), *Water Resources Research* 18(1) — seasonal Kendall test.
- Hirsch & Slack (1984), *Water Resources Research* 20(6) — covariance-corrected seasonal test.
- Sen (1968), *JASA* 63 — slope estimator; Gilbert (1987) — confidence interval.
- Benjamini & Hochberg (1995), *JRSS B* 57 — false discovery rate.
- Rodell et al. (2018), *Nature* 557 — emerging trends in global freshwater availability (GRACE).
