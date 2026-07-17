"""Weekly new-stock ideas one-pager (mobile-first HTML) — the screener's shortlist, shown in the
iOS app's web view and served by GET /candidates. Each card shows the composite + sub-scores, the
Compounder/GARP/Tailwind tags, and the LLM's verdict / thesis / exit_if / risks.

Rendered on demand from the persisted Candidate rows, so it always reflects the latest weekly run.
Advisory only — it ranks and explains ideas; it is not a recommendation to buy.
"""

from __future__ import annotations

import html
import re


def _anchor(text: str, prefix: str) -> str:
    """Stable HTML id for deep-linking (e.g. stock-TCS, sec-Financial-Services)."""
    return prefix + "-" + re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-")

_VERDICT_COLOR = {"strong": "#16a34a", "watch": "#d97706", "avoid": "#dc2626"}
_SUB_LABELS = {"quality": "Quality", "growth": "Growth", "durability": "Durability",
               "valuation": "Valuation", "safety": "Safety", "liquidity": "Liquidity"}
# key -> (label, formatter)
_PCT = lambda v: f"{v:.1f}%"
_NUM = lambda v: f"{v:.2f}"
_METRICS = {
    "roe": ("ROE", _PCT), "roe_5y": ("ROE 5y", _PCT), "roce": ("ROCE", _PCT),
    "sales_cagr_5y": ("Sales CAGR 5y", _PCT), "profit_cagr_5y": ("Profit CAGR 5y", _PCT),
    "pe": ("P/E", _NUM), "debt_to_equity": ("D/E", _NUM),
    "promoter_holding": ("Promoter", _PCT), "promoter_pledge": ("Pledge", _PCT),
    "dividend_yield": ("Div yield", _PCT),
}


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _score_color(v) -> str:
    if v is None:
        return "#9ca3af"
    return "#16a34a" if v >= 60 else "#d97706" if v >= 45 else "#dc2626"


def _bar(v, color) -> str:
    w = max(0, min(100, v if v is not None else 0))
    return f'<div class="bar"><div class="fill" style="width:{w:.0f}%;background:{color}"></div></div>'


def _subscores(subs: dict) -> str:
    out = []
    for key, label in _SUB_LABELS.items():
        v = subs.get(key)
        color = _score_color(v)
        val = "—" if v is None else f"{v:.0f}"
        out.append(f'<div class="srow"><div class="slabel">{label}</div>{_bar(v, color)}'
                   f'<div class="sval" style="color:{color}">{val}</div></div>')
    return "".join(out)


def _metrics(data: dict, peg) -> str:
    cells = []
    for key, (label, fmt) in _METRICS.items():
        v = data.get(key)
        if v is not None:
            cells.append(f'<div class="kv"><span>{label}</span><b>{_esc(fmt(v))}</b></div>')
    if peg is not None:
        cells.append(f'<div class="kv"><span>PEG</span><b>{_esc(_NUM(peg))}</b></div>')
    mc = data.get("market_cap")
    if mc is not None:
        cells.append(f'<div class="kv"><span>Mkt cap</span><b>₹{mc:,.0f} cr</b></div>')
    return f'<div class="grid">{"".join(cells)}</div>' if cells else ""


def _list(title: str, items: list | None) -> str:
    items = [i for i in (items or []) if str(i).strip()]
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(i)}</li>" for i in items)
    return f'<div class="lst"><div class="lttl">{title}</div><ul>{lis}</ul></div>'


def _chips(buckets: list | None) -> str:
    return "".join(f'<span class="chip">{_esc(b)}</span>' for b in (buckets or []))


def _card(c: dict) -> str:
    sym = _esc(c.get("symbol"))
    anchor = _anchor(c.get("symbol") or "", "stock")   # deep-link target: #stock-<SYMBOL>
    comp = c.get("composite")
    comp_txt = "—" if comp is None else f"{comp:.0f}"
    data = c.get("data") or {}
    industry = data.get("industry")
    ind_html = f'<div class="ind">{_esc(industry)}</div>' if industry else ""
    llm = c.get("llm") or {}
    verdict = (llm.get("verdict") or "").lower()
    vbadge = ""
    if verdict:
        vc = _VERDICT_COLOR.get(verdict, "#6b7280")
        conv = _esc(llm.get("conviction") or "")
        vbadge = f'<span class="badge" style="background:{vc}">{verdict.upper()}·{conv}</span>'
    thesis = llm.get("thesis")
    thesis_html = f'<p class="note">{_esc(thesis)}</p>' if thesis else ""
    tailwind = llm.get("tailwind")
    tw_html = (f'<p class="tw">Tailwind: {_esc(tailwind)}</p>'
               if tailwind and tailwind.lower() != "none" else "")
    return f"""<section class="card" id="{anchor}">
 <div class="top"><div><span class="sym">{sym}</span>
   <span class="score" style="color:{_score_color(comp)}">{comp_txt}</span></div>{vbadge}</div>
 {ind_html}<div class="chips">{_chips(c.get("buckets"))}</div>
 {thesis_html}{tw_html}
 {_metrics(data, c.get("peg"))}
 <div class="subs">{_subscores(c.get("subscores") or {})}</div>
 {_list("Exit if", llm.get("exit_if"))}
 {_list("Risks", llm.get("risks"))}
</section>"""


def render_candidates_page(candidates: list[dict], run_date: str, universe: int | None = None) -> str:
    n = len(candidates)
    uni = f" · {universe} screened" if universe else ""
    # Group by sector, preserving the order candidates arrive in (already sector-grouped by the job).
    groups: dict[str, list[dict]] = {}
    for c in candidates:
        sec = (c.get("data") or {}).get("sector") or "Other"
        groups.setdefault(sec, []).append(c)

    if not groups:
        cards = '<section class="card"><p class="note">No candidates yet — the weekly screen has not produced a shortlist.</p></section>'
        toc = ""
    else:
        toc = '<div class="toc">' + " ".join(
            f'<a href="#{_anchor(sec, "sec")}">{_esc(sec)} ({len(rows)})</a>'
            for sec, rows in groups.items()) + "</div>"
        parts = []
        for sec, rows in groups.items():
            parts.append(f'<h2 class="sec-h" id="{_anchor(sec, "sec")}">{_esc(sec)}</h2>')
            parts.extend(_card(c) for c in rows)
        cards = toc + "".join(parts)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>New-stock ideas — {_esc(run_date)}</title>
<style>
:root{{color-scheme:light dark}}
*{{box-sizing:border-box}}
body{{font:15px/1.55 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:14px;color:#111;background:#f2f2f7}}
@media (prefers-color-scheme:dark){{body{{color:#e5e5ea;background:#000}}.card{{background:#1c1c1e!important}}
 .bar{{background:#2c2c2e!important}} h1{{color:#e5e5ea}}
 .chip,.toc a{{background:#2c2c2e!important;color:#c7c7cc!important}}}}
h1{{font-size:1.5rem;margin:0 0 2px}}
.hsub{{color:#8e8e93;font-size:.85rem;margin-bottom:12px}}
.card{{background:#fff;border-radius:14px;padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.06);scroll-margin-top:14px}}
.sec-h{{font-size:.9rem;margin:18px 2px 8px;color:#8e8e93;text-transform:uppercase;letter-spacing:.04em;scroll-margin-top:14px}}
.toc{{margin:0 0 14px}}
.toc a{{display:inline-block;background:#eef;color:#3730a3;border-radius:999px;padding:3px 10px;margin:0 6px 6px 0;font-size:.72rem;font-weight:600;text-decoration:none}}
.ind{{color:#8e8e93;font-size:.78rem;margin:2px 0 0}}
.top{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
.rk{{color:#8e8e93;font-weight:700}} .sym{{font-size:1.2rem;font-weight:800}}
.score{{font-size:1.1rem;font-weight:800;margin-left:6px;font-variant-numeric:tabular-nums}}
.badge{{display:inline-block;color:#fff;font-weight:700;font-size:.7rem;padding:4px 9px;border-radius:999px;text-transform:capitalize}}
.chips{{margin:8px 0}} .chip{{display:inline-block;background:#eef;border-radius:999px;padding:2px 9px;font-size:.7rem;font-weight:600;color:#3730a3;margin-right:5px}}
.note{{margin:6px 0;font-size:.95rem}} .tw{{margin:4px 0;font-size:.85rem;color:#8e8e93}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;margin:10px 0}}
.kv{{display:flex;justify-content:space-between;border-bottom:1px solid rgba(128,128,128,.15);padding:3px 0;font-size:.88rem}}
.kv span{{color:#8e8e93}}
.subs{{margin:10px 0}}
.srow{{display:flex;align-items:center;gap:10px;margin:6px 0}}
.slabel{{flex:0 0 30%;font-size:.82rem}}
.bar{{flex:1;height:8px;background:#e5e5ea;border-radius:4px;overflow:hidden}} .fill{{height:100%;border-radius:4px}}
.sval{{flex:0 0 36px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}}
.lst{{margin:8px 0}} .lttl{{font-size:.75rem;text-transform:uppercase;letter-spacing:.03em;color:#8e8e93;margin-bottom:2px}}
.lst ul{{margin:0;padding-left:18px}} .lst li{{font-size:.88rem;margin:2px 0}}
.disc{{color:#8e8e93;font-size:.72rem;margin-top:14px}}
</style></head><body>
<h1>New-stock ideas</h1>
<div class="hsub">{_esc(run_date)} · {n} candidates{uni} · ranked by composite</div>
{cards}
<p class="disc">Decision support, not investment advice. Screened and scored automatically; verify
independently before any action.</p>
</body></html>"""
