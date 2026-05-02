from __future__ import annotations

from pathlib import Path

import fitz

from .utils import ensure_dir, relative_to


def extract_images(
    pdf_path: str | Path,
    output_dir: str | Path,
    min_width: int = 32,
    min_height: int = 32,
) -> tuple[list[dict], list[str]]:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    images_dir = ensure_dir(output_dir / "images")
    results: list[dict] = []
    logs: list[str] = []

    try:
        with fitz.open(pdf_path) as document:
            for page_index, page in enumerate(document, start=1):
                try:
                    images = page.get_images(full=True)
                except Exception as exc:
                    logs.append(f"이미지 목록 추출 실패: page {page_index} - {exc}")
                    continue

                for image_index, image in enumerate(images, start=1):
                    try:
                        xref = image[0]
                        pixmap = fitz.Pixmap(document, xref)
                        if pixmap.alpha or pixmap.n > 4:
                            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                        if pixmap.width < min_width or pixmap.height < min_height:
                            logs.append(
                                f"작은 이미지 제외: page {page_index} image {image_index} "
                                f"({pixmap.width}x{pixmap.height})"
                            )
                            pixmap = None
                            continue
                        file_path = images_dir / f"page_{page_index:03d}_image_{image_index:02d}.png"
                        width = pixmap.width
                        height = pixmap.height
                        pixmap.save(file_path)
                        pixmap = None

                        results.append(
                            {
                                "page": page_index,
                                "file": relative_to(output_dir, file_path),
                                "caption": f"page {page_index} image {image_index}",
                                "description": f"PDF page {page_index}에 포함된 이미지",
                                "width": width,
                                "height": height,
                            }
                        )
                    except Exception as exc:
                        logs.append(f"이미지 저장 실패: page {page_index} image {image_index} - {exc}")
    except Exception as exc:
        logs.append(f"PDF 이미지 추출 초기화 실패: {exc}")

    return results, logs
