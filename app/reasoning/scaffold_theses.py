"""Scaffold theses.yaml from the latest stored holdings.

theses.yaml is the heart of the agent — it encodes WHY you own each stock and what would
break the thesis, so Phase 4 can judge "is the thesis still intact?" rather than just reacting
to price. This generator pre-fills the structure (one block per current holding) with TODOs and
research-backed default exit conditions for you to edit.

Run:  python -m app.reasoning.scaffold_theses          # writes theses.yaml (won't overwrite)
      python -m app.reasoning.scaffold_theses --force   # overwrite existing
"""

from __future__ import annotations

import sys
from datetime import date

from ..config import REPO_ROOT
from ..storage.db import bootstrap
from ..storage.models import Holding

_HEADER = """\
# theses.yaml — the heart of the agent: WHY you own each stock + what would break the thesis.
# The agent checks each holding against THIS, not just price. Keyed by NSE tradingsymbol.
# Fill in every TODO. Tailor the exit_if conditions to each business (the defaults are generic
# starting points from the decision-methods research). Regenerate the skeleton with:
#     python -m app.reasoning.scaffold_theses
"""

# Generic, research-backed exit conditions (RESEARCH_DECISION_METHODS.md) — edit per stock.
_DEFAULT_EXITS = [
    "Revenue or EPS declines for 2 consecutive quarters",
    "Falls below the 200-DMA while fundamentals deteriorate (not a price dip alone)",
    "Debt/solvency worsens materially (interest coverage < 1.5x) or a dividend cut",
    "A governance red flag (auditor exit, rising promoter pledge, SEBI action)",
]


def _block(h: Holding) -> str:
    pnl = f" | P&L ₹{h.pnl:,.0f}" if h.pnl is not None else ""
    exits = "\n".join(f'    - "{c}"' for c in _DEFAULT_EXITS)
    return f"""
{h.symbol}:
  # Position: {h.qty:.0f} @ avg ₹{h.avg_price:.2f} | LTP ₹{h.ltp:.2f} | weight {h.weight_pct:.1f}%{pnl}
  thesis: ""              # TODO: one line — the core reason you hold this
  conviction: medium      # high | medium | low
  target_weight_pct: {round(h.weight_pct or 0)}       # your intended weight (current shown above)
  bought_reason: ""       # TODO: what made you buy it originally
  exit_if:                # TODO: tailor these to THIS business
{exits}
"""


def build_scaffold(holdings: list[Holding]) -> str:
    holdings = sorted(holdings, key=lambda h: h.weight_pct or 0, reverse=True)
    return _HEADER + "".join(_block(h) for h in holdings)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    force = "--force" in argv
    out = REPO_ROOT / "theses.yaml"
    if out.exists() and not force:
        print(f"{out} already exists — refusing to overwrite (use --force). No changes made.")
        return

    session_factory = bootstrap()
    with session_factory() as session:
        latest = session.query(Holding).order_by(Holding.run_date.desc()).first()
        if latest is None:
            print("No holdings in the DB yet — run the morning job first.")
            return
        holdings = session.query(Holding).filter_by(run_date=latest.run_date).all()

    out.write_text(build_scaffold(holdings), encoding="utf-8")
    print(f"Wrote {out} with {len(holdings)} holdings (run_date {latest.run_date}). Fill in the TODOs.")


if __name__ == "__main__":
    main()
