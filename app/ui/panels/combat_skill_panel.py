"""技能详情面板（战斗预设-技能）。

该面板在战斗预设模式下作为主窗口右侧的一个标签页，用于编辑单个“技能”预设的
详细配置字段，对应设计文档中的“技能页面”（基础设置 / 连段配置 / 数值配置 /
生命周期管理等分组）。

数据结构约定：
- 技能资源的基础字段（skill_id/skill_name/description/...）仍由战斗预设模型管理；
- 本面板的扩展配置写入技能 JSON 的 `metadata.skill_editor` 字段：
  - metadata.skill_editor.basic:   基础设置（启用坠崖保护、是否可在空中释放、技能备注）
  - metadata.skill_editor.combo:   连段配置（是否开启蓄力分支、蓄力公共前摇）
  - metadata.skill_editor.numeric: 数值配置（冷却/次数/消耗/索敌范围等）
  - metadata.skill_editor.lifecycle: 生命周期管理（次数上限与销毁策略）

面板本身只负责 UI 展示与字典读写，真正的持久化由外层 PackageController 负责，
通过 `data_changed` 信号触发立即保存。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from app.ui.foundation.theme_manager import Colors, Sizes
from app.ui.panels.combat_player_panel_sections import _GraphBindingContext
from app.ui.panels.combat_preset_editor_structs import SkillEditorStruct
from app.ui.panels.combat_skill_edit_widget import CombatSkillEditWidget
from app.ui.panels.panel_dict_utils import (
    ensure_dict_field,
    ensure_nested_dict,
    ensure_nested_list,
)
from app.ui.panels.panel_scaffold import PanelScaffold
from app.ui.panels.template_instance.graphs_tab import GraphsTab
from app.ui.panels.template_instance_service import TemplateInstanceService


PresetPackage = Union[PackageView, GlobalResourceView]
SkillGraphsContext = _GraphBindingContext


class CombatSkillPanel(PanelScaffold):
    """技能详情面板。

    - 左上方状态徽章展示当前技能名；
    - 主体采用单页 + 分组（基础设置/连段配置/数值配置/生命周期管理）布局；
    - 所有字段变更会更新技能 JSON 的 metadata.skill_editor 段并通过 data_changed
      信号通知外层立即持久化。
    """

    data_changed = QtCore.pyqtSignal()
    # 节点图被双击或通过按钮请求打开时发射，由主窗口负责实际打开图编辑器
    graph_selected = QtCore.pyqtSignal(str, dict)

    def __init__(
        self,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="技能详情",
            description="在战斗预设模式下编辑单个技能的基础设置、连段与数值配置。",
        )

        self.resource_manager: Optional[ResourceManager] = resource_manager
        self.package_index_manager: Optional[PackageIndexManager] = package_index_manager

        self.current_package: Optional[PresetPackage] = None
        self.current_skill_id: Optional[str] = None
        self.current_skill_data: Optional[Dict[str, Any]] = None
        self.skill_editor: SkillEditorStruct = SkillEditorStruct(
            basic={},
            combo={},
            numeric={},
            lifecycle={},
        )

        # 节点图上下文与服务（复用模板/实例面板中的 GraphsTab 能力）
        self._graph_service = TemplateInstanceService()
        self.skill_graphs_context: Optional[SkillGraphsContext] = None
        self.skill_graphs_tab: Optional[GraphsTab] = None

        # 主标签页：技能编辑 / 节点图
        self.main_tabs: QtWidgets.QTabWidget

        # 顶部状态徽章
        self._status_label = self.create_status_badge(
            "CombatSkillStatusBadge",
            "未选中技能",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )

        # 技能编辑页签：拆分为独立 widget，面板只负责上下文注入与信号转发
        self._edit_widget: Optional[CombatSkillEditWidget] = None

        self._build_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        """搭建“技能编辑 / 节点图”两个主标签页。"""
        self.main_tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.main_tabs, 1)

        edit_page = QtWidgets.QWidget()
        graphs_page = QtWidgets.QWidget()

        self.main_tabs.addTab(edit_page, "技能编辑")
        self.main_tabs.addTab(graphs_page, "节点图")

        self._build_edit_tab(edit_page)
        self._build_graphs_tab(graphs_page)

    def _build_edit_tab(self, page: QtWidgets.QWidget) -> None:
        """构建“技能编辑”标签页（拆分为独立 edit widget）。"""
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self._edit_widget = CombatSkillEditWidget(page)
        self._edit_widget.data_changed.connect(self._on_edit_data_changed)
        page_layout.addWidget(self._edit_widget, 1)

    def _build_graphs_tab(self, page: QtWidgets.QWidget) -> None:
        """构建“节点图”标签页，复用通用 GraphsTab。"""
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.skill_graphs_tab = GraphsTab(page, graph_data_provider=None)
        self.skill_graphs_tab.set_service(self._graph_service)
        if self.resource_manager is not None:
            self.skill_graphs_tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager is not None:
            self.skill_graphs_tab.set_package_index_manager(self.package_index_manager)

        # 技能节点图：仅允许绑定客户端节点图下“技能节点图”文件夹中的图
        # （对应 assets/资源库/项目存档/<package_id>/节点图/client/技能节点图/*）
        self.skill_graphs_tab.set_allowed_graph_scope(
            graph_type="client",
            folder_prefix="技能节点图",
        )

        self.skill_graphs_tab.data_changed.connect(self._on_skill_graphs_tab_changed)
        self.skill_graphs_tab.graph_selected.connect(self.graph_selected.emit)

        layout.addWidget(self.skill_graphs_tab)

    # ------------------------------------------------------------------ 公共接口

    def set_context(
        self,
        package: Optional[PresetPackage],
        skill_id: Optional[str],
    ) -> None:
        """设置当前技能上下文并加载字段。"""
        self.current_package = package
        self.current_skill_id = skill_id

        if not package or not skill_id:
            self.current_skill_data = None
            self.skill_editor = SkillEditorStruct(basic={}, combo={}, numeric={}, lifecycle={})
            self.skill_graphs_context = None
            if self.skill_graphs_tab is not None:
                self.skill_graphs_tab.clear()
            if self._edit_widget is not None:
                self._edit_widget.set_context(
                    skill_id=None,
                    skill_data=None,
                    skill_editor=self.skill_editor,
                )
            self.setEnabled(False)
            self._update_status_badge()
            return

        skill_map = package.combat_presets.skills
        skill_data = skill_map.get(skill_id)
        if not isinstance(skill_data, dict):
            self.current_skill_data = None
            self.skill_editor = SkillEditorStruct(basic={}, combo={}, numeric={}, lifecycle={})
            self.skill_graphs_context = None
            if self.skill_graphs_tab is not None:
                self.skill_graphs_tab.clear()
            if self._edit_widget is not None:
                self._edit_widget.set_context(
                    skill_id=None,
                    skill_data=None,
                    skill_editor=self.skill_editor,
                )
            self.setEnabled(False)
            self._update_status_badge()
            return

        self.current_skill_data = skill_data
        skill_editor_raw = ensure_nested_dict(skill_data, "metadata", "skill_editor")

        basic_section = ensure_dict_field(skill_editor_raw, "basic")
        combo_section = ensure_dict_field(skill_editor_raw, "combo")
        numeric_section = ensure_dict_field(skill_editor_raw, "numeric")
        lifecycle_section = ensure_dict_field(skill_editor_raw, "lifecycle")

        self.skill_editor = SkillEditorStruct(
            basic=basic_section,
            combo=combo_section,
            numeric=numeric_section,
            lifecycle=lifecycle_section,
        )

        # 技能级节点图上下文（metadata.skill_editor.graphs / graph_variable_overrides）
        graphs_value = ensure_nested_list(skill_data, "metadata", "skill_editor", "graphs")
        overrides_value = ensure_nested_dict(skill_data, "metadata", "skill_editor", "graph_variable_overrides")

        self.skill_graphs_context = SkillGraphsContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        if self.skill_graphs_tab is not None:
            self.skill_graphs_tab.set_context(
                self.skill_graphs_context,
                "template",
                self.current_package,
                force=True,
            )

        if self._edit_widget is not None:
            self._edit_widget.set_context(
                skill_id=self.current_skill_id,
                skill_data=self.current_skill_data,
                skill_editor=self.skill_editor,
            )
        self._update_status_badge()
        self.setEnabled(True)

    # ------------------------------------------------------------------ 内部加载 & 状态

    def _clear_ui(self) -> None:
        """清空编辑页签与节点图页签的显示状态。"""
        if self._edit_widget is not None:
            self._edit_widget.set_context(
                skill_id=None,
                skill_data=None,
                skill_editor=self.skill_editor,
            )

        self.skill_graphs_context = None
        if self.skill_graphs_tab is not None:
            self.skill_graphs_tab.clear()

    def _update_status_badge(self) -> None:
        if self._status_label is None:
            return
        if not self.current_skill_id or not self.current_skill_data:
            self._status_label.setText("未选中技能")
            self.update_status_badge_style(
                self._status_label,
                Colors.INFO_BG,
                Colors.TEXT_PRIMARY,
            )
            return
        display_name = (
            str(self.current_skill_data.get("skill_name", "")).strip()
            or self.current_skill_id
        )
        self._status_label.setText(f"技能 · {display_name}")
        self.update_status_badge_style(
            self._status_label,
            Colors.INFO_BG,
            Colors.PRIMARY,
        )

    def _on_edit_data_changed(self) -> None:
        """技能编辑页签数据变化：更新徽章并向外转发保存信号。"""
        self._update_status_badge()
        self.data_changed.emit()

    def _mark_skill_modified(self) -> None:
        if not self.current_skill_data:
            return
        self.current_skill_data["last_modified"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    # ------------------------------------------------------------------ 槽函数：节点图页签

    def _on_skill_graphs_tab_changed(self) -> None:
        """节点图标签页数据变化时写回 metadata.skill_editor.graphs 与变量覆盖。"""
        if not self.current_skill_data or not self.skill_graphs_context:
            return

        metadata = ensure_dict_field(self.current_skill_data, "metadata")
        skill_editor_raw = ensure_dict_field(metadata, "skill_editor")

        skill_editor_raw["graphs"] = self.skill_graphs_context.default_graphs
        if self.skill_graphs_context.graph_variable_overrides:
            skill_editor_raw["graph_variable_overrides"] = (
                self.skill_graphs_context.graph_variable_overrides
            )
        else:
            skill_editor_raw.pop("graph_variable_overrides", None)

        self._mark_skill_modified()
        self.data_changed.emit()


__all__ = ["CombatSkillPanel"]



