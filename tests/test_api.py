"""
Tests for the FastAPI endpoint (Step 5).

These run the API in OFFLINE mode: a TariffOrchestrator backed by ScriptedLLM
and a small fake document are injected via AppState, so the endpoint is
exercised end-to-end with no network and no API key.

This proves the HTTP contract (request validation, response shape, error
handling) independently of the live LLM.
"""

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from port_tariff.agent.locations import TRANSNET_TARIFF_LOCATIONS  # noqa: E402
from port_tariff.agent.orchestrator import TariffOrchestrator  # noqa: E402
from port_tariff.api.app import AppState, create_app  # noqa: E402
from port_tariff.extraction.extractor import RuleExtractor  # noqa: E402
from port_tariff.extraction.llm_provider import ScriptedLLM  # noqa: E402
from port_tariff.ingestion.pdf_ingestor import ParsedDocument, ParsedPage  # noqa: E402


def _fake_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="fake.pdf",
        pages=[ParsedPage(page_number=i, text=f"p{i}", tables=[]) for i in range(1, 13)],
    )


# canned correct rules keyed to the request order
CANNED = {
    "light_dues": {
        "tariff_type": "light_dues", "port": "Durban",
        "basis": "per_100t_ceiling", "rate_per_unit": 117.08, "services": 1,
        "source_section": "1.1.1", "source_page": "p09",
    },
    "pilotage_dues": {
        "tariff_type": "pilotage_dues", "port": "Durban",
        "basis": "per_100t_ceiling", "basic_fee": 18608.61, "rate_per_unit": 9.72,
        "services": 2, "source_section": "3.3", "source_page": "p13",
    },
}


def _offline_client(order: list[str]) -> TestClient:
    responses = [json.dumps(CANNED[t]) for t in order]
    orchestrator = TariffOrchestrator(
        RuleExtractor(ScriptedLLM(responses)), TRANSNET_TARIFF_LOCATIONS
    )
    state = AppState(orchestrator=orchestrator, document=_fake_document())
    return TestClient(create_app(state))


def test_health():
    client = _offline_client([])
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_calculate_single_tariff():
    client = _offline_client(["light_dues"])
    resp = client.post(
        "/calculate",
        json={
            "port": "Durban",
            "vessel": {"gross_tonnage": 51300, "name": "SUDESTADA"},
            "tariffs": ["light_dues"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["port"] == "Durban"
    assert body["vessel"] == "SUDESTADA"
    assert body["line_items"][0]["tariff_type"] == "light_dues"
    assert body["line_items"][0]["amount"] == 60062.04
    assert body["total"] == 60062.04


def test_calculate_multiple_tariffs_total():
    client = _offline_client(["light_dues", "pilotage_dues"])
    resp = client.post(
        "/calculate",
        json={
            "port": "Durban",
            "vessel": {"gross_tonnage": 51300},
            "tariffs": ["light_dues", "pilotage_dues"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == round(60062.04 + 47189.94, 2)
    assert body["line_items"][1]["services"] == 2
    assert body["line_items"][1]["source"] == "section 3.3, page p13"


def test_invalid_vessel_rejected_by_validation():
    """gross_tonnage must be > 0 -> 422 from pydantic validation."""
    client = _offline_client([])
    resp = client.post(
        "/calculate",
        json={"port": "Durban", "vessel": {"gross_tonnage": 0}},
    )
    assert resp.status_code == 422


def test_missing_port_rejected():
    client = _offline_client([])
    resp = client.post(
        "/calculate", json={"vessel": {"gross_tonnage": 51300}}
    )
    assert resp.status_code == 422


def test_extraction_failure_surfaces_as_line_item():
    """If the LLM returns junk, the tariff comes back as an error line item,
    not a 500 -- the run degrades gracefully."""
    orchestrator = TariffOrchestrator(
        RuleExtractor(ScriptedLLM(["not json"])), TRANSNET_TARIFF_LOCATIONS
    )
    state = AppState(orchestrator=orchestrator, document=_fake_document())
    client = TestClient(create_app(state))
    resp = client.post(
        "/calculate",
        json={
            "port": "Durban",
            "vessel": {"gross_tonnage": 51300},
            "tariffs": ["light_dues"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["line_items"][0]["status"] == "extraction_error"
    assert body["line_items"][0]["amount"] is None


def test_calculate_via_natural_language_query():
    """The API accepts a free-text query, parses it, and calculates."""
    import json as _json

    from port_tariff.agent.nl_parser import NLQueryParser

    # NL parser LLM returns the structured query; orchestrator LLM returns rules
    nl_response = _json.dumps(
        {
            "port": "Durban",
            "gross_tonnage": 51300,
            "loa_meters": 229.2,
            "chargeable_days": 3.396,
            "vessel_name": "SUDESTADA",
            "tariffs": ["light_dues"],
        }
    )
    orchestrator = TariffOrchestrator(
        RuleExtractor(ScriptedLLM([json.dumps(CANNED["light_dues"])])),
        TRANSNET_TARIFF_LOCATIONS,
    )
    state = AppState(
        orchestrator=orchestrator,
        document=_fake_document(),
        nl_parser=NLQueryParser(ScriptedLLM(nl_response)),
    )
    client = TestClient(create_app(state))
    resp = client.post(
        "/calculate",
        json={"query": "all light dues for SUDESTADA 51300 GT at Durban"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["port"] == "Durban"
    assert body["line_items"][0]["amount"] == 60062.04


def test_calculate_requires_some_input():
    client = _offline_client([])
    resp = client.post("/calculate", json={})
    assert resp.status_code == 422
