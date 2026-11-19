from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from eol_ui.theme import register_fonts, stylesheet, tokens
from eol_ui.widgets import Badge

KINDS = {
    "PASS": tokens.PASS_BADGE,
    "FAIL": tokens.FAIL,
    "PENDING": tokens.CHIP_GRAY,
    "RUNNING": tokens.ACCENT_SOFT,
    "MOCK": tokens.ACCENT,
    "CHANGED": tokens.ACCENT,
}


@pytest.mark.parametrize("kind", KINDS)
def test_badge_is_pill(qtbot, kind):
    register_fonts()
    QApplication.instance().setStyleSheet(stylesheet())
    host = QWidget()
    host.setObjectName("host")
    host.setStyleSheet("QWidget#host { background: white; }")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    badge = Badge(kind, kind)
    layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    image = host.grab().toImage()
    left, top, right, bottom = badge.x(), badge.y(), badge.x() + badge.width() - 1, badge.y() + badge.height() - 1
    fill = image.pixelColor((left + right) // 2, top + 2).name().upper()
    assert fill == KINDS[kind].upper()
    for corner in ((left, top), (right, top), (left, bottom), (right, bottom)):
        assert image.pixelColor(*corner).name().upper() != fill
    assert badge.height() in (tokens.BADGE_HEIGHT, tokens.BADGE_COMPACT_HEIGHT)


def test_badge_radius_is_half_height():
    sheet = stylesheet()
    assert f"border-radius: {tokens.BADGE_HEIGHT // 2}px" in sheet.split("QLabel[badge] {")[1].split("}")[0]
    changed = sheet.split('QLabel[badge="CHANGED"] {')[1].split("}")[0]
    assert f"border-radius: {tokens.BADGE_COMPACT_HEIGHT // 2}px" in changed
