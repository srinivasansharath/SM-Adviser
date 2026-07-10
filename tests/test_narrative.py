from app.reasoning.llm import MockLLM, get_llm
from app.reasoning.narrative import generate_narrative
from app.safety.guardrails import enforce_bounded_language

_DATA = {
    "run_date": "2026-07-10",
    "portfolio": {"value": 100, "total_pnl": 0, "day_change_pct": 0, "top5_pct": 50,
                  "holdings_count": 1, "attention_count": 0, "fii_net": None, "dii_net": None},
    "holdings": [
        {"symbol": "TCS", "classification": "Hold", "confidence": "High", "weight_pct": 5,
         "ret_20d": -4, "rel_strength": -8, "rsi": 45, "drawdown": -38, "above_200dma": False}
    ],
}


def test_generate_narrative_parses_json():
    canned = (
        '{"executive": "Portfolio concentrated; TCS thesis intact despite the dip.",'
        ' "holdings": {"TCS": {"thesis_status": "intact",'
        ' "note": "Strong ROCE; price weakness is a dip, not impairment."}}}'
    )
    n = generate_narrative(
        MockLLM(canned), _DATA,
        {"TCS": {"thesis": "cash machine", "conviction": "high", "exit_if": ["x"]}},
        {"TCS": {"pe": 14, "roce": 63, "roe": 52}},
    )
    assert n["executive"]
    assert n["holdings"]["TCS"]["thesis_status"] == "intact"
    assert n["usage"].input_tokens > 0


def test_narrative_handles_nonjson_gracefully():
    n = generate_narrative(MockLLM("not json at all"), _DATA, {}, {})
    assert n["executive"]  # falls back to the raw text
    assert n["holdings"] == {}


def test_bounded_language_flags_overconfidence():
    _, v = enforce_bounded_language("This stock is guaranteed to go up.")
    assert v
    _, ok = enforce_bounded_language("Thesis intact; monitor the next results.")
    assert ok == []


def test_get_llm_none_without_key():
    class S:
        anthropic_api_key = None

    assert get_llm(S()) is None
