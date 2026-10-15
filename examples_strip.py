"""
Trend Detective — compact, scrollable strip of example tiles (Streamlit v2 custom component).

Every tile has the same size: icon, place (one line) and "what · context" (one line).
Clicking a tile sends {"i": index} to Python as the trigger value "open".
"""

import streamlit as st

CSS = """
.tde-wrap { position: relative; display: flex; align-items: center; gap: 6px; font-family: 'Inter', system-ui, sans-serif; }
.tde-strip { display: flex; gap: 8px; overflow-x: auto; scroll-behavior: smooth; padding: 4px 2px 8px 2px; flex: 1;
  scrollbar-width: thin; scrollbar-color: rgba(124,156,255,0.35) transparent; }
.tde-strip::-webkit-scrollbar { height: 6px; }
.tde-strip::-webkit-scrollbar-thumb { background: rgba(124,156,255,0.35); border-radius: 3px; }
.tde-tile { all: unset; box-sizing: border-box; flex: 0 0 272px; width: 272px; min-width: 272px; max-width: 272px;
  overflow: hidden; height: 54px; display: flex; align-items: center; gap: 11px;
  padding: 0 14px; border-radius: 14px; cursor: pointer; background: rgba(12,15,24,0.72);
  border: 1px solid rgba(255,255,255,0.08); transition: border-color .15s, background .15s, transform .15s; }
.tde-tile:hover { border-color: rgba(124,156,255,0.7); background: rgba(124,156,255,0.08); transform: translateY(-1px); }
.tde-tile.on { border-color: #7C9CFF; background: rgba(124,156,255,0.16); }
.tde-ic { font-size: 19px; line-height: 1; flex: none; width: 26px; text-align: center; }
.tde-tx { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.tde-pl { font: 600 13px 'Sora', 'Inter', sans-serif; color: #EDEFF7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tde-wh { font-size: 11.5px; color: #8A93A8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tde-tag { font-size: 10px; font-weight: 700; letter-spacing: .06em; color: #FFB547; margin-right: 4px; }
.tde-nav { all: unset; cursor: pointer; flex: none; width: 30px; height: 30px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; color: #C9CEDD; background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1); font-size: 16px; }
.tde-nav:hover { border-color: #7C9CFF; color: #fff; }
@media (max-width: 700px) { .tde-nav { display: none; } .tde-tile { flex-basis: 220px; width: 220px; min-width: 220px; max-width: 220px; } }
"""

JS = r"""
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export default function (component) {
  const { data, parentElement } = component;
  let S = parentElement.__tde;
  if (!S) {
    S = parentElement.__tde = {};
    const wrap = document.createElement('div');
    wrap.className = 'tde-wrap';
    wrap.innerHTML = `<button class="tde-nav" data-d="-1" title="Previous">‹</button>
      <div class="tde-strip"></div><button class="tde-nav" data-d="1" title="More examples">›</button>`;
    parentElement.appendChild(wrap);
    S.strip = wrap.querySelector('.tde-strip');
    wrap.querySelectorAll('.tde-nav').forEach(b => b.onclick = () => S.strip.scrollBy({ left: +b.dataset.d * 520 }));
  }
  S.set = component.setTriggerValue;
  const key = JSON.stringify(data.items);
  if (key !== S.key) {
    S.key = key;
    S.strip.innerHTML = data.items.map((it, i) => `
      <button class="tde-tile" data-i="${i}" title="${esc(it.label)} — ${esc(it.what)}. ${esc(it.context)}">
        <span class="tde-ic">${esc(it.icon)}</span>
        <span class="tde-tx"><span class="tde-pl">${esc(it.label)}</span>
          <span class="tde-wh">${it.compare ? '<span class="tde-tag">COMPARE</span>' : ''}${esc(it.what)} · ${esc(it.context)}</span></span>
      </button>`).join('');
    S.strip.querySelectorAll('.tde-tile').forEach(t => t.onclick = () => S.set('open', { i: +t.dataset.i, nonce: Date.now() }));
  }
  S.strip.querySelectorAll('.tde-tile').forEach(t => t.classList.toggle('on', +t.dataset.i === data.active));
}
"""


def _register():
    return st.components.v2.component("trend_detective_examples", css=CSS, js=JS, isolate_styles=False)


_STRIP = _register()


def examples_strip(items: list[dict], active: int | None, key: str, on_open):
    """items: [{icon, label, what, context, compare}]; on_open runs as a callback when a tile is clicked."""
    global _STRIP
    try:
        return _STRIP(data=dict(items=items, active=active), key=key, on_open_change=on_open)
    except Exception as e:     # fresh runtime (e.g. AppTest) with an empty component registry
        if "not registered" not in str(e):
            raise
        _STRIP = _register()
        return _STRIP(data=dict(items=items, active=active), key=key, on_open_change=on_open)


def read_open(key: str):
    val = st.session_state.get(key)
    if val is None:
        return None
    return val.get("open") if isinstance(val, dict) else getattr(val, "open", None)
