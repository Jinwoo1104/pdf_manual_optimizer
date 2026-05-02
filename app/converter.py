from __future__ import annotations

from pathlib import Path
from typing import Callable
from collections import Counter
from dataclasses import dataclass

from .chunker import create_chunks
from .cleaner import clean_pages_with_report
from .image_extractor import extract_images
from .keyword_extractor import enrich_chunks
from .section_splitter import split_sections_with_report
from .table_extractor import extract_tables
from .text_extractor import extract_text_pages
from .utils import ensure_dir, make_doc_id, sanitize_filename
from .writer import write_all_manuals_index, write_document_package

LogCallback = Callable[[str], None]
DEBUG_TARGET_TITLE = "2.1. 그룹 관리"


@dataclass
class ConvertOptions:
    include_toc_in_chunks: bool = False
    extract_tables: bool = True
    extract_images: bool = True
    small_table_filter: bool = True
    min_table_rows: int = 3
    min_image_width: int = 32
    min_image_height: int = 32
    debug: bool = False


def convert_pdf(
    pdf_path: str | Path,
    output_root: str | Path,
    log: LogCallback | None = None,
    options: ConvertOptions | None = None,
) -> dict:
    pdf_path = Path(pdf_path)
    output_root = Path(output_root)
    options = options or ConvertOptions()

    try:
        _log(log, f"변환 시작: {pdf_path.name}")
        extracted = extract_text_pages(pdf_path)
        if options.debug:
            _log_target_debug_raw(log, pdf_path.name, extracted["pages"])
        doc_title = extracted["title"]
        doc_id = make_doc_id(doc_title)
        folder_name = sanitize_filename(doc_title, fallback=pdf_path.stem)
        document_dir = ensure_dir(output_root / "converted_manuals" / folder_name)

        clean_result = clean_pages_with_report(extracted["pages"])
        pages = clean_result.pages
        if options.debug:
            _log_target_debug_clean(log, pdf_path.name, pages, clean_result.repeated_margin_lines)
        section_result = split_sections_with_report(
            pages,
            default_title=doc_title,
            repeated_header_candidates=set(clean_result.repeated_margin_lines),
        )
        sections = section_result.sections
        if options.debug:
            _log_target_debug_split(log, pdf_path.name, section_result)
        _log_repeated_headers(log, clean_result.repeated_margin_lines)
        _log(log, f"최종 섹션 수: {len(sections)}")
        _log_removed_duplicate_sections(
            log,
            section_result.removed_duplicate_count,
            section_result.removed_duplicate_titles,
        )
        _log_rejected_section_candidates(log, section_result.rejected_title_candidates)

        if options.extract_tables:
            tables, table_logs = extract_tables(
                pdf_path,
                document_dir,
                small_table_filter=options.small_table_filter,
                min_rows=options.min_table_rows,
            )
            for message in table_logs:
                _log(log, message)
            _log(log, f"표 추출 완료: {len(tables)}개")
        else:
            tables = []
            _log(log, "표 추출 건너뜀")

        if options.extract_images:
            images, image_logs = extract_images(
                pdf_path,
                document_dir,
                min_width=options.min_image_width,
                min_height=options.min_image_height,
            )
            for message in image_logs:
                _log(log, message)
            _log(log, f"이미지 추출 완료: {len(images)}개")
        else:
            images = []
            _log(log, "이미지 추출 건너뜀")

        chunk_sections = sections
        if options.include_toc_in_chunks and section_result.toc_pages:
            chunk_sections = _sections_with_toc(sections, section_result.toc_pages)
        chunks = create_chunks(
            sections=chunk_sections,
            doc_id=doc_id,
            doc_title=doc_title,
            source_pdf=pdf_path.name,
        )
        chunks = enrich_chunks(chunks)
        _log(log, f"최종 chunk 수: {len(chunks)}")
        _log_duplicate_sections(log, sections)

        index = write_document_package(
            output_dir=document_dir,
            doc_id=doc_id,
            doc_title=doc_title,
            source_pdf=pdf_path.name,
            page_count=extracted["page_count"],
            sections=sections,
            chunks=chunks,
            tables=tables,
            images=images,
            toc_pages=section_result.toc_pages,
        )
        if options.debug:
            _log_target_debug_index(log, pdf_path.name, index)

        result = {
            "success": True,
            "pdf": str(pdf_path),
            "output_dir": str(document_dir),
            "index": index,
            "message": f"변환 완료: {pdf_path.name}",
        }
        _log(log, result["message"])
        return result
    except Exception as exc:
        message = f"변환 실패: {pdf_path.name} - {exc}"
        _log(log, message)
        return {
            "success": False,
            "pdf": str(pdf_path),
            "output_dir": "",
            "index": None,
            "message": message,
        }


def convert_pdfs(
    pdf_paths: list[str | Path],
    output_root: str | Path,
    log: LogCallback | None = None,
    progress: Callable[[int, int], None] | None = None,
    options: ConvertOptions | None = None,
) -> dict:
    output_root = Path(output_root)
    ensure_dir(output_root / "converted_manuals")

    results: list[dict] = []
    indexes: list[dict] = []
    total = len(pdf_paths)

    for index, pdf_path in enumerate(pdf_paths, start=1):
        result = convert_pdf(pdf_path, output_root, log=log, options=options)
        results.append(result)
        if result.get("success") and result.get("index"):
            indexes.append(result["index"])
        if progress:
            progress(index, total)

    all_index_path = write_all_manuals_index(output_root, indexes)
    _log(log, f"통합 색인 저장 완료: {all_index_path}")

    return {
        "success_count": len(indexes),
        "failure_count": total - len(indexes),
        "results": results,
        "all_manuals_index": str(all_index_path),
        "output_root": str(output_root / "converted_manuals"),
    }


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)


def _log_repeated_headers(callback: LogCallback | None, repeated_headers: list[str]) -> None:
    if not repeated_headers:
        _log(callback, "제거된 반복 헤더 후보: 없음")
        return

    preview = ", ".join(repeated_headers[:20])
    suffix = f" 외 {len(repeated_headers) - 20}개" if len(repeated_headers) > 20 else ""
    _log(callback, f"제거된 반복 헤더 후보: {preview}{suffix}")


def _log_duplicate_sections(callback: LogCallback | None, sections: list[dict]) -> None:
    counter = Counter(section.get("section_title", "전체 문서") for section in sections)
    duplicated = [(title, count) for title, count in counter.most_common() if count > 1][:10]
    if not duplicated:
        _log(callback, "중복 섹션명 상위 10개: 없음")
        return

    summary = ", ".join(f"{title}({count})" for title, count in duplicated)
    _log(callback, f"중복 섹션명 상위 10개: {summary}")


def _log_rejected_section_candidates(callback: LogCallback | None, candidates: list[str]) -> None:
    if not candidates:
        _log(callback, "제외된 가짜 섹션 제목 후보: 없음")
        return

    preview = ", ".join(candidates[:20])
    suffix = f" 외 {len(candidates) - 20}개" if len(candidates) > 20 else ""
    _log(callback, f"제외된 가짜 섹션 제목 후보: {preview}{suffix}")


def _log_removed_duplicate_sections(callback: LogCallback | None, count: int, titles: list[str]) -> None:
    _log(callback, f"제거된 중복 섹션 수: {count}")
    if not titles:
        _log(callback, "제거된 중복 섹션 제목 목록: 없음")
        return

    unique_titles: list[str] = []
    for title in titles:
        if title not in unique_titles:
            unique_titles.append(title)

    preview = ", ".join(unique_titles[:20])
    suffix = f" 외 {len(unique_titles) - 20}개" if len(unique_titles) > 20 else ""
    _log(callback, f"제거된 중복 섹션 제목 목록: {preview}{suffix}")


def _sections_with_toc(sections: list[dict], toc_pages: list[dict]) -> list[dict]:
    toc_sections = [
        {
            "section_title": "목차",
            "page_start": toc_page.get("page", 1),
            "page_end": toc_page.get("page", 1),
            "text": toc_page.get("text", ""),
        }
        for toc_page in toc_pages
        if toc_page.get("text")
    ]
    return toc_sections + sections


def _should_debug_target(pdf_name: str) -> bool:
    return pdf_name.lower().startswith("administratorsmanual.ko")


def _log_target_debug_raw(callback: LogCallback | None, pdf_name: str, pages: list[dict]) -> None:
    if not _should_debug_target(pdf_name):
        return
    hit_pages = [page["page"] for page in pages if DEBUG_TARGET_TITLE in page.get("text", "")]
    _log(callback, f"[DEBUG] target title found in raw pages: {hit_pages or 'no'}")


def _log_target_debug_clean(
    callback: LogCallback | None,
    pdf_name: str,
    pages: list[dict],
    repeated_margin_lines: list[str],
) -> None:
    if not _should_debug_target(pdf_name):
        return
    hit_pages = [page["page"] for page in pages if DEBUG_TARGET_TITLE in page.get("text", "")]
    in_repeated = DEBUG_TARGET_TITLE in repeated_margin_lines
    _log(callback, f"[DEBUG] target title found after cleaner: {hit_pages or 'no'}")
    _log(callback, f"[DEBUG] target title in repeated margin headers: {'yes' if in_repeated else 'no'}")


def _log_target_debug_split(callback: LogCallback | None, pdf_name: str, section_result) -> None:
    if not _should_debug_target(pdf_name):
        return
    in_toc = DEBUG_TARGET_TITLE in section_result.toc_titles
    accepted = any(section.get("section_title") == DEBUG_TARGET_TITLE for section in section_result.sections)
    rejected = DEBUG_TARGET_TITLE in section_result.rejected_title_candidates
    removed = DEBUG_TARGET_TITLE in section_result.removed_duplicate_titles
    reason = "accepted" if accepted else "unknown"
    if rejected:
        reason = "fake_title"
    if removed:
        reason = "duplicate_or_empty_section"
    if DEBUG_TARGET_TITLE in getattr(section_result, "toc_titles", []):
        reason = reason if accepted else "toc_only_or_not_seen_as_body_title"

    _log(callback, f"[DEBUG] target title in toc_titles: {'yes' if in_toc else 'no'}")
    _log(callback, f"[DEBUG] target title accepted as section candidate: {'yes' if accepted else 'no'}")
    _log(callback, f"[DEBUG] target title rejected as fake section: {'yes' if rejected else 'no'}")
    _log(callback, f"[DEBUG] target title removed by deduplicate_sections: {'yes' if removed else 'no'}")
    _log(callback, f"[DEBUG] target title final splitter reason: {reason}")


def _log_target_debug_index(callback: LogCallback | None, pdf_name: str, index: dict) -> None:
    if not _should_debug_target(pdf_name):
        return
    exists = any(section.get("title") == DEBUG_TARGET_TITLE for section in index.get("sections", []))
    _log(callback, f"[DEBUG] target title in writer index.sections before save: {'yes' if exists else 'no'}")
