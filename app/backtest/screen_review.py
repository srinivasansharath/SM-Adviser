"""Did the weekly screener's advice actually work? A retrospective on real past recommendations.

    python -m app.backtest.screen_review [--min-days 14] [--benchmark ^NSEI]

Unlike backtest/engine.py — which reconstructs a signal from history and is therefore exposed to
look-ahead and survivorship bias — this reads what the screener ACTUALLY recommended, on the day it
recommended it, from the candidates table. `detail.data.cmp` is the price at that moment. So the
comparison is genuinely out-of-sample: the recommendation was recorded before the outcome existed.

It measures each candidate's return since recommendation against the benchmark over the SAME
window, because a rising tide lifts everything and absolute returns would flatter the screener in
a bull market.

HONEST LIMITS, which the output repeats:
  - Horizons here are weeks, not years. Short-horizon equity returns are mostly noise.
  - Cohorts are ~11 names. Differences of a few percent between buckets are not signal.
  - Nothing is annualised, because extrapolating weeks to years would be meaningless.
  - It cannot tell you the screener is good. It CAN tell you if it is obviously broken.
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
from collections import defaultdict


def _pct(a: float, b: float) -> float | None:
    """Return from a to b, in percent."""
    if not a or a <= 0 or b is None:
        return None
    return (b / a - 1.0) * 100.0


def load_candidates(session_factory) -> list[dict]:
    """Every past recommendation with the price it was made at."""
    from ..storage.models import Candidate

    out = []
    with session_factory() as s:
        for c in s.query(Candidate).order_by(Candidate.run_date, Candidate.rank).all():
            detail = c.detail or {}
            data = detail.get("data") or {}
            llm = detail.get("llm") or {}
            cmp_price = data.get("cmp")
            if not cmp_price:
                continue                      # cannot measure without an entry price
            out.append({
                "run_date": c.run_date,
                "symbol": c.symbol,
                "rank": c.rank,
                "composite": c.composite,
                "cmp": float(cmp_price),
                "verdict": (llm.get("verdict") if isinstance(llm, dict) else None),
                "buckets": c.buckets or [],
            })
    return out


# Organic single-day moves beyond this are rare; unadjusted splits/bonuses are not. yfinance is
# called with auto_adjust=True, but on 2026-09-08 ORIANA showed an 80% one-day "drop" (1205 -> 250,
# a ~1:5 ratio) that Yahoo had not adjusted — five cohorts all read as ~-77%, which would have
# dominated the mean and inverted the composite finding. Quarantine, never silently average in.
SPLIT_SUSPECT_PCT = 35.0


def suspect_corporate_action(candles: list[dict]) -> tuple[bool, str | None]:
    """True when the series contains a one-day move big enough to look like an unadjusted split."""
    for i in range(1, len(candles)):
        prev, cur = candles[i - 1]["close"], candles[i]["close"]
        if not prev:
            continue
        move = (cur - prev) / prev * 100.0
        if abs(move) >= SPLIT_SUSPECT_PCT:
            ratio = (prev / cur) if cur else 0
            return True, (f"{move:+.0f}% on {candles[i]['date']} "
                          f"(~1:{ratio:.1f} ratio)" if move < 0 else
                          f"{move:+.0f}% on {candles[i]['date']}")
    return False, None


def _close_on_or_before(candles: list[dict], when: dt.date) -> float | None:
    best = None
    for c in candles:
        d = c["date"]
        d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)[:10])
        if d <= when:
            best = c["close"]
    return best


def review(session_factory, market_data, benchmark: str = "^NSEI", min_days: int = 14,
           today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    rows = load_candidates(session_factory)
    # Always return the same shape — callers should not have to branch on an error key just
    # because there is nothing to measure yet.
    if not rows:
        return {"results": [], "quarantined": [], "today": today, "benchmark": benchmark,
                "skipped_fresh": 0, "note": "no candidates with a recorded entry price"}

    oldest = min(r["run_date"] for r in rows)
    span_days = (today - oldest).days + 10

    bench = market_data.get_index_candles(benchmark, span_days) or []
    bench_now = bench[-1]["close"] if bench else None

    results: list[dict] = []
    quarantined: list[dict] = []
    for sym in sorted({r["symbol"] for r in rows}):
        try:
            candles = market_data.get_daily_candles(sym, span_days)
        except Exception:
            candles = []
        if not candles:
            continue
        suspect, why = suspect_corporate_action(candles)
        now_price = candles[-1]["close"]
        for r in [x for x in rows if x["symbol"] == sym]:
            held = (today - r["run_date"]).days
            if held < min_days:
                continue                      # too fresh to say anything
            ret = _pct(r["cmp"], now_price)
            b0 = _close_on_or_before(bench, r["run_date"])
            bret = _pct(b0, bench_now) if b0 else None
            if ret is None or bret is None:
                continue
            row = {**r, "held_days": held, "ret_pct": ret, "bench_pct": bret,
                   "excess_pct": ret - bret, "suspect": suspect, "suspect_why": why}
            (quarantined if suspect else results).append(row)
    return {"results": results, "quarantined": quarantined, "today": today,
            "benchmark": benchmark,
            "skipped_fresh": sum(1 for r in rows if (today - r["run_date"]).days < min_days)}


def _summarise(label: str, rows: list[dict]) -> str:
    if not rows:
        return f"  {label:<26} (none)"
    ex = [r["excess_pct"] for r in rows]
    beat = sum(1 for e in ex if e > 0)
    return (f"  {label:<26} n={len(rows):<4} median excess {statistics.median(ex):+7.1f}%  "
            f"mean {statistics.mean(ex):+7.1f}%  beat benchmark {beat}/{len(rows)} "
            f"({100*beat/len(rows):.0f}%)")


def report(rev: dict) -> str:
    res = rev["results"]
    if rev.get("note") and not res:
        return rev["note"]
    L = [f"Weekly screener review — {len(res)} recommendations with >= 14 days elapsed",
         f"(as of {rev['today']}, vs {rev['benchmark']}; "
         f"{rev['skipped_fresh']} too recent to judge)", ""]
    if not res:
        return "\n".join(L + ["  nothing old enough to evaluate yet"])

    L.append("OVERALL")
    L.append(_summarise("all recommendations", res))
    L.append("")

    L.append("BY COHORT (the Sunday it was recommended)")
    by_date = defaultdict(list)
    for r in res:
        by_date[r["run_date"]].append(r)
    for d in sorted(by_date):
        L.append(_summarise(str(d), by_date[d]))
    L.append("")

    L.append("DOES A HIGHER COMPOSITE MEAN A BETTER OUTCOME?")
    scored = [r for r in res if r["composite"] is not None]
    if len(scored) >= 8:
        scored.sort(key=lambda r: r["composite"], reverse=True)
        half = len(scored) // 2
        L.append(_summarise("top half by composite", scored[:half]))
        L.append(_summarise("bottom half by composite", scored[half:]))
    else:
        L.append("  too few scored candidates to split")
    L.append("")

    L.append("BY LLM VERDICT")
    by_v = defaultdict(list)
    for r in res:
        by_v[r["verdict"] or "(none)"].append(r)
    for v in sorted(by_v):
        L.append(_summarise(v, by_v[v]))
    L.append("")

    best = sorted(res, key=lambda r: r["excess_pct"], reverse=True)
    L.append("BEST / WORST vs benchmark")
    for r in best[:5]:
        L.append(f"  + {r['symbol']:<12} {r['run_date']}  {r['held_days']:>3}d  "
                 f"{r['ret_pct']:+7.1f}%  excess {r['excess_pct']:+7.1f}%")
    for r in best[-5:]:
        L.append(f"  - {r['symbol']:<12} {r['run_date']}  {r['held_days']:>3}d  "
                 f"{r['ret_pct']:+7.1f}%  excess {r['excess_pct']:+7.1f}%")
    q = rev.get("quarantined") or []
    if q:
        L += ["", "QUARANTINED — price series looks unadjusted for a corporate action,",
              "so the 'return' would be an artifact, not a loss. Excluded from every number above:"]
        for sym in sorted({r["symbol"] for r in q}):
            ex = [r for r in q if r["symbol"] == sym]
            L.append(f"  ! {sym:<12} {len(ex)} recommendation(s), apparent {ex[0]['ret_pct']:+.0f}% "
                     f"— {ex[0]['suspect_why']}")
        L.append("  Verify these by hand before believing either the loss or the exclusion.")

    L += ["",
          "READ THIS BEFORE DRAWING CONCLUSIONS:",
          "  Horizons are weeks. Short-horizon returns are mostly noise, and cohorts are ~11 names,",
          "  so bucket differences of a few percent mean nothing. This can show the screener is",
          "  obviously broken; it cannot show that it is good. Re-run as history accumulates."]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-days", type=int, default=14)
    ap.add_argument("--benchmark", default="^NSEI")
    args = ap.parse_args()

    from ..connectors.market_data import get_market_data
    from ..storage.db import default_session_factory

    print(report(review(default_session_factory(), get_market_data(),
                        benchmark=args.benchmark, min_days=args.min_days)))


if __name__ == "__main__":
    main()
