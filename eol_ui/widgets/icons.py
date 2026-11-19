from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from eol_ui.theme import tokens

_STROKE = 'stroke="{c}" fill="none" stroke-linecap="round" stroke-linejoin="round"'

# name -> (viewBox size, body template using {c} for color and {a} for the accent color)
_ICONS: Dict[str, Tuple[int, str]] = {
    "logo": (
        32,
        '<rect width="32" height="32" rx="9" fill="{c}"/>'
        '<path d="M9 21V11m0 5h6m0-5v10m4-10h5m-5 5h4m-4-5v10" stroke="#FFFFFF" stroke-width="2" '
        'fill="none" stroke-linecap="round"/>',
    ),
    "play": (16, '<path d="M2 1.5v13l12-6.5z" fill="{c}"/>'),
    "stop": (14, '<rect x="1" y="1" width="12" height="12" rx="2.5" fill="{c}"/>'),
    "check": (14, '<path d="M2.5 7.5l3 3 6-6.5" stroke-width="2" ' + _STROKE + "/>"),
    "x": (14, '<path d="M3 3l8 8M11 3l-8 8" stroke-width="2" ' + _STROKE + "/>"),
    "temp": (
        14,
        '<path d="M7 1.5v7M5 9.5a2 2 0 1 0 4 0 2 2 0 0 0-4 0M5 3h1M5 5h1" stroke-width="1.6" ' + _STROKE + "/>",
    ),
    "force": (14, '<path d="M2 7h10M9 4l3 3-3 3" stroke-width="1.6" ' + _STROKE + "/>"),
    "power": (14, '<path d="M7 1.5v5M4.2 3.6a4.5 4.5 0 1 0 5.6 0" stroke-width="1.6" ' + _STROKE + "/>"),
    "robot": (14, '<path d="M2 11h10M4 11V5h6v6M7 5V2" stroke-width="1.6" ' + _STROKE + "/>"),
    "log-empty": (24, '<path d="M4 6h16M4 12h10M4 18h7" stroke-width="2" ' + _STROKE + "/>"),
    "measure-empty": (
        40,
        '<rect x="6" y="8" width="28" height="24" rx="5" stroke-width="2" ' + _STROKE + "/>"
        '<path d="M12 16h16M12 22h10" stroke-width="2" ' + _STROKE + "/>",
    ),
    "spinner": (
        16,
        '<circle cx="8" cy="8" r="6.5" stroke="#D0D5DD" stroke-width="2" fill="none"/>'
        '<path d="M8 1.5a6.5 6.5 0 0 1 6.5 6.5" stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round"/>',
    ),
}

ICON_NAMES = tuple(_ICONS)
_DEFAULT_SIZES = {"logo": 32}
_cache: Dict[Tuple[str, int, str, float], QPixmap] = {}


def _svg(name: str, color: str) -> Tuple[bytes, int]:
    size, body = _ICONS[name]
    text = body.replace("{c}", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">{text}</svg>'.encode(),
        size,
    )


def icon_pixmap(
    name: str, size: Optional[int] = None, color: str = tokens.ACCENT, ratio: float = 2.0
) -> QPixmap:
    """Render the named icon at `size` logical px (default: its design size) in `color`."""
    if name not in _ICONS:
        raise KeyError(name)
    side = size or _DEFAULT_SIZES.get(name, _ICONS[name][0])
    key = (name, side, color, ratio)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    data, _ = _svg(name, color)
    renderer = QSvgRenderer(QByteArray(data))
    pixmap = QPixmap(int(side * ratio), int(side * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, side * ratio, side * ratio))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    _cache[key] = pixmap
    return pixmap


def icon(name: str, size: Optional[int] = None, color: str = tokens.ACCENT) -> QIcon:
    return QIcon(icon_pixmap(name, size, color))


__all__ = ["ICON_NAMES", "icon", "icon_pixmap"]
