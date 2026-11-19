from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QWidget

from eol_ui.theme import tokens

DASH = "—"
_HEADROOM = 1.25


def set_property(widget: QWidget, name: str, value: object) -> None:
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def card() -> QFrame:
    frame = QFrame()
    frame.setProperty("card", True)
    return frame


def label(text: str = "", role: Optional[str] = None) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    return widget


def format_number(value: Optional[float], unit: str = "", digits: int = 1) -> str:
    if value is None:
        return DASH
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return f"{text}{unit}"


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return DASH
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class Badge(QLabel):
    def __init__(self, text: str = "", kind: str = "PENDING") -> None:
        super().__init__(text)
        self.set_kind(kind, text)

    def set_kind(self, kind: str, text: Optional[str] = None) -> None:
        if text is not None:
            self.setText(text)
        set_property(self, "badge", kind)


def verdict_kind(passed: Optional[bool]) -> str:
    if passed is None:
        return "PENDING"
    return "PASS" if passed else "FAIL"


def judge_range(value: float, low: Optional[float], high: Optional[float]) -> Optional[bool]:
    if low is None or high is None:
        return None
    return low <= value <= high


class RangeBar(QProgressBar):
    def __init__(self) -> None:
        super().__init__()
        self.setTextVisible(False)
        self.setRange(0, 1000)
        self.setValue(0)

    def show_value(self, value: float, low: Optional[float], high: Optional[float]) -> None:
        passed = judge_range(value, low, high)
        if low is None or high is None or high <= 0:
            self.setValue(0)
        else:
            fraction = min(max(value / (high * _HEADROOM), 0.0), 1.0)
            self.setValue(int(fraction * 1000))
        set_property(self, "range", verdict_kind(passed))
        self.setToolTip(
            f"{format_number(low, digits=2)} – {format_number(high, digits=2)} kgf, "
            f"측정 {format_number(value, digits=3)}"
        )


def status_color(known: Optional[bool]) -> str:
    if known is None:
        return tokens.UNKNOWN
    return tokens.PASS if known else tokens.FAIL
