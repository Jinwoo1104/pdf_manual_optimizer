from __future__ import annotations

from pathlib import Path

import pandas as pd
import pdfplumber

from .utils import ensure_dir, relative_to


def extract_tables(
    pdf_path: str | Path,
    output_dir: str | Path,
    small_table_filter: bool = True,
    min_rows: int = 3,
) -> tuple[list[dict], list[str]]:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    tables_dir = ensure_dir(output_dir / "tables")
    results: list[dict] = []
    logs: list[str] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                try:
                    page_tables = page.extract_tables() or []
                except Exception as exc:
                    logs.append(f"표 추출 실패: page {page_index} - {exc}")
                    continue

                for table_index, table in enumerate(page_tables, start=1):
                    if not table:
                        continue

                    max_columns = max(len(row or []) for row in table)
                    rows = [(row or []) + [""] * (max_columns - len(row or [])) for row in table]
                    if small_table_filter and len(rows) < min_rows:
                        logs.append(f"작은 표 제외: page {page_index} table {table_index} ({len(rows)}행)")
                        continue
                    dataframe = pd.DataFrame(rows)
                    file_path = tables_dir / f"page_{page_index:03d}_table_{table_index:02d}.csv"
                    dataframe.to_csv(file_path, index=False, header=False, encoding="utf-8-sig")

                    results.append(
                        {
                            "page": page_index,
                            "file": relative_to(output_dir, file_path),
                            "rows": len(rows),
                            "columns": max_columns,
                        }
                    )
    except Exception as exc:
        logs.append(f"PDF 표 추출 초기화 실패: {exc}")

    return results, logs
