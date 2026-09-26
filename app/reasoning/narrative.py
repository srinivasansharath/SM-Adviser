"""Generate the LLM narrative from the scored portfolio, with guardrails + audit."""

from __future__ import annotations

import json
import re

from ..safety.guardrails import enforce_bounded_language
from .llm import LLMClient, LLMResponse
from .prompts import SYSTEM_PROMPT, build_user_prompt


def _parse_json(text: str) -> tuple[dict, bool]:
    """Best-effort parse of the model's JSON (tolerates markdown fences / trailing prose).

    Returns (parsed, ok). `ok` matters: this used to fall back to an empty holdings dict with no
    signal, so a truncated or malformed response produced a run that reported
    `narrative: true, violations: 0` while containing no per-holding analysis at all. Silent
    degradation that looks like success is worse than an error.
    """
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t), True
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0)), True
            except json.JSONDecodeError:
                pass
    return {"executive": t[:500], "holdings": {}}, False


def generate_narrative(llm: LLMClient, data: dict, theses: dict, fundamentals_data: dict | None,
                       news_data: dict | None = None, max_tokens: int | None = None) -> dict:
    """Return {"executive", "holdings": {sym: {thesis_status, note, thesis_feedback}}, "usage",
    "violations"}. thesis_feedback coaches the user: what to write when a holding has no thesis,
    or the biggest gap in one they have written."""
    prompt = build_user_prompt(data, theses, fundamentals_data, news_data)
    # Output scales with holdings: each now carries a note AND thesis_feedback. A fixed 4000 cap
    # truncated the JSON mid-structure once coaching was added, which the parser then swallowed.
    if max_tokens is None:
        n = len(data.get("holdings") or []) or 1
        max_tokens = max(4000, 1000 + 700 * n)
    resp: LLMResponse = llm.complete(SYSTEM_PROMPT, prompt, max_tokens=max_tokens)
    parsed, parsed_ok = _parse_json(resp.text)

    violations: list[str] = []
    if not parsed_ok:
        violations.append(
            "narrative JSON did not parse — per-holding analysis is empty "
            "(model output was likely truncated; raise max_tokens)")
    exec_txt, v = enforce_bounded_language(parsed.get("executive", ""))
    violations += v
    parsed["executive"] = exec_txt

    holdings = parsed.get("holdings") or {}
    for sym, h in holdings.items():
        note, v = enforce_bounded_language((h or {}).get("note", ""))
        violations += v
        if isinstance(h, dict):
            h["note"] = note
            # Coaching is still advice about a holding, so it goes through the same guardrail.
            fb, fv = enforce_bounded_language((h.get("thesis_feedback") or ""))
            violations += fv
            h["thesis_feedback"] = fb
    parsed["holdings"] = holdings

    return {
        "executive": parsed.get("executive", ""),
        "holdings": holdings,
        "usage": resp,
        "violations": violations,
        "parsed_ok": parsed_ok,
    }
