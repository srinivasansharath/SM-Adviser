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


# --- price-risk / low-base guards (EMMVEE regression: pre-IPO CAGRs defeated three guards) ---

def _candles(n, lo=100.0, hi=100.0):
    """n sessions; last 126 span lo..hi so high_low_ratio is controllable."""
    out = []
    for i in range(n):
        px = lo if i % 2 else hi
        out.append({"date": f"d{i}", "open": px, "high": px, "low": px, "close": px, "volume": 100000})
    return out


def test_price_helpers():
    from app.analytics.screening import high_low_ratio, price_history_days
    assert price_history_days(_candles(30)) == 30
    assert price_history_days([]) is None
    assert high_low_ratio(_candles(130, lo=50.0, hi=100.0)) == 2.0
    assert high_low_ratio(None) is None


def test_recent_listing_floors_durability_despite_claimed_history():
    """The EMMVEE case: provider reports 5y ROE from pre-IPO accounts, but only ~120 sessions
    of real trading exist. Durability must NOT reward that."""
    from app.analytics.screening import score_durability
    data = {"roe_5y": 51.0, "roe_3y": 56.0, "roe": 51.1,
            "sales_cagr_5y": 64.0, "profit_cagr_5y": 158.0}
    assert score_durability(data) > 90                      # old behaviour, long history assumed
    assert score_durability({**data, "price_history_days": 120}) == 25.0   # recent listing -> floored


def test_recent_listing_cannot_be_a_compounder():
    from app.analytics.screening import buckets
    data = {"roe_5y": 51.0, "roe_3y": 56.0, "roe": 51.1, "profit_cagr_5y": 158.0, "promoter_pledge": 0.0}
    assert "Compounder" in buckets(data)
    assert "Compounder" not in buckets({**data, "price_history_days": 120})


def test_peg_growth_denominator_is_capped():
    """A 158% low-base CAGR must not make a rich multiple look free."""
    from app.analytics.screening import peg, score_valuation
    data = {"pe": 55.0, "profit_cagr_5y": 158.0}
    assert peg(data) == round(55.0 / 40.0, 2)               # capped at 40, not 55/158=0.35
    assert score_valuation(data) <= 55.0                    # and richness caps the score


def test_rich_pe_cannot_score_top_valuation():
    from app.analytics.screening import score_valuation
    assert score_valuation({"pe": 18.0, "profit_cagr_5y": 30.0}) > 55.0   # sane multiple unaffected
    assert score_valuation({"pe": 80.0, "profit_cagr_5y": 158.0}) <= 55.0


def test_volatility_lowers_safety_and_raises_caution():
    from app.analytics.screening import cautions, score_safety
    calm = {"debt_to_equity": 0.1, "promoter_pledge": 0.0, "high_low_ratio_6m": 1.3}
    wild = {**calm, "high_low_ratio_6m": 2.8}
    assert score_safety(calm) > score_safety(wild)
    assert any("volatile" in c for c in cautions(wild))
    assert not any("volatile" in c for c in cautions(calm))


def test_cautions_are_not_exclusions():
    """Cautions surface risk without silently dropping the name (red_flags do the excluding)."""
    from app.analytics.screening import score_candidate
    r = score_candidate({"symbol": "X", "pe": 60.0, "profit_cagr_5y": 158.0,
                         "price_history_days": 120, "high_low_ratio_6m": 2.5,
                         "median_daily_value_cr": 5.0, "debt_to_equity": 0.1, "promoter_pledge": 0.0})
    assert r["excluded"] is False
    assert len(r["cautions"]) >= 3
