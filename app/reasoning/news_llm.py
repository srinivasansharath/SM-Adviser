"""LLM sentiment pass over corporate filings -> the news_risk sub-score.

Judges filings holistically — direction (rating upgrade vs downgrade), materiality, and multiple
events weighed together — which keyword matching can't. Runs BEFORE deterministic scoring (scoring
consumes its output). Falls back to the deterministic `score_news_risk` when there's no LLM or it
fails, so tests stay hermetic and daily runs stay robust.
"""

from __future__ import annotations

import json
import re

from ..analytics.news import material_items
from .llm import LLMClient

_SYSTEM = (
    "You are a risk assessor reading a company's recent official stock-exchange (BSE) filings. "
    "For each stock output a news_risk score 0-100: 100 = clearly benign/positive, 60 = "
    "routine/neutral, 30 = cautionary, 0 = serious negative (fraud, default, SEBI/regulatory "
    "action, auditor resignation, major litigation, heavy dilution, mass management exits). Weigh "
    "DIRECTION and MATERIALITY holistically — a rating upgrade or a value-accretive order win is "
    "positive; a downgrade, dilutive fundraise, governance red flag or an exchange 'clarification "
    "sought' is negative; routine intimations sit near 60. WEIGHT RECENCY: a filing from the last "
    "few days matters far more than one from weeks ago, which is likely already reflected in the "
    "price. Base it ONLY on the filings provided (each has a date); never invent facts. This is a "
    "decision-support risk score, not investment advice. Output STRICT JSON only, no prose outside it."
)
_SCHEMA = '{"<SYMBOL>": {"news_risk": <integer 0-100>, "note": "<=1 sentence explaining the score"}}'


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def assess_news(llm: LLMClient | None, news_data: dict | None, max_tokens: int = 1200) -> dict:
    """Return {"scores": {symbol: {news_risk, note}}, "usage": LLMResponse|None, "prompt": str}.
    Only holdings with material filings are scored; empty otherwise."""
    if not llm or not news_data:
        return {"scores": {}, "usage": None, "prompt": ""}

    payload = {}
    for sym, items in news_data.items():
        mats = material_items(items)
        if mats:
            payload[sym] = [
                {"date": i.get("date"), "type": i.get("subcategory") or i.get("category"),
                 "headline": i.get("headline")}
                for i in mats[:8]
            ]
    if not payload:
        return {"scores": {}, "usage": None, "prompt": ""}

    prompt = (
        "Recent MATERIAL filings per holding. Score each stock's news_risk.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Return STRICT JSON exactly matching this schema:\n{_SCHEMA}"
    )
    resp = llm.complete(_SYSTEM, prompt, max_tokens=max_tokens)
    parsed = _parse_json(resp.text)

    scores = {}
    for sym, v in (parsed or {}).items():
        if isinstance(v, dict) and isinstance(v.get("news_risk"), (int, float)):
            score = max(0.0, min(100.0, float(v["news_risk"])))
            scores[sym] = {"news_risk": round(score, 1), "note": str(v.get("note") or "")[:220]}
    return {"scores": scores, "usage": resp, "prompt": prompt}
