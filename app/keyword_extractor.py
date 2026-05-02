from __future__ import annotations

import re
from collections import Counter


PRIORITY_TERMS = [
    "로그인",
    "암호",
    "비밀번호",
    "관리자",
    "사용자",
    "설정",
    "오류",
    "검토",
    "승인",
    "페이지",
    "템플릿",
    "권한",
    "저장",
    "삭제",
    "등록",
    "조회",
    "검색",
    "시스템",
    "메뉴",
    "보고서",
]

STOPWORDS = {"그리고", "그러나", "입니다", "합니다", "대한", "위한", "에서", "으로", "또는", "있는", "없는"}


def enrich_chunks(chunks: list[dict]) -> list[dict]:
    for chunk in chunks:
        chunk["keywords"] = extract_keywords(chunk.get("section", ""), chunk.get("content", ""))
        chunk["summary"] = summarize(chunk.get("section", ""), chunk.get("content", ""))
    return chunks


def extract_keywords(section_title: str, content: str, limit: int = 10) -> list[str]:
    candidates: list[str] = []

    candidates.extend(_tokenize(section_title))
    for term in PRIORITY_TERMS:
        if term in section_title or term in content:
            candidates.append(term)

    words = _tokenize(content)
    counter = Counter(word for word in words if word not in STOPWORDS and len(word) >= 2)
    candidates.extend(word for word, _ in counter.most_common(20))

    unique: list[str] = []
    for word in candidates:
        if word not in unique and len(word) >= 2:
            unique.append(word)
        if len(unique) >= limit:
            break

    return unique


def summarize(section_title: str, content: str, max_length: int = 180) -> str:
    sentences = _split_sentences(content)
    base = " ".join(sentences[:3]).strip()
    if section_title and base:
        summary = f"{section_title}: {base}"
    else:
        summary = base or section_title or "본문 내용이 비어 있습니다."

    if len(summary) > max_length:
        summary = summary[: max_length - 1].rstrip() + "..."
    return summary


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text)


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?。！？다요함음임됨])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]

