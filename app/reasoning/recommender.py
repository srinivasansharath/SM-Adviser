"""Run the scoring engine over a day's holdings and persist Score + Recommendation rows."""

from __future__ import annotations

from datetime import date

from ..storage.models import Holding, Metric, OrderFlow, Recommendation, Score
from .scoring import score_holding

_METRIC_FIELDS = (
    "ret_1d", "ret_5d", "ret_20d", "drawdown", "rsi", "vol_spike", "rel_strength",
    "sma_20", "sma_50", "sma_200",
)
_SCORE_FIELDS = ("thesis", "fundamental", "technical", "valuation", "news_risk", "portfolio_fit")


def _metric_dict(m: Metric | None) -> dict:
    return {f: getattr(m, f) for f in _METRIC_FIELDS} if m else {}


def _of_dict(o: OrderFlow | None) -> dict:
    return {"signal": o.signal, "delivery_pct": o.delivery_pct} if o else {}


def _prev_classification(session, symbol: str, run_date: date) -> str | None:
    row = (
        session.query(Recommendation)
        .filter(Recommendation.symbol == symbol, Recommendation.run_date < run_date)
        .order_by(Recommendation.run_date.desc())
        .first()
    )
    return row.classification if row else None


def run_scoring(session_factory, run_date: date, theses: dict, config: dict,
                fundamentals_data: dict | None = None, news_data: dict | None = None) -> int:
    count = 0
    with session_factory() as session:
        session.query(Score).filter(Score.run_date == run_date).delete()
        session.query(Recommendation).filter(Recommendation.run_date == run_date).delete()

        holdings = session.query(Holding).filter_by(run_date=run_date).all()
        metrics = {m.symbol: m for m in session.query(Metric).filter_by(run_date=run_date)}
        flows = {o.symbol: o for o in session.query(OrderFlow).filter_by(run_date=run_date)}

        for h in holdings:
            meta = (theses or {}).get(h.symbol)
            prev = _prev_classification(session, h.symbol, run_date)
            result = score_holding(
                {"symbol": h.symbol, "ltp": h.ltp, "weight_pct": h.weight_pct},
                _metric_dict(metrics.get(h.symbol)),
                _of_dict(flows.get(h.symbol)),
                (fundamentals_data or {}).get(h.symbol),
                meta,
                prev,
                config,
                news=(news_data or {}).get(h.symbol),
            )

            sub = result["subscores"]
            session.add(Score(run_date=run_date, symbol=h.symbol, **{f: sub.get(f) for f in _SCORE_FIELDS}))
            session.add(
                Recommendation(
                    run_date=run_date,
                    symbol=h.symbol,
                    classification=result["classification"],
                    confidence=result["confidence"],
                    reason="; ".join(result["reasons"]) if result["reasons"] else None,
                    evidence=None,  # LLM layer (Phase 4b) attaches cited evidence
                    prev_classification=prev,
                )
            )
            count += 1
        session.commit()
    return count
