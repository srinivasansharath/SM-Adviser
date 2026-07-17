from datetime import date

from app.jobs import weekly_screen
from app.reasoning.llm import MockLLM
from app.reasoning.screen_llm import deep_dive
from app.storage.models import Candidate, LLMCall

_CAND = {"symbol": "SOLARINDS", "composite": 86.0, "buckets": ["Compounder"], "peg": 1.2,
         "data": {"roe": 30, "roe_5y": 28, "sales_cagr_5y": 22, "profit_cagr_5y": 25, "pe": 45}}

_CANNED = ('{"SOLARINDS": {"verdict": "strong", "conviction": "high", "bucket": "Compounder", '
           '"thesis": "Dominant explosives maker with a durable, high-return franchise.", '
           '"exit_if": ["ROE falls below 18% for two years", "defence order pipeline dries up"], '
           '"tailwind": "defence and infra capex", "risks": ["input-cost swings"]}}')


def test_deep_dive_parses_and_cleans():
    out = deep_dive(MockLLM(_CANNED), [_CAND])
    a = out["assessments"]["SOLARINDS"]
    assert a["verdict"] == "strong" and a["conviction"] == "high"
    assert a["bucket"] == "Compounder"
    assert len(a["exit_if"]) == 2 and "ROE" in a["exit_if"][0]
    assert "explosives" in a["thesis"]
    assert out["usage"] is not None


def test_deep_dive_empty_without_llm_or_candidates():
    assert deep_dive(None, [_CAND])["assessments"] == {}
    assert deep_dive(MockLLM(_CANNED), [])["assessments"] == {}


def test_deep_dive_bad_verdict_defaults_to_watch():
    canned = '{"X": {"verdict": "definitely-buy", "conviction": "insane", "thesis": "ok", "exit_if": []}}'
    a = deep_dive(MockLLM(canned), [{"symbol": "X", "data": {}}])["assessments"]["X"]
    assert a["verdict"] == "watch" and a["conviction"] == "medium"   # invalid enums normalised


def test_deep_dive_survives_llm_failure():
    calls = {"n": 0}

    class _Boom(MockLLM):
        def complete(self, system, prompt, max_tokens=1500):
            calls["n"] += 1
            raise TimeoutError("down")
    # Degrades to empty after retrying (no crash); sleep stubbed so the test doesn't wait.
    out = deep_dive(_Boom(), [_CAND], retries=3, sleep=lambda _: None)
    assert out["assessments"] == {} and calls["n"] == 3


def test_deep_dive_retries_then_succeeds():
    _CANNED = '{"X": {"verdict": "watch", "conviction": "low", "thesis": "ok", "exit_if": []}}'

    class _Flaky(MockLLM):
        def __init__(self):
            super().__init__(_CANNED)
            self.n = 0

        def complete(self, system, prompt, max_tokens=1500):
            self.n += 1
            if self.n == 1:
                raise TimeoutError("blip")
            return super().complete(system, prompt, max_tokens)

    out = deep_dive(_Flaky(), [{"symbol": "X", "data": {}}], retries=3, sleep=lambda _: None)
    assert out["assessments"]["X"]["verdict"] == "watch"    # recovered on the 2nd attempt


# --- wiring into the weekly run ---------------------------------------------------------------
class _Uni(weekly_screen.UniverseConnector):
    name = "t"

    def get_universe(self):
        return [{"symbol": "SOLARINDS", "roce": 35, "market_cap": 90000,
                 "profit_growth_qtr": 20, "sales_growth_qtr": 18, "pe": 45}]


class _Fund(weekly_screen.FundamentalsConnector):
    name = "tf"

    def get_fundamentals(self, symbol, exchange="NSE"):
        return {"roe": 30, "roe_5y": 28, "roe_3y": 29, "sales_cagr_5y": 22, "profit_cagr_5y": 25,
                "debt_to_equity": 0.2, "promoter_holding": 73, "promoter_pledge": 0}


def test_weekly_run_attaches_llm_and_audits_cost(session_factory):
    from app.connectors.market_data import MockMarketData

    rd = date(2026, 7, 16)
    summary = weekly_screen.run(
        universe=_Uni(), fundamentals=_Fund(), market_data=MockMarketData(),
        session_factory=session_factory, run_date=rd, config={}, llm=MockLLM(_CANNED),
    )
    assert summary["assessed"] == 1
    assert summary["top"][0]["verdict"] == "strong"
    with session_factory() as s:
        cand = s.query(Candidate).filter_by(run_date=rd, symbol="SOLARINDS").one()
        assert cand.detail["llm"]["thesis"]                          # assessment persisted on the row
        calls = s.query(LLMCall).filter_by(run_date=rd).all()
        assert calls and calls[0].cost is not None                   # token cost audited
