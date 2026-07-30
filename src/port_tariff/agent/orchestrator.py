"""
Tariff calculation orchestrator.

This is the top-level coordinator that fulfils the objective end-to-end:

    tariff document + vessel query
        -> for each applicable tariff:
             locate the relevant pages
             LLM extracts the rule (automation)
             engine calculates deterministically (accuracy)
        -> assemble a complete, itemised result with provenance + notes

It ties together ingestion (Step 2), extraction (Step 3), and calculation
(Step 1). It holds no tariff maths and no hardcoded rates of its own -- it
coordinates the layers that do.

Robustness: one tariff failing to extract does not abort the whole run. Each
tariff's outcome (success or a captured error) is recorded, so the caller
always gets a complete picture rather than a hard crash on the first problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..calculation.engine import CalculationEngine, TariffResult, VesselProfile
from ..extraction.extractor import ExtractionError, RuleExtractor, TariffLocation
from ..ingestion.pdf_ingestor import ParsedDocument
from .query import VesselQuery


@dataclass
class TariffLineItem:
    """One tariff's outcome within a full calculation."""

    tariff_type: str
    amount: Optional[float]
    currency: Optional[str]
    status: str  # "ok" | "extraction_error"
    source_section: Optional[str] = None
    source_page: Optional[str] = None
    services: Optional[int] = None
    notes: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CalculationReport:
    """The complete result of a vessel query."""

    port: str
    vessel_name: Optional[str]
    line_items: list[TariffLineItem] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(
            sum(li.amount for li in self.line_items if li.amount is not None), 2
        )

    @property
    def currency(self) -> Optional[str]:
        for li in self.line_items:
            if li.currency:
                return li.currency
        return None

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "vessel": self.vessel_name,
            "currency": self.currency,
            "line_items": [
                {
                    "tariff_type": li.tariff_type,
                    "amount": li.amount,
                    "status": li.status,
                    "source": (
                        f"section {li.source_section}, page {li.source_page}"
                        if li.source_section
                        else None
                    ),
                    "services": li.services,
                    "notes": li.notes,
                    "error": li.error,
                }
                for li in self.line_items
            ],
            "total": self.total,
        }


class TariffOrchestrator:
    """Coordinates extraction + calculation across all requested tariffs."""

    def __init__(
        self,
        extractor: RuleExtractor,
        locations: dict[str, TariffLocation],
        engine: Optional[CalculationEngine] = None,
    ) -> None:
        self._extractor = extractor
        self._locations = locations
        self._engine = engine or CalculationEngine()

    def run(
        self, document: ParsedDocument, query: VesselQuery
    ) -> CalculationReport:
        report = CalculationReport(port=query.port, vessel_name=query.vessel_name)

        tariff_types = query.tariffs or list(self._locations.keys())

        for tariff_type in tariff_types:
            location = self._locations.get(tariff_type)
            if location is None:
                report.line_items.append(
                    TariffLineItem(
                        tariff_type=tariff_type,
                        amount=None,
                        currency=None,
                        status="extraction_error",
                        error=f"No document location configured for '{tariff_type}'.",
                    )
                )
                continue

            try:
                rule = self._extractor.extract(document, location, port=query.port)
            except ExtractionError as exc:
                report.line_items.append(
                    TariffLineItem(
                        tariff_type=tariff_type,
                        amount=None,
                        currency=None,
                        status="extraction_error",
                        error=str(exc),
                    )
                )
                continue

            result: TariffResult = self._engine.calculate(rule, query.vessel)
            report.line_items.append(
                TariffLineItem(
                    tariff_type=tariff_type,
                    amount=result.rounded(),
                    currency=result.currency,
                    status="ok",
                    source_section=result.source_section,
                    source_page=result.source_page,
                    services=result.services,
                    notes=result.notes,
                )
            )

        return report
