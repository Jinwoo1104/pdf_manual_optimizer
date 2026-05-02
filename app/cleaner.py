from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


PAGE_NUMBER_PATTERNS = [
    re.compile(r"^\s*[-–—]?\s*\d+\s*[-–—]?\s*$"),
    re.compile(r"^\s*page\s+\d+(\s*/\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
    re.compile(r"^\s*[-–—]?\s*\d+\s*/\s*\d+\s*[-–—]?\s*$"),
]


@dataclass
class CleanResult:
    pages: list[dict]
    repeated_margin_lines: list[str] = field(default_factory=list)
    removed_margin_lines: list[str] = field(default_factory=list)


def clean_pages(pages: list[dict]) -> list[dict]:
    return clean_pages_with_report(pages).pages


def clean_pages_with_report(pages: list[dict]) -> CleanResult:
    repeated_lines = _find_repeated_short_lines(pages)
    repeated_margin_lines = _find_repeated_margin_lines(pages)
    seen_margin_counts: Counter[str] = Counter()
    removed_margin_lines: Counter[str] = Counter()
    cleaned_pages: list[dict] = []

    for page in pages:
        lines = page.get("text", "").splitlines()
        kept: list[str] = []
        margin_indexes = _margin_indexes(lines)

        for line_index, line in enumerate(lines):
            normalized = _normalize_line(line)
            if not normalized:
                kept.append("")
                continue
            if _is_page_number(normalized):
                continue
            if normalized in repeated_lines:
                removed_margin_lines[normalized] += 1
                continue
            if line_index in margin_indexes and normalized in repeated_margin_lines:
                if _looks_like_detail_section_title(normalized):
                    kept.append(normalized)
                    continue
                # 반복 헤더/푸터 후보의 첫 등장은 본문/목차일 수 있으므로 보존한다.
                allowed_occurrences = 2 if _looks_like_one_level_section_title(normalized) else 1
                if seen_margin_counts[normalized] >= allowed_occurrences:
                    removed_margin_lines[normalized] += 1
                    continue
                seen_margin_counts[normalized] += 1
            kept.append(normalized)

        cleaned_pages.append(
            {
                "page": page["page"],
                "text": _compact_text("\n".join(kept)),
            }
        )

    return CleanResult(
        pages=cleaned_pages,
        repeated_margin_lines=sorted(repeated_margin_lines),
        removed_margin_lines=[line for line, _ in removed_margin_lines.most_common()],
    )


def _find_repeated_short_lines(pages: list[dict]) -> set[str]:
    counter: Counter[str] = Counter()
    total_pages = max(len(pages), 1)

    for page in pages:
        page_lines = {
            _normalize_line(line)
            for line in page.get("text", "").splitlines()
            if 2 <= len(_normalize_line(line)) <= 80
            and not _looks_like_section_title(_normalize_line(line))
            and not _looks_like_body_sentence(_normalize_line(line))
        }
        counter.update(page_lines)

    threshold = max(3, int(total_pages * 0.45))
    return {line for line, count in counter.items() if count >= threshold}


def _find_repeated_margin_lines(pages: list[dict], margin_size: int = 2) -> set[str]:
    counter: Counter[str] = Counter()

    for page in pages:
        lines = [_normalize_line(line) for line in page.get("text", "").splitlines()]
        lines = [line for line in lines if line and not _is_page_number(line)]
        indexes = _margin_indexes(lines, margin_size=margin_size)
        page_margin_lines = {
            lines[index]
            for index in indexes
            if index < len(lines) and 2 <= len(lines[index]) <= 100
            and not _looks_like_body_sentence(lines[index])
        }
        counter.update(page_margin_lines)

    return {line for line, count in counter.items() if count >= 2}


def _margin_indexes(lines: list[str], margin_size: int = 2) -> set[int]:
    if not lines:
        return set()
    last_index = len(lines) - 1
    indexes = set(range(min(margin_size, len(lines))))
    indexes.update(range(max(0, last_index - margin_size + 1), last_index + 1))
    return indexes


def _normalize_line(line: str) -> str:
    return re.sub(r"[ \t\u00a0]+", " ", line).strip()


def _looks_like_section_title(line: str) -> bool:
    return bool(
        re.match(r"^\d+(?:\.\d+)*\.?\s+.{2,90}$", line)
        or re.match(r"^부록\s*[A-Z가-힣]\.\s+.{2,90}$", line)
    )


def _looks_like_detail_section_title(line: str) -> bool:
    return bool(
        re.match(r"^\d+\.\d+(?:\.\d+)*\.?\s+.{2,90}$", line)
        or re.match(r"^부록\s*[A-Z가-힣]\.\s+.{2,90}$", line)
    )


def _looks_like_one_level_section_title(line: str) -> bool:
    return bool(re.match(r"^\d+\.\s+.{2,90}$", line)) and not _looks_like_detail_section_title(line)


def _looks_like_body_sentence(line: str) -> bool:
    if len(line) <= 1:
        return True
    if re.match(r"^\d+\)\s+.+(다|된다|한다|간다|한다\.)\.?$", line):
        return True
    if re.search(r"(다|된다|한다|간다|합니다|십시오|하세요)\.?$", line):
        return True
    if len(line) <= 4 and re.search(r"(다|됨|함)\.?$", line):
        return True
    return False


def _is_page_number(line: str) -> bool:
    return any(pattern.match(line) for pattern in PAGE_NUMBER_PATTERNS)


def _compact_text(text: str) -> str:
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
