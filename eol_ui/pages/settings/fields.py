from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eol_ui.settings import ParamSpec
from eol_ui.widgets import Badge, label, set_property

_UNIT_TEXT = {"C": "℃", "um": "µm", "um/s": "µm/s", "um/s2": "µm/s²"}
CHANGED_TEXT = "변경"


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "켜짐" if value else "꺼짐"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def range_hint(spec: ParamSpec) -> str:
    if spec.min is None or spec.max is None:
        return ""
    return f"{spec.min:g} – {spec.max:g}"


class ParamField(QWidget):
    edited = Signal(str, object)

    def __init__(self, spec: ParamSpec, title: str) -> None:
        super().__init__()
        self.spec = spec
        self._loading = False
        self._range = range_hint(spec)
        self._title = label(title)
        self._title.setObjectName(f"title-{spec.name}")
        self._badge = Badge(CHANGED_TEXT, "CHANGED")
        self._badge.setObjectName(f"changed-{spec.name}")
        self._hint = label("", "hint")
        self._hint.setObjectName(f"hint-{spec.name}")
        self._error = label("", "field-error")
        self._error.setObjectName(f"error-{spec.name}")
        self._error.setWordWrap(True)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self._title)
        head.addWidget(self._badge)
        head.addStretch(1)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.addLayout(head)
        self._build_editor(self._layout)
        self._layout.addWidget(self._hint)
        self._layout.addWidget(self._error)
        self.show_state(False, None, "")

    def _build_editor(self, layout: QVBoxLayout) -> None:
        self._edit = QLineEdit()
        self._edit.setObjectName(f"input-{self.spec.name}")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._edit, 1)
        unit = _UNIT_TEXT.get(self.spec.unit or "", self.spec.unit or "")
        if unit:
            row.addWidget(label(unit, "muted"))
        layout.addLayout(row)
        self._edit.textChanged.connect(self._on_text)

    def _on_text(self, text: str) -> None:
        if not self._loading:
            self.edited.emit(self.spec.name, text)

    def load(self, value: Any) -> None:
        self._loading = True
        try:
            self._set_editor_value(value)
        finally:
            self._loading = False

    def _set_editor_value(self, value: Any) -> None:
        self._edit.setText(value if isinstance(value, str) else str(value))

    def _error_target(self) -> QWidget:
        return self._edit

    def show_state(self, changed: bool, error: Optional[str], baseline_text: str) -> None:
        self._badge.setVisible(changed)
        parts = []
        if changed:
            parts.append(f"프로파일 {baseline_text}")
        if self._range:
            parts.append(self._range)
        self._hint.setText(" · ".join(parts))
        self._error.setText(error or "")
        self._error.setVisible(bool(error))
        set_property(self._error_target(), "error", bool(error))
        set_property(self._error_target(), "changed", changed)

    @property
    def edit(self) -> QLineEdit:
        return self._edit

    def changed_visible(self) -> bool:
        return not self._badge.isHidden()

    def hint_text(self) -> str:
        return self._hint.text()

    def error_text(self) -> str:
        return self._error.text()

    def has_error_property(self) -> bool:
        return bool(self._error_target().property("error"))


class BoolField(ParamField):
    def _build_editor(self, layout: QVBoxLayout) -> None:
        self._title.hide()
        self._check = QCheckBox(self._title.text())
        self._check.setObjectName(f"input-{self.spec.name}")
        layout.addWidget(self._check)
        self._check.toggled.connect(lambda checked: self._emit(checked))

    def _emit(self, checked: bool) -> None:
        if not self._loading:
            self.edited.emit(self.spec.name, checked)

    def _set_editor_value(self, value: Any) -> None:
        self._check.setChecked(bool(value))

    def _error_target(self) -> QWidget:
        return self._check

    @property
    def check(self) -> QCheckBox:
        return self._check

    @property
    def edit(self) -> QLineEdit:
        raise AttributeError("BoolField has no text editor")


class ListField(ParamField):
    _add_error = ""

    def _build_editor(self, layout: QVBoxLayout) -> None:
        self._values: List[float] = []
        self._chips = QWidget()
        self._chips.setObjectName(f"chips-{self.spec.name}")
        self._chip_row = QHBoxLayout(self._chips)
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        self._add_input = QLineEdit()
        self._add_input.setObjectName(f"add-input-{self.spec.name}")
        self._add_input.setPlaceholderText("값")
        self._add_input.setMaximumWidth(100)
        self._add_button = QPushButton("+ 추가")
        self._add_button.setObjectName(f"add-button-{self.spec.name}")
        self._add_button.setProperty("chip-add", True)
        self._add_input.returnPressed.connect(self._add_from_input)
        self._add_button.clicked.connect(self._add_from_input)
        layout.addWidget(self._chips)

    @property
    def edit(self) -> QLineEdit:
        return self._add_input

    @property
    def add_button(self) -> QPushButton:
        return self._add_button

    def _error_target(self) -> QWidget:
        return self._chips

    def _set_editor_value(self, value: Any) -> None:
        self._values = [float(item) for item in value]
        self._add_error = ""
        self._rebuild_chips()

    def _rebuild_chips(self) -> None:
        while self._chip_row.count():
            item = self._chip_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                if widget is not self._add_input and widget is not self._add_button:
                    widget.deleteLater()
        unit = _UNIT_TEXT.get(self.spec.unit or "", self.spec.unit or "")
        for index, value in enumerate(self._values):
            self._chip_row.addWidget(self._make_chip(index, value, unit))
        self._chip_row.addWidget(self._add_input)
        self._chip_row.addWidget(self._add_button)
        self._chip_row.addStretch(1)

    def _make_chip(self, index: int, value: float, unit: str) -> QWidget:
        chip = QWidget()
        chip.setObjectName(f"chip-{self.spec.name}-{index}")
        row = QHBoxLayout(chip)
        row.setContentsMargins(0, 0, 0, 0)
        text = label(f"{value:g} {unit}".strip())
        text.setProperty("chip", True)
        remove = QPushButton("✕")
        remove.setObjectName(f"chip-remove-{self.spec.name}-{index}")
        remove.setProperty("chip-remove", True)
        remove.clicked.connect(lambda _=False, at=index: self._remove(at))
        row.addWidget(text)
        row.addWidget(remove)
        return chip

    def chip_texts(self) -> List[str]:
        found = []
        for index in range(len(self._values)):
            chip = self._chips.findChild(QWidget, f"chip-{self.spec.name}-{index}")
            found.append(chip.findChild(QLabel).text() if chip else "")
        return found

    def _emit_values(self) -> None:
        self._rebuild_chips()
        self.edited.emit(self.spec.name, list(self._values))

    def _remove(self, index: int) -> None:
        del self._values[index]
        self._add_error = ""
        self._emit_values()

    def _add_from_input(self) -> None:
        text = self._add_input.text().strip()
        if not text:
            return
        try:
            value = float(text)
        except ValueError:
            self._add_error = "숫자가 아니다"
            self._show_add_error()
            return
        self._add_error = ""
        self._add_input.clear()
        self._values.append(value)
        self._emit_values()

    def _show_add_error(self) -> None:
        self._error.setText(self._add_error)
        self._error.setVisible(True)

    def show_state(self, changed: bool, error: Optional[str], baseline_text: str) -> None:
        super().show_state(changed, error or self._add_error or None, baseline_text)


__all__ = [
    "BoolField",
    "CHANGED_TEXT",
    "ListField",
    "ParamField",
    "format_value",
    "range_hint",
]
