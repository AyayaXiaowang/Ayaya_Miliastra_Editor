"""Combat tab for template/instance panel (物件/造物/实体)."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6 import QtWidgets

from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from app.ui.foundation.dialog_utils import show_info_dialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toggle_switch import ToggleSwitch
from app.ui.panels.panel_dict_utils import (
    ensure_nested_dict,
)
from app.ui.panels.panel_scaffold import build_scrollable_column
from app.ui.panels.template_instance.tab_base import TemplateInstanceTabBase
from app.ui.panels.ui.ui_control_group_collapsible_section import CollapsibleSection


class CombatTab(TemplateInstanceTabBase):
    """战斗标签页：为物件/造物模板与其实体摆放提供战斗相关字段编辑。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._updating_ui: bool = False
        self._is_read_only: bool = False
        self._supported_widgets: list[QtWidgets.QWidget] = []
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area, _content_widget, content_layout = build_scrollable_column(
            self,
            spacing=Sizes.SPACING_MEDIUM,
            margins=(
                Sizes.PADDING_SMALL,
                Sizes.PADDING_SMALL,
                Sizes.PADDING_SMALL,
                Sizes.PADDING_SMALL,
            ),
            add_trailing_stretch=False,
        )
        root_layout.addWidget(scroll_area)

        self._unsupported_hint = QtWidgets.QLabel(self)
        self._unsupported_hint.setWordWrap(True)
        self._unsupported_hint.setStyleSheet(ThemeManager.info_label_style())
        self._unsupported_hint.setText("当前对象不支持战斗配置（仅物件/造物模板与其实体摆放可用）。")
        self._unsupported_hint.setVisible(False)
        content_layout.addWidget(self._unsupported_hint)

        # --- 基础属性（不折叠）------------------------------------------------
        basic_group = QtWidgets.QGroupBox("基础属性", self)
        basic_group.setStyleSheet(ThemeManager.group_box_style())
        basic_layout = QtWidgets.QFormLayout(basic_group)
        basic_layout.setSpacing(Sizes.SPACING_SMALL)

        self.level_spin = QtWidgets.QSpinBox(basic_group)
        self.level_spin.setRange(1, 999)
        self.level_spin.setValue(1)
        basic_layout.addRow("等级", self.level_spin)

        self.base_hp_spin = QtWidgets.QDoubleSpinBox(basic_group)
        self.base_hp_spin.setRange(0.0, 9_999_999.0)
        self.base_hp_spin.setDecimals(2)
        self.base_hp_spin.setValue(10.0)
        basic_layout.addRow("基础生命值", self.base_hp_spin)

        self.base_attack_spin = QtWidgets.QDoubleSpinBox(basic_group)
        self.base_attack_spin.setRange(0.0, 9_999_999.0)
        self.base_attack_spin.setDecimals(2)
        self.base_attack_spin.setValue(1.0)
        basic_layout.addRow("基础攻击力", self.base_attack_spin)

        self.base_defense_spin = QtWidgets.QDoubleSpinBox(basic_group)
        self.base_defense_spin.setRange(0.0, 9_999_999.0)
        self.base_defense_spin.setDecimals(2)
        self.base_defense_spin.setValue(500.0)
        basic_layout.addRow("基础防御力", self.base_defense_spin)

        self.is_invincible_switch = ToggleSwitch(basic_group)
        basic_layout.addRow("是否无敌", self.is_invincible_switch)

        content_layout.addWidget(basic_group)
        self._supported_widgets.append(basic_group)

        # --- 仇恨配置（折叠组）------------------------------------------------
        self.aggro_section = CollapsibleSection("仇恨配置", self)
        self.aggro_hint = QtWidgets.QLabel(self.aggro_section)
        self.aggro_hint.setWordWrap(True)
        self.aggro_hint.setStyleSheet(ThemeManager.info_label_style())
        self.aggro_section.content_layout.addWidget(self.aggro_hint)
        content_layout.addWidget(self.aggro_section)
        self._supported_widgets.append(self.aggro_section)

        # --- 受击盒设置（折叠组）----------------------------------------------
        self.hitbox_section = CollapsibleSection("受击盒设置", self)
        hitbox_form = QtWidgets.QFormLayout()
        hitbox_form.setSpacing(Sizes.SPACING_SMALL)

        self.hitbox_initial_combo = QtWidgets.QComboBox(self.hitbox_section)
        self.hitbox_initial_combo.addItem("暂无", 0)
        self.hitbox_initial_combo.addItem("启用", 1)
        self.hitbox_initial_combo.addItem("禁用", 2)
        hitbox_form.addRow("初始生效", self.hitbox_initial_combo)

        self.hitbox_detail_button = QtWidgets.QPushButton("详细编辑", self.hitbox_section)
        self.hitbox_detail_button.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.hitbox_detail_button.setStyleSheet(ThemeManager.button_style())
        hitbox_form.addRow(self.hitbox_detail_button)

        self.hitbox_section.content_layout.addLayout(hitbox_form)
        content_layout.addWidget(self.hitbox_section)
        self._supported_widgets.append(self.hitbox_section)

        # --- 战斗设置（折叠组）------------------------------------------------
        self.combat_section = CollapsibleSection("战斗设置", self)
        combat_form = QtWidgets.QFormLayout()
        combat_form.setSpacing(Sizes.SPACING_SMALL)

        self.immune_to_element_switch = ToggleSwitch(self.combat_section)
        combat_form.addRow("不可被元素附着", self.immune_to_element_switch)

        self.untargetable_switch = ToggleSwitch(self.combat_section)
        combat_form.addRow("不可被目标锁定", self.untargetable_switch)

        self.tracking_point_edit = QtWidgets.QLineEdit(self.combat_section)
        self.tracking_point_edit.setPlaceholderText("例如：GI_RootNode")
        self.tracking_point_edit.setStyleSheet(ThemeManager.input_style())
        combat_form.addRow("子弹追踪点", self.tracking_point_edit)

        self.hit_vfx_edit = self._build_asset_reference_edit(
            parent=self.combat_section,
            placeholder_text="AssetID_Or_Path",
        )
        combat_form.addRow("受击特效", self.hit_vfx_edit)

        self.knockdown_vfx_edit = self._build_asset_reference_edit(
            parent=self.combat_section,
            placeholder_text="AssetID_Or_Path",
        )
        combat_form.addRow("被击倒特效", self.knockdown_vfx_edit)

        self.combat_detail_button = QtWidgets.QPushButton("详细编辑", self.combat_section)
        self.combat_detail_button.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.combat_detail_button.setStyleSheet(ThemeManager.button_style())
        combat_form.addRow(self.combat_detail_button)

        self.combat_section.content_layout.addLayout(combat_form)
        content_layout.addWidget(self.combat_section)
        self._supported_widgets.append(self.combat_section)

        # --- 能力单元（折叠组）------------------------------------------------
        self.ability_section = CollapsibleSection("能力单元", self)
        self.ability_detail_button = QtWidgets.QPushButton("详细编辑", self.ability_section)
        self.ability_detail_button.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.ability_detail_button.setStyleSheet(ThemeManager.button_style())
        self.ability_section.content_layout.addWidget(self.ability_detail_button)
        content_layout.addWidget(self.ability_section)
        self._supported_widgets.append(self.ability_section)

        content_layout.addStretch(1)

        # --- 信号绑定 --------------------------------------------------------
        self.level_spin.valueChanged.connect(self._on_base_stats_changed)
        self.base_hp_spin.valueChanged.connect(self._on_base_stats_changed)
        self.base_attack_spin.valueChanged.connect(self._on_base_stats_changed)
        self.base_defense_spin.valueChanged.connect(self._on_base_stats_changed)
        self.is_invincible_switch.stateChanged.connect(self._on_base_stats_changed)

        self.hitbox_initial_combo.currentIndexChanged.connect(self._on_hitbox_changed)
        self.hitbox_detail_button.clicked.connect(self._on_edit_hitbox_detail)

        self.immune_to_element_switch.stateChanged.connect(self._on_combat_settings_changed)
        self.untargetable_switch.stateChanged.connect(self._on_combat_settings_changed)
        self.tracking_point_edit.editingFinished.connect(self._on_combat_settings_changed)
        self.hit_vfx_edit.editingFinished.connect(self._on_combat_settings_changed)
        self.knockdown_vfx_edit.editingFinished.connect(self._on_combat_settings_changed)
        self.combat_detail_button.clicked.connect(self._on_edit_combat_detail)

        self.ability_detail_button.clicked.connect(self._on_edit_ability_detail)

    @staticmethod
    def _build_asset_reference_edit(
        *,
        parent: QtWidgets.QWidget,
        placeholder_text: str,
    ) -> QtWidgets.QLineEdit:
        edit = QtWidgets.QLineEdit(parent)
        edit.setPlaceholderText(placeholder_text)
        edit.setStyleSheet(ThemeManager.input_style())
        return edit

    # ------------------------------------------------------------------ Context / refresh

    def _reset_ui(self) -> None:
        self._updating_ui = True
        self._unsupported_hint.setVisible(False)

        self.level_spin.setValue(1)
        self.base_hp_spin.setValue(10.0)
        self.base_attack_spin.setValue(1.0)
        self.base_defense_spin.setValue(500.0)
        self.is_invincible_switch.setChecked(False)

        self.aggro_hint.setText("")

        self.hitbox_initial_combo.setCurrentIndex(0)

        self.immune_to_element_switch.setChecked(False)
        self.untargetable_switch.setChecked(False)
        self.tracking_point_edit.setText("")
        self.hit_vfx_edit.setText("")
        self.knockdown_vfx_edit.setText("")

        self._updating_ui = False

    def _refresh_ui(self) -> None:
        self._updating_ui = True

        supported = self._is_supported_context()
        self._unsupported_hint.setVisible(not supported)
        for widget in self._supported_widgets:
            widget.setVisible(supported)

        if not supported:
            self._updating_ui = False
            return

        battle = self._read_battle_section()

        base_stats = battle.get("base_stats", {})
        if not isinstance(base_stats, dict):
            base_stats = {}

        self.level_spin.setValue(_safe_int(base_stats.get("level"), default=1, minimum=1))
        self.base_hp_spin.setValue(_safe_float(base_stats.get("max_hp"), default=10.0, minimum=0.0))
        self.base_attack_spin.setValue(_safe_float(base_stats.get("attack"), default=1.0, minimum=0.0))
        self.base_defense_spin.setValue(_safe_float(base_stats.get("defense"), default=500.0, minimum=0.0))
        self.is_invincible_switch.setChecked(bool(base_stats.get("is_invincible", False)))

        self._refresh_aggro_hint()

        hitbox_config = battle.get("hitbox_config", {})
        if not isinstance(hitbox_config, dict):
            hitbox_config = {}
        initial_state = _safe_int(hitbox_config.get("initial_state"), default=0, minimum=0)
        hitbox_index = self.hitbox_initial_combo.findData(initial_state)
        self.hitbox_initial_combo.setCurrentIndex(hitbox_index if hitbox_index >= 0 else 0)

        combat_settings = battle.get("combat_settings", {})
        if not isinstance(combat_settings, dict):
            combat_settings = {}
        self.immune_to_element_switch.setChecked(bool(combat_settings.get("cannot_be_element_attached", False)))
        self.untargetable_switch.setChecked(bool(combat_settings.get("cannot_be_target_locked", False)))
        tracking_point = combat_settings.get("tracking_point_bone")
        self.tracking_point_edit.setText(
            str(tracking_point).strip() if isinstance(tracking_point, str) and tracking_point.strip() else "GI_RootNode"
        )

        vfx = combat_settings.get("vfx", {})
        if not isinstance(vfx, dict):
            vfx = {}
        self.hit_vfx_edit.setText(str(vfx.get("on_hit", "")).strip())
        self.knockdown_vfx_edit.setText(str(vfx.get("on_knockdown", "")).strip())

        self._apply_read_only_state()
        self._updating_ui = False

    def _apply_read_only_state(self) -> None:
        readonly = self._is_read_only
        for widget in (
            self.level_spin,
            self.base_hp_spin,
            self.base_attack_spin,
            self.base_defense_spin,
            self.is_invincible_switch,
            self.hitbox_initial_combo,
            self.hitbox_detail_button,
            self.immune_to_element_switch,
            self.untargetable_switch,
            self.tracking_point_edit,
            self.hit_vfx_edit,
            self.knockdown_vfx_edit,
            self.combat_detail_button,
            self.ability_detail_button,
        ):
            widget.setEnabled(not readonly)

    def set_read_only(self, read_only: bool) -> None:
        self._is_read_only = bool(read_only)
        self._apply_read_only_state()

    # ------------------------------------------------------------------ Model helpers

    def _is_supported_context(self) -> bool:
        """仅对物件/造物模板与实体摆放开放。"""
        obj = self.current_object
        if obj is None:
            return False
        if self.object_type == "level_entity":
            return False
        if self._is_drop_item_context():
            return False
        entity_type = ""
        if self.object_type == "template" and isinstance(obj, TemplateConfig):
            entity_type = obj.entity_type
        elif self.object_type == "instance" and isinstance(obj, InstanceConfig):
            template = self._template_for_instance(obj)
            if isinstance(template, TemplateConfig):
                entity_type = template.entity_type
            else:
                metadata = getattr(obj, "metadata", {}) or {}
                if isinstance(metadata, dict):
                    raw = metadata.get("entity_type")
                    entity_type = raw.strip() if isinstance(raw, str) else ""
        entity_type = entity_type.strip()
        return entity_type in {"物件", "造物"}

    def _read_battle_section(self) -> dict[str, Any]:
        obj = self.current_object
        if obj is None:
            return {}
        entity_config = getattr(obj, "entity_config", None)
        if not isinstance(entity_config, dict):
            return {}
        battle = entity_config.get("battle", {})
        return battle if isinstance(battle, dict) else {}

    def _write_battle_section(self) -> dict[str, Any]:
        """确保 battle 段落存在并返回可写 dict。"""
        obj = self.current_object
        if obj is None:
            raise ValueError("未设置 current_object，无法写入 battle 段落")

        entity_config = getattr(obj, "entity_config", None)
        if not isinstance(entity_config, dict):
            entity_config = {}
            setattr(obj, "entity_config", entity_config)

        return ensure_nested_dict(entity_config, "battle")

    # ------------------------------------------------------------------ Apply changes

    def _on_base_stats_changed(self, *_args: object) -> None:
        if self._updating_ui or self._is_read_only:
            return
        battle = self._write_battle_section()
        base_stats = ensure_nested_dict(battle, "base_stats")
        base_stats["level"] = int(self.level_spin.value())
        base_stats["max_hp"] = float(self.base_hp_spin.value())
        base_stats["attack"] = float(self.base_attack_spin.value())
        base_stats["defense"] = float(self.base_defense_spin.value())
        base_stats["is_invincible"] = self.is_invincible_switch.isChecked()
        self.data_changed.emit()

    def _on_hitbox_changed(self, *_args: object) -> None:
        if self._updating_ui or self._is_read_only:
            return
        battle = self._write_battle_section()
        hitbox = ensure_nested_dict(battle, "hitbox_config")
        state = self.hitbox_initial_combo.currentData()
        hitbox["initial_state"] = int(state) if isinstance(state, int) else 0
        self.data_changed.emit()

    def _on_combat_settings_changed(self, *_args: object) -> None:
        if self._updating_ui or self._is_read_only:
            return
        battle = self._write_battle_section()
        settings = ensure_nested_dict(battle, "combat_settings")

        settings["cannot_be_element_attached"] = self.immune_to_element_switch.isChecked()
        settings["cannot_be_target_locked"] = self.untargetable_switch.isChecked()

        tracking_point = self.tracking_point_edit.text().strip()
        settings["tracking_point_bone"] = tracking_point or "GI_RootNode"

        vfx = ensure_nested_dict(settings, "vfx")
        hit_vfx = self.hit_vfx_edit.text().strip()
        knockdown_vfx = self.knockdown_vfx_edit.text().strip()
        vfx["on_hit"] = hit_vfx
        vfx["on_knockdown"] = knockdown_vfx

        self.data_changed.emit()

    # ------------------------------------------------------------------ Aggro hint

    def _refresh_aggro_hint(self) -> None:
        hatred_type = ""
        package = self.current_package
        management = getattr(package, "management", None) if package is not None else None
        settings_payload = getattr(management, "level_settings", None) if management is not None else None
        if isinstance(settings_payload, dict):
            value = settings_payload.get("hatred_type", "")
            hatred_type = value.strip() if isinstance(value, str) else ""

        if hatred_type != "自定义":
            self.aggro_hint.setText(
                "在「关卡设置」中的「仇恨类型」选择「自定义」类型后可配置相关内容。"
            )
            self.aggro_hint.setStyleSheet(ThemeManager.info_label_style())
            return

        self.aggro_hint.setText("当前关卡已启用「自定义」仇恨类型（本页具体配置项待接入）。")
        self.aggro_hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; padding: 8px;")

    # ------------------------------------------------------------------ Detail buttons

    def _on_edit_hitbox_detail(self) -> None:
        show_info_dialog(self, "受击盒设置", "当前版本仅支持“初始生效”字段；受击盒形状/位置编辑器待接入。")

    def _on_edit_combat_detail(self) -> None:
        show_info_dialog(self, "战斗设置", "当前版本仅支持基础标记/追踪点/特效引用；高级战斗参数编辑器待接入。")

    def _on_edit_ability_detail(self) -> None:
        show_info_dialog(self, "能力单元", "能力单元编辑器待接入。")


def _safe_int(value: object, *, default: int, minimum: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(minimum, int(value))
    return max(minimum, int(default))


def _safe_float(value: object, *, default: float, minimum: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(minimum, float(value))
    return max(minimum, float(default))


__all__ = ["CombatTab"]


