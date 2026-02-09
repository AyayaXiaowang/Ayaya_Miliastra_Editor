"""任务清单与图编辑器联动相关的事件处理 Mixin"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.dialog_utils import show_warning_dialog
from app.ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager
from app.models.todo_generator import TodoGenerator
from app.models import TodoItem
from app.models.view_modes import ViewMode
from engine.utils.logging.logger import log_info
from app.runtime.services.graph_data_service import get_shared_graph_data_service
from app.ui.todo.current_todo_resolver import (
    CurrentTodoContext,
    build_context_from_host,
    resolve_current_todo_for_leaf,
)
from app.models.todo_detail_info_accessors import get_detail_type
from app.ui.main_window.right_panel_contracts import (
    CONTRACT_SHOW_PROPERTY,
    CONTRACT_SHOW_GRAPH_PROPERTY,
    CONTRACT_TODO_HIDE_EXECUTION_MONITOR_KEEP_PROPERTY,
    CONTRACT_TODO_SHOW_EXECUTION_MONITOR,
    RightPanelVisibilityContract,
)


@dataclass(frozen=True)
class _TodoRefreshSnapshot:
    previous_selected_id: str
    previous_current_id: str
    previous_detail_info: Dict[str, Any] | None


@dataclass(frozen=True)
class _PendingTodoFocusRequest:
    todo_id: str
    detail_info: Dict[str, Any] | None
    graph_id: str


class _TodoGenerateWorker(QtCore.QThread):
    """后台生成任务清单（避免阻塞 UI 线程）。"""

    generated = QtCore.pyqtSignal(int, str, object)  # request_id, package_id, todos(list[TodoItem])

    def __init__(
        self,
        *,
        request_id: int,
        package_id: str,
        package: Any,
        resource_manager: Any,
        package_index_manager: Any,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.request_id = int(request_id)
        self.package_id = str(package_id or "")
        self.package = package
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self.setObjectName(f"TodoGenerateWorker#{self.request_id}")

    def run(self) -> None:
        generator = TodoGenerator(
            self.package,
            self.resource_manager,
            package_index_manager=self.package_index_manager,
        )
        todos = generator.generate_todos()
        self.generated.emit(self.request_id, self.package_id, todos)


class TodoEventsMixin:
    """负责任务清单刷新、勾选状态变更，以及与图编辑器联动的事件处理逻辑。"""

    def _mark_pending_todo_refresh_request(
        self,
        *,
        desired_package_id: str,
        force: bool,
    ) -> None:
        """记录“当前刷新完成后仍需再次刷新”的意图。

        典型场景：
        - 刷新进行中用户切换存档（必须在旧线程结束后为新存档补一次刷新）
        - 设置变更希望强制重新生成任务清单（force=True）
        """
        setattr(self, "_todo_refresh_pending", True)
        setattr(self, "_todo_refresh_pending_package_id", str(desired_package_id or ""))
        if force:
            setattr(self, "_todo_refresh_pending_force", True)

    def _consume_pending_todo_refresh_request(self) -> tuple[str, bool] | None:
        """取出并清理待刷新请求：返回 (pending_package_id, pending_force)。"""
        if not bool(getattr(self, "_todo_refresh_pending", False)):
            return None
        pending_package_id = str(getattr(self, "_todo_refresh_pending_package_id", "") or "")
        pending_force = bool(getattr(self, "_todo_refresh_pending_force", False))
        setattr(self, "_todo_refresh_pending", False)
        setattr(self, "_todo_refresh_pending_package_id", "")
        setattr(self, "_todo_refresh_pending_force", False)
        return (pending_package_id, pending_force)

    # === 图编辑器右上角按钮与上下文 ===

    def register_graph_editor_todo_context(
        self,
        todo_id: str,
        detail_info: Dict[str, Any],
        todo_title: str = "",
    ) -> None:
        """记录从任务清单跳转到图编辑器的上下文，供编辑页面执行按钮使用。"""
        if not todo_id or not isinstance(detail_info, dict):
            self._graph_editor_todo_context = None
            self._update_graph_editor_todo_button_visibility()
            return

        snapshot = dict(detail_info)
        stored_title = todo_title or snapshot.get("title", "")

        self._graph_editor_todo_context = {
            "todo_id": todo_id,
            "detail_info": snapshot,
            "title": stored_title,
        }
        self._update_graph_editor_todo_button_visibility()

    def _on_graph_editor_execute_from_todo(self) -> None:
        """编辑器右上角按钮：前往任务清单并尽量定位当前图对应的步骤（必要时先生成 Todo）。"""
        current_graph_id = ""
        if hasattr(self, "graph_controller"):
            current_graph_id = str(getattr(self.graph_controller, "current_graph_id", "") or "")

        # 门禁：节点图源码非法时，可能会在 Todo 预览/懒加载/执行链路中触发解析异常；
        # 这里在跳转前做一次“能否加载图资源”的检查，失败则弹窗阻止进入执行页。
        if current_graph_id and hasattr(self, "app_state"):
            resource_manager = getattr(self.app_state, "resource_manager", None)
            package_index_manager = getattr(self.app_state, "package_index_manager", None)
            graph_data_service = get_shared_graph_data_service(resource_manager, package_index_manager)
            graph_config = graph_data_service.get_graph_config(current_graph_id)
            if graph_config is None:
                error_text = graph_data_service.get_graph_load_error(current_graph_id)
                message = error_text or f"节点图 '{current_graph_id}' 不存在或已被删除。"
                show_warning_dialog(self, "无法前往执行", message)
                return

        context: Optional[Dict[str, Any]] = getattr(self, "_graph_editor_todo_context", None)
        todo_id = ""
        detail_info: Dict[str, Any] = {}
        context_graph_id = ""
        if context and isinstance(context, dict):
            todo_id = str(context.get("todo_id") or "")
            detail_info = dict(context.get("detail_info") or {})
            context_graph_id = str(detail_info.get("graph_id") or "")

        # 关键：避免使用“过期的 Todo 上下文”导致跳转到错误的执行步骤。
        # 常见场景：用户从 Todo 跳到图 A（缓存了 todo_id），随后从图库/属性面板打开图 B；
        # 若此时仍优先使用旧 todo_id，会导致“前往执行”跳回图 A 的步骤而不是图 B。
        if current_graph_id and todo_id and context_graph_id != str(current_graph_id):
            todo_id = ""
            detail_info = {}
            setattr(self, "_graph_editor_todo_context", None)

        self._navigate_to_mode("todo")

        # 关键：进入 Todo 后立刻把共享画布挂到预览页（不等 220ms），避免“先切页再出现画布”的重开观感。
        if hasattr(self, "todo_widget") and self.todo_widget:
            if hasattr(self.todo_widget, "right_stack"):
                self.todo_widget.right_stack.setCurrentIndex(1)
            preview_panel = getattr(self.todo_widget, "preview_panel", None)
            if preview_panel is not None and hasattr(preview_panel, "show_shared_canvas_now"):
                preview_panel.show_shared_canvas_now()

        # 立即（下一帧）定位任务上下文，避免额外的延迟导致用户感觉“又打开了一次”。
        def _jump_and_resolve() -> None:
            if not hasattr(self, "todo_widget") or not self.todo_widget:
                return

            # 进入 Todo 模式后，确保任务数据已加载（若尚未生成，则生成一次）
            self._ensure_todo_data_loaded()

            # 优先跳回已有上下文的 todo_id
            if todo_id:
                self.todo_widget.focus_task_from_external(todo_id, detail_info)
                return

            # 若没有上下文，则尝试按当前图 ID 自动匹配一个步骤并定位
            if current_graph_id:
                # 若 Todo 仍在后台生成中，先记下“跳转意图”，待生成完成后再定位。
                if not self.todo_widget.has_loaded_todos():
                    setattr(
                        self,
                        "_pending_todo_focus_request",
                        _PendingTodoFocusRequest(
                            todo_id="",
                            detail_info=None,
                            graph_id=str(current_graph_id),
                        ),
                    )
                    return

                candidate = self.todo_widget.find_first_todo_for_graph(current_graph_id)
                if candidate is None:
                    return
                self.register_graph_editor_todo_context(
                    candidate.todo_id,
                    candidate.detail_info,
                    candidate.title,
                )
                self.todo_widget.focus_task_from_external(candidate.todo_id, candidate.detail_info)

        QtCore.QTimer.singleShot(0, _jump_and_resolve)

    def _update_graph_editor_todo_button_visibility(self) -> None:
        """根据上下文与当前图状态，更新编辑器执行按钮的可见性和文案。"""
        button = getattr(self, "graph_editor_todo_button", None)
        if button is None or not hasattr(self, "graph_controller"):
            return

        button_label = "前往执行"
        current_mode = None
        if hasattr(self, "central_stack"):
            current_mode = ViewMode.from_index(self.central_stack.currentIndex())

        should_show = current_mode is ViewMode.GRAPH_EDITOR

        button.setText(button_label)
        button.setVisible(should_show)

        graph_view = getattr(self.graph_controller, "view", None)
        if graph_view is not None and isinstance(graph_view, QtWidgets.QWidget):
            TopRightControlsManager.update_position(graph_view)

    def _ensure_todo_data_loaded(self) -> None:
        """若任务清单尚未加载，自动生成一次数据供上下文匹配使用。"""
        if bool(getattr(self, "_todo_refresh_in_progress", False)):
            return
        todo_widget = getattr(self, "todo_widget", None)
        if todo_widget is None:
            return
        if todo_widget.has_loaded_todos():
            return

        current_mode = None
        if hasattr(self, "central_stack"):
            current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode is not ViewMode.TODO:
            return

        package_controller = getattr(self, "package_controller", None)
        if package_controller is None or package_controller.current_package is None:
            return

        self._refresh_todo_list()

    def _ensure_todo_context_for_graph(self, graph_id: str) -> None:
        """当直接从其它页面打开图时，尝试匹配到任务清单中的步骤。"""
        if not graph_id or not hasattr(self, "todo_widget") or not self.todo_widget:
            return

        current_ctx: Optional[Dict[str, Any]] = getattr(self, "_graph_editor_todo_context", None)
        current_graph = ""
        if current_ctx:
            current_graph = str((current_ctx.get("detail_info") or {}).get("graph_id") or "")
        if current_ctx and current_graph == str(graph_id):
            return

        candidate = self.todo_widget.find_first_todo_for_graph(graph_id)
        if candidate is None:
            # 若无法为当前 graph_id 匹配到 Todo，则清理旧上下文，避免后续“前往执行”跳到别的图。
            if current_ctx:
                self._graph_editor_todo_context = None
            return

        self.register_graph_editor_todo_context(
            candidate.todo_id,
            candidate.detail_info,
            candidate.title,
        )

    # === 任务清单 ===

    def _refresh_todo_list(self, *, force: bool = False) -> None:
        """刷新任务清单。

        说明：
        - 生成在后台线程执行；同一时刻只允许一个生成线程在跑，避免切存档/进设置时触发线程风暴。
        - 若刷新进行中又触发刷新（例如切换存档），会记录待刷新请求，等当前线程结束后自动补刷新，
          避免“生成中被挡掉 → 旧结果因 package_id 不匹配被丢弃 → 页面卡在生成中”的问题。
        """
        todo_widget = getattr(self, "todo_widget", None)

        if bool(getattr(self, "_todo_refresh_in_progress", False)):
            current_package_id = str(getattr(self.package_controller, "current_package_id", "") or "")
            self._mark_pending_todo_refresh_request(
                desired_package_id=current_package_id,
                force=bool(force),
            )

            running_worker = getattr(self, "_todo_refresh_worker", None)
            running_package_id = str(getattr(running_worker, "package_id", "") or "")
            if todo_widget is not None and hasattr(todo_widget, "set_stats_status"):
                if running_package_id and current_package_id and running_package_id != current_package_id:
                    todo_widget.set_stats_status(
                        "正在生成任务清单…（存档已切换，完成后将自动刷新）"
                    )
                else:
                    todo_widget.set_stats_status("正在生成任务清单…")
            return

        # 本轮刷新开始前：清理上一轮“待刷新”标记（后续若再次触发，会重新设置）
        setattr(self, "_todo_refresh_pending", False)
        setattr(self, "_todo_refresh_pending_package_id", "")
        setattr(self, "_todo_refresh_pending_force", False)

        # 在刷新前尽量记录一次任务清单上下文，供刷新后恢复选中与右侧联动使用。
        previous_selected_id: str = ""
        previous_current_id: str = ""
        previous_detail_info: Dict[str, Any] | None = None

        if todo_widget is not None and getattr(todo_widget, "has_loaded_todos", None):
            if todo_widget.has_loaded_todos():
                context = build_context_from_host(todo_widget)
                previous_selected_id = context.selected_todo_id or ""
                previous_current_id = context.current_todo_id or ""
                if context.current_detail_info:
                    previous_detail_info = dict(context.current_detail_info)

        package = self.package_controller.current_package
        package_id = getattr(self.package_controller, "current_package_id", "")
        package_type_name = type(package).__name__ if package is not None else "None"
        log_info(
            "[TODO-REFRESH] start: package_id={} package_type={}",
            package_id,
            package_type_name,
        )

        if not package:
            # 任务清单仅对“具体存档”有意义：全局视图下没有 todo_states 的落盘语义。
            unavailable_message = "请选择一个存档以生成任务清单"
            if str(package_id) == "global_view":
                unavailable_message = "当前为「共享资源」视图：请选择一个项目存档以生成任务清单"

            if todo_widget is not None and hasattr(todo_widget, "show_unavailable_state"):
                todo_widget.show_unavailable_state(unavailable_message)
            log_info("[TODO-REFRESH] skip: current_package 为空")
            return

        # 先更新状态徽章，让用户看到“正在生成”，避免常驻“加载中”造成误解。
        if todo_widget is not None and hasattr(todo_widget, "set_stats_status"):
            todo_widget.set_stats_status("正在生成任务清单…")
            # 让文案有机会先渲染到 UI（不阻塞后续耗时生成）
            QtWidgets.QApplication.processEvents()

        refresh_request_id = int(getattr(self, "_todo_refresh_request_id", 0)) + 1
        setattr(self, "_todo_refresh_request_id", refresh_request_id)
        setattr(self, "_todo_refresh_in_progress", True)

        snapshot = _TodoRefreshSnapshot(
            previous_selected_id=previous_selected_id,
            previous_current_id=previous_current_id,
            previous_detail_info=previous_detail_info,
        )

        worker = _TodoGenerateWorker(
            request_id=refresh_request_id,
            package_id=str(package_id),
            package=package,
            resource_manager=self.app_state.resource_manager,
            package_index_manager=self.app_state.package_index_manager,
            parent=self,
        )
        setattr(self, "_todo_refresh_worker", worker)
        expected_worker_package_id = str(package_id or "")

        def _on_generated(request_id: int, worker_package_id: str, todos_obj: object) -> None:
            latest_request_id = int(getattr(self, "_todo_refresh_request_id", 0))
            if int(request_id) != latest_request_id:
                return

            setattr(self, "_todo_refresh_in_progress", False)
            setattr(self, "_todo_refresh_worker", None)

            current_package_id = str(getattr(self.package_controller, "current_package_id", "") or "")
            if str(worker_package_id) != current_package_id:
                # 结果属于旧存档：为当前存档补一次刷新，避免 UI 卡在“正在生成…”
                self._mark_pending_todo_refresh_request(
                    desired_package_id=current_package_id,
                    force=False,
                )
                pending = self._consume_pending_todo_refresh_request()
                if pending is not None:
                    pending_package_id, pending_force = pending
                    should_schedule = bool(pending_force) or (
                        bool(pending_package_id) and str(pending_package_id) != str(worker_package_id)
                    )
                    if should_schedule:
                        current_mode = None
                        if hasattr(self, "central_stack"):
                            current_mode = ViewMode.from_index(self.central_stack.currentIndex())
                        if current_mode == ViewMode.TODO:
                            QtCore.QTimer.singleShot(
                                0, lambda: self._refresh_todo_list(force=bool(pending_force))
                            )
                return

            if todo_widget is None:
                return

            current_package = getattr(self.package_controller, "current_package", None)
            if current_package is None:
                return

            todos = todos_obj if isinstance(todos_obj, list) else []
            log_info("[TODO-REFRESH] generated: todo_count={}", len(todos))
            todo_widget.load_todos(todos, current_package.todo_states)

            self._restore_todo_context_after_refresh(todo_widget, snapshot=snapshot)
            self._apply_pending_todo_focus_request_if_any(todo_widget)

            pending = self._consume_pending_todo_refresh_request()
            if pending is not None:
                pending_package_id, pending_force = pending
                should_schedule = bool(pending_force) or (
                    bool(pending_package_id) and str(pending_package_id) != str(worker_package_id)
                )
                if should_schedule:
                    current_mode = None
                    if hasattr(self, "central_stack"):
                        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
                    if current_mode == ViewMode.TODO:
                        QtCore.QTimer.singleShot(
                            0, lambda: self._refresh_todo_list(force=bool(pending_force))
                        )

        worker.generated.connect(_on_generated)

        def _on_worker_finished() -> None:
            # 若生成过程中抛出了异常，generated 不会被发射；这里保证“生成中”状态不会永远卡住。
            latest_request_id = int(getattr(self, "_todo_refresh_request_id", 0))
            if refresh_request_id != latest_request_id:
                return
            if not bool(getattr(self, "_todo_refresh_in_progress", False)):
                return
            setattr(self, "_todo_refresh_in_progress", False)
            setattr(self, "_todo_refresh_worker", None)
            if todo_widget is not None and hasattr(todo_widget, "set_stats_status"):
                todo_widget.set_stats_status("任务清单生成失败（请查看控制台错误）")

            pending = self._consume_pending_todo_refresh_request()
            if pending is not None:
                pending_package_id, pending_force = pending
                should_schedule = bool(pending_force) or (
                    bool(pending_package_id)
                    and str(pending_package_id) != str(expected_worker_package_id)
                )
                if should_schedule:
                    current_mode = None
                    if hasattr(self, "central_stack"):
                        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
                    if current_mode == ViewMode.TODO:
                        QtCore.QTimer.singleShot(
                            0, lambda: self._refresh_todo_list(force=bool(pending_force))
                        )

        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(_on_worker_finished)
        worker.start()

    def _restore_todo_context_after_refresh(
        self,
        todo_widget: Any,
        *,
        snapshot: _TodoRefreshSnapshot,
    ) -> None:
        """刷新 Todo 后，尽量恢复到刷新前最接近的任务上下文（树选中/当前步骤/详情匹配）。"""
        has_previous_context = bool(
            snapshot.previous_selected_id
            or snapshot.previous_current_id
            or snapshot.previous_detail_info
        )
        if not has_previous_context:
            return

        refreshed_context = build_context_from_host(todo_widget)
        restore_context = CurrentTodoContext(
            selected_todo_id=snapshot.previous_selected_id,
            current_todo_id=snapshot.previous_current_id,
            current_detail_info=snapshot.previous_detail_info,
            todo_map=refreshed_context.todo_map,
            todos=refreshed_context.todos,
            find_first_todo_for_graph=refreshed_context.find_first_todo_for_graph,
            get_item_by_id=refreshed_context.get_item_by_id,
        )
        resolved_todo = resolve_current_todo_for_leaf(restore_context)
        if resolved_todo is None:
            return
        if not hasattr(todo_widget, "focus_task_from_external"):
            return
        todo_widget.focus_task_from_external(resolved_todo.todo_id, resolved_todo.detail_info)

    def _apply_pending_todo_focus_request_if_any(self, todo_widget: Any) -> None:
        """用于“前往执行”等入口：若此前记录了跳转意图，则在 Todo 生成完成后再进行聚焦。"""
        pending: _PendingTodoFocusRequest | None = getattr(self, "_pending_todo_focus_request", None)
        if pending is None or not isinstance(pending, _PendingTodoFocusRequest):
            return

        # 若明确提供 todo_id，则交给 todo_widget 自己处理（它会自行做缺失处理）
        if pending.todo_id:
            todo_widget.focus_task_from_external(pending.todo_id, pending.detail_info)
            setattr(self, "_pending_todo_focus_request", None)
            return

        graph_id = str(pending.graph_id or "")
        if not graph_id:
            setattr(self, "_pending_todo_focus_request", None)
            return

        candidate = todo_widget.find_first_todo_for_graph(graph_id)
        if candidate is None:
            setattr(self, "_pending_todo_focus_request", None)
            return

        self.register_graph_editor_todo_context(
            candidate.todo_id,
            candidate.detail_info,
            candidate.title,
        )
        todo_widget.focus_task_from_external(candidate.todo_id, candidate.detail_info)
        setattr(self, "_pending_todo_focus_request", None)

    def _on_todo_checked(self, todo_id: str, checked: bool) -> None:
        """任务勾选状态改变"""
        package = self.package_controller.current_package
        if not package:
            return
        normalized_todo_id = str(todo_id or "")
        target_checked = bool(checked)
        if not normalized_todo_id:
            return

        # 重要：只在“真实发生变化”时才标记存档为未保存。
        # - 避免树刷新/会话恢复等场景重复发射同值信号导致“退出必弹未保存”；
        # - todo_states 的语义：仅存储 True 的叶子完成度（缺省即 False），减少无意义写盘与噪音 diff。
        previous_state = bool(package.todo_states.get(normalized_todo_id, False))
        if previous_state == target_checked:
            # 若为 False 且 key 不存在，视为无变化；若为 True 且已存在，同样无变化。
            return

        if target_checked:
            package.todo_states[normalized_todo_id] = True
        else:
            package.todo_states.pop(normalized_todo_id, None)

        # 标记当前存档存在未保存的 Todo 进度变化：
        # - 勾选操作只更新内存中的 todo_states 与 UI 树三态；
        # - 实际落盘仍交由工具栏“保存”按钮或窗口关闭流程统一处理，避免在频繁勾选时
        #   反复触发资源保存与 FileWatcher 导致的整表刷新。
        package_controller = getattr(self, "package_controller", None)
        if package_controller is not None and hasattr(package_controller, "mark_index_dirty"):
            package_controller.mark_index_dirty()
        set_status = getattr(self, "_set_last_save_status", None)
        if callable(set_status):
            set_status("unsaved")

    def on_todo_selection_changed(self, todo: TodoItem) -> None:
        """任务清单选中项变化时，根据任务类型在右侧展示只读属性面板。

        设计约定：
        - 模板/实例类任务在任务清单模式下同步到右侧元件属性面板，面板以只读方式展示；
        - 其他任务不干预属性面板标签，只保留执行监控等模式自带标签；
        - 离开任务清单模式后，由模式切换逻辑恢复属性面板的可编辑状态。
        """
        if not todo or not getattr(self, "package_controller", None):
            return

        # 同步到 ViewState（单一真源）
        view_state = getattr(self, "view_state", None)
        todo_state = getattr(view_state, "todo", None)
        if todo_state is not None:
            setattr(todo_state, "todo_id", str(getattr(todo, "todo_id", "") or ""))
            setattr(todo_state, "task_type", str(getattr(todo, "task_type", "") or ""))
            detail_info_any = getattr(todo, "detail_info", None) or {}
            setattr(todo_state, "detail_info", dict(detail_info_any) if isinstance(detail_info_any, dict) else {})

        package = self.package_controller.current_package
        if not package or not hasattr(self, "property_panel"):
            return

        detail_info = todo.detail_info or {}
        detail_type = get_detail_type(detail_info)
        task_type = str(todo.task_type or "")

        # 节点图变量：不在任务详情里展示表格；保持中间共享画布显示，并将右侧切到“图属性 → 节点图变量”。
        if detail_type == "graph_variables_table":
            # 该步骤不应展示“执行监控”，先确保监控标签被收敛隐藏。
            self._update_execution_monitor_tab_for_todo(todo, switch_to=False)

            graph_id = str(getattr(todo, "target_id", "") or "") or str(detail_info.get("graph_id") or "")
            if graph_id and hasattr(self, "graph_property_panel") and self.graph_property_panel is not None:
                self.graph_property_panel.set_graph(graph_id)
                if hasattr(self.graph_property_panel, "switch_to_variables_tab"):
                    self.graph_property_panel.switch_to_variables_tab()

            # 强制展示图属性面板并切换到它（避免在 TODO 模式下被其它标签抢占）。
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_GRAPH_PROPERTY)
            self.schedule_ui_session_state_save()
            return

        # 优先根据步骤类型控制“执行监控”标签的显示：仅在节点图相关步骤下展示。
        # 注意：图相关步骤的 task_type 往往仍为 "template"/"instance"（表示归属对象），
        # 若不在这里先行拦截，会导致图步骤在选中/自动执行时被误判为“模板/实例任务”，从而抢占到“属性”tab。
        self._update_execution_monitor_tab_for_todo(todo, switch_to=True)

        is_graph_related_step = (
            detail_type == "template_graph_root"
            or detail_type == "event_flow_root"
            or detail_type.startswith("graph")
            or detail_type.startswith("composite_")
        )
        if is_graph_related_step:
            return

        is_template_task = task_type == "template" or detail_type == "template"
        is_instance_task = task_type == "instance" or detail_type == "instance"

        # 仅在模板/实例相关任务下展示属性面板
        if not (is_template_task or is_instance_task):
            # 若此前因 Todo 选中而打开过属性面板，这里不强制关闭，仅在模式切换时统一回收
            return

        # 切换到只读模式，防止在任务清单页面误修改真实数据
        if hasattr(self.property_panel, "set_read_only"):
            self.property_panel.set_read_only(True)

        if is_template_task:
            template_id = detail_info.get("template_id") or todo.target_id
            if template_id:
                self.property_panel.set_template(package, str(template_id))
        elif is_instance_task:
            instance_id = detail_info.get("instance_id") or todo.target_id
            if instance_id:
                self.property_panel.set_instance(package, str(instance_id))

        # 在任务清单模式下按需将“属性”标签插入右侧标签页（并收敛其它详情标签）
        self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PROPERTY)
        self.schedule_ui_session_state_save()

    def _update_execution_monitor_tab_for_todo(self, todo: TodoItem, *, switch_to: bool = False) -> bool:
        """根据 Todo 步骤类型按需显示/隐藏右侧“执行监控”标签页。

        规则：
        - 仅当步骤属于节点图相关类型时显示：
          - 模板图根: template_graph_root
          - 事件流根: event_flow_root
          - 复合节点步骤: 以 \"composite_\" 开头
          - 节点图叶子步骤: 以 \"graph\" 开头，且排除图根/变量总表
        - 其他步骤（如纯模板属性、实例属性、管理类任务）不显示执行监控标签。
        """
        detail_info = todo.detail_info or {}
        detail_type = get_detail_type(detail_info)

        is_template_graph_root = detail_type == "template_graph_root"
        is_event_flow_root = detail_type == "event_flow_root"
        is_composite_step = detail_type.startswith("composite_")
        is_leaf_graph_step = (
            detail_type.startswith("graph")
            and not is_template_graph_root
            and not is_event_flow_root
            and detail_type != "graph_variables_table"
        )
        should_show_monitor = (
            is_template_graph_root
            or is_event_flow_root
            or is_composite_step
            or is_leaf_graph_step
        )

        current_view_mode = None
        if hasattr(self, "central_stack"):
            current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())

        # 仅在 TODO 模式下做右侧收敛：避免其它模式中 GraphView 的双击跳转等事件误触发。
        if current_view_mode == ViewMode.TODO:
            if should_show_monitor:
                contract = (
                    CONTRACT_TODO_SHOW_EXECUTION_MONITOR
                    if switch_to
                    else RightPanelVisibilityContract(
                        keep_tab_ids=("execution_monitor", "property"),
                        ensure_tab_ids=("execution_monitor",),
                        preferred_tab_id=None,
                    )
                )
                self.right_panel.apply_visibility_contract(contract)
            else:
                self.right_panel.apply_visibility_contract(CONTRACT_TODO_HIDE_EXECUTION_MONITOR_KEEP_PROPERTY)
        return should_show_monitor
