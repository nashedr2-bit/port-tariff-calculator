#!/usr/bin/env python3
"""
Live end-to-end demonstration against real Gemini.

Runs the FULL pipeline on the real Transnet PDF via the orchestrator:

    PDF ingest -> (per tariff) Gemini extracts rule -> validate -> engine
    calculates -> assemble itemised report -> compare to ground truth.

This is the end-to-end proof that the agent "finds" the rules itself, with no
hardcoded rule in the calculation path.

USAGE (on a machine with network access to Gemini):

    pip install -r requirements.txt
    export GEMINI_API_KEY="your-key-here"      # macOS / Linux
    #   $env:GEMINI_API_KEY="your-key-here"     # Windows PowerShell
    export PYTHONPATH=src
    python run_live_extraction.py

Your API key is read from the environment only. It is never written to disk,
never printed, never committed.
"""

from __future__ import annotations

import sys

from port_tariff.agent.locations import TRANSNET_TARIFF_LOCATIONS
from port_tariff.agent.orchestrator import TariffOrchestrator
from port_tariff.agent.query import VesselQuery
from port_tariff.calculation.engine import VesselProfile
from port_tariff.extraction.extractor import RuleExtractor
from port_tariff.extraction.llm_provider import GeminiProvider
from port_tariff.ingestion.pdf_ingestor import PdfIngestor

PDF_PATH = "data/port_tariff_transnet_2024.pdf"
PORT = "Durban"

VESSEL = VesselProfile(
    gross_tonnage=51300,
    loa_meters=229.2,
    chargeable_days=3.396,  # entrance-to-entrance basis; see README notes
)

GROUND_TRUTH = {
    "light_dues": 60062.04,
    "port_dues": 199549.22,
    "vts_dues": 33315.75,
    "pilotage_dues": 47189.94,
    "towage_dues": 147074.38,
    "running_lines": 19639.50,
}

REL_TOL = 1e-3  # 0.1% -- absorbs the documented VTS source-tonnage gap


def main() -> int:
    print("=" * 72)
    print("LIVE GEMINI PIPELINE  --  SUDESTADA @ Durban")
    print("=" * 72)

    try:
        llm = GeminiProvider(temperature=0.0)  # current default model
    except Exception as exc:  # noqa: BLE001
        print(f"\n[SETUP ERROR] Could not initialise Gemini: {exc}")
        print("Ensure GEMINI_API_KEY is set and google-genai is installed.")
        return 2

    print(f"Model: {llm.model_name}")
    print("Ingesting PDF ...")
    document = PdfIngestor().ingest(PDF_PATH)

    orchestrator = TariffOrchestrator(
        extractor=RuleExtractor(llm),
        locations=TRANSNET_TARIFF_LOCATIONS,
    )
    query = VesselQuery(
        port=PORT,
        vessel=VESSEL,
        vessel_name="SUDESTADA",
        tariffs=list(GROUND_TRUTH.keys()),
    )

    print("Running orchestrated extraction + calculation ...\n")
    report = orchestrator.run(document, query)

    passes = 0
    for li in report.line_items:
        print("-" * 72)
        print(f"TARIFF: {li.tariff_type}")
        if li.status != "ok":
            print(f"  [EXTRACTION ERROR] {li.error}")
            continue
        src = (
            f"section {li.source_section}, page {li.source_page}"
            if li.source_section
            else "n/a"
        )
        print(f"  source:     {src}   services={li.services}")
        if li.notes:
            print(f"  agent note: {li.notes}")
        expected = GROUND_TRUTH.get(li.tariff_type)
        if expected is None:
            print(f"  calculated: {li.amount:,.2f}")
            continue
        ok = abs(li.amount - expected) <= abs(expected) * REL_TOL
        passes += ok
        print(
            f"  calculated: {li.amount:>14,.2f}   ground truth: "
            f"{expected:>14,.2f}   [{'PASS' if ok else 'FAIL'}]"
        )

    print("\n" + "=" * 72)
    print(
        f"RESULT: {passes}/{len(GROUND_TRUTH)} tariffs match ground truth "
        f"within {REL_TOL:.1%}"
    )
    print(f"TOTAL (all extracted line items): {report.total:,.2f} {report.currency}")
    print("=" * 72)
    print(
        "\nNote: 'running_lines' is the one genuinely ambiguous tariff -- its\n"
        "ground-truth value comes from the BERTHING section (3.8), while a\n"
        "similarly-named 'Running of Vessel Lines' section (3.9) exists too.\n"
        "The agent resolves this by weighing charge structure over section title\n"
        "(see extraction rule 7) and reliably selects 3.8. See README for the\n"
        "full diagnosis and before/after measurement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
