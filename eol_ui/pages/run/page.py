from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eol_tester.config import list_test_profiles
from eol_ui.progress import ProgressState
from eol_ui.runner import (
    MeasurementEvent,
    RunnerBusyError,
    RunOutcome,
    RunRequest,
    SequenceRunner,
)
from eol_ui.widgets import LogPanel, card, label

from .measurements import MeasurementList
from .progress_card import ProgressCard
from .tiles import LiveTiles

ABORT_NOTICE = "중단 요청됨 — 현재 측정이 끝나면 Teardown(전원 OFF · 로봇 원점 복귀)을 실행합니다."
CLOSE_NOTICE = "Teardown 후 종료합니다"
HARDWARE_BUSY_NOTICE = "연결 테스트 중에는 시작할 수 없습니다."
_TICK_MS = 500


class RunPage(QWidget):
    profile_changed = Signal(str)
    running_changed = Signal(bool)

    def __init__(self, runner: SequenceRunner) -> None:
        super().__init__()
        self._runner = runner
        self._pending_parameters: Dict[str, Any] = {}
        self._last_rows = 0
        self._hardware_busy = False
        self._last_running = False

        self._serial = QLineEdit()
        self._serial.setObjectName("serial-input")
        self._serial.setPlaceholderText("시리얼 번호")
        self._wip = QLineEdit()
        self._wip.setObjectName("wip-input")
        self._wip.setPlaceholderText("WIP ID")
        self._profile = QComboBox()
        self._profile.setObjectName("profile-combo")
        self._applied = label("", "muted")
        self._applied.setObjectName("applied-count")
        self._start = QPushButton("시작")
        self._start.setObjectName("start-button")
        self._start.setProperty("primary", True)
        self._abort = QPushButton("중단")
        self._abort.setObjectName("abort-button")
        self._abort.setProperty("danger", True)
        self._notice = label("", "notice")
        self._notice.setObjectName("notice")
        self._notice.setWordWrap(True)

        self._progress = ProgressCard()
        self._tiles = LiveTiles()
        self._measurements = MeasurementList()
        self._log = LogPanel()
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._build_layout()
        self.refresh_profiles()
        self.set_applied_count(0)
        self._serial.textChanged.connect(self._sync_buttons)
        self._profile.activated.connect(lambda _: self.profile_changed.emit(self._profile.currentText()))
        self._start.clicked.connect(self._on_start_clicked)
        self._abort.clicked.connect(lambda: self.request_abort())
        runner.log.connect(self._log.append)
        runner.progress.connect(self._on_progress)
        runner.event.connect(self._on_event)
        runner.finished.connect(self._on_finished)
        self._sync_buttons()

    def _build_layout(self) -> None:
        inputs = card()
        row = QGridLayout(inputs)
        row.addWidget(label("시리얼 번호", "muted"), 0, 0)
        row.addWidget(label("WIP ID", "muted"), 0, 1)
        row.addWidget(label("프로파일", "muted"), 0, 2)
        row.addWidget(self._serial, 1, 0)
        row.addWidget(self._wip, 1, 1)
        row.addWidget(self._profile, 1, 2)
        row.addWidget(self._start, 1, 3)
        row.addWidget(self._abort, 1, 4)
        row.addWidget(self._applied, 2, 0, 1, 5)
        row.addWidget(self._notice, 3, 0, 1, 5)

        left = QVBoxLayout()
        left.addWidget(inputs)
        left.addWidget(self._progress.widget)
        left.addWidget(self._log, 1)

        right = QVBoxLayout()
        right.addWidget(self._tiles)
        right.addWidget(self._measurements, 1)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 3)
        layout.addLayout(right, 2)

    @property
    def is_running(self) -> bool:
        return self._runner.is_running

    def refresh_profiles(self) -> None:
        current = self._profile.currentText()
        self._profile.clear()
        self._profile.addItems(list_test_profiles())
        if current:
            self._profile.setCurrentText(current)

    def set_profile(self, name: str) -> None:
        index = self._profile.findText(name)
        if index >= 0:
            self._profile.setCurrentIndex(index)

    def profile_name(self) -> str:
        return self._profile.currentText()

    def profile_names(self) -> list:
        return [self._profile.itemText(index) for index in range(self._profile.count())]

    def set_applied_count(self, count: int) -> None:
        self._applied.setText(f"적용된 변경 {count}개")

    def applied_text(self) -> str:
        return self._applied.text()

    def set_hardware_busy(self, busy: bool) -> None:
        self._hardware_busy = busy
        if busy:
            self.show_notice(HARDWARE_BUSY_NOTICE)
        elif self.notice_text() == HARDWARE_BUSY_NOTICE:
            self.show_notice("")
        self._sync_buttons()

    def set_pending_parameters(self, parameters: Mapping[str, Any]) -> None:
        self._pending_parameters = dict(parameters)

    def build_request(self) -> RunRequest:
        wip = self._wip.text().strip()
        parameters = {**self._pending_parameters, "test_profile": self._profile.currentText()}
        return RunRequest(
            serial_number=self._serial.text().strip(),
            wip_id=wip or None,
            parameters=parameters,
        )

    def start_run(self, serial_number: Optional[str] = None) -> None:
        if serial_number is not None:
            self._serial.setText(serial_number)
        if not self._can_start():
            return
        self._prepare_for_run()
        try:
            self._runner.start(self.build_request())
        except RunnerBusyError:
            self.show_notice("이미 실행 중입니다.")
            return
        self._timer.start()
        self._sync_buttons()

    def request_abort(self, notice: str = ABORT_NOTICE) -> None:
        if not self._runner.is_running:
            return
        self._runner.request_abort()
        self.show_notice(notice)
        self._sync_buttons()

    def show_notice(self, text: str) -> None:
        self._notice.setText(text)

    def notice_text(self) -> str:
        return self._notice.text()

    def _can_start(self) -> bool:
        return (
            bool(self._serial.text().strip())
            and not self._runner.is_running
            and not self._hardware_busy
        )

    def _prepare_for_run(self) -> None:
        self._log.clear()
        self._measurements.clear()
        self._last_rows = 0
        self.show_notice("")
        self._progress.show_state(ProgressState())
        self._tiles.show_state(ProgressState())

    def _sync_buttons(self) -> None:
        running = self._runner.is_running
        self._start.setEnabled(self._can_start())
        self._abort.setEnabled(running and not self._runner.abort_requested)
        for editor in (self._serial, self._wip, self._profile):
            editor.setEnabled(not running)
        if running != self._last_running:
            self._last_running = running
            self.running_changed.emit(running)

    def _on_start_clicked(self) -> None:
        self.start_run()

    def _tick(self) -> None:
        self._show_state(self._runner.progress_state())

    def _on_progress(self, state: ProgressState) -> None:
        self._show_state(state)
        self._sync_buttons()

    def _show_state(self, state: ProgressState) -> None:
        self._progress.show_state(state)
        self._tiles.show_state(state)
        while self._last_rows < state.measurements_done:
            self._last_rows += 1
            self._measurements.add_pending(
                state.mcu_target_temperature, state.robot_position, state.last_force or 0.0
            )

    def _on_event(self, event: object) -> None:
        if isinstance(event, MeasurementEvent):
            self._measurements.apply_event(
                event.name, float(event.value), event.min_value, event.max_value, event.passed
            )

    def _on_finished(self, outcome: RunOutcome) -> None:
        self._timer.stop()
        self._show_state(self._runner.progress_state())
        self._measurements.close_pending()
        self._sync_buttons()

    @property
    def progress(self) -> ProgressCard:
        return self._progress

    @property
    def tiles(self) -> LiveTiles:
        return self._tiles

    @property
    def measurements(self) -> MeasurementList:
        return self._measurements

    @property
    def log_panel(self) -> LogPanel:
        return self._log
