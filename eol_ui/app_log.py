from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "WF EOL Tester" / "logs"


def prepare_streams(directory: Optional[Path] = None, now: Optional[datetime] = None) -> Optional[Path]:
    """Make stdout/stderr safe before eol_tester binds its loguru sink to sys.stdout.

    Without a console (pythonw) both streams are None, so they go to a new dated
    UTF-8 log file instead of crashing. With a console they are switched to UTF-8
    so emoji in log lines no longer fail on cp949 consoles or redirects.
    """
    if sys.stdout is None or sys.stderr is None:
        target_dir = directory or log_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"eol_ui_{(now or datetime.now()):%Y%m%d_%H%M%S}.log"
        stream: TextIO = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
        return path
    for current in (sys.stdout, sys.stderr):
        encoding = (getattr(current, "encoding", None) or "").lower().replace("-", "")
        reconfigure = getattr(current, "reconfigure", None)
        if encoding != "utf8" and reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    return None
