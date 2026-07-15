"""Operational status: connector health for the latest run + cumulative LLM token/cost spend.

Backs the authed `/status` API endpoint and the ops watchdog. Read-only over the audit tables
(`run_health` snapshots + `llm_calls`), so it never touches the market or the model."""

from __future__ import annotations

from datetime import date, timedelta

from ..storage.models import LLMCall, Snapshot


def _latest_run_health(session) -> tuple[str | None, dict]:
    row = (
        session.query(Snapshot)
        .filter(Snapshot.kind == "run_health")
        .order_by(Snapshot.run_date.desc(), Snapshot.id.desc())
        .first()
    )
    if not row or not isinstance(row.payload, dict):
        return None, {}
    return str(row.run_date), row.payload


def _usage(session, today: date) -> dict:
    rows = session.query(LLMCall).all()
    month_start = today.replace(day=1)
    day30 = today - timedelta(days=30)

    def agg(rs: list[LLMCall]) -> dict:
        return {
            "calls": len(rs),
            "tokens": sum(r.tokens or 0 for r in rs),
            "cost_usd": round(sum(r.cost or 0.0 for r in rs), 2),
        }

    return {
        "this_month": agg([r for r in rows if r.run_date and r.run_date >= month_start]),
        "last_30d": agg([r for r in rows if r.run_date and r.run_date >= day30]),
        "all_time": agg(rows),
        "note": "cost is an estimate from token counts × configured per-model rates",
    }


def build_status(session_factory, today: date | None = None, budget_usd: float | None = None) -> dict:
    """Connector health (latest run) + token/cost spend. If budget_usd is given, flags an
    over-budget month so callers can prompt the operator to recharge."""
    today = today or date.today()
    with session_factory() as session:
        last_run, connectors = _latest_run_health(session)
        usage = _usage(session, today)

    degraded = [k for k, v in connectors.items() if isinstance(v, dict) and v.get("status") == "degraded"]
    out = {
        "status": "degraded" if degraded else "ok",
        "last_run": last_run,
        "connectors": connectors,
        "degraded": degraded,
        "usage": usage,
    }
    if budget_usd is not None:
        spent = usage["this_month"]["cost_usd"]
        out["budget"] = {
            "monthly_usd": budget_usd,
            "spent_usd": spent,
            "remaining_usd": round(budget_usd - spent, 2),
            "over_budget": spent >= budget_usd,
        }
    return out
