"""
Trend Detective — plain-language trend summaries.

Turns the numbers from trends.analyze_trend() into a short explanation anyone can
read: what is changing, where, how much, and whether it is a real change.

Uses Groq (llama-3.3-70b-versatile by default, override with GROQ_MODEL) when
GROQ_API_KEY is set. Without a key — or if the API call fails — a deterministic
template states the same facts, so the offline demo still works. The LLM only
receives the computed facts and is told not to invent numbers.
"""

from __future__ import annotations

import math
import os

import nasa_variables as nv
import plain
from plain import fmt, fmt_p  # noqa: F401  (re-exported for app.py)
from trends import TrendResult

DEFAULT_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = (
    "You explain NASA Earth data to the general public — think of a curious 14-year-old. "
    "Use short sentences and everyday words; when a technical word is unavoidable, explain it in brackets. "
    "You use ONLY the numbers and facts provided; you never invent data, places or dates. "
    "You never claim a cause as proven; possible causes are phrased as ideas to investigate. "
    "If the change is not statistically significant you say clearly that there is no clear change. "
    "Write in English."
)


def llm_available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def rate_text(r: TrendResult, var: nv.Variable) -> str:
    return f"{fmt(r.slope, signed=True)} {var.units} per year"


def change_text(r: TrendResult, var: nv.Variable) -> str:
    unit = "percentage points" if var.units.startswith("%") else var.units
    s = f"{fmt(r.total_change, signed=True)} {unit}"
    if r.pct_change is not None and math.isfinite(r.pct_change):
        s += f" ({fmt(r.pct_change, signed=True)}%)"
    return s


def headline(r: TrendResult, var: nv.Variable, place: str) -> str:
    """One plain sentence, e.g. 'Since 2001 the land in Loess Plateau has become 42% greener — almost certainly a real change.'"""
    if r.direction == "insufficient data":
        return f"There are not enough measurements for {place} to tell whether anything is changing."
    title, label = plain.answer(r, var)
    big, _ = plain.how_much(r, var)
    if r.significant:
        phrase = var.up_phrase if r.tendency == "rising" else var.down_phrase
        updown = "up" if r.total_change > 0 else "down"
        return (f"{phrase[0].upper() + phrase[1:]} in {place}: {updown} {big} between {r.first_year} and "
                f"{r.last_year}. {label}.")
    return f"No clear change in {place} between {r.first_year} and {r.last_year} — {label[0].lower() + label[1:]}."


# ─────────────────────────────────────────────
# Facts handed to the LLM (and used by the template)
# ─────────────────────────────────────────────

def facts_block(r: TrendResult, var: nv.Variable, place: str, context: str = "") -> str:
    title, label = plain.answer(r, var)
    big, meaning = plain.how_much(r, var)
    lines = [
        f"Question: {var.question}",
        f"What is measured: {var.plain} — {var.explain}",
        f"Data: {var.mission} ({var.agency}), about {nv.fmt_distance(var.pixel_m)} per pixel",
        f"Place: {place}" + (f" — background: {context}" if context else ""),
        f"Years: {r.first_year}–{r.last_year} ({r.n_years} years of monthly data)",
        f"Plain answer: {title}. {label}.",
        f"How much: {big} {meaning} (total {change_text(r, var)}; {plain.per_decade(r, var)})",
        f"Change compared with normal year-to-year ups and downs: {plain.noise_text(r)}",
        f"Consistency: {plain.consistency(r, var)[1]}",
        f"Evidence: p-value {fmt_p(r.p_value)} at strictness α = {r.alpha}. {plain.chance_text(r.p_value)}",
        f"Technical: seasonal Mann-Kendall test with Hirsch-Slack correction; Sen's slope {rate_text(r, var)} "
        f"({int(round(r.ci_level * 100))}% range {fmt(r.slope_ci_low, True)} to {fmt(r.slope_ci_high, True)})",
    ]
    if var.notes:
        lines.append(f"Data note: {var.notes}")
    lines += [f"Caveat: {w}" for w in r.warnings]
    return "\n".join(f"- {x}" for x in lines)


# ─────────────────────────────────────────────
# Template (no LLM)
# ─────────────────────────────────────────────

def template_summary(r: TrendResult, var: nv.Variable, place: str, context: str = "") -> str:
    if r.direction == "insufficient data":
        return f"**{headline(r, var, place)}**\n\n" + "\n".join(f"- {w}" for w in r.warnings)
    title, label = plain.answer(r, var)
    big, meaning = plain.how_much(r, var)
    where = place + (f" — {context}" if context else "")
    found = f"Between {r.first_year} and {r.last_year} the value changed by **{big}** ({meaning}), " \
            f"or {plain.per_decade(r, var)}. {plain.noise_text(r)}"
    if r.significant:
        sure = f"**{label}.** {plain.chance_text(r.p_value)} {plain.consistency(r, var)[1]}"
    else:
        sure = (f"**{label}.** {plain.chance_text(r.p_value)} That is too often to rule out chance, so we can't call "
                f"this a real trend yet. It doesn't prove nothing changed — only that these years can't show it clearly.")
    out = [f"### {title}", "",
           f"**What we looked at:** {var.question} {var.explain}", "",
           f"**Where:** {where}. Each satellite pixel covers about {nv.fmt_distance(var.pixel_m)}.", "",
           f"**What we found:** {found}", "",
           f"**How sure are we?** {sure}", "",
           "**Keep in mind:** a real change tells you *that* something changed, not *why*. "
           "Look at the chart for sudden jumps (like a dam breaking) — they are events, not slow trends."]
    if r.warnings:
        out += [""] + [f"- {w}" for w in r.warnings]
    return "\n".join(out)


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────

def _chat(prompt: str, max_tokens: int = 700) -> str:
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def generate_trend_summary(r: TrendResult, var: nv.Variable, place: str,
                           context: str = "", use_llm: bool = True) -> tuple[str, str]:
    """Returns (markdown, engine label)."""
    fallback = template_summary(r, var, place, context)
    if not (use_llm and llm_available()) or r.direction == "insufficient data":
        return fallback, "template"
    prompt = f"""Write a short explanation (Markdown, at most 200 words) from these computed facts:

{facts_block(r, var, place, context)}

Use exactly this structure:
### <the plain answer, e.g. "Yes — the land is getting greener">
**What we looked at:** <the question and what the satellite measures, in everyday words>
**Where:** <the place>
**What we found:** <how much it changed, compared with normal year-to-year ups and downs>
**How sure are we?** <the evidence in plain words; say what "significant" does and doesn't mean>
**Possible causes to look into:** <one or two ideas, clearly labelled as ideas; omit if nothing sensible>

Output only the explanation."""
    try:
        return _chat(prompt), f"Groq · {os.environ.get('GROQ_MODEL', DEFAULT_MODEL)}"
    except Exception as e:
        return fallback + f"\n\n*AI summary unavailable ({str(e)[:80]}); showing the template.*", "template"


def template_comparison(rows: list[tuple[str, TrendResult]], var: nv.Variable) -> str:
    up = [p for p, r in rows if r.significant and r.tendency == "rising"]
    down = [p for p, r in rows if r.significant and r.tendency == "falling"]
    lines = []
    if up and down:
        lines.append(f"### Opposite directions!\n\n**{', '.join(up)}:** {var.up_phrase}. "
                     f"**{', '.join(down)}:** {var.down_phrase}.")
    elif up or down:
        lines.append(f"### Same direction in {len(up) + len(down)} of {len(rows)} places")
    else:
        lines.append(f"### No clear change in any of the places")
    lines.append("")
    for place, r in rows:
        title, label = plain.answer(r, var)
        big, meaning = plain.how_much(r, var)
        lines.append(f"- **{place}:** {title.lower()} — {big} {meaning} ({label.lower()}).")
    lines += ["", "The same measurement can go up in one place and down in another. Finding out *why* the places "
              "differ is how scientists discover the process behind a change."]
    return "\n".join(lines)


def generate_comparison_summary(rows: list[tuple[str, TrendResult]], var: nv.Variable,
                                story: str = "", use_llm: bool = True) -> tuple[str, str]:
    fallback = template_comparison(rows, var)
    if not (use_llm and llm_available()):
        return fallback, "template"
    blocks = "\n\n".join(f"### {place}\n{facts_block(r, var, place)}" for place, r in rows)
    prompt = f"""Compare these places (Markdown, at most 220 words). {('Background: ' + story) if story else ''}

{blocks}

Structure:
### <headline: same direction or opposite directions?>
One short bullet per place with the plain answer and how much it changed.
**Why might they differ?** One or two ideas, clearly labelled as ideas.
Output only the explanation."""
    try:
        return _chat(prompt, 800), f"Groq · {os.environ.get('GROQ_MODEL', DEFAULT_MODEL)}"
    except Exception as e:
        return fallback + f"\n\n*AI summary unavailable ({str(e)[:80]}); showing the template.*", "template"


def template_scan(rows: list[dict], place: str) -> str:
    sig = [r for r in rows if r["significant_fdr"]]
    lines = [f"### {len(sig)} of {len(rows)} things are clearly changing in {place}"]
    if sig:
        lines += [""] + [f"- {r['icon']} **{r['variable']}:** {r['answer']} ({r['big']} {r['meaning']})" for r in sig]
    else:
        lines += ["", "None of the measurements shows a clear change here."]
    lines += ["", "*Because we test many things at once, we use a stricter check so that lucky coincidences "
              "don't show up as changes.*"]
    return "\n".join(lines)
