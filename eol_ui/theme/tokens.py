from __future__ import annotations

BACKGROUND = "#EEF0F4"
CARD = "#FFFFFF"
BORDER = "#E3E6EC"
DIVIDER = "#EAECF0"
DIVIDER_SOFT = "#F2F4F7"
INPUT_BORDER = "#D0D5DD"
TEXT = "#111827"
TEXT_MUTED = "#667085"
TEXT_SECONDARY = "#475467"
TEXT_STRONG = "#344054"
CAPTION = "#5B6472"
TEXT_FAINT = "#98A2B3"

ACCENT = "#2B59C3"
ACCENT_HOVER = "#1E428F"
ACCENT_DISABLED = "#B2C3EC"
ACCENT_SOFT = "#EEF4FF"
ACCENT_FAINT = "#F5F8FF"

PASS = "#12B76A"
PASS_TEXT = "#067647"
PASS_STRONG = "#079455"
PASS_SOFT = "#ECFDF3"
PASS_BADGE = "#DCFAE6"
PASS_RING = "#D1FADF"
PASS_BORDER = "#ABEFC6"

FAIL = "#D92D20"
FAIL_TEXT = "#B42318"
FAIL_SOFT = "#FEF3F2"
FAIL_FAINT = "#FFF6F5"
FAIL_BORDER = "#FECDCA"
FAIL_RING = "#FEE4E2"
FAIL_DOT = "#F04438"

CHIP_GRAY = "#F2F4F7"
CHIP_GRAY_BORDER = "#E4E7EC"

NEUTRAL = TEXT_MUTED
UNKNOWN = TEXT_FAINT
WARN_ROW = "#FFF4E5"
ERROR_ROW = "#FDECEA"
WARN_TEXT = "#92400E"

LOG_BACKGROUND = "#0F172A"
LOG_TEXT = "#E2E8F0"
LOG_TIME = "#64748B"
LOG_EMPTY = "#94A3B8"

SANS_FAMILIES = ("IBM Plex Sans KR", "Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "sans-serif")
MONO_FAMILIES = ("IBM Plex Mono", "DejaVu Sans Mono", "Consolas", "monospace")

DEVICE_CHIP_COLORS = {
    True: {"bg": PASS_SOFT, "border": PASS_BORDER, "text": PASS_TEXT, "dot": PASS, "ring": PASS_RING},
    None: {"bg": CHIP_GRAY, "border": CHIP_GRAY_BORDER, "text": TEXT_SECONDARY, "dot": TEXT_FAINT, "ring": DIVIDER},
    False: {"bg": FAIL_SOFT, "border": FAIL_BORDER, "text": FAIL_TEXT, "dot": FAIL_DOT, "ring": FAIL_RING},
}


def font_stack(families: tuple[str, ...]) -> str:
    return ", ".join(f'"{name}"' if " " in name else name for name in families)
