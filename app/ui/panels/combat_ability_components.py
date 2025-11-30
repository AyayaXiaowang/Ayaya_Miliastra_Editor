"""能力编辑页的可复用组件集合。

目前仅包含“战斗设置”组件，用于在玩家模板 -> 角色编辑 -> 能力标签页中配置：
- 不可被元素附着
- 不可被目标锁定
- 受击特效
- 被击倒特效

设计目标：
- 将一组战斗相关字段打包为可折叠的独立组件，便于在其他能力编辑场景中复用
- 组件本身只负责 UI 展示与数据收集，通过简单的 dict 进行读写，不直接依赖具体存盘格式
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.configs.combat import CombatEffectAssetType
from ui.foundation.theme_manager import Colors, Sizes
from ui.foundation.toggle_switch import ToggleSwitch
from ui.panels.ui_control_group_collapsible_section import CollapsibleSection


@dataclass(frozen=True)
class AbilityComponentSpec:
    """用于标记能力组件的元信息，方便在不同页面中复用与约束。

    - component_id: 程序内唯一标识
    - display_name: UI 展示名称
    - allowed_hosts: 允许挂载的宿主类型（例如 "player_template_role"）
    - allowed_tabs: 允许出现的标签页 key（例如 "role_abilities"）
    """

    component_id: str
    display_name: str
    allowed_hosts: Tuple[str, ...]
    allowed_tabs: Tuple[str, ...]
    description: str = ""


class EffectConfigEditor(QtWidgets.QWidget):
    """受击/被击倒特效配置子组件。

    该组件不关心具体存盘模型，仅在 `load_from_dict` / `to_dict` 中约定好字段名称：
    - effect_asset_type: "限时特效" / "循环特效"
    - effect_asset_id: 特效资产配置 ID（字符串形式）
    - play_sound: 是否播放特效资产自带音效
    - scale: [uniform_scale, uniform_scale, uniform_scale]
    - offset: [x, y, z]
    - rotation: [x, y, z]
    """

    changed = QtCore.pyqtSignal()

    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._title = title
        self._build_ui()

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)

        title_label = QtWidgets.QLabel(self._title)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(Sizes.SPACING_SMALL)

        self.asset_type_combo = QtWidgets.QComboBox()
        for asset_type in CombatEffectAssetType:
            self.asset_type_combo.addItem(asset_type.value, asset_type)
        form.addRow("特效资产类型", self.asset_type_combo)

        self.asset_id_edit = QtWidgets.QLineEdit()
        self.asset_id_edit.setPlaceholderText("输入特效资产配置ID")
        form.addRow("特效资产ID", self.asset_id_edit)

        self.play_sound_switch = ToggleSwitch()
        form.addRow("是否播放特效资产音效", self.play_sound_switch)

        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.01, 100.0)
        self.scale_spin.setDecimals(2)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setValue(1.0)
        form.addRow("缩放比例", self.scale_spin)

        self.offset_x_spin, self.offset_y_spin, self.offset_z_spin = self._create_vector_row(
            form, "偏移"
        )
        (
            self.rotation_x_spin,
            self.rotation_y_spin,
            self.rotation_z_spin,
        ) = self._create_vector_row(form, "旋转")

        layout.addLayout(form)

        self.asset_type_combo.currentIndexChanged.connect(self._emit_changed)
        self.asset_id_edit.textChanged.connect(self._emit_changed)
        self.play_sound_switch.stateChanged.connect(self._emit_changed)
        self.scale_spin.valueChanged.connect(self._emit_changed)
        for spin_box in (
            self.offset_x_spin,
            self.offset_y_spin,
            self.offset_z_spin,
            self.rotation_x_spin,
            self.rotation_y_spin,
            self.rotation_z_spin,
        ):
            spin_box.valueChanged.connect(self._emit_changed)

    def _create_vector_row(
        self,
        form: QtWidgets.QFormLayout,
        label_text: str,
    ) -> Tuple[QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox]:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)

        x_spin = self._create_vector_spinbox()
        y_spin = self._create_vector_spinbox()
        z_spin = self._create_vector_spinbox()

        for axis_label_text, spin in (("X", x_spin), ("Y", y_spin), ("Z", z_spin)):
            axis_label = QtWidgets.QLabel(axis_label_text)
            axis_label.setFixedWidth(14)
            layout.addWidget(axis_label)
            layout.addWidget(spin)

        layout.addStretch()
        form.addRow(label_text, container)
        return x_spin, y_spin, z_spin

    @staticmethod
    def _create_vector_spinbox() -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(-9999.0, 9999.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setValue(0.0)
        return spin

    # ------------------------------------------------------------------ 数据读写

    def _reset_fields(self) -> None:
        self.asset_type_combo.setCurrentIndex(0)
        self.asset_id_edit.setText("")
        self.play_sound_switch.setChecked(True)
        self.scale_spin.setValue(1.0)
        for spin_box in (
            self.offset_x_spin,
            self.offset_y_spin,
            self.offset_z_spin,
            self.rotation_x_spin,
            self.rotation_y_spin,
            self.rotation_z_spin,
        ):
            spin_box.setValue(0.0)

    def load_from_dict(self, data: Optional[Dict[str, Any]]) -> None:
        """从字典加载配置，容错为主，不抛异常。"""
        self.blockSignals(True)

        if not isinstance(data, dict):
            self._reset_fields()
            self.blockSignals(False)
            return

        effect_asset_type = data.get("effect_asset_type")
        if isinstance(effect_asset_type, str):
            index = self.asset_type_combo.findText(effect_asset_type)
            if index >= 0:
                self.asset_type_combo.setCurrentIndex(index)
            else:
                self.asset_type_combo.setCurrentIndex(0)
        else:
            self.asset_type_combo.setCurrentIndex(0)

        asset_id = data.get("effect_asset_id")
        self.asset_id_edit.setText(str(asset_id)) if asset_id is not None else self.asset_id_edit.setText("")

        play_sound = data.get("play_sound", True)
        self.play_sound_switch.setChecked(bool(play_sound))

        scale_value = data.get("scale", 1.0)
        if isinstance(scale_value, (int, float)):
            self.scale_spin.setValue(scale_value)
        elif isinstance(scale_value, (list, tuple)) and scale_value:
            first_value = scale_value[0]
            if isinstance(first_value, (int, float)):
                self.scale_spin.setValue(first_value)
            else:
                self.scale_spin.setValue(1.0)
        else:
            self.scale_spin.setValue(1.0)

        offset_values = self._normalize_vector(data.get("offset"))
        self.offset_x_spin.setValue(offset_values[0])
        self.offset_y_spin.setValue(offset_values[1])
        self.offset_z_spin.setValue(offset_values[2])

        rotation_values = self._normalize_vector(data.get("rotation"))
        self.rotation_x_spin.setValue(rotation_values[0])
        self.rotation_y_spin.setValue(rotation_values[1])
        self.rotation_z_spin.setValue(rotation_values[2])

        self.blockSignals(False)

    @staticmethod
    def _normalize_vector(value: Any) -> Tuple[float, float, float]:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            raw_x, raw_y, raw_z = value[0], value[1], value[2]
        else:
            raw_x = raw_y = raw_z = 0.0

        x = raw_x if isinstance(raw_x, (int, float)) else 0.0
        y = raw_y if isinstance(raw_y, (int, float)) else 0.0
        z = raw_z if isinstance(raw_z, (int, float)) else 0.0
        return float(x), float(y), float(z)

    def _is_default_state(self) -> bool:
        asset_id_text = self.asset_id_edit.text().strip()
        is_default_type = self.asset_type_combo.currentIndex() == 0
        is_default_scale = abs(self.scale_spin.value() - 1.0) < 1e-6
        is_default_offset = (
            abs(self.offset_x_spin.value()) < 1e-6
            and abs(self.offset_y_spin.value()) < 1e-6
            and abs(self.offset_z_spin.value()) < 1e-6
        )
        is_default_rotation = (
            abs(self.rotation_x_spin.value()) < 1e-6
            and abs(self.rotation_y_spin.value()) < 1e-6
            and abs(self.rotation_z_spin.value()) < 1e-6
        )
        return (
            not asset_id_text
            and is_default_type
            and self.play_sound_switch.isChecked()
            and is_default_scale
            and is_default_offset
            and is_default_rotation
        )

    def to_dict(self) -> Optional[Dict[str, Any]]:
        """导出当前配置；当处于全默认状态且未填写资产ID时返回 None。"""
        if self._is_default_state():
            return None

        result: Dict[str, Any] = {}

        asset_type = self.asset_type_combo.currentData()
        if isinstance(asset_type, CombatEffectAssetType):
            result["effect_asset_type"] = asset_type.value
        else:
            result["effect_asset_type"] = self.asset_type_combo.currentText()

        asset_id_text = self.asset_id_edit.text().strip()
        if asset_id_text:
            result["effect_asset_id"] = asset_id_text

        result["play_sound"] = self.play_sound_switch.isChecked()

        uniform_scale = self.scale_spin.value()
        result["scale"] = [uniform_scale, uniform_scale, uniform_scale]
        result["offset"] = [
            self.offset_x_spin.value(),
            self.offset_y_spin.value(),
            self.offset_z_spin.value(),
        ]
        result["rotation"] = [
            self.rotation_x_spin.value(),
            self.rotation_y_spin.value(),
            self.rotation_z_spin.value(),
        ]

        return result

    # ------------------------------------------------------------------ 信号

    def _emit_changed(self) -> None:
        self.changed.emit()


class CombatSettingsSection(CollapsibleSection):
    """战斗设置能力组件。

    仅用于“玩家模板 -> 角色编辑 -> 能力”标签页，负责收集战斗层面的基础标记与受击/击倒特效配置。
    外部通过 `set_from_metadata()` 与 `to_metadata()` 与字典结构互相转换。
    """

    changed = QtCore.pyqtSignal()

    spec = AbilityComponentSpec(
        component_id="combat_settings",
        display_name="战斗设置",
        allowed_hosts=("player_template_role",),
        allowed_tabs=("role_abilities",),
        description="配置角色在战斗中的基础标记与受击/被击倒特效。",
    )

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("战斗设置", parent)
        self.setObjectName("CombatSettingsSection")
        self.setStyleSheet(
            f"""
            QWidget#CombatSettingsSection {{
                background-color: {Colors.BG_CARD};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
                border: 1px solid {Colors.BORDER_LIGHT};
            }}
        """
        )
        self._build_ui()

    def _build_ui(self) -> None:
        flags_group = QtWidgets.QGroupBox("基础战斗标记")
        flags_layout = QtWidgets.QFormLayout(flags_group)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        flags_layout.setSpacing(Sizes.SPACING_SMALL)

        self.cannot_be_element_attached_switch = ToggleSwitch()
        self.cannot_be_target_locked_switch = ToggleSwitch()

        flags_layout.addRow("不可被元素附着", self.cannot_be_element_attached_switch)
        flags_layout.addRow("不可被目标锁定", self.cannot_be_target_locked_switch)

        self.content_layout.addWidget(flags_group)

        self.hit_effect_editor = EffectConfigEditor("受击特效")
        self.knockdown_effect_editor = EffectConfigEditor("被击倒特效")
        self.content_layout.addWidget(self.hit_effect_editor)
        self.content_layout.addWidget(self.knockdown_effect_editor)
        self.content_layout.addStretch()

        self.cannot_be_element_attached_switch.stateChanged.connect(self._emit_changed)
        self.cannot_be_target_locked_switch.stateChanged.connect(self._emit_changed)
        self.hit_effect_editor.changed.connect(self._emit_changed)
        self.knockdown_effect_editor.changed.connect(self._emit_changed)

    # ------------------------------------------------------------------ 数据读写

    def _set_switch_checked(self, widget: ToggleSwitch, value: bool) -> None:
        widget.blockSignals(True)
        widget.setChecked(value)
        widget.blockSignals(False)

    def set_from_metadata(self, data: Optional[Dict[str, Any]]) -> None:
        """从 metadata 字典加载战斗设置。

        预期结构：
        {
            "cannot_be_element_attached": bool,
            "cannot_be_target_locked": bool,
            "hit_effect": {...},
            "knockdown_effect": {...}
        }
        """
        if not isinstance(data, dict):
            self._set_switch_checked(self.cannot_be_element_attached_switch, False)
            self._set_switch_checked(self.cannot_be_target_locked_switch, False)
            self.hit_effect_editor.load_from_dict(None)
            self.knockdown_effect_editor.load_from_dict(None)
            return

        self._set_switch_checked(
            self.cannot_be_element_attached_switch,
            bool(data.get("cannot_be_element_attached", False)),
        )
        self._set_switch_checked(
            self.cannot_be_target_locked_switch,
            bool(data.get("cannot_be_target_locked", False)),
        )

        self.hit_effect_editor.load_from_dict(
            data.get("hit_effect") if isinstance(data.get("hit_effect"), dict) else None
        )
        self.knockdown_effect_editor.load_from_dict(
            data.get("knockdown_effect") if isinstance(data.get("knockdown_effect"), dict) else None
        )

    def to_metadata(self) -> Dict[str, Any]:
        """导出为可写入 metadata 的字典结构。"""
        result: Dict[str, Any] = {
            "cannot_be_element_attached": self.cannot_be_element_attached_switch.isChecked(),
            "cannot_be_target_locked": self.cannot_be_target_locked_switch.isChecked(),
        }

        hit_effect_data = self.hit_effect_editor.to_dict()
        knockdown_effect_data = self.knockdown_effect_editor.to_dict()
        if hit_effect_data is not None:
            result["hit_effect"] = hit_effect_data
        if knockdown_effect_data is not None:
            result["knockdown_effect"] = knockdown_effect_data

        return result

    # ------------------------------------------------------------------ 信号

    def _emit_changed(self) -> None:
        self.changed.emit()


__all__ = [
    "AbilityComponentSpec",
    "EffectConfigEditor",
    "CombatSettingsSection",
]


