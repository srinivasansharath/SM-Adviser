"""LLM client abstraction — swappable like the connectors (Anthropic + mock for tests)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Daily narrative uses Sonnet (cheap, strong); weekly deep-dives can pass Opus.
DEFAULT_MODEL = "claude-sonnet-5"


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> LLMResponse:
        ...


class AnthropicClient(LLMClient):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._api_key = api_key
        self.model = model
        self._client = None

    def _c(self):  # pragma: no cover - network
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> LLMResponse:  # pragma: no cover - network
        msg = self._c().messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
        )


class MockLLM(LLMClient):
    name = "mock"
    model = "mock"

    def __init__(self, canned: str | None = None):
        self._canned = canned or (
            '{"executive": "Portfolio is heavily concentrated; two holdings on watch.",'
            ' "holdings": {}}'
        )

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> LLMResponse:
        return LLMResponse(text=self._canned, model="mock", input_tokens=100, output_tokens=50)


def get_llm(settings, model: str = DEFAULT_MODEL) -> LLMClient | None:
    """Return an Anthropic client if a key is configured, else None (scoring still works)."""
    key = getattr(settings, "anthropic_api_key", None)
    return AnthropicClient(key, model=model) if key else None
