"""
Trend Detective — plain-language answers for people who are not scientists.

Turns a TrendResult into everyday sentences: is it changing (yes / maybe / no),
how sure are we, how much, and how consistently. The technical numbers stay
available in the "for experts" parts of the app; this module never hides them,
it only translates them.
"""

from __future__ import annotations

import math

import nasa_variables as nv
from trends import TrendResult


def fmt(x: float | None, signed: bool = False) -> str:
    """Readable number: 1,234 · 12.3 · 1.23 · 0.0065 (never scientific notation)."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    a = abs(x)
    if a >= 100:
        s = f"{x:,.0f}"
    elif a >= 10:
        s = f"{x:.1f}"
    elif a >= 1:
        s = f"{x:.2f}"
    elif a == 0:
        s = "0"
    else:   # three significant digits: 0.0065, 0.163, 0.00021
        decimals = 2 - math.floor(math.log10(a))
        s = f"{x:.{decimals}f}".rstrip("0").rstrip(".")
    if signed and x > 0:
        s = "+" + s
    return s


def fmt_p(p: float) -> str:
    if p is None or not math.isfinite(p):
        return "n/a"
    return "< 0.001" if p < 0.001 else f"{p:.3f}"

LEVELS = {
    4: "Almost certainly a real change",
    3: "Very likely a real change",
    2: "Probably a real change",
    1: "Maybe — not enough evidence yet",
    0: "No clear change — could easily be chance",
}


def confidence(p: float, alpha: float) -> tuple[int, str]:
    """0 (no evidence) … 4 (overwhelming evidence), respecting the chosen strictness α."""
    if p is None or not math.isfinite(p):
        return 0, "Not enough data to tell"
    if p < min(0.001, alpha):
        level = 4
    elif p < min(0.01, alpha):
        level = 3
    elif p < alpha:
        level = 2
    elif p < 0.10:
        level = 1
    else:
        level = 0
    return level, LEVELS[level]


def chance_text(p: float) -> str:
    """What the p-value means, in words."""
    if p is None or not math.isfinite(p):
        return ""
    if p < 0.001:
        odds = "less than 1 time in 1,000"
    else:
        n = max(1, round(1 / p))
        odds = f"about 1 time in {n:,}" if n > 1 else "almost every time"
    return f"If nothing were really changing, a pattern this steady would show up by chance {odds}."


def answer(r: TrendResult, var: nv.Variable) -> tuple[str, str]:
    """(headline, one-line explanation) — e.g. ("Yes — the land is getting greener", "Almost certainly a real change")."""
    if r.direction == "insufficient data":
        return "Not enough data to tell", f"We need at least 4 years of measurements; this place has {r.n_years}."
    level, label = confidence(r.p_value, r.alpha)
    phrase = var.up_phrase if r.tendency == "rising" else var.down_phrase
    if r.significant:
        return f"Yes — {phrase}", label
    if level == 1:
        return f"Maybe — {phrase}", "A hint of change, but it could still be chance"
    return "No clear change", "The ups and downs look like normal year-to-year variation"


def how_much(r: TrendResult, var: nv.Variable) -> tuple[str, str]:
    """(big number, what it means) — e.g. ("42%", "greener since 2001"), ("22.7 cm water", "losing water since 2002")."""
    if r.direction == "insufficient data" or not math.isfinite(r.total_change):
        return "–", "not enough data"
    word = var.up_word if r.total_change > 0 else var.down_word
    if r.pct_change is not None and math.isfinite(r.pct_change):
        return f"{abs(r.pct_change):.0f}%", f"{word} since {r.first_year}"
    unit = "percentage points" if var.units.startswith("%") else var.units
    return f"{fmt(abs(r.total_change))} {unit}", f"{word} since {r.first_year}"


def per_decade(r: TrendResult, var: nv.Variable) -> str:
    if not math.isfinite(r.slope):
        return ""
    return f"{fmt(r.slope * 10, True)} {var.units} every 10 years"


def consistency(r: TrendResult, var: nv.Variable) -> tuple[str, str]:
    """(share, sentence) from Kendall's tau: how often a later year beat an earlier one."""
    if not math.isfinite(r.tau):
        return "–", ""
    up = (1 + r.tau) / 2
    if r.tau >= 0:
        return f"{up:.0%}", (f"In {up:.0%} of all year-to-year comparisons the later year was {var.up_word} "
                             f"(a coin toss would give about 50%).")
    return f"{1 - up:.0%}", (f"In {1 - up:.0%} of all year-to-year comparisons the later year was {var.down_word} "
                             f"(a coin toss would give about 50%).")


def noise_text(r: TrendResult) -> str:
    c = r.change_vs_variability
    if c is None or not math.isfinite(c):
        return ""
    if c >= 1.5:
        return f"The change is {fmt(c)}× bigger than the normal ups and downs from one year to the next."
    if c >= 0.75:
        return "The change is about as big as the normal ups and downs from one year to the next."
    return "The change is smaller than the normal ups and downs from one year to the next."


def verdict_short(r: TrendResult, var: nv.Variable) -> str:
    """Tiny badge text for cards: '▲ greener', '▼ drier', '● no clear change'."""
    if r.direction == "insufficient data":
        return "not enough data"
    if not r.significant:
        return "● no clear change"
    return ("▲ " + var.up_word) if r.tendency == "rising" else ("▼ " + var.down_word)


GLOSSARY = [
    ("Trend", "The overall direction of a measurement over many years — rising, falling or flat — ignoring the "
              "ups and downs from season to season and year to year."),
    ("Significant", "Scientists call a trend significant when it is very unlikely to be just chance. "
                    "It tells you the change is real, not what caused it."),
    ("p-value", "The chance of seeing a pattern this steady if nothing were really changing. Smaller = stronger "
                "evidence. Below 0.05 (1 in 20) is the usual threshold for 'significant'."),
    ("Strictness (α)", "The p-value threshold you accept. 0.05 is standard; 0.01 is stricter (fewer false alarms, "
                       "but real changes are missed more often)."),
    ("NDVI / greenness", "A number from about −0.1 (water, bare rock) to 0.9 (dense forest) computed from how "
                         "strongly plants reflect near-infrared light compared with red light."),
    ("Anomaly", "How much a month differs from what is normal for that month — e.g. a July that is 1 °C "
                "warmer than the average July."),
    ("Sen's slope", "The typical change per year: the middle value of all the year-to-year changes. "
                    "Unlike a straight-line fit, one odd year can't pull it around."),
    ("Mann-Kendall test", "The significance test we use. It compares every year with every later year "
                          "(January with January, July with July…) and counts how often the later one is higher."),
    ("Pixel", "One square of a satellite image. Its size (30 m to 55 km here) sets how much detail you can see."),
    ("NASA missions", "Terra MODIS, Landsat + Sentinel-2 (HLS), GPM, SMAP, GRACE and Suomi NPP VIIRS are "
                      "satellites; FLDAS is a NASA computer model fed with satellite and weather data."),
]
