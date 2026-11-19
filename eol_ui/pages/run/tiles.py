from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from eol_ui.progress import ProgressState
from eol_ui.theme import tokens
from eol_ui.widgets import card, format_number, label
from eol_ui.widgets.basics import DASH
from eol_ui.widgets.icons import icon_pixmap

_MONO = tokens.font_stack(tokens.MONO_FAMILIES)
NO_VALUE_DETAIL = "실행 전"
_EMPTY_COLORS = (tokens.CHIP_GRAY, tokens.TEXT_FAINT)
# tile -> (icon name, icon background, icon foreground)
_COLORS: Dict[str, Tuple[str, str, str]] = {
    "temperature": ("temp", "#FEF0C7", "#B54708"),
    "force": ("force", tokens.ACCENT_SOFT, tokens.ACCENT),
    "power": ("power", tokens.PASS_SOFT, tokens.PASS_TEXT),
    "robot": ("robot", "#F4EBFF", "#6941C6"),
}


class _Tile:
    def __init__(self, title: str, name: str) -> None:
        self.name = name
        self.widget = card()
        self.icon = QLabel()
        self.icon.setFixedSize(26, 26)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value = label(DASH)
        self.value.setObjectName(f"tile-{name}")
        self.unit = label("")
        self.unit.setStyleSheet(f"font-size: 14px; font-weight: 500; color: {tokens.TEXT_MUTED};")
        self.detail = label(NO_VALUE_DETAIL)
        self.detail.setStyleSheet(f"font-family: {_MONO}; font-size: 12px; color: {tokens.TEXT_MUTED};")
        caption = label(title, "caption")
        caption.setStyleSheet("font-size: 11px;")

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.icon)
        head.addWidget(caption, 1)
        figure = QHBoxLayout()
        figure.setSpacing(4)
        figure.addWidget(self.value)
        figure.addWidget(self.unit, 0, Qt.AlignmentFlag.AlignBottom)
        figure.addStretch(1)
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addLayout(head)
        layout.addLayout(figure)
        layout.addWidget(self.detail)
        self.show(None, "", NO_VALUE_DETAIL)

    def show(self, number: Optional[str], unit: str, detail: str, value_color: Optional[str] = None) -> None:
        icon_name, icon_background, icon_color = _COLORS[self.name]
        if number is None:
            icon_background, icon_color = _EMPTY_COLORS
        self.icon.setStyleSheet(f"background: {icon_background}; border-radius: 8px;")
        self.icon.setPixmap(icon_pixmap(icon_name, 14, icon_color))
        color = tokens.TEXT_FAINT if number is None else (value_color or tokens.TEXT)
        self.value.setText(DASH if number is None else number)
        self.value.setStyleSheet(f"font-family: {_MONO}; font-size: 26px; font-weight: 600; color: {color};")
        self.unit.setText(unit if number is not None else "")
        self.detail.setText(detail)

    def text(self) -> str:
        unit = self.unit.text()
        if not unit:
            return self.value.text()
        return f"{self.value.text()}{'' if unit == '°C' else ' '}{unit}"


def _number(value: Optional[float], digits: int, grouping: bool = False) -> Optional[str]:
    if value is None:
        return None
    if grouping:
        return f"{value:,.{digits}f}"
    return format_number(value, "", digits)


class LiveTiles(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._tiles: Dict[str, _Tile] = {
            "temperature": _Tile("MCU 온도", "temperature"),
            "force": _Tile("Force", "force"),
            "power": _Tile("전원", "power"),
            "robot": _Tile("로봇 위치", "robot"),
        }
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for index, tile in enumerate(self._tiles.values()):
            grid.addWidget(tile.widget, index // 2, index % 2)
            grid.setColumnStretch(index % 2, 1)

    def show_state(self, state: ProgressState) -> None:
        actual = _number(state.mcu_actual_temperature, 1)
        target = format_number(state.mcu_target_temperature)
        self._tiles["temperature"].show(
            actual, "°C", NO_VALUE_DETAIL if actual is None else f"목표 {target} ℃" if state.mcu_target_temperature is not None else "목표 —"
        )
        force = _number(state.last_force, 3)
        self._tiles["force"].show(force, "kgf", "최근 측정" if force is not None else NO_VALUE_DETAIL)
        power = self._tiles["power"]
        if state.power_on is None:
            power.show(None, "", NO_VALUE_DETAIL)
        else:
            power.show(
                "ON" if state.power_on else "OFF",
                "",
                f"{format_number(state.power_voltage, 'V')} · {format_number(state.power_current, 'A')}",
                tokens.PASS_TEXT if state.power_on else None,
            )
        robot = _number(state.robot_position, 0, grouping=True)
        self._tiles["robot"].show(robot, "µm", "스트로크 위치" if robot is not None else NO_VALUE_DETAIL)

    def texts(self) -> Dict[str, str]:
        return {name: tile.text() for name, tile in self._tiles.items()}

    def detail(self, name: str) -> str:
        return self._tiles[name].detail.text()
