from __future__ import annotations

from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from eol_ui.progress import Phase, StageStatus
from eol_ui.theme import tokens
from eol_ui.widgets import label, set_property

STAGES = ((Phase.SETUP, "Setup"), (Phase.FORCE_TEST, "Force Test"), (Phase.TEARDOWN, "Teardown"))
_MONO = tokens.font_stack(tokens.MONO_FAMILIES)

# status -> (circle background, circle border, circle text color, title color, connector color)
_COLORS: Dict[StageStatus, Tuple[str, str, str, str, str]] = {
    StageStatus.DONE: (tokens.PASS, tokens.PASS, "#FFFFFF", tokens.TEXT, tokens.PASS),
    StageStatus.RUNNING: (tokens.ACCENT_SOFT, tokens.ACCENT, tokens.ACCENT, tokens.TEXT, "#EAECF0"),
    StageStatus.PENDING: ("#FFFFFF", tokens.INPUT_BORDER, tokens.TEXT_FAINT, tokens.TEXT_MUTED, "#EAECF0"),
    StageStatus.FAILED: (tokens.FAIL_SOFT, tokens.FAIL, tokens.FAIL, tokens.TEXT, "#EAECF0"),
}
_MARKS = {StageStatus.DONE: "✓", StageStatus.FAILED: "✕"}


class _Step(QWidget):
    def __init__(self, phase: Phase, number: int, title: str, last: bool) -> None:
        super().__init__()
        self._number = number
        self.circle = QLabel(str(number))
        self.circle.setFixedSize(34, 34)
        self.circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = label(title)
        self.sub = label("")
        self.sub.setObjectName(f"stage-{phase.value}")
        self.sub.setStyleSheet(f"font-family: {_MONO}; font-size: 12px;")
        self.line = QFrame()
        self.line.setFixedHeight(2)
        self.line.setVisible(not last)

        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(self.title)
        text.addWidget(self.sub)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.circle)
        row.addLayout(text)
        row.addSpacing(4)
        row.addWidget(self.line, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(10)

    def show_status(self, status: StageStatus, sub_text: str) -> None:
        background, border, number, title, connector = _COLORS[status]
        self.circle.setText(_MARKS.get(status, str(self._number)))
        self.circle.setStyleSheet(
            f"background: {background}; border: 2px solid {border}; border-radius: 17px; "
            f"color: {number}; font-family: {_MONO}; font-size: 14px; font-weight: 700;"
        )
        self.title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {title};")
        self.line.setStyleSheet(f"background: {connector}; border: none; border-radius: 1px;")
        self.sub.setText(sub_text)
        set_property(self.sub, "stage", status.value)
        self.setProperty("status", status.value)


class Stepper(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._steps: Dict[Phase, _Step] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        for column, (phase, title) in enumerate(STAGES):
            step = _Step(phase, column + 1, title, last=column == len(STAGES) - 1)
            self._steps[phase] = step
            grid.addWidget(step, 0, column)
            grid.setColumnStretch(column, 1)

    def show_status(self, phase: Phase, status: StageStatus, sub_text: str) -> None:
        self._steps[phase].show_status(status, sub_text)

    def sub_text(self, phase: Phase) -> str:
        return self._steps[phase].sub.text()

    def mark(self, phase: Phase) -> str:
        return self._steps[phase].circle.text()

    def status(self, phase: Phase) -> str:
        return str(self._steps[phase].property("status"))
