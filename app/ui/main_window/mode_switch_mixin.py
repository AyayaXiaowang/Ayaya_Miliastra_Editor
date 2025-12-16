"""模式切换 Mixin - 负责视图模式切换和右侧面板管理。

约定：
- 模式切换的“公共步骤”仍在此处：保存当前编辑状态、切中央堆栈、应用右侧标签配置与收敛；
- 进入模式的“副作用”交由 ModePresenter 体系（`mode_presenters`）承载；
- 当前模式与关键选中上下文由 `MainWindowViewState` 作为单一真源维护。
"""
from __future__ import annotations

from app.models.view_modes import ViewMode
from app.ui.main_window.mode_presenters import ModeEnterRequest
from app.ui.main_window.mode_transition_service import ModeTransitionRequest


class ModeSwitchMixin:
    """模式切换相关方法的Mixin"""

    def _tab_title_for_id(self, tab_id: str) -> str:
        """兼容入口：根据 tab_id 返回标签标题。

        历史上部分模块会在动态插入标签时调用该方法获取标题（例如执行监控）。
        右侧标签的实际挂载/移除已统一由 `right_panel_registry` 管理，但保留该方法
        以避免跨模块导入或散落的硬编码标题。
        """
        title_map = {
            "graph_property": "图属性",
            "composite_property": "复合节点属性",
            "composite_pins": "虚拟引脚",
            "ui_settings": "界面控件设置",
            "execution_monitor": "执行监控",
            "player_editor": "玩家模板",
            "player_class_editor": "职业",
            "skill_editor": "技能",
            "item_editor": "道具",
            "validation_detail": "详细信息",
            "property": "属性",
            "management_property": "属性",
            "signal_editor": "信号",
            "struct_editor": "结构体",
            "main_camera_editor": "主镜头",
            "peripheral_system_editor": "外围系统",
            "equipment_entry_editor": "装备词条",
            "equipment_tag_editor": "装备标签",
            "equipment_type_editor": "装备类型",
        }
        return title_map.get(tab_id, tab_id)

    def _apply_right_tabs_for_mode(self, view_mode: ViewMode) -> None:
        """根据集中配置统一设置右侧标签页（不包含基础"属性"面板）。"""
        self.right_panel_registry.apply_for_mode(view_mode)

    def ensure_execution_monitor_panel_visible(self, *, visible: bool, switch_to: bool = False) -> None:
        """按需在右侧标签中挂载/移除执行监控面板。

        供任务清单/执行桥等调用，避免这些模块直接操作 `side_tab` 结构或依赖私有的可见性更新方法。
        不触发视图模式切换，只负责标签的存在性与选中状态。
        """
        self.right_panel_registry.ensure_visible("execution_monitor", visible=visible, switch_to=switch_to)

    def _update_right_panel_visibility(self) -> None:
        """根据右侧标签页数量动态显示/隐藏右侧面板"""
        self.right_panel_registry.update_visibility()

    def _enforce_right_panel_contract(self, view_mode: ViewMode) -> None:
        """强制右侧标签集与当前模式允许的集合一致，清理越权残留标签。"""
        self.right_panel_registry.enforce_contract(view_mode)

    def _switch_to_first_visible_tab(self) -> None:
        """切换到第一个可见且启用的标签"""
        self.right_panel_registry.switch_to_first_visible_tab()

    def _remove_ui_settings_tab(self) -> None:
        """移除界面控件设置标签"""
        self.right_panel_registry.ensure_visible("ui_settings", visible=False)

    def _hide_all_management_edit_pages(self, except_key: str | None = None) -> None:
        """在右侧标签中移除除 except_key 外的所有管理编辑页标签。"""
        pages = getattr(self, "management_edit_pages", None)
        if not isinstance(pages, dict):
            return

        tab_id_by_key = {
            "equipment_entries": "equipment_entry_editor",
            "equipment_tags": "equipment_tag_editor",
            "equipment_types": "equipment_type_editor",
            "peripheral_systems": "peripheral_system_editor",
            "main_cameras": "main_camera_editor",
            "signals": "signal_editor",
            "struct_definitions": "struct_editor",
        }

        for key in pages.keys():
            if key == except_key:
                continue
            tab_id = tab_id_by_key.get(key)
            if tab_id is None:
                continue
            self.right_panel_registry.ensure_visible(tab_id, visible=False)

    def _ensure_management_edit_page_for_section(self, section_key: str | None = None) -> None:
        """管理模式下为指定 section 清理旧编辑页占位，并依赖统一的列表与右侧面板体系。

        当前行为：
        - 信号、结构体与主镜头使用各自的专用右侧面板；
        - 计时器等基础管理类型使用 `ManagementPropertyPanel` 构建可编辑或只读表单；
        - 其余管理类型仅依赖中央列表与必要的对话框完成编辑，不再在右侧挂载单独管理页面。
        """
        _ = (section_key,)
        self._hide_all_management_edit_pages(None)

    def _ensure_management_property_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏管理配置通用“属性”标签（管理模式专用）。"""
        self.right_panel_registry.ensure_visible("management_property", visible=should_show)

    def _ensure_property_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏"属性"标签（模板/实例）。"""
        self.right_panel_registry.ensure_visible("property", visible=should_show)

    def _remove_property_in_other_modes(self) -> None:
        """在其他模式下移除属性面板"""
        self._ensure_property_tab_visible(False)

    def _sync_nav_highlight_for_mode(self, view_mode: ViewMode) -> None:
        """根据当前视图模式同步左侧导航高亮状态。"""
        if not hasattr(self, "nav_bar"):
            return
        nav_mode = view_mode.to_string()
        # 图编辑器没有独立导航按钮，使用“节点图库”作为高亮锚点，保持体验一致
        if view_mode == ViewMode.GRAPH_EDITOR:
            nav_mode = "graph_library"
        self.nav_bar.set_current_mode(nav_mode)

    def _switch_to_validation_and_validate(self) -> None:
        """切换到验证页面（F5快捷键）。

        实际的验证逻辑在进入验证模式时由 `_on_mode_changed` 统一触发，
        以便与通过导航栏切换到验证页面的行为保持一致。
        """
        self.nav_bar.set_current_mode("validation")
        self._on_mode_changed("validation")

    def _on_mode_changed(self, mode: str) -> None:
        """模式切换主入口：委托给 ModeTransitionService 执行公共流程。"""
        service = getattr(self, "mode_transition_service", None)
        transition = getattr(service, "transition", None)
        if callable(transition):
            transition(self, ModeTransitionRequest(mode_string=mode))
            return

        # 兼容：若服务未注入，退化为原始实现（显式抛错更利于定位初始化顺序问题）
        raise RuntimeError("ModeTransitionService 未初始化，无法切换模式")

