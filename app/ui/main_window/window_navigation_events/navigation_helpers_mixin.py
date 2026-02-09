"""导航与辅助跳转相关的事件处理 Mixin。"""

from __future__ import annotations

from app.models.view_modes import ViewMode


class NavigationHelpersMixin:
    """提供主窗口内的通用跳转/定位能力（供导航协调器与 UI 入口复用）。"""

    def _navigate_to_mode(self, mode: str) -> None:
        """导航到指定模式

        如果是图编辑器，没有对应的左侧导航按钮；为达到一致体验，左侧高亮"节点图库"。
        """
        nav_mode = mode
        if mode == "graph_editor":
            nav_mode = "graph_library"

        self.nav_bar.set_current_mode(nav_mode)
        self._on_mode_changed(mode)

    def _on_management_section_changed(self, section_key: str) -> None:
        """管理面板左侧 section 选中变化时，根据当前 section 更新右侧相关标签。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            return

        # ViewState 记录当前 section（单一真源雏形）
        view_state = getattr(self, "view_state", None)
        management_state = getattr(view_state, "management", None) if view_state is not None else None
        if management_state is not None:
            setattr(management_state, "section_key", str(section_key))

        self.right_panel.apply_management_section(section_key)

    def _open_player_editor(self) -> None:
        """打开玩家编辑器（战斗预设页签内部）"""
        # 确保战斗预设页面的“玩家模板”标签被选中
        if hasattr(self, "combat_widget") and hasattr(self.combat_widget, "switch_to_player_editor"):
            self.combat_widget.switch_to_player_editor()
        elif hasattr(self, "combat_widget") and hasattr(self.combat_widget, "tabs"):
            self.combat_widget.tabs.setCurrentIndex(0)
        # 同时将右侧面板切换到玩家模板详情标签（如已挂载）
        self.right_panel.switch_to("player_editor")


