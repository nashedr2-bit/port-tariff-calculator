"""
Tests for the orchestration layer (Step 4).

Verify the end-to-end flow offline: a vessel query drives extraction +
calculation across multiple tariffs, assembles a complete report, and handles
a failing tariff gracefully without aborting the whole run.
"""

import json

from port_tariff.agent.orchestrator import TariffOrchestrator
from port_tariff.agent.query import VesselQuery, vessel_profile_from_brief
from port_tariff.calculation.engine import VesselProfile
from port_tariff.extraction.extractor import RuleExtractor, TariffLocation
from port_tariff.extraction.llm_provider import ScriptedLLM
from port_tariff.ingestion.pdf_ingestor import ParsedDocument, ParsedPage


def _doc() -> ParsedDocument:
    return ParsedDocument(
        source_path="fake.pdf",
        pages=[ParsedPage(page_number=i, text=f"p{i}", tables=[]) for i in range(1, 13)],
    )


LIGHT_JSON = json.dumps(
    {
        "tariff_type": "light_dues",
        "port": "Durban",
        "basis": "per_100t_ceiling",
        "rate_per_unit": 117.08,
        "services": 1,
        "source_section": "1.1.1",
        "source_page": "p09",
    }
)
PILOTAGE_JSON = json.dumps(
    {
        "tariff_type": "pilotage_dues",
        "port": "Durban",
        "basis": "per_100t_ceiling",
        "basic_fee": 18608.61,
        "rate_per_unit": 9.72,
        "services": 2,
        "source_section": "3.3",
        "source_page": "p13",
    }
)

LOCATIONS = {
    "light_dues": TariffLocation("light_dues", 5, 6),
    "pilotage_dues": TariffLocation("pilotage_dues", 7, 8),
}


def test_orchestrator_runs_multiple_tariffs():
    # ScriptedLLM returns light first, pilotage second (call order)
    llm = ScriptedLLM([LIGHT_JSON, PILOTAGE_JSON])
    orch = TariffOrchestrator(RuleExtractor(llm), LOCATIONS)
    query = VesselQuery(
        port="Durban",
        vessel=VesselProfile(gross_tonnage=51300),
        vessel_name="SUDESTADA",
        tariffs=["light_dues", "pilotage_dues"],
    )
    report = orch.run(_doc(), query)

    assert len(report.line_items) == 2
    amounts = {li.tariff_type: li.amount for li in report.line_items}
    assert amounts["light_dues"] == 60062.04
    assert amounts["pilotage_dues"] == 47189.94
    assert report.total == round(60062.04 + 47189.94, 2)


def test_orchestrator_records_source_and_services():
    llm = ScriptedLLM([PILOTAGE_JSON])
    orch = TariffOrchestrator(RuleExtractor(llm), LOCATIONS)
    query = VesselQuery(
        port="Durban",
        vessel=VesselProfile(gross_tonnage=51300),
        tariffs=["pilotage_dues"],
    )
    report = orch.run(_doc(), query)
    li = report.line_items[0]
    assert li.source_section == "3.3"
    assert li.services == 2
    assert li.status == "ok"


def test_orchestrator_handles_extraction_failure_gracefully():
    """A bad LLM response for one tariff must not abort the whole run."""
    llm = ScriptedLLM(["not json at all"])
    orch = TariffOrchestrator(RuleExtractor(llm), LOCATIONS)
    query = VesselQuery(
        port="Durban",
        vessel=VesselProfile(gross_tonnage=51300),
        tariffs=["light_dues"],
    )
    report = orch.run(_doc(), query)
    li = report.line_items[0]
    assert li.status == "extraction_error"
    assert li.amount is None
    assert li.error is not None


def test_orchestrator_unknown_tariff_is_recorded_not_crashed():
    llm = ScriptedLLM([LIGHT_JSON])
    orch = TariffOrchestrator(RuleExtractor(llm), LOCATIONS)
    query = VesselQuery(
        port="Durban",
        vessel=VesselProfile(gross_tonnage=51300),
        tariffs=["nonexistent_tariff"],
    )
    report = orch.run(_doc(), query)
    assert report.line_items[0].status == "extraction_error"


def test_report_to_dict_shape():
    llm = ScriptedLLM([LIGHT_JSON])
    orch = TariffOrchestrator(RuleExtractor(llm), LOCATIONS)
    query = VesselQuery(
        port="Durban",
        vessel=VesselProfile(gross_tonnage=51300),
        vessel_name="SUDESTADA",
        tariffs=["light_dues"],
    )
    d = orch.run(_doc(), query).to_dict()
    assert d["port"] == "Durban"
    assert d["vessel"] == "SUDESTADA"
    assert d["total"] == 60062.04
    assert d["line_items"][0]["tariff_type"] == "light_dues"


class TestVesselProfileFromBrief:
    def test_nested_brief_structure(self):
        payload = {
            "technical_specs": {"gross_tonnage": 51300, "loa_meters": 229.2},
            "operational_data": {"days_alongside": 3.39},
        }
        vp = vessel_profile_from_brief(payload)
        assert vp.gross_tonnage == 51300
        assert vp.loa_meters == 229.2
        assert vp.chargeable_days == 3.39

    def test_flat_structure(self):
        payload = {"gross_tonnage": 20000, "loa_meters": 180, "chargeable_days": 2.5}
        vp = vessel_profile_from_brief(payload)
        assert vp.gross_tonnage == 20000
        assert vp.chargeable_days == 2.5

    def test_missing_gt_raises(self):
        import pytest

        with pytest.raises(ValueError):
            vessel_profile_from_brief({"technical_specs": {}})
