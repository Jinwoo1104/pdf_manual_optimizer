from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SEARCH_FIELDS = ("doc_title", "source_pdf", "section", "keywords", "summary", "content")
QUERY_STOPWORDS = {
    "없는",
    "없",
    "있는",
    "있",
    "테스트",
    "테스트입니다",
    "알려줘",
    "알려주세요",
    "기능",
    "무엇을",
    "무엇",
    "어떻게",
    "하나요",
    "있나요",
    "에서는",
    "에서",
    "으로",
    "하는",
    "하기",
}


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
        score, direct_hits = score_chunk_with_details(chunk, terms)
        if score <= 0:
            continue
        result = dict(chunk)
        result["score"] = score
        result["_direct_hits"] = direct_hits
        scored.append(result)

    scored.sort(
        key=lambda item: (
            item["score"],
            item.get("_direct_hits", 0),
            _content_term_frequency(item, terms),
            -len(str(item.get("content", ""))),
        ),
        reverse=True,
    )
    return scored[:top_k]


def score_chunk(chunk: dict[str, Any], terms: list[str]) -> int:
    return score_chunk_with_details(chunk, terms)[0]


def score_chunk_with_details(chunk: dict[str, Any], terms: list[str]) -> tuple[int, int]:
    score = 0
    direct_hits = 0
    doc_title = _as_text(chunk.get("doc_title", "")).lower()
    source_pdf = _as_text(chunk.get("source_pdf", "")).lower()
    section = _as_text(chunk.get("section", "")).lower()
    keywords = [_as_text(keyword).lower() for keyword in chunk.get("keywords", []) if _as_text(keyword)]
    summary = _as_text(chunk.get("summary", "")).lower()
    content = _as_text(chunk.get("content", "")).lower()

    for term in terms:
        lowered = term.lower()
        variants = _term_variants(lowered)
        if lowered in section:
            score += 8
        if any(lowered in keyword for keyword in keywords):
            score += 6
        summary_hits = _variant_frequency(summary, variants)
        content_hits = _variant_frequency(content, variants)
        section_hits = _variant_frequency(section, variants)
        if summary_hits:
            score += 4 + min(summary_hits * 2, 8)
            direct_hits += summary_hits
        if section_hits:
            score += min(section_hits * 2, 6)
            direct_hits += section_hits
        if lowered in doc_title:
            score += 3
        if lowered in source_pdf:
            score += 2
        if content_hits:
            # 같은 섹션 안에서는 본문 직접 일치가 chunk 순위를 가르는 핵심 신호다.
            score += 5 + min(content_hits * 2, 12)
            direct_hits += content_hits

        if _section_title_equals_term(section, lowered):
            score += 50

    matched_terms = sum(
        1
        for term in terms
        if _variant_frequency(f"{doc_title} {source_pdf} {section} {' '.join(keywords)} {summary} {content}", _term_variants(term.lower()))
    )
    if matched_terms == len(terms) and len(terms) > 1:
        score += 5
    content_matched_terms = sum(1 for term in terms if _variant_frequency(content, _term_variants(term.lower())))
    if content_matched_terms >= 2:
        score += content_matched_terms * 8
    distinct_matched_terms = sum(
        1
        for term in terms
        if _variant_frequency(f"{section} {' '.join(keywords)} {summary} {content}", _term_variants(term.lower()))
    )
    if distinct_matched_terms >= 2:
        score += distinct_matched_terms * 6
    if len(content.strip()) < 30:
        score -= 2
    return max(score, 0), direct_hits


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
        token = _normalize_query_token(token)
        if not token:
            continue
        if token in QUERY_STOPWORDS:
            continue
        if token not in unique:
            unique.append(token)
    return unique


def _normalize_query_token(token: str) -> str:
    if re.search(r"[가-힣]", token):
        token = re.sub(r"(입니다|합니다|인가요|하나요|나요|에서는|으로는|에게는|에서는|으로|에서|에게|부터|까지|처럼|보다|이나|거나|하고|은|는|을|를|이|가|와|과|에|의)$", "", token)
    return token


def _term_variants(term: str) -> list[str]:
    variants = [term]
    if re.search(r"[가-힣]", term):
        variants.extend(
            [
                f"{term}됨",
                f"{term}된",
                f"{term}하는",
                f"{term}한다",
                f"{term}하고",
                f"{term}하기",
                f"[{term}]",
            ]
        )
    return list(dict.fromkeys(variants))


def _variant_frequency(text: str, variants: list[str]) -> int:
    return sum(text.count(variant) for variant in variants if variant)


def _content_term_frequency(chunk: dict[str, Any], terms: list[str]) -> int:
    content = _as_text(chunk.get("content", "")).lower()
    return sum(_variant_frequency(content, _term_variants(term.lower())) for term in terms)


def _section_title_equals_term(section: str, term: str) -> bool:
    title = re.sub(r"^\d+(?:\.\d+)*\.\s+", "", section).strip().lower()
    return title == term


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_as_text(item) for item in value)
    return str(value)
