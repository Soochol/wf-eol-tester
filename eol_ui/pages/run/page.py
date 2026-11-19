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

import eol_tester.config as eol_config
from eol_ui.progress import ProgressState
from eol_ui.runner import (
    MeasurementEvent,
    RunnerBusyError,
    RunOutcome,
    RunRequest,
    SequenceRunner,
)
from eol_ui.theme import tokens
from eol_ui.widgets import LogPanel, card, elevate, flatten, label
from eol_ui.widgets.basics import PRIMARY_SHADOW
from eol_ui.widgets.icons import icon

from .measurements import MeasurementList
from .plan import MeasurementPlan, plan_measurements
from .progress_card import ProgressCard
from .tiles import LiveTiles

ABORT_NOTICE = "중단 요청됨 — 현재 측정이 끝나면 Teardown(전원 OFF · 로봇 원점 복귀)을 실행합니다."
CLOSE_NOTICE = "Teardown 후 종료합니다"
HARDWARE_BUSY_NOTICE = "연결 테스트 중에는 시작할 수 없습니다."
NO_PROFILES_NOTICE = "테스트 프로파일이 없어 시작할 수 없습니다. 설정 화면에서 프로파일을 만드세요."
ABORT_HINT = "중단하면 현재 동작 뒤 Teardown(전원 OFF · 로봇 원점 복귀)을 실행합니다."
_TICK_MS = 500
_RIGHT_COLUMN_WIDTH = 380


def idle_hint(profile: str) -> str:
    return f"프로파일 {profile}(으)로 실행합니다." if profile else "프로파일을 선택하세요."


def plan_text(plan: Optional[MeasurementPlan], total: Optional[int] = None) -> str:
    if plan is None and not total:
        return ""
    if plan is None or (total and plan.total != total):
        return f"측정 {total}회 예정"
    repeats = f" × 반복 {plan.repeats}회" if plan.repeats >= 2 else ""
    return f"온도 {plan.temperatures}개 × 위치 {plan.positions}개{repeats} = 측정 {plan.total}회 예정"


def missing_profile_notice(name: str) -> str:
    return f"프로파일 '{name}' 파일이 없어 시작할 수 없습니다. 다른 프로파일을 선택하세요."


def _plan_for_run(plan: Optional[MeasurementPlan], state: ProgressState) -> Optional[MeasurementPlan]:
    if plan is None:
        return None
    repeats = state.repetition[1]
    return MeasurementPlan(plan.temperatures, plan.positions, repeats) if repeats >= 1 else plan


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
        self._missing_profile: Optional[str] = None

        self._serial = QLineEdit()
        self._serial.setObjectName("serial-input")
        self._serial.setPlaceholderText("스캔 또는 입력")
        self._wip = QLineEdit()
        self._wip.setObjectName("wip-input")
        self._wip.setPlaceholderText("선택")
        self._profile = QComboBox()
        self._profile.setObjectName("profile-combo")
        # theme QSS keys the 44px field on [size="lg"], but "size" is a built-in QWidget property
        # and cannot carry a string, so the same rule is applied on the widgets themselves.
        mono = tokens.font_stack(tokens.MONO_FAMILIES)
        for field in (self._serial, self._wip, self._profile):
            field.setFixedHeight(44)
        for field in (self._serial, self._wip):
            field.setStyleSheet(
                f"QLineEdit {{ border-radius: 10px; padding: 0 12px; font-family: {mono}; font-size: 15px; }}"
            )
        self._profile.setStyleSheet("QComboBox { border-radius: 10px; padding: 0 12px; font-size: 15px; }")
        self._hint = label("", None)
        self._hint.setObjectName("run-hint")
        self._hint.setStyleSheet(f"font-size: 13px; color: {tokens.TEXT_MUTED};")
        self._hint.setWordWrap(True)
        self._applied = label("", "muted")
        self._applied.setObjectName("applied-count")
        self._start = QPushButton(" 시작")
        self._start.setObjectName("start-button")
        self._start.setProperty("primary", True)
        self._abort = QPushButton(" 중단")
        self._abort.setObjectName("abort-button")
        self._abort.setProperty("danger", True)
        self._notice = label("", "notice")
        self._notice.setObjectName("notice")
        self._notice.setWordWrap(True)
        self._shadowed = False
        self._start.setMinimumWidth(120)
        self._abort.setMinimumWidth(104)

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
        self._profile.activated.connect(self._on_profile_activated)
        self._start.clicked.connect(self._on_start_clicked)
        self._abort.clicked.connect(lambda: self.request_abort())
        runner.log.connect(self._log.append)
        runner.progress.connect(self._on_progress)
        runner.event.connect(self._on_event)
        runner.finished.connect(self._on_finished)
        self._sync_buttons()

    def _build_layout(self) -> None:
        inputs = card(shadow=True)
        row = QGridLayout(inputs)
        row.setContentsMargins(20, 18, 20, 16)
        row.setHorizontalSpacing(14)
        row.setVerticalSpacing(6)
        for column, text in enumerate(("시리얼 번호", "WIP ID", "프로파일")):
            row.addWidget(label(text, "caption"), 0, column)
        row.addWidget(self._serial, 1, 0)
        row.addWidget(self._wip, 1, 1)
        row.addWidget(self._profile, 1, 2)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self._start)
        buttons.addWidget(self._abort)
        row.addLayout(buttons, 1, 3)
        row.setColumnStretch(0, 3)
        row.setColumnStretch(1, 2)
        row.setColumnStretch(2, 2)
        row.addWidget(self._hint, 2, 0, 1, 4)
        row.addWidget(self._applied, 3, 0, 1, 4)
        row.addWidget(self._notice, 4, 0, 1, 4)

        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(inputs)
        left.addWidget(self._progress.widget)
        left.addWidget(self._log, 1)

        right_column = QWidget()
        right_column.setFixedWidth(_RIGHT_COLUMN_WIDTH)
        right = QVBoxLayout(right_column)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(16)
        right.addWidget(self._tiles)
        right.addWidget(self._measurements, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)
        layout.addLayout(left, 1)
        layout.addWidget(right_column)

    @property
    def is_running(self) -> bool:
        return self._runner.is_running

    def refresh_profiles(self) -> None:
        current = self._profile.currentText()
        self._profile.clear()
        self._profile.addItems(eol_config.list_test_profiles())
        if self._missing_profile and self._profile.findText(self._missing_profile) < 0:
            self._profile.insertItem(0, self._missing_profile)
            current = self._missing_profile
        else:
            self._clear_missing()
        if current:
            self._profile.setCurrentText(current)
        standing = self._standing_notice()
        if standing:
            self.show_notice(standing)
        elif self.notice_text() == NO_PROFILES_NOTICE:
            self.show_notice("")
        self._sync_buttons()

    def set_profile(self, name: str) -> None:
        index = self._profile.findText(name)
        if index < 0:
            self.refresh_profiles()
            index = self._profile.findText(name)
        if index >= 0:
            self._profile.setCurrentIndex(index)
            self._drop_unselected_missing()
            self._sync_buttons()

    def _drop_unselected_missing(self) -> None:
        missing = self._missing_profile
        if missing is None or self._profile.currentText() == missing:
            return
        self._clear_missing()
        self._profile.removeItem(self._profile.findText(missing))
        self._sync_buttons()

    def _clear_missing(self) -> None:
        missing = self._missing_profile
        self._missing_profile = None
        if missing is not None and self.notice_text() == missing_profile_notice(missing):
            self.show_notice("")

    def _heal_missing(self) -> None:
        missing = self._missing_profile
        if missing and self._profile.currentText() == missing and self._profile_file_exists():
            self.refresh_profiles()

    def _on_profile_activated(self, _: int) -> None:
        self._drop_unselected_missing()
        self._sync_buttons()
        self.profile_changed.emit(self._profile.currentText())

    def _standing_notice(self) -> str:
        if self._hardware_busy:
            return HARDWARE_BUSY_NOTICE
        if self._missing_profile:
            return missing_profile_notice(self._missing_profile)
        if self._profile.count() == 0:
            return NO_PROFILES_NOTICE
        return ""

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
            self.show_notice(self._standing_notice())
        self._sync_buttons()

    def set_pending_parameters(self, parameters: Mapping[str, Any]) -> None:
        self._pending_parameters = dict(parameters)
        if not self._runner.is_running:
            self._sync_plan()

    def build_request(self) -> RunRequest:
        wip = self._wip.text().strip()
        parameters = {**self._pending_parameters, "test_profile": self._profile.currentText()}
        return RunRequest(
            serial_number=self._serial.text().strip(),
            wip_id=wip or None,
            parameters=parameters,
        )

    def start_run(self, serial_number: Optional[str] = None) -> None:
        self._heal_missing()
        if serial_number is not None:
            self._serial.setText(serial_number)
        if not self._can_start():
            return
        if not self._profile_file_exists():
            self._missing_profile = self._profile.currentText()
            self.refresh_profiles()
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
            and self._profile.count() > 0
            and self._missing_profile is None
            and not self._runner.is_running
            and not self._hardware_busy
        )

    def _profile_file_exists(self) -> bool:
        return (eol_config.TEST_PROFILES_DIR / f"{self._profile.currentText()}.yaml").is_file()

    def _prepare_for_run(self) -> None:
        self._log.clear()
        self._measurements.clear()
        self._last_rows = 0
        self.show_notice("")
        self._progress.show_state(ProgressState())
        self._tiles.show_state(ProgressState())
        self._sync_plan()

    def _sync_plan(self, state: Optional[ProgressState] = None) -> None:
        plan = plan_measurements(self._profile.currentText(), self._pending_parameters)
        total = state.measurements_total if state is not None and state.measurements_total > 0 else None
        if state is not None and total:
            plan = _plan_for_run(plan, state)
        self._measurements.set_plan_text(plan_text(plan, total))
        self._measurements.set_counts(
            state.measurements_done if state is not None else 0, total or (plan.total if plan else None)
        )

    def _sync_buttons(self) -> None:
        self._heal_missing()
        running = self._runner.is_running
        self._start.setEnabled(self._can_start())
        self._abort.setEnabled(running and not self._runner.abort_requested)
        for editor in (self._serial, self._wip, self._profile):
            editor.setEnabled(not running)
        self._style_buttons(running)
        self._progress.set_run_state(running, self._runner.abort_requested)
        self._hint.setText(ABORT_HINT if running else idle_hint(self._profile.currentText()))
        if not running and self._measurements.row_count() == 0:
            self._sync_plan()
        if running != self._last_running:
            self._last_running = running
            self.running_changed.emit(running)

    def _style_buttons(self, running: bool) -> None:
        can_start = self._start.isEnabled()
        self._start.setIcon(icon("play", 16, "#FFFFFF"))
        self._abort.setIcon(icon("stop", 14, tokens.FAIL if self._abort.isEnabled() else tokens.TEXT_FAINT))
        if can_start != self._shadowed:
            self._shadowed = can_start
            if can_start:
                elevate(self._start, *PRIMARY_SHADOW)
            else:
                flatten(self._start)

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
        self._sync_plan(state)
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
