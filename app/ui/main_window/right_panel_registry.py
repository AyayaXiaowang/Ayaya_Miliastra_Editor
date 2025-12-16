"""右侧标签面板注册表。

目标：
- 将“tab_id -> widget -> title -> 可见性/模式约束”的规则集中管理；
- 模式切换时只做一次“静态标签 diff + 动态标签越权回收”，避免在多个 if/elif 中散落 addTab/removeTab；
- 让上层只表达意图（某个 tab 需要显示/隐藏、模式切换后应用配置），不直接操作 QTabWidget 细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PyQt6 import QtWidgets

from app.models.view_modes import ViewMode, RIGHT_PANEL_TABS


@dataclass(frozen=True)
class RightPanelTabSpec:
    tab_id: str
    widget: QtWidgets.QWidget
    title: str
    is_dynamic: bool
    allowed_modes: set[ViewMode] | None = None


class RightPanelRegistry:
    """统一管理主窗口右侧 QTabWidget 的标签挂载/移除与收敛。"""

    def __init__(
        self,
        *,
        side_tab: QtWidgets.QTabWidget,
        right_panel_container: QtWidgets.QWidget,
    ) -> None:
        self._side_tab = side_tab
        self._right_panel_container = right_panel_container
        self._specs: dict[str, RightPanelTabSpec] = {}

    # ===== 注册 =====

    def register_static(self, tab_id: str, widget: QtWidgets.QWidget, title: str) -> None:
        self._register(
            RightPanelTabSpec(
                tab_id=tab_id,
                widget=widget,
                title=title,
                is_dynamic=False,
                allowed_modes=None,
            )
        )

    def register_dynamic(
        self,
        tab_id: str,
        widget: QtWidgets.QWidget,
        title: str,
        *,
        allowed_modes: Iterable[ViewMode] | None,
    ) -> None:
        allowed_set = set(allowed_modes) if allowed_modes is not None else None
        self._register(
            RightPanelTabSpec(
                tab_id=tab_id,
                widget=widget,
                title=title,
                is_dynamic=True,
                allowed_modes=allowed_set,
            )
        )

    def _register(self, spec: RightPanelTabSpec) -> None:
        if not isinstance(spec.tab_id, str) or not spec.tab_id:
            raise ValueError("tab_id 不能为空")
        self._specs[spec.tab_id] = spec

    # ===== 基础操作 =====

    def ensure_visible(self, tab_id: str, *, visible: bool, switch_to: bool = False) -> None:
        spec = self._specs.get(tab_id)
        if spec is None:
            raise KeyError(f"未注册的右侧标签: {tab_id!r}")

        panel = spec.widget
        index = self._side_tab.indexOf(panel)
        if visible:
            if index == -1:
                self._side_tab.addTab(panel, spec.title)
            if switch_to:
                self._side_tab.setCurrentWidget(panel)
        else:
            if index != -1:
                if self._side_tab.currentWidget() is panel and self._side_tab.count() > 1:
                    self._side_tab.setCurrentIndex(0)
                self._side_tab.removeTab(index)

        self.update_visibility()

    def switch_to(self, tab_id: str) -> None:
        spec = self._specs.get(tab_id)
        if spec is None:
            raise KeyError(f"未注册的右侧标签: {tab_id!r}")
        panel = spec.widget
        if self._side_tab.indexOf(panel) != -1:
            self._side_tab.setCurrentWidget(panel)

    # ===== 模式应用与收敛 =====

    def apply_for_mode(self, view_mode: ViewMode) -> None:
        """按 `RIGHT_PANEL_TABS` 应用静态标签，并回收当前模式不允许保留的动态标签。"""
        desired_static = set(RIGHT_PANEL_TABS.get(view_mode, tuple()))

        for tab_id, spec in self._specs.items():
            if not spec.is_dynamic:
                self.ensure_visible(tab_id, visible=(tab_id in desired_static))
                continue

            # 动态标签：仅做“越权回收”，不负责“默认显示”
            if spec.allowed_modes is not None and view_mode not in spec.allowed_modes:
                self.ensure_visible(tab_id, visible=False)

        self.update_visibility()

    def enforce_contract(self, view_mode: ViewMode) -> None:
        """强制收敛右侧标签集，仅保留当前模式允许集合内的标签。"""
        desired_static = set(RIGHT_PANEL_TABS.get(view_mode, tuple()))
        allowed_dynamic: set[str] = set()
        for tab_id, spec in self._specs.items():
            if not spec.is_dynamic:
                continue
            if spec.allowed_modes is None or view_mode in spec.allowed_modes:
                allowed_dynamic.add(tab_id)
        allowed = desired_static | allowed_dynamic

        for index in range(self._side_tab.count() - 1, -1, -1):
            widget = self._side_tab.widget(index)
            tab_id = self._find_tab_id_by_widget(widget)
            if tab_id is None:
                continue
            if tab_id not in allowed:
                if self._side_tab.currentWidget() is widget and self._side_tab.count() > 1:
                    self._side_tab.setCurrentIndex(0)
                self._side_tab.removeTab(index)

        self.update_visibility()

    def _find_tab_id_by_widget(self, widget: QtWidgets.QWidget) -> str | None:
        for tab_id, spec in self._specs.items():
            if spec.widget is widget:
                return tab_id
        return None

    # ===== UI 细节 =====

    def switch_to_first_visible_tab(self) -> None:
        current_widget = self._side_tab.currentWidget()
        if current_widget and current_widget.isVisible() and current_widget.isEnabled():
            return

        for index in range(self._side_tab.count()):
            widget = self._side_tab.widget(index)
            if widget and widget.isVisible() and widget.isEnabled():
                self._side_tab.setCurrentIndex(index)
                return

    def update_visibility(self) -> None:
        if self._side_tab.count() == 0:
            self._right_panel_container.hide()
        else:
            self._right_panel_container.show()


