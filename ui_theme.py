"""
Trend Detective — visual design system (CSS, Plotly theme, small HTML builders).

Look: deep-space background with an aurora glow, glass panels, a violet→blue
accent gradient, amber for "evidence". Type: Sora (display), Inter (text),
JetBrains Mono (numbers).
"""

import html
import math

BG = "#05060A"
SURFACE = "#0C0F18"
TEXT = "#EDEFF7"
MUTED = "#8A93A8"
DIM = "#4A5168"
ACCENT = "#7C9CFF"
ACCENT_2 = "#B38CFF"
AMBER = "#FFB547"
GRID = "rgba(255,255,255,0.06)"
NS_COLOR = "#8A93A8"
REGION_COLORS = ["#7C9CFF", "#FFB547", "#3DDC97", "#FF6B81", "#B38CFF", "#4FD1E8"]

LOGO_SVG = """
<svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="tdg" x1="0" y1="0" x2="40" y2="40">
    <stop offset="0" stop-color="#7C9CFF"/><stop offset="1" stop-color="#B38CFF"/></linearGradient></defs>
  <circle cx="17" cy="17" r="12" stroke="url(#tdg)" stroke-width="2.6"/>
  <ellipse cx="17" cy="17" rx="5.2" ry="12" stroke="url(#tdg)" stroke-width="1.4" opacity="0.8"/>
  <path d="M5.5 13.5h23M5.5 20.5h23" stroke="url(#tdg)" stroke-width="1.4" opacity="0.8"/>
  <path d="M8 24 L13 19 L17 21 L23 13 L27 15" stroke="#FFB547" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M26 26 L36 36" stroke="url(#tdg)" stroke-width="4" stroke-linecap="round"/>
</svg>"""

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{ --td-accent: {ACCENT}; --td-accent2: {ACCENT_2}; --td-amber: {AMBER}; }}
.stApp {{
  background:
    radial-gradient(1100px 520px at 8% -8%, rgba(124,156,255,0.13), transparent 60%),
    radial-gradient(900px 480px at 100% -5%, rgba(179,140,255,0.10), transparent 60%),
    radial-gradient(700px 400px at 50% 110%, rgba(61,220,151,0.05), transparent 60%),
    {BG} !important;
}}
header[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], footer, #MainMenu {{ display: none !important; }}
[data-testid="stMainBlockContainer"], .main .block-container {{ padding: 0.9rem 2rem 3rem 2rem !important; max-width: 1440px; }}
html, body, .stApp, .stMarkdown, p, li, label, input, textarea, button {{ font-family: 'Inter', system-ui, sans-serif !important; }}
h1, h2, h3, h4 {{ font-family: 'Sora', 'Inter', sans-serif !important; color: {TEXT} !important; letter-spacing: -0.01em; }}
p, li {{ color: #C3C9D8; }}
[data-testid="stMarkdownContainer"] strong {{ color: {TEXT}; }}

/* ── top bar ── */
.td-top {{ display: flex; align-items: center; justify-content: space-between; gap: 1.2rem; flex-wrap: wrap; margin-bottom: 0.4rem; }}
.td-brand {{ display: flex; align-items: center; gap: 0.8rem; }}
.td-name {{ font-family: 'Sora', sans-serif; font-weight: 800; font-size: 1.4rem; color: {TEXT}; letter-spacing: -0.02em; line-height: 1; }}
.td-name span {{ background: linear-gradient(90deg, {ACCENT}, {ACCENT_2}); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.td-sub {{ font-size: 0.78rem; color: {MUTED}; margin-top: 0.25rem; }}
.td-chips {{ display: flex; gap: 0.4rem; flex-wrap: wrap; }}
.td-chip {{ font-size: 0.74rem; padding: 0.3rem 0.65rem; border-radius: 99px; border: 1px solid rgba(255,255,255,0.1); color: #C3C9D8; }}
.td-chip.ok {{ border-color: rgba(61,220,151,0.45); color: #3DDC97; background: rgba(61,220,151,0.06); }}
.td-chip.warn {{ border-color: rgba(255,181,71,0.45); color: {AMBER}; background: rgba(255,181,71,0.06); }}
.td-banner {{ border: 1px solid rgba(255,181,71,0.35); background: rgba(255,181,71,0.06); color: #E9CFA0; border-radius: 12px;
  padding: 0.55rem 0.9rem; font-size: 0.82rem; margin-bottom: 0.6rem; }}

/* ── glass containers (st.container(key=...)) ── */
.st-key-inv_bar, [class*="st-key-glass"] {{
  background: rgba(12,15,24,0.72); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px;
  padding: 0.85rem 1.1rem 0.7rem 1.1rem; backdrop-filter: blur(12px); margin-top: 0.7rem; border-radius: 16px; }}
.td-label {{ font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; color: {MUTED}; font-weight: 700; margin-bottom: 0.35rem; }}
[data-testid="stWidgetLabel"] p {{ font-size: 0.8rem !important; letter-spacing: 0.02em; color: {MUTED} !important; font-weight: 600 !important; }}

/* pills & segmented controls: separate rounded buttons with the same spacing
   (Streamlit joins segmented buttons edge to edge: column-gap 0 and margin-right -1px) */
[data-testid="stButtonGroup"] > div {{ column-gap: 6px !important; row-gap: 6px !important; }}
button[kind="segmented_control"], button[kind="segmented_controlActive"] {{ margin-right: 0 !important; }}
[data-testid="stPopover"] button p {{ white-space: nowrap; }}
button[kind="pills"], button[kind="segmented_control"] {{
  background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.09) !important; color: #C3C9D8 !important;
  border-radius: 99px !important; transition: all .15s ease; }}
button[kind="pills"]:hover, button[kind="segmented_control"]:hover {{ border-color: rgba(124,156,255,0.6) !important; color: #fff !important; }}
button[kind="pillsActive"], button[kind="segmented_controlActive"] {{
  background: linear-gradient(135deg, rgba(124,156,255,0.95), rgba(179,140,255,0.95)) !important; border: 1px solid transparent !important;
  color: #05060A !important; font-weight: 600 !important; border-radius: 99px !important; }}
button[kind="pillsActive"] p, button[kind="segmented_controlActive"] p {{ color: #05060A !important; font-weight: 600 !important; }}
/* measurements (pills) are the second-level choice: lighter selected style than topics / views */
button[kind="pillsActive"] {{ background: rgba(124,156,255,0.16) !important; border: 1px solid {ACCENT} !important; }}
button[kind="pillsActive"] p {{ color: {TEXT} !important; }}
.st-key-view_sel button {{ padding: 0.4rem 1rem !important; font-size: 0.86rem !important; }}

/* buttons */
.stButton > button, .stDownloadButton > button {{ border-radius: 12px !important; font-weight: 600 !important;
  border: 1px solid rgba(255,255,255,0.12) !important; background: rgba(255,255,255,0.04) !important; color: {TEXT} !important; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: rgba(124,156,255,0.7) !important; }}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {{ background: linear-gradient(135deg, {ACCENT}, {ACCENT_2}) !important; color: #05060A !important; border: none !important;
  box-shadow: 0 10px 30px -12px rgba(124,156,255,0.8); }}
.stButton > button[kind="primary"] p, [data-testid="stBaseButton-primary"] p {{ color: #05060A !important; }}
[data-testid="stExpander"] details {{ border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 14px !important; background: rgba(12,15,24,0.5); }}

/* ── investigation headline ── */
.td-headline {{ margin: 0.9rem 0 0.1rem 0; }}
.td-headline .k {{ font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; color: {AMBER}; font-weight: 700; }}
.td-headline .t {{ font-family: 'Sora', sans-serif; font-size: 1.4rem; font-weight: 700; color: {TEXT}; line-height: 1.25; margin-top: 0.1rem; }}
.td-headline .t span {{ color: {MUTED}; font-weight: 500; }}
.td-headline .s {{ font-size: 0.8rem; color: {MUTED}; margin-top: 0.25rem; }}

/* ── verdict hero ── */

/* ── KPI tiles ── */
.td-kpi {{ background: rgba(12,15,24,0.72); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 0.7rem 0.9rem; height: 100%; }}
.td-kpi .k {{ font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase; color: {MUTED}; font-weight: 700; }}
.td-kpi .v {{ font: 600 clamp(1rem, 1.5vw, 1.3rem) 'JetBrains Mono', monospace; color: {TEXT}; margin-top: 0.35rem; white-space: nowrap; }}
.td-kpi .s {{ font-size: 0.78rem; color: {MUTED}; margin-top: 0.3rem; line-height: 1.4; }}

/* ── cards ── */
.td-note {{ background: rgba(124,156,255,0.06); border: 1px solid rgba(124,156,255,0.25); border-left: 3px solid {ACCENT};
  border-radius: 12px; padding: 0.6rem 0.85rem; font-size: 0.84rem; color: #D5DAE8; line-height: 1.5; margin: 0.3rem 0 0.6rem 0; }}
.td-scan-card {{ background: rgba(12,15,24,0.72); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 0.85rem 1rem 0.4rem 1rem; }}
.td-scan-card .h {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }}
.td-scan-card .n {{ font-weight: 600; color: {TEXT}; font-size: 0.92rem; line-height: 1.3; }}
.td-scan-card .m {{ font-size: 0.74rem; color: {MUTED}; margin-top: 0.15rem; }}
.td-badge {{ font-size: 0.72rem; font-weight: 700; padding: 0.22rem 0.55rem; border-radius: 99px; white-space: nowrap; }}
.td-scan-card .r {{ font: 500 0.82rem 'JetBrains Mono', monospace; color: #C3C9D8; margin-top: 0.45rem; }}
.td-empty {{ text-align: center; padding: 1.4rem; border: 1px dashed rgba(255,255,255,0.12); border-radius: 16px; color: {MUTED}; }}
.td-foot {{ font-size: 0.76rem; color: {DIM}; margin-top: 1.8rem; text-align: center; }}

/* ── friendly landing ── */
.td-stephead {{ display: flex; align-items: center; gap: 0.55rem; margin: 0.8rem 0 0.45rem 0; flex-wrap: wrap; }}
.td-stephead .n {{ width: 23px; height: 23px; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center;
  font: 700 0.78rem 'Sora', sans-serif; color: #05060A; background: linear-gradient(135deg, {ACCENT}, {ACCENT_2}); }}
.td-stephead .t {{ font: 700 0.98rem 'Sora', sans-serif; color: {TEXT}; }}
.td-stephead .h {{ font-size: 0.8rem; color: {MUTED}; }}
.st-key-inv_bar .td-stephead {{ margin-top: 0; }}
.td-question {{ font: 600 0.96rem 'Sora', sans-serif; color: {TEXT}; margin-top: 0.15rem; line-height: 1.45; }}
.td-question span {{ color: {MUTED}; font: 400 0.82rem 'Inter', sans-serif; }}

/* ── the answer ── */
.td-answer {{ border-radius: 18px; padding: 1rem 1.25rem; margin: 0.6rem 0 0.7rem 0; border: 1px solid; display: grid;
  grid-template-columns: 1.7fr 1fr; gap: 1.2rem; align-items: center; }}
.td-answer .q {{ font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: {MUTED}; font-weight: 700; }}
.td-answer .a {{ font: 800 clamp(1.3rem, 2.2vw, 1.8rem) 'Sora', sans-serif; line-height: 1.15; margin-top: 0.25rem; letter-spacing: -0.02em; }}
.td-answer .s {{ font-size: 0.92rem; color: #D5DAE8; margin-top: 0.4rem; line-height: 1.45; }}
.td-sure .k {{ font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; color: {MUTED}; font-weight: 700; }}
.td-dots {{ display: flex; gap: 5px; margin: 0.45rem 0 0.35rem 0; }}
.td-dots span {{ flex: 1; height: 8px; border-radius: 5px; background: rgba(255,255,255,0.08); }}
.td-sure .l {{ font: 600 0.93rem 'Sora', sans-serif; color: {TEXT}; }}
.td-sure .c {{ font-size: 0.76rem; color: {MUTED}; margin-top: 0.25rem; line-height: 1.4; }}
.td-facts {{ display: grid; grid-template-columns: repeat(var(--n, 3), minmax(0, 1fr)); gap: 0.7rem; margin: 0 0 0.5rem 0; }}
.td-fact {{ background: rgba(12,15,24,0.72); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 0.7rem 0.95rem; }}
.td-fact .k {{ font-size: 0.72rem; color: {MUTED}; font-weight: 600; }}
.td-fact .v {{ font: 700 clamp(1.15rem, 1.8vw, 1.45rem) 'Sora', sans-serif; color: {TEXT}; margin-top: 0.2rem; line-height: 1.15; }}
.td-fact .m {{ font-size: 0.84rem; color: #D5DAE8; margin-top: 0.15rem; line-height: 1.35; }}
.td-fact .x {{ font-size: 0.74rem; color: {MUTED}; margin-top: 0.3rem; line-height: 1.35; }}
.td-gloss dt {{ font-weight: 700; color: {TEXT}; margin-top: 0.7rem; }}
.td-gloss dd {{ margin: 0.15rem 0 0 0; color: #C3C9D8; font-size: 0.9rem; line-height: 1.5; }}

@media (max-width: 1000px) {{
  .td-answer {{ grid-template-columns: 1fr; }}
  [data-testid="stMainBlockContainer"], .main .block-container {{ padding: 0.8rem 0.8rem 3rem 0.8rem !important; }}
  .td-headline .t {{ font-size: 1.35rem; }}
}}
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"], .main .block-container {{ padding: 0.6rem 0.75rem 2.5rem 0.75rem !important; }}
  /* rows that stay on one line (header: brand + Help; compared place + remove button) */
  .st-key-topbar [data-testid="stHorizontalBlock"], [class*="st-key-row_"] [data-testid="stHorizontalBlock"] {{
    flex-wrap: nowrap !important; gap: 0.5rem; }}
  .st-key-topbar [data-testid="stHorizontalBlock"] {{ align-items: flex-start !important; }}
  .st-key-topbar [data-testid="stColumn"], [class*="st-key-row_"] [data-testid="stColumn"] {{
    min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }}
  .st-key-topbar [data-testid="stColumn"]:last-child, [class*="st-key-row_"] [data-testid="stColumn"]:last-child {{
    flex: 0 0 auto !important; }}
  .td-top {{ gap: 0.5rem; }}
  .td-brand {{ gap: 0.55rem; }}
  .td-brand svg {{ width: 30px; height: 30px; flex: none; }}
  .td-name {{ font-size: 1.2rem; }}
  .td-sub {{ font-size: 0.74rem; }}
  .td-banner {{ font-size: 0.78rem; }}
  .st-key-inv_bar, [class*="st-key-glass"] {{ padding: 0.75rem 0.8rem 0.6rem 0.8rem; }}
  .td-headline .t {{ font-size: 1.15rem; }}
  .td-answer {{ padding: 0.85rem 0.95rem; gap: 0.8rem; }}
  .td-answer .a {{ font-size: 1.35rem; }}
  .td-facts {{ grid-template-columns: 1fr; }}
  [data-testid="stMarkdownContainer"] h1 {{ font-size: 1.45rem !important; }}
  [data-testid="stMarkdownContainer"] h2 {{ font-size: 1.25rem !important; }}
  [data-testid="stMarkdownContainer"] h3 {{ font-size: 1.08rem !important; }}
  .st-key-view_sel button {{ padding: 0.35rem 0.75rem !important; font-size: 0.82rem !important; }}
}}
</style>
"""

PLOTLY = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(255,255,255,0.015)",
    font=dict(family="Inter, sans-serif", color="#AEB5C8", size=12),
    xaxis=dict(gridcolor=GRID, linecolor=GRID, zeroline=False),
    yaxis=dict(gridcolor=GRID, linecolor=GRID, zeroline=False),
    margin=dict(t=40, b=30, l=8, r=8),
    hoverlabel=dict(bgcolor="#0C0F18", bordercolor="rgba(255,255,255,0.15)", font_color=TEXT, font_family="Inter"),
)


def esc(s) -> str:
    return html.escape(str(s))


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(h: str, a: float) -> str:
    r, g, b = hex_to_rgb(h)
    return f"rgba({r},{g},{b},{a})"


def top_bar(live: bool, llm: bool) -> str:
    gee = '<span class="td-chip ok">● Live NASA data</span>' if live else \
        '<span class="td-chip warn">● Demo mode · saved data</span>'
    ai = '<span class="td-chip ok">● AI explanations</span>' if llm else ''
    return f"""<div class="td-top">
      <div class="td-brand">{LOGO_SVG}<div><div class="td-name">Trend <span>Detective</span></div>
        <div class="td-sub">Is our planet changing where you care about? Find out with 25 years of NASA satellite data.</div></div></div>
      <div class="td-chips">{gee}{ai}</div></div>"""


def kpi(k: str, v: str, s: str = "", color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return f'<div class="td-kpi"><div class="k">{k}</div><div class="v"{style}>{v}</div><div class="s">{s}</div></div>'


def badge(text: str, color: str) -> str:
    return f'<span class="td-badge" style="color:{color};background:{rgba(color, 0.12)};border:1px solid {rgba(color, 0.4)}">{esc(text)}</span>'

def confidence_dots(level: int, color: str) -> str:
    """Five bars: how sure we are that the change is real (0-4 filled, plus one for 'any data')."""
    spans = "".join(f'<span style="background:{color if i <= level else "rgba(255,255,255,0.08)"}"></span>' for i in range(5))
    return f'<div class="td-dots">{spans}</div>'


def fact(label: str, value: str, meaning: str, extra: str = "", color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return (f'<div class="td-fact"><div class="k">{label}</div><div class="v"{style}>{value}</div>'
            f'<div class="m">{meaning}</div><div class="x">{extra}</div></div>')


def facts_row(cards: list[str]) -> str:
    """Cards in one grid row — every card gets the height of the tallest one."""
    return f'<div class="td-facts" style="--n:{len(cards)}">{"".join(cards)}</div>'


def step_header(n: int, title: str, hint: str = "") -> str:
    h = f'<span class="h">— {hint}</span>' if hint else ""
    return f'<div class="td-stephead"><span class="n">{n}</span><span class="t">{title}</span>{h}</div>'
