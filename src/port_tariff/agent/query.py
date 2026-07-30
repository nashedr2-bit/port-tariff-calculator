"""
Vessel query models.

The objective asks the system to consume "a natural language vessel query".
In practice a robust system accepts BOTH:

  * a structured vessel profile (the JSON in the test brief), and
  * a free-text natural-language query ("Calculate all dues for the SUDESTADA,
    a 51,300 GT bulk carrier at Durban, alongside 3.4 days").

This module models the structured form and provides a light parser that maps a
vessel-profile JSON (as given in the brief) into the engine's VesselProfile.
Free-text parsing is delegated to the agent layer (an LLM turns prose into this
structured form), keeping deterministic mapping separate from probabilistic
language understanding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..calculation.engine import VesselProfile


@dataclass
class VesselQuery:
    """A request to calculate tariffs for a vessel at a port."""

    port: str
    vessel: VesselProfile
    vessel_name: Optional[str] = None
    tariffs: Optional[list[str]] = None  # None = all known tariffs


def vessel_profile_from_brief(payload: dict[str, Any]) -> VesselProfile:
    """Map the test-brief vessel JSON into the engine's VesselProfile.

    Accepts the nested structure from the brief:
        { "technical_specs": {"gross_tonnage": ..., "loa_meters": ...},
          "operational_data": {"days_alongside": ...} }
    and also a flat structure:
        { "gross_tonnage": ..., "loa_meters": ..., "chargeable_days": ... }

    chargeable_days falls back to days_alongside when not separately provided.
    """
    tech = payload.get("technical_specs", payload)
    ops = payload.get("operational_data", payload)

    gt = tech.get("gross_tonnage")
    if gt is None:
        raise ValueError("Vessel payload missing gross_tonnage.")

    loa = tech.get("loa_meters", 0.0) or 0.0
    chargeable_days = (
        payload.get("chargeable_days")
        if payload.get("chargeable_days") is not None
        else ops.get("days_alongside", 0.0)
    ) or 0.0

    return VesselProfile(
        gross_tonnage=float(gt),
        loa_meters=float(loa),
        chargeable_days=float(chargeable_days),
    )
