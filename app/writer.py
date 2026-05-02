from __future__ import annotations

from pathlib import Path

from .utils import append_jsonl, write_json


def write_document_package(
    output_dir: str | Path,
    doc_id: str,
    doc_title: str,
    source_pdf: str,
    page_count: int,
    sections: list[dict],
    chunks: list[dict],
    tables: list[dict],
    images: list[dict],
    toc_pages: list[dict] | None = None,
) -> dict:
    output_dir = Path(output_dir)
    toc_pages = toc_pages or []

    _write_markdown(output_dir / "manual.md", doc_title, source_pdf, sections, tables, images, toc_pages)
    append_jsonl(output_dir / "chunks.jsonl", chunks)

    index = {
        "doc_id": doc_id,
        "doc_title": doc_title,
        "source_pdf": source_pdf,
        "page_count": page_count,
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "table_count": len(tables),
        "image_count": len(images),
        "sections": [
            {
                "title": section.get("section_title", "전체 문서"),
                "page_start": section.get("page_start", 1),
                "page_end": section.get("page_end", section.get("page_start", 1)),
            }
            for section in sections
        ],
        "toc": [
            {
                "page": toc_page.get("page", 1),
                "entries": toc_page.get("entries", []),
            }
            for toc_page in toc_pages
        ],
        "tables": tables,
        "images": images,
    }
    write_json(output_dir / "index.json", index)
    return index


def write_all_manuals_index(output_root: str | Path, indexes: list[dict]) -> Path:
    output_root = Path(output_root)
    converted_root = output_root / "converted_manuals"
    payload = {
        "manual_count": len(indexes),
        "manuals": indexes,
    }
    path = converted_root / "all_manuals_index.json"
    write_json(path, payload)
    return path


def _write_markdown(
    path: Path,
    doc_title: str,
    source_pdf: str,
    sections: list[dict],
    tables: list[dict],
    images: list[dict],
    toc_pages: list[dict],
) -> None:
    lines = [
        f"# {doc_title}",
        "",
        f"- 원본 PDF: {source_pdf}",
        f"- 섹션 수: {len(sections)}",
        f"- 표 수: {len(tables)}",
        f"- 이미지 수: {len(images)}",
        "",
    ]

    if toc_pages:
        lines.extend(["## 목차", ""])
        for toc_page in toc_pages:
            lines.extend(
                [
                    f"> page {toc_page.get('page', 1)}",
                    "",
                    toc_page.get("text", "").strip(),
                    "",
                ]
            )

    for section in sections:
        title = section.get("section_title", "전체 문서")
        page_start = section.get("page_start", 1)
        page_end = section.get("page_end", page_start)
        lines.extend(
            [
                f"## {title}",
                "",
                f"> pages {page_start}-{page_end}",
                "",
                section.get("text", "").strip(),
                "",
            ]
        )

    if tables:
        lines.extend(["## 추출된 표", ""])
        for table in tables:
            lines.append(f"- page {table['page']}: `{table['file']}` ({table['rows']}x{table['columns']})")
        lines.append("")

    if images:
        lines.extend(["## 추출된 이미지", ""])
        for image in images:
            lines.append(f"- page {image['page']}: `{image['file']}` - {image['description']}")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
