"""
Tests for the LLM rule-extraction layer.

These run fully OFFLINE using ScriptedLLM (canned responses), so they verify
the extraction + parsing + validation logic with no network or API key.

The pivotal test is `test_extracted_rule_reproduces_ground_truth`: it feeds a
realistic LLM JSON response through extraction, then through the calculation
engine, and asserts we still hit the Transnet ground-truth value. This proves
the full automation path -- document -> LLM rule -> engine -> correct number --
without any hardcoded rule in the calculation path.
"""

import json

import pytest

from port_tariff.calculation.engine import CalculationEngine, VesselProfile
from port_tariff.extraction.extractor import (
    ExtractionError,
    RuleExtractor,
    TariffLocation,
)
from port_tariff.extraction.llm_provider import ScriptedLLM
from port_tariff.ingestion.pdf_ingestor import ParsedDocument, ParsedPage


def _doc() -> ParsedDocument:
    """A tiny fake document; content is irrelevant because the ScriptedLLM
    ignores the prompt and returns a fixed response."""
    return ParsedDocument(
        source_path="fake.pdf",
        pages=[
            ParsedPage(page_number=i, text=f"page {i} text", tables=[])
            for i in range(1, 13)
        ],
    )


# A realistic LLM response for Durban pilotage (what a correct extraction looks like)
PILOTAGE_JSON = json.dumps(
    {
        "tariff_type": "pilotage_dues",
        "port": "Durban",
        "currency": "ZAR",
        "basis": "per_100t_ceiling",
        "basic_fee": 18608.61,
        "rate_per_unit": 9.72,
        "time_rate_per_unit": 0,
        "services": 2,
        "minimum_fee": None,
        "tiers": [],
        "source_section": "3.3",
        "source_page": "p13",
        "notes": "Durban column; charged in+out.",
    }
)


def test_extraction_produces_valid_rule():
    extractor = RuleExtractor(ScriptedLLM(PILOTAGE_JSON))
    loc = TariffLocation("pilotage_dues", page_start=7, page_end=7)
    rule = extractor.extract(_doc(), loc, port="Durban")
    assert rule.tariff_type == "pilotage_dues"
    assert rule.basic_fee == 18608.61
    assert rule.services == 2


def test_extracted_rule_reproduces_ground_truth():
    """The extracted rule, run through the engine, hits ground truth exactly."""
    extractor = RuleExtractor(ScriptedLLM(PILOTAGE_JSON))
    loc = TariffLocation("pilotage_dues", page_start=7, page_end=7)
    rule = extractor.extract(_doc(), loc, port="Durban")

    engine = CalculationEngine()
    vessel = VesselProfile(gross_tonnage=51300)
    result = engine.calculate(rule, vessel)
    assert result.rounded() == 47189.94


def test_code_fenced_json_is_handled():
    """LLM wrapping JSON in ```json fences must still parse."""
    fenced = f"```json\n{PILOTAGE_JSON}\n```"
    extractor = RuleExtractor(ScriptedLLM(fenced))
    loc = TariffLocation("pilotage_dues", page_start=7, page_end=7)
    rule = extractor.extract(_doc(), loc, port="Durban")
    assert rule.basic_fee == 18608.61


def test_non_json_response_raises_extraction_error():
    extractor = RuleExtractor(ScriptedLLM("I think the fee is about 18000 rand."))
    loc = TariffLocation("pilotage_dues", page_start=7, page_end=7)
    with pytest.raises(ExtractionError, match="non-JSON"):
        extractor.extract(_doc(), loc, port="Durban")


def test_malformed_rule_raises_extraction_error():
    """Valid JSON but invalid schema (bad basis) is caught."""
    bad = json.dumps(
        {"tariff_type": "x", "port": "Durban", "basis": "not_a_real_basis"}
    )
    extractor = RuleExtractor(ScriptedLLM(bad))
    loc = TariffLocation("x", page_start=1, page_end=1)
    with pytest.raises(ExtractionError, match="schema validation"):
        extractor.extract(_doc(), loc, port="Durban")


def test_tiered_towage_extraction_reproduces_ground_truth():
    """A tiered towage rule extracted from JSON reproduces ground truth."""
    towage_json = json.dumps(
        {
            "tariff_type": "towage_dues",
            "port": "Durban",
            "basis": "per_100t_ceiling",
            "services": 2,
            "tiers": [
                {"floor": 0, "ceiling": 2000, "base_fee": 8140.0,
                 "increment_per_100t": 0},
                {"floor": 2000, "ceiling": 10000, "base_fee": 12633.99,
                 "increment_per_100t": 268.99},
                {"floor": 10000, "ceiling": 50000, "base_fee": 38494.51,
                 "increment_per_100t": 84.95},
                {"floor": 50000, "ceiling": 100000, "base_fee": 73118.07,
                 "increment_per_100t": 32.24},
                {"floor": 100000, "ceiling": None, "base_fee": 93548.13,
                 "increment_per_100t": 23.65},
            ],
            "source_section": "3.6",
            "source_page": "p15",
        }
    )
    extractor = RuleExtractor(ScriptedLLM(towage_json))
    loc = TariffLocation("towage_dues", page_start=8, page_end=8)
    rule = extractor.extract(_doc(), loc, port="Durban")

    engine = CalculationEngine()
    result = engine.calculate(rule, VesselProfile(gross_tonnage=51300))
    assert result.rounded() == 147074.38
