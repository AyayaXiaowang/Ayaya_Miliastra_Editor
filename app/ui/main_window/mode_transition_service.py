"""模式切换服务：集中封装主窗口模式切换的公共步骤与顺序约束。

目标：
- 让 `ModeSwitchMixin` 只保留最薄的一层事件入口，减少多人协作冲突点；
- 把“保存/切堆栈/调用 presenter/右侧收敛/会话保存”等顺序依赖集中到可复用服务。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.view_modes import ViewMode
from app.ui.main_window.mode_presenters import ModeEnterRequest


@dataclass(slots=True)
class ModeTransitionRequest:
    mode_string: str


class ModeTransitionService:
    """封装主窗口模式切换公共流程。"""

    def transition(self, main_window: Any, request: ModeTransitionRequest) -> None:
        mode = request.mode_string

        print(f"\n[模式切换] 从当前模式切换到: {mode}")
        print(f"[模式切换] current_graph_id: {main_window.graph_controller.current_graph_id}")
        print(f"[模式切换] current_graph_container: {main_window.graph_controller.current_graph_container}")

        current_mode = ViewMode.from_index(main_window.central_stack.currentIndex())
        print(f"[模式切换] 当前模式: {current_mode}")

        # 1) 离开复合节点：保存当前复合节点
        if current_mode == ViewMode.COMPOSITE:
            composite_mgr = getattr(main_window, "composite_widget", None)
            current_comp_id = (
                getattr(composite_mgr, "current_composite_id", None) if composite_mgr else None
            )
            if current_comp_id:
                print(f"[模式切换] 保存复合节点: {current_comp_id}")
                composite_mgr._save_current_composite()

        # 2) 离开节点图编辑：如有脏则保存
        if main_window.graph_controller.current_graph_id:
            if main_window.graph_controller.is_dirty:
                print("[模式切换] 检测到未保存修改，触发保存节点图...")
                main_window.graph_controller.save_current_graph()
            else:
                print("[模式切换] 节点图无修改，跳过保存")
        else:
            print("[模式切换] 跳过保存（无current_graph_id）")

        # 3) 解析目标模式
        view_mode = ViewMode.from_string(mode)
        if view_mode is None:
            print(f"[模式切换] 警告：未知模式 {mode}")
            return

        # 4) ViewState 记录模式切换（单一真源）
        view_state = getattr(main_window, "view_state", None)
        set_mode = getattr(view_state, "set_mode", None)
        if callable(set_mode):
            set_mode(current=view_mode, previous=current_mode or view_mode)

        # 5) 同步左侧导航高亮
        main_window._sync_nav_highlight_for_mode(view_mode)

        # 6) 切换中央堆栈
        main_window.central_stack.setCurrentIndex(view_mode.value)

        # 7) 调整左右分割器比例（TODO 模式特殊）
        if hasattr(main_window, "main_splitter"):
            if view_mode == ViewMode.TODO:
                main_window.main_splitter.setSizes([1600, 400])
            else:
                main_window.main_splitter.setSizes([1200, 800])

        # 8) 进入模式副作用（presenter）
        previous_mode = current_mode or view_mode
        preferred_tab_id = None
        coordinator = getattr(main_window, "mode_presenter_coordinator", None)
        enter_method = getattr(coordinator, "enter_mode", None)
        if callable(enter_method):
            preferred_tab_id = enter_method(
                ModeEnterRequest(view_mode=view_mode, previous_mode=previous_mode)
            )

        # 9) 应用右侧静态标签配置 + 切到 preferred
        main_window._apply_right_tabs_for_mode(view_mode)
        if preferred_tab_id:
            main_window.right_panel_registry.switch_to(preferred_tab_id)

        # 10) 收敛右侧标签与可见性
        main_window._enforce_right_panel_contract(view_mode)
        main_window._switch_to_first_visible_tab()
        main_window._update_right_panel_visibility()

        # 11) 调试输出
        central_index = main_window.central_stack.currentIndex()
        central_mode = ViewMode.from_index(central_index)
        central_is_graph_view = (main_window.central_stack.currentWidget() is main_window.view)

        nav_current = None
        if hasattr(main_window, "nav_bar") and hasattr(main_window.nav_bar, "buttons"):
            for mode_key, button in main_window.nav_bar.buttons.items():
                if button.isChecked():
                    nav_current = mode_key
                    break

        if hasattr(main_window, "side_tab"):
            side_count = main_window.side_tab.count()
            side_titles = [main_window.side_tab.tabText(i) for i in range(side_count)]
            current_side_title = (
                main_window.side_tab.tabText(main_window.side_tab.currentIndex())
                if side_count > 0
                else "<none>"
            )
        else:
            side_count = 0
            side_titles = []
            current_side_title = "<none>"

        print(
            f"[MODE-STATE] nav={nav_current} | central={{index:{central_index}, mode:{central_mode}, is_graph_view:{central_is_graph_view}}} | "
            f"side={{count:{side_count}, current:'{current_side_title}', tabs:{side_titles}}}"
        )

        # 12) 保存状态提示与会话快照
        refresh_label = getattr(main_window, "_refresh_save_status_label_for_mode", None)
        if callable(refresh_label):
            refresh_label(view_mode)

        schedule_save = getattr(main_window, "_schedule_ui_session_state_save", None)
        if callable(schedule_save):
            schedule_save()


