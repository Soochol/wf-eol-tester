from __future__ import annotations

import sys
from typing import Optional, Sequence

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from eol_ui.main_window import APP_NAME, MainWindow
from eol_ui.theme import stylesheet


def main(argv: Optional[Sequence[str]] = None) -> int:
    app = QApplication(list(argv if argv is not None else sys.argv))
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(stylesheet())
    window = MainWindow()
    window.show()
    code = app.exec()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return code
