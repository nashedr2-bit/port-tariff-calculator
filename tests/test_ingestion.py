"""Tests for the PDF ingestion layer.

These use the bundled Transnet tariff PDF to verify that ingestion produces
faithful structured content -- specifically that key rate values survive
extraction, since everything downstream depends on them being present.
"""

from pathlib import Path

import pytest

from port_tariff.ingestion.pdf_ingestor import ParsedPage, PdfIngestor

DATA = Path(__file__).parent.parent / "data" / "port_tariff_transnet_2024.pdf"

pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="Sample tariff PDF not present."
)


@pytest.fixture(scope="module")
def document():
    return PdfIngestor().ingest(DATA)


def test_all_pages_ingested(document):
    assert len(document.pages) == 27


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        PdfIngestor().ingest("does/not/exist.pdf")


def test_out_of_range_page_raises(document):
    with pytest.raises(IndexError):
        document.page(999)


def test_key_rate_values_survive_extraction(document):
    """Each critical Durban rate must appear in its expected page's content.
    If these vanish, the LLM has nothing to extract."""
    full = document.full_markdown()
    for value in ["117.08", "192.73", "57.79", "18 608.61", "73 118.07", "2 801.91"]:
        assert value in full, f"Rate {value} missing from ingested document."


def test_markdown_renders_tables(document):
    """Pilotage page should render at least one markdown table block."""
    md = document.page(7).as_markdown()
    assert "[TABLE" in md
    assert "|" in md


def test_parsed_page_markdown_roundtrip():
    page = ParsedPage(
        page_number=1,
        text="Some rule text.",
        tables=[[["Port", "Rate"], ["Durban", "0.65"]]],
    )
    md = page.as_markdown()
    assert "Some rule text." in md
    assert "| Port | Rate |" in md
    assert "| Durban | 0.65 |" in md
