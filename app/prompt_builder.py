from __future__ import annotations

from typing import Any


def build_ai_prompt(
    question: str,
    results: list[dict[str, Any]],
    top_k: int = 5,
    max_content_chars: int = 1200,
    max_prompt_chars: int = 12000,
) -> str:
    question = question.strip()
    selected = results[:top_k]

    lines = [
        "아래 매뉴얼 발췌를 근거로 사용자 질문에 답변하세요.",
        "근거에 없는 내용은 추측하지 마세요.",
        "답변에는 문서명, 섹션명, 페이지 범위를 함께 제시하세요.",
        "",
        "[사용자 질문]",
        question or "(질문이 입력되지 않았습니다.)",
        "",
        "[관련 매뉴얼 발췌]",
    ]

    if not selected:
        lines.extend(["관련 chunk가 선택되지 않았습니다.", ""])
        return "\n".join(lines).strip() + "\n"

    for index, chunk in enumerate(selected, start=1):
        content = _truncate(str(chunk.get("content", "")).strip(), max_content_chars)
        summary = str(chunk.get("summary", "")).strip()
        pages = _format_pages(chunk)
        lines.extend(
            [
                f"{index}.",
                f"문서명: {chunk.get('doc_title', '')}",
                f"원본 PDF: {chunk.get('source_pdf', '')}",
                f"섹션: {chunk.get('section', '')}",
                f"페이지: {pages}",
                f"요약: {summary}",
                "내용:",
                content,
                "",
            ]
        )

        current = "\n".join(lines).strip() + "\n"
        if len(current) > max_prompt_chars:
            lines = _trim_to_limit(lines, max_prompt_chars)
            break

    return "\n".join(lines).strip() + "\n"


def _format_pages(chunk: dict[str, Any]) -> str:
    page_start = chunk.get("page_start", "")
    page_end = chunk.get("page_end", page_start)
    if page_start == page_end:
        return str(page_start)
    return f"{page_start}-{page_end}"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _trim_to_limit(lines: list[str], max_prompt_chars: int) -> list[str]:
    text = "\n".join(lines)
    if len(text) <= max_prompt_chars:
        return lines

    trimmed = text[: max_prompt_chars - 80].rstrip()
    trimmed += "\n\n[일부 발췌는 프롬프트 길이 제한으로 생략되었습니다.]"
    return trimmed.splitlines()
