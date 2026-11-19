from __future__ import annotations

from collections import deque
from typing import Deque, List

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedLayout,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from eol_ui.runner import LogRecord
from eol_ui.theme import tokens

from .basics import card, label
from .icons import icon_pixmap

MAX_LINES = 5000

_LEVEL_RANK = {"TRACE": 0, "DEBUG": 10, "INFO": 20, "SUCCESS": 25, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}
FILTERS = (("전체", 0), ("INFO", 20), ("WARN", 30), ("ERROR", 40))

WARN_RANK = 30
ERROR_RANK = 40

EMPTY_TEXT = "시작하면 시퀀스 로그가 여기에 표시됩니다"
FILTERED_EMPTY_TEXT = "이 레벨의 로그가 없습니다"

_BADGE_TEXT = {"WARNING": "WARN", "CRITICAL": "CRIT", "SUCCESS": "OK"}
# level -> (badge text color, badge background)
_BADGE_COLORS = {
    "INFO": ("#BFDBFE", QColor(59, 130, 246, 46)),
    "WARNING": ("#FDE68A", QColor(245, 158, 11, 51)),
    "WARN": ("#FDE68A", QColor(245, 158, 11, 51)),
    "DEBUG": ("#CBD5E1", QColor(148, 163, 184, 41)),
    "TRACE": ("#CBD5E1", QColor(148, 163, 184, 41)),
    "ERROR": ("#FECACA", QColor(239, 68, 68, 56)),
    "CRITICAL": ("#FECACA", QColor(239, 68, 68, 56)),
    "SUCCESS": ("#A7F3D0", QColor(16, 185, 129, 46)),
}
_WARN_LINE = QColor(245, 158, 11, 20)
_ERROR_LINE = QColor(239, 68, 68, 26)
_BADGE_WIDTH = 46
_BADGE_HEIGHT = 18
_GAP = 12
_PAD_X = 18
_LINE_HEIGHT = 1.6
_LEVEL_ROLE = Qt.ItemDataRole.UserRole + 1
_STAMP_ROLE = Qt.ItemDataRole.UserRole + 2
_MESSAGE_ROLE = Qt.ItemDataRole.UserRole + 3


def level_rank(level: str) -> int:
    return _LEVEL_RANK.get(level.upper(), 20)


def badge_text(level: str) -> str:
    upper = level.upper()
    return _BADGE_TEXT.get(upper, upper)


def _mono_font(pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(list(tokens.MONO_FAMILIES))
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


class _LogDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._body = _mono_font(13)
        self._badge = _mono_font(11, QFont.Weight.DemiBold)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(0, int(QFontMetrics(self._body).height() * _LINE_HEIGHT) + 4)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rank = level_rank(index.data(_LEVEL_ROLE) or "")
        rect = option.rect
        if rank >= ERROR_RANK:
            painter.fillRect(rect, _ERROR_LINE)
        elif rank >= WARN_RANK:
            painter.fillRect(rect, _WARN_LINE)
        stamp_width = QFontMetrics(self._body).horizontalAdvance("00:00:00")
        x = rect.left() + _PAD_X
        painter.setFont(self._body)
        painter.setPen(QColor(tokens.LOG_TIME))
        painter.drawText(QRect(x, rect.top(), stamp_width, rect.height()), Qt.AlignmentFlag.AlignVCenter, index.data(_STAMP_ROLE))
        x += stamp_width + _GAP
        level = (index.data(_LEVEL_ROLE) or "").upper()
        color, background = _BADGE_COLORS.get(level, _BADGE_COLORS["INFO"])
        badge = QRect(x, rect.top() + (rect.height() - _BADGE_HEIGHT) // 2, _BADGE_WIDTH, _BADGE_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(badge, 4, 4)
        painter.setFont(self._badge)
        painter.setPen(QColor(color))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, badge_text(level))
        x += _BADGE_WIDTH + _GAP
        painter.setFont(self._body)
        painter.setPen(QColor(tokens.LOG_TEXT))
        message = QFontMetrics(self._body).elidedText(
            index.data(_MESSAGE_ROLE) or "", Qt.TextElideMode.ElideRight, max(rect.right() - x - _PAD_X, 0)
        )
        painter.drawText(QRect(x, rect.top(), max(rect.right() - x, 0), rect.height()), Qt.AlignmentFlag.AlignVCenter, message)
        painter.restore()


class LogPanel(QWidget):
    def __init__(self, max_lines: int = MAX_LINES) -> None:
        super().__init__()
        self._records: Deque[LogRecord] = deque(maxlen=max_lines)
        self._threshold = 0
        self._warnings = 0

        self._list = QListWidget()
        self._list.setObjectName("log")
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setItemDelegate(_LogDelegate(self._list))
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setStyleSheet(
            "QListWidget#log { border-radius: 0; border-bottom-left-radius: 13px; border-bottom-right-radius: 13px;"
            " padding: 10px 0; }"
            "QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }"
            "QScrollBar::handle:vertical { background: #334155; border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        self._count = label("0줄 · 경고 0", None)
        self._count.setObjectName("log-count")
        self._count.setStyleSheet(
            f"font-family: {tokens.font_stack(tokens.MONO_FAMILIES)}; font-size: 12px; color: {tokens.TEXT_MUTED};"
        )
        self._auto_scroll = QCheckBox("자동 스크롤")
        self._auto_scroll.setChecked(True)

        self._empty_icon = label("", None)
        self._empty_icon.setPixmap(icon_pixmap("log-empty", 28, tokens.LOG_EMPTY))
        self._empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_text = label(EMPTY_TEXT, None)
        self._empty_text.setObjectName("log-empty")
        self._empty_text.setStyleSheet(f"color: {tokens.LOG_EMPTY}; font-size: 13px;")
        self._empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty = QWidget()
        empty.setStyleSheet(f"background: {tokens.LOG_BACKGROUND};")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setSpacing(8)
        empty_layout.addStretch(1)
        empty_layout.addWidget(self._empty_icon)
        empty_layout.addWidget(self._empty_text)
        empty_layout.addStretch(1)
        self._body = QStackedLayout()
        self._body.addWidget(self._list)
        self._body.addWidget(empty)

        self._buttons = QButtonGroup(self)
        self._buttons.setExclusive(True)
        segments = QFrame()
        segments.setProperty("segmented", True)
        segment_row = QHBoxLayout(segments)
        segment_row.setContentsMargins(3, 3, 3, 3)
        segment_row.setSpacing(2)
        for text, rank in FILTERS:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName(f"filter-{text}")
            button.setProperty("segment", True)
            button.setProperty("compact", True)
            button.setChecked(rank == 0)
            button.clicked.connect(lambda _=False, r=rank: self.set_threshold(r))
            self._buttons.addButton(button)
            segment_row.addWidget(button)

        head = QFrame()
        head.setObjectName("log-head")
        head.setStyleSheet(
            f"QFrame#log-head {{ background: {tokens.CARD}; border: none; border-bottom: 1px solid {tokens.DIVIDER};"
            " border-top-left-radius: 14px; border-top-right-radius: 14px; }"
        )
        bar = QHBoxLayout(head)
        bar.setContentsMargins(20, 10, 16, 10)
        bar.setSpacing(12)
        bar.addWidget(label("로그", "title"))
        bar.addWidget(self._count)
        bar.addStretch(1)
        bar.addWidget(segments)
        bar.addWidget(self._auto_scroll)

        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(head)
        layout.addLayout(self._body, 1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self._refresh_body()

    def append(self, record: LogRecord) -> None:
        if len(self._records) == self._records.maxlen:
            self._drop_oldest()
        self._records.append(record)
        if level_rank(record.level) >= WARN_RANK:
            self._warnings += 1
        if level_rank(record.level) >= self._threshold:
            self._list.addItem(self._make_item(record))
            if self._auto_scroll.isChecked():
                self._list.scrollToBottom()
        self._update_count()
        self._refresh_body()

    def clear(self) -> None:
        self._records.clear()
        self._warnings = 0
        self._list.clear()
        self._update_count()
        self._refresh_body()

    def set_threshold(self, rank: int) -> None:
        self._threshold = rank
        self._rebuild()

    def visible_lines(self) -> List[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def item_is_warn(self, row: int) -> bool:
        return bool(self._list.item(row).data(Qt.ItemDataRole.UserRole))

    def line_count(self) -> int:
        return len(self._records)

    def count_text(self) -> str:
        return self._count.text()

    def empty_text(self) -> str:
        """The placeholder shown instead of the list, or "" while lines are visible."""
        return self._empty_text.text() if self._body.currentIndex() == 1 else ""

    def badge_texts(self) -> List[str]:
        return [badge_text(self._list.item(i).data(_LEVEL_ROLE)) for i in range(self._list.count())]

    def auto_scroll(self) -> bool:
        return self._auto_scroll.isChecked()

    def set_auto_scroll(self, enabled: bool) -> None:
        self._auto_scroll.setChecked(enabled)

    def filter_button(self, text: str) -> QPushButton:
        return self.findChild(QPushButton, f"filter-{text}")

    def _drop_oldest(self) -> None:
        oldest = self._records[0]
        if level_rank(oldest.level) >= WARN_RANK:
            self._warnings -= 1
        if level_rank(oldest.level) >= self._threshold and self._list.count():
            self._list.takeItem(0)

    def _rebuild(self) -> None:
        self._list.clear()
        for record in self._records:
            if level_rank(record.level) >= self._threshold:
                self._list.addItem(self._make_item(record))
        if self._auto_scroll.isChecked():
            self._list.scrollToBottom()
        self._refresh_body()

    def _refresh_body(self) -> None:
        if self._list.count():
            self._body.setCurrentIndex(0)
            return
        self._empty_text.setText(FILTERED_EMPTY_TEXT if self._records else EMPTY_TEXT)
        self._body.setCurrentIndex(1)

    def _update_count(self) -> None:
        self._count.setText(f"{len(self._records)}줄 · 경고 {self._warnings}")

    @staticmethod
    def _make_item(record: LogRecord) -> QListWidgetItem:
        stamp = record.timestamp.strftime("%H:%M:%S")
        item = QListWidgetItem(f"{stamp}  {record.level:<7} {record.message}")
        item.setData(Qt.ItemDataRole.UserRole, level_rank(record.level) >= WARN_RANK)
        item.setData(_LEVEL_ROLE, record.level)
        item.setData(_STAMP_ROLE, stamp)
        item.setData(_MESSAGE_ROLE, record.message)
        return item
