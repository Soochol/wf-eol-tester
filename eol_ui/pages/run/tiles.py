from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from eol_ui.progress import ProgressState
from eol_ui.widgets import card, format_number, label
from eol_ui.widgets.basics import DASH


class _Tile:
    def __init__(self, title: str, name: str) -> None:
        self.widget = card()
        self.value = label(DASH, "tile-value")
        self.value.setObjectName(f"tile-{name}")
        self.detail = label("", "muted")
        layout = QVBoxLayout(self.widget)
        layout.addWidget(label(title, "muted"))
        layout.addWidget(self.value)
        layout.addWidget(self.detail)


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
        for index, tile in enumerate(self._tiles.values()):
            grid.addWidget(tile.widget, index // 2, index % 2)

    def show_state(self, state: ProgressState) -> None:
        temperature = self._tiles["temperature"]
        temperature.value.setText(format_number(state.mcu_actual_temperature, "°C"))
        temperature.detail.setText(f"목표 {format_number(state.mcu_target_temperature, '°C')}")
        self._tiles["force"].value.setText(format_number(state.last_force, " kgf", 3))
        power = self._tiles["power"]
        power.value.setText(
            DASH if state.power_on is None else ("ON" if state.power_on else "OFF")
        )
        power.detail.setText(
            f"{format_number(state.power_voltage, 'V')} · {format_number(state.power_current, 'A')}"
        )
        self._tiles["robot"].value.setText(format_number(state.robot_position, " µm", 0))

    def texts(self) -> Dict[str, str]:
        return {name: tile.value.text() for name, tile in self._tiles.items()}

    def detail(self, name: str) -> str:
        return self._tiles[name].detail.text()
