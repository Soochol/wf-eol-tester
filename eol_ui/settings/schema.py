from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple, cast

import yaml

import eol_tester.config as eol_config

Kind = Literal["float", "int", "bool", "float_list"]

MANIFEST_FILE = Path(eol_config.CONFIG_DIR).parent / "manifest.yaml"

_KIND_BY_MANIFEST_TYPE = {"float": "float", "integer": "int", "boolean": "bool"}
_LIST_PARAMETERS = ("temperature_list", "stroke_positions")

STROKE_MIN = 0.0
STROKE_MAX = 180000.0

PROFILE_LOCATION: dict[str, Optional[Tuple[str, str]]] = {
    "voltage": ("hardware", "voltage"),
    "current": ("hardware", "current"),
    "standby_temperature": ("hardware", "standby_temperature"),
    "activation_temperature": ("hardware", "activation_temperature"),
    "initial_position": ("hardware", "initial_position"),
    "operating_position": ("hardware", "operating_position"),
    "velocity": ("motion_control", "velocity"),
    "acceleration": ("motion_control", "acceleration"),
    "temperature_list": ("test_parameters", "temperature_list"),
    "stroke_positions": ("test_parameters", "stroke_positions"),
    "repeat_count": ("execution", "repeat_count"),
    "timeout_seconds": ("execution", "timeout_seconds"),
    "force_limit_min": ("pass_criteria", "force_limit_min"),
    "force_limit_max": ("pass_criteria", "force_limit_max"),
    "stop_on_failure": None,
}


@dataclass(frozen=True)
class ParamSpec:
    name: str
    display_name: str
    kind: Kind
    unit: Optional[str]
    min: Optional[float]
    max: Optional[float]
    default: object
    description: str


def _parse_default_list(text: str) -> list[float]:
    return [float(part) for part in text.split(",") if part.strip()]


def load_schema() -> dict[str, ParamSpec]:
    manifest = yaml.safe_load(MANIFEST_FILE.read_text(encoding="utf-8"))
    schema: dict[str, ParamSpec] = {}
    for name, entry in manifest["parameters"].items():
        if name in _LIST_PARAMETERS:
            kind: Kind = "float_list"
            default: object = _parse_default_list(entry["default"])
            low: Optional[float] = None
            high: Optional[float] = None
            if name == "stroke_positions":
                low, high = STROKE_MIN, STROKE_MAX
        else:
            kind = cast(Kind, _KIND_BY_MANIFEST_TYPE[entry["type"]])
            default = entry["default"]
            low, high = entry.get("min"), entry.get("max")
        schema[name] = ParamSpec(
            name=name,
            display_name=entry["display_name"],
            kind=kind,
            unit=entry.get("unit"),
            min=low,
            max=high,
            default=default,
            description=entry.get("description", ""),
        )
    return schema
