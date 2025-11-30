from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

from PyQt6 import QtCore, QtWidgets

from ui.foundation import input_dialogs

FieldGetter = Callable[[], Any]
FieldSetter = Callable[[Any], None]


class BaseWidgetConfigPanel(QtWidgets.QWidget):
    """控件配置面板基类，提供字段绑定与统一的设置读写。"""

    config_changed = QtCore.pyqtSignal(dict)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.current_config: Dict[str, Any] = {}
        self._bindings: Dict[str, tuple[FieldGetter, FieldSetter]] = {}
        self._syncing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """设置 UI - 子类实现"""

    # ----------------------------------------------------------------------------------
    # 公共配置接口
    # ----------------------------------------------------------------------------------
    def load_config(self, config: Dict[str, Any]) -> None:
        self.current_config = config.copy()
        self._update_ui_from_config()

    def _update_ui_from_config(self) -> None:
        settings = self._settings()
        self._syncing = True
        for key, (_, setter) in self._bindings.items():
            setter(settings.get(key))
        self._syncing = False

    def get_config(self) -> Dict[str, Any]:
        return self.current_config.copy()

    # ----------------------------------------------------------------------------------
    # 绑定工具
    # ----------------------------------------------------------------------------------
    def _settings(self) -> Dict[str, Any]:
        return self.current_config.setdefault("settings", {})

    def _register_binding(
        self,
        key: str,
        getter: FieldGetter,
        setter: FieldSetter,
        signal: Optional[QtCore.pyqtBoundSignal] = None,
    ) -> None:
        self._bindings[key] = (getter, setter)
        if signal is not None:
            signal.connect(lambda *_, key=key: self._on_field_changed(key))

    def _on_field_changed(self, key: str) -> None:
        if self._syncing:
            return
        settings = self._settings()
        getter = self._bindings[key][0]
        settings[key] = getter()
        self._emit_changed()

    def _emit_changed(self) -> None:
        self.config_changed.emit(self.get_config())

    # 常用控件绑定 ----------------------------------------------------------------------
    def _bind_line_edit(
        self,
        key: str,
        widget: QtWidgets.QLineEdit,
        *,
        default: str = "",
    ) -> QtWidgets.QLineEdit:
        self._register_binding(
            key,
            getter=widget.text,
            setter=lambda value, widget=widget, default=default: widget.setText(
                value if value is not None else default
            ),
            signal=widget.textChanged,
        )
        return widget

    def _bind_plain_text_edit(
        self,
        key: str,
        widget: QtWidgets.QPlainTextEdit,
        *,
        default: str = "",
    ) -> QtWidgets.QPlainTextEdit:
        self._register_binding(
            key,
            getter=widget.toPlainText,
            setter=lambda value, widget=widget, default=default: widget.setPlainText(
                value if value is not None else default
            ),
            signal=widget.textChanged,
        )
        return widget

    def _bind_combo_box(
        self,
        key: str,
        widget: QtWidgets.QComboBox,
        *,
        default_text: Optional[str] = None,
        default_index: int = 0,
    ) -> QtWidgets.QComboBox:
        def setter(
            value,
            widget: QtWidgets.QComboBox = widget,
            default_text: Optional[str] = default_text,
            default_index: int = default_index,
        ) -> None:
            target_value = value if value is not None else default_text
            if target_value is not None and widget.findText(target_value) >= 0:
                widget.setCurrentText(target_value)
            elif widget.count() > default_index >= 0:
                widget.setCurrentIndex(default_index)

        self._register_binding(
            key,
            getter=widget.currentText,
            setter=setter,
            signal=widget.currentTextChanged,
        )
        return widget

    def _bind_checkbox(
        self,
        key: str,
        widget: QtWidgets.QCheckBox,
        *,
        default: bool = False,
    ) -> QtWidgets.QCheckBox:
        self._register_binding(
            key,
            getter=widget.isChecked,
            setter=lambda value, widget=widget, default=default: widget.setChecked(
                bool(value) if value is not None else default
            ),
            signal=widget.stateChanged,
        )
        return widget

    def _bind_spin_box(
        self,
        key: str,
        widget: QtWidgets.QSpinBox | QtWidgets.QDoubleSpinBox,
        *,
        default: float = 0,
    ) -> QtWidgets.QSpinBox | QtWidgets.QDoubleSpinBox:
        def setter(value: Any, widget=widget, default_value=default) -> None:
            target = value if value is not None else default_value
            if isinstance(widget, QtWidgets.QSpinBox):
                widget.setValue(int(target))
            else:
                widget.setValue(float(target))

        self._register_binding(
            key,
            getter=widget.value,
            setter=setter,
            signal=widget.valueChanged,
        )
        return widget


@dataclass
class KeyMappingFields:
    keyboard: QtWidgets.QLineEdit
    gamepad: Optional[QtWidgets.QLineEdit] = None


class VariableSelector(QtWidgets.QWidget):
    """统一的变量选择输入部件。"""

    value_selected = QtCore.pyqtSignal(str)

    def __init__(self, placeholder: str = "", parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QtWidgets.QLineEdit()
        if placeholder:
            self.line_edit.setPlaceholderText(placeholder)
        layout.addWidget(self.line_edit, 1)

        select_btn = QtWidgets.QPushButton("选择...")
        select_btn.setFixedWidth(68)
        select_btn.clicked.connect(self._prompt_variable)
        layout.addWidget(select_btn)

    def _prompt_variable(self) -> None:
        cleaned = input_dialogs.prompt_text(
            self,
            "选择变量",
            "变量名称:",
            text=self.line_edit.text(),
        )
        if cleaned is None:
            return
        self.line_edit.setText(cleaned)
        self.value_selected.emit(cleaned)


class WidgetConfigForm(QtWidgets.QWidget):
    """封装常用字段添加方法，保持表单一致性。"""

    def __init__(
        self,
        owner: BaseWidgetConfigPanel,
        *,
        margins: Sequence[int] = (0, 0, 0, 0),
    ) -> None:
        super().__init__(owner)
        self._owner = owner
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(*margins)
        layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
        self.layout = layout

    def add_line_edit(
        self,
        label: str,
        key: str,
        *,
        placeholder: str = "",
        default: str = "",
    ) -> QtWidgets.QLineEdit:
        edit = QtWidgets.QLineEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        self._owner._bind_line_edit(key, edit, default=default)
        self.layout.addRow(label, edit)
        return edit

    def add_plain_text_edit(
        self,
        label: str,
        key: str,
        *,
        placeholder: str = "",
        max_height: Optional[int] = None,
    ) -> QtWidgets.QPlainTextEdit:
        edit = QtWidgets.QPlainTextEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        if max_height:
            edit.setMaximumHeight(max_height)
        self._owner._bind_plain_text_edit(key, edit)
        self.layout.addRow(label, edit)
        return edit

    def add_combo_box(
        self,
        label: str,
        key: str,
        items: Sequence[str],
        *,
        default_text: Optional[str] = None,
        default_index: int = 0,
    ) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.addItems(list(items))
        self._owner._bind_combo_box(key, combo, default_text=default_text, default_index=default_index)
        self.layout.addRow(label, combo)
        return combo

    def add_checkbox(
        self,
        key: str,
        text: str,
        *,
        default: bool = False,
        row_label: str = "",
    ) -> QtWidgets.QCheckBox:
        checkbox = QtWidgets.QCheckBox(text)
        self._owner._bind_checkbox(key, checkbox, default=default)
        self.layout.addRow(row_label, checkbox)
        return checkbox

    def add_spin_box(
        self,
        label: str,
        key: str,
        *,
        minimum: int = 0,
        maximum: int = 100,
        default: int = 0,
    ) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        self._owner._bind_spin_box(key, spin, default=default)
        self.layout.addRow(label, spin)
        return spin

    def add_double_spin_box(
        self,
        label: str,
        key: str,
        *,
        minimum: float = 0.0,
        maximum: float = 100.0,
        step: float = 0.1,
        suffix: str = "",
        default: float = 0.0,
    ) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        if suffix:
            spin.setSuffix(suffix)
        self._owner._bind_spin_box(key, spin, default=default)
        self.layout.addRow(label, spin)
        return spin

    def add_variable_selector(
        self,
        label: str,
        key: str,
        *,
        placeholder: str = "",
    ) -> VariableSelector:
        selector = VariableSelector(placeholder, self)
        self._owner._bind_line_edit(key, selector.line_edit)
        self.layout.addRow(label, selector)
        return selector

    def add_key_mapping_pair(
        self,
        keyboard_key: str,
        gamepad_key: Optional[str] = None,
        *,
        keyboard_label: str = "按键映射(键鼠):",
        gamepad_label: str = "按键映射(手柄):",
        keyboard_placeholder: str = "",
        gamepad_placeholder: str = "",
    ) -> KeyMappingFields:
        keyboard_edit = self.add_line_edit(
            keyboard_label,
            keyboard_key,
            placeholder=keyboard_placeholder,
        )
        gamepad_edit: Optional[QtWidgets.QLineEdit] = None
        if gamepad_key:
            gamepad_edit = self.add_line_edit(
                gamepad_label,
                gamepad_key,
                placeholder=gamepad_placeholder,
            )
        return KeyMappingFields(keyboard=keyboard_edit, gamepad=gamepad_edit)

    def add_row_widget(self, label: str, widget: QtWidgets.QWidget) -> None:
        self.layout.addRow(label, widget)

    def add_section_widget(self, widget: QtWidgets.QWidget) -> None:
        self.layout.addRow(widget)

