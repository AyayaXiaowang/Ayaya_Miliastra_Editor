"""导航切换、窗口状态与验证相关的事件处理 Mixin"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui

from ui.foundation.toast_notification import ToastNotification
from ui.dialogs.settings_dialog import SettingsDialog
from app.models.view_modes import ViewMode
from engine.validate.comprehensive_validator import ComprehensiveValidator


class WindowAndNavigationEventsMixin:
    """负责导航切换、窗口标题/保存状态、验证与设置等通用事件处理逻辑。"""

    # === 窗口标题与状态 ===

    def _update_window_title(self, title: str) -> None:
        """更新窗口标题"""
        from ui.main_window.main_window import APP_TITLE

        self.setWindowTitle(f"{APP_TITLE} - {title}")

    def _refresh_save_status_label_for_mode(self, view_mode: ViewMode) -> None:
        """根据当前视图模式刷新右上角保存状态提示文案。"""
        if not hasattr(self, "save_status_label"):
            return

        # 节点图库 / 复合节点页面：固定提示为只读
        if view_mode in (ViewMode.GRAPH_LIBRARY, ViewMode.COMPOSITE):
            self.save_status_label.setText("当前页面不允许修改")
            self.save_status_label.setProperty("status", "readonly")
            self.save_status_label.style().unpolish(self.save_status_label)
            self.save_status_label.style().polish(self.save_status_label)
            return

        # 其他模式：根据最近一次保存状态恢复提示文案
        last_status = getattr(self, "_last_save_status", "saved")
        status_text_map = {
            "saved": "✓ 已保存",
            "unsaved": "● 未保存",
            "saving": "⟳ 保存中...",
        }
        self.save_status_label.setText(status_text_map.get(last_status, "已保存"))
        self.save_status_label.setProperty("status", last_status)
        self.save_status_label.style().unpolish(self.save_status_label)
        self.save_status_label.style().polish(self.save_status_label)

    def _on_save_status_changed(self, status: str) -> None:
        """保存状态改变"""
        # 记录最近一次保存状态，便于离开只读页面后恢复提示
        self._last_save_status = status

        if not hasattr(self, "save_status_label"):
            return

        current_mode = None
        if hasattr(self, "central_stack"):
            current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode in (ViewMode.GRAPH_LIBRARY, ViewMode.COMPOSITE):
            # 在节点图库与复合节点模式下，始终显示“当前页面不允许修改”
            self._refresh_save_status_label_for_mode(current_mode)
            return

        status_text_map = {
            "saved": "✓ 已保存",
            "unsaved": "● 未保存",
            "saving": "⟳ 保存中...",
        }
        self.save_status_label.setText(status_text_map.get(status, "已保存"))
        self.save_status_label.setProperty("status", status)
        self.save_status_label.style().unpolish(self.save_status_label)
        self.save_status_label.style().polish(self.save_status_label)

    # === 全局 Toast 通知 ===

    def _show_toast(self, message: str, toast_type: str) -> None:
        """显示 Toast 通知"""
        ToastNotification.show_message(self, message, toast_type)

    # === 导航与辅助跳转 ===

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
        if hasattr(self, "_update_ui_settings_tab_for_management"):
            self._update_ui_settings_tab_for_management(section_key)
        if hasattr(self, "_ensure_signal_editor_tab_for_management"):
            self._ensure_signal_editor_tab_for_management(section_key)
        if hasattr(self, "_ensure_struct_editor_tab_for_management"):
            self._ensure_struct_editor_tab_for_management(section_key)
        if hasattr(self, "_ensure_main_camera_editor_tab_for_management"):
            self._ensure_main_camera_editor_tab_for_management(section_key)
        if hasattr(self, "_ensure_peripheral_system_editor_tab_for_management"):
            self._ensure_peripheral_system_editor_tab_for_management(section_key)

    def _open_player_editor(self) -> None:
        """打开玩家编辑器（战斗预设页签内部）"""
        # 确保战斗预设页面的“玩家模板”标签被选中
        if hasattr(self, "combat_widget") and hasattr(self.combat_widget, "switch_to_player_editor"):
            self.combat_widget.switch_to_player_editor()
        elif hasattr(self, "combat_widget") and hasattr(self.combat_widget, "tabs"):
            self.combat_widget.tabs.setCurrentIndex(0)
        # 同时将右侧面板切换到玩家模板详情标签（如已挂载）
        if hasattr(self, "side_tab") and hasattr(self, "player_editor_panel"):
            idx = self.side_tab.indexOf(self.player_editor_panel)
            if idx != -1:
                self.side_tab.setCurrentIndex(idx)

    # === 验证与设置 ===

    def _trigger_validation(self) -> None:
        """触发当前存档的验证流程"""
        package = self.package_controller.current_package
        if not package:
            self.validation_panel.clear()
            return

        validator = ComprehensiveValidator(package, self.resource_manager, verbose=False)
        issues = validator.validate_all()
        self.validation_panel.update_issues(issues)

    def _open_settings_dialog(self) -> None:
        """打开设置对话框并在需要时刷新任务清单"""
        dialog = SettingsDialog(self)
        dialog.exec()

        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode == ViewMode.TODO:
            self._refresh_todo_list()
            self._show_toast("已根据新设置刷新任务清单", "success")

    # === 窗口关闭 ===

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """窗口关闭事件"""
        self.file_watcher_manager.cleanup()
        self.package_controller.save_package()

        from engine.configs.settings import settings

        settings.save()
        event.accept()


