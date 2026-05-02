from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SEARCH_FIELDS = ("doc_title", "source_pdf", "section", "keywords", "summary", "content")


def find_chunks_jsonl_paths(folder: str | Path) -> list[Path]:
    root = Path(folder)
    candidates = [
        root / "chunks.jsonl",
        *root.glob("*/chunks.jsonl"),
        *root.glob("converted_manuals/*/chunks.jsonl"),
    ]

    seen: set[Path] = set()
    paths: list[Path] = []
    for path in candidates:
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(path)
    return sorted(paths, key=lambda item: str(item).lower())


def load_chunks_jsonl(path: str | Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                chunk = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} line {line_number}: JSON 파싱 실패 - {exc}") from exc
            if isinstance(chunk, dict):
                chunks.append(_normalize_chunk(chunk))
    return chunks


def load_chunks_from_paths(paths: list[str | Path]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in paths:
        chunks.extend(load_chunks_jsonl(path))
    return chunks


def search_chunks(query: str, chunks: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    terms = _tokenize(query)
    if not terms:
        return []

    scored: list[dict[str, Any]] = []
    for chunk in chunks:
        score = score_chunk(chunk, terms)
        if score <= 0:
            continue
        result = dict(chunk)
        result["score"] = score
        scored.append(result)

    scored.sort(
        key=lambda item: (
            item["score"],
            len(str(item.get("summary", ""))),
            -len(str(item.get("content", ""))),
        ),
        reverse=True,
    )
    return scored[:top_k]


def score_chunk(chunk: dict[str, Any], terms: list[str]) -> int:
    score = 0
    doc_title = _as_text(chunk.get("doc_title", "")).lower()
    source_pdf = _as_text(chunk.get("source_pdf", "")).lower()
    section = _as_text(chunk.get("section", "")).lower()
    keywords = [_as_text(keyword).lower() for keyword in chunk.get("keywords", []) if _as_text(keyword)]
    summary = _as_text(chunk.get("summary", "")).lower()
    content = _as_text(chunk.get("content", "")).lower()

    for term in terms:
        lowered = term.lower()
        if lowered in section:
            score += 8
        if any(lowered in keyword for keyword in keywords):
            score += 6
        if lowered in summary:
            score += 4
        if lowered in doc_title:
            score += 3
        if lowered in source_pdf:
            score += 2
        score += min(content.count(lowered), 5)

    matched_terms = sum(
        1
        for term in terms
        if term.lower() in f"{doc_title} {source_pdf} {section} {' '.join(keywords)} {summary} {content}"
    )
    if matched_terms == len(terms) and len(terms) > 1:
        score += 5
    if len(content.strip()) < 30:
        score -= 2
    return max(score, 0)


def _normalize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    normalized = {field: chunk.get(field, "" if field != "keywords" else []) for field in SEARCH_FIELDS}
    normalized["chunk_id"] = chunk.get("chunk_id", "")
    normalized["page_start"] = chunk.get("page_start", 1)
    normalized["page_end"] = chunk.get("page_end", normalized["page_start"])
    if not isinstance(normalized["keywords"], list):
        normalized["keywords"] = [_as_text(normalized["keywords"])]
    return normalized


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", text)
    unique: list[str] = []
    for token in tokens:
        if token not in unique:
            unique.append(token)
    return unique


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_as_text(item) for item in value)
    return str(value)

