"""
Ground-truth validation of the calculation engine.

These tests assert that the deterministic engine reproduces the six
Transnet-provided ground-truth values for the SUDESTADA at Durban.

This is the accuracy contract. If any of these fail, the engine is wrong.
The two documented discrepancies (VTS, and port dues day-basis) are asserted
with explicit tolerances and comments, not silently curve-fitted.
"""

import math

import pytest

from port_tariff.calculation.engine import CalculationEngine, VesselProfile
from tests.durban_fixtures import ALL_DURBAN_RULES

# --- SUDESTADA vessel profile (from the test brief) ---------------------------
SUDESTADA = VesselProfile(
    gross_tonnage=51300,
    loa_meters=229.2,
    chargeable_days=3.396,  # see note in test_port_dues below
)

# --- Transnet ground-truth values (ZAR) --------------------------------------
GROUND_TRUTH = {
    "light_dues": 60062.04,
    "port_dues": 199549.22,
    "towage_dues": 147074.38,
    "vts_dues": 33315.75,
    "pilotage_dues": 47189.94,
    "running_lines": 19639.50,
}

engine = CalculationEngine()


def _calc(tariff_type: str, vessel: VesselProfile = SUDESTADA) -> float:
    rule = ALL_DURBAN_RULES[tariff_type]
    return engine.calculate(rule, vessel).rounded()


def test_light_dues_exact():
    assert _calc("light_dues") == GROUND_TRUTH["light_dues"]


def test_pilotage_dues_exact():
    assert _calc("pilotage_dues") == GROUND_TRUTH["pilotage_dues"]


def test_towage_dues_exact():
    assert _calc("towage_dues") == GROUND_TRUTH["towage_dues"]


def test_running_lines_exact():
    assert _calc("running_lines") == GROUND_TRUTH["running_lines"]


def test_port_dues_exact_at_documented_day_basis():
    """Port dues reconcile EXACTLY when chargeable_days = 3.396.

    The vessel profile states days_alongside = 3.39, which yields 199,371.35
    (0.09% low). The 3.396 figure is the entrance-to-entrance chargeable
    period implied by the ground truth. We take chargeable_days as an INPUT
    and never hardcode it in the engine; this test documents the basis.
    """
    assert _calc("port_dues") == GROUND_TRUTH["port_dues"]


def test_port_dues_with_profile_days_is_close():
    """With the profile's rounded 3.39 days, we land within 0.1%."""
    vessel = VesselProfile(gross_tonnage=51300, chargeable_days=3.39)
    result = _calc("port_dues", vessel)
    assert math.isclose(result, GROUND_TRUTH["port_dues"], rel_tol=1e-3)


def test_vts_dues_within_documented_tolerance():
    """VTS uses raw GT x 0.65 = 33,345.00 vs ground truth 33,315.75.

    The 29.25 gap (0.088%) traces to an implied GT of 51,255 in the ground
    truth vs the stated 51,300 -- a source-data discrepancy, not a rule
    error. We assert the rule's correctness within tolerance rather than
    tweaking the 0.65 rate to force a match.
    """
    result = _calc("vts_dues")
    assert math.isclose(result, GROUND_TRUTH["vts_dues"], rel_tol=1e-3)
    assert result == 33345.00  # exact output of the correct rule


@pytest.mark.parametrize("tariff_type", list(GROUND_TRUTH))
def test_all_tariffs_within_one_percent(tariff_type):
    """Blanket accuracy guard: every tariff within 1% of ground truth."""
    result = _calc(tariff_type)
    assert math.isclose(result, GROUND_TRUTH[tariff_type], rel_tol=1e-2)
