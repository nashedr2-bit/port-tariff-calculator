"""
Shared calculation primitives.

These are the low-level building blocks referenced by every tariff rule.
Defining them once, here, guarantees that (for example) the "per 100 tons
or part thereof" rounding is identical across light dues, port dues,
pilotage, towage and berthing. No duplicated arithmetic anywhere.
"""

from __future__ import annotations

import math


def blocks_per_100t(tonnage: float) -> int:
    """Number of '100 tons or part thereof' blocks.

    The phrase "per 100 tons or part thereof" appears throughout the tariff
    book (sections 1.1.1, 3.3, 3.6, 3.8, 4.1.1). "Or part thereof" means a
    partial block counts as a whole block -> always round UP.

    >>> blocks_per_100t(51300)
    513
    >>> blocks_per_100t(51301)
    514
    """
    if tonnage < 0:
        raise ValueError(f"Tonnage cannot be negative: {tonnage}")
    return math.ceil(tonnage / 100)


def metres_ceiling(loa_meters: float) -> int:
    """Length overall in whole metres, rounding up ('or part thereof').

    Used by per-metre light dues at a vessel's registered port
    (section 1.1.1, rate 24.64 per metre).
    """
    if loa_meters < 0:
        raise ValueError(f"Length cannot be negative: {loa_meters}")
    return math.ceil(loa_meters)


def apply_minimum(amount: float, minimum: float | None) -> float:
    """Floor an amount at a minimum fee, if one is defined."""
    if minimum is None:
        return amount
    return max(amount, minimum)
