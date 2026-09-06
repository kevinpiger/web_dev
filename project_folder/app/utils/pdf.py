"""PDF introspection helpers. No DB access, no business rules."""

from pathlib import Path

from pypdf import PdfReader


def page_count(pdf_path: Path) -> int:
    reader = PdfReader(str(pdf_path))
    return len(reader.pages)
