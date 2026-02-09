"""右侧面板对外唯一入口：RightPanelController。

目标：
- 让业务代码只依赖 `main_window.right_panel`，而不是同时操作 registry/policy；
- 把“tab 显隐/模式收敛/管理 section 策略/战斗详情策略”等集中到一个可查入口，
  避免出现多处同时维护同一套 UI 合同导致漂移。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.view_modes import ViewMode
from app.ui.main_window.right_panel_contracts import RightPanelVisibilityContract
from app.ui.main_window.right_panel_policy import RightPanelPolicy
from app.ui.main_window.right_panel_registry import RightPanelRegistry


@dataclass(slots=True)
class RightPanelController:
    """主窗口右侧面板控制器（Facade/单一入口）。"""

    registry: RightPanelRegistry
    policy: RightPanelPolicy

    # === registry passthrough（保持调用面最小） ==================================

    def ensure_visible(self, tab_id: str, *, visible: bool, switch_to: bool = False) -> None:
        self.registry.ensure_visible(tab_id, visible=visible, switch_to=switch_to)

    def get_widget(self, tab_id: str):
        return self.registry.get_widget(tab_id)

    def switch_to(self, tab_id: str) -> None:
        self.registry.switch_to(tab_id)

    def apply_for_mode(self, view_mode: ViewMode) -> None:
        self.registry.apply_for_mode(view_mode)

    def enforce_contract(self, view_mode: ViewMode) -> None:
        self.registry.enforce_contract(view_mode)

    def switch_to_first_visible_tab(self) -> None:
        self.registry.switch_to_first_visible_tab()

    def update_visibility(self) -> None:
        self.registry.update_visibility()

    def apply_visibility_contract(self, contract: RightPanelVisibilityContract) -> None:
        """统一入口：按可见性合同收敛右侧 tab 集合。"""
        self.registry.apply_visibility_contract(contract)

    # === 高阶策略（统一入口） =====================================================

    def prepare_for_mode_enter(self, view_mode: ViewMode) -> None:
        """进入模式前的统一“右侧面板默认态”收敛。

        约定：
        - 右侧面板的“允许存在集合”由 `apply_for_mode/enforce_contract` 解决；
        - 右侧面板的“默认是否可见”（即：即使允许也不一定默认展示）在这里集中处理，
          避免在 presenter/mixin 里重复写 hide 分支导致漂移。
        """
        _ = view_mode
        # 这些 tab 允许在少数模式下动态出现，但默认都应是隐藏态：
        self.registry.ensure_visible("property", visible=False)
        self.registry.ensure_visible("management_property", visible=False)
        self.registry.ensure_visible("ui_settings", visible=False)
        self.registry.ensure_visible("execution_monitor", visible=False)
        # 战斗预设详情页签全部默认隐藏（由选中上下文驱动）
        self.policy.reset_combat_detail_tabs()

    def set_tab_visible(self, tab_id: str, *, visible: bool, switch_to: bool = False) -> None:
        """统一的 tab 显隐入口（默认委托 policy，便于未来扩展）。"""
        self.policy.set_tab_visible(tab_id, visible=visible, switch_to=switch_to)

    def apply_management_section(self, section_key: str | None) -> None:
        self.policy.apply_management_section(section_key)

    def apply_management_selection(self, section_key: str | None, *, has_selection: bool) -> None:
        self.policy.apply_management_selection(section_key, has_selection=has_selection)

    def set_combat_detail_tabs_visible(
        self,
        *,
        player_template: bool = False,
        player_class: bool = False,
        skill: bool = False,
        item: bool = False,
    ) -> None:
        self.policy.set_combat_detail_tabs_visible(
            player_template=player_template,
            player_class=player_class,
            skill=skill,
            item=item,
        )

    def reset_combat_detail_tabs(self) -> None:
        self.policy.reset_combat_detail_tabs()


def build_right_panel_controller(*, main_window: Any, registry: RightPanelRegistry) -> RightPanelController:
    """工厂：由主窗口装配层创建 RightPanelController，并保证 policy 依赖正确的真源。"""
    policy = RightPanelPolicy(main_window)
    return RightPanelController(registry=registry, policy=policy)


