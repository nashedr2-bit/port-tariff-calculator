"""
Natural-language query parser.

Turns free-text vessel queries into the structured VesselQuery the orchestrator
consumes. The LLM extracts explicit facts from the prose; a deterministic step
maps those facts into the engine's VesselProfile. Language understanding and
value handling are kept separate, and the parsed output is schema-validated
before use -- malformed LLM output is caught here, not downstream.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError

from ..calculation.engine import VesselProfile
from ..extraction.llm_provider import LLMProvider
from .nl_prompts import build_nl_query_prompt
from .query import VesselQuery


class NLQueryError(Exception):
    """Raised when a natural-language query cannot be parsed into a query."""


class _ParsedNLQuery(BaseModel):
    """Schema for the LLM's structured extraction of a free-text query."""

    port: str = Field(..., min_length=1)
    gross_tonnage: float = Field(..., gt=0)
    loa_meters: float = Field(0.0, ge=0)
    chargeable_days: float = Field(0.0, ge=0)
    vessel_name: str | None = None
    tariffs: list[str] | None = None


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return fence.group(1).strip() if fence else text


class NLQueryParser:
    """Parses free-text vessel queries into structured VesselQuery objects."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def parse(self, query_text: str) -> VesselQuery:
        if not query_text or not query_text.strip():
            raise NLQueryError("Query text is empty.")

        raw = self._llm.generate(build_nl_query_prompt(query_text))
        cleaned = _strip_code_fences(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise NLQueryError(
                f"LLM returned non-JSON for query.\n"
                f"Raw (first 300): {cleaned[:300]}"
            ) from exc

        try:
            parsed = _ParsedNLQuery(**data)
        except ValidationError as exc:
            raise NLQueryError(f"Parsed query failed validation:\n{exc}") from exc

        vessel = VesselProfile(
            gross_tonnage=parsed.gross_tonnage,
            loa_meters=parsed.loa_meters,
            chargeable_days=parsed.chargeable_days,
        )
        return VesselQuery(
            port=parsed.port,
            vessel=vessel,
            vessel_name=parsed.vessel_name,
            tariffs=parsed.tariffs,
        )
