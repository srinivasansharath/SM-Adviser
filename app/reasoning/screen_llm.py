"""Stage-4 LLM deep-dive over the screener shortlist (BUILD_PLAN Phase 6).

The deterministic funnel ranks candidates on the numbers; this adds the qualitative layer a buy
decision actually needs: is the high ROE/growth DURABLE or a cyclical/one-off peak, what's the real
structural tailwind, and — most usefully — a written THESIS plus MEASURABLE exit_if conditions in
the exact shape as the holdings theses, so a name you act on drops straight into the existing engine.

Runs on the shortlist only (cheap, weekly). Falls back to empty (deterministic ranking stands) when
there's no LLM or the call fails, so tests stay hermetic and the weekly run stays robust. Advisory
only — it assesses and explains, it never says "buy"; thesis text is bounded-language enforced.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable

from ..safety.guardrails import enforce_bounded_language
from .llm import LLMClient

_VERDICTS = {"strong", "watch", "avoid"}
_CONVICTIONS = {"high", "medium", "low"}

_SYSTEM = (
    "You are an equity analyst assessing LONG-TERM (1-4 year) buy candidates for a watchlist. For "
    "each stock you receive its quantitative profile (quality / growth / durability / valuation "
    "metrics and a composite score already computed by a deterministic screen). Judge, using the "
    "numbers and only well-established knowledge of the company: (1) whether the quality and growth "
    "look DURABLE or a cyclical / one-off peak; (2) the real structural or sector tailwind, if any "
    "(else 'none'); (3) whether the valuation is sane for the growth; (4) the main risks. Then write "
    "a concise THESIS (why a long-term investor might own it) and EXIT_IF conditions — MEASURABLE "
    "things that would break the thesis, e.g. 'ROE falls below 15% for two years', 'promoter pledge "
    "rises above 25%', 'revenue growth stalls below 8%'. Assign a verdict: 'strong' (numbers and "
    "story both support), 'watch' (mixed / needs monitoring), 'avoid' (metrics flatter a weak, "
    "cyclical or risky business). Base every claim ONLY on the provided metrics and well-established "
    "facts; do NOT invent recent specifics (orders, results, deals) you cannot verify. This is "
    "DECISION SUPPORT, not investment advice: use measured language, never guarantees or 'must buy'. "
    "Output STRICT JSON only, no prose outside it."
)
_SCHEMA = ('{"<SYMBOL>": {"verdict": "strong|watch|avoid", "conviction": "high|medium|low", '
           '"bucket": "Compounder|GARP|Tailwind|Turnaround", "thesis": "<=2 sentences", '
           '"exit_if": ["measurable condition", "..."], "tailwind": "<sector tailwind or none>", '
           '"risks": ["risk", "..."]}}')

_PROFILE_FIELDS = (
    "roe", "roe_5y", "roe_3y", "roce", "sales_cagr_5y", "profit_cagr_5y", "pe", "debt_to_equity",
    "promoter_holding", "promoter_pledge", "market_cap", "dividend_yield",
)


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


def _profile(cand: dict) -> dict:
    """Compact quantitative profile handed to the model for one candidate."""
    data = cand.get("data") or {}
    prof = {"symbol": cand.get("symbol"), "composite": cand.get("composite"),
            "buckets": cand.get("buckets"), "peg": cand.get("peg")}
    for f in _PROFILE_FIELDS:
        if data.get(f) is not None:
            prof[f] = data[f]
    return prof


def _clean(sym: str, v: dict) -> dict | None:
    if not isinstance(v, dict):
        return None
    thesis, violations = enforce_bounded_language(str(v.get("thesis") or "")[:400])
    exit_if = [str(x)[:160] for x in (v.get("exit_if") or []) if str(x).strip()][:5]
    risks = [str(x)[:160] for x in (v.get("risks") or []) if str(x).strip()][:5]
    verdict = str(v.get("verdict") or "").lower()
    conviction = str(v.get("conviction") or "").lower()
    return {
        "verdict": verdict if verdict in _VERDICTS else "watch",
        "conviction": conviction if conviction in _CONVICTIONS else "medium",
        "bucket": str(v.get("bucket") or "")[:24],
        "thesis": thesis,
        "exit_if": exit_if,
        "tailwind": str(v.get("tailwind") or "")[:160],
        "risks": risks,
        "violations": len(violations),
    }


def deep_dive(llm: LLMClient | None, candidates: list[dict], max_tokens: int | None = None,
              limit: int = 15, retries: int = 3, retry_delay: float = 4.0,
              sleep: Callable[[float], None] | None = None) -> dict:
    """Return {"assessments": {symbol: {...}}, "usage": LLMResponse|None, "prompt": str}.
    Assesses the top `limit` candidates; empty (deterministic ranking stands) with no LLM or on failure.
    The one LLM call is the unattended weekly run's flakiest step, so a transient failure (network
    blip, empty/unparseable body) is retried with backoff before giving up."""
    if not llm or not candidates:
        return {"assessments": {}, "usage": None, "prompt": ""}

    picks = candidates[:limit]
    # Each stock's assessment (thesis + exit_if + risks) is ~500-700 output tokens; too small a
    # budget truncates the JSON mid-object and the whole parse fails. Scale to the batch size.
    if max_tokens is None:
        max_tokens = min(16000, 700 * len(picks) + 1000)
    payload = [_profile(c) for c in picks]
    prompt = (
        "Assess each long-term buy candidate below from its quantitative profile.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Return STRICT JSON exactly matching this schema:\n{_SCHEMA}"
    )
    sleeper = sleep or time.sleep
    parsed: dict = {}
    resp = None
    for attempt in range(1, retries + 1):
        try:
            resp = llm.complete(_SYSTEM, prompt, max_tokens=max_tokens)
            parsed = _parse_json(resp.text)
        except Exception:
            resp, parsed = None, {}
        if parsed:
            break
        if attempt < retries:
            sleeper(retry_delay * attempt)   # linear backoff: 4s, 8s, ...
    if not parsed:
        # Deterministic ranking stands; the weekly run doesn't fail over a missing LLM pass.
        return {"assessments": {}, "usage": resp, "prompt": prompt}

    assessments: dict = {}
    for sym, v in (parsed or {}).items():
        cleaned = _clean(sym, v)
        if cleaned:
            assessments[sym] = cleaned
    return {"assessments": assessments, "usage": resp, "prompt": prompt}
