from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout

from eol_ui.progress import Phase, ProgressState, StageStatus
from eol_ui.widgets import card, format_duration, label, set_property

_STAGE_TITLES = ((Phase.SETUP, "Setup"), (Phase.FORCE_TEST, "Force Test"), (Phase.TEARDOWN, "Teardown"))
_STATUS_TEXT = {
    StageStatus.PENDING: "대기",
    StageStatus.RUNNING: "진행 중",
    StageStatus.DONE: "완료",
    StageStatus.FAILED: "실패",
}


class ProgressCard:
    def __init__(self) -> None:
        self.widget = card()
        self._stage_labels: Dict[Phase, object] = {}
        self._percent = label("0%", "percent")
        self._percent.setObjectName("percent")
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._activity = label("대기 중")
        self._activity.setObjectName("activity")
        self._timing = label("", "muted")
        self._timing.setObjectName("timing")
        self._chips = {name: label("", None) for name in ("temperature", "position", "repetition")}
        for chip in self._chips.values():
            chip.setProperty("chip", True)

        stages = QGridLayout()
        for column, (phase, title) in enumerate(_STAGE_TITLES):
            stages.addWidget(label(title, "title"), 0, column)
            status = label("")
            status.setObjectName(f"stage-{phase.value}")
            self._stage_labels[phase] = status
            stages.addWidget(status, 1, column)

        chips = QHBoxLayout()
        for chip in self._chips.values():
            chips.addWidget(chip)
        chips.addStretch(1)

        head = QHBoxLayout()
        head.addWidget(label("진행 상태", "title"))
        head.addStretch(1)
        head.addWidget(self._percent)

        layout = QVBoxLayout(self.widget)
        layout.addLayout(head)
        layout.addLayout(stages)
        layout.addWidget(self._bar)
        layout.addLayout(chips)
        layout.addWidget(self._activity)
        layout.addWidget(self._timing)
        self.show_state(ProgressState())

    def show_state(self, state: ProgressState) -> None:
        for phase, widget in self._stage_labels.items():
            stage = state.stages[phase]
            widget.setText(self._stage_text(phase, state))
            set_property(widget, "stage", stage.status.value)
        self._percent.setText(f"{state.percent:.0f}%")
        self._bar.setValue(int(state.percent * 10))
        self._chips["temperature"].setText(f"온도 {state.temperature[0]}/{state.temperature[1]}")
        self._chips["position"].setText(f"위치 {state.position[0]}/{state.position[1]}")
        self._chips["repetition"].setText(f"반복 {state.repetition[0]}/{state.repetition[1]}")
        self._activity.setText(state.activity)
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
        return self._stage_labels[phase].text()

    def activity_text(self) -> str:
        return self._activity.text()


__all__ = ["ProgressCard"]
