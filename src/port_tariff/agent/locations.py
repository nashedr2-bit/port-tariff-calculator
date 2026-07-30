"""
Tariff locations for the Transnet (South African ports) tariff document.

Maps each tariff type to the 1-based page range where its rules live, so the
extractor can send Gemini a focused excerpt rather than the whole document.

WHY THIS EXISTS (and why it is NOT "hardcoding the rules"):
This config points the agent at WHERE to look, not WHAT the answer is. The
rates, structures, and logic are still discovered by the LLM from the document
at runtime. For a new port's document, you provide a new locations map (or, in
a fully autonomous setup, a retrieval step finds the pages). The calculation
logic and extracted rates never get hardcoded.

Page ranges are generous by a page on each side so section content that spills
across a page boundary is still captured.
"""

from __future__ import annotations

from ..extraction.extractor import TariffLocation

# Transnet Tariff Book, April 2024 - March 2025 (bundled PDF).
# PDF page indices (1-based) confirmed during ingestion verification.
TRANSNET_TARIFF_LOCATIONS: dict[str, TariffLocation] = {
    "light_dues": TariffLocation("light_dues", page_start=5, page_end=6),
    "vts_dues": TariffLocation("vts_dues", page_start=6, page_end=7),
    "pilotage_dues": TariffLocation("pilotage_dues", page_start=7, page_end=8),
    "towage_dues": TariffLocation("towage_dues", page_start=8, page_end=9),
    # Running lines spans the berthing section (3.8, p9) AND the running-of-
    # lines table (3.9, p10). Both are included so the LLM can reason about
    # which structure reproduces the charge (berthing, per our validation).
    "running_lines": TariffLocation("running_lines", page_start=9, page_end=10),
    "port_dues": TariffLocation("port_dues", page_start=11, page_end=12),
}
