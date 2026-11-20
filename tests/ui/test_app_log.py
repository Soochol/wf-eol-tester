from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

import pytest

from eol_ui.app_log import prepare_streams


def test_no_console_goes_to_dated_utf8_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    path = prepare_streams(tmp_path, datetime(2026, 11, 20, 10, 14, 3))
    assert path == tmp_path / "eol_ui_20261120_101403.log"
    sys.stdout.write("✅ Temperature verified 52.0°C\n")
    sys.stdout.flush()
    assert sys.stderr is sys.stdout
    assert "✅ Temperature verified 52.0°C" in path.read_text(encoding="utf-8")
    sys.stdout.close()


def test_each_launch_gets_its_own_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = []
    for second in (1, 2):
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)
        paths.append(prepare_streams(tmp_path, datetime(2026, 11, 20, 10, 0, second)))
        sys.stdout.close()
    assert len(set(paths)) == 2


def test_cp949_console_switches_to_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp949")
    monkeypatch.setattr(sys, "stdout", console)
    monkeypatch.setattr(sys, "stderr", console)
    assert prepare_streams() is None
    console.write("✅ ok\n")
    console.flush()
    assert raw.getvalue().decode("utf-8") == "✅ ok\n"
