from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eol_ui.runner import MeasurementRecord, RunOutcome, Verdict
from eol_ui.theme import tokens
from eol_ui.widgets import (
    Badge,
    RangeBar,
    card,
    elevate,
    flatten,
    format_duration,
    format_number,
    label,
    set_property,
)
from eol_ui.widgets.basics import DASH, PRIMARY_SHADOW, verdict_kind
from eol_ui.widgets.icons import icon

from .parts import BANNER_COLORS, BANNER_ICONS, CircleIcon, GradientBanner, ResultTable

_BANNER_TITLE = {
    Verdict.PASS: "PASS",
    Verdict.FAIL: "FAIL",
    Verdict.ABORTED: "중단됨",
    Verdict.ERROR: "오류",
}
_PASS_DETAIL = "모든 측정값이 판정 기준 안에 있습니다."
_FAIL_GENERIC = "판정 기준을 벗어난 측정이 있습니다."
_ABORTED_TEXT = "사용자 요청으로 중단되었습니다. Teardown을 실행했습니다."
NO_RESULTS_TEXT = "저장된 결과 없음"
_COLUMNS = ("온도", "위치", "Force", "범위", "판정")
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_SIDE_WIDTH = 380
_ZWSP = "​"
_MONO = tokens.font_stack(tokens.MONO_FAMILIES)
_WHITE_TEXT = "color: white; background: transparent;"
_CAPTION_TEXT = "color: rgba(255,255,255,204); background: transparent; font-size: 12px;"


def _breakable(text: str) -> str:
    """Let a label wrap long file names and paths: add break points after separators."""
    for separator in "_-./\\":
        text = text.replace(separator, separator + _ZWSP)
    return text


def _mono_font(size: int, weight: int = 400) -> QFont:
    font = QFont()
    font.setFamilies(list(tokens.MONO_FAMILIES))
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


def _cell(widget: QWidget, center: bool = False, failed: bool = False) -> QWidget:
    holder = QWidget()
    holder.setObjectName("result-cell")
    background = f"background: {tokens.FAIL_FAINT}; " if failed else ""
    holder.setStyleSheet(
        f"QWidget#result-cell {{ {background}border-bottom: 1px solid {tokens.DIVIDER_SOFT}; }}"
    )
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(14, 0, 14, 0)
    if center:
        layout.addStretch(1)
    layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    if center:
        layout.addStretch(1)
    return holder


def _failure_detail(outcome: RunOutcome) -> str:
    for record in outcome.measurements:
        if record.passed or record.force is None:
            continue
        where = f"{format_number(record.temperature)} ℃에서 Force "
        if record.max_value is not None and record.force > record.max_value:
            return f"{where}상한 {format_number(record.max_value, digits=3)} kgf를 넘었습니다."
        if record.min_value is not None and record.force < record.min_value:
            return f"{where}하한 {format_number(record.min_value, digits=3)} kgf에 못 미쳤습니다."
        break
    return _FAIL_GENERIC


class ResultPage(QWidget):
    next_requested = Signal(str)
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._outcome: Optional[RunOutcome] = None
        self._file_names: List[str] = []

        banner = self._build_banner()
        results = self._build_results_card()
        side = QWidget()
        side.setFixedWidth(_SIDE_WIDTH)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(16)
        side_layout.addWidget(self._build_saved_card())
        side_layout.addWidget(self._build_teardown_card())
        side_layout.addWidget(self._build_next_card())
        side_layout.addStretch(1)

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addWidget(results, 1)
        body.addWidget(side, 0, Qt.AlignmentFlag.AlignTop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)
        layout.addWidget(banner)
        layout.addLayout(body, 1)
        self._sync_next()

    def _build_banner(self) -> QFrame:
        self._banner = GradientBanner()
        self._banner.setObjectName("banner")
        self._banner_icon = CircleIcon(64, "#2EFFFFFF", "check", 32)
        self._banner_title = label("")
        self._banner_title.setObjectName("banner-title")
        self._banner_title.setStyleSheet(f"{_WHITE_TEXT} font-size: 52px; font-weight: 700;")
        self._banner_detail = label("")
        self._banner_detail.setObjectName("banner-detail")
        self._banner_detail.setWordWrap(True)
        self._banner_detail.setStyleSheet(f"{_WHITE_TEXT} font-size: 15px;")
        text = QVBoxLayout()
        text.setSpacing(8)
        text.addWidget(self._banner_title)
        text.addWidget(self._banner_detail)

        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(4)
        self._banner_values: List = []
        for column, caption in enumerate(("시리얼 번호", "WIP ID", "소요 시간", "측정")):
            head = label(caption)
            head.setStyleSheet(_CAPTION_TEXT)
            value = label("")
            value.setStyleSheet(f"{_WHITE_TEXT} font-family: {_MONO}; font-size: 18px; font-weight: 600;")
            grid.addWidget(head, 0, column)
            grid.addWidget(value, 1, column)
            self._banner_values.append(value)

        row = QHBoxLayout(self._banner)
        row.setContentsMargins(30, 26, 30, 26)
        row.setSpacing(18)
        row.addWidget(self._banner_icon)
        row.addLayout(text, 1)
        row.addSpacing(22)
        row.addLayout(grid)
        return self._banner

    def _build_results_card(self) -> QFrame:
        self._table = ResultTable(len(_COLUMNS))
        self._table.setObjectName("result-table")
        for column, name in enumerate(_COLUMNS):
            item = QTableWidgetItem(name)
            align = _RIGHT if column == 2 else Qt.AlignmentFlag.AlignCenter if column == 4 else _LEFT
            item.setTextAlignment(align)
            self._table.setHorizontalHeaderItem(column, item)
        self._criteria = label("", "mono")
        self._criteria.setObjectName("result-criteria")
        self._criteria.setStyleSheet(f"font-size: 12px; color: {tokens.TEXT_MUTED};")
        head = QHBoxLayout()
        head.setContentsMargins(18, 16, 18, 14)
        head.setSpacing(10)
        head.addWidget(label("측정 결과", "title"))
        head.addWidget(self._criteria)
        head.addStretch(1)
        frame = card(shadow=True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(1, 0, 1, 10)
        layout.setSpacing(0)
        layout.addLayout(head)
        layout.addWidget(self._table, 1)
        return frame

    def _build_saved_card(self) -> QFrame:
        self._files = QWidget()
        self._files.setObjectName("result-files")
        self._files_layout = QVBoxLayout(self._files)
        self._files_layout.setContentsMargins(0, 0, 0, 0)
        self._files_layout.setSpacing(6)
        self._no_results = label(NO_RESULTS_TEXT, "muted")
        self._no_results.setObjectName("no-results")
        self._folder = label("", "mono")
        self._folder.setObjectName("results-folder")
        self._folder.setWordWrap(True)
        self._folder.setStyleSheet(f"font-size: 11px; color: {tokens.TEXT_MUTED};")
        self._open_folder = QPushButton("결과 폴더 열기")
        self._open_folder.setObjectName("open-folder-button")
        self._open_folder.setFixedHeight(44)
        self._open_folder.clicked.connect(self._open_results_folder)
        frame = card(shadow=True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(label("저장된 결과", "title"))
        layout.addWidget(self._folder)
        layout.addWidget(self._files)
        layout.addWidget(self._no_results)
        layout.addWidget(self._open_folder)
        return frame

    def _build_teardown_card(self) -> QFrame:
        self._teardown_icon = CircleIcon(32, tokens.CHIP_GRAY, None, 16)
        self._teardown_title = label("")
        self._teardown_title.setObjectName("teardown-title")
        self._teardown_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        self._teardown = label("", "mono")
        self._teardown.setObjectName("teardown-result")
        self._teardown.setWordWrap(True)
        self._teardown.setStyleSheet(f"font-size: 12px; color: {tokens.TEXT_MUTED};")
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._teardown_title)
        text.addWidget(self._teardown)
        frame = card(shadow=True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self._teardown_icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        return frame

    def _build_next_card(self) -> QFrame:
        self._next_serial = QLineEdit()
        self._next_serial.setObjectName("next-serial-input")
        self._next_serial.setPlaceholderText("바코드 스캔 또는 입력")
        self._next_serial.setStyleSheet(
            "QLineEdit { min-height: 48px; max-height: 48px; border-radius: 10px; padding: 0 14px;"
            f" font-family: {_MONO}; font-size: 15px; font-weight: 500; }}"
        )
        self._next = QPushButton("다음 테스트 시작")
        self._next.setObjectName("next-button")
        self._next.setProperty("primary", True)
        self._next.setIcon(icon("play", 14, "#FFFFFF"))
        self._back = QPushButton("실행 화면으로")
        self._back.setObjectName("back-button")
        self._back.setFixedHeight(44)
        self._next_serial.textChanged.connect(self._sync_next)
        self._next_serial.returnPressed.connect(self._request_next)
        self._next.clicked.connect(self._request_next)
        self._back.clicked.connect(self.back_requested)
        frame = card(shadow=True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(label("다음 DUT 시리얼 번호", "caption"))
        layout.addWidget(self._next_serial)
        layout.addWidget(self._next)
        layout.addWidget(self._back)
        return frame

    def show_outcome(self, outcome: RunOutcome) -> None:
        self._outcome = outcome
        kind = outcome.verdict.value
        passed = sum(1 for m in outcome.measurements if m.passed)
        total = len(outcome.measurements)
        elapsed = (outcome.finished_at - outcome.started_at).total_seconds()
        set_property(self._banner, "banner", kind)
        self._banner.update()
        self._banner_icon.set_style("#2EFFFFFF", BANNER_ICONS[kind], "#FFFFFF")
        elevate(self._banner, 24, 8, BANNER_COLORS[kind][2])
        self._banner_title.setText(_BANNER_TITLE[outcome.verdict])
        self._banner_detail.setText(self._detail_text(outcome))
        self._banner_detail.setVisible(bool(self._banner_detail.text()))
        for widget, text in zip(
            self._banner_values,
            (outcome.serial_number, outcome.wip_id or DASH, format_duration(elapsed), f"{passed}/{total}"),
        ):
            widget.setText(text)
        self._fill_table(outcome)
        self._fill_files(outcome)
        self._fill_teardown(outcome)
        self._next_serial.clear()
        self._next_serial.setFocus()

    @staticmethod
    def _detail_text(outcome: RunOutcome) -> str:
        if outcome.verdict is Verdict.ERROR:
            return outcome.error or ""
        if outcome.verdict is Verdict.ABORTED:
            return _ABORTED_TEXT
        if outcome.verdict is Verdict.FAIL:
            return _failure_detail(outcome)
        return _PASS_DETAIL

    def _fill_table(self, outcome: RunOutcome) -> None:
        self._table.setRowCount(0)
        limits = next(
            ((m.min_value, m.max_value) for m in outcome.measurements
             if m.min_value is not None and m.max_value is not None),
            None,
        )
        self._criteria.setVisible(limits is not None)
        if limits is not None:
            low, high = limits
            self._criteria.setText(
                f"판정 기준 {format_number(low, digits=3)} – {format_number(high, digits=3)} kgf"
            )
        for record in outcome.measurements:
            self._add_row(record)

    def _add_row(self, record: MeasurementRecord) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        failed = not record.passed
        strong = QColor(tokens.FAIL_TEXT) if failed else QColor(tokens.TEXT)
        position = DASH if record.position is None else f"{record.position:,.0f} µm"
        cells = (
            (format_number(record.temperature, "°C"), _LEFT, QColor(tokens.TEXT), 400),
            (position, _LEFT, QColor(tokens.TEXT_SECONDARY), 400),
            (format_number(record.force, " kgf", 3), _RIGHT, strong, 600),
        )
        for column, (text, align, color, weight) in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setTextAlignment(align)
            item.setFont(_mono_font(14, weight))
            item.setForeground(color)
            self._table.setItem(row, column, item)
        if record.force is None:
            range_cell: QWidget = label(DASH, "muted")
        else:
            range_cell = RangeBar()
            range_cell.show_value(record.force, record.min_value, record.max_value)
        self._table.setCellWidget(row, 3, _cell(range_cell, failed=failed))
        kind = verdict_kind(record.passed)
        self._table.setCellWidget(row, 4, _cell(Badge(kind, kind), center=True, failed=failed))
        if failed:
            for column in range(3):
                self._table.item(row, column).setBackground(QColor(tokens.FAIL_FAINT))
        self._table.setItem(row, 3, self._blank(failed))
        self._table.setItem(row, 4, self._blank(failed))

    @staticmethod
    def _blank(failed: bool) -> QTableWidgetItem:
        item = QTableWidgetItem("")
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        if failed:
            item.setBackground(QColor(tokens.FAIL_FAINT))
        return item

    def _fill_files(self, outcome: RunOutcome) -> None:
        while self._files_layout.count():
            self._files_layout.takeAt(0).widget().deleteLater()
        directory = outcome.results_dir
        self._file_names = [
            str(path.relative_to(directory)) if directory else str(path) for path in outcome.result_files
        ]
        for name in self._file_names:
            chip = label(_breakable(name), "mono")
            chip.setWordWrap(True)
            chip.setStyleSheet(
                f"QLabel {{ background: #F9FAFB; border: 1px solid {tokens.DIVIDER_SOFT}; border-radius: 8px;"
                f" padding: 8px 10px; font-size: 12px; color: {tokens.TEXT_STRONG}; }}"
            )
            self._files_layout.addWidget(chip)
        has_files = bool(self._file_names)
        self._folder.setText(_breakable(str(directory)) if directory and has_files else "")
        self._folder.setVisible(has_files)
        self._files.setVisible(has_files)
        self._no_results.setVisible(not has_files)
        self._open_folder.setEnabled(directory is not None and directory.is_dir())

    def _fill_teardown(self, outcome: RunOutcome) -> None:
        stage = outcome.stages.get("teardown")
        if stage is None:
            title, background, glyph, color = "Teardown 기록 없음", tokens.CHIP_GRAY, None, tokens.TEXT_FAINT
        elif stage.passed:
            title, background, glyph, color = "Teardown 완료", tokens.PASS_BADGE, "check", tokens.PASS_TEXT
        else:
            title, background, glyph, color = "Teardown 실패", tokens.FAIL_SOFT, "x", tokens.FAIL_TEXT
        self._teardown_icon.set_style(background, glyph, color)
        self._teardown_title.setText(title)
        self._teardown.setText(self._teardown_text(outcome))

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
        enabled = bool(self._next_serial.text().strip())
        self._next.setEnabled(enabled)
        if enabled:
            elevate(self._next, *PRIMARY_SHADOW)
        else:
            flatten(self._next)

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
        serial, wip, elapsed, counts = (value.text() for value in self._banner_values)
        return f"SN {serial} · WIP {wip} · 소요 {elapsed} · {counts} PASS"

    @property
    def banner_detail(self) -> str:
        return self._banner_detail.text()

    def banner_values(self) -> List[str]:
        return [value.text() for value in self._banner_values]

    def file_names(self) -> List[str]:
        return list(self._file_names)

    def no_results_visible(self) -> bool:
        return not self._no_results.isHidden()

    def teardown_title(self) -> str:
        return self._teardown_title.text()

    def teardown_text(self) -> str:
        return self._teardown.text()

    def table_row_count(self) -> int:
        return self._table.rowCount()

    def row_background(self, row: int) -> QColor:
        return self._table.item(row, 0).background().color()

    def row_force_color(self, row: int) -> QColor:
        return self._table.item(row, 2).foreground().color()
