from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger

import eol_tester.config as eol_config
from eol_tester.domain.value_objects import HardwareConfig
from eol_tester.hardware_adapter import create_standalone_hardware_adapter

DEVICES = ("robot", "loadcell", "mcu", "power", "digital_io")

EDITABLE: dict[str, dict[str, type]] = {
    "robot": {"axis_id": int, "irq_no": int},
    "loadcell": {"port": str, "baudrate": int},
    "mcu": {"port": str, "baudrate": int},
    "power": {"host": str, "port": int},
    "digital_io": {"input_module_no": int, "output_module_no": int},
}

REAL_MODELS = {
    "robot": "ajinextek",
    "loadcell": "bs205",
    "mcu": "lma",
    "power": "oda",
    "digital_io": "ajinextek",
}

MOCK_BACKUP_KEY = "ui_real_models"

ConnectionResult = dict[str, tuple[bool, Optional[str]]]


def _coerce(kind: type, raw: Any) -> Any:
    if kind is str:
        text = str(raw).strip()
        if not text:
            raise ValueError("비어 있을 수 없다")
        return text
    if isinstance(raw, bool):
        raise ValueError("정수가 아니다")
    try:
        number = float(raw)
    except (TypeError, ValueError):
        raise ValueError("정수가 아니다") from None
    if number != int(number) or number < 0:
        raise ValueError("0 이상의 정수여야 한다")
    return int(number)


class HardwareStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.load()

    @staticmethod
    def path() -> Path:
        return eol_config.get_config_path()

    def load(self) -> None:
        self._data = yaml.safe_load(self.path().read_text(encoding="utf-8")) or {}

    def model(self, device: str) -> str:
        return self._data[device]["model"]

    def get(self, device: str, key: str) -> Any:
        return self._data[device][key]

    def set_value(self, device: str, key: str, raw: Any) -> None:
        kind = EDITABLE[device][key]
        self._data[device][key] = _coerce(kind, raw)

    def is_mock(self) -> bool:
        return HardwareConfig.from_dict(self._data).is_mock_mode()

    def set_mock(self, enabled: bool) -> None:
        if enabled:
            backup = dict(self._data.get(MOCK_BACKUP_KEY) or {})
            for device in DEVICES:
                current = self._data[device]["model"]
                if current != "mock":
                    backup[device] = current
                self._data[device]["model"] = "mock"
            self._data[MOCK_BACKUP_KEY] = backup
        else:
            backup = self._data.get(MOCK_BACKUP_KEY) or {}
            for device in DEVICES:
                self._data[device]["model"] = backup.get(device, REAL_MODELS[device])
            self._data.pop(MOCK_BACKUP_KEY, None)

    def save(self) -> None:
        self.path().write_text(
            yaml.safe_dump(self._data, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    async def connection_test(self) -> ConnectionResult:
        adapter = None
        connect_error: Optional[str] = None
        try:
            adapter = create_standalone_hardware_adapter(
                hardware_config=eol_config.load_hardware_config()
            )
            try:
                await adapter.connect()
            except Exception as error:
                connect_error = str(error) or type(error).__name__
            status = await adapter.get_hardware_status()
        except Exception as error:
            message = str(error) or type(error).__name__
            return {device: (False, message) for device in DEVICES}
        finally:
            if adapter is not None:
                try:
                    await adapter.disconnect()
                except Exception as error:
                    logger.warning(f"connection_test disconnect failed: {error}")
        return {
            device: (True, None)
            if status.get(device)
            else (False, connect_error or "연결되지 않았다")
            for device in DEVICES
        }
