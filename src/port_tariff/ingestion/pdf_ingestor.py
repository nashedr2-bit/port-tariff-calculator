"""
PDF ingestion layer.

Turns a dense, table-heavy port tariff PDF into a clean, structured
representation that the LLM extraction layer can read reliably.

Two complementary views are produced per page:
  * text   -- the linear text (good for prose rules like "charged once")
  * tables -- extracted tabular data (good for per-port rate tables)

We deliberately keep BOTH because tariff rules live in both forms: some are
plain sentences (light dues), others are dense multi-column tables (towage,
pilotage). Discarding either loses rules.

This layer is document-agnostic: it makes no assumptions about which port or
which tariffs are present. It simply produces faithful structured content for
the extraction layer to interpret.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


@dataclass
class ParsedPage:
    """One page's structured content."""

    page_number: int  # 1-based PDF page index
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)

    def table_count(self) -> int:
        return len(self.tables)

    def as_markdown(self) -> str:
        """Render page as markdown (text + tables) for LLM consumption.

        Tables become pipe-delimited markdown so the LLM sees column
        structure explicitly rather than as collapsed whitespace.
        """
        parts = [self.text.strip()]
        for i, table in enumerate(self.tables):
            parts.append(f"\n[TABLE {i + 1} on page {self.page_number}]")
            for row in table:
                cells = [(c or "").strip().replace("\n", " ") for c in row]
                parts.append("| " + " | ".join(cells) + " |")
        return "\n".join(parts)


@dataclass
class ParsedDocument:
    """The whole tariff document as structured pages."""

    source_path: str
    pages: list[ParsedPage]

    def page(self, n: int) -> ParsedPage:
        """1-based page access."""
        if n < 1 or n > len(self.pages):
            raise IndexError(
                f"Page {n} out of range (document has {len(self.pages)} pages)."
            )
        return self.pages[n - 1]

    def pages_in_range(self, start: int, end: int) -> list[ParsedPage]:
        """Inclusive 1-based range of pages."""
        return [self.page(n) for n in range(start, end + 1)]

    def full_markdown(self) -> str:
        return "\n\n".join(p.as_markdown() for p in self.pages)


class PdfIngestor:
    """Parses a PDF into a ParsedDocument."""

    def __init__(self) -> None:
        if pdfplumber is None:  # pragma: no cover
            raise ImportError(
                "pdfplumber is required for PDF ingestion. "
                "Install with: pip install pdfplumber"
            )

    def ingest(self, pdf_path: str | Path) -> ParsedDocument:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        pages: list[ParsedPage] = []
        with pdfplumber.open(str(path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                raw_tables = page.extract_tables() or []
                # normalise: ensure every cell is a str (pdfplumber may emit None)
                tables = [
                    [[cell if cell is not None else "" for cell in row] for row in tbl]
                    for tbl in raw_tables
                ]
                pages.append(
                    ParsedPage(page_number=idx, text=text, tables=tables)
                )

        return ParsedDocument(source_path=str(path), pages=pages)
