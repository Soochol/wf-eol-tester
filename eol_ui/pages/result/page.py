from __future__ import annotations

from typing import List

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eol_ui.runner import RunOutcome, Verdict
from eol_ui.widgets import Badge, RangeBar, card, format_duration, format_number, label, set_property
from eol_ui.widgets.basics import DASH, verdict_kind

_BANNER_TITLE = {
    Verdict.PASS: "PASS",
    Verdict.FAIL: "FAIL",
    Verdict.ABORTED: "중단됨",
    Verdict.ERROR: "오류",
}
_ABORTED_TEXT = "사용자 요청으로 중단되었습니다. Teardown을 실행했습니다."
NO_RESULTS_TEXT = "저장된 결과 없음"
_COLUMNS = ("온도", "위치", "Force", "범위", "판정")


def _padded(widget: QWidget, center: bool = False) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(8, 4, 8, 4)
    if center:
        layout.addStretch(1)
    layout.addWidget(widget)
    if center:
        layout.addStretch(1)
    return holder


class ResultPage(QWidget):
    next_requested = Signal(str)
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._outcome: RunOutcome | None = None

        self._banner = QFrame()
        self._banner.setObjectName("banner")
        self._banner_title = label("", "banner-title")
        self._banner_title.setObjectName("banner-title")
        self._banner_summary = label("", "banner-text")
        self._banner_summary.setObjectName("banner-summary")
        self._banner_detail = label("", "banner-text")
        self._banner_detail.setObjectName("banner-detail")
        self._banner_detail.setWordWrap(True)
        banner_layout = QVBoxLayout(self._banner)
        banner_layout.addWidget(self._banner_title)
        banner_layout.addWidget(self._banner_summary)
        banner_layout.addWidget(self._banner_detail)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setObjectName("result-table")
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(40)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setShowGrid(False)

        self._files = QListWidget()
        self._files.setObjectName("result-files")
        self._no_results = label(NO_RESULTS_TEXT, "muted")
        self._no_results.setObjectName("no-results")
        self._folder = label("", "muted")
        self._folder.setObjectName("results-folder")
        self._open_folder = QPushButton("결과 폴더 열기")
        self._open_folder.setObjectName("open-folder-button")
        self._open_folder.clicked.connect(self._open_results_folder)
        self._teardown = label("")
        self._teardown.setObjectName("teardown-result")

        self._next_serial = QLineEdit()
        self._next_serial.setObjectName("next-serial-input")
        self._next_serial.setPlaceholderText("다음 DUT 시리얼 번호")
        self._next = QPushButton("다음 테스트 시작")
        self._next.setObjectName("next-button")
        self._next.setProperty("primary", True)
        self._back = QPushButton("실행 화면으로")
        self._back.setObjectName("back-button")
        self._next_serial.textChanged.connect(self._sync_next)
        self._next_serial.returnPressed.connect(self._request_next)
        self._next.clicked.connect(self._request_next)
        self._back.clicked.connect(self.back_requested)

        results = card()
        results_layout = QVBoxLayout(results)
        results_layout.addWidget(label("측정 결과", "title"))
        results_layout.addWidget(self._table, 1)

        side = card()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(label("저장된 결과", "title"))
        side_layout.addWidget(self._folder)
        side_layout.addWidget(self._files, 1)
        side_layout.addWidget(self._no_results)
        side_layout.addWidget(self._open_folder)
        side_layout.addWidget(label("Teardown 결과", "title"))
        side_layout.addWidget(self._teardown)

        footer = card()
        footer_layout = QHBoxLayout(footer)
        footer_layout.addWidget(self._next_serial, 1)
        footer_layout.addWidget(self._next)
        footer_layout.addWidget(self._back)

        body = QHBoxLayout()
        body.addWidget(results, 3)
        body.addWidget(side, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(self._banner)
        layout.addLayout(body, 1)
        layout.addWidget(footer)
        self._sync_next()

    def show_outcome(self, outcome: RunOutcome) -> None:
        self._outcome = outcome
        passed = sum(1 for m in outcome.measurements if m.passed)
        total = len(outcome.measurements)
        set_property(self._banner, "banner", outcome.verdict.value)
        self._banner_title.setText(_BANNER_TITLE[outcome.verdict])
        elapsed = (outcome.finished_at - outcome.started_at).total_seconds()
        self._banner_summary.setText(
            f"SN {outcome.serial_number} · WIP {outcome.wip_id or DASH} · "
            f"소요 {format_duration(elapsed)} · {passed}/{total} PASS"
        )
        self._banner_detail.setText(self._detail_text(outcome))
        self._banner_detail.setVisible(bool(self._banner_detail.text()))
        self._fill_table(outcome)
        self._fill_files(outcome)
        self._teardown.setText(self._teardown_text(outcome))
        self._next_serial.clear()
        self._next_serial.setFocus()

    @staticmethod
    def _detail_text(outcome: RunOutcome) -> str:
        if outcome.verdict is Verdict.ERROR:
            return outcome.error or ""
        if outcome.verdict is Verdict.ABORTED:
            return _ABORTED_TEXT
        return ""

    def _fill_table(self, outcome: RunOutcome) -> None:
        self._table.setRowCount(0)
        for record in outcome.measurements:
            row = self._table.rowCount()
            self._table.insertRow(row)
            cells = (
                format_number(record.temperature, "°C"),
                format_number(record.position, " µm", 0),
                format_number(record.force, " kgf", 3),
            )
            for column, text in enumerate(cells):
                self._table.setItem(row, column, QTableWidgetItem(text))
            if record.force is None:
                range_cell: QWidget = label(DASH, "muted")
            else:
                range_cell = RangeBar()
                range_cell.show_value(record.force, record.min_value, record.max_value)
            self._table.setCellWidget(row, 3, _padded(range_cell))
            kind = verdict_kind(record.passed)
            self._table.setCellWidget(row, 4, _padded(Badge(kind, kind), center=True))

    def _fill_files(self, outcome: RunOutcome) -> None:
        self._files.clear()
        directory = outcome.results_dir
        for path in outcome.result_files:
            self._files.addItem(str(path.relative_to(directory)))
        has_files = self._files.count() > 0
        self._folder.setText(str(directory) if directory and has_files else "")
        self._folder.setVisible(has_files)
        self._files.setVisible(has_files)
        self._no_results.setVisible(not has_files)
        self._open_folder.setEnabled(directory is not None and directory.is_dir())

    @staticmethod
    def _teardown_text(outcome: RunOutcome) -> str:
        stage = outcome.stages.get("teardown")
        if stage is None:
            return f"passed: {DASH} · 소요 {DASH} · error: {DASH}"
        return (
            f"passed: {'예' if stage.passed else '아니오'} · "
            f"소요 {format_duration(stage.duration)} · error: {stage.error or DASH}"
        )

    def _sync_next(self) -> None:
        self._next.setEnabled(bool(self._next_serial.text().strip()))

    def _request_next(self) -> None:
        serial = self._next_serial.text().strip()
        if serial:
            self.next_requested.emit(serial)

    def _open_results_folder(self) -> None:
        if self._outcome is not None and self._outcome.results_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._outcome.results_dir)))

    @property
    def banner_title(self) -> str:
        return self._banner_title.text()

    @property
    def banner_kind(self) -> str:
        return str(self._banner.property("banner"))

    @property
    def banner_summary(self) -> str:
        return self._banner_summary.text()

    @property
    def banner_detail(self) -> str:
        return self._banner_detail.text()

    def file_names(self) -> List[str]:
        return [self._files.item(i).text() for i in range(self._files.count())]

    def no_results_visible(self) -> bool:
        return not self._no_results.isHidden()

    def teardown_text(self) -> str:
        return self._teardown.text()

    def table_row_count(self) -> int:
        return self._table.rowCount()
