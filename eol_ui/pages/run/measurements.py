from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from eol_ui.widgets import Badge, RangeBar, card, format_number, judge_range, label
from eol_ui.widgets.basics import verdict_kind

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


class _RowView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._title = label("", "mono")
        self._force = label("", "mono")
        self._badge = Badge(PENDING_TEXT)
        self._bar = RangeBar()
        top = QHBoxLayout()
        top.addWidget(self._title, 1)
        top.addWidget(self._force)
        top.addWidget(self._badge)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addLayout(top)
        layout.addWidget(self._bar)

    def show_row(self, row: MeasureRow) -> None:
        self._title.setText(f"{format_number(row.temperature, '°C')} · {format_number(row.position, 'µm', 0)}")
        self._force.setText(f"{format_number(row.force, ' kgf', 3)}")
        self._bar.show_value(row.force, row.min_value, row.max_value)
        self._badge.set_kind(verdict_kind(row.passed), _badge_text(row))

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
        self._empty = label("측정 값이 아직 없습니다", "muted")
        frame = card()
        self._body = QVBoxLayout(frame)
        self._body.addWidget(label("측정 결과", "title"))
        self._body.addWidget(self._empty)
        self._body.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

    def clear(self) -> None:
        for view in self._views:
            view.setParent(None)
            view.deleteLater()
        self._rows.clear()
        self._views.clear()
        self._empty.show()

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
        self._body.insertWidget(self._body.count() - 1, view)
        self._rows.append(row)
        self._views.append(view)


__all__ = ["MeasureRow", "MeasurementList", "parse_measurement_name"]
