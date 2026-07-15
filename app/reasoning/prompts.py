"""Prompt templates + guardrails for the narrative layer."""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You are a cautious portfolio risk analyst for an Indian (NSE/BSE) investor's \
PERSONAL, read-only decision-support tool. Non-negotiable rules:

- Decision support only — NOT investment advice. Never guarantee outcomes. No "will go up/down", \
no "for sure", no promised price targets, no "multibagger". Bounded language only.
- Use only these action labels: Hold, Watch, Accumulate Candidate, Trim Candidate, Exit Candidate.
- A falling PRICE is not a sell signal; falling FUNDAMENTALS or a broken THESIS are. Explicitly \
distinguish a temporary price dip (hold a quality business) from genuine thesis impairment (exit).
- Judge each holding's thesis by evaluating its exit_if conditions against the evidence provided \
(scores, technicals, fundamentals, and recent_filings — official BSE corporate announcements). A \
material filing (management/auditor change, credit-rating action, litigation, SEBI/exchange action, \
fund-raising/dilution, results) is first-class evidence and can trigger an exit_if condition — but \
do not overreact to a single routine filing. If the thesis text is missing, say confidence is limited.
- Tie every statement to the given evidence. Be concise, specific, and honest about uncertainty.
- Output STRICT JSON only, matching the requested schema. No text outside the JSON."""

_SCHEMA = (
    '{"executive": "<=3 sentences: portfolio state + biggest risks", '
    '"holdings": {"<SYMBOL>": {"thesis_status": "intact|watch|impaired", '
    '"note": "1-2 sentences tying the score, fundamentals and thesis; note which exit_if conditions '
    '(if any) are triggered"}}}'
)


def _holding_view(r: dict, meta: dict, fund: dict, news: list | None = None) -> dict:
    from ..analytics.news import material_items

    filings = [
        f"{i.get('date','')} {i.get('subcategory') or i.get('category') or ''}: {i.get('headline','')}"
        for i in material_items(news)
    ][:6]
    return {
        "symbol": r["symbol"],
        "classification": r.get("classification"),
        "confidence": r.get("confidence"),
        "weight_pct": r.get("weight_pct"),
        "ret_20d": r.get("ret_20d"),
        "rel_strength_vs_nifty": r.get("rel_strength"),
        "rsi": r.get("rsi"),
        "drawdown": r.get("drawdown"),
        "above_200dma": r.get("above_200dma"),
        "pe": fund.get("pe"),
        "roce": fund.get("roce"),
        "roe": fund.get("roe"),
        "thesis": meta.get("thesis") or "(not provided)",
        "conviction": meta.get("conviction"),
        "exit_if": meta.get("exit_if") or [],
        "recent_filings": filings,
    }


def build_user_prompt(data: dict, theses: dict, fundamentals_data: dict | None,
                      news_data: dict | None = None) -> str:
    holdings = [
        _holding_view(r, (theses or {}).get(r["symbol"]) or {},
                      (fundamentals_data or {}).get(r["symbol"]) or {},
                      (news_data or {}).get(r["symbol"]))
        for r in data["holdings"]
    ]
    payload = {"as_of": data["run_date"], "portfolio": data["portfolio"], "holdings": holdings}
    return (
        "Today's scored portfolio (a deterministic engine already classified each holding). "
        "Evaluate each holding's thesis (intact/watch/impaired) by checking its exit_if conditions "
        "against the evidence, then write a portfolio executive summary.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Return STRICT JSON exactly matching this schema:\n{_SCHEMA}"
    )
