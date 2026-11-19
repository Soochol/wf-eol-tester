from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from eol_ui.theme import tokens
from eol_ui.widgets import Badge, RangeBar, card, format_number, judge_range, label
from eol_ui.widgets.basics import verdict_kind
from eol_ui.widgets.icons import icon_pixmap

_MEASUREMENT_NAME = re.compile(r"^force_(-?\d+(?:\.\d+)?)C_(-?\d+(?:\.\d+)?)um$")

PENDING_TEXT = "판정 대기"
INCOMPLETE_TEXT = "미완료"

Key = Tuple[Optional[float], Optional[float]]


@dataclass(frozen=True)
class MeasureRow:
    temperature: Optional[float]
    position: Optional[float]
    force: float
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    passed: Optional[bool] = None
    incomplete: bool = False

    @property
    def key(self) -> Key:
        return (self.temperature, self.position)


def parse_measurement_name(name: str) -> Key:
    match = _MEASUREMENT_NAME.match(name)
    if match is None:
        return (None, None)
    return (float(match.group(1)), float(match.group(2)))


_ROW_BACKGROUNDS = {"PENDING": tokens.ACCENT_FAINT, "FAIL": tokens.FAIL_FAINT}
_MONO = tokens.font_stack(tokens.MONO_FAMILIES)


class _RowView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._title = label("", None)
        self._title.setStyleSheet(f"font-family: {_MONO}; font-size: 14px; font-weight: 500;")
        self._force = label("", None)
        self._force.setStyleSheet(f"font-family: {_MONO}; font-size: 15px; font-weight: 600;")
        self._badge = Badge(PENDING_TEXT)
        self._badge.setMinimumWidth(56)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bar = RangeBar()
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._title, 1)
        top.addWidget(self._force)
        top.addWidget(self._badge)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 11, 18, 11)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(self._bar)

    def show_row(self, row: MeasureRow) -> None:
        self._title.setText(f"{format_number(row.temperature, '°C')} · {format_number(row.position, 'µm', 0)}")
        self._force.setText(f"{format_number(row.force, ' kgf', 3)}")
        self._bar.show_value(row.force, row.min_value, row.max_value)
        kind = verdict_kind(row.passed)
        self._badge.set_kind(kind, _badge_text(row))
        background = _ROW_BACKGROUNDS.get(kind, "transparent")
        self.setStyleSheet(f"_RowView {{ background: {background}; border-top: 1px solid {tokens.DIVIDER_SOFT}; }}")

    @property
    def badge_text(self) -> str:
        return self._badge.text()


def _badge_text(row: MeasureRow) -> str:
    if row.passed is None:
        return INCOMPLETE_TEXT if row.incomplete else PENDING_TEXT
    return "PASS" if row.passed else "FAIL"


class MeasurementList(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._rows: List[MeasureRow] = []
        self._views: List[_RowView] = []
        self._plan_text = ""
        muted = f"font-size: 12px; color: {tokens.TEXT_MUTED}; font-family: {_MONO};"
        self._limits = label("", None)
        self._limits.setObjectName("measure-limits")
        self._limits.setStyleSheet(muted)
        self._limits.hide()
        self._counts = label("", None)
        self._counts.setObjectName("measure-counts")
        self._counts.setStyleSheet(muted)

        self._empty = QWidget()
        self._empty.setObjectName("measure-empty")
        art = QLabel()
        art.setPixmap(icon_pixmap("measure-empty", 40, tokens.TEXT_FAINT))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline = label("아직 측정값이 없습니다", None)
        headline.setStyleSheet(f"font-size: 14px; font-weight: 500; color: {tokens.TEXT_MUTED};")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._plan = label("", None)
        self._plan.setObjectName("measure-plan")
        self._plan.setStyleSheet(f"font-size: 12px; color: {tokens.TEXT_FAINT};")
        self._plan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._plan.hide()
        empty = QVBoxLayout(self._empty)
        empty.setContentsMargins(18, 32, 18, 32)
        empty.setSpacing(10)
        empty.addStretch(1)
        empty.addWidget(art)
        empty.addWidget(headline)
        empty.addWidget(self._plan)
        empty.addStretch(1)

        head = QHBoxLayout()
        head.setContentsMargins(18, 0, 18, 12)
        head.setSpacing(10)
        head.addWidget(label("측정 결과", "title"))
        head.addWidget(self._limits)
        head.addStretch(1)
        head.addWidget(self._counts)

        frame = card()
        self._body = QVBoxLayout(frame)
        self._body.setContentsMargins(0, 16, 0, 6)
        self._body.setSpacing(0)
        self._body.addLayout(head)
        self._body.addWidget(self._empty, 1)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self._scroll.setWidget(self._rows_host)
        self._scroll.setMinimumHeight(0)
        self._scroll.hide()
        self._body.addWidget(self._scroll, 1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

    def clear(self) -> None:
        for view in self._views:
            view.setParent(None)
            view.deleteLater()
        self._rows.clear()
        self._views.clear()
        self._limits.hide()
        self._scroll.hide()
        self._empty.show()

    def set_plan_text(self, text: str) -> None:
        self._plan_text = text
        self._plan.setText(text)
        self._plan.setVisible(bool(text))

    def plan_text(self) -> str:
        return self._plan.text() if not self._plan.isHidden() else ""

    def empty_visible(self) -> bool:
        return not self._empty.isHidden()

    def set_counts(self, done: int, total: Optional[int]) -> None:
        self._counts.setText("" if not total else f"{done} / {total}")

    def counts_text(self) -> str:
        return self._counts.text()

    def limits_text(self) -> str:
        return self._limits.text() if not self._limits.isHidden() else ""

    def row_count(self) -> int:
        return len(self._rows)

    def rows(self) -> List[MeasureRow]:
        return list(self._rows)

    def badge_texts(self) -> List[str]:
        return [view.badge_text for view in self._views]

    def add_pending(self, temperature: Optional[float], position: Optional[float], force: float) -> None:
        self._append(MeasureRow(temperature, position, force))

    def apply_event(
        self,
        name: str,
        value: float,
        min_value: Optional[float],
        max_value: Optional[float],
        passed: Optional[bool],
    ) -> None:
        if min_value is not None and max_value is not None:
            self._limits.setText(
                f"기준 {format_number(min_value, digits=2)} – {format_number(max_value, digits=2)} kgf"
            )
            self._limits.show()
        key = parse_measurement_name(name)
        verdict = passed if passed is not None else judge_range(value, min_value, max_value)
        matched = [i for i, row in enumerate(self._rows) if row.key == key]
        if not matched:
            self._append(MeasureRow(key[0], key[1], value, min_value, max_value, verdict))
            return
        for index in matched:
            updated = replace(self._rows[index], min_value=min_value, max_value=max_value, passed=verdict)
            self._rows[index] = updated
            self._views[index].show_row(updated)

    def close_pending(self) -> None:
        for index, row in enumerate(self._rows):
            if row.passed is None and not row.incomplete:
                closed = replace(row, incomplete=True)
                self._rows[index] = closed
                self._views[index].show_row(closed)

    def _append(self, row: MeasureRow) -> None:
        view = _RowView()
        view.show_row(row)
        self._empty.hide()
        self._scroll.show()
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, view)
        self._rows.append(row)
        self._views.append(view)


__all__ = ["MeasureRow", "MeasurementList", "parse_measurement_name"]
