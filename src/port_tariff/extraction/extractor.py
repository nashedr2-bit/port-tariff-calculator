"""
Rule extractor.

Orchestrates the automation core: given an ingested document, a tariff type,
and a port, it asks the LLM to read the relevant excerpt and return a
structured rule, then parses and VALIDATES that response into a TariffRule the
engine can consume.

The validation step is critical error-handling: the LLM's output is untrusted
until it parses cleanly into our Pydantic schema. Malformed JSON, missing
fields, or inconsistent structures are caught here and raised as clear
ExtractionErrors -- they never reach the calculation engine as silent bad data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from ..ingestion.pdf_ingestor import ParsedDocument
from ..rules.schema import TariffRule
from .llm_provider import LLMProvider
from .prompts import build_extraction_prompt


class ExtractionError(Exception):
    """Raised when the LLM response cannot be turned into a valid rule."""


@dataclass
class TariffLocation:
    """Where in the document a given tariff's rules live.

    In a fully autonomous agent this is discovered by semantic search /
    retrieval. We keep it explicit and injectable so extraction can be tested
    deterministically and so a human can override page hints when needed.
    The page ranges are 1-based and inclusive.
    """

    tariff_type: str
    page_start: int
    page_end: int


def _strip_code_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` despite instructions.
    Strip fences defensively before parsing."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


class RuleExtractor:
    """Extracts validated TariffRules from a document using an LLM."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def extract(
        self,
        document: ParsedDocument,
        location: TariffLocation,
        port: str,
    ) -> TariffRule:
        """Extract one tariff rule for one port."""
        excerpt = self._build_excerpt(document, location)
        prompt = build_extraction_prompt(
            tariff_type=location.tariff_type,
            port=port,
            document_excerpt=excerpt,
        )
        raw = self._llm.generate(prompt)
        return self._parse(raw, location.tariff_type, port)

    def _build_excerpt(
        self, document: ParsedDocument, location: TariffLocation
    ) -> str:
        pages = document.pages_in_range(location.page_start, location.page_end)
        return "\n\n".join(p.as_markdown() for p in pages)

    def _parse(self, raw: str, tariff_type: str, port: str) -> TariffRule:
        cleaned = _strip_code_fences(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"LLM returned non-JSON for {tariff_type}@{port}: {exc}\n"
                f"Raw response (first 300 chars): {cleaned[:300]}"
            ) from exc

        try:
            rule = TariffRule(**data)
        except ValidationError as exc:
            raise ExtractionError(
                f"LLM JSON failed schema validation for {tariff_type}@{port}:\n"
                f"{exc}"
            ) from exc

        # sanity: the LLM must not have silently answered for a different tariff
        if rule.tariff_type != tariff_type:
            rule = rule.model_copy(update={"tariff_type": tariff_type})
        return rule
