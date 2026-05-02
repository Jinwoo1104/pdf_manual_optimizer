from __future__ import annotations

import re
from dataclasses import dataclass, field


MAX_TITLE_LENGTH = 60
NUMBERED_TITLE_PATTERN = re.compile(r"^\s*[1-9]\d?(?:\.[1-9]\d?)*\.\s+.{2,60}$")
APPENDIX_TITLE_PATTERN = re.compile(r"^\s*부록\s*[A-Z가-힣]\.\s+.{2,60}$")
LOOSE_NUMBER_START_PATTERN = re.compile(r"^\s*\d")


@dataclass
class SectionSplitResult:
    sections: list[dict]
    rejected_title_candidates: list[str] = field(default_factory=list)
    toc_titles: list[str] = field(default_factory=list)
    toc_pages: list[dict] = field(default_factory=list)
    removed_duplicate_count: int = 0
    removed_duplicate_titles: list[str] = field(default_factory=list)


@dataclass
class TitleDecision:
    is_title: bool
    reject_reason: str | None = None
    skip_line: bool = False


def split_sections(
    pages: list[dict],
    default_title: str = "전체 문서",
    repeated_header_candidates: set[str] | list[str] | None = None,
) -> list[dict]:
    return split_sections_with_report(
        pages,
        default_title=default_title,
        repeated_header_candidates=repeated_header_candidates,
    ).sections


def split_sections_with_report(
    pages: list[dict],
    default_title: str = "전체 문서",
    repeated_header_candidates: set[str] | list[str] | None = None,
) -> SectionSplitResult:
    sections: list[dict] = []
    current: dict | None = None
    rejected_candidates: list[str] = []
    rejected_seen: set[str] = set()
    repeated_headers = {candidate.strip() for candidate in (repeated_header_candidates or [])}
    toc_titles = _extract_toc_titles(pages)
    toc_pages = _extract_toc_pages(pages)
    toc_page_numbers = {page["page"] for page in toc_pages}
    accepted_one_level_titles: set[str] = set()
    seen_titles: set[str] = set()

    for page in pages:
        page_number = page["page"]
        lines = page.get("text", "").splitlines()
        if page_number in toc_page_numbers:
            continue

        for line in lines:
            stripped = line.strip()
            decision = _classify_title(
                stripped,
                repeated_headers,
                accepted_one_level_titles,
                seen_titles,
                toc_titles,
            )
            if decision.is_title:
                if current:
                    current["text"] = current["text"].strip()
                    current["page_end"] = page_number
                    sections.append(current)
                current = {
                    "section_title": stripped,
                    "page_start": page_number,
                    "page_end": page_number,
                    "text": "",
                }
                seen_titles.add(stripped)
                if _is_one_level_title(stripped):
                    accepted_one_level_titles.add(stripped)
            elif (
                decision.reject_reason
                and decision.reject_reason not in {"repeated_header", "duplicate_chapter"}
                and stripped not in rejected_seen
            ):
                rejected_candidates.append(stripped)
                rejected_seen.add(stripped)

            if current and not decision.skip_line:
                current["text"] += line + "\n"

        if current:
            current["page_end"] = page_number
        elif page.get("text", "").strip():
            current = {
                "section_title": default_title,
                "page_start": page_number,
                "page_end": page_number,
                "text": page["text"] + "\n",
            }

    if current:
        current["text"] = current["text"].strip()
        sections.append(current)

    if not sections:
        sections = [
            {
                "section_title": default_title,
                "page_start": 1,
                "page_end": 1,
                "text": "",
            }
        ]

    deduped_sections, removed_duplicate_titles = deduplicate_sections(sections)

    return SectionSplitResult(
        sections=deduped_sections,
        rejected_title_candidates=rejected_candidates[:50],
        toc_titles=sorted(toc_titles),
        toc_pages=toc_pages,
        removed_duplicate_count=len(removed_duplicate_titles),
        removed_duplicate_titles=removed_duplicate_titles,
    )


def deduplicate_sections(sections: list[dict]) -> tuple[list[dict], list[str]]:
    deduped: list[dict] = []
    removed_titles: list[str] = []
    seen_title_pages: set[tuple[str, int]] = set()
    seen_chapter_titles: set[str] = set()

    for index, section in enumerate(sections):
        title = section.get("section_title", "전체 문서")
        page_start = int(section.get("page_start", 1))
        page_end = int(section.get("page_end", page_start))
        key = (title, page_start)
        chapter_key = _chapter_dedupe_key(title)

        if key in seen_title_pages:
            removed_titles.append(title)
            if deduped and _is_sparse_section(deduped[-1]):
                deduped[-1] = section
            continue

        if chapter_key and chapter_key in seen_chapter_titles:
            removed_titles.append(title)
            if deduped and deduped[-1].get("section_title") == title:
                deduped[-1]["text"] = _merge_section_text(deduped[-1].get("text", ""), section.get("text", ""))
                deduped[-1]["page_end"] = max(int(deduped[-1].get("page_end", page_end)), page_end)
            continue

        if deduped:
            previous = deduped[-1]
            previous_title = previous.get("section_title", "전체 문서")
            previous_end = int(previous.get("page_end", previous.get("page_start", page_start)))
            if title == previous_title and page_start <= previous_end + 1:
                removed_titles.append(title)
                if _is_sparse_section(previous) and not _is_sparse_section(section):
                    deduped[-1] = section
                else:
                    previous["text"] = _merge_section_text(previous.get("text", ""), section.get("text", ""))
                    previous["page_end"] = max(previous_end, page_end)
                continue

        if _is_sparse_section(section) and index + 1 < len(sections):
            next_title = sections[index + 1].get("section_title", "")
            if title == next_title:
                removed_titles.append(title)
                continue

        seen_title_pages.add(key)
        if chapter_key:
            seen_chapter_titles.add(chapter_key)
        deduped.append(section)

    return deduped, removed_titles


def _classify_title(
    line: str,
    repeated_headers: set[str],
    accepted_one_level_titles: set[str],
    seen_titles: set[str],
    toc_titles: set[str],
) -> TitleDecision:
    if not line:
        return TitleDecision(False)
    if len(line) > MAX_TITLE_LENGTH:
        return TitleDecision(False, "too_long")

    if line in repeated_headers and line in seen_titles and _is_strict_title_shape(line):
        return TitleDecision(False, "repeated_header", skip_line=True)

    if _is_appendix_title(line):
        return TitleDecision(True)

    if _is_numbered_title(line):
        if _is_one_level_title(line):
            # 반복 상단 헤더로 잡힌 1단계 장 제목은 첫 섹션 후보만 인정한다.
            if line in repeated_headers and line in seen_titles:
                return TitleDecision(False, "repeated_header", skip_line=True)
            if line in accepted_one_level_titles:
                return TitleDecision(False, "duplicate_chapter", skip_line=True)
        return TitleDecision(True)

    if line in toc_titles:
        return TitleDecision(True)

    if LOOSE_NUMBER_START_PATTERN.match(line) and _looks_like_fake_numeric_title(line):
        return TitleDecision(False, "fake_numeric")

    return TitleDecision(False)


def _extract_toc_titles(pages: list[dict], max_pages: int = 12) -> set[str]:
    titles: set[str] = set()

    for page in pages[:max_pages]:
        raw_lines = [line.strip() for line in page.get("text", "").splitlines() if line.strip()]
        has_toc_marker = any(_is_toc_marker(line) for line in raw_lines[:8])
        strict_title_lines = [_normalize_toc_line(line) for line in raw_lines]
        strict_count = sum(1 for line in strict_title_lines if _is_strict_title_shape(line))

        toc_line_count = sum(1 for line in raw_lines if _is_toc_line(line))
        if not has_toc_marker and strict_count < 4 and toc_line_count < 3:
            continue

        for line in strict_title_lines:
            if _is_strict_title_shape(line) and not _looks_like_table_row(line):
                titles.add(line)

    return titles


def _extract_toc_pages(pages: list[dict], max_pages: int = 12) -> list[dict]:
    toc_pages: list[dict] = []

    for page in pages[:max_pages]:
        text = page.get("text", "")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue

        has_toc_marker = any(_is_toc_marker(line) for line in lines[:8])
        toc_line_count = sum(1 for line in lines if _is_toc_line(line))
        title_like_count = sum(1 for line in lines if _is_strict_title_shape(_normalize_toc_line(line)))
        if has_toc_marker or toc_line_count >= 2 or (toc_line_count >= 1 and title_like_count >= 3):
            toc_pages.append(
                {
                    "page": page.get("page", 1),
                    "text": text.strip(),
                    "entries": [
                        _normalize_toc_line(line)
                        for line in lines
                        if _is_toc_line(line) and _is_strict_title_shape(_normalize_toc_line(line))
                    ],
                }
            )

    return toc_pages


def _normalize_toc_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"\s*\.{2,}\s*\d+\s*$", "", line)
    line = re.sub(r"\s+\d+\s*$", "", line)
    return line.strip()


def _is_toc_marker(line: str) -> bool:
    compact = re.sub(r"\s+", "", line).lower()
    return compact in {"목차", "목차.", "contents", "tableofcontents"} or compact.startswith("목차")


def _is_toc_line(line: str) -> bool:
    stripped = re.sub(r"\s+", " ", line).strip()
    if not stripped:
        return False
    if re.search(r"\.{3,}\s*\d+\s*$", stripped):
        return True
    if _is_strict_title_shape(_normalize_toc_line(stripped)) and re.search(r"\s+\d{1,4}\s*$", stripped):
        return True
    return False


def _is_strict_title_shape(line: str) -> bool:
    return _is_numbered_title(line) or _is_appendix_title(line)


def _is_numbered_title(line: str) -> bool:
    if not NUMBERED_TITLE_PATTERN.match(line):
        return False
    number_part, title_text = line.split(" ", 1)
    if _looks_like_decimal_number(number_part.rstrip(".")):
        return False
    if _starts_with_table_word(title_text):
        return False
    if _title_text_looks_like_table_row(title_text):
        return False
    return True


def _is_appendix_title(line: str) -> bool:
    return bool(APPENDIX_TITLE_PATTERN.match(line))


def _is_one_level_title(line: str) -> bool:
    match = re.match(r"^\s*[1-9]\d?\.\s+", line)
    return bool(match and line.count(".") == 1)


def _looks_like_decimal_number(number_text: str) -> bool:
    parts = number_text.split(".")
    return len(parts) == 2 and len(parts[1]) >= 3


def _looks_like_fake_numeric_title(line: str) -> bool:
    if re.match(r"^\s*(0|10|1000)\s+\S+", line):
        return True
    if re.match(r"^\s*\d+(?:\.\d+)?\s+\d", line):
        return True
    return _looks_like_table_row(line)


def _looks_like_table_row(line: str) -> bool:
    if len(line) > MAX_TITLE_LENGTH:
        return True
    number_tokens = re.findall(r"\d+(?:\.\d+)?", line)
    if len(number_tokens) >= 3:
        return True
    if re.search(r"\d{3,}\s+(단위|자리|구분|그룹)", line):
        return True
    if re.match(r"^\s*\d+(?:\.\d+)?\s+\d+(?:\.\d+)?", line):
        return True
    return False


def _title_text_looks_like_table_row(title_text: str) -> bool:
    cleaned = re.sub(r"\b[A-Z]\d+\b", "", title_text, flags=re.IGNORECASE)
    number_tokens = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if len(number_tokens) >= 2:
        return True
    if re.search(r"\d{3,}\s+(단위|자리|구분|그룹)", cleaned):
        return True
    if re.match(r"^(0|10|1000)\s+\S+", cleaned):
        return True
    return False


def _starts_with_table_word(title_text: str) -> bool:
    return bool(re.match(r"^(자리|진수|단위|구분|형식|값|숫자)\b", title_text.strip()))


def _body_without_title(section: dict) -> str:
    title = section.get("section_title", "").strip()
    lines = [line.strip() for line in section.get("text", "").splitlines() if line.strip()]
    if lines and lines[0] == title:
        lines = lines[1:]
    return "\n".join(lines).strip()


def _is_sparse_section(section: dict) -> bool:
    return len(_body_without_title(section)) < 20


def _merge_section_text(first: str, second: str) -> str:
    first = first.strip()
    second = second.strip()
    if not first:
        return second
    if not second:
        return first
    if second in first:
        return first
    return f"{first}\n\n{second}"


def _chapter_dedupe_key(title: str) -> str | None:
    if not _is_one_level_title(title):
        return None
    match = re.match(r"^\s*([1-9]\d?)\.\s+(.+)$", title)
    if not match:
        return None
    number, text = match.groups()
    text = re.sub(r"\s*[A-Z]\d+(?:\s*,\s*[A-Z]\d+)*\s*$", "", text, flags=re.IGNORECASE)
    return f"{number}. {text.strip()}"
