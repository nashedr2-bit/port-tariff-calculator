"""
Generalization test.

The central claim of this system is that the calculation engine holds NO
port-specific logic -- it executes rule *shapes*, and the specific rates come
from the extracted rules. To prove that, this test invents a fictional
"Amsterdam" port with completely different rates, a different currency, and
different structures, and runs it through the SAME engine used for Durban,
with zero code changes.

If this passes, the engine genuinely generalizes: pointing it at any port's
rules (however they are obtained) produces correct calculations without
touching the engine.
"""

import math

from port_tariff.calculation.engine import CalculationEngine, VesselProfile
from port_tariff.rules.schema import ChargeBasis, TariffRule, Tier

engine = CalculationEngine()


def test_fictional_amsterdam_per_gt_raw():
    """A made-up EUR per-GT harbour due, different rate and currency."""
    rule = TariffRule(
        tariff_type="harbour_due",
        port="Amsterdam",
        currency="EUR",
        basis=ChargeBasis.PER_GT_RAW,
        rate_per_unit=0.42,
        minimum_fee=100.0,
    )
    vessel = VesselProfile(gross_tonnage=20000)
    result = engine.calculate(rule, vessel)
    assert result.amount == 0.42 * 20000          # 8,400.00
    assert result.currency == "EUR"


def test_fictional_amsterdam_basic_plus_per_100t_with_services():
    """A made-up pilotage-style charge: basic + per-100t, charged x2."""
    rule = TariffRule(
        tariff_type="pilotage_due",
        port="Amsterdam",
        currency="EUR",
        basis=ChargeBasis.PER_100T_CEILING,
        basic_fee=500.0,
        rate_per_unit=2.5,
        services=2,
    )
    vessel = VesselProfile(gross_tonnage=20000)  # 200 blocks
    result = engine.calculate(rule, vessel)
    assert result.amount == (500.0 + 2.5 * 200) * 2   # 2,000.00


def test_fictional_amsterdam_tiered_structure():
    """A made-up tiered towage charge with different bands and increments."""
    rule = TariffRule(
        tariff_type="towage_due",
        port="Amsterdam",
        currency="EUR",
        basis=ChargeBasis.PER_100T_CEILING,
        services=2,
        tiers=[
            Tier(floor=0, ceiling=25000, base_fee=5000.0, increment_per_100t=10.0),
            Tier(floor=25000, ceiling=None, base_fee=8000.0, increment_per_100t=5.0),
        ],
    )
    vessel = VesselProfile(gross_tonnage=30000)  # falls in 2nd band
    result = engine.calculate(rule, vessel)
    blocks_above = math.ceil((30000 - 25000) / 100)  # 50
    expected = (8000.0 + 5.0 * blocks_above) * 2     # (8000 + 250) * 2 = 16,500
    assert result.amount == expected


def test_same_engine_no_special_casing():
    """The engine never branches on port name -- proven by calculating two
    different ports with the same code path and only different rule data."""
    durban_like = TariffRule(
        tariff_type="x", port="Durban", basis=ChargeBasis.PER_100T_CEILING,
        rate_per_unit=117.08,
    )
    amsterdam_like = TariffRule(
        tariff_type="x", port="Amsterdam", currency="EUR",
        basis=ChargeBasis.PER_100T_CEILING, rate_per_unit=99.0,
    )
    vessel = VesselProfile(gross_tonnage=51300)  # 513 blocks
    assert engine.calculate(durban_like, vessel).amount == 513 * 117.08
    assert engine.calculate(amsterdam_like, vessel).amount == 513 * 99.0
