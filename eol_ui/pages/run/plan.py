from __future__ import annotations

from typing import Any, Mapping, NamedTuple, Optional

import eol_tester.config as eol_config


class MeasurementPlan(NamedTuple):
    temperatures: int
    positions: int
    repeats: int

    @property
    def total(self) -> int:
        return self.temperatures * self.positions * self.repeats


def _count_list(value: Any) -> Optional[int]:
    """Count list entries the way the sequence reads `temperature_list` / `stroke_positions`."""
    if isinstance(value, str):
        return len([float(part.strip()) for part in value.split(",")])
    if isinstance(value, (list, tuple)):
        return len(value)
    return None


def _positive(count: Optional[int]) -> Optional[int]:
    return count if count is not None and count > 0 else None


def plan_measurements(profile_name: str, overrides: Mapping[str, Any]) -> Optional[MeasurementPlan]:
    """Expected matrix for the selected profile with applied parameters on top; None if it cannot be computed."""
    if not profile_name or not (eol_config.TEST_PROFILES_DIR / f"{profile_name}.yaml").is_file():
        return None
    try:
        profile = eol_config.load_test_profile(profile_name)
        parameters = profile.get("test_parameters") or {}
        execution = profile.get("execution") or {}
        temperatures = overrides.get("temperature_list", parameters.get("temperature_list"))
        positions = overrides.get("stroke_positions", parameters.get("stroke_positions"))
        repeats = overrides.get("repeat_count", execution.get("repeat_count", 1))
        counts = (_positive(_count_list(temperatures)), _positive(_count_list(positions)), int(repeats))
    except (ValueError, TypeError, AttributeError, OSError):
        return None
    if counts[0] is None or counts[1] is None or counts[2] < 1:
        return None
    return MeasurementPlan(counts[0], counts[1], counts[2])
