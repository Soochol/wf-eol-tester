from __future__ import annotations

import asyncio
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from eol_ui.settings import HardwareStore


class ConnectionTestThread(QThread):
    done = Signal(object)

    def __init__(self, store: HardwareStore, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._store = store

    def run(self) -> None:
        self.done.emit(asyncio.run(self._store.connection_test()))
