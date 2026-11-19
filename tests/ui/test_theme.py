from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QLabel

from eol_ui.main_window import MainWindow
from eol_ui.theme import fonts, register_fonts, stylesheet
from eol_ui.widgets.icons import ICON_NAMES, icon_pixmap

FONTS_DIR = Path(fonts.__file__).parent / "fonts"


def test_register_fonts_twice_and_families(qtbot):
    register_fonts()
    register_fonts()
    families = QFontDatabase.families()
    assert "IBM Plex Sans KR" in families
    assert "IBM Plex Mono" in families


def test_font_files_bundled():
    assert len(list(FONTS_DIR.glob("*.ttf"))) == 7
    assert (FONTS_DIR / "OFL-IBMPlexSansKR.txt").is_file()
    assert (FONTS_DIR / "OFL-IBMPlexMono.txt").is_file()


def test_register_fonts_missing_dir_is_harmless(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(fonts, "_registered", False)
    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path / "nope")
    assert fonts.register_fonts() == []


def test_semibold_label_uses_plex(qtbot):
    register_fonts()
    QApplication.instance().setStyleSheet(stylesheet())
    label = QLabel("측정 Abc")
    qtbot.addWidget(label)
    font = QFont(label.font())
    font.setWeight(QFont.Weight.DemiBold)
    label.setFont(font)
    label.show()
    assert QFontInfo(label.font()).family().startswith("IBM Plex Sans KR")


@pytest.mark.parametrize("name", ICON_NAMES)
def test_icons_render(qtbot, name):
    pixmap = icon_pixmap(name, 24)
    assert not pixmap.isNull()


@pytest.mark.usefixtures("mock_hardware")
def test_header_device_chips(qtbot):
    QApplication.instance().setStyleSheet(stylesheet())
    window = MainWindow()
    qtbot.addWidget(window)
    window._paint_devices({"robot": True, "mcu": False})
    assert window.device_connected("robot") is True
    assert window.device_connected("mcu") is False
    assert window.device_connected("power") is None
    sheets = {window._device_dots[k].styleSheet() for k in ("robot", "mcu", "power")}
    assert len(sheets) == 3
