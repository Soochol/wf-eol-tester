from __future__ import annotations

BACKGROUND = "#F3F4F6"
CARD = "#FFFFFF"
BORDER = "#E2E5EA"
TEXT = "#1F2937"
TEXT_MUTED = "#6B7280"
ACCENT = "#2B59C3"
PASS = "#0F7B5F"
FAIL = "#C2410C"
NEUTRAL = "#6B7280"
UNKNOWN = "#9CA3AF"
WARN_ROW = "#FFF4E5"
ERROR_ROW = "#FDECEA"
WARN_TEXT = "#92400E"
ACCENT_DISABLED = "#A9B8DD"
LOG_BACKGROUND = "#111827"
LOG_TEXT = "#E5E7EB"

SANS_FAMILIES = ("IBM Plex Sans KR", "Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "sans-serif")
MONO_FAMILIES = ("IBM Plex Mono", "DejaVu Sans Mono", "Consolas", "monospace")


def font_stack(families: tuple[str, ...]) -> str:
    return ", ".join(f'"{name}"' if " " in name else name for name in families)
