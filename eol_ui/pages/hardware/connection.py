from __future__ import annotations

import asyncio
from typing import Set

from PySide6.QtCore import QThread, Signal

from eol_ui.settings import HardwareStore
from eol_ui.settings.hardware_store import DEVICES


_UNFINISHED: Set[QThread] = set()


class ConnectionTestThread(QThread):
    done = Signal(object)

    def __init__(self, store: HardwareStore) -> None:
        super().__init__()
        self._store = store
        _UNFINISHED.add(self)
        self.finished.connect(self.deleteLater)
        self.destroyed.connect(lambda *_, thread=self: _UNFINISHED.discard(thread))

    def run(self) -> None:
        try:
            result = asyncio.run(self._store.connection_test())
        except Exception as error:
            message = str(error) or type(error).__name__
            result = {device: (False, message) for device in DEVICES}
        self.done.emit(result)
