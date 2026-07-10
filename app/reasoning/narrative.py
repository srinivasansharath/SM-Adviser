"""Generate the LLM narrative from the scored portfolio, with guardrails + audit."""

from __future__ import annotations

import json
import re

from ..safety.guardrails import enforce_bounded_language
from .llm import LLMClient, LLMResponse
from .prompts import SYSTEM_PROMPT, build_user_prompt


def _parse_json(text: str) -> dict:
    """Best-effort parse of the model's JSON (tolerates markdown fences / trailing prose)."""
    t = text.strip()
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
    return {"executive": t[:500], "holdings": {}}


def generate_narrative(llm: LLMClient, data: dict, theses: dict, fundamentals_data: dict | None,
                       max_tokens: int = 4000) -> dict:
    """Return {"executive", "holdings": {sym: {thesis_status, note}}, "usage", "violations"}."""
    prompt = build_user_prompt(data, theses, fundamentals_data)
    resp: LLMResponse = llm.complete(SYSTEM_PROMPT, prompt, max_tokens=max_tokens)
    parsed = _parse_json(resp.text)

    violations: list[str] = []
    exec_txt, v = enforce_bounded_language(parsed.get("executive", ""))
    violations += v
    parsed["executive"] = exec_txt

    holdings = parsed.get("holdings") or {}
    for sym, h in holdings.items():
        note, v = enforce_bounded_language((h or {}).get("note", ""))
        violations += v
        if isinstance(h, dict):
            h["note"] = note
    parsed["holdings"] = holdings

    return {
        "executive": parsed.get("executive", ""),
        "holdings": holdings,
        "usage": resp,
        "violations": violations,
    }
