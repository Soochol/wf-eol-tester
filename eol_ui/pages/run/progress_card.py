from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from eol_ui.progress import Phase, ProgressState, StageStatus
from eol_ui.theme import tokens
from eol_ui.widgets import card, format_duration, label, set_property

from .spinner import SpinnerIcon
from .stepper import STAGES, Stepper

IDLE_ACTIVITY = "시리얼 번호를 입력하고 시작을 누르세요"
_DEFAULT_ACTIVITY = ProgressState().activity
_MONO = tokens.font_stack(tokens.MONO_FAMILIES)
_STATUS_TEXT = {
    StageStatus.PENDING: "대기",
    StageStatus.RUNNING: "진행 중",
    StageStatus.DONE: "완료",
    StageStatus.FAILED: "실패",
}
# badge kind -> (text, foreground, background)
_BADGES = {
    "idle": ("대기", tokens.TEXT_SECONDARY, tokens.CHIP_GRAY),
    "running": ("테스트 진행 중", tokens.ACCENT, tokens.ACCENT_SOFT),
    "aborting": ("중단 요청됨", tokens.FAIL_TEXT, tokens.FAIL_SOFT),
    "finished": ("완료", tokens.PASS_TEXT, tokens.PASS_BADGE),
}


class ProgressCard:
    def __init__(self) -> None:
        self.widget = card()
        self._running = False
        self._aborting = False
        self._has_run = False
        self._status = QLabel()
        self._status.setObjectName("status-badge")
        self._percent = label("0%", "percent")
        self._percent.setObjectName("percent")
        self._percent.setStyleSheet(f"font-family: {_MONO}; font-size: 20px; font-weight: 600;")
        self._percent.setMinimumWidth(56)
        self._percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._bar.setProperty("thick", True)
        self._activity = label("")
        self._activity.setObjectName("activity")
        self._activity.setStyleSheet(f"font-size: 14px; color: {tokens.TEXT_STRONG};")
        self._timing = label("", None)
        self._timing.setObjectName("timing")
        self._timing.setStyleSheet(f"font-family: {_MONO}; font-size: 13px; color: {tokens.TEXT_MUTED};")
        self._chips = {name: label("", "mono") for name in ("temperature", "position", "repetition")}
        for chip in self._chips.values():
            chip.setProperty("chip", True)
        self._spinner = SpinnerIcon()
        self._stepper = Stepper()

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(label("진행 상태", "title"))
        head.addWidget(self._status)
        head.addStretch(1)
        head.addWidget(self._timing)

        progress = QHBoxLayout()
        progress.setSpacing(16)
        progress.addWidget(self._bar, 1)
        progress.addWidget(self._percent)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for chip in self._chips.values():
            chips.addWidget(chip)
        chips.addSpacing(6)
        chips.addWidget(self._spinner)
        chips.addWidget(self._activity)
        chips.addStretch(1)

        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(16)
        layout.addLayout(head)
        layout.addWidget(self._stepper)
        layout.addLayout(progress)
        layout.addLayout(chips)
        self._state = ProgressState()
        self.show_state(self._state)
        self._show_badge()

    def set_run_state(self, running: bool, aborting: bool = False) -> None:
        if running:
            self._has_run = True
        self._running = running
        self._aborting = running and aborting
        self._spinner.set_spinning(running)
        self._show_badge()
        self.show_state(self._state)

    def reset(self) -> None:
        self._has_run = False
        self._running = False
        self._aborting = False
        self._spinner.set_spinning(False)
        self._show_badge()

    def _show_badge(self) -> None:
        if self._aborting:
            kind = "aborting"
        elif self._running:
            kind = "running"
        elif self._has_run:
            kind = "finished"
        else:
            kind = "idle"
        text, foreground, background = _BADGES[kind]
        self._status.setText(text)
        self._status.setStyleSheet(
            f"background: {background}; color: {foreground}; border-radius: 12px; "
            "padding: 4px 10px; font-size: 12px; font-weight: 600;"
        )

    def show_state(self, state: ProgressState) -> None:
        self._state = state
        for phase, _ in STAGES:
            self._stepper.show_status(phase, state.stages[phase].status, self._stage_text(phase, state))
        self._percent.setText(f"{state.percent:.0f}%")
        self._bar.setValue(int(state.percent * 10))
        self._chips["temperature"].setText(f"온도 {state.temperature[0]}/{state.temperature[1]}")
        self._chips["position"].setText(f"위치 {state.position[0]}/{state.position[1]}")
        self._chips["repetition"].setText(f"반복 {state.repetition[0]}/{state.repetition[1]}")
        idle = not self._running and state.activity == _DEFAULT_ACTIVITY
        self._activity.setText(IDLE_ACTIVITY if idle else state.activity)
        self._timing.setText(
            f"경과 {format_duration(state.elapsed)} · 예상 잔여 {format_duration(state.remaining)}"
        )

    @staticmethod
    def _stage_text(phase: Phase, state: ProgressState) -> str:
        stage = state.stages[phase]
        text = _STATUS_TEXT[stage.status]
        if phase is Phase.FORCE_TEST and stage.status is StageStatus.RUNNING:
            text = f"측정 {state.measurements_done}/{state.measurements_total}"
        if stage.duration is not None:
            text += f" · {format_duration(stage.duration)}"
        return text

    def percent_value(self) -> float:
        return float(self._percent.text().rstrip("%") or 0)

    def stage_text(self, phase: Phase) -> str:
        return self._stepper.sub_text(phase)

    def stage_mark(self, phase: Phase) -> str:
        return self._stepper.mark(phase)

    def stage_status(self, phase: Phase) -> str:
        return self._stepper.status(phase)

    def status_text(self) -> str:
        return self._status.text()

    def activity_text(self) -> str:
        return self._activity.text()

    def spinner_visible(self) -> bool:
        return not self._spinner.isHidden()

    def spinner_active(self) -> bool:
        return self._spinner.is_spinning()


__all__ = ["ProgressCard"]
