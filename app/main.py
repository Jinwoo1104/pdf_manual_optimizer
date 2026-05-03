from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from app.converter import ConvertOptions, convert_pdfs
    from app.prompt_builder import build_ai_prompt
    from app.searcher import find_chunks_jsonl_paths, load_chunks_from_paths, search_chunks
    from app.utils import format_log
except ImportError:
    from .converter import ConvertOptions, convert_pdfs
    from .prompt_builder import build_ai_prompt
    from .searcher import find_chunks_jsonl_paths, load_chunks_from_paths, search_chunks
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
        self.loaded_chunks: list[dict] = []
        self.search_results: list[dict] = []
        self.loaded_chunk_paths: list[Path] = []

        self.setWindowTitle("PDF Manual Optimizer - AI 검색용 패키지 변환기")
        self.resize(980, 720)
        self._build_ui()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_convert_tab(), "PDF 변환")
        tabs.addTab(self._build_search_tab(), "검색/프롬프트 생성")
        self.setCentralWidget(tabs)

    def _build_convert_tab(self) -> QWidget:
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

        return root

    def _build_search_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)

        title = QLabel("변환된 chunks.jsonl을 검색하고, AI에 붙여넣을 프롬프트를 생성합니다.")
        title.setWordWrap(True)
        layout.addWidget(title)

        load_row = QHBoxLayout()
        self.select_chunks_folder_button = QPushButton("변환 결과 폴더 선택")
        self.select_chunks_file_button = QPushButton("chunks.jsonl 선택")
        self.chunk_status_label = QLabel("로드된 chunk: 0개")
        self.chunk_status_label.setWordWrap(True)
        self.select_chunks_folder_button.clicked.connect(self.select_chunks_folder)
        self.select_chunks_file_button.clicked.connect(self.select_chunks_files)
        load_row.addWidget(self.select_chunks_folder_button)
        load_row.addWidget(self.select_chunks_file_button)
        load_row.addWidget(self.chunk_status_label, stretch=1)
        layout.addLayout(load_row)

        self.search_notice_label = QLabel("")
        self.search_notice_label.setWordWrap(True)
        layout.addWidget(self.search_notice_label)

        query_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("질문 또는 검색어를 입력하세요")
        self.search_button = QPushButton("검색")
        self.search_button.clicked.connect(self.run_search)
        self.query_input.returnPressed.connect(self.run_search)
        query_row.addWidget(self.query_input, stretch=1)
        query_row.addWidget(self.search_button)
        layout.addLayout(query_row)

        layout.addWidget(QLabel("검색 결과"))
        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(["score", "doc_title", "section", "pages", "summary"])
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.results_table, stretch=3)

        prompt_button_row = QHBoxLayout()
        self.generate_prompt_button = QPushButton("프롬프트 생성")
        self.copy_prompt_button = QPushButton("클립보드 복사")
        self.generate_prompt_button.setEnabled(False)
        self.copy_prompt_button.setEnabled(False)
        self.generate_prompt_button.clicked.connect(self.generate_prompt)
        self.copy_prompt_button.clicked.connect(self.copy_prompt)
        prompt_button_row.addWidget(self.generate_prompt_button)
        prompt_button_row.addWidget(self.copy_prompt_button)
        prompt_button_row.addStretch(1)
        layout.addLayout(prompt_button_row)

        layout.addWidget(QLabel("프롬프트 미리보기"))
        self.prompt_preview = QTextEdit()
        layout.addWidget(self.prompt_preview, stretch=3)

        return root

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

    def select_chunks_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "변환 결과 폴더 선택")
        if not directory:
            return
        paths = find_chunks_jsonl_paths(directory)
        if not paths:
            QMessageBox.warning(self, "chunks.jsonl 없음", "선택한 폴더에서 chunks.jsonl을 찾지 못했습니다.")
            return
        self.load_chunks(paths)

    def select_chunks_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "chunks.jsonl 선택",
            "",
            "JSONL Files (*.jsonl);;All Files (*.*)",
        )
        if not files:
            return
        self.load_chunks([Path(file_path) for file_path in files])

    def load_chunks(self, paths: list[Path]) -> None:
        try:
            self.loaded_chunks = load_chunks_from_paths(paths)
        except Exception as exc:
            QMessageBox.critical(self, "chunk 로드 실패", str(exc))
            return

        self.loaded_chunk_paths = list(paths)
        self.search_results = []
        self.results_table.setRowCount(0)
        self.prompt_preview.clear()
        self.generate_prompt_button.setEnabled(False)
        self.copy_prompt_button.setEnabled(False)
        self.update_chunk_status(paths)
        self.search_notice_label.setText(self.build_load_notice(paths))
        QMessageBox.information(self, "chunk 로드 완료", f"{len(self.loaded_chunks)}개 chunk를 로드했습니다.")

    def run_search(self) -> None:
        if not self.loaded_chunks:
            QMessageBox.warning(self, "chunk 필요", "먼저 chunks.jsonl을 로드하세요.")
            return
        query = self.query_input.text().strip()
        if not query:
            QMessageBox.warning(self, "검색어 필요", "질문 또는 검색어를 입력하세요.")
            return

        self.search_results = search_chunks(query, self.loaded_chunks, top_k=5)
        self.populate_results_table(self.search_results)
        if not self.search_results:
            self.prompt_preview.setPlainText("검색 결과가 없습니다.")
            self.search_notice_label.setText("검색 결과가 없습니다. 다른 표현이나 더 구체적인 키워드로 검색해보세요.")
            self.generate_prompt_button.setEnabled(False)
            self.copy_prompt_button.setEnabled(False)
            return

        top_score = int(self.search_results[0].get("score", 0))
        if top_score < 35:
            self.search_notice_label.setText("검색 결과의 관련성이 낮을 수 있습니다.")
        else:
            self.search_notice_label.setText("")
        self.generate_prompt_button.setEnabled(True)
        self.copy_prompt_button.setEnabled(False)

    def populate_results_table(self, results: list[dict]) -> None:
        self.results_table.setRowCount(len(results))
        for row, result in enumerate(results):
            values = [
                str(result.get("score", "")),
                str(result.get("doc_title", "")),
                str(result.get("section", "")),
                self.format_pages(result),
                str(result.get("summary", "")),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.results_table.setItem(row, column, item)
        self.results_table.resizeRowsToContents()

    def generate_prompt(self) -> None:
        if not self.search_results:
            self.run_search()
            if not self.search_results:
                return

        selected_results = self.get_selected_results()
        if not selected_results:
            selected_results = self.search_results[:5]

        prompt = build_ai_prompt(self.query_input.text(), selected_results, top_k=5)
        self.prompt_preview.setPlainText(prompt)
        self.copy_prompt_button.setEnabled(True)

    def copy_prompt(self) -> None:
        prompt = self.prompt_preview.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "프롬프트 없음", "먼저 프롬프트를 생성하세요.")
            return
        QApplication.clipboard().setText(prompt)
        QMessageBox.information(self, "복사 완료", "프롬프트를 클립보드에 복사했습니다.")

    def get_selected_results(self) -> list[dict]:
        rows = sorted({index.row() for index in self.results_table.selectedIndexes()})
        return [self.search_results[row] for row in rows if row < len(self.search_results)]

    def set_controls_enabled(self, enabled: bool) -> None:
        self.select_pdf_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.select_output_button.setEnabled(enabled)
        self.start_button.setEnabled(enabled)
        self.extract_tables_checkbox.setEnabled(enabled)
        self.extract_images_checkbox.setEnabled(enabled)

    def update_chunk_status(self, paths: list[Path]) -> None:
        doc_titles = sorted(
            {
                str(chunk.get("doc_title") or chunk.get("source_pdf") or "제목 없음")
                for chunk in self.loaded_chunks
            }
        )
        doc_text = ", ".join(doc_titles[:8])
        if len(doc_titles) > 8:
            doc_text += f" 외 {len(doc_titles) - 8}개"
        self.chunk_status_label.setText(
            f"로드된 chunk: {len(self.loaded_chunks)}개 / 파일 {len(paths)}개\n"
            f"문서: {doc_text or '없음'}"
        )

    def build_load_notice(self, paths: list[Path]) -> str:
        doc_count = len(
            {
                str(chunk.get("doc_title") or chunk.get("source_pdf") or "제목 없음")
                for chunk in self.loaded_chunks
            }
        )
        if len(paths) == 1 or doc_count == 1:
            return "현재 1개 매뉴얼만 검색 중입니다. 전체 매뉴얼 검색을 원하면 converted_manuals 폴더를 선택하세요."
        return ""

    def log(self, message: str) -> None:
        self.log_raw(format_log(message))

    def log_raw(self, message: str) -> None:
        self.log_edit.append(message)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    @staticmethod
    def format_pages(chunk: dict) -> str:
        page_start = chunk.get("page_start", "")
        page_end = chunk.get("page_end", page_start)
        if page_start == page_end:
            return str(page_start)
        return f"{page_start}-{page_end}"


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
