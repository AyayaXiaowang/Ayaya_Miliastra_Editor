"""
玩家模板详情面板。

用于在战斗预设模式下展示和编辑“玩家模板”的详细配置，包括：
- 玩家编辑：基础属性等
- 角色编辑：角色列表与角色下的属性/能力/通用组件/节点图占位

实际运行时语义由上层战斗系统决定，本面板侧重结构化编辑与数据落盘。

实现上采用 PanelScaffold + Mixin 拆分结构：
- 本文件中的 CombatPlayerEditorPanel 负责上下文管理、状态徽章、
  所属存档行与模板级时间戳等高层职责；
- 具体的 UI 构建与字段读写逻辑由 `combat_player_panel_sections.CombatPlayerPanelSectionsMixin`
  提供，以降低单文件体积并保持职责清晰。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from ui.foundation.theme_manager import Colors
from ui.panels.combat_ability_components import CombatSettingsSection
from ui.panels.combat_player_panel_sections import (
    CombatPlayerPanelSectionsMixin,
    _GraphBindingContext,
    _PlayerEditorStruct,
)
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.template_instance.graphs_tab import GraphsTab
from ui.panels.template_instance_service import TemplateInstanceService
from ui.panels.package_membership_selector import PackageMembershipSelector, build_package_membership_row


PresetPackage = Union[PackageView, GlobalResourceView]


class CombatPlayerEditorPanel(PanelScaffold, CombatPlayerPanelSectionsMixin):
    """玩家模板详情面板（右侧标签页）。"""

    data_changed = QtCore.pyqtSignal()
    graph_selected = QtCore.pyqtSignal(str, dict)

    def __init__(
        self,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="玩家模板详情",
            description="配置玩家实体及其角色在战斗中的预设数据。",
        )
        self.resource_manager: Optional[ResourceManager] = resource_manager
        self.package_index_manager: Optional[PackageIndexManager] = package_index_manager
        self.current_package: Optional[PresetPackage] = None
        self.current_template_id: Optional[str] = None
        self.current_template_data: Optional[Dict[str, Any]] = None
        self.player_editor: _PlayerEditorStruct = _PlayerEditorStruct(player={}, role={})

        # 顶部状态徽章与所属存档行
        self._status_label = self.create_status_badge(
            "CombatPlayerStatusBadge",
            "未选中玩家模板",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )
        self._package_membership_widget: Optional[QtWidgets.QWidget] = None
        self.package_selector: Optional[PackageMembershipSelector] = None

        # 节点图相关上下文与服务（复用元件/实例面板的 GraphsTab 实现）
        self._graph_service = TemplateInstanceService()
        self.player_graphs_context: Optional[_GraphBindingContext] = None
        self.role_graphs_context: Optional[_GraphBindingContext] = None
        self.player_graphs_tab: Optional[GraphsTab] = None
        self.role_graphs_tab: Optional[GraphsTab] = None
        self.role_combat_settings_section: Optional[CombatSettingsSection] = None

        self._build_package_membership_row()
        self._build_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        self.main_tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.main_tabs, 1)

        # 顶层：玩家编辑 / 角色编辑
        self.player_edit_page = QtWidgets.QWidget()
        self.role_edit_page = QtWidgets.QWidget()
        self.main_tabs.addTab(self.player_edit_page, "玩家编辑")
        self.main_tabs.addTab(self.role_edit_page, "角色编辑")

        self._build_player_edit_ui()
        self._build_role_edit_ui()
    def _build_package_membership_row(self) -> None:
        """在状态徽章下方构建全局的“所属存档”行。"""
        (
            self._package_membership_widget,
            _label_widget,
            self.package_selector,
        ) = build_package_membership_row(
            self.body_layout,
            self,
            self._on_package_membership_changed,
        )
        self._set_package_membership_visible(False)

    def _set_package_membership_visible(self, visible: bool) -> None:
        if self._package_membership_widget is not None:
            self._package_membership_widget.setVisible(visible)
        if self.package_selector is not None:
            self.package_selector.setEnabled(visible)


    # ------------------------------------------------------------------ 上下文管理

    def set_context(self, package: Optional[PresetPackage], template_id: Optional[str]) -> None:
        """设置当前玩家模板上下文。"""
        self.current_package = package
        self.current_template_id = template_id

        if not package or not template_id:
            self.current_template_data = None
            self.player_editor = _PlayerEditorStruct(player={}, role={})
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            self._clear_package_membership_ui()
            return

        template_map = package.combat_presets.player_templates
        template_data = template_map.get(template_id)
        if template_data is None:
            self.current_template_data = None
            self.player_editor = _PlayerEditorStruct(player={}, role={})
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            self._clear_package_membership_ui()
            return

        self.current_template_data = template_data
        metadata = template_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            template_data["metadata"] = metadata

        player_editor_raw = metadata.get("player_editor")
        if not isinstance(player_editor_raw, dict):
            player_editor_raw = {"player": {}, "role": {}}
            metadata["player_editor"] = player_editor_raw

        player_section = player_editor_raw.get("player")
        if not isinstance(player_section, dict):
            player_section = {}
            player_editor_raw["player"] = player_section
        role_section = player_editor_raw.get("role")
        if not isinstance(role_section, dict):
            role_section = {}
            player_editor_raw["role"] = role_section

        self.player_editor = _PlayerEditorStruct(player=player_section, role=role_section)

        # 为玩家/角色构建节点图上下文，并同步到 GraphsTab
        self._setup_player_graphs_context()
        self._setup_role_graphs_context()

        self._load_player_fields()
        self._load_role_fields()
        self._update_status_badge()
        self._update_package_membership_ui()
        self.setEnabled(True)

    def _update_status_badge(self) -> None:
        """根据当前玩家模板刷新状态徽章文本与颜色。"""
        if self._status_label is None:
            return
        if not self.current_template_id or not self.current_template_data:
            self._status_label.setText("未选中玩家模板")
            self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_PRIMARY)
            return
        name = str(self.current_template_data.get("template_name", "")).strip() or self.current_template_id
        self._status_label.setText(f"玩家模板 · {name}")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.PRIMARY)

    # ------------------------------------------------------------------ 所属存档（玩家模板） ---------------------------------------------

    def _clear_package_membership_ui(self) -> None:
        if self.package_selector is not None:
            self.package_selector.clear_membership()
        self._set_package_membership_visible(False)

    def _update_package_membership_ui(self) -> None:
        """根据 PackageIndex 刷新玩家模板的所属存档多选下拉。"""
        manager = self.package_index_manager
        selector = self.package_selector
        template_id = self.current_template_id

        if manager is None or selector is None or not template_id:
            self._clear_package_membership_ui()
            return

        packages = manager.list_packages()
        if not packages:
            self._clear_package_membership_ui()
            return

        membership: set[str] = set()
        for package_info in packages:
            package_id_value = package_info.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_id = package_id_value
            resources = manager.get_package_resources(package_id)
            if not resources:
                continue
            preset_ids = resources.combat_presets.get("player_templates", [])
            if isinstance(preset_ids, list) and template_id in preset_ids:
                membership.add(package_id)

        selector.set_packages(packages)
        selector.set_membership(membership)
        self._set_package_membership_visible(True)

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """所属存档复选变化：写回 PackageIndex.combat_presets.player_templates。"""
        manager = self.package_index_manager
        template_id = self.current_template_id
        if manager is None or not package_id or not template_id:
            return

        if is_checked:
            manager.add_resource_to_package(
                package_id,
                "combat_player_templates",
                template_id,
            )
        else:
            manager.remove_resource_from_package(
                package_id,
                "combat_player_templates",
                template_id,
            )

        # 若当前上下文是具体存档视图，刷新其战斗预设缓存，确保列表立即反映归属变化
        current_pkg = self.current_package
        if hasattr(current_pkg, "_combat_presets_cache"):
            setattr(current_pkg, "_combat_presets_cache", None)

    # ------------------------------------------------------------------ 玩家编辑数据加载/写回

    def _mark_template_modified(self) -> None:
        if not self.current_template_data:
            return
        self.current_template_data["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
