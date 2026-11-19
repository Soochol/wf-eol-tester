from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QCloseEvent, QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import eol_tester
from eol_tester.config import load_hardware_config
from eol_ui.pages import ResultPage, RunPage, SettingsPage
from eol_ui.pages.hardware.page import CLOSE_WAIT_NOTICE
from eol_ui.pages.run import CLOSE_NOTICE
from eol_ui.progress import ProgressState
from eol_ui.runner import RunOutcome, SequenceRunner
from eol_ui.theme import tokens
from eol_ui.widgets import Badge, label
from eol_ui.widgets.icons import icon_pixmap

APP_NAME = "WF EOL Tester"
DEVICES = (
    ("robot", "Robot"),
    ("loadcell", "LoadCell"),
    ("mcu", "MCU"),
    ("power", "Power"),
    ("digital_io", "DIO"),
)
_MANIFEST = Path(eol_tester.__file__).parent / "manifest.yaml"


def read_sequence_identity() -> str:
    manifest = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
    return f"{manifest['name']} {manifest['version']}"


class _Dot(QWidget):
    """9px status dot inside a 3px ring."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(15, 15)
        self._dot = QColor(tokens.TEXT_FAINT)
        self._ring = QColor(tokens.DIVIDER)

    def set_colors(self, dot: str, ring: str) -> None:
        self._dot, self._ring = QColor(dot), QColor(ring)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._ring)
        painter.drawEllipse(QRectF(0, 0, 15, 15))
        painter.setBrush(self._dot)
        painter.drawEllipse(QRectF(3, 3, 9, 9))


class DeviceChip(QFrame):
    """Device pill: ring dot + name, colored by connected True / False / None (unknown)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setProperty("device-chip", True)
        self.setFixedHeight(30)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 12, 0)
        row.setSpacing(6)
        self._dot = _Dot()
        self._text = QLabel(text)
        row.addWidget(self._dot)
        row.addWidget(self._text)
        self.set_connected(None)

    def set_connected(self, known: Optional[bool]) -> None:
        colors = tokens.DEVICE_CHIP_COLORS[known]
        self.setProperty("connected", known)
        self.setStyleSheet(
            f"QFrame[device-chip=\"true\"] {{ background: {colors['bg']}; border-color: {colors['border']}; }}"
            f"QFrame[device-chip=\"true\"] QLabel {{ color: {colors['text']}; }}"
        )
        self._dot.set_colors(colors["dot"], colors["ring"])


class MainWindow(QMainWindow):
    def __init__(self, runner: Optional[SequenceRunner] = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.runner = runner or SequenceRunner(self)
        self._closing = False

        self.run_page = RunPage(self.runner)
        self.result_page = ResultPage()
        self.settings_page = SettingsPage()

        self._run_stack = QStackedWidget()
        self._run_stack.addWidget(self.run_page)
        self._run_stack.addWidget(self.result_page)
        self._tab_stack = QStackedWidget()
        self._tab_stack.addWidget(self._run_stack)
        self._tab_stack.addWidget(self.settings_page)

        self.mock_badge = Badge("MOCK", "MOCK")
        self.mock_badge.setObjectName("mock-badge")
        self._device_dots: Dict[str, DeviceChip] = {}

        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_header())
        body = QVBoxLayout()
        body.setContentsMargins(24, 20, 24, 20)
        body.addWidget(self._tab_stack)
        layout.addLayout(body, 1)
        self.setCentralWidget(root)

        self.result_page.next_requested.connect(self._start_next)
        self.result_page.back_requested.connect(self.show_run_page)
        self.runner.progress.connect(self._on_progress)
        self.runner.finished.connect(self._on_finished)
        self._connect_settings()
        self.refresh_mock_badge()

    def _connect_settings(self) -> None:
        parameters = self.settings_page.parameters
        hardware = self.settings_page.hardware
        self.run_page.refresh_profiles()
        self.run_page.set_profile(parameters.profile_name)
        self.run_page.profile_changed.connect(parameters.select_profile)
        parameters.profile_changed.connect(self.run_page.set_profile)
        parameters.profiles_changed.connect(self.run_page.refresh_profiles)
        parameters.profiles_changed.connect(
            lambda: self.run_page.set_profile(parameters.profile_name)
        )
        parameters.applied.connect(self._on_applied)
        self._on_applied(parameters.carried_parameters(), 0)
        self.run_page.running_changed.connect(hardware.set_running)
        hardware.set_running(self.runner.is_running)
        hardware.busy_changed.connect(self.run_page.set_hardware_busy)
        hardware.busy_changed.connect(self._on_hardware_busy)
        hardware.mock_changed.connect(lambda _: self.refresh_mock_badge())
        hardware.connection_tested.connect(self._paint_devices)

    def _on_hardware_busy(self, busy: bool) -> None:
        if not busy and self._closing:
            self.close()

    def _on_applied(self, parameters: object, count: int) -> None:
        self.run_page.set_pending_parameters(parameters)
        self.run_page.set_applied_count(count)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 10, 24, 10)
        row.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("logo")
        logo.setPixmap(icon_pixmap("logo", 32, tokens.ACCENT))
        logo.setFixedSize(32, 32)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = label(APP_NAME, "title")
        title.setObjectName("app-title")
        sequence = label(read_sequence_identity(), "muted")
        sequence.setObjectName("sequence-identity")
        titles.addWidget(title)
        titles.addWidget(sequence)
        row.addWidget(logo)
        row.addLayout(titles)
        row.addSpacing(24)

        segmented = QFrame()
        segmented.setProperty("segmented", True)
        segment_row = QHBoxLayout(segmented)
        segment_row.setContentsMargins(4, 4, 4, 4)
        segment_row.setSpacing(4)
        group = QButtonGroup(self)
        for index, text in enumerate(("실행", "설정")):
            button = QPushButton(text)
            button.setProperty("segment", True)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setObjectName(f"tab-{index}")
            group.addButton(button, index)
            segment_row.addWidget(button)
        group.idClicked.connect(self._tab_stack.setCurrentIndex)
        row.addWidget(segmented)

        row.addStretch(1)
        row.addWidget(self.mock_badge)
        for key, text in DEVICES:
            chip = DeviceChip(text)
            chip.setObjectName(f"device-{key}")
            self._device_dots[key] = chip
            row.addWidget(chip)
        self._paint_devices({})
        return header

    def refresh_mock_badge(self) -> None:
        self.mock_badge.setVisible(load_hardware_config().is_mock_mode())

    def _paint_devices(self, devices: Dict[str, bool]) -> None:
        for key, dot in self._device_dots.items():
            dot.set_connected(devices.get(key))

    def device_connected(self, key: str) -> Optional[bool]:
        return self._device_dots[key].property("connected")

    def show_run_page(self) -> None:
        self._run_stack.setCurrentWidget(self.run_page)

    def _on_progress(self, state: ProgressState) -> None:
        self._paint_devices(dict(state.devices))

    def _on_finished(self, outcome: RunOutcome) -> None:
        self.result_page.show_outcome(outcome)
        self._run_stack.setCurrentWidget(self.result_page)
        self.refresh_mock_badge()
        if self._closing:
            self.close()

    def _start_next(self, serial_number: str) -> None:
        self.show_run_page()
        self.run_page.start_run(serial_number)

    def closeEvent(self, event: QCloseEvent) -> None:
        hardware = self.settings_page.hardware
        if self.runner.is_running:
            self._closing = True
            self.run_page.request_abort(CLOSE_NOTICE)
            event.ignore()
            return
        if hardware.is_testing():
            self._closing = True
            hardware.show_close_wait()
            self.run_page.show_notice(CLOSE_WAIT_NOTICE)
            event.ignore()
            return
        hardware.shutdown()
        super().closeEvent(event)


__all__ = ["APP_NAME", "MainWindow"]
