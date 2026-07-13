"""Per-stock analysis one-pager (mobile-first HTML) — shown in the iOS app when a holding
is tapped. Explains HOW the Hold/Watch/Trim/Exit call was reached: the six sub-scores, the
composite band, the LLM's plain-language read, and the underlying evidence.

Rendered once per holding during the daily run (into reports_out/stock_<SYMBOL>.html) and
served by GET /stock/{symbol}. Designed to reflow on a phone and respect dark mode.
"""

from __future__ import annotations

import html
from pathlib import Path

from ..reasoning.scoring import DEFAULT_WEIGHTS, composite

# Classification -> accent colour (matches the app + daily report).
_CLASS_COLOR = {
    "Accumulate Candidate": "#16a34a",
    "Hold": "#16a34a",
    "Watch": "#d97706",
    "Trim Candidate": "#ea580c",
    "Exit Candidate": "#dc2626",
}
_THESIS_COLOR = {"intact": "#16a34a", "watch": "#d97706", "impaired": "#dc2626"}
_SUBSCORE_LABELS = {
    "technical": "Technical", "fundamental": "Fundamental", "valuation": "Valuation",
    "portfolio_fit": "Portfolio fit", "thesis": "Thesis", "news_risk": "News risk",
}
_FUND_LABELS = {
    "pe": "P/E", "roce": "ROCE", "roe": "ROE", "dividend_yield": "Div yield",
    "book_value": "Book value", "market_cap": "Mkt cap", "debt_to_equity": "D/E",
}
_BANDS = [(0, "Exit"), (30, "Trim"), (45, "Hold"), (60, "Watch"), (75, "Accumulate")]


def _pct(v, plus=True) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%" if plus else f"{v:.2f}%"


def _score_color(v) -> str:
    if v is None:
        return "#9ca3af"
    return "#16a34a" if v >= 60 else "#d97706" if v >= 45 else "#dc2626"


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _bar(v, color) -> str:
    w = max(0, min(100, v if v is not None else 0))
    return (f'<div class="bar"><div class="fill" style="width:{w:.0f}%;background:{color}"></div></div>')


def _subscore_rows(scores: dict) -> str:
    out = []
    for key, label in _SUBSCORE_LABELS.items():
        v = scores.get(key)
        w = DEFAULT_WEIGHTS.get(key, 0)
        val = "no data" if v is None else f"{v:.0f}"
        color = _score_color(v)
        out.append(
            f'<div class="srow"><div class="slabel">{label}'
            f'<span class="wt">wt {int(w*100)}%</span></div>'
            f'{_bar(v, color)}<div class="sval" style="color:{color}">{val}</div></div>'
        )
    return "".join(out)


def _fundamentals_rows(fund: dict) -> str:
    if not fund:
        return '<div class="muted">No fundamentals fetched for this stock.</div>'
    cells = []
    for key, label in _FUND_LABELS.items():
        if key in fund and fund[key] is not None:
            cells.append(f'<div class="kv"><span>{label}</span><b>{_esc(fund[key])}</b></div>')
    # include any extra keys we don't have a label for
    for key, v in fund.items():
        if key not in _FUND_LABELS and v is not None:
            cells.append(f'<div class="kv"><span>{_esc(key)}</span><b>{_esc(v)}</b></div>')
    return f'<div class="grid">{"".join(cells)}</div>' if cells else '<div class="muted">—</div>'


def _evidence_grid(row: dict) -> str:
    def cell(label, val):
        return f'<div class="kv"><span>{label}</span><b>{val}</b></div>'

    dma50 = "above" if row.get("above_50dma") else "below" if row.get("above_50dma") is not None else "—"
    dma200 = "above" if row.get("above_200dma") else "below" if row.get("above_200dma") is not None else "—"
    rsi = row.get("rsi")
    cells = [
        cell("Today", _pct(row.get("day_change_pct"))),
        cell("1 month", _pct(row.get("ret_20d"))),
        cell("1 year", _pct(row.get("ret_252d"))),
        cell("Since buy", _pct(row.get("return_pct"))),
        cell("vs 50-DMA", dma50),
        cell("vs 200-DMA", dma200),
        cell("RSI (14)", "—" if rsi is None else f"{rsi:.0f}"),
        cell("Max drawdown", _pct(row.get("drawdown"), plus=False)),
        cell("Rel. strength", "—" if row.get("rel_strength") is None else f'{row["rel_strength"]:+.1f}'),
        cell("Weight", "—" if row.get("weight_pct") is None else f'{row["weight_pct"]:.1f}%'),
    ]
    return f'<div class="grid">{"".join(cells)}</div>'


def _reasons_list(rec_reason: str | None) -> str:
    if not rec_reason:
        return ""
    items = [r.strip() for r in rec_reason.split(";") if r.strip()]
    lis = "".join(f"<li>{_esc(r)}</li>" for r in items)
    return f"<ul class='reasons'>{lis}</ul>"


def render_stock_page(row: dict, note: dict | None, run_date: str, prices_as_of: str | None = None) -> str:
    sym = _esc(row.get("symbol"))
    cls = row.get("classification") or "Unclassified"
    accent = _CLASS_COLOR.get(cls, "#6b7280")
    conf = row.get("confidence") or "—"
    prev = row.get("prev_classification")
    changed = f' · was {_esc(prev)}' if prev and prev != cls else ""

    scores = row.get("scores") or {}
    comp, coverage, conf_label = composite(scores)
    comp_txt = "—" if comp is None else f"{comp:.0f}"
    marker = "" if comp is None else (
        f'<div class="cmark" style="left:{max(0,min(100,comp)):.0f}%"></div>')
    band_ticks = "".join(
        f'<span class="tick" style="left:{edge}%">{lbl}</span>' for edge, lbl in _BANDS)

    note = note or {}
    thesis = (note.get("thesis_status") or "").lower()
    note_txt = note.get("note")
    analyst = ""
    if note_txt:
        badge = ""
        if thesis:
            tc = _THESIS_COLOR.get(thesis, "#6b7280")
            badge = f'<span class="pill" style="background:{tc}">Thesis: {thesis.upper()}</span>'
        analyst = (f'<section class="card"><h2>Analyst view {badge}</h2>'
                   f'<p class="note">{_esc(note_txt)}</p></section>')

    ltp = row.get("ltp")
    ltp_txt = "—" if ltp is None else (f"₹{ltp:,.0f}" if ltp >= 1000 else f"₹{ltp:,.2f}")
    ret = row.get("return_pct")
    pnl = row.get("pnl")
    ret_color = "#16a34a" if (ret or 0) >= 0 else "#dc2626"
    pnl_txt = "" if pnl is None else f' ({"+" if pnl >= 0 else "-"}₹{abs(pnl):,.0f})'

    asof = f' · prices {_esc(prices_as_of)}' if prices_as_of else ""

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sym} — analysis</title>
<style>
:root{{color-scheme:light dark}}
*{{box-sizing:border-box}}
body{{font:15px/1.55 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:14px;
 color:#111;background:#f2f2f7}}
@media (prefers-color-scheme:dark){{body{{color:#e5e5ea;background:#000}}.card{{background:#1c1c1e!important}}
 .bar{{background:#2c2c2e!important}} .tick{{color:#8e8e93}} h2{{color:#e5e5ea}}}}
.card{{background:#fff;border-radius:14px;padding:14px 16px;margin-bottom:12px;
 box-shadow:0 1px 3px rgba(0,0,0,.06)}}
h1{{font-size:1.7rem;margin:0}} h2{{font-size:.95rem;margin:0 0 10px;color:#333}}
.badge{{display:inline-block;color:#fff;font-weight:700;font-size:.8rem;padding:4px 10px;border-radius:999px}}
.pill{{display:inline-block;color:#fff;font-weight:600;font-size:.65rem;padding:2px 8px;border-radius:999px;
 vertical-align:middle;margin-left:6px}}
.top{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
.price{{font-size:1.3rem;font-weight:700}} .sub{{color:#8e8e93;font-size:.85rem}}
.note{{margin:0;font-size:.95rem}}
.gauge{{position:relative;height:12px;background:linear-gradient(90deg,#dc2626,#ea580c,#d97706,#16a34a);
 border-radius:6px;margin:26px 6px 30px}}
.cmark{{position:absolute;top:-6px;width:4px;height:24px;background:#111;border:2px solid #fff;border-radius:3px}}
@media (prefers-color-scheme:dark){{.cmark{{background:#fff;border-color:#000}}}}
.tick{{position:absolute;top:16px;transform:translateX(-50%);font-size:.6rem;color:#8e8e93;white-space:nowrap}}
.srow{{display:flex;align-items:center;gap:10px;margin:8px 0}}
.slabel{{flex:0 0 34%;font-size:.85rem}} .wt{{color:#8e8e93;font-size:.65rem;margin-left:5px}}
.bar{{flex:1;height:8px;background:#e5e5ea;border-radius:4px;overflow:hidden}}
.fill{{height:100%;border-radius:4px}}
.sval{{flex:0 0 48px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px}}
.kv{{display:flex;justify-content:space-between;border-bottom:1px solid rgba(128,128,128,.15);padding:4px 0;font-size:.9rem}}
.kv span{{color:#8e8e93}}
.reasons{{margin:6px 0 0;padding-left:18px}} .reasons li{{margin:3px 0;font-size:.9rem}}
.muted{{color:#8e8e93;font-size:.85rem}}
.disc{{color:#8e8e93;font-size:.72rem;text-align:center;margin:14px 4px 4px}}
</style></head><body>

<section class="card">
  <div class="top">
    <h1>{sym}</h1>
    <span class="badge" style="background:{accent}">{_esc(cls)}</span>
  </div>
  <div class="top" style="margin-top:8px">
    <div class="price">{ltp_txt}</div>
    <div class="sub">Confidence: {_esc(conf)}{changed}</div>
  </div>
  <div class="sub" style="margin-top:4px">
    Since buy <b style="color:{ret_color}">{_pct(ret)}</b>{pnl_txt}
  </div>
</section>

{analyst}

<section class="card">
  <h2>How this call was reached</h2>
  <div class="gauge">{marker}{band_ticks}</div>
  <div class="sub">Composite score <b style="color:#111">{comp_txt}</b>/100 (data coverage {int(coverage*100)}% → {conf_label} confidence). The composite is a weighted blend of the sub-scores below, mapped to a band; a hysteresis buffer avoids day-to-day churn.</div>
  {_reasons_list(row.get("rec_reason"))}
</section>

<section class="card">
  <h2>Sub-scores (0–100, higher = healthier)</h2>
  {_subscore_rows(scores)}
</section>

<section class="card">
  <h2>Evidence</h2>
  {_evidence_grid(row)}
</section>

<section class="card">
  <h2>Fundamentals</h2>
  {_fundamentals_rows(row.get("fundamentals") or {})}
</section>

<div class="disc">As of {_esc(run_date)}{asof}. Personal informational use, not investment advice.</div>
</body></html>"""


def write_stock_pages(data: dict, output_dir: Path, narrative: dict | None = None) -> list[Path]:
    """Render one analysis page per holding into output_dir/stock_<SYMBOL>.html."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    notes = (narrative or {}).get("holdings") or {}
    paths = []
    for row in data.get("holdings", []):
        sym = row.get("symbol")
        if not sym:
            continue
        note = notes.get(sym) if isinstance(notes.get(sym), dict) else None
        htmlp = output_dir / f"stock_{sym}.html"
        htmlp.write_text(
            render_stock_page(row, note, data.get("run_date", ""), data.get("prices_as_of")),
            encoding="utf-8",
        )
        paths.append(htmlp)
    return paths
