from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from eol_ui.widgets import card, label

from .names import profile_name_error


class ProfileBar(QWidget):
    profile_selected = Signal(str)
    revert_requested = Signal()
    save_requested = Signal(str, bool)
    apply_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._pending_overwrite: Optional[str] = None
        self._errors = 0

        self._combo = QComboBox()
        self._combo.setObjectName("settings-profile-combo")
        self._counts = label("", "counts")
        self._counts.setObjectName("change-counts")
        self._revert = QPushButton("되돌리기")
        self._revert.setObjectName("revert-button")
        self._name = QLineEdit()
        self._name.setObjectName("profile-name-input")
        self._name.setPlaceholderText("새 프로파일 이름")
        self._save = QPushButton("프로파일로 저장")
        self._save.setObjectName("save-profile-button")
        self._apply = QPushButton("다음 실행에 적용")
        self._apply.setObjectName("apply-button")
        self._apply.setProperty("primary", True)
        self._message = label("", "notice")
        self._message.setObjectName("profile-message")
        self._message.setWordWrap(True)
        self._overwrite = QPushButton("덮어쓰기")
        self._overwrite.setObjectName("overwrite-button")
        self._overwrite.setProperty("danger", True)
        self._cancel = QPushButton("취소")
        self._cancel.setObjectName("overwrite-cancel-button")
        self._overwrite_prompt = label("", "notice")
        self._overwrite_prompt.setObjectName("overwrite-prompt")

        panel = card()
        outer = QVBoxLayout(panel)
        top = QHBoxLayout()
        top.addWidget(label("프로파일", "muted"))
        top.addWidget(self._combo)
        top.addWidget(self._counts)
        top.addStretch(1)
        top.addWidget(self._revert)
        top.addWidget(self._name)
        top.addWidget(self._save)
        top.addWidget(self._apply)
        confirm = QHBoxLayout()
        confirm.addWidget(self._overwrite_prompt)
        confirm.addWidget(self._overwrite)
        confirm.addWidget(self._cancel)
        confirm.addStretch(1)
        self._confirm_row = QWidget()
        self._confirm_row.setLayout(confirm)
        confirm.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(top)
        outer.addWidget(self._confirm_row)
        outer.addWidget(self._message)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

        self._combo.activated.connect(self._on_activated)
        self._revert.clicked.connect(self.revert_requested)
        self._apply.clicked.connect(self.apply_requested)
        self._save.clicked.connect(self._on_save)
        self._overwrite.clicked.connect(self._on_overwrite)
        self._cancel.clicked.connect(self._clear_overwrite)
        self._name.textChanged.connect(self._on_name_changed)
        self._clear_overwrite()
        self.show_message("")

    def set_profiles(self, names: List[str], current: str) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(names)
        self._combo.setCurrentText(current)
        self._combo.blockSignals(False)

    def current_profile(self) -> str:
        return self._combo.currentText()

    def profile_names(self) -> List[str]:
        return [self._combo.itemText(index) for index in range(self._combo.count())]

    def select_profile(self, name: str) -> None:
        index = self._combo.findText(name)
        if index >= 0:
            self._combo.setCurrentIndex(index)
            self._on_activated(index)

    def _on_activated(self, index: int) -> None:
        self.profile_selected.emit(self._combo.itemText(index))

    def show_counts(self, changed: int, errors: int) -> None:
        self._counts.setText(f"변경 {changed} · 오류 {errors}")
        self._apply.setEnabled(errors == 0)
        self._apply.setToolTip("" if errors == 0 else "오류를 먼저 고쳐 주세요")
        self._errors = errors
        self._sync_save()
        self._revert.setEnabled(changed > 0 or errors > 0)

    def counts_text(self) -> str:
        return self._counts.text()

    def show_message(self, text: str) -> None:
        self._message.setText(text)
        self._message.setVisible(bool(text))

    def message_text(self) -> str:
        return self._message.text()

    def set_name(self, text: str) -> None:
        self._name.setText(text)

    def _on_name_changed(self, _: str) -> None:
        self._clear_overwrite()
        self.show_message("")

    def _on_save(self) -> None:
        name = self._name.text().strip()
        problem = profile_name_error(name)
        if problem:
            self.show_message(problem)
            return
        if name in self.profile_names():
            self._pending_overwrite = name
            self._overwrite_prompt.setText(f"'{name}' 프로파일이 이미 있습니다. 덮어쓸까요?")
            self._confirm_row.setVisible(True)
            self._sync_save()
            return
        self.save_requested.emit(name, False)

    def _on_overwrite(self) -> None:
        name = self._pending_overwrite
        self._clear_overwrite()
        if name:
            self.save_requested.emit(name, True)

    def _clear_overwrite(self) -> None:
        self._pending_overwrite = None
        self._confirm_row.setVisible(False)
        self._sync_save()

    def _sync_save(self) -> None:
        confirming = self._pending_overwrite is not None
        self._name.setEnabled(not confirming)
        self._save.setEnabled(self._errors == 0 and not confirming)

    def overwrite_prompt_visible(self) -> bool:
        return not self._confirm_row.isHidden()

    def clear_name(self) -> None:
        self._name.clear()

    @property
    def combo(self) -> QComboBox:
        return self._combo

    @property
    def apply_button(self) -> QPushButton:
        return self._apply

    @property
    def save_button(self) -> QPushButton:
        return self._save

    @property
    def revert_button(self) -> QPushButton:
        return self._revert

    @property
    def overwrite_button(self) -> QPushButton:
        return self._overwrite

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel

    @property
    def name_input(self) -> QLineEdit:
        return self._name
