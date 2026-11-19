from __future__ import annotations

import asyncio
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from eol_ui.settings import HardwareStore
from eol_ui.settings.hardware_store import DEVICES


class ConnectionTestThread(QThread):
    done = Signal(object)

    def __init__(self, store: HardwareStore, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._store = store

    def run(self) -> None:
        try:
            result = asyncio.run(self._store.connection_test())
        except Exception as error:
            message = str(error) or type(error).__name__
            result = {device: (False, message) for device in DEVICES}
        self.done.emit(result)
