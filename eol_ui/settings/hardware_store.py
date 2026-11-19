from __future__ import annotations

import asyncio
import math
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


def _describe(error: BaseException) -> str:
    return str(error) or type(error).__name__


def _all_failed(message: str) -> ConnectionResult:
    return {device: (False, message) for device in DEVICES}


def _coerce(kind: type, raw: Any) -> Any:
    if kind is str:
        if raw is None or isinstance(raw, bool):
            raise ValueError("문자열이 아니다")
        text = str(raw).strip()
        if not text:
            raise ValueError("비어 있을 수 없다")
        return text
    if isinstance(raw, bool):
        raise ValueError("정수가 아니다")
    try:
        number = float(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("정수가 아니다") from None
    if not math.isfinite(number) or number != int(number) or number < 0:
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
        try:
            self._read_saved_file()
            hardware_config = eol_config.load_hardware_config()
            adapter = create_standalone_hardware_adapter(hardware_config=hardware_config)
        except Exception as error:
            return _all_failed(_describe(error))
        try:
            return await self._connect_and_report(adapter)
        finally:
            try:
                await adapter.disconnect()
            except Exception as error:
                logger.warning(f"connection_test disconnect failed: {error}")

    def _read_saved_file(self) -> None:
        try:
            data = yaml.safe_load(self.path().read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(f"설정 파일을 읽지 못했다: {error}") from error
        if not isinstance(data, dict) or not data:
            raise ValueError("설정 파일이 비어 있거나 올바르지 않다")

    @staticmethod
    async def _connect_and_report(adapter: Any) -> ConnectionResult:
        facade = adapter._facade
        services = {
            "robot": facade.robot_service,
            "loadcell": facade.loadcell_service,
            "mcu": facade.mcu_service,
            "power": facade.power_service,
            "digital_io": facade.digital_io_service,
        }
        outcomes = await asyncio.gather(
            *(service.connect() for service in services.values()), return_exceptions=True
        )
        errors = {
            device: _describe(outcome)
            for device, outcome in zip(services, outcomes)
            if isinstance(outcome, BaseException)
        }
        try:
            status = await adapter.get_hardware_status()
        except Exception as error:
            return {device: (False, errors.get(device, _describe(error))) for device in DEVICES}
        return {
            device: (True, None)
            if status.get(device) and device not in errors
            else (False, errors.get(device, "연결되지 않았다"))
            for device in DEVICES
        }
