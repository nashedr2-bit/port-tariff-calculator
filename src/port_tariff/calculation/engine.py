"""
Deterministic tariff calculation engine.

This is the accuracy-critical core of the system. It takes a fully-specified
TariffRule (produced by the extraction layer) plus a vessel profile, and
returns an exact monetary result.

Design guarantees:
  * No LLM involvement. Same inputs -> same output, always.
  * No hardcoded port-specific values. Every number comes from the rule.
  * Every branch is unit-tested against Transnet ground-truth values.

The engine understands HOW to execute a rule of a given shape; it never
knows the specific rates for any port. That separation is what lets the
same engine calculate Durban today and Amsterdam tomorrow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..rules.schema import ChargeBasis, TariffRule
from .primitives import apply_minimum, blocks_per_100t, metres_ceiling


@dataclass(frozen=True)
class VesselProfile:
    """The subset of vessel attributes the engine needs.

    Kept deliberately small and explicit. The full vessel JSON from a query
    is mapped down to this by the agent layer; the engine depends only on
    what it actually uses.
    """

    gross_tonnage: float
    loa_meters: float = 0.0
    chargeable_days: float = 0.0

    def __post_init__(self) -> None:
        if self.gross_tonnage < 0:
            raise ValueError("gross_tonnage cannot be negative.")
        if self.loa_meters < 0:
            raise ValueError("loa_meters cannot be negative.")
        if self.chargeable_days < 0:
            raise ValueError("chargeable_days cannot be negative.")


@dataclass(frozen=True)
class TariffResult:
    """The outcome of calculating one tariff, with full traceability."""

    tariff_type: str
    port: str
    amount: float
    currency: str
    per_service_amount: float
    services: int
    basis: str
    source_section: Optional[str] = None
    source_page: Optional[str] = None
    notes: Optional[str] = None

    def rounded(self, dp: int = 2) -> float:
        return round(self.amount, dp)


class CalculationEngine:
    """Executes a TariffRule against a VesselProfile."""

    def calculate(self, rule: TariffRule, vessel: VesselProfile) -> TariffResult:
        """Compute a single tariff. Dispatches on the rule's basis/structure,
        applies the per-service amount, multiplies by the service count, and
        floors at any minimum fee."""

        if rule.tiers:
            per_service = self._calc_tiered(rule, vessel)
        elif rule.basis == ChargeBasis.PER_GT_RAW:
            per_service = self._calc_per_gt_raw(rule, vessel)
        elif rule.basis == ChargeBasis.PER_100T_CEILING:
            per_service = self._calc_per_100t(rule, vessel)
        elif rule.basis == ChargeBasis.PER_METRE_LOA:
            per_service = self._calc_per_metre(rule, vessel)
        elif rule.basis == ChargeBasis.FLAT:
            per_service = rule.basic_fee
        else:  # pragma: no cover - guarded by enum
            raise ValueError(f"Unsupported charge basis: {rule.basis}")

        total = per_service * rule.services
        total = apply_minimum(total, rule.minimum_fee)

        return TariffResult(
            tariff_type=rule.tariff_type,
            port=rule.port,
            amount=total,
            currency=rule.currency,
            per_service_amount=per_service,
            services=rule.services,
            basis=rule.basis.value,
            source_section=rule.source_section,
            source_page=rule.source_page,
            notes=rule.notes,
        )

    # --- structure handlers -------------------------------------------------

    def _calc_per_gt_raw(self, rule: TariffRule, vessel: VesselProfile) -> float:
        """Raw gross tonnage x rate (e.g. VTS: 0.65 x GT)."""
        return rule.basic_fee + rule.rate_per_unit * vessel.gross_tonnage

    def _calc_per_100t(self, rule: TariffRule, vessel: VesselProfile) -> float:
        """basic_fee + rate per 100-ton block, optionally plus a time
        component of time_rate per 100-ton block per chargeable day.

        Covers light dues (basic_fee=0), pilotage/berthing (basic_fee>0),
        and port dues (time_rate>0)."""
        blocks = blocks_per_100t(vessel.gross_tonnage)
        amount = rule.basic_fee + rule.rate_per_unit * blocks
        if rule.time_rate_per_unit:
            amount += rule.time_rate_per_unit * blocks * vessel.chargeable_days
        return amount

    def _calc_per_metre(self, rule: TariffRule, vessel: VesselProfile) -> float:
        """basic_fee + rate per whole metre of LOA."""
        metres = metres_ceiling(vessel.loa_meters)
        return rule.basic_fee + rule.rate_per_unit * metres

    def _calc_tiered(self, rule: TariffRule, vessel: VesselProfile) -> float:
        """Find the tier the vessel falls in, then:
        base_fee + increment_per_100t x ceil((tonnage - tier.floor)/100).

        Used by towage (section 3.6)."""
        gt = vessel.gross_tonnage
        tier = next((t for t in rule.tiers if t.contains(gt)), None)
        if tier is None:
            raise ValueError(
                f"No tier matches gross tonnage {gt} for "
                f"{rule.tariff_type} at {rule.port}."
            )
        blocks_above = blocks_per_100t(gt - tier.floor)
        return tier.base_fee + tier.increment_per_100t * blocks_above
