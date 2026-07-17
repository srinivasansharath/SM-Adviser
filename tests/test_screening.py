from app.analytics.screening import (
    buckets,
    coarse_score,
    composite,
    is_financial,
    peg,
    red_flags,
    score_candidate,
    score_durability,
    score_growth,
    score_quality,
    score_safety,
    score_valuation,
)

# Representative real-shaped rows (from live screener parses).
TCS = {  # quality compounder, cheap-ish
    "symbol": "TCS", "roe": 51.8, "roe_5y": 49.0, "roe_3y": 52.0, "roce": 63.0,
    "sales_cagr_5y": 10.0, "profit_cagr_5y": 9.0, "pe": 14.8, "debt_to_equity": 0.11,
    "promoter_holding": 71.77, "promoter_pledge": 0.0, "median_daily_value_cr": 200.0,
}
JPPOWER = {  # governance red flag: 73% pledge
    "symbol": "JPPOWER", "roe": 3.6, "roe_5y": 5.0, "roce": 6.97, "profit_cagr_5y": 24.0,
    "sales_cagr_5y": 11.0, "pe": 25.8, "debt_to_equity": 0.27, "promoter_holding": 24.0,
    "promoter_pledge": 73.0, "median_daily_value_cr": 40.0,
}
HDFCBANK = {  # financial: no promoter / no D-E, quality must come from ROE
    "symbol": "HDFCBANK", "roe": 13.6, "roe_5y": 15.0, "roce": 7.02, "sales_cagr_5y": 22.0,
    "profit_cagr_5y": 19.0, "pe": 16.5, "debt_to_equity": None, "promoter_holding": None,
    "promoter_pledge": 0.0, "median_daily_value_cr": 500.0,
}


def test_is_financial_detection():
    assert is_financial(HDFCBANK) is True          # None D/E + None promoter + ROE present
    assert is_financial(TCS) is False
    assert is_financial({"sector": "Private Sector Bank", "roe": 12}) is True


def test_quality_scores_track_roe_and_skip_roce_for_banks():
    assert score_quality(TCS) > 80                 # ROE ~50, consistent
    assert score_quality(JPPOWER) < 40             # ROE ~4
    # Bank quality is ROE-only (ROCE 7 would drag it if wrongly included).
    assert score_quality(HDFCBANK) is not None and score_quality(HDFCBANK) > 45


def test_growth_and_valuation():
    assert score_growth({"sales_cagr_5y": 25, "profit_cagr_5y": 25}) > 85
    assert score_growth({"sales_cagr_5y": 2, "profit_cagr_5y": 1}) < 20
    assert score_growth({"pe": 20}) is None        # no CAGR -> undefined
    # PEG-led valuation: cheap growth scores higher than pricey no-growth.
    assert score_valuation({"pe": 15, "profit_cagr_5y": 25}) > score_valuation({"pe": 60, "profit_cagr_5y": 5})


def test_durability_penalises_no_history_and_spikes():
    # No multi-year track record -> demoted (low), NOT renormalised away.
    assert score_durability({"roe": 160}) == 25.0
    # A steady compounder beats a one-year spike with the same latest ROE.
    steady = score_durability({"roe": 26, "roe_3y": 25, "roe_5y": 24, "sales_cagr_5y": 18, "profit_cagr_5y": 20})
    spike = score_durability({"roe": 160, "roe_3y": 20, "roe_5y": 8, "sales_cagr_5y": 5, "profit_cagr_5y": 4})
    assert steady > spike
    assert steady > 70

    # In the full composite, a no-track-record freak must rank below a durable compounder even if
    # its latest-year numbers look spectacular.
    freak = {"symbol": "FREAK", "roe": 165, "roce": 165, "pe": 6, "promoter_pledge": 0,
             "sales_growth_qtr": 2900, "profit_growth_qtr": 2900, "median_daily_value_cr": 50}
    assert composite(score_candidate(steady_row())["subscores"]) > composite(score_candidate(freak)["subscores"])


def steady_row():
    return {"symbol": "STEADY", "roe": 26, "roe_3y": 25, "roe_5y": 24, "roce": 30,
            "sales_cagr_5y": 16, "profit_cagr_5y": 18, "pe": 30, "promoter_pledge": 0,
            "median_daily_value_cr": 50}


def test_peg():
    assert peg({"pe": 20, "profit_cagr_5y": 20}) == 1.0
    assert peg({"pe": 20, "profit_cagr_5y": 0}) is None     # undefined for non-positive growth
    assert peg({"pe": -5, "profit_cagr_5y": 10}) is None    # loss-maker


def test_safety_skips_leverage_for_financials():
    s_bank = score_safety(HDFCBANK)     # only pledge counts (D/E skipped)
    assert s_bank == 100.0              # pledge 0 -> full
    assert score_safety({"debt_to_equity": 0.1, "promoter_pledge": 0}) > 90
    assert score_safety({"debt_to_equity": 2.0, "promoter_pledge": 40}) < 30


def test_composite_renormalises_over_present():
    # Missing sub-scores are excluded, not treated as zero.
    only_q = composite({"quality": 80, "growth": None, "valuation": None, "safety": None, "liquidity": None})
    assert only_q == 80.0
    assert composite({"quality": None, "growth": None}) is None


def test_red_flags_hard_gates():
    assert any("pledge" in f for f in red_flags(JPPOWER))                       # 73% pledge
    assert red_flags(TCS) == []                                                 # clean
    assert any("illiquid" in f for f in red_flags({"median_daily_value_cr": 0.3}))
    assert any("leverage" in f for f in red_flags({"debt_to_equity": 5.0}))
    assert any("chronic" in f for f in red_flags({"profit_cagr_5y": -4, "roe": 2}))
    # A configured stricter pledge gate catches a moderately-pledged name.
    cfg = {"screening": {"pledge_max_pct": 10}}
    assert any("pledge" in f for f in red_flags({"promoter_pledge": 15}, cfg))


def test_buckets_tagging():
    assert "Compounder" in buckets(TCS)                    # consistent high ROE, low pledge
    assert "Compounder" not in buckets(JPPOWER)            # pledged + weak ROE
    garp = {"profit_cagr_5y": 20, "pe": 18}               # PEG 0.9 -> GARP
    assert "GARP" in buckets(garp)
    # Tailwind now needs a quality floor + acceleration meaningfully above the 5y trend.
    tailwind = {"profit_growth_qtr": 40, "sales_growth_qtr": 30, "sales_cagr_5y": 10, "roce": 20}
    assert "Tailwind" in buckets(tailwind)
    # A junk micro-cap spike with no quality does NOT get tagged Tailwind anymore.
    assert "Tailwind" not in buckets({"profit_growth_qtr": 900, "sales_growth_qtr": 800, "roce": 3})


def test_score_candidate_end_to_end():
    good = score_candidate(TCS)
    assert good["excluded"] is False and good["composite"] > 65
    assert "Compounder" in good["buckets"]

    bad = score_candidate(JPPOWER)
    assert bad["excluded"] is True                         # pledge gate fired
    assert any("pledge" in f for f in bad["red_flags"])


def test_diversified_featured():
    from collections import Counter

    from app.analytics.screening import diversified_featured

    def c(sym, comp, sector):
        return {"symbol": sym, "composite": comp, "data": {"sector": sector}}

    scored = [c("A", 90, "IT"), c("B", 88, "IT"), c("C", 85, "IT"), c("D", 84, "IT"),  # IT dominates
              c("E", 80, "Banks"), c("F", 70, "Banks"),
              c("G", 60, "Pharma"), c("H", 50, "Auto"), c("I", 40, "Energy")]
    featured = diversified_featured(scored, per_sector=3, sectors=4)
    counts = Counter(x["data"]["sector"] for x in featured)
    assert counts["IT"] == 3                              # capped at per_sector (D dropped)
    assert set(counts) == {"IT", "Banks", "Pharma", "Auto"}   # top 4 sectors by best composite
    assert "Energy" not in counts                        # 5th sector excluded


def test_coarse_score_orders_quality_growth():
    strong = coarse_score({"roce": 40, "profit_growth_qtr": 30, "sales_growth_qtr": 25, "pe": 20})
    weak = coarse_score({"roce": 6, "profit_growth_qtr": -10, "sales_growth_qtr": -5, "pe": 90})
    assert strong > weak
    assert coarse_score({}) == 0.0                         # all-missing -> 0, never crashes
