from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import eol_tester
from eol_tester.config import load_hardware_config
from eol_ui.pages import ResultPage, RunPage, SettingsPage
from eol_ui.pages.run import CLOSE_NOTICE
from eol_ui.progress import ProgressState
from eol_ui.runner import RunOutcome, SequenceRunner
from eol_ui.theme import tokens
from eol_ui.widgets import Badge, label

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
        self._device_dots: Dict[str, QWidget] = {}

        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_header())
        body = QVBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
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
        self.run_page.running_changed.connect(hardware.set_running)
        hardware.set_running(self.runner.is_running)
        hardware.busy_changed.connect(self.run_page.set_hardware_busy)
        hardware.mock_changed.connect(lambda _: self.refresh_mock_badge())
        hardware.connection_tested.connect(self._paint_devices)

    def _on_applied(self, parameters: object, count: int) -> None:
        self.run_page.set_pending_parameters(parameters)
        self.run_page.set_applied_count(count)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 8, 16, 8)
        title = label(APP_NAME, "title")
        title.setObjectName("app-title")
        sequence = label(read_sequence_identity(), "muted")
        sequence.setObjectName("sequence-identity")
        row.addWidget(title)
        row.addWidget(sequence)
        row.addSpacing(16)

        group = QButtonGroup(self)
        for index, text in enumerate(("실행", "설정")):
            button = QPushButton(text)
            button.setProperty("tab", True)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setObjectName(f"tab-{index}")
            group.addButton(button, index)
            row.addWidget(button)
        group.idClicked.connect(self._tab_stack.setCurrentIndex)

        row.addStretch(1)
        row.addWidget(self.mock_badge)
        for key, text in DEVICES:
            dot = label(f"● {text}", "muted")
            dot.setObjectName(f"device-{key}")
            self._device_dots[key] = dot
            row.addWidget(dot)
        self._paint_devices({})
        return header

    def refresh_mock_badge(self) -> None:
        self.mock_badge.setVisible(load_hardware_config().is_mock_mode())

    def _paint_devices(self, devices: Dict[str, bool]) -> None:
        for key, dot in self._device_dots.items():
            known = devices.get(key)
            color = tokens.UNKNOWN if known is None else (tokens.PASS if known else tokens.FAIL)
            dot.setStyleSheet(f"color: {color};")
            dot.setProperty("connected", known)

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
        if not self.runner.is_running:
            self.settings_page.hardware.shutdown()
            super().closeEvent(event)
            return
        self._closing = True
        self.run_page.request_abort(CLOSE_NOTICE)
        event.ignore()


__all__ = ["APP_NAME", "MainWindow"]
