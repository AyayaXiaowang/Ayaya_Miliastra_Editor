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
from app.ui.main_window.right_panel_contracts import RightPanelVisibilityContract


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

    def get_widget(self, tab_id: str) -> QtWidgets.QWidget:
        """获取已注册 tab_id 对应的面板 widget（不隐式改变可见性）。"""
        spec = self._specs.get(tab_id)
        if spec is None:
            raise KeyError(f"未注册的右侧标签: {tab_id!r}")
        return spec.widget

    def switch_to(self, tab_id: str) -> None:
        spec = self._specs.get(tab_id)
        if spec is None:
            raise KeyError(f"未注册的右侧标签: {tab_id!r}")
        panel = spec.widget
        if self._side_tab.indexOf(panel) != -1:
            self._side_tab.setCurrentWidget(panel)

    def apply_visibility_contract(self, contract: RightPanelVisibilityContract) -> None:
        """按合同一次性收敛右侧标签集：只保留 contract.keep_tab_ids，其余全部移除。

        约定：
        - keep_tab_ids 决定“允许存在”的集合；
        - ensure_tab_ids 决定“必须显示”的集合（会按需插入）；
        - preferred_tab_id 若可见，则 apply 后切换到它。

        该方法用于将“收起别人的，展示自己的”行为配置化，避免散落在各事件入口里写
        多处 ensure_visible(False)/removeTab 的互斥逻辑。
        """
        keep_set = {tab_id for tab_id in contract.keep_tab_ids if isinstance(tab_id, str) and tab_id}
        ensure_set = {tab_id for tab_id in contract.ensure_tab_ids if isinstance(tab_id, str) and tab_id}
        preferred_tab_id = (
            str(contract.preferred_tab_id)
            if isinstance(contract.preferred_tab_id, str) and contract.preferred_tab_id
            else None
        )

        if not ensure_set.issubset(keep_set):
            raise ValueError("RightPanelVisibilityContract.ensure_tab_ids 必须是 keep_tab_ids 的子集")

        if preferred_tab_id is not None and preferred_tab_id not in keep_set:
            raise ValueError("RightPanelVisibilityContract.preferred_tab_id 必须在 keep_tab_ids 中")

        # 校验 tab_id 均已注册（尽早暴露配置错误）
        for tab_id in keep_set | ensure_set:
            if tab_id not in self._specs:
                raise KeyError(f"未注册的右侧标签: {tab_id!r}")

        # 1) 先移除所有不在 keep 中的已可见标签（从后往前删除，避免 index 漂移）
        for index in range(self._side_tab.count() - 1, -1, -1):
            widget = self._side_tab.widget(index)
            visible_tab_id = self._find_tab_id_by_widget(widget)
            if visible_tab_id is None:
                continue
            if visible_tab_id in keep_set:
                continue
            if self._side_tab.currentWidget() is widget and self._side_tab.count() > 1:
                self._side_tab.setCurrentIndex(0)
            self._side_tab.removeTab(index)

        # 2) 再确保 ensure 中的标签全部存在
        for tab_id in contract.ensure_tab_ids:
            if not isinstance(tab_id, str) or not tab_id:
                continue
            spec = self._specs.get(tab_id)
            if spec is None:
                raise KeyError(f"未注册的右侧标签: {tab_id!r}")
            if self._side_tab.indexOf(spec.widget) == -1:
                self._side_tab.addTab(spec.widget, spec.title)

        # 3) 最后按需切换到 preferred 标签（若可见）
        if preferred_tab_id is not None:
            preferred_spec = self._specs.get(preferred_tab_id)
            if preferred_spec is not None and self._side_tab.indexOf(preferred_spec.widget) != -1:
                self._side_tab.setCurrentWidget(preferred_spec.widget)

        self.update_visibility()

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


