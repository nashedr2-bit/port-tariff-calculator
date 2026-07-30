"""
Universal tariff rule schema.

This module defines the abstract shape that ANY port tariff fits into,
regardless of port or document. The LLM extraction layer populates these
structures at runtime by reading a tariff PDF; the calculation engine
consumes them deterministically.

The key design principle: this schema knows about STRUCTURE (how a charge
is shaped) but never about specific VALUES for a given port. Those values
are supplied by the extraction layer at runtime, which is what makes the
system generalise to any port or document without code changes.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ChargeBasis(str, Enum):
    """How the primary quantity for a charge is measured.

    PER_GT_RAW          -> multiply raw gross tonnage (e.g. VTS: 0.65 x GT)
    PER_100T_CEILING    -> ceil(tonnage / 100) blocks (most tariffs)
    PER_METRE_LOA       -> ceil(length overall) metres (some light dues)
    FLAT                -> a fixed fee independent of size
    """

    PER_GT_RAW = "per_gt_raw"
    PER_100T_CEILING = "per_100t_ceiling"
    PER_METRE_LOA = "per_metre_loa"
    FLAT = "flat"


class Tier(BaseModel):
    """A single tonnage band within a tiered charge (e.g. towage).

    A tier applies when the vessel's tonnage falls within
    [floor, ceiling). Within the tier, the charge is:
        base_fee + increment_per_100t * ceil((tonnage - floor) / 100)
    """

    floor: float = Field(..., description="Lower tonnage bound (inclusive).")
    ceiling: Optional[float] = Field(
        None, description="Upper tonnage bound (exclusive). None = open-ended top tier."
    )
    base_fee: float = Field(..., description="Fixed fee for vessels in this tier.")
    increment_per_100t: float = Field(
        0.0, description="Added per 100 tons (ceiling) above this tier's floor."
    )

    def contains(self, tonnage: float) -> bool:
        if tonnage < self.floor:
            return False
        if self.ceiling is None:
            return True
        return tonnage < self.ceiling


class TariffRule(BaseModel):
    """A single, fully-specified tariff rule for one tariff type at one port.

    This is the object the LLM produces (by reading the document) and the
    calculation engine consumes. Every field except the identifying ones has
    a sensible default so a simple flat charge needs minimal specification.
    """

    # --- identity ---
    tariff_type: str = Field(..., description="e.g. 'light_dues', 'port_dues'.")
    port: str = Field(..., description="Port this rule applies to, e.g. 'Durban'.")
    currency: str = Field("ZAR", description="Currency of all monetary values.")

    # --- how the charge is measured ---
    basis: ChargeBasis = Field(..., description="Measurement basis for the charge.")

    # --- simple (non-tiered) structure ---
    basic_fee: float = Field(
        0.0, description="Fixed base fee (before any per-unit component)."
    )
    rate_per_unit: float = Field(
        0.0,
        description="Rate applied per unit of the basis "
        "(per GT, per 100t block, or per metre).",
    )

    # --- tiered structure (overrides simple structure when present) ---
    tiers: list[Tier] = Field(
        default_factory=list,
        description="Tonnage bands. When present, the matching tier's "
        "base_fee + increment_per_100t drives the charge.",
    )

    # --- time component (e.g. port dues: per 100t per 24h) ---
    time_rate_per_unit: float = Field(
        0.0,
        description="Optional per-unit-per-day rate added on top "
        "(used by port dues). Multiplied by chargeable_days.",
    )

    # --- service multiplier ---
    services: int = Field(
        1,
        ge=1,
        description="Number of chargeable services. Marine movement services "
        "(pilotage, towage, berthing) are charged x2 (in + out).",
    )

    # --- floors / minimums ---
    minimum_fee: Optional[float] = Field(
        None, description="Charge is floored at this value if provided."
    )

    # --- provenance (traceability, not used in maths) ---
    source_section: Optional[str] = Field(
        None, description="Document section this rule came from, e.g. '3.3'."
    )
    source_page: Optional[str] = Field(
        None, description="Printed page reference, e.g. 'p13'."
    )
    notes: Optional[str] = Field(
        None, description="Any interpretation notes captured during extraction."
    )

    @model_validator(mode="after")
    def _validate_structure(self) -> "TariffRule":
        """Guard against internally inconsistent rules before they reach
        the calculation engine. Fail loudly at construction, not silently
        during calculation."""
        if self.basis == ChargeBasis.FLAT:
            if self.rate_per_unit or self.tiers or self.time_rate_per_unit:
                raise ValueError(
                    "FLAT basis cannot have rate_per_unit, tiers, or time_rate."
                )
        if self.tiers:
            # tiers must be ordered and non-overlapping
            sorted_floors = sorted(t.floor for t in self.tiers)
            if sorted_floors != [t.floor for t in self.tiers]:
                raise ValueError("Tiers must be provided in ascending floor order.")
        return self
