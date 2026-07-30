"""
API request/response models.

Pydantic models that define the HTTP contract for the /calculate endpoint.
Keeping these separate from the internal dataclasses gives us a stable public
API shape that is validated at the boundary, independent of internal changes.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class VesselSpec(BaseModel):
    """Vessel attributes accepted by the API.

    Accepts either flat fields or the nested test-brief structure via the
    /calculate endpoint's parser. Here we model the flat, explicit form.
    """

    gross_tonnage: float = Field(..., gt=0, description="Gross tonnage.")
    loa_meters: float = Field(0.0, ge=0, description="Length overall in metres.")
    chargeable_days: float = Field(
        0.0, ge=0, description="Chargeable days alongside (for time-based dues)."
    )
    name: Optional[str] = Field(None, description="Vessel name (optional).")


class CalculationRequest(BaseModel):
    """Body for POST /calculate.

    Two ways to specify the vessel and port:
      * structured: provide `port` + `vessel` (reliable, testable), or
      * natural language: provide `query` free-text, which is parsed by the LLM
        into the structured form.
    At least one mode must be supplied. Structured fields take precedence when
    both are present.
    """

    port: Optional[str] = Field(None, description="Port name, e.g. 'Durban'.")
    vessel: Optional[VesselSpec] = None
    tariffs: Optional[list[str]] = Field(
        None,
        description="Specific tariffs to calculate. Omit for all known tariffs.",
    )
    query: Optional[str] = Field(
        None,
        description="Natural-language query, e.g. 'all dues for the SUDESTADA, "
        "51300 GT at Durban, 3.4 days alongside'. Parsed by the LLM when the "
        "structured port/vessel fields are not provided.",
    )


class LineItemResponse(BaseModel):
    tariff_type: str
    amount: Optional[float]
    status: str
    source: Optional[str] = None
    services: Optional[int] = None
    notes: Optional[str] = None
    error: Optional[str] = None


class CalculationResponse(BaseModel):
    port: str
    vessel: Optional[str]
    currency: Optional[str]
    line_items: list[LineItemResponse]
    total: float

    @classmethod
    def from_report_dict(cls, d: dict[str, Any]) -> "CalculationResponse":
        return cls(
            port=d["port"],
            vessel=d.get("vessel"),
            currency=d.get("currency"),
            line_items=[LineItemResponse(**li) for li in d["line_items"]],
            total=d["total"],
        )
