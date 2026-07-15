from app.connectors.news import BSEAnnouncements, MockNews, _is_material, get_news


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
