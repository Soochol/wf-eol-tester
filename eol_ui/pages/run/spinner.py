from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtWidgets import QLabel, QWidget

from eol_ui.theme import tokens
from eol_ui.widgets.icons import icon_pixmap

_SIZE = 16
_STEP_DEGREES = 30
_INTERVAL_MS = 80


class SpinnerIcon(QLabel):
    """Rotating arc shown only while a run is in progress. The timer stops when hidden or destroyed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_SIZE, _SIZE)
        self._angle = 0
        self._base = icon_pixmap("spinner", _SIZE, tokens.ACCENT)
        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)
        self.setPixmap(self._base)
        self.hide()

    def set_spinning(self, spinning: bool) -> None:
        if spinning:
            self.show()
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._angle = 0
            self.setPixmap(self._base)
            self.hide()

    def is_spinning(self) -> bool:
        return self._timer.isActive()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._angle = (self._angle + _STEP_DEGREES) % 360
        side = self._base.width()
        rotated: QPixmap = self._base.transformed(
            QTransform().rotate(self._angle), Qt.TransformationMode.SmoothTransformation
        )
        x = (rotated.width() - side) // 2
        y = (rotated.height() - side) // 2
        cropped = rotated.copy(x, y, side, side)
        cropped.setDevicePixelRatio(self._base.devicePixelRatio())
        self.setPixmap(cropped)
