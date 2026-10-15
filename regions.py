"""
Trend Detective — preset regions and "case files".

Each story was screened against the real NASA data on 2026-09-28 before being
written down here; the claims in `finding` are what the data showed then
(periods and p-values from the seasonal Mann-Kendall test in trends.py).
"""

PRESETS = {
    "loess_plateau": dict(
        name="Loess Plateau, China", lat=36.8, lon=109.5, radius_km=40,
        blurb="Large-scale afforestation and 'Grain for Green' since 1999.",
    ),
    "amazon_front": dict(
        name="Amazon deforestation front, Pará, Brazil", lat=-7.2, lon=-55.5, radius_km=40,
        blurb="Forest cleared for pasture along the BR-163 highway (Novo Progresso).",
    ),
    "kakhovka_bed": dict(
        name="Former Kakhovka Reservoir bed, Ukraine", lat=47.54, lon=35.12, radius_km=8,
        blurb="The reservoir drained after the dam was destroyed in June 2023; a young forest is growing on the old lake bed.",
    ),
    "cherkasy_farmland": dict(
        name="Farmland near Smila, Cherkasy, Ukraine", lat=49.444, lon=31.998, radius_km=25,
        blurb="Rain-fed cropland in central Ukraine.",
    ),
    "nw_india": dict(
        name="Punjab & Haryana, India", lat=29.8, lon=75.8, radius_km=250,
        blurb="Intensive irrigated agriculture fed by groundwater pumping.",
    ),
    "lake_victoria": dict(
        name="Lake Victoria basin, East Africa", lat=-1.0, lon=33.0, radius_km=250,
        blurb="Record lake levels after very wet years (2019–2020).",
    ),
    "caspian_north": dict(
        name="Northern Caspian Sea", lat=45.5, lon=51.0, radius_km=250,
        blurb="The world's largest lake is shrinking.",
    ),
    "aral_basin": dict(
        name="Aral Sea basin", lat=45.0, lon=60.0, radius_km=300,
        blurb="Rivers feeding the Aral Sea have been diverted for irrigation since the 1960s.",
    ),
    "amu_darya_fields": dict(
        name="Khorezm irrigated oasis, Uzbekistan", lat=41.55, lon=60.62, radius_km=25,
        blurb="Cotton and wheat irrigated with Amu Darya water that no longer reaches the Aral Sea.",
    ),
    "aletsch": dict(
        name="Aletsch Glacier region, Swiss Alps", lat=46.45, lon=8.05, radius_km=20,
        blurb="Europe's largest glacier and its surrounding peaks.",
    ),
    "las_vegas": dict(
        name="Las Vegas, USA", lat=36.10, lon=-115.20, radius_km=25,
        blurb="One of the fastest-growing metropolitan areas in the USA.",
    ),
}

# Multi-region case files: the same variable moving in opposite directions.
STORIES = [
    dict(
        key="landcover_temperature",
        short="Loess Plateau vs Amazon",
        context="Tree planting in one region, forest clearing in the other",
        title="Trees cool the ground, clearing heats it",
        places="China vs Brazil",
        variable="lst_day", regions=["loess_plateau", "amazon_front"], start_year=2001,
        question="Can the same physical process make surface temperature rise in one place and fall in another?",
        finding="Where vegetation was added (Loess Plateau) daytime land surface temperature fell by about 3 °C "
                "since 2001; where forest was cleared (Amazon) it rose by about 1.5 °C. Both trends are "
                "significant (p < 0.001). The shared process is evapotranspiration: plants move water into the "
                "air, which uses energy that would otherwise heat the surface.",
    ),
    dict(
        key="landcover_et",
        short="Loess Plateau vs Amazon",
        context="Tree planting in one region, forest clearing in the other",
        title="More plants, more water in the air",
        places="China vs Brazil",
        variable="evapotranspiration", regions=["loess_plateau", "amazon_front"], start_year=2001,
        question="What happens to the water plants return to the air when vegetation is added or removed?",
        finding="Evapotranspiration rose about 40 % on the greening Loess Plateau and fell about 6 % on the "
                "Amazon deforestation front (both significant).",
    ),
    dict(
        key="water_storage",
        short="India · Caspian · East Africa",
        context="Three large basins with different water use and rainfall",
        title="Some regions gain water, others lose it",
        places="India · Caspian Sea · East Africa",
        variable="water_storage", regions=["nw_india", "caspian_north", "lake_victoria"], start_year=2002,
        question="Where is the total amount of water stored on land rising or falling?",
        finding="GRACE shows water storage falling by ~4 cm/yr in NW India (groundwater pumping) and ~4 cm/yr "
                "around the northern Caspian, while the Lake Victoria basin gained ~3 cm/yr after very wet "
                "years. All three trends are significant (p < 0.001).",
    ),
]

# Single-place examples: (place, what to look at, first year, one factual line of context).
# Shown in the Examples section, in the globe's example list and as orange pins.
EXAMPLES = [
    ("kakhovka_bed", "ndvi_modis", 2014, "Reservoir drained in June 2023"),
    ("loess_plateau", "ndvi_modis", 2001, "Large-scale tree planting since 1999"),
    ("nw_india", "water_storage", 2002, "Irrigated farmland using groundwater"),
    ("aral_basin", "water_storage", 2002, "Rivers diverted for irrigation since the 1960s"),
    ("amu_darya_fields", "ndvi_modis", 2001, "Irrigated oasis on the Amu Darya river"),
    ("aletsch", "snow_cover", 2001, "Europe's largest glacier and surrounding peaks"),
    ("las_vegas", "night_lights", 2014, "Fast-growing desert city"),
    ("cherkasy_farmland", "air_temp", 2001, "Rain-fed farmland in central Ukraine"),
]

# Short place labels for compact example tiles.
SHORT_NAMES = {
    "kakhovka_bed": "Kakhovka Reservoir, Ukraine", "loess_plateau": "Loess Plateau, China",
    "nw_india": "Punjab & Haryana, India", "aral_basin": "Aral Sea basin", "amu_darya_fields": "Khorezm oasis, Uzbekistan",
    "aletsch": "Aletsch Glacier, Switzerland", "las_vegas": "Las Vegas, USA", "cherkasy_farmland": "Cherkasy, Ukraine",
}

# The examples strip: all single places, then the comparisons.
LANDING_EXAMPLES = (
    [dict(kind="single", preset=pk, variable=vk, start=start, context=text, label=SHORT_NAMES[pk])
     for pk, vk, start, text in EXAMPLES]
    + [dict(kind="compare", story=s["key"], variable=s["variable"], context=s["context"], label=s["short"])
       for s in STORIES]
)


def region_dict(key: str) -> dict:
    p = PRESETS[key]
    return dict(name=p["name"], lat=p["lat"], lon=p["lon"], radius_km=p["radius_km"], polygon=None, preset=key)
