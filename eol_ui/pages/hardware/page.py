from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

import eol_tester.config as eol_config
from eol_ui.settings import HardwareStore
from eol_ui.settings.hardware_store import DEVICES, EDITABLE, ConnectionResult
from eol_ui.widgets import card, label, set_property
from eol_ui.widgets.basics import status_color

from .connection import ConnectionTestThread

DEVICE_TITLES = {
    "robot": "Robot",
    "loadcell": "LoadCell",
    "mcu": "MCU",
    "power": "Power",
    "digital_io": "Digital I/O",
}
KEY_TITLES = {
    "axis_id": "axis",
    "irq_no": "irq",
    "port": "port",
    "baudrate": "baud",
    "host": "host",
    "input_module_no": "in",
    "output_module_no": "out",
}
LOCK_REASON = "실행 중에는 하드웨어 설정을 바꾸거나 연결을 시험할 수 없습니다."
UNKNOWN_TEXT = "미확인"
CONNECTED_TEXT = "연결됨"
CONFIG_PATH_TEXT = "config/hardware_config.yaml"


class HardwarePage(QWidget):
    mock_changed = Signal(bool)
    connection_tested = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, store: Optional[HardwareStore] = None) -> None:
        super().__init__()
        self._store = store or HardwareStore()
        self._locked = False
        self._testing = False
        self._thread: Optional[ConnectionTestThread] = None
        self._edits: Dict[Tuple[str, str], QLineEdit] = {}
        self._models: Dict[str, object] = {}
        self._statuses: Dict[str, object] = {}

        self._path = label(CONFIG_PATH_TEXT, "mono")
        self._path.setObjectName("hardware-path")
        self._path.setToolTip(str(self._store.path()))
        self._mock = QPushButton("Mock 모드")
        self._mock.setObjectName("mock-switch")
        self._mock.setCheckable(True)
        self._mock.setProperty("switch", True)
        self._save = QPushButton("저장")
        self._save.setObjectName("hardware-save")
        self._test = QPushButton("연결 테스트")
        self._test.setObjectName("connection-test")
        self._reason = label("", "notice")
        self._reason.setObjectName("hardware-lock-reason")
        self._message = label("", "muted")
        self._message.setObjectName("hardware-message")
        self._message.setWordWrap(True)
        self._build_layout()
        self._refresh_models()
        self._mock.setChecked(self._store.is_mock())
        self._mock.toggled.connect(self._on_mock_toggled)
        self._save.clicked.connect(self._on_save)
        self._test.clicked.connect(self._on_test)
        self._sync_enabled()

    def _build_layout(self) -> None:
        panel = card()
        outer = QVBoxLayout(panel)
        head = QHBoxLayout()
        head.addWidget(label("하드웨어 연결", "title"))
        head.addWidget(self._path)
        head.addStretch(1)
        head.addWidget(self._mock)
        head.addWidget(self._save)
        head.addWidget(self._test)
        outer.addLayout(head)
        outer.addWidget(self._reason)
        grid = QGridLayout()
        for column, title in enumerate(("장치", "모델", "연결 설정", "상태")):
            grid.addWidget(label(title, "muted"), 0, column)
        for row, device in enumerate(DEVICES, start=1):
            grid.addWidget(label(DEVICE_TITLES[device]), row, 0)
            model = label("", "mono")
            model.setObjectName(f"hw-model-{device}")
            grid.addWidget(model, row, 1)
            self._models[device] = model
            grid.addWidget(self._build_editors(device), row, 2)
            status = label(UNKNOWN_TEXT, "muted")
            status.setObjectName(f"hw-status-{device}")
            grid.addWidget(status, row, 3)
            self._statuses[device] = status
        grid.setColumnStretch(2, 1)
        outer.addLayout(grid)
        outer.addWidget(self._message)
        outer.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

    def _build_editors(self, device: str) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        for key in EDITABLE[device]:
            edit = QLineEdit(str(self._store.get(device, key)))
            edit.setObjectName(f"hw-edit-{device}-{key}")
            edit.setToolTip(key)
            edit.textChanged.connect(lambda _=None, w=edit: set_property(w, "error", False))
            row.addWidget(label(KEY_TITLES[key], "muted"))
            row.addWidget(edit)
            self._edits[(device, key)] = edit
        return holder

    def _refresh_models(self) -> None:
        for device in DEVICES:
            self._models[device].setText(self._store.model(device))

    def _reload_edits(self) -> None:
        for (device, key), edit in self._edits.items():
            edit.setText(str(self._store.get(device, key)))

    def edit(self, device: str, key: str) -> QLineEdit:
        return self._edits[(device, key)]

    def edit_widgets(self) -> list:
        return list(self._edits.values())

    @property
    def mock_switch(self) -> QPushButton:
        return self._mock

    @property
    def save_button(self) -> QPushButton:
        return self._save

    @property
    def test_button(self) -> QPushButton:
        return self._test

    def model_text(self, device: str) -> str:
        return self._models[device].text()

    def status_text(self, device: str) -> str:
        return self._statuses[device].text()

    def lock_reason(self) -> str:
        return self._reason.text()

    def message_text(self) -> str:
        return self._message.text()

    def is_testing(self) -> bool:
        return self._testing

    def set_running(self, running: bool) -> None:
        self._locked = running
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        enabled = not self._locked and not self._testing
        for edit in self._edits.values():
            edit.setEnabled(enabled)
        for button in (self._save, self._mock, self._test):
            button.setEnabled(enabled)
        self._reason.setText(LOCK_REASON if self._locked else "")
        self._reason.setVisible(self._locked)

    def _on_mock_toggled(self, enabled: bool) -> None:
        try:
            self._store.load()
            self._store.set_mock(enabled)
            self._store.save()
        except Exception as error:
            self._store.load()
            self._mock.blockSignals(True)
            self._mock.setChecked(self._store.is_mock())
            self._mock.blockSignals(False)
            self._message.setText(f"Mock 전환을 저장하지 못했습니다: {error}")
            return
        self._refresh_models()
        self._reset_statuses()
        self._message.setText("Mock 모드를 켜고 저장했습니다." if enabled else "Mock 모드를 끄고 저장했습니다.")
        self.mock_changed.emit(enabled)

    def _on_save(self) -> None:
        problems = []
        try:
            self._store.load()
            for (device, key), edit in self._edits.items():
                try:
                    self._store.set_value(device, key, edit.text())
                except ValueError as error:
                    set_property(edit, "error", True)
                    problems.append(f"{DEVICE_TITLES[device]} {key}: {error}")
            if problems:
                self._store.load()
                self._message.setText("저장하지 않았습니다. " + " / ".join(problems))
                return
            self._store.save()
        except Exception as error:
            self._message.setText(f"저장하지 못했습니다: {error}")
            return
        self._message.setText(f"{CONFIG_PATH_TEXT}에 저장했습니다.")
        self._reset_statuses()

    def _reset_statuses(self) -> None:
        for device in DEVICES:
            self._set_status(device, UNKNOWN_TEXT, None)

    def _set_status(self, device: str, text: str, connected: Optional[bool]) -> None:
        widget = self._statuses[device]
        widget.setText(text)
        widget.setProperty("connected", connected)
        widget.setStyleSheet("" if connected is None else f"color: {status_color(connected)};")

    def _on_test(self) -> None:
        if self._testing or self._locked:
            return
        self._testing = True
        self._message.setText("연결을 시험하는 중입니다...")
        self._sync_enabled()
        self.busy_changed.emit(True)
        thread = ConnectionTestThread(self._store, self)
        thread.done.connect(self._on_test_done)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        thread.start()

    def _on_test_done(self, result: ConnectionResult) -> None:
        self._testing = False
        for device, (ok, error) in result.items():
            self._set_status(device, CONNECTED_TEXT if ok else f"실패: {error}", ok)
        self._message.setText("연결 테스트를 마쳤습니다.")
        self._sync_enabled()
        self.busy_changed.emit(False)
        self.connection_tested.emit({device: ok for device, (ok, _) in result.items()})

    def shutdown(self) -> None:
        thread = self._thread
        if thread is not None:
            try:
                thread.wait()
            except RuntimeError:
                pass
