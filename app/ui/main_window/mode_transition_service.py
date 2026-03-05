"""模式切换服务：集中封装主窗口模式切换的公共步骤与顺序约束。

目标：
- 让 `ModeSwitchMixin` 只保留最薄的一层事件入口，减少多人协作冲突点；
- 把“保存/切堆栈/调用 presenter/右侧收敛/会话保存”等顺序依赖集中到可复用服务。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.models.view_modes import ViewMode
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.main_window.mode_presenters import ModeEnterRequest
from engine.utils.logging.logger import log_debug


@dataclass(slots=True)
class ModeTransitionRequest:
    mode_string: str


class _ModeTransitionHost(Protocol):
    """ModeTransitionService 依赖的最小主窗口契约（显式接口）。

    说明：
    - 这里故意只声明“流程编排必须用到”的成员，避免服务随意依赖主窗口的隐式 self.*；
    - 服务侧只通过这组显式入口完成切换，不依赖主窗口的兼容别名。
    """

    # 核心 UI/状态对象
    central_stack: Any
    main_splitter: Any
    nav_bar: Any
    right_panel: Any
    view_state: Any
    app_state: Any

    # 编辑上下文（保存/离开时需要）
    graph_controller: Any
    composite_widget: Any
    mode_presenter_coordinator: Any

    # 稳定的公开钩子（避免依赖 _private 方法名）
    def refresh_save_status_label_for_mode(self, view_mode: ViewMode) -> None: ...
    def schedule_ui_session_state_save(self) -> None: ...
    def save_current_composite_if_needed(self) -> None: ...
    def on_mode_transition_completed(self, view_mode: ViewMode) -> None: ...


class ModeTransitionService:
    """封装主窗口模式切换公共流程。"""

    def transition(self, main_window: _ModeTransitionHost, request: ModeTransitionRequest) -> None:
        mode_string = request.mode_string
        current_mode = ViewMode.from_index(main_window.central_stack.currentIndex())

        log_debug(
            "[MODE] transition start: from={} to={} graph_id={} dirty={}",
            current_mode,
            mode_string,
            getattr(main_window.graph_controller, "current_graph_id", None),
            getattr(main_window.graph_controller, "is_dirty", None),
        )

        # 1) 离开复合节点：保存当前复合节点（若存在选中）
        if current_mode == ViewMode.COMPOSITE:
            main_window.save_current_composite_if_needed()

        # 2) 离开节点图编辑：如有脏则保存
        current_graph_identifier = getattr(main_window.graph_controller, "current_graph_id", "")
        if current_graph_identifier and getattr(main_window.graph_controller, "is_dirty", False):
            log_debug("[MODE] saving dirty graph before leaving: {}", current_graph_identifier)
            main_window.graph_controller.save_current_graph()

        # 3) 解析目标模式（非法输入直接抛错更利于定位）
        target_view_mode = ViewMode.from_string(mode_string)
        if target_view_mode is None:
            raise ValueError(f"未知模式: {mode_string!r}")

        # 3.5) TODO 模式的“全局画布只读化”：
        # - 进入 TODO：将 GraphEditorController 统一切到只读预览能力，确保任务清单预览不可编辑；
        # - 离开 TODO：恢复进入前的能力快照，避免切回编辑器后仍卡在只读。
        if target_view_mode == ViewMode.TODO and current_mode != ViewMode.TODO:
            previous_capabilities = getattr(main_window.graph_controller, "edit_session_capabilities", None)
            setattr(main_window, "_graph_capabilities_before_todo", previous_capabilities)
            main_window.graph_controller.set_edit_session_capabilities(EditSessionCapabilities.read_only_preview())
        elif current_mode == ViewMode.TODO and target_view_mode != ViewMode.TODO:
            previous_capabilities = getattr(main_window, "_graph_capabilities_before_todo", None)
            if isinstance(previous_capabilities, EditSessionCapabilities):
                main_window.graph_controller.set_edit_session_capabilities(previous_capabilities)

        # 4) ViewState 记录模式切换（单一真源）
        main_window.view_state.set_mode(
            current=target_view_mode,
            previous=current_mode or target_view_mode,
        )

        # 5) 同步左侧导航高亮（图编辑器借用“节点图库”作为锚点）
        nav_mode_string = target_view_mode.to_string()
        if target_view_mode == ViewMode.GRAPH_EDITOR:
            nav_mode_string = "graph_library"
        main_window.nav_bar.set_current_mode(nav_mode_string)

        # 6) 切换中央堆栈
        main_window.central_stack.setCurrentIndex(target_view_mode.value)

        # 7) 调整左右分割器比例（TODO 模式特殊）
        if target_view_mode == ViewMode.TODO:
            main_window.main_splitter.setSizes([1600, 400])
        else:
            main_window.main_splitter.setSizes([1200, 800])

        # 8) 进入模式前：统一收敛右侧面板默认态（避免跨模式残留“允许但不该默认展示”的标签）
        main_window.right_panel.prepare_for_mode_enter(target_view_mode)

        # 9) 进入模式副作用（presenter）
        previous_mode = current_mode or target_view_mode
        preferred_tab_id = main_window.mode_presenter_coordinator.enter_mode(
            ModeEnterRequest(view_mode=target_view_mode, previous_mode=previous_mode)
        )

        # 10) 应用右侧静态标签配置 + 切到 preferred
        main_window.right_panel.apply_for_mode(target_view_mode)
        if preferred_tab_id:
            main_window.right_panel.switch_to(preferred_tab_id)

        # 11) 收敛右侧标签与可见性
        main_window.right_panel.enforce_contract(target_view_mode)
        main_window.right_panel.switch_to_first_visible_tab()
        main_window.right_panel.update_visibility()

        # 12) 调试输出（高层快照）
        central_index = main_window.central_stack.currentIndex()
        central_mode = ViewMode.from_index(central_index)
        central_is_graph_view = (
            main_window.central_stack.currentWidget() is main_window.app_state.graph_view
        )

        nav_current = None
        nav_buttons = getattr(main_window.nav_bar, "buttons", None)
        if isinstance(nav_buttons, dict):
            for mode_key, button in nav_buttons.items():
                if getattr(button, "isChecked", lambda: False)():
                    nav_current = mode_key
                    break

        side_tab = getattr(main_window, "side_tab", None)
        if side_tab is not None and hasattr(side_tab, "count"):
            side_count = side_tab.count()
            side_titles = [side_tab.tabText(i) for i in range(side_count)]
            current_side_title = (
                side_tab.tabText(side_tab.currentIndex()) if side_count > 0 else "<none>"
            )
        else:
            side_count = 0
            side_titles = []
            current_side_title = "<none>"

        log_debug(
            "[MODE-STATE] nav={} | central={{index:{}, mode:{}, is_graph_view:{}}} | side={{count:{}, current:'{}', tabs:{}}}",
            nav_current,
            central_index,
            central_mode,
            central_is_graph_view,
            side_count,
            current_side_title,
            side_titles,
        )

        # 13) 保存状态提示与会话快照（稳定公开钩子）
        main_window.refresh_save_status_label_for_mode(target_view_mode)
        main_window.schedule_ui_session_state_save()
        main_window.on_mode_transition_completed(target_view_mode)


