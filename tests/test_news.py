from app.analytics.news import has_negative_news, score_news_risk
from app.connectors.news import BSEAnnouncements, MockNews, _is_material, get_news
from app.reasoning.llm import MockLLM
from app.reasoning.news_llm import assess_news
from app.reasoning.scoring import score_holding


def test_assess_news_llm_pass():
    news_data = {"TCS": [{"material": True, "subcategory": "Dividend", "headline": "Board approves dividend"}]}
    llm = MockLLM('{"TCS": {"news_risk": 82, "note": "dividend is shareholder-positive"}}')
    out = assess_news(llm, news_data)
    assert out["scores"]["TCS"]["news_risk"] == 82.0
    assert "dividend" in out["scores"]["TCS"]["note"].lower()


def test_assess_news_empty_when_no_llm_or_no_material():
    assert assess_news(None, {"X": []})["scores"] == {}
    assert assess_news(MockLLM(), {"X": [{"material": False}]})["scores"] == {}   # early-out, LLM not called


def test_score_holding_llm_news_override_wins():
    # A negative deterministic signal is overridden by the LLM's direction-aware score.
    r = score_holding({"symbol": "X", "ltp": 10, "weight_pct": 5}, None, None, None, None, None, {},
                      news=[{"material": True, "subcategory": "Resignation", "headline": "resign"}],
                      news_risk_override=90.0)
    assert r["subscores"]["news_risk"] == 90.0


def test_news_risk_score():
    assert score_news_risk(None) is None
    assert score_news_risk([{"material": False, "headline": "x"}]) is None   # nothing material
    neg = [{"material": True, "subcategory": "Resignation of Director", "headline": "Resignation of Director"}]
    pos = [{"material": True, "subcategory": "Dividend", "headline": "Board approves Dividend"}]
    assert score_news_risk(neg) < 65          # negative event drags it down
    assert score_news_risk(pos) > 65          # positive lifts it


def test_news_recency_weighting():
    import datetime as dt
    today = dt.date(2026, 7, 15)
    recent = [{"material": True, "subcategory": "Resignation", "headline": "resign", "date": "2026-07-14"}]
    old = [{"material": True, "subcategory": "Resignation", "headline": "resign", "date": "2026-06-16"}]
    assert score_news_risk(recent, today) < score_news_risk(old, today)   # recent negative bites more
    assert has_negative_news(recent, today=today)          # recent -> attention
    assert not has_negative_news(old, today=today)         # 29d old -> stale, no attention


def test_has_negative_news():
    assert has_negative_news([{"material": True, "subcategory": "Resignation", "headline": "resign"}])
    assert has_negative_news([{"material": True, "subcategory": "Fund Raising", "headline": "fund raising"}])
    assert not has_negative_news([{"material": True, "subcategory": "Dividend", "headline": "dividend"}])


def test_mock_news():
    n = get_news("mock")
    items = n.get_announcements("TCS")
    assert items and items[0]["material"] and items[0]["source"] == "mock"


def test_materiality_flags_events_not_noise():
    assert _is_material("Board Meeting", "Board Meeting", "consider results", None)
    assert _is_material("Company Update", "Change in Management", "", None)
    assert _is_material("Corp. Action", "Dividend", "board approves dividend", None)
    assert _is_material("", "", "", "1")                              # BSE critical flag
    # noise stays non-material even though it's a Regulation 30 filing
    assert not _is_material("Company Update", "Newspaper Publication",
                            "Announcement under Regulation 30 (LODR)-Newspaper Publication", None)
    assert not _is_material("Insider Trading / SAST", "Closure of Trading Window",
                            "Closure of Trading Window", None)


def test_bse_unknown_symbol_returns_empty():
    # No network: an unmapped symbol short-circuits before any request.
    assert BSEAnnouncements().get_announcements("ZZ_NOT_A_SYMBOL") == []
