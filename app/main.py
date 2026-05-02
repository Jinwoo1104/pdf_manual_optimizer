from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from app.converter import ConvertOptions, convert_pdfs
    from app.utils import format_log
except ImportError:
    from .converter import ConvertOptions, convert_pdfs
    from .utils import format_log


class ConvertWorker(QObject):
    log_message = Signal(str)
    progress_changed = Signal(int)
    finished = Signal(dict)

    def __init__(self, pdf_paths: list[str], output_dir: str, options: ConvertOptions) -> None:
        super().__init__()
        self.pdf_paths = pdf_paths
        self.output_dir = output_dir
        self.options = options

    def run(self) -> None:
        def emit_log(message: str) -> None:
            self.log_message.emit(format_log(message))

        def emit_progress(done: int, total: int) -> None:
            percent = int(done / total * 100) if total else 0
            self.progress_changed.emit(percent)

        result = convert_pdfs(
            self.pdf_paths,
            self.output_dir,
            log=emit_log,
            progress=emit_progress,
            options=self.options,
        )
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.pdf_paths: list[str] = []
        self.output_dir = ""
        self.thread: QThread | None = None
        self.worker: ConvertWorker | None = None

        self.setWindowTitle("PDF Manual Optimizer - AI 검색용 패키지 변환기")
        self.resize(860, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        title = QLabel("회사 매뉴얼 PDF를 Markdown, JSONL, Index 기반 AI 검색용 패키지로 변환합니다.")
        title.setWordWrap(True)
        layout.addWidget(title)

        button_row = QHBoxLayout()
        self.select_pdf_button = QPushButton("PDF 파일 선택")
        self.clear_button = QPushButton("PDF 목록 초기화")
        self.select_output_button = QPushButton("저장 위치 선택")
        self.start_button = QPushButton("변환 시작")

        self.select_pdf_button.clicked.connect(self.select_pdfs)
        self.clear_button.clicked.connect(self.clear_pdfs)
        self.select_output_button.clicked.connect(self.select_output_dir)
        self.start_button.clicked.connect(self.start_conversion)

        for button in [
            self.select_pdf_button,
            self.clear_button,
            self.select_output_button,
            self.start_button,
        ]:
            button_row.addWidget(button)
        layout.addLayout(button_row)

        self.output_label = QLabel("저장 위치: 선택되지 않음")
        self.output_label.setWordWrap(True)
        layout.addWidget(self.output_label)

        option_row = QHBoxLayout()
        self.extract_tables_checkbox = QCheckBox("표 추출")
        self.extract_images_checkbox = QCheckBox("이미지 추출")
        self.extract_tables_checkbox.setChecked(True)
        self.extract_images_checkbox.setChecked(True)
        option_row.addWidget(self.extract_tables_checkbox)
        option_row.addWidget(self.extract_images_checkbox)
        option_row.addStretch(1)
        layout.addLayout(option_row)

        layout.addWidget(QLabel("선택된 PDF 목록"))
        self.pdf_list = QListWidget()
        layout.addWidget(self.pdf_list, stretch=2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("변환 로그"))
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, stretch=3)

        self.setCentralWidget(root)

    def select_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "PDF 파일 선택",
            "",
            "PDF Files (*.pdf)",
        )
        if not files:
            return

        existing = set(self.pdf_paths)
        for file_path in files:
            if file_path not in existing:
                self.pdf_paths.append(file_path)
                self.pdf_list.addItem(file_path)
        self.log(f"{len(files)}개 PDF 선택됨")

    def clear_pdfs(self) -> None:
        self.pdf_paths.clear()
        self.pdf_list.clear()
        self.progress_bar.setValue(0)
        self.log("PDF 목록 초기화 완료")

    def select_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "저장 위치 선택")
        if not directory:
            return
        self.output_dir = directory
        self.output_label.setText(f"저장 위치: {directory}")
        self.log(f"저장 위치 선택: {directory}")

    def start_conversion(self) -> None:
        if not self.pdf_paths:
            QMessageBox.warning(self, "PDF 필요", "변환할 PDF 파일을 먼저 선택하세요.")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "저장 위치 필요", "변환 결과를 저장할 위치를 선택하세요.")
            return

        self.set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.log("변환 작업을 시작합니다.")

        self.thread = QThread()
        options = ConvertOptions(
            extract_tables=self.extract_tables_checkbox.isChecked(),
            extract_images=self.extract_images_checkbox.isChecked(),
        )
        self.worker = ConvertWorker(self.pdf_paths.copy(), self.output_dir, options)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log_message.connect(self.log_raw)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_conversion_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_conversion_finished(self, result: dict) -> None:
        self.set_controls_enabled(True)
        self.progress_bar.setValue(100)
        output_root = result.get("output_root", str(Path(self.output_dir) / "converted_manuals"))
        self.log(
            f"변환 완료: 성공 {result.get('success_count', 0)}개, 실패 {result.get('failure_count', 0)}개"
        )
        self.log(f"출력 폴더: {output_root}")
        QMessageBox.information(self, "변환 완료", f"변환이 완료되었습니다.\n\n출력 폴더:\n{output_root}")
        self.thread = None
        self.worker = None

    def set_controls_enabled(self, enabled: bool) -> None:
        self.select_pdf_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.select_output_button.setEnabled(enabled)
        self.start_button.setEnabled(enabled)
        self.extract_tables_checkbox.setEnabled(enabled)
        self.extract_images_checkbox.setEnabled(enabled)

    def log(self, message: str) -> None:
        self.log_raw(format_log(message))

    def log_raw(self, message: str) -> None:
        self.log_edit.append(message)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
