from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from eol_ui.pages.hardware import HardwarePage
from eol_ui.settings import HardwareStore

from .parameters import ParametersPanel

MENU = (("테스트 파라미터", "params"), ("하드웨어 연결", "hardware"))


class SettingsPage(QWidget):
    def __init__(self, store: Optional[HardwareStore] = None) -> None:
        super().__init__()
        self.setObjectName("settings-page")
        self.parameters = ParametersPanel()
        self.hardware = HardwarePage(store)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.parameters)
        self._stack.addWidget(self.hardware)
        menu = QVBoxLayout()
        group = QButtonGroup(self)
        for index, (text, key) in enumerate(MENU):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setProperty("side", True)
            button.setObjectName(f"menu-{key}")
            group.addButton(button, index)
            menu.addWidget(button)
        menu.addStretch(1)
        group.idClicked.connect(self._stack.setCurrentIndex)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(menu)
        layout.addWidget(self._stack, 1)
