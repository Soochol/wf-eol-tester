from __future__ import annotations

from . import tokens as t


def stylesheet() -> str:
    mono = t.font_stack(t.MONO_FAMILIES)
    return f"""
* {{ font-family: {t.font_stack(t.SANS_FAMILIES)}; color: {t.TEXT}; font-size: 13px; }}
QMainWindow, QWidget#root, QStackedWidget {{ background: {t.BACKGROUND}; }}
QLabel {{ background: transparent; }}
QFrame[card="true"] {{ background: {t.CARD}; border: 1px solid {t.BORDER}; border-radius: 14px; }}
QLabel[role="muted"] {{ color: {t.TEXT_MUTED}; }}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="caption"] {{ color: {t.CAPTION}; font-size: 12px; font-weight: 600; }}
QLabel[role="mono"], QLabel[role="tile-value"] {{ font-family: {mono}; }}
QLabel[role="tile-value"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="percent"] {{ font-family: {mono}; font-size: 28px; font-weight: 600; }}
QLabel[role="banner-title"] {{ font-size: 34px; font-weight: 700; }}
QLabel[role="notice"] {{ color: {t.FAIL}; }}
QLabel[chip="true"] {{ background: {t.CHIP_GRAY}; border-radius: 10px; padding: 2px 10px; }}
QLabel[badge] {{ border-radius: 999px; padding: 3px 10px; font-size: 12px; font-weight: 700; }}
QLabel[badge="MOCK"] {{ background: {t.ACCENT}; color: white; }}
QLabel[badge="PASS"] {{ background: {t.PASS_BADGE}; color: {t.PASS_TEXT}; }}
QLabel[badge="FAIL"] {{ background: {t.FAIL}; color: white; }}
QLabel[badge="RUNNING"], QLabel[badge="JUDGING"] {{ background: {t.ACCENT_SOFT}; color: {t.ACCENT}; }}
QLabel[badge="PENDING"], QLabel[badge="WAITING"] {{ background: {t.CHIP_GRAY}; color: {t.TEXT_SECONDARY}; }}
QLabel[stage="pending"] {{ color: {t.UNKNOWN}; }}
QLabel[stage="running"] {{ color: {t.ACCENT}; font-weight: 600; }}
QLabel[stage="done"] {{ color: {t.PASS_TEXT}; font-weight: 600; }}
QLabel[stage="failed"] {{ color: {t.FAIL}; font-weight: 600; }}
QFrame[banner="PASS"] {{ background: {t.PASS}; border-radius: 12px; }}
QFrame[banner="FAIL"], QFrame[banner="ERROR"] {{ background: {t.FAIL}; border-radius: 12px; }}
QFrame[banner="ABORTED"] {{ background: {t.NEUTRAL}; border-radius: 12px; }}
QLabel[role="banner-title"], QLabel[role="banner-text"] {{ color: white; }}
QLineEdit, QComboBox {{ background: white; border: 1px solid {t.INPUT_BORDER}; border-radius: 8px; padding: 5px 8px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {t.ACCENT}; }}
QLineEdit[size="lg"], QComboBox[size="lg"] {{ min-height: 44px; max-height: 44px; border-radius: 10px;
  padding: 0 12px; font-family: {mono}; font-size: 15px; }}
QPushButton {{ background: white; border: 1px solid {t.INPUT_BORDER}; border-radius: 10px; padding: 6px 16px;
  color: {t.TEXT_STRONG}; font-weight: 600; }}
QPushButton:hover {{ background: {t.ACCENT_FAINT}; }}
QPushButton:disabled {{ color: {t.UNKNOWN}; background: {t.CHIP_GRAY}; border-color: {t.CHIP_GRAY_BORDER}; }}
QPushButton[primary="true"] {{ background: {t.ACCENT}; border: none; border-radius: 12px; color: white;
  font-size: 15px; font-weight: 700; min-height: 48px; max-height: 48px; padding: 0 24px; }}
QPushButton[primary="true"]:hover {{ background: {t.ACCENT_HOVER}; }}
QPushButton[primary="true"]:disabled {{ background: {t.ACCENT_DISABLED}; color: white; }}
QPushButton[danger="true"] {{ background: white; border: 1.5px solid {t.FAIL}; border-radius: 12px; color: {t.FAIL};
  font-size: 15px; font-weight: 700; min-height: 48px; max-height: 48px; padding: 0 24px; }}
QPushButton[danger="true"]:hover {{ background: {t.FAIL_FAINT}; }}
QPushButton[danger="true"]:disabled {{ background: white; border-color: {t.CHIP_GRAY_BORDER}; color: {t.TEXT_FAINT}; }}
QFrame[segmented="true"] {{ background: {t.CHIP_GRAY}; border: none; border-radius: 12px; }}
QPushButton[segment="true"] {{ background: transparent; border: none; border-radius: 9px; padding: 7px 18px;
  color: {t.TEXT_SECONDARY}; font-weight: 600; }}
QPushButton[segment="true"]:hover {{ color: {t.TEXT}; }}
QPushButton[segment="true"]:checked {{ background: white; color: {t.TEXT}; }}
QPushButton[segment="true"][compact="true"] {{ padding: 4px 12px; font-size: 12px; border-radius: 8px; }}
QLabel[badge="CHANGED"] {{ background: {t.ACCENT}; color: white; border-radius: 8px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}
QLabel[role="hint"] {{ color: {t.TEXT_MUTED}; font-size: 12px; }}
QLabel[role="field-error"] {{ color: {t.FAIL}; font-size: 12px; }}
QLabel[role="counts"] {{ background: {t.WARN_ROW}; color: {t.WARN_TEXT}; border-radius: 10px; padding: 3px 10px; font-weight: 600; }}
QLineEdit[changed="true"] {{ border-color: {t.ACCENT}; }}
QLineEdit[error="true"], QWidget[error="true"] {{ border: 1px solid {t.FAIL}; border-radius: 8px; }}
QLineEdit:disabled {{ color: {t.UNKNOWN}; background: {t.CHIP_GRAY}; }}
QPushButton[side="true"] {{ text-align: left; border: none; background: transparent; padding: 10px 14px; min-width: 130px; }}
QPushButton[side="true"]:checked {{ background: {t.ACCENT_SOFT}; color: {t.ACCENT}; font-weight: 600; }}
QPushButton[switch="true"]:checked {{ background: {t.ACCENT}; color: white; border-color: {t.ACCENT}; }}
QPushButton[chip-remove="true"] {{ padding: 0 6px; border-radius: 9px; min-width: 18px; }}
QProgressBar {{ background: {t.DIVIDER}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {t.ACCENT}; border-radius: 3px; }}
QProgressBar[range="PASS"]::chunk {{ background: {t.PASS}; }}
QProgressBar[range="FAIL"]::chunk {{ background: {t.FAIL}; }}
QProgressBar[thick="true"] {{ border-radius: 6px; max-height: 12px; min-height: 12px; }}
QProgressBar[thick="true"]::chunk {{ border-radius: 6px; }}
QPlainTextEdit#log, QListWidget#log {{ background: {t.LOG_BACKGROUND}; color: {t.LOG_TEXT}; border-radius: 10px;
  font-family: {mono}; font-size: 12px; padding: 6px; border: none; }}
QTableWidget {{ background: white; border: none; gridline-color: {t.DIVIDER}; }}
QHeaderView::section {{ background: {t.BACKGROUND}; border: none; padding: 6px; color: {t.TEXT_MUTED}; }}
QFrame#header {{ background: {t.CARD}; border: none; border-bottom: 1px solid {t.BORDER}; }}
QLabel#app-title {{ font-size: 16px; font-weight: 700; }}
QLabel#sequence-identity {{ font-family: {mono}; font-size: 11px; color: {t.TEXT_MUTED}; }}
QLabel#logo {{ background: transparent; }}
QFrame[device-chip="true"] {{ border-radius: 15px; border-width: 1px; border-style: solid; }}
QFrame[device-chip="true"] QLabel {{ background: transparent; font-size: 12px; font-weight: 600; }}
"""
