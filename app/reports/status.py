"""Operational health — the data behind the authed `/status` endpoint, the ops watchdog, and the
in-app health view. Covers both scheduled jobs and their external APIs:

  * portfolio_review  (daily morning run)  — zerodha, market-data, fundamentals, news, order-flow
  * new_stock_screen  (weekly screener run) — universe (screener), fundamentals, market-data, LLM
  * system            — database, LLM token/cost spend vs budget

Each job records a `*_health` snapshot per run (which external calls returned data vs errored); this
reads those, adds freshness (has the job run recently?), and rolls everything into an overall
status + a plain-language `issues` list. Read-only over the audit tables — never touches an API."""

from __future__ import annotations

from datetime import date, timedelta

from ..storage.models import LLMCall, Snapshot


def _latest(session, kind: str) -> Snapshot | None:
    return (
        session.query(Snapshot)
        .filter(Snapshot.kind == kind)
        .order_by(Snapshot.run_date.desc(), Snapshot.id.desc())
        .first()
    )


def _usage(session, today: date) -> dict:
    rows = session.query(LLMCall).all()
    month_start = today.replace(day=1)
    day30 = today - timedelta(days=30)

    def agg(rs: list[LLMCall]) -> dict:
        return {"calls": len(rs), "tokens": sum(r.tokens or 0 for r in rs),
                "cost_usd": round(sum(r.cost or 0.0 for r in rs), 2)}

    return {
        "this_month": agg([r for r in rows if r.run_date and r.run_date >= month_start]),
        "last_30d": agg([r for r in rows if r.run_date and r.run_date >= day30]),
        "all_time": agg(rows),
        "note": "cost is an estimate from token counts × configured per-model rates",
    }


def _service(session, kind: str, label: str, max_age_days: int, today: date, issues: list,
             fallback_kind: str | None = None) -> dict:
    """Health of one scheduled job from its latest `*_health` snapshot: per-connector status +
    freshness. Appends human-readable problems to `issues`.

    Grace period: if there's no health snapshot yet but the job DID produce output recently (its
    `fallback_kind` snapshot — holdings / screen), don't flag it (a fresh deploy that hasn't recorded
    health is not a failure). And a job with no evidence of ever running is 'unknown' but silent —
    not a page (it's not-yet-set-up, not broken; a job that stops after running is caught by staleness)."""
    snap = _latest(session, kind)
    payload = snap.payload if snap and isinstance(snap.payload, dict) else {}
    connectors = {k: v for k, v in payload.items() if isinstance(v, dict)}
    run_aborted = bool(payload.get("run_aborted"))

    # Freshness reference: the health snapshot, else a "the job ran" fallback snapshot.
    ref = snap or (_latest(session, fallback_kind) if fallback_kind else None)
    last_run = str(ref.run_date) if ref else None
    age_days = (today - ref.run_date).days if ref else None

    degraded = [k for k, v in connectors.items() if v.get("status") == "degraded"]
    if ref is None:
        status = "unknown"          # never run and no output -> informational only, no alert
    elif age_days is not None and age_days > max_age_days:
        status = "stale"
        issues.append(f"{label}: last ran {age_days} days ago (expected within {max_age_days})")
    elif run_aborted:
        status = "failed"
        issues.append(f"{label}: last run aborted before completing")
    elif degraded:
        status = "degraded"
        for k in degraded:
            issues.append(f"{label}: {k} degraded — {connectors[k].get('detail', '')}".rstrip(" —"))
    else:
        status = "ok"               # includes: ran recently but health not yet recorded (deploy gap)

    meta = {k: v for k, v in payload.items() if not isinstance(v, dict) and k != "run_aborted"}
    return {"status": status, "last_run": last_run, "age_days": age_days,
            "run_aborted": run_aborted, "connectors": connectors, **meta}


def build_status(session_factory, today: date | None = None, budget_usd: float | None = None) -> dict:
    """Full operational health: portfolio-review + new-stock-screen + system, with an overall
    status and a plain-language `issues` list the app and watchdog can surface directly."""
    today = today or date.today()
    issues: list[str] = []
    with session_factory() as session:
        portfolio_review = _service(session, "run_health", "Portfolio review", 3, today, issues,
                                    fallback_kind="holdings")
        new_stock_screen = _service(session, "screen_health", "New-stock screen", 8, today, issues,
                                    fallback_kind="screen")
        usage = _usage(session, today)

    budget = None
    if budget_usd is not None:
        spent = usage["this_month"]["cost_usd"]
        over = spent >= budget_usd
        budget = {"monthly_usd": budget_usd, "spent_usd": spent,
                  "remaining_usd": round(budget_usd - spent, 2), "over_budget": over}
        if over:
            issues.append(f"LLM spend ${spent:.2f} exceeded the ${budget_usd:.0f} monthly budget — recharge")

    return {
        "status": "degraded" if issues else "ok",
        "issues": issues,
        "services": {
            "portfolio_review": portfolio_review,
            "new_stock_screen": new_stock_screen,
            "system": {"database": "ok", "llm": {"usage": usage, "budget": budget}},
        },
    }
