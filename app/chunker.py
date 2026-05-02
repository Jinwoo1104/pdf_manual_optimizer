from __future__ import annotations

import re


def create_chunks(
    sections: list[dict],
    doc_id: str,
    doc_title: str,
    source_pdf: str,
    min_size: int = 1200,
    max_size: int = 1800,
) -> list[dict]:
    chunks: list[dict] = []

    for section in sections:
        pieces = _split_text(section.get("text", ""), min_size=min_size, max_size=max_size)
        for piece in pieces:
            chunk_number = len(chunks) + 1
            chunks.append(
                {
                    "chunk_id": f"{doc_id}_{chunk_number:04d}",
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "source_pdf": source_pdf,
                    "section": section.get("section_title", "전체 문서"),
                    "page_start": section.get("page_start", 1),
                    "page_end": section.get("page_end", section.get("page_start", 1)),
                    "keywords": [],
                    "summary": "",
                    "content": piece,
                }
            )

    return chunks


def _split_text(text: str, min_size: int, max_size: int) -> list[str]:
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= max_size:
        return [text]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if not current:
            current = paragraph
        elif len(current) + len(paragraph) + 2 <= max_size:
            current = f"{current}\n\n{paragraph}"
        else:
            if len(current) >= min_size:
                chunks.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}"
                chunks.extend(_hard_split(current, max_size))
                current = ""

    if current:
        chunks.extend(_hard_split(current, max_size))

    return chunks


def _hard_split(text: str, max_size: int) -> list[str]:
    if len(text) <= max_size:
        return [text]

    sentences = re.split(r"(?<=[.!?。！？다요함음임됨])\s+", text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_size:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(sentence[index : index + max_size] for index in range(0, len(sentence), max_size))
        elif len(current) + len(sentence) + 1 <= max_size:
            current = f"{current} {sentence}".strip()
        else:
            chunks.append(current.strip())
            current = sentence

    if current:
        chunks.append(current.strip())

    return chunks

