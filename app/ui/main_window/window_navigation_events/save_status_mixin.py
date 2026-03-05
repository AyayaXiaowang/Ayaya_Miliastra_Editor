"""窗口标题与保存状态相关的事件处理 Mixin。"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from app.models.view_modes import ViewMode
from app.ui.foundation.toast_notification import ToastNotification


class SaveStatusMixin:
    """负责窗口标题与右上角保存状态标签的刷新与保存入口封装。"""

    def _apply_save_status_label(self, *, status: str, text: str) -> None:
        """统一设置右上角保存状态标签的文案与样式状态。"""
        if not hasattr(self, "save_status_label"):
            return
        self.save_status_label.setText(text)
        self.save_status_label.setProperty("status", status)
        self.save_status_label.style().unpolish(self.save_status_label)
        self.save_status_label.style().polish(self.save_status_label)

    def _get_current_right_panel_widget(self) -> Optional[QtWidgets.QWidget]:
        side_tab = getattr(self, "side_tab", None)
        if isinstance(side_tab, QtWidgets.QTabWidget):
            current = side_tab.currentWidget()
            if isinstance(current, QtWidgets.QWidget):
                return current
        return None

    def _update_window_title(self, title: str) -> None:
        """更新窗口标题"""
        from app.ui.main_window.main_window import APP_TITLE

        self.setWindowTitle(f"{APP_TITLE} - {title}")

    def _refresh_save_status_label_for_mode(self, view_mode: ViewMode) -> None:
        """根据当前视图模式刷新右上角保存状态提示文案。"""
        if not hasattr(self, "save_status_label"):
            return

        # 统一只读/不可保存提示文案（用于禁用编辑或禁止保存的页面）
        readonly_text = "当前页面不允许修改（不保存）"

        # 节点图库页面：固定提示为只读
        if view_mode == ViewMode.GRAPH_LIBRARY:
            self._apply_save_status_label(status="readonly", text=readonly_text)
            return

        # 验证页面：固定提示为只读（仅查看结果与触发校验，不产生可保存修改）
        if view_mode == ViewMode.VALIDATION:
            self._apply_save_status_label(status="readonly", text=readonly_text)
            return

        # 复合节点页面：根据页面能力显示
        if view_mode == ViewMode.COMPOSITE:
            composite_widget = getattr(self, "composite_widget", None)
            can_persist = bool(getattr(composite_widget, "can_persist_composite", False))
            if can_persist:
                self._apply_save_status_label(status="saved", text="复合节点：允许保存")
            else:
                self._apply_save_status_label(status="readonly", text="复合节点：预览（不保存）")
            return

        # 右侧面板只读页签（在同一 view_mode 内可能动态出现/切换）：
        # - 管理面板下的信号/结构体详情为代码级只读视图
        # - 任务清单下的属性面板为只读预览视图
        current_right_panel = self._get_current_right_panel_widget()
        signal_panel = getattr(self, "signal_management_panel", None)
        struct_panel = getattr(self, "struct_definition_panel", None)
        property_panel = getattr(self, "property_panel", None)

        if current_right_panel is not None and current_right_panel is signal_panel:
            self._apply_save_status_label(status="readonly", text=readonly_text)
            return
        if current_right_panel is not None and current_right_panel is struct_panel:
            self._apply_save_status_label(status="readonly", text=readonly_text)
            return

        if current_right_panel is not None and current_right_panel is property_panel:
            # TemplateInstancePanel 内部以 `_read_only` 作为只读真源
            is_property_panel_read_only = bool(getattr(property_panel, "_read_only", False))
            if is_property_panel_read_only:
                self._apply_save_status_label(status="readonly", text=readonly_text)
                return

        # 其他模式：根据最近一次保存状态恢复提示文案
        last_status = getattr(self, "_last_save_status", "saved")
        status_text_map = {
            "saved": "✓ 已保存",
            "unsaved": "● 未保存",
            "saving": "⟳ 保存中...",
            "readonly": "只读（不保存）",
        }
        self._apply_save_status_label(
            status=last_status,
            text=status_text_map.get(last_status, "✓ 已保存"),
        )

    def _set_last_save_status(self, status: str) -> None:
        """设置最近一次保存状态并刷新右上角状态标签（不附带图编辑器的脏标记副作用）。"""
        normalized = str(status or "").strip() or "saved"
        self._last_save_status = normalized

        if not hasattr(self, "save_status_label"):
            return

        current_mode = None
        if hasattr(self, "central_stack"):
            current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode is None:
            status_text_map = {
                "saved": "✓ 已保存",
                "unsaved": "● 未保存",
                "saving": "⟳ 保存中...",
                "readonly": "只读（不保存）",
            }
            self._apply_save_status_label(
                status=normalized,
                text=status_text_map.get(normalized, "✓ 已保存"),
            )
            return

        self._refresh_save_status_label_for_mode(current_mode)

    def _on_right_panel_tab_changed(self, _index: int) -> None:
        """右侧标签页切换时刷新保存状态标签。

        目的：当同一 view_mode 内切换到“只读/不可保存”的页签时，右上角提示需即时更新，
        避免残留“已保存”造成误导。
        """
        if not hasattr(self, "central_stack"):
            return
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode is None:
            return
        self._refresh_save_status_label_for_mode(current_mode)

    def _on_save_status_changed(self, status: str) -> None:
        """保存状态改变"""
        controller = getattr(self, "package_controller", None)
        if controller is not None:
            if status == "unsaved" and hasattr(controller, "mark_graph_dirty"):
                controller.mark_graph_dirty()
            elif status in ("saved", "readonly") and hasattr(controller, "clear_graph_dirty"):
                controller.clear_graph_dirty()
        self._set_last_save_status(status)

    def _on_save_requested_from_toolbar(self) -> None:
        """工具栏“保存”入口：提供清晰的保存反馈并更新状态标签。"""
        package_controller = getattr(self, "package_controller", None)
        if package_controller is None:
            return

        has_unsaved = False
        has_unsaved_method = getattr(package_controller, "has_unsaved_changes", None)
        if callable(has_unsaved_method):
            has_unsaved = bool(has_unsaved_method())
        else:
            dirty_state = getattr(package_controller, "dirty_state", None)
            has_unsaved = bool(getattr(dirty_state, "is_empty", lambda: True)() is False)

        if not has_unsaved:
            self._set_last_save_status("saved")
            ToastNotification.show_message(self, "没有需要保存的更改。", "info")
            return

        self._set_last_save_status("saving")
        if hasattr(package_controller, "save_now"):
            package_controller.save_now()
        else:
            package_controller.save_package()
        self._set_last_save_status("saved")
        ToastNotification.show_message(self, "已保存。", "success")


