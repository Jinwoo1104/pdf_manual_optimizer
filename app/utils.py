from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def sanitize_filename(name: str, fallback: str = "manual") -> str:
    # Windows 금지 문자와 제어 문자를 제거하되 한글은 보존한다.
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = cleaned or fallback
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_file"
    return cleaned[:120]


def make_doc_id(title: str) -> str:
    normalized = sanitize_filename(title, fallback="manual").lower()
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "manual"


def write_json(path: str | Path, data: Any) -> None:
    with Path(path).open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def append_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False))
            file.write("\n")


def format_log(message: str) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    return f"[{now}] {message}"


def relative_to(base: Path, target: Path) -> str:
    return target.relative_to(base).as_posix()

