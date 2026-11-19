from __future__ import annotations

from . import tokens as t


def stylesheet() -> str:
    return f"""
* {{ font-family: {t.font_stack(t.SANS_FAMILIES)}; color: {t.TEXT}; font-size: 13px; }}
QMainWindow, QWidget#root, QStackedWidget {{ background: {t.BACKGROUND}; }}
QLabel {{ background: transparent; }}
QFrame[card="true"] {{ background: {t.CARD}; border: 1px solid {t.BORDER}; border-radius: 10px; }}
QLabel[role="muted"] {{ color: {t.TEXT_MUTED}; }}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="mono"], QLabel[role="tile-value"] {{ font-family: {t.font_stack(t.MONO_FAMILIES)}; }}
QLabel[role="tile-value"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="percent"] {{ font-family: {t.font_stack(t.MONO_FAMILIES)}; font-size: 28px; font-weight: 600; }}
QLabel[role="banner-title"] {{ font-size: 34px; font-weight: 700; }}
QLabel[role="notice"] {{ color: {t.FAIL}; }}
QLabel[chip="true"] {{ background: {t.BACKGROUND}; border-radius: 10px; padding: 2px 10px; }}
QLabel[badge="MOCK"] {{ background: {t.ACCENT}; color: white; border-radius: 9px; padding: 2px 10px; font-weight: 600; }}
QLabel[badge="PASS"] {{ background: {t.PASS}; color: white; border-radius: 9px; padding: 2px 10px; font-weight: 600; }}
QLabel[badge="FAIL"] {{ background: {t.FAIL}; color: white; border-radius: 9px; padding: 2px 10px; font-weight: 600; }}
QLabel[badge="PENDING"] {{ background: {t.BORDER}; color: {t.TEXT_MUTED}; border-radius: 9px; padding: 2px 10px; }}
QLabel[stage="pending"] {{ color: {t.UNKNOWN}; }}
QLabel[stage="running"] {{ color: {t.ACCENT}; font-weight: 600; }}
QLabel[stage="done"] {{ color: {t.PASS}; font-weight: 600; }}
QLabel[stage="failed"] {{ color: {t.FAIL}; font-weight: 600; }}
QFrame[banner="PASS"] {{ background: {t.PASS}; border-radius: 12px; }}
QFrame[banner="FAIL"], QFrame[banner="ERROR"] {{ background: {t.FAIL}; border-radius: 12px; }}
QFrame[banner="ABORTED"] {{ background: {t.NEUTRAL}; border-radius: 12px; }}
QLabel[role="banner-title"], QLabel[role="banner-text"] {{ color: white; }}
QLineEdit, QComboBox {{ background: white; border: 1px solid {t.BORDER}; border-radius: 6px; padding: 5px 8px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {t.ACCENT}; }}
QPushButton {{ background: white; border: 1px solid {t.BORDER}; border-radius: 6px; padding: 6px 16px; }}
QPushButton:disabled {{ color: {t.UNKNOWN}; background: {t.BACKGROUND}; }}
QPushButton[primary="true"] {{ background: {t.ACCENT}; border-color: {t.ACCENT}; color: white; font-weight: 600; }}
QPushButton[primary="true"]:disabled {{ background: {t.ACCENT_DISABLED}; border-color: {t.ACCENT_DISABLED}; color: white; }}
QPushButton[danger="true"] {{ color: {t.FAIL}; border-color: {t.FAIL}; }}
QPushButton[danger="true"]:disabled {{ color: {t.UNKNOWN}; border-color: {t.BORDER}; }}
QPushButton[tab="true"] {{ border: none; border-radius: 0; background: transparent; padding: 8px 16px; }}
QPushButton[tab="true"]:checked {{ color: {t.ACCENT}; border-bottom: 2px solid {t.ACCENT}; font-weight: 600; }}
QLabel[badge="CHANGED"] {{ background: {t.ACCENT}; color: white; border-radius: 8px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}
QLabel[role="hint"] {{ color: {t.TEXT_MUTED}; font-size: 12px; }}
QLabel[role="field-error"] {{ color: {t.FAIL}; font-size: 12px; }}
QLabel[role="counts"] {{ background: {t.WARN_ROW}; color: {t.WARN_TEXT}; border-radius: 10px; padding: 3px 10px; font-weight: 600; }}
QLineEdit[changed="true"] {{ border-color: {t.ACCENT}; }}
QLineEdit[error="true"], QWidget[error="true"] {{ border: 1px solid {t.FAIL}; border-radius: 6px; }}
QLineEdit:disabled {{ color: {t.UNKNOWN}; background: {t.BACKGROUND}; }}
QPushButton[side="true"] {{ text-align: left; border: none; background: transparent; padding: 10px 14px; min-width: 130px; }}
QPushButton[side="true"]:checked {{ background: {t.ACCENT_SOFT}; color: {t.ACCENT}; font-weight: 600; }}
QPushButton[switch="true"]:checked {{ background: {t.ACCENT}; color: white; border-color: {t.ACCENT}; }}
QPushButton[chip-remove="true"] {{ padding: 0 6px; border-radius: 9px; min-width: 18px; }}
QProgressBar {{ background: {t.BORDER}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {t.ACCENT}; border-radius: 4px; }}
QProgressBar[range="PASS"]::chunk {{ background: {t.PASS}; }}
QProgressBar[range="FAIL"]::chunk {{ background: {t.FAIL}; }}
QPlainTextEdit#log, QListWidget#log {{ background: {t.LOG_BACKGROUND}; color: {t.LOG_TEXT}; border-radius: 8px;
  font-family: {t.font_stack(t.MONO_FAMILIES)}; font-size: 12px; padding: 6px; border: none; }}
QTableWidget {{ background: white; border: none; gridline-color: {t.BORDER}; }}
QHeaderView::section {{ background: {t.BACKGROUND}; border: none; padding: 6px; color: {t.TEXT_MUTED}; }}
QFrame#header {{ background: {t.CARD}; border-bottom: 1px solid {t.BORDER}; }}
"""
