from __future__ import annotations

from collections import deque
from typing import Deque, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eol_ui.runner import LogRecord
from eol_ui.theme import tokens

from .basics import card, label

MAX_LINES = 5000

_LEVEL_RANK = {"TRACE": 0, "DEBUG": 10, "INFO": 20, "SUCCESS": 25, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}
FILTERS = (("전체", 0), ("INFO", 20), ("WARN", 30), ("ERROR", 40))

WARN_RANK = 30
ERROR_RANK = 40


def level_rank(level: str) -> int:
    return _LEVEL_RANK.get(level.upper(), 20)


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
        self._count = label("0줄 · 경고 0", "muted")
        self._count.setObjectName("log-count")
        self._auto_scroll = QCheckBox("자동 스크롤")
        self._auto_scroll.setChecked(True)

        self._buttons = QButtonGroup(self)
        self._buttons.setExclusive(True)
        bar = QHBoxLayout()
        bar.addWidget(label("로그", "title"))
        for text, rank in FILTERS:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName(f"filter-{text}")
            button.setChecked(rank == 0)
            button.clicked.connect(lambda _=False, r=rank: self.set_threshold(r))
            self._buttons.addButton(button)
            bar.addWidget(button)
        bar.addStretch(1)
        bar.addWidget(self._auto_scroll)
        bar.addWidget(self._count)

        frame = card()
        layout = QVBoxLayout(frame)
        layout.addLayout(bar)
        layout.addWidget(self._list, 1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

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

    def clear(self) -> None:
        self._records.clear()
        self._warnings = 0
        self._list.clear()
        self._update_count()

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

    def _update_count(self) -> None:
        self._count.setText(f"{len(self._records)}줄 · 경고 {self._warnings}")

    @staticmethod
    def _make_item(record: LogRecord) -> QListWidgetItem:
        stamp = record.timestamp.strftime("%H:%M:%S")
        item = QListWidgetItem(f"{stamp}  {record.level:<7} {record.message}")
        rank = level_rank(record.level)
        item.setData(Qt.ItemDataRole.UserRole, rank >= WARN_RANK)
        if rank >= ERROR_RANK:
            item.setBackground(QColor(tokens.ERROR_ROW))
            item.setForeground(QColor(tokens.FAIL))
        elif rank >= WARN_RANK:
            item.setBackground(QColor(tokens.WARN_ROW))
            item.setForeground(QColor(tokens.WARN_TEXT))
        return item

