from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QScrollArea, QVBoxLayout, QWidget

from eol_ui.settings import ProfileExistsError, SettingsModel
from eol_ui.widgets import card, label

from .fields import BoolField, ListField, ParamField, format_value
from .profile_bar import ProfileBar

DISCARD_NOTICE = "프로파일을 바꿔서 편집 중이던 변경과 적용한 변경을 버렸습니다."

GROUPS: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
    ("전원", (("voltage", "전압"), ("current", "전류"))),
    ("판정 기준", (("force_limit_min", "Force 하한"), ("force_limit_max", "Force 상한"))),
    (
        "온도",
        (
            ("temperature_list", "측정 온도 목록"),
            ("standby_temperature", "대기 온도"),
            ("activation_temperature", "활성화 온도"),
        ),
    ),
    (
        "위치 · 모션",
        (
            ("stroke_positions", "스트로크 위치"),
            ("initial_position", "초기 위치"),
            ("operating_position", "최대 스트로크"),
            ("velocity", "속도"),
            ("acceleration", "가속도"),
        ),
    ),
    (
        "실행",
        (
            ("repeat_count", "반복 횟수"),
            ("timeout_seconds", "타임아웃"),
            ("stop_on_failure", "실패 시 즉시 중단"),
        ),
    ),
)


def _initial_profile(names: List[str]) -> str:
    if "default" in names or not names:
        return "default"
    return names[0]


class ParametersPanel(QWidget):
    applied = Signal(object, int)
    profile_changed = Signal(str)
    profiles_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.model = SettingsModel()
        self._applied_count = 0
        self._fields: Dict[str, ParamField] = {}

        self._guide = label("", "muted")
        self._guide.setObjectName("settings-guide")
        self._guide.setWordWrap(True)
        self._bar = ProfileBar()
        self._build_layout()

        self._bar.profile_selected.connect(self.select_profile)
        self._bar.revert_requested.connect(self.revert)
        self._bar.apply_requested.connect(self.apply)
        self._bar.save_requested.connect(self.save_profile)

        self.model.load(_initial_profile(self.model.profile_names()))
        self.refresh_profiles()
        self._reload_fields()

    def _build_layout(self) -> None:
        cards = QWidget()
        grid = QGridLayout(cards)
        grid.setContentsMargins(0, 0, 0, 0)
        for index, (title, members) in enumerate(GROUPS):
            panel = card()
            panel.setObjectName(f"group-{index}")
            column = QVBoxLayout(panel)
            column.addWidget(label(title, "title"))
            for name, text in members:
                field = self._make_field(name, text)
                field.edited.connect(self._on_edited)
                self._fields[name] = field
                column.addWidget(field)
            column.addStretch(1)
            grid.addWidget(panel, index // 2, index % 2)
        grid.setRowStretch(len(GROUPS) // 2 + 1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(cards)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._guide)
        layout.addWidget(self._bar)
        layout.addWidget(scroll, 1)

    def _make_field(self, name: str, title: str) -> ParamField:
        spec = self.model.schema[name]
        if spec.kind == "bool":
            return BoolField(spec, title)
        if spec.kind == "float_list":
            return ListField(spec, title)
        return ParamField(spec, title)

    def field(self, name: str) -> ParamField:
        return self._fields[name]

    @property
    def bar(self) -> ProfileBar:
        return self._bar

    @property
    def profile_name(self) -> str:
        return self.model.profile_name

    @property
    def applied_count(self) -> int:
        return self._applied_count

    def carried_parameters(self) -> Dict[str, Any]:
        return self.model.carried_parameters()

    def profile_names(self) -> List[str]:
        return self._bar.profile_names()

    def refresh_profiles(self) -> None:
        self._bar.set_profiles(self.model.profile_names(), self.model.profile_name)
        self._guide.setText(
            f"폼의 초기값은 test_profiles/{self.model.profile_name}.yaml에서 읽습니다. "
            "시퀀스에는 바꾼 항목만 전달됩니다."
        )

    def select_profile(self, name: str) -> None:
        if name not in self.model.profile_names():
            self.refresh_profiles()
            return
        if name == self.model.profile_name:
            return
        discarded = self.model.changed_count() > 0 or self._applied_count > 0
        self.model.load(name)
        self._after_profile_load()
        self._bar.show_message(DISCARD_NOTICE if discarded else "")

    def _after_profile_load(self) -> None:
        self._set_applied(self.model.carried_parameters(), 0)
        self.refresh_profiles()
        self._reload_fields()
        self.profile_changed.emit(self.model.profile_name)

    def _set_applied(self, parameters: Mapping[str, Any], count: int) -> None:
        self._applied_count = count
        self.applied.emit(dict(parameters), count)

    def _reload_fields(self) -> None:
        for name, field in self._fields.items():
            field.load(self.model.value(name))
        self._refresh_states()

    def _refresh_states(self) -> None:
        errors = self.model.errors()
        for name, field in self._fields.items():
            field.show_state(
                self.model.is_changed(name),
                errors.get(name),
                format_value(self.model.baseline(name)),
            )
        rules = self.model.rule_errors()
        self._bar.show_rule_errors(rules)
        self._bar.show_counts(self.model.changed_count(), len(errors) + len(rules))

    def _on_edited(self, name: str, raw: Any) -> None:
        self.model.set_value(name, raw)
        self._bar.show_message("")
        self._refresh_states()

    def revert(self) -> None:
        self.model.revert()
        self._bar.show_message("")
        self._reload_fields()

    def apply(self) -> None:
        if self.model.error_count():
            return
        parameters = self.model.to_parameters()
        self._set_applied(parameters, self.model.changed_count())
        self._bar.show_message("")

    def save_profile(self, name: str, overwrite: bool) -> None:
        try:
            self.model.save_as(name, overwrite=overwrite)
        except ProfileExistsError:
            self._bar.show_message(f"'{name}' 프로파일이 이미 있습니다.")
            return
        except ValueError as error:
            self._bar.show_message(str(error))
            return
        self._bar.clear_name()
        self._after_profile_load()
        self.profiles_changed.emit()
        self._bar.show_message(f"'{name}' 프로파일로 저장했습니다.")
