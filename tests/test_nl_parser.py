"""
Tests for the natural-language query parser.

Run offline with ScriptedLLM: verify that a free-text query is parsed into a
correct structured VesselQuery, that the result drives the engine to ground
truth, and that malformed responses are caught.
"""

import json

import pytest

from port_tariff.agent.nl_parser import NLQueryError, NLQueryParser
from port_tariff.calculation.engine import CalculationEngine
from port_tariff.extraction.llm_provider import ScriptedLLM
from tests.durban_fixtures import PILOTAGE_DUES_DURBAN

# what the LLM should return for:
# "Calculate all dues for the SUDESTADA, a 51,300 GT bulk carrier at Durban,
#  alongside for 3.4 days"
GOOD_RESPONSE = json.dumps(
    {
        "port": "Durban",
        "gross_tonnage": 51300,
        "loa_meters": 229.2,
        "chargeable_days": 3.4,
        "vessel_name": "SUDESTADA",
        "tariffs": None,
    }
)


def test_parses_free_text_into_structured_query():
    parser = NLQueryParser(ScriptedLLM(GOOD_RESPONSE))
    q = parser.parse(
        "Calculate all dues for the SUDESTADA, a 51,300 GT bulk carrier "
        "at Durban, alongside for 3.4 days"
    )
    assert q.port == "Durban"
    assert q.vessel.gross_tonnage == 51300
    assert q.vessel.chargeable_days == 3.4
    assert q.vessel_name == "SUDESTADA"
    assert q.tariffs is None  # all tariffs


def test_parsed_query_drives_engine_to_ground_truth():
    parser = NLQueryParser(ScriptedLLM(GOOD_RESPONSE))
    q = parser.parse("... SUDESTADA 51300 GT Durban ...")
    engine = CalculationEngine()
    result = engine.calculate(PILOTAGE_DUES_DURBAN, q.vessel)
    assert result.rounded() == 47189.94


def test_specific_tariffs_extracted():
    resp = json.dumps(
        {
            "port": "Durban",
            "gross_tonnage": 20000,
            "loa_meters": 0,
            "chargeable_days": 0,
            "vessel_name": None,
            "tariffs": ["light_dues", "vts_dues"],
        }
    )
    parser = NLQueryParser(ScriptedLLM(resp))
    q = parser.parse("What are the light and VTS dues for a 20000 GT ship at Durban?")
    assert q.tariffs == ["light_dues", "vts_dues"]


def test_code_fenced_response_handled():
    parser = NLQueryParser(ScriptedLLM(f"```json\n{GOOD_RESPONSE}\n```"))
    q = parser.parse("anything")
    assert q.vessel.gross_tonnage == 51300


def test_empty_query_raises():
    parser = NLQueryParser(ScriptedLLM(GOOD_RESPONSE))
    with pytest.raises(NLQueryError, match="empty"):
        parser.parse("   ")


def test_non_json_response_raises():
    parser = NLQueryParser(ScriptedLLM("The ship is quite large."))
    with pytest.raises(NLQueryError, match="non-JSON"):
        parser.parse("some query")


def test_missing_tonnage_raises():
    resp = json.dumps({"port": "Durban", "gross_tonnage": 0})
    parser = NLQueryParser(ScriptedLLM(resp))
    with pytest.raises(NLQueryError, match="validation"):
        parser.parse("a query with no tonnage")
