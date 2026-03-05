from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation import input_dialogs

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
        self._variable_selector_get_current_package: Optional[Callable[[], object | None]] = None
        self._variable_selectors: list["VariableSelector"] = []
        self._setup_ui()

    def set_variable_selector_get_current_package(
        self, get_current_package: Callable[[], object | None] | None
    ) -> None:
        """为 VariableSelector 注入“当前项目存档”获取入口（用于按包语义过滤关卡变量候选项）。"""
        self._variable_selector_get_current_package = get_current_package
        for selector in self._variable_selectors:
            selector.set_get_current_package(get_current_package)

    def _register_variable_selector(self, selector: "VariableSelector") -> None:
        if selector in self._variable_selectors:
            return
        self._variable_selectors.append(selector)
        selector.set_get_current_package(self._variable_selector_get_current_package)

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


def _build_keyboard_key_candidates() -> list[str]:
    # 需求基线：0-9, A-Z, F1-F12（额外补充少量常用键名，仍允许手动输入）
    digits = [str(i) for i in range(10)]
    letters = [chr(ord("A") + i) for i in range(26)]
    functions = [f"F{i}" for i in range(1, 13)]
    common = ["Space", "Enter", "Esc", "Tab", "Shift", "Ctrl", "Alt"]
    return digits + letters + functions + common


KEYBOARD_KEY_CANDIDATES = _build_keyboard_key_candidates()
GAMEPAD_KEY_CANDIDATES = [
    "A",
    "B",
    "X",
    "Y",
    "LB",
    "RB",
    "LT",
    "RT",
    "Start",
    "Select",
    "DPadUp",
    "DPadDown",
    "DPadLeft",
    "DPadRight",
]


class VariableSelector(QtWidgets.QWidget):
    """统一的变量选择输入部件。"""

    value_selected = QtCore.pyqtSignal(str)

    def __init__(self, placeholder: str = "", parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._raw_value: str = ""
        self._syncing_text: bool = False
        self._get_current_package: Optional[Callable[[], object | None]] = None
        # 当处于全局视图且无法获得“当前项目存档”时，变量选择需要先显式选择一个包；
        # 该 override 用于：
        # - 选择完成后仍能把显示文本渲染为 `variable_name (variable_id)`
        # - 避免在无包上下文时回退到全局变量集做“名称→ID”自动归一化
        self._display_override_level_variables: Optional[Dict[str, Dict[str, Any]]] = None
        self._display_override_package_id: str = ""

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QtWidgets.QLineEdit()
        if placeholder:
            self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.textChanged.connect(self._on_text_changed)
        self.line_edit.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self.line_edit, 1)

        select_btn = QtWidgets.QPushButton("选择...")
        select_btn.setFixedWidth(68)
        select_btn.clicked.connect(self._prompt_variable)
        layout.addWidget(select_btn)

    def set_get_current_package(
        self, get_current_package: Callable[[], object | None] | None
    ) -> None:
        self._get_current_package = get_current_package

    def get_value(self) -> str:
        return self._raw_value

    def set_value(self, value: Any) -> None:
        raw_text = "" if value is None else str(value)
        normalized_raw = self._normalize_raw_value(raw_text)
        self._raw_value = normalized_raw
        self._sync_display_from_raw()

    def _on_text_changed(self, text: str) -> None:
        if self._syncing_text:
            return
        self._raw_value = str(text or "").strip()
        self.value_selected.emit(self._raw_value)

    def _on_editing_finished(self) -> None:
        # 将“显示文本”归一为存档配置中的最终值（仅做首尾空白归一化；不再做旧格式/ID 的兼容归一）。
        normalized_raw = self._normalize_raw_value(self.line_edit.text())
        if normalized_raw != self._raw_value:
            self._raw_value = normalized_raw
            self._sync_display_from_raw()
            self.value_selected.emit(self._raw_value)

    def _normalize_raw_value(self, input_text: str) -> str:
        return str(input_text or "").strip()

    def _get_package_level_variables(self) -> Optional[Dict[str, Dict]]:
        """返回当前项目存档的变量映射；若不存在存档上下文则返回 None。"""
        package = self._get_current_package() if callable(self._get_current_package) else None
        management = getattr(package, "management", None) if package is not None else None
        package_level_variables = getattr(management, "level_variables", None) if management is not None else None
        if isinstance(package_level_variables, dict):
            return package_level_variables
        return None

    def _get_effective_level_variables_for_display(self) -> Optional[Dict[str, Dict[str, Any]]]:
        package_level_variables = self._get_package_level_variables()
        if package_level_variables is not None:
            return package_level_variables  # type: ignore[return-value]
        if isinstance(self._display_override_level_variables, dict):
            return self._display_override_level_variables
        return None

    def _sync_display_from_raw(self) -> None:
        display_text = self._build_display_text(self._raw_value)
        self._syncing_text = True
        self.line_edit.setText(display_text)
        self._syncing_text = False

    def _build_display_text(self, raw_value: str) -> str:
        raw_text = str(raw_value or "").strip()
        if not raw_text:
            return ""
        return raw_text

    def _is_special_global_view_package_id(self, package_id: str) -> bool:
        return package_id == "global_view"

    def _resolve_app_state(self) -> object | None:
        window_obj = self.window()
        return getattr(window_obj, "app_state", None)

    def _prompt_package_id_for_variable_scope(self) -> str:
        """全局视图下：先选择一个“项目存档上下文”，再列举该包可用变量。"""
        from app.ui.foundation import dialog_utils

        app_state = self._resolve_app_state()
        package_index_manager = getattr(app_state, "package_index_manager", None) if app_state is not None else None
        if package_index_manager is None:
            dialog_utils.show_error_dialog(self, "选择变量", "无法获取项目存档列表，请检查项目状态。")
            return ""

        packages = package_index_manager.list_packages()
        items: list[str] = []
        for info in packages:
            if not isinstance(info, dict):
                continue
            package_id_value = info.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value.strip():
                continue
            package_id = package_id_value.strip()
            package_name = str(info.get("name", "") or "").strip() or package_id
            items.append(f"{package_name} | {package_id}")

        if not items:
            dialog_utils.show_info_dialog(
                self,
                "选择变量",
                "当前工程未发现任何可用的项目存档（无法为变量选择提供包上下文）。",
            )
            return ""

        items.sort(key=lambda text: text.lower())
        selected = input_dialogs.prompt_item(
            self,
            "选择变量所属项目存档",
            "项目存档:",
            items,
            current_index=0,
            editable=False,
        )
        if selected is None:
            return ""

        parts = [part.strip() for part in selected.split("|")]
        return parts[1] if len(parts) >= 2 else ""

    def _load_package_level_variables_by_package_id(self, package_id: str) -> Optional[Dict[str, Dict[str, Any]]]:
        from app.ui.foundation import dialog_utils
        from engine.resources.package_view import PackageView

        package_id_text = str(package_id or "").strip()
        if not package_id_text:
            return None

        app_state = self._resolve_app_state()
        package_index_manager = getattr(app_state, "package_index_manager", None) if app_state is not None else None
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        if package_index_manager is None or resource_manager is None:
            dialog_utils.show_error_dialog(
                self,
                "选择变量",
                "无法加载项目存档，请检查资源是否就绪。",
            )
            return None

        package_index = package_index_manager.load_package_index(package_id_text)
        if package_index is None:
            dialog_utils.show_error_dialog(self, "选择变量", f"未找到指定的项目存档：{package_id_text}，它可能已被移动或删除。")
            return None

        package_view = PackageView(package_index=package_index, resource_manager=resource_manager)
        management = getattr(package_view, "management", None)
        variables = getattr(management, "level_variables", None) if management is not None else None
        if isinstance(variables, dict):
            return variables
        return None

    def _prompt_variable(self) -> None:
        from app.ui.foundation import dialog_utils
        from .variable_picker_dialog import VariablePickerDialog
        available_variables: Dict[str, Dict[str, Any]] | None = None

        package = self._get_current_package() if callable(self._get_current_package) else None
        package_id_value = getattr(package, "package_id", None) if package is not None else None
        package_id_text = str(package_id_value or "").strip() if isinstance(package_id_value, str) else ""

        # 1) 存档上下文：直接使用当前项目存档引用聚合出的变量集合（稳定且按包过滤）。
        package_level_variables = self._get_package_level_variables()
        if package_level_variables is not None:
            available_variables = package_level_variables  # type: ignore[assignment]
            # 清空 override，避免后续显示与当前包不一致
            self._display_override_level_variables = None
            self._display_override_package_id = ""

        # 2) 全局视图或无上下文：必须先选择一个包作为“变量可见范围”
        if available_variables is None:
            # 特殊视图也视为“无包上下文”（变量集合应由用户选择包决定）
            if package_id_text and not self._is_special_global_view_package_id(package_id_text):
                # 仍可能存在“包对象不完整但 package_id 可用”的情况：兜底按 package_id 加载
                loaded = self._load_package_level_variables_by_package_id(package_id_text)
                if loaded is not None:
                    available_variables = loaded
                    self._display_override_level_variables = loaded
                    self._display_override_package_id = package_id_text

        if available_variables is None:
            selected_package_id = self._prompt_package_id_for_variable_scope()
            if not selected_package_id:
                return
            loaded = self._load_package_level_variables_by_package_id(selected_package_id)
            if loaded is None:
                return
            available_variables = loaded
            self._display_override_level_variables = loaded
            self._display_override_package_id = selected_package_id

        if not available_variables:
            dialog_utils.show_info_dialog(
                self,
                "选择变量",
                "当前上下文下没有可用的关卡变量。\n"
                "如果你在存档视图中，请先在 管理配置 > 关卡变量 中将变量文件加入当前存档引用。",
            )
            return

        picker = VariablePickerDialog(available_variables, parent=self)
        if picker.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        chosen_name = str(picker.get_selected_variable_name() or "").strip()
        if not chosen_name:
            return

        self._raw_value = chosen_name
        self._sync_display_from_raw()
        self.value_selected.emit(self._raw_value)


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
        self._owner._register_variable_selector(selector)
        self._owner._register_binding(
            key,
            getter=selector.get_value,
            setter=lambda value, selector=selector: selector.set_value(value),
            signal=selector.value_selected,
        )
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
        keyboard_completer = QtWidgets.QCompleter(KEYBOARD_KEY_CANDIDATES, keyboard_edit)
        keyboard_completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        keyboard_edit.setCompleter(keyboard_completer)

        gamepad_edit: Optional[QtWidgets.QLineEdit] = None
        if gamepad_key:
            gamepad_edit = self.add_line_edit(
                gamepad_label,
                gamepad_key,
                placeholder=gamepad_placeholder,
            )
            gamepad_completer = QtWidgets.QCompleter(GAMEPAD_KEY_CANDIDATES, gamepad_edit)
            gamepad_completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
            gamepad_edit.setCompleter(gamepad_completer)
        return KeyMappingFields(keyboard=keyboard_edit, gamepad=gamepad_edit)

    def add_row_widget(self, label: str, widget: QtWidgets.QWidget) -> None:
        self.layout.addRow(label, widget)

    def add_section_widget(self, widget: QtWidgets.QWidget) -> None:
        self.layout.addRow(widget)

