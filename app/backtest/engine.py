"""Backtest harness (Phase 5) — how predictive is the agent's as-of TECHNICAL signal?

For each (symbol, past date) we reconstruct the agent's technical score + risk flag using only
data available up to that date, then measure the forward return vs NIFTY over several horizons.
This validates the technical engine; it does NOT validate fundamentals/thesis/LLM (those can't be
reconstructed point-in-time without look-ahead bias).

Honest caveats: small samples are directional, not conclusive; the current-ticker universe carries
survivorship bias; momentum-type signals are inherently noisy over short horizons.
"""

from __future__ import annotations

import pandas as pd

from ..analytics.technicals import compute_metrics
from ..reasoning.scoring import score_technical
from ..reports.signals import evaluate_flags

# A diverse, liquid basket chosen for coverage across sectors — NOT picked by outcome.
DEFAULT_UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT",
    "TATAMOTORS", "SUNPHARMA", "HINDUNILVR", "AXISBANK", "MARUTI", "BHARTIARTL", "ASIANPAINT",
]


def forward_return_pct(candles: list[dict], i: int, horizon: int) -> float | None:
    if i + horizon >= len(candles):
        return None
    c0 = candles[i]["close"]
    if not c0:
        return None
    return round((candles[i + horizon]["close"] / c0 - 1) * 100, 2)


def evaluate_point(candles: list[dict], index_by_date: dict, i: int, horizons: list[int], config: dict) -> dict:
    """Reconstruct the as-of technical signal at index i and its forward (excess) returns."""
    metric = compute_metrics(candles[: i + 1])
    ltp = candles[i]["close"]
    as_of = candles[i]["date"]

    # As-of relative strength (20-day) vs the index.
    if i >= 20 and as_of in index_by_date:
        prior = candles[i - 20]["date"]
        if prior in index_by_date and candles[i - 20]["close"] and index_by_date[prior]:
            s20 = (ltp / candles[i - 20]["close"] - 1) * 100
            x20 = (index_by_date[as_of] / index_by_date[prior] - 1) * 100
            metric["rel_strength"] = round(s20 - x20, 2)

    res = {
        "as_of": as_of,
        "tech_score": score_technical(metric, ltp),
        "flag": evaluate_flags({"weight_pct": None, "ltp": ltp}, metric, {}, config)["flag"],
        "fwd": {},
        "excess": {},
    }
    ni0 = index_by_date.get(as_of)
    for h in horizons:
        fr = forward_return_pct(candles, i, h)
        res["fwd"][h] = fr
        ex = None
        if fr is not None and ni0:
            ni1 = index_by_date.get(candles[i + h]["date"])
            if ni1:
                ex = round(fr - (ni1 / ni0 - 1) * 100, 2)
        res["excess"][h] = ex
    return res


def run_backtest(symbols: list[str], market_data, as_of_offsets: list[int], horizons: list[int],
                 config: dict | None = None, history: int = 520) -> list[dict]:
    config = config or {}
    idx = market_data.get_index_candles("NIFTY 50", history)
    index_by_date = {c["date"]: c["close"] for c in idx}

    results: list[dict] = []
    for sym in symbols:
        try:
            candles = market_data.get_daily_candles(sym, history)
        except Exception:
            continue
        if len(candles) < 260:
            continue
        for off in as_of_offsets:
            i = len(candles) - 1 - off
            if i < 210:  # need ~200 days of history for the 200-DMA
                continue
            r = evaluate_point(candles, index_by_date, i, horizons, config)
            r["symbol"] = sym
            results.append(r)
    return results


def scorecard(results: list[dict], horizons: list[int]) -> dict:
    rows = [r for r in results if r["tech_score"] is not None]
    out: dict = {"n_observations": len(rows), "horizons": {}}
    for h in horizons:
        pts = [(r["tech_score"], r["excess"][h], r["flag"]) for r in rows if r["excess"].get(h) is not None]
        if not pts:
            continue
        tech = pd.Series([p[0] for p in pts])
        exc = pd.Series([p[1] for p in pts])
        # Spearman = Pearson on ranks (avoids a scipy dependency).
        corr = None
        if len(pts) > 2 and tech.nunique() > 1 and exc.nunique() > 1:
            corr = round(tech.rank().corr(exc.rank()), 3)
        risk = [p[1] for p in pts if p[2] == "risk"]
        ok = [p[1] for p in pts if p[2] == "ok"]

        def avg(x):
            return round(sum(x) / len(x), 2) if x else None

        out["horizons"][h] = {
            "n": len(pts),
            "spearman_score_vs_excess": corr,
            "avg_excess_ok_calls": avg(ok),
            "n_ok": len(ok),
            "avg_excess_risk_calls": avg(risk),
            "n_risk": len(risk),
            "ok_outperformed_rate": round(sum(1 for e in ok if e > 0) / len(ok), 2) if ok else None,
            "risk_underperformed_rate": round(sum(1 for e in risk if e < 0) / len(risk), 2) if risk else None,
        }
    return out


def main() -> None:
    import json

    from ..connectors.market_data import get_market_data

    horizons = [21, 63, 126]  # ~1, 3, 6 months (trading days)
    results = run_backtest(
        DEFAULT_UNIVERSE, get_market_data(), as_of_offsets=[252, 147], horizons=horizons
    )
    card = scorecard(results, horizons)
    print(json.dumps(card, indent=2, default=str))
    print("\nPer-observation (symbol | as_of | tech | flag | excess@1m/3m/6m):")
    for r in sorted(results, key=lambda x: (x["symbol"], str(x["as_of"]))):
        ex = r["excess"]
        print(f"  {r['symbol']:>11} {str(r['as_of'])[:10]}  tech={r['tech_score']!s:>5}  {r['flag']:>5}  "
              f"{ex.get(21)!s:>7}/{ex.get(63)!s:>7}/{ex.get(126)!s:>7}")


if __name__ == "__main__":
    main()
