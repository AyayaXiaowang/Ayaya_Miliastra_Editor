"""主窗口导航历史（后退/前进）相关的事件处理 Mixin。"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui

from app.models.view_modes import ViewMode

from ..navigation_history import NavigationEntry


class NavigationHistoryMixin:
    """维护主窗口级导航历史并提供后退/前进回放能力。"""

    def _bootstrap_navigation_history_after_startup(self) -> None:
        """在启动完成/会话恢复之后初始化导航历史的第一条 entry。"""
        history = getattr(self, "navigation_history", None)
        if history is None:
            return

        if hasattr(self, "_navigation_history_ready"):
            self._navigation_history_ready = True
        else:
            setattr(self, "_navigation_history_ready", True)

        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode is None:
            return

        history.bootstrap(NavigationEntry(mode_string=current_mode.to_string()))
        self._update_navigation_history_actions()

    def _on_mode_transition_completed(self, view_mode: ViewMode) -> None:
        """模式切换完成后记录导航历史（供工具栏后退/前进使用）。"""
        history = getattr(self, "navigation_history", None)
        if history is None:
            return

        if not bool(getattr(self, "_navigation_history_ready", False)):
            self._update_navigation_history_actions()
            return

        if bool(getattr(self, "_navigation_history_is_replaying", False)):
            self._update_navigation_history_actions()
            return

        mode_string = view_mode.to_string()
        history.record(NavigationEntry(mode_string=mode_string))
        self._update_navigation_history_actions()

    def _update_navigation_history_actions(self) -> None:
        history = getattr(self, "navigation_history", None)
        if history is None:
            return

        back_action = getattr(self, "navigation_back_action", None)
        if isinstance(back_action, QtGui.QAction):
            back_action.setEnabled(history.can_go_back())

        forward_action = getattr(self, "navigation_forward_action", None)
        if isinstance(forward_action, QtGui.QAction):
            forward_action.setEnabled(history.can_go_forward())

    def _on_navigate_back(self) -> None:
        history = getattr(self, "navigation_history", None)
        if history is None:
            return
        entry = history.go_back()
        if entry is None:
            self._update_navigation_history_actions()
            return
        self._apply_navigation_history_entry(entry)

    def _on_navigate_forward(self) -> None:
        history = getattr(self, "navigation_history", None)
        if history is None:
            return
        entry = history.go_forward()
        if entry is None:
            self._update_navigation_history_actions()
            return
        self._apply_navigation_history_entry(entry)

    def _apply_navigation_history_entry(self, entry: NavigationEntry) -> None:
        """回放一条历史 entry：切换模式，并在需要时补齐模式内定位。"""
        if not entry.mode_string:
            return

        self._navigation_history_is_replaying = True
        try:
            self._on_mode_changed(entry.mode_string)
        finally:
            self._navigation_history_is_replaying = False

        self._apply_navigation_entry_context(entry)
        self._update_navigation_history_actions()

    def _apply_navigation_entry_context(self, entry: NavigationEntry) -> None:
        """在模式切换后应用 entry 的额外上下文（例如复合节点预览定位）。"""
        if entry.mode_string != "composite":
            return

        composite_id_value = entry.context.get("composite_id", "")
        composite_id = str(composite_id_value or "").strip()
        if not composite_id:
            return

        composite_widget = getattr(self, "composite_widget", None)
        if composite_widget is None:
            return

        select_by_id = getattr(composite_widget, "select_composite_by_id", None)
        if not callable(select_by_id):
            return

        select_by_id(composite_id)
        # 兜底：下一帧再尝试一次，避免懒加载/布局未就绪导致定位失败
        QtCore.QTimer.singleShot(0, lambda: select_by_id(composite_id))


