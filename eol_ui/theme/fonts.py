from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtGui import QFontDatabase

FONTS_DIR = Path(__file__).parent / "fonts"
_registered = False


def register_fonts() -> List[str]:
    """Register the bundled IBM Plex fonts once; fall back to system fonts on any failure."""
    global _registered
    if _registered:
        return []
    _registered = True
    families: List[str] = []
    try:
        files = sorted(FONTS_DIR.glob("*.ttf"))
    except OSError:
        return families
    for path in files:
        try:
            font_id = QFontDatabase.addApplicationFont(str(path))
        except Exception:
            continue
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families
