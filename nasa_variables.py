"""
Trend Detective — catalog of NASA-measured / NASA-modelled variables.

Every entry was checked against the Google Earth Engine catalog
(IDs, bands, scale factors, record length) on 2026-09-25.
Adding a variable = adding one Variable(...) entry; the data layer,
statistics, charts and LLM summaries all read from this registry.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime

LAST_FULL_YEAR = datetime.now().year - 1

# Diverging palettes for trend maps: (falling colour ... 0 ... rising colour)
BROWN_GREEN = ["8c510a", "d8b365", "f6f6f6", "5ab4ac", "01665e"]
BLUE_RED = ["2166ac", "92c5de", "f7f7f7", "f4a582", "b2182b"]
RED_BLUE = ["b2182b", "f4a582", "f7f7f7", "92c5de", "2166ac"]
PURPLE_ORANGE = ["542788", "b2abd2", "f7f7f7", "fdb863", "b35806"]

# Sequential palettes for the values themselves (time-lapse and before/after maps), low -> high
SEQ_GREEN = ["5c3a14", "a07534", "d9c27a", "b8dc8a", "5fb35a", "1f7a3a", "0b4a24"]
SEQ_BUILT = ["1b6b3a", "5aa55a", "c9d98c", "f6d58b", "f08a4b", "c73b2b"]
SEQ_HEAT = ["313695", "4575b4", "74add1", "abd9e9", "fee090", "fdae61", "f46d43", "d73027", "a50026"]
SEQ_RAIN = ["fff4b8", "c7e9b4", "7fcdbb", "41b6c4", "1d91c0", "225ea8", "0c2c84"]
SEQ_SOIL = ["7a4a12", "c69b52", "efe0b0", "b9e2dc", "4fb0a5", "0d6b5f"]
SEQ_SNOW = ["16213a", "2c5a8c", "5f95cf", "a9cdf2", "e9f4ff", "ffffff"]
SEQ_LIGHTS = ["000004", "3b0f70", "8c2981", "de4968", "fe9f6d", "fcfdbf"]
DIV_WATER = ["b2182b", "ef8a62", "fddbc7", "f7f7f7", "d1e5f0", "67a9cf", "2166ac"]


@dataclass(frozen=True)
class Variable:
    key: str
    name: str
    group: str
    units: str
    collection: str
    band: str
    pixel_m: int
    start_year: int
    mission: str
    agency: str
    kind: str                          # "satellite" | "model" | "satellite + model"
    description: str
    higher_means: str                  # plain-language meaning of an increase
    scale: float = 1.0
    offset: float = 0.0
    rate: str | None = None            # "per_hour" | "per_second" | "per_8day": convert rate -> monthly total
    valid_range: tuple | None = None
    preprocess: str | None = None      # special handling in geoai_engine
    end_year: int | None = None        # None = ongoing
    relative_change: bool = True       # report change as % of mean level?
    palette: tuple = tuple(BROWN_GREEN)
    notes: str = ""
    short: str = ""                    # compact label for pills / cards
    icon: str = "🛰️"
    seq_palette: tuple = tuple(SEQ_GREEN)  # colour scale for the values (time-lapse, before/after)
    centered: bool = False             # values are anomalies around 0 -> symmetric colour scale
    # ── plain language for non-experts ──
    plain: str = ""                    # everyday name, e.g. "Plant greenness"
    question: str = ""                 # e.g. "Is the land getting greener?"
    up_word: str = "higher"            # what "rising" means, e.g. "greener"
    down_word: str = "lower"           # what "falling" means, e.g. "less green"
    explain: str = ""                  # one sentence, no jargon
    up_phrase: str = "it is rising"    # full clause for a rising trend
    down_phrase: str = "it is falling"

    @property
    def last_year(self) -> int:
        return min(self.end_year or LAST_FULL_YEAR, LAST_FULL_YEAR)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.units})"

    @property
    def source_line(self) -> str:
        return f"{self.mission} · {self.agency} · {self.kind} · ~{fmt_distance(self.pixel_m)} pixels · {self.start_year}–{self.last_year}"

    def monthly_factor(self, year: int, month: int) -> float:
        """Multiplier that turns a mean rate into a monthly total (1.0 for state variables)."""
        days = calendar.monthrange(year, month)[1]
        return {
            "per_hour": 24.0 * days,
            "per_second": 86400.0 * days,
            "per_8day": days / 8.0,
        }.get(self.rate, 1.0)

    @property
    def annual_factor(self) -> float:
        """Multiplier that turns a mean rate into an annual total (for trend maps)."""
        return {
            "per_hour": 24.0 * 365.25,
            "per_second": 86400.0 * 365.25,
            "per_8day": 365.25 / 8.0,
        }.get(self.rate, 1.0)

    @property
    def map_units(self) -> str:
        """Units of the annual values used in trend maps."""
        return self.units.replace("/month", "/year") if self.rate else self.units


def fmt_distance(m: float) -> str:
    return f"{m:.0f} m" if m < 1000 else f"{m / 1000:.0f} km"


VARIABLES: dict[str, Variable] = {v.key: v for v in [
    # ── Vegetation ──────────────────────────────────────────────────────
    Variable(
        key="ndvi_modis", up_phrase="the land is getting greener", down_phrase="the land is getting less green", plain="Plant greenness", question="Is the land getting greener?", up_word="greener", down_word="less green", explain="How much healthy green vegetation covers the ground, measured from space by NASA's Terra satellite.", seq_palette=tuple(SEQ_GREEN), short="NDVI · MODIS", icon="🌿", name="Vegetation greenness (NDVI)", group="Plants",
        units="NDVI", collection="MODIS/061/MOD13A3", band="NDVI", scale=0.0001,
        pixel_m=1000, start_year=2000, mission="Terra MODIS", agency="NASA", kind="satellite",
        description="Normalized Difference Vegetation Index from the monthly MODIS vegetation-index composite.",
        higher_means="greener, denser or healthier vegetation",
    ),
    Variable(
        key="evi_modis", up_phrase="plants are growing more", down_phrase="plants are growing less", plain="Plant growth", question="Are plants growing more?", up_word="more plant growth", down_word="less plant growth", explain="How actively plants are growing — like greenness, but better for dense forests.", seq_palette=tuple(SEQ_GREEN), short="EVI · MODIS", icon="🌳", name="Enhanced Vegetation Index (EVI)", group="Plants",
        units="EVI", collection="MODIS/061/MOD13A3", band="EVI", scale=0.0001,
        pixel_m=1000, start_year=2000, mission="Terra MODIS", agency="NASA", kind="satellite",
        description="Like NDVI but less saturated over dense canopies and less sensitive to soil and haze.",
        higher_means="more photosynthetically active vegetation",
    ),
    Variable(
        key="ndvi_hls", up_phrase="the land is getting greener", down_phrase="the land is getting less green", plain="Plant greenness (sharp, 30 m)", question="Is the land getting greener, field by field?", up_word="greener", down_word="less green", explain="Plant greenness at 30 m detail — you can see single fields — from NASA's Landsat + Sentinel-2 product.", seq_palette=tuple(SEQ_GREEN), short="NDVI 30 m · HLS", icon="🌾", name="Vegetation greenness, 30 m (NDVI)", group="Plants",
        units="NDVI", collection="NASA/HLS/HLSL30/v002 + HLSS30/v002", band="NDVI",
        pixel_m=30, start_year=2014, preprocess="hls_ndvi",
        mission="Harmonized Landsat 8/9 + Sentinel-2 (HLS)", agency="NASA", kind="satellite",
        description="Field-scale NDVI from NASA's Harmonized Landsat Sentinel-2 product, cloud/shadow/snow masked with Fmask.",
        higher_means="greener, denser or healthier vegetation",
        notes="Sentinel-2 scenes join from late 2015, so early years have fewer clear views.",
    ),
    Variable(
        key="ndbi_hls", up_phrase="the area is getting more built-up", down_phrase="the area is getting less built-up", plain="Buildings & bare ground", question="Is the area getting more built-up?", up_word="more built-up", down_word="less built-up", explain="How much of the ground is roofs, roads or bare soil instead of plants, at 30 m detail.", seq_palette=tuple(SEQ_BUILT), short="Built-up 30 m · HLS", icon="🏙️", name="Built-up index, 30 m (NDBI)", group="People",
        units="NDBI", collection="NASA/HLS/HLSL30/v002 + HLSS30/v002", band="NDBI",
        pixel_m=30, start_year=2014, preprocess="hls_ndbi",
        mission="Harmonized Landsat 8/9 + Sentinel-2 (HLS)", agency="NASA", kind="satellite",
        description="Normalized Difference Built-up Index (SWIR vs NIR). Rises with impervious surfaces and bare soil.",
        higher_means="more built-up / impervious or bare surface",
        relative_change=False, palette=tuple(PURPLE_ORANGE),
    ),
    # ── Temperature ─────────────────────────────────────────────────────
    Variable(
        key="lst_day", up_phrase="the ground is getting hotter during the day", down_phrase="the ground is getting cooler during the day", plain="Ground temperature (day)", question="Is the ground getting hotter during the day?", up_word="hotter", down_word="cooler", explain="How hot the ground surface is around 10:30 in the morning, measured by NASA's Terra satellite.", seq_palette=tuple(SEQ_HEAT), short="Surface temp · day", icon="☀️", name="Land surface temperature, day", group="Heat",
        units="°C", collection="MODIS/061/MOD11A2", band="LST_Day_1km", scale=0.02, offset=-273.15,
        pixel_m=1000, start_year=2001, mission="Terra MODIS", agency="NASA", kind="satellite",
        description="Daytime (~10:30 local) skin temperature of the land surface from 8-day composites.",
        higher_means="a hotter land surface in daytime",
        relative_change=False, palette=tuple(BLUE_RED),
    ),
    Variable(
        key="lst_night", up_phrase="the nights are getting warmer", down_phrase="the nights are getting cooler", plain="Ground temperature (night)", question="Are the nights getting warmer?", up_word="warmer", down_word="cooler", explain="How warm the ground surface is around 10:30 at night.", seq_palette=tuple(SEQ_HEAT), short="Surface temp · night", icon="🌙", name="Land surface temperature, night", group="Heat",
        units="°C", collection="MODIS/061/MOD11A2", band="LST_Night_1km", scale=0.02, offset=-273.15,
        pixel_m=1000, start_year=2001, mission="Terra MODIS", agency="NASA", kind="satellite",
        description="Night-time (~22:30 local) skin temperature of the land surface from 8-day composites.",
        higher_means="warmer nights at the land surface",
        relative_change=False, palette=tuple(BLUE_RED),
    ),
    Variable(
        key="air_temp", up_phrase="the air is getting warmer", down_phrase="the air is getting cooler", plain="Air temperature", question="Is the air getting warmer?", up_word="warmer", down_word="cooler", explain="The temperature of the air near the ground, from a NASA computer model of the land.", seq_palette=tuple(SEQ_HEAT), short="Air temperature", icon="🌡️", name="Air temperature (near surface)", group="Heat",
        units="°C", collection="NASA/FLDAS/NOAH01/C/GL/M/V001", band="Tair_f_tavg", offset=-273.15,
        pixel_m=11000, start_year=1982, mission="FLDAS Noah land model", agency="NASA GSFC", kind="model",
        description="Monthly mean near-surface air temperature from the FEWS NET Land Data Assimilation System.",
        higher_means="warmer air",
        relative_change=False, palette=tuple(BLUE_RED),
    ),
    # ── Water ───────────────────────────────────────────────────────────
    Variable(
        key="precipitation", up_phrase="it is getting wetter", down_phrase="it is getting drier", plain="Rain & snowfall", question="Is it getting wetter or drier?", up_word="wetter", down_word="drier", explain="How much rain and snow falls each month, measured by the NASA/JAXA GPM satellites.", seq_palette=tuple(SEQ_RAIN), short="Precipitation", icon="🌧️", name="Precipitation", group="Water",
        units="mm/month", collection="NASA/GPM_L3/IMERG_MONTHLY_V07", band="precipitation",
        rate="per_hour", pixel_m=11000, start_year=1998, end_year=2025,
        mission="GPM IMERG (merged satellite-gauge)", agency="NASA / JAXA", kind="satellite",
        description="Monthly precipitation from the Integrated Multi-satellitE Retrievals for GPM, version 07.",
        higher_means="wetter conditions (more rain and snow)",
        palette=tuple(RED_BLUE),
        notes="The GEE copy currently ends in September 2025.",
    ),
    Variable(
        key="soil_moisture", up_phrase="the soil is getting wetter", down_phrase="the soil is getting drier", plain="Soil wetness", question="Is the soil getting wetter or drier?", up_word="wetter", down_word="drier", explain="How much water is in the top 10 cm of soil, from a NASA computer model of the land.", seq_palette=tuple(SEQ_SOIL), short="Soil moisture · FLDAS", icon="💧", name="Soil moisture, 0–10 cm", group="Water",
        units="m³/m³", collection="NASA/FLDAS/NOAH01/C/GL/M/V001", band="SoilMoi00_10cm_tavg",
        pixel_m=11000, start_year=1982, mission="FLDAS Noah land model", agency="NASA GSFC", kind="model",
        description="Monthly volumetric water content of the top 10 cm of soil.",
        higher_means="wetter topsoil",
        palette=tuple(RED_BLUE),
    ),
    Variable(
        key="soil_moisture_smap", up_phrase="the soil is getting wetter", down_phrase="the soil is getting drier", plain="Soil wetness (satellite)", question="Is the soil getting wetter or drier?", up_word="wetter", down_word="drier", explain="How much water is in the top 5 cm of soil, measured by NASA's SMAP satellite.", seq_palette=tuple(SEQ_SOIL), short="Soil moisture · SMAP", icon="🛰️", name="Soil moisture, 0–5 cm (SMAP)", group="Water",
        units="m³/m³", collection="NASA/SMAP/SPL4SMGP/008", band="sm_surface",
        pixel_m=11000, start_year=2016, mission="SMAP Level-4 (radiometer + model)", agency="NASA", kind="satellite + model",
        description="Surface soil moisture from SMAP brightness temperatures assimilated into a land model (3-hourly, averaged to months).",
        higher_means="wetter topsoil",
        palette=tuple(RED_BLUE),
        notes="3-hourly source data: the first request for a new region can take a minute.",
    ),
    Variable(
        key="evapotranspiration", up_phrase="more water is evaporating from the land", down_phrase="less water is evaporating from the land", plain="Water rising from land & plants", question="Is more water evaporating from the land?", up_word="more evaporation", down_word="less evaporation", explain="How much water goes back into the air from soil and plant leaves.", seq_palette=tuple(SEQ_RAIN), short="Evapotranspiration", icon="💨", name="Evapotranspiration", group="Water",
        units="mm/month", collection="MODIS/061/MOD16A2GF", band="ET", scale=0.1, rate="per_8day",
        pixel_m=500, start_year=2001, end_year=2025, mission="Terra MODIS", agency="NASA", kind="satellite",
        description="Water evaporated from soil and transpired by plants (gap-filled 8-day product).",
        higher_means="more water returned to the atmosphere by land and plants",
        palette=tuple(RED_BLUE),
    ),
    Variable(
        key="water_storage", up_phrase="the region is gaining water", down_phrase="the region is losing water", plain="All water stored (incl. underground)", question="Is the region gaining or losing water?", up_word="gaining water", down_word="losing water", explain="All water in a large region — lakes, soil, snow and groundwater — weighed by the GRACE satellites through tiny changes in Earth's gravity.", seq_palette=tuple(DIV_WATER), centered=True, short="Water storage · GRACE", icon="🌊", name="Total water storage anomaly (GRACE)", group="Water",
        units="cm water", collection="NASA/GRACE/MASS_GRIDS_V04/MASCON_CRI", band="lwe_thickness",
        pixel_m=55000, start_year=2002, end_year=2024,
        mission="GRACE & GRACE-FO (JPL mascons)", agency="NASA / DLR / GFZ", kind="satellite",
        description="Change in all water stored on and below the land surface (groundwater, soil, snow, lakes), "
                    "as equivalent water depth relative to the 2004–2009 mean.",
        higher_means="more water stored in the region (groundwater, soil moisture, snow, surface water)",
        relative_change=False, palette=tuple(RED_BLUE),
        notes="Native resolution is ~300 km (3° mascons); there is an 11-month gap between GRACE and GRACE-FO (2017–2018).",
    ),
    # GLDAS-2.2 Catchment model with GRACE data assimilation: GRACE's water totals spread over a 0.25° grid
    Variable(
        key="water_storage_gldas", up_phrase="the region is gaining water", down_phrase="the region is losing water", plain="All water stored (model, sharper)", question="Is the region gaining or losing water?", up_word="gaining water", down_word="losing water", explain="All water held by the land — groundwater, soil, snow and plants — from NASA's GLDAS land model, kept on track by the GRACE satellites. About 10× sharper than GRACE alone.", seq_palette=tuple(SEQ_RAIN), short="Water storage · GLDAS", icon="🗺️", name="Terrestrial water storage (GLDAS + GRACE)", group="Water",
        units="cm water", collection="NASA/GLDAS/V022/CLSM/G025/DA1D", band="TWS_tavg", scale=0.1,
        pixel_m=27830, start_year=2003, mission="GLDAS Catchment land model + GRACE data assimilation", agency="NASA GSFC", kind="model",
        description="Daily total water storage of the land (groundwater, soil moisture, snow, canopy water) from the "
                    "GLDAS-2.2 Catchment model, which assimilates GRACE/GRACE-FO, on a 0.25° grid.",
        higher_means="more water stored in the land (groundwater, soil, snow)",
        relative_change=False, palette=tuple(RED_BLUE),
        notes="A computer model guided by GRACE: the ~28 km detail comes from the model, GRACE itself only sees ~300 km. "
              "Water in lakes and rivers is not included, and where groundwater is pumped heavily the model shows a "
              "smaller loss than GRACE (NW India: about −8 vs −44 cm per 10 years).",
    ),
    Variable(
        key="groundwater_gldas", up_phrase="groundwater is building up", down_phrase="groundwater is running out", plain="Groundwater (model)", question="Is the groundwater running out?", up_word="more groundwater", down_word="less groundwater", explain="Water stored deep underground, from NASA's GLDAS land model kept on track by the GRACE satellites (28 km detail).", seq_palette=tuple(SEQ_RAIN), short="Groundwater · GLDAS", icon="🚰", name="Groundwater storage (GLDAS + GRACE)", group="Water",
        units="cm water", collection="NASA/GLDAS/V022/CLSM/G025/DA1D", band="GWS_tavg", scale=0.1,
        pixel_m=27830, start_year=2003, mission="GLDAS Catchment land model + GRACE data assimilation", agency="NASA GSFC", kind="model",
        description="Daily groundwater storage from the GLDAS-2.2 Catchment model, which assimilates GRACE/GRACE-FO, "
                    "on a 0.25° grid.",
        higher_means="more water stored underground",
        relative_change=False, palette=tuple(RED_BLUE),
        notes="A computer model guided by GRACE: the ~28 km detail comes from the model, GRACE itself only sees ~300 km. "
              "Pumping for irrigation is not modelled directly, so where it is heavy the model shows a smaller loss than "
              "GRACE (NW India: about −6 vs −44 cm per 10 years).",
    ),
    # ── Snow & ice ──────────────────────────────────────────────────────
    Variable(
        key="snow_cover", up_phrase="there is more snow", down_phrase="the snow is disappearing", plain="Snow cover", question="Is the snow disappearing?", up_word="snowier", down_word="less snowy", explain="How much of the ground is covered by snow, averaged over each month.", seq_palette=tuple(SEQ_SNOW), short="Snow cover", icon="❄️", name="Snow cover", group="Snow & ice",
        units="% of area", collection="MODIS/061/MOD10A1", band="NDSI_Snow_Cover", valid_range=(0, 100),
        pixel_m=500, start_year=2001, mission="Terra MODIS", agency="NASA", kind="satellite",
        description="Daily fractional snow cover (NDSI-based), averaged to monthly means over cloud-free days.",
        higher_means="more snow on the ground",
        relative_change=False, palette=tuple(RED_BLUE),
        notes="Daily source data: long periods take longer to compute.",
    ),
    # ── Human activity ──────────────────────────────────────────────────
    Variable(
        key="night_lights", up_phrase="the nights are getting brighter", down_phrase="the nights are getting darker", plain="Lights at night", question="Are there more lights at night?", up_word="brighter", down_word="darker", explain="How bright the area is at night — a sign of cities, roads and economic activity.", seq_palette=tuple(SEQ_LIGHTS), short="Night lights", icon="💡", name="Night-time lights", group="People",
        units="nW/cm²/sr", collection="NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", band="avg_rad",
        pixel_m=463, start_year=2014, mission="Suomi NPP VIIRS Day/Night Band", agency="NASA / NOAA", kind="satellite",
        description="Monthly average night-time radiance (stray-light corrected), a proxy for settlement, economic activity and power supply.",
        higher_means="brighter nights (more lighting, settlement or economic activity)",
        palette=tuple(PURPLE_ORANGE),
        notes="High-latitude summer months are missing (no true darkness).",
    ),
]}

ORDER = ["ndvi_modis", "evi_modis", "ndvi_hls",
         "lst_day", "lst_night", "air_temp",
         "precipitation", "soil_moisture", "soil_moisture_smap", "evapotranspiration", "water_storage",
         "water_storage_gldas", "groundwater_gldas",
         "snow_cover",
         "night_lights", "ndbi_hls"]
VARIABLES = {k: VARIABLES[k] for k in ORDER}

GROUPS = list(dict.fromkeys(v.group for v in VARIABLES.values()))
TOPIC_ICONS = {"Plants": "🌿", "Heat": "🌡️", "Water": "💧", "Snow & ice": "❄️", "People": "🏙️"}


def get(key: str) -> Variable:
    return VARIABLES[key]


def by_group() -> dict[str, list[Variable]]:
    return {g: [v for v in VARIABLES.values() if v.group == g] for g in GROUPS}
