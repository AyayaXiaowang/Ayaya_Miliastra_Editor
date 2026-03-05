"""职业详情面板（战斗预设-职业）。

该面板在战斗预设模式下右侧显示，用于编辑单个“职业”预设的详细配置。

分为三个标签：
- 战斗：基础战斗属性、等级与经验、移动与镜头等设置（图1）
- 技能：普通攻击、主动技能与自定义按键技能（图2）
- 节点图：复用通用 GraphsTab，挂载职业相关节点图

数据结构约定：
- 职业资源基础字段由 `PlayerClassConfig` 提供（base_health/base_attack/base_defense/base_speed/skill_list）
- 该面板的扩展配置写入职业 JSON 的 `metadata.class_editor` 字段：
  - metadata.class_editor.battle: 战斗与成长相关字段
  - metadata.class_editor.skills: 技能与快捷键相关字段
  - metadata.class_editor.graphs: 职业层级挂载的节点图 ID 列表
  - metadata.class_editor.graph_variable_overrides: 节点图暴露变量覆盖
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from app.ui.foundation.theme_manager import Colors
from app.ui.panels.combat.combat_class_edit_widgets import (
    CombatClassBattleTabWidget,
    CombatClassSkillsTabWidget,
)
from app.ui.panels.combat.combat_preset_editor_structs import ClassEditorStruct
from app.ui.panels.panel_dict_utils import (
    ensure_dict_field,
    ensure_nested_dict,
    ensure_nested_list,
)
from app.ui.panels.combat.combat_player_panel_sections import _GraphBindingContext
from app.ui.panels.panel_scaffold import PanelScaffold
from app.ui.panels.template_instance.graphs_tab import GraphsTab
from app.ui.panels.template_instance_service import TemplateInstanceService


PresetPackage = Union[PackageView, GlobalResourceView]


_ClassEditorStruct = ClassEditorStruct


class CombatPlayerClassPanel(PanelScaffold):
    """职业详情面板。

    - 左上方状态徽章展示当前职业名
    - 主体为“战斗 / 技能 / 节点图”三个标签
    - 所有字段变更会更新职业 JSON 并通过 data_changed 信号通知外层立即持久化
    """

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
            title="职业详情",
            description="配置职业在战斗中的基础属性、技能与节点图。",
        )

        self.resource_manager: Optional[ResourceManager] = resource_manager
        self.package_index_manager: Optional[PackageIndexManager] = package_index_manager

        self.current_package: Optional[PresetPackage] = None
        self.current_class_id: Optional[str] = None
        self.current_class_data: Optional[Dict[str, Any]] = None
        self.class_editor: _ClassEditorStruct = _ClassEditorStruct(battle={}, skills={})

        # 顶部状态徽章
        self._status_label = self.create_status_badge(
            "CombatPlayerClassStatusBadge",
            "未选中职业",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )

        # 节点图上下文与服务
        self._graph_service = TemplateInstanceService()
        self.class_graphs_context: Optional[_GraphBindingContext] = None
        self.class_graphs_tab: Optional[GraphsTab] = None

        # 主标签页 + 拆分后的子页签组件（战斗/技能）
        self.main_tabs: QtWidgets.QTabWidget
        self._battle_tab_widget: Optional[CombatClassBattleTabWidget] = None
        self._skills_tab_widget: Optional[CombatClassSkillsTabWidget] = None

        self._build_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        self.main_tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.main_tabs, 1)

        battle_page = QtWidgets.QWidget()
        skills_page = QtWidgets.QWidget()
        graphs_page = QtWidgets.QWidget()

        self.main_tabs.addTab(battle_page, "战斗")
        self.main_tabs.addTab(skills_page, "技能")
        self.main_tabs.addTab(graphs_page, "节点图")

        battle_layout = QtWidgets.QVBoxLayout(battle_page)
        battle_layout.setContentsMargins(0, 0, 0, 0)
        battle_layout.setSpacing(0)
        self._battle_tab_widget = CombatClassBattleTabWidget(
            on_dirty=self._on_editor_dirty,
            parent=battle_page,
        )
        battle_layout.addWidget(self._battle_tab_widget, 1)

        skills_layout = QtWidgets.QVBoxLayout(skills_page)
        skills_layout.setContentsMargins(0, 0, 0, 0)
        skills_layout.setSpacing(0)
        self._skills_tab_widget = CombatClassSkillsTabWidget(
            on_dirty=self._on_editor_dirty,
            parent=skills_page,
        )
        skills_layout.addWidget(self._skills_tab_widget, 1)

        self._build_graphs_tab(graphs_page)

    def _build_graphs_tab(self, page: QtWidgets.QWidget) -> None:
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.class_graphs_tab = GraphsTab(page, graph_data_provider=None)
        self.class_graphs_tab.set_service(self._graph_service)
        if self.resource_manager is not None:
            self.class_graphs_tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager is not None:
            self.class_graphs_tab.set_package_index_manager(self.package_index_manager)
        self.class_graphs_tab.data_changed.connect(self._on_graphs_tab_changed)
        self.class_graphs_tab.graph_selected.connect(self.graph_selected.emit)

        layout.addWidget(self.class_graphs_tab)

    # ------------------------------------------------------------------ 公共接口

    def set_context(self, package: Optional[PresetPackage], class_id: Optional[str]) -> None:
        """设置当前职业上下文。"""
        self.current_package = package
        self.current_class_id = class_id

        if not package or not class_id:
            self.current_class_data = None
            self.class_editor = _ClassEditorStruct(battle={}, skills={})
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        class_map = package.combat_presets.player_classes
        class_data = class_map.get(class_id)
        if class_data is None:
            self.current_class_data = None
            self.class_editor = _ClassEditorStruct(battle={}, skills={})
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        self.current_class_data = class_data
        class_editor_raw = ensure_nested_dict(class_data, "metadata", "class_editor")
        battle_section = ensure_dict_field(class_editor_raw, "battle")
        skills_section = ensure_dict_field(class_editor_raw, "skills")

        self.class_editor = _ClassEditorStruct(battle=battle_section, skills=skills_section)

        # 兼容旧数据：如未配置 skills 段落但已有 skill_list，则默认视作主动技能列表
        if "active_skills" not in skills_section:
            raw_skill_list = class_data.get("skill_list", [])
            if isinstance(raw_skill_list, list):
                normalized_skill_ids: List[str] = []
                for raw_id in raw_skill_list:
                    if isinstance(raw_id, str) and raw_id and raw_id not in normalized_skill_ids:
                        normalized_skill_ids.append(raw_id)
                if normalized_skill_ids:
                    skills_section["active_skills"] = normalized_skill_ids

        # 节点图上下文
        graphs_value = ensure_nested_list(class_data, "metadata", "class_editor", "graphs")
        overrides_value = ensure_nested_dict(class_data, "metadata", "class_editor", "graph_variable_overrides")

        self.class_graphs_context = _GraphBindingContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        if self.class_graphs_tab is not None:
            self.class_graphs_tab.set_context(
                self.class_graphs_context,
                "template",
                self.current_package,
                force=True,
            )

        if self._battle_tab_widget is not None:
            self._battle_tab_widget.set_context(
                class_data=self.current_class_data,
                battle_section=self.class_editor.battle,
            )
        if self._skills_tab_widget is not None:
            self._skills_tab_widget.set_context(
                class_data=self.current_class_data,
                skills_section=self.class_editor.skills,
                package=self.current_package,
            )
        self._update_status_badge()
        self.setEnabled(True)

    # ------------------------------------------------------------------ 状态徽章

    def _update_status_badge(self) -> None:
        if self._status_label is None:
            return
        if not self.current_class_id or not self.current_class_data:
            self._status_label.setText("未选中职业")
            self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_PRIMARY)
            return
        name_value = self.current_class_data.get("class_name", "")
        display_name = str(name_value).strip() or self.current_class_id
        self._status_label.setText(f"职业 · {display_name}")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.PRIMARY)

    # ------------------------------------------------------------------ 清空与加载

    def _clear_ui(self) -> None:
        """清空战斗/技能子页签与节点图页签。"""
        if self._battle_tab_widget is not None:
            self._battle_tab_widget.clear()
        if self._skills_tab_widget is not None:
            self._skills_tab_widget.clear()

        self.class_graphs_context = None
        if self.class_graphs_tab is not None:
            self.class_graphs_tab.clear()

    def _on_editor_dirty(self) -> None:
        """战斗/技能页签字段变化：标记修改并向外转发保存信号。"""
        self._mark_class_modified()
        self._update_status_badge()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 修改标记

    def _mark_class_modified(self) -> None:
        if not self.current_class_data:
            return
        self.current_class_data["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------ 节点图

    def _on_graphs_tab_changed(self) -> None:
        """节点图标签页数据变化时写回 metadata.class_editor。"""
        if not self.current_class_data or not self.class_graphs_context:
            return

        metadata = ensure_dict_field(self.current_class_data, "metadata")
        class_editor_raw = ensure_dict_field(metadata, "class_editor")

        class_editor_raw["graphs"] = self.class_graphs_context.default_graphs
        if self.class_graphs_context.graph_variable_overrides:
            class_editor_raw["graph_variable_overrides"] = self.class_graphs_context.graph_variable_overrides
        else:
            class_editor_raw.pop("graph_variable_overrides", None)

        self._mark_class_modified()
        self.data_changed.emit()


__all__ = ["CombatPlayerClassPanel"]



