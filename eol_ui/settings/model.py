from __future__ import annotations

import copy
import math
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Optional

import yaml
from loguru import logger
from station_service_sdk import ExecutionContext

import eol_tester.config as eol_config
from eol_tester.domain.exceptions import ConfigurationValidationError
from eol_tester.domain.value_objects import TestConfiguration
from eol_tester.sequence import EOLForceTestSequence
from eol_tester.services.configuration_validator import ConfigurationValidator
from eol_ui.settings.schema import PROFILE_LOCATION, PROFILE_ONLY_PARAMETERS, ParamSpec, load_schema

Value = Any


class ProfileExistsError(Exception):
    pass


def _parse_float(raw: Any) -> float:
    if isinstance(raw, bool):
        raise ValueError("숫자가 아니다")
    try:
        value = float(raw.strip() if isinstance(raw, str) else raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("숫자가 아니다") from None
    if not math.isfinite(value):
        raise ValueError("숫자가 아니다")
    return value


def _parse_int(raw: Any) -> int:
    value = _parse_float(raw)
    if value != int(value):
        raise ValueError("정수가 아니다")
    return int(value)


def _parse_list(raw: Any) -> list[float]:
    items = raw.split(",") if isinstance(raw, str) else raw
    try:
        items = list(items)
    except TypeError:
        raise ValueError("목록이 아니다") from None
    if isinstance(raw, str):
        items = [item for item in items if item.strip()]
    if not items:
        raise ValueError("비어 있을 수 없다")
    return [_parse_float(item) for item in items]


def _parse_bool(raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise ValueError("참/거짓이 아니다")
    return raw


_PARSERS = {"float": _parse_float, "int": _parse_int, "bool": _parse_bool, "float_list": _parse_list}


def _range_error(spec: ParamSpec, value: float) -> Optional[str]:
    if spec.min is not None and value < spec.min:
        return f"{spec.min:g} 이상이어야 한다"
    if spec.max is not None and value > spec.max:
        return f"{spec.max:g} 이하여야 한다"
    return None


_VALIDATOR_LOGGER = "eol_tester.services.configuration_validator"
_FORCE_LIMITS = ("force_limit_min", "force_limit_max")


class _SilentOutput:
    pass


def _without_nulls(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    return {key: _without_nulls(value) for key, value in node.items() if value is not None}


def _finish(coroutine: Awaitable[None]) -> None:
    try:
        coroutine.send(None)  # type: ignore[attr-defined]
    except StopIteration:
        return
    coroutine.close()  # type: ignore[attr-defined]
    raise RuntimeError("검증기가 비동기 대기를 요구한다")


class SettingsModel:
    def __init__(self) -> None:
        self.schema: dict[str, ParamSpec] = load_schema()
        self._profile_name = ""
        self._profile: dict[str, Any] = {}
        self._baseline: dict[str, Value] = {}
        self._raw: dict[str, Any] = {}
        self._rules: Optional[list[str]] = None

    @property
    def profile_name(self) -> str:
        return self._profile_name

    @staticmethod
    def profile_names() -> list[str]:
        return eol_config.list_test_profiles()

    def load(self, profile_name: str) -> None:
        self._profile = copy.deepcopy(eol_config.load_test_profile(profile_name))
        self._profile_name = profile_name
        self._baseline = {name: self._read_baseline(spec) for name, spec in self.schema.items()}
        self._raw = {}
        self._rules = None

    def _read_baseline(self, spec: ParamSpec) -> Value:
        location = PROFILE_LOCATION[spec.name]
        value = spec.default
        if location is not None:
            section, key = location
            found = (self._profile.get(section) or {}).get(key)
            value = spec.default if found is None else found
            if spec.kind == "bool" and not isinstance(value, bool):
                value = spec.default
        return _PARSERS[spec.kind](value)

    def baseline(self, name: str) -> Value:
        return self._baseline[name]

    def set_value(self, name: str, raw: Any) -> None:
        if name not in self.schema:
            raise KeyError(name)
        self._raw[name] = raw
        self._rules = None

    def value(self, name: str) -> Any:
        return self._raw.get(name, self._baseline[name])

    def _parsed(self, name: str) -> tuple[Optional[Value], Optional[str]]:
        spec = self.schema[name]
        try:
            parsed = _PARSERS[spec.kind](self.value(name))
        except ValueError as error:
            return None, str(error)
        values = parsed if spec.kind == "float_list" else [parsed]
        if spec.kind != "bool":
            for item in values:
                message = _range_error(spec, item)
                if message:
                    return None, message
        return parsed, None

    def error(self, name: str) -> Optional[str]:
        parsed, message = self._parsed(name)
        if message:
            return message
        if name == "force_limit_max":
            low, _ = self._parsed("force_limit_min")
            if low is not None and parsed < low:
                return "force_limit_min보다 작을 수 없다"
        return None

    def errors(self) -> dict[str, str]:
        found = {}
        for name in self.schema:
            message = self.error(name)
            if message:
                found[name] = message
        return found

    def rule_errors(self) -> list[str]:
        if self._rules is None:
            self._rules = self._check_rules() if not self.errors() else []
        return list(self._rules)

    def error_count(self) -> int:
        return len(self.errors()) + len(self.rule_errors())

    def _run_parameters(self, names: list[str]) -> dict[str, Any]:
        parameters: dict[str, Any] = {"test_profile": self._profile_name}
        parameters.update(self.carried_parameters())
        for name in names:
            parameters[name] = self._parsed(name)[0]
        return parameters

    def _check_rules(self) -> list[str]:
        logger.disable(_VALIDATOR_LOGGER)
        try:
            _finish(ConfigurationValidator().validate_test_configuration(self._test_configuration()))
        except ConfigurationValidationError as error:
            return list(error.errors)
        except Exception as error:
            return [f"설정을 검증하지 못했다: {error}"]
        finally:
            logger.enable(_VALIDATOR_LOGGER)
        return []

    def _test_configuration(self) -> TestConfiguration:
        changed = self.changed_names()
        sequence = EOLForceTestSequence(
            ExecutionContext(serial_number="settings"),
            output_strategy=_SilentOutput(),  # type: ignore[arg-type]
            parameters=self._run_parameters(changed),
        )
        config = sequence._create_test_config_from_profile(_without_nulls(self._profile))
        overrides = sequence._collect_parameter_overrides()
        if overrides:
            config = config.with_overrides(**overrides)
        if any(name in changed for name in _FORCE_LIMITS):
            criteria = replace(
                config.pass_criteria,
                force_limit_min=self._parsed("force_limit_min")[0],
                force_limit_max=self._parsed("force_limit_max")[0],
            )
            config = config.with_overrides(pass_criteria=criteria)
        return config

    def carried_parameters(self) -> dict[str, Any]:
        return {
            name: self._baseline[name]
            for name in PROFILE_ONLY_PARAMETERS
            if self._baseline[name] != self.schema[name].default
        }

    def is_changed(self, name: str) -> bool:
        if name not in self._raw:
            return False
        parsed, message = self._parsed(name)
        return message is not None or parsed != self._baseline[name]

    def changed_names(self) -> list[str]:
        return [name for name in self.schema if self.is_changed(name)]

    def changed_count(self) -> int:
        return len(self.changed_names())

    def revert(self) -> None:
        self._raw = {}
        self._rules = None

    def to_parameters(self) -> dict[str, Any]:
        if self.error_count():
            raise ValueError(f"오류가 있어 변환할 수 없다: {self.errors()}")
        return self._run_parameters(self.changed_names())

    def save_as(self, name: str, overwrite: bool = False) -> Path:
        if not name or name != Path(name).name or name.startswith("."):
            raise ValueError(f"프로파일 이름이 올바르지 않다: {name!r}")
        if self.error_count():
            raise ValueError(f"오류가 있어 저장할 수 없다: {self.errors()}")
        path = eol_config.TEST_PROFILES_DIR / f"{name}.yaml"
        if path.exists() and not overwrite:
            raise ProfileExistsError(name)
        profile = copy.deepcopy(self._profile)
        for changed in self.changed_names():
            location = PROFILE_LOCATION[changed]
            if location is None:
                continue
            section, key = location
            profile[section] = profile.get(section) or {}
            profile[section][key] = self._parsed(changed)[0]
        metadata = profile["metadata"] = profile.get("metadata") or {}
        metadata["profile_name"] = name
        metadata["created_at"] = datetime.now().isoformat()
        metadata["created_by"] = "eol_ui"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        self.load(name)
        return path
