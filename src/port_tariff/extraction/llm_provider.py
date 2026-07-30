"""
LLM provider abstraction.

The extraction layer depends on this small interface, NOT on any specific
vendor SDK. This keeps the system provider-agnostic: Gemini is the default
(per the test's recommendation), but the same extraction code runs against any
provider that implements `generate`.

It also makes the whole pipeline testable OFFLINE: tests inject a
`ScriptedLLM` that returns canned responses, so extraction logic can be
verified without network access or an API key.

Uses the current `google-genai` SDK (the older `google-generativeai` package
is end-of-life).
"""

from __future__ import annotations

import os
from typing import Protocol

# Current default model. 2.0-flash was retired by Google; 2.5-flash is the
# current fast, low-cost generation. Overridable via constructor / env var.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class LLMProvider(Protocol):
    """Minimal contract the extraction layer needs from any LLM."""

    def generate(self, prompt: str) -> str:
        """Return the model's text response for a prompt."""
        ...


class GeminiProvider:
    """Google Gemini implementation using the modern google-genai SDK.

    Imported lazily so the package works (and tests run) without the SDK
    installed. A real API key is read from GEMINI_API_KEY (or passed in) --
    never hardcoded, never logged.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model_name = model or os.environ.get(
            "GEMINI_MODEL", DEFAULT_GEMINI_MODEL
        )
        self.temperature = temperature
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "No Gemini API key. Set GEMINI_API_KEY or pass api_key=..."
            )
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "google-genai is required for GeminiProvider. "
                "Install with: pip install google-genai"
            ) from exc

        self._genai = genai
        self._client = genai.Client(api_key=self._api_key)

    def generate(self, prompt: str) -> str:  # pragma: no cover - needs network
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=self.temperature),
        )
        return response.text


class ScriptedLLM:
    """Deterministic offline LLM for tests.

    Returns pre-scripted responses in order, or a single fixed response.
    Lets us validate the entire extraction + parsing + calculation pipeline
    with zero network dependency.
    """

    def __init__(self, responses: list[str] | str) -> None:
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self._calls = 0

    def generate(self, prompt: str) -> str:
        if self._calls >= len(self._responses):
            return self._responses[-1]
        resp = self._responses[self._calls]
        self._calls += 1
        return resp

    @property
    def call_count(self) -> int:
        return self._calls
