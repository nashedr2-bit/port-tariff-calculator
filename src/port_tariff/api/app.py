"""
FastAPI application exposing the tariff calculator as an HTTP service.

    POST /calculate   -> calculate all applicable tariffs for a vessel at a port
    GET  /health      -> liveness check
    GET  /docs        -> interactive API documentation (auto-generated)

MODES
-----
The endpoint runs LIVE by default: it ingests the tariff document and calls the
configured LLM (Gemini) to extract rules at runtime -- the real capability the
task is about.

An OFFLINE mode is available for testing without an API key or network: inject
a pre-built extractor (e.g. one backed by ScriptedLLM). This mirrors how the
test suite validates the pipeline, and lets Alan's team verify the API contract
without spending quota. The endpoint logic is identical in both modes -- only
the LLM provider differs -- which demonstrates the provider-agnostic design.

The document is ingested once at startup and reused across requests (parsing a
27-page PDF per request would be wasteful).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException

from ..agent.locations import TRANSNET_TARIFF_LOCATIONS
from ..agent.orchestrator import TariffOrchestrator
from ..agent.query import VesselQuery
from ..calculation.engine import VesselProfile
from ..extraction.extractor import RuleExtractor
from ..ingestion.pdf_ingestor import ParsedDocument, PdfIngestor
from .models import CalculationRequest, CalculationResponse

DEFAULT_PDF = os.environ.get(
    "TARIFF_PDF_PATH", "data/port_tariff_transnet_2024.pdf"
)


class AppState:
    """Holds injected dependencies so the app is testable.

    In production these are built from real components (Gemini + the bundled
    PDF). In tests, an offline orchestrator + a small fake document are
    injected, so the endpoint runs with no network or key.
    """

    def __init__(
        self,
        orchestrator: Optional[TariffOrchestrator] = None,
        document: Optional[ParsedDocument] = None,
        nl_parser: Optional["object"] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._document = document
        self._nl_parser = nl_parser

    @property
    def orchestrator(self) -> TariffOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = self._build_live_orchestrator()
        return self._orchestrator

    @property
    def nl_parser(self):
        if self._nl_parser is None:
            self._nl_parser = self._build_live_nl_parser()
        return self._nl_parser

    @property
    def document(self) -> ParsedDocument:
        if self._document is None:
            self._document = PdfIngestor().ingest(DEFAULT_PDF)
        return self._document

    @staticmethod
    def _build_live_orchestrator() -> TariffOrchestrator:
        # Imported here so the app can start in offline mode without the SDK.
        from ..extraction.llm_provider import GeminiProvider

        extractor = RuleExtractor(GeminiProvider(temperature=0.0))
        return TariffOrchestrator(extractor, TRANSNET_TARIFF_LOCATIONS)

    @staticmethod
    def _build_live_nl_parser():
        from ..agent.nl_parser import NLQueryParser
        from ..extraction.llm_provider import GeminiProvider

        return NLQueryParser(GeminiProvider(temperature=0.0))


def create_app(state: Optional[AppState] = None) -> FastAPI:
    """Application factory. Pass a custom AppState to inject an offline
    orchestrator/document for testing."""
    app = FastAPI(
        title="Port Tariff Calculator",
        version="1.0.0",
        description=(
            "Calculates vessel port dues by reading a port tariff document "
            "with an LLM and computing charges deterministically."
        ),
    )
    app.state.deps = state or AppState()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/calculate", response_model=CalculationResponse)
    def calculate(request: CalculationRequest) -> CalculationResponse:
        deps: AppState = app.state.deps

        # Path 1: natural-language query (parsed by the LLM) when structured
        # port/vessel are not both provided but a query string is.
        if request.query and not (request.port and request.vessel):
            try:
                query = deps.nl_parser.parse(request.query)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=422,
                    detail=f"Could not parse natural-language query: {exc}",
                ) from exc
            if request.tariffs:
                query.tariffs = request.tariffs
        else:
            # Path 2: structured input.
            if not request.port or not request.vessel:
                raise HTTPException(
                    status_code=422,
                    detail="Provide either (port + vessel) or a natural-language "
                    "'query'.",
                )
            try:
                vessel = VesselProfile(
                    gross_tonnage=request.vessel.gross_tonnage,
                    loa_meters=request.vessel.loa_meters,
                    chargeable_days=request.vessel.chargeable_days,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            query = VesselQuery(
                port=request.port,
                vessel=vessel,
                vessel_name=request.vessel.name,
                tariffs=request.tariffs,
            )

        try:
            report = deps.orchestrator.run(deps.document, query)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=500, detail=f"Tariff document not available: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface a clean 500
            raise HTTPException(
                status_code=500, detail=f"Calculation failed: {exc}"
            ) from exc

        return CalculationResponse.from_report_dict(report.to_dict())

    return app


@lru_cache
def get_app() -> FastAPI:
    """Cached live app for `uvicorn port_tariff.api.app:get_app --factory`."""
    return create_app()
