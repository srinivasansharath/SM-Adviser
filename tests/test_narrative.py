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


def test_unparseable_narrative_is_reported_not_swallowed():
    """A truncated response used to yield holdings={} with violations=[] — the run then reported
    `narrative: true, violations: 0` for an empty result. Silent degradation that looks like
    success is the failure mode this whole pipeline exists to avoid."""
    from app.reasoning.llm import MockLLM
    from app.reasoning.narrative import generate_narrative

    data = {"run_date": "2026-09-26", "portfolio": {}, "holdings": [{"symbol": "INFY"}]}
    truncated = '{"executive": "Portfolio is mixed.", "holdings": {"INFY": {"thesis_stat'
    out = generate_narrative(MockLLM(truncated), data, {"INFY": {}}, {}, {})

    assert out["parsed_ok"] is False
    assert out["holdings"] == {}
    assert any("did not parse" in v for v in out["violations"]), "failure must be visible"


def test_valid_narrative_reports_parsed_ok():
    import json

    from app.reasoning.llm import MockLLM
    from app.reasoning.narrative import generate_narrative

    data = {"run_date": "2026-09-26", "portfolio": {}, "holdings": [{"symbol": "INFY"}]}
    good = json.dumps({"executive": "Fine.", "holdings": {
        "INFY": {"thesis_status": "none", "note": "n", "thesis_feedback": "write one"}}})
    out = generate_narrative(MockLLM(good), data, {"INFY": {}}, {}, {})
    assert out["parsed_ok"] is True
    assert out["holdings"]["INFY"]["thesis_feedback"] == "write one"


def test_token_budget_scales_with_holding_count():
    """Coaching added a second field per holding, so a fixed cap truncated larger portfolios."""
    import json

    from app.reasoning.llm import MockLLM
    from app.reasoning.narrative import generate_narrative

    seen = {}

    class Spy(MockLLM):
        def complete(self, system, prompt, max_tokens=1500):
            seen["max_tokens"] = max_tokens
            return super().complete(system, prompt, max_tokens=max_tokens)

    good = json.dumps({"executive": "x", "holdings": {}})
    for n in (1, 7, 20):
        data = {"run_date": "d", "portfolio": {},
                "holdings": [{"symbol": f"S{i}"} for i in range(n)]}
        generate_narrative(Spy(good), data, {}, {}, {})
        assert seen["max_tokens"] >= 1000 + 700 * n or seen["max_tokens"] == 4000
    assert seen["max_tokens"] > 4000, "a 20-holding portfolio must get more than the old fixed cap"
