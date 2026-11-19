from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QHeaderView, QStyledItemDelegate, QTableWidget, QWidget

from eol_ui.theme import tokens
from eol_ui.widgets.icons import icon_pixmap

# verdict -> (gradient start, gradient end, shadow rgba)
BANNER_COLORS: Dict[str, Tuple[str, str, QColor]] = {
    "PASS": ("#079455", "#067647", QColor(7, 148, 85, 64)),
    "FAIL": ("#D92D20", "#B42318", QColor(217, 45, 32, 64)),
    "ERROR": ("#D92D20", "#B42318", QColor(217, 45, 32, 64)),
    "ABORTED": ("#475467", "#344054", QColor(71, 84, 103, 64)),
}
BANNER_ICONS = {"PASS": "check", "FAIL": "x", "ERROR": "x", "ABORTED": "stop"}
BANNER_RADIUS = 16
_COLUMN_SHARES = (16, 19, 17, 34, 14)


class GradientBanner(QFrame):
    """Verdict banner. Paints a diagonal gradient chosen by its `banner` property."""

    def paintEvent(self, event) -> None:
        start, end, _ = BANNER_COLORS.get(str(self.property("banner")), BANNER_COLORS["ABORTED"])
        gradient = QLinearGradient(QPointF(0, 0), QPointF(self.width(), self.height()))
        gradient.setColorAt(0, QColor(start))
        gradient.setColorAt(1, QColor(end))
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), BANNER_RADIUS, BANNER_RADIUS)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillPath(path, gradient)


class CircleIcon(QWidget):
    """Filled circle with an optional centred icon."""

    def __init__(self, diameter: int, background: str, glyph: Optional[str] = None,
                 glyph_size: int = 16, glyph_color: str = "#FFFFFF") -> None:
        super().__init__()
        self.setFixedSize(diameter, diameter)
        self._background = QColor(background)
        self._glyph = glyph
        self._glyph_size = glyph_size
        self._glyph_color = glyph_color

    def set_style(self, background: str, glyph: Optional[str], glyph_color: str) -> None:
        self._background = QColor(background)
        self._glyph = glyph
        self._glyph_color = glyph_color
        self.update()

    @property
    def glyph(self) -> Optional[str]:
        return self._glyph

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._background)
        painter.drawEllipse(self.rect())
        if self._glyph:
            side = self._glyph_size
            pixmap = icon_pixmap(self._glyph, side, self._glyph_color)
            painter.drawPixmap((self.width() - side) // 2, (self.height() - side) // 2, pixmap)


class _RowBackgroundDelegate(QStyledItemDelegate):
    """Stylesheet `::item` rules ignore BackgroundRole, so paint it by hand."""

    def paint(self, painter, option, index) -> None:
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background is not None:
            painter.fillRect(option.rect, background)
        super().paint(painter, option, index)


class ResultTable(QTableWidget):
    """Table whose columns follow fixed shares of the viewport width."""

    STYLE = f"""
QTableWidget {{ background: white; border: none; }}
QHeaderView::section {{ background: #F9FAFB; border: none; border-bottom: 1px solid {tokens.DIVIDER};
  padding: 10px 14px; color: {tokens.TEXT_MUTED}; font-size: 12px; font-weight: 600; }}
QTableWidget::item {{ padding: 0 14px; border-bottom: 1px solid {tokens.DIVIDER_SOFT}; }}
"""

    def __init__(self, columns: int) -> None:
        super().__init__(0, columns)
        self.setStyleSheet(self.STYLE)
        self.setItemDelegate(_RowBackgroundDelegate(self))
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(46)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setHighlightSections(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setShowGrid(False)
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumHeight(120)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_columns()

    def _fit_columns(self) -> None:
        width = self.viewport().width()
        total = sum(_COLUMN_SHARES)
        used = 0
        for column, share in enumerate(_COLUMN_SHARES):
            size = width - used if column == len(_COLUMN_SHARES) - 1 else width * share // total
            self.setColumnWidth(column, size)
            used += size
