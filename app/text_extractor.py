from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz


def extract_text_pages(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    pages: list[dict[str, Any]] = []

    with fitz.open(pdf_path) as document:
        metadata = document.metadata or {}
        title = (metadata.get("title") or "").strip()

        for index, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True) or ""
            pages.append({"page": index, "text": text})

        return {
            "title": title or pdf_path.stem,
            "page_count": document.page_count,
            "pages": pages,
        }

