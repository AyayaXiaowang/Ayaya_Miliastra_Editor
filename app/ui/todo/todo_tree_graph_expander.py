from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import time

from PyQt6 import QtCore, QtWidgets, sip
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.models.todo_generator import TodoGenerator
from app.models.todo_detail_info_accessors import get_graph_id
from app.runtime.services.graph_data_service import get_shared_graph_data_service
from app.ui.foundation.dialog_utils import show_warning_dialog
from app.ui.todo.todo_config import StepTypeRules


_GRAPH_EXPAND_PLACEHOLDER_MARKER: str = "graph_expand_placeholder"


def _is_tree_item_alive(item: object) -> bool:
    """判断 QTreeWidgetItem 的 sip 包装对象是否仍绑定有效的 C++ 对象。

    说明：
    - Qt 在清空/刷新树时会直接释放旧的 C++ item。
    - Python 侧引用仍可能保留（例如缓存 dict），此时调用任何方法都会抛
      `wrapped C/C++ object ... has been deleted`。
    """

    if not isinstance(item, QtWidgets.QTreeWidgetItem):
        return False
    return not sip.isdeleted(item)


def _find_graph_expand_placeholder_item(
    tree_manager: Any,
    graph_root_id: str,
) -> Optional[QtWidgets.QTreeWidgetItem]:
    placeholders = getattr(tree_manager, "_graph_expand_placeholders", None)
    if isinstance(placeholders, dict):
        stored = placeholders.get(graph_root_id)
        if isinstance(stored, QtWidgets.QTreeWidgetItem):
            if _is_tree_item_alive(stored):
                return stored
            placeholders.pop(graph_root_id, None)

    item_map: Dict[str, QtWidgets.QTreeWidgetItem] = getattr(tree_manager, "_item_map", {})
    root_item = item_map.get(graph_root_id) if isinstance(item_map, dict) else None
    if not _is_tree_item_alive(root_item):
        return None

    marker_role = getattr(tree_manager, "MARKER_ROLE", None)
    for child_index in range(root_item.childCount()):
        child = root_item.child(child_index)
        if not _is_tree_item_alive(child):
            continue
        if isinstance(marker_role, int):
            marker = child.data(0, marker_role)
            if marker == _GRAPH_EXPAND_PLACEHOLDER_MARKER:
                return child
        text = str(child.text(0) or "")
        if text.startswith("正在生成节点图步骤"):
            return child
    return None


def _remove_graph_expand_placeholder_item(tree_manager: Any, graph_root_id: str) -> None:
    placeholders = getattr(tree_manager, "_graph_expand_placeholders", None)
    if isinstance(placeholders, dict):
        placeholders.pop(graph_root_id, None)

    placeholder_item = _find_graph_expand_placeholder_item(tree_manager, graph_root_id)
    if isinstance(placeholder_item, QtWidgets.QTreeWidgetItem):
        parent_item = placeholder_item.parent()
        if parent_item is not None:
            parent_item.removeChild(placeholder_item)


@dataclass
class GraphExpandContext:
    """懒加载模板图步骤时所需的上下文。"""

    parent_id: str
    graph_id: str
    preview_template_id: str
    package: Any
    resource_manager: Any
    package_index_manager: Optional[Any] = None


class _GraphExpandWorker(QtCore.QThread):
    """后台展开模板图根的详细步骤（避免阻塞 UI 线程）。"""

    expanded = QtCore.pyqtSignal(int, str, str, object)  # request_id, graph_root_id, package_id, todos(list[TodoItem])
    progress = QtCore.pyqtSignal(
        int, str, str, int, int, str
    )  # request_id, graph_root_id, package_id, completed, total, stage

    def __init__(
        self,
        *,
        request_id: int,
        graph_root_id: str,
        package_id: str,
        context: GraphExpandContext,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.request_id = int(request_id)
        self.graph_root_id = str(graph_root_id or "")
        self.package_id = str(package_id or "")
        self.context = context
        self.setObjectName(f"GraphExpandWorker#{self.request_id}:{self.graph_root_id}")
        self._last_progress_percent: int = -1
        self._last_progress_stage: str = ""
        self._last_progress_emit_ts: float = 0.0

    def run(self) -> None:
        # 先汇报一个“加载资源”阶段，确保 UI 能立刻展示占位与阶段文案。
        self.progress.emit(
            self.request_id,
            self.graph_root_id,
            self.package_id,
            0,
            1,
            "加载节点图资源",
        )

        def _on_progress(stage: str, completed: int, total: int) -> None:
            safe_total = int(total) if int(total) > 0 else 1
            safe_completed = int(completed) if int(completed) > 0 else 0
            percent = int(safe_completed * 100 / safe_total)
            if percent < 0:
                percent = 0
            if percent > 100:
                percent = 100
            stage_text = str(stage or "")

            now_ts = time.perf_counter()
            stage_changed = stage_text != self._last_progress_stage
            percent_changed = percent != self._last_progress_percent
            should_emit = stage_changed or percent_changed
            if not should_emit:
                return
            # 节流：避免高频信号刷新 UI
            if not percent_changed and (now_ts - self._last_progress_emit_ts) < 0.08:
                return

            self._last_progress_stage = stage_text
            self._last_progress_percent = percent
            self._last_progress_emit_ts = now_ts
            self.progress.emit(
                self.request_id,
                self.graph_root_id,
                self.package_id,
                safe_completed,
                safe_total,
                stage_text,
            )

        graph_data_service = get_shared_graph_data_service(
            self.context.resource_manager,
            self.context.package_index_manager,
        )
        graph_config = graph_data_service.get_graph_config(self.context.graph_id)
        if graph_config is None:
            # 失败原因由 GraphDataService 统一缓存：由 UI 线程的兜底清理逻辑读取并提示。
            return

        todos = TodoGenerator.expand_graph_tasks(
            package=self.context.package,
            resource_manager=self.context.resource_manager,
            package_index_manager=self.context.package_index_manager,
            parent_id=self.context.parent_id,
            graph_id=self.context.graph_id,
            graph_name=graph_config.name,
            graph_data=graph_config.data,
            preview_template_id=self.context.preview_template_id,
            suppress_auto_jump=False,
            graph_root=None,
            attach_graph_root=True,
            progress_callback=_on_progress,
        )
        self.expanded.emit(self.request_id, self.graph_root_id, self.package_id, todos)


class _GraphExpandResultApplier(QtCore.QObject):
    """在 UI 线程应用“图展开结果”，并负责清理 inflight/占位项/回调。"""

    def __init__(
        self,
        *,
        tree_manager: Any,
        request_id: int,
        graph_root_id: str,
        expected_package_id: str,
        context: GraphExpandContext,
    ) -> None:
        super().__init__(tree_manager)
        self.tree_manager = tree_manager
        self.request_id = int(request_id)
        self.graph_root_id = str(graph_root_id or "")
        self.expected_package_id = str(expected_package_id or "")
        self.context = context
        self._handled: bool = False
        self._last_percent: int = -1

    @QtCore.pyqtSlot(int, str, str, int, int, str)
    def on_progress(
        self,
        request_id: int,
        graph_root_id: str,
        package_id: str,
        completed: int,
        total: int,
        stage: str,
    ) -> None:
        if int(request_id) != self.request_id:
            return
        if str(graph_root_id or "") != self.graph_root_id:
            return

        tree_manager = self.tree_manager

        # 校验当前上下文是否仍匹配（避免把旧包/旧图的进度更新到新树上）
        current_package_id = ""
        dependency_getter = getattr(tree_manager, "_graph_expand_dependency_getter", None)
        if callable(dependency_getter):
            dependencies = dependency_getter()
            if isinstance(dependencies, tuple) and len(dependencies) >= 1:
                current_package = dependencies[0]
                current_package_id = str(getattr(current_package, "package_id", "") or "")

        expected_package_id = str(self.expected_package_id or "")
        incoming_package_id = str(package_id or "")
        package_ok = True
        # 仅在“能够拿到明确 package_id”时才进行严格比对；
        # 避免 dependency_getter 在某些 UI 状态下返回的 package 缺少 package_id，
        # 导致进度始终被挡掉而占位项卡在 0%。
        if expected_package_id and incoming_package_id and incoming_package_id != expected_package_id:
            package_ok = False
        if expected_package_id and current_package_id and current_package_id != expected_package_id:
            package_ok = False
        if not package_ok:
            return

        safe_total = int(total) if int(total) > 0 else 1
        safe_completed = int(completed) if int(completed) > 0 else 0
        percent = int(safe_completed * 100 / safe_total)
        if percent < 0:
            percent = 0
        if percent > 100:
            percent = 100
        if percent < self._last_percent:
            percent = self._last_percent
        self._last_percent = percent

        stage_text = str(stage or "正在生成节点图步骤…")

        placeholder_item = _find_graph_expand_placeholder_item(tree_manager, self.graph_root_id)
        if isinstance(placeholder_item, QtWidgets.QTreeWidgetItem):
            placeholder_item.setText(
                0,
                f"正在生成节点图步骤… {percent}%（{stage_text}）",
            )
            # 若此前占位项引用丢失（例如整树刷新重建），恢复到 placeholders 以便后续清理。
            placeholders = getattr(tree_manager, "_graph_expand_placeholders", None)
            if isinstance(placeholders, dict) and self.graph_root_id not in placeholders:
                placeholders[self.graph_root_id] = placeholder_item

        host = tree_manager.parent() if hasattr(tree_manager, "parent") else None
        if host is not None:
            current_todo_id = str(getattr(host, "current_todo_id", "") or "")
            if current_todo_id == self.graph_root_id:
                detail_panel = getattr(host, "detail_panel", None)
                if detail_panel is not None and hasattr(detail_panel, "set_generation_progress"):
                    detail_panel.set_generation_progress(percent, stage_text)

    @QtCore.pyqtSlot(int, str, str, object)
    def on_expanded(
        self,
        request_id: int,
        graph_root_id: str,
        package_id: str,
        todos_obj: object,
    ) -> None:
        # 仅处理属于本次请求的结果（防止信号误绑或重复触发）
        if int(request_id) != self.request_id:
            return
        if str(graph_root_id or "") != self.graph_root_id:
            return

        tree_manager = self.tree_manager
        self._handled = True
        success = False

        # --- 清理：占位项（先移除，避免后续插入子项时混入“正在生成...”）
        # 注意：树在展开过程中可能发生刷新/重建，导致 placeholders 引用丢失；
        # 这里用“从树上扫描 marker/text”兜底删除，避免出现“步骤已生成但占位仍停留 0%”。
        _remove_graph_expand_placeholder_item(tree_manager, self.graph_root_id)

        # --- 校验当前上下文是否仍匹配（避免把旧包/旧图的展开结果回填到新树上）
        current_package_id = ""
        dependency_getter = getattr(tree_manager, "_graph_expand_dependency_getter", None)
        if callable(dependency_getter):
            dependencies = dependency_getter()
            if isinstance(dependencies, tuple) and len(dependencies) >= 1:
                current_package = dependencies[0]
                current_package_id = str(getattr(current_package, "package_id", "") or "")

        expected_package_id = str(self.expected_package_id or "")
        incoming_package_id = str(package_id or "")
        package_ok = True
        if expected_package_id and incoming_package_id and incoming_package_id != expected_package_id:
            package_ok = False
        if expected_package_id and current_package_id and current_package_id != expected_package_id:
            package_ok = False

        todos_list: List[TodoItem] = []
        if isinstance(todos_obj, list):
            for entry in todos_obj:
                if isinstance(entry, TodoItem):
                    todos_list.append(entry)

        if package_ok and todos_list:
            todo_map: Dict[str, TodoItem] = getattr(tree_manager, "todo_map", {})
            todos: List[TodoItem] = getattr(tree_manager, "todos", [])

            existing_graph_root = todo_map.get(self.graph_root_id) if isinstance(todo_map, dict) else None
            generated_graph_root = None
            for todo in todos_list:
                if todo.todo_id == self.graph_root_id:
                    generated_graph_root = todo
                    break

            if existing_graph_root is not None and generated_graph_root is not None:
                # 1) 先把根 Todo 的结构信息回填到“既有对象”（保持引用稳定）
                existing_graph_root.title = generated_graph_root.title
                existing_graph_root.description = generated_graph_root.description
                existing_graph_root.level = generated_graph_root.level
                existing_graph_root.parent_id = generated_graph_root.parent_id
                existing_graph_root.children = list(generated_graph_root.children)
                existing_graph_root.task_type = generated_graph_root.task_type
                existing_graph_root.target_id = generated_graph_root.target_id
                existing_graph_root.detail_info = dict(generated_graph_root.detail_info or {})

                # 2) 合并新增 Todo 到权威 todo_map / todos 列表
                for expanded_todo in todos_list:
                    if expanded_todo.todo_id == self.graph_root_id:
                        continue
                    if expanded_todo.todo_id not in todo_map:
                        todo_map[expanded_todo.todo_id] = expanded_todo
                        todos.append(expanded_todo)

                # 3) 确保父级引用保持一致
                parent_todo = todo_map.get(self.context.parent_id)
                if parent_todo is not None and self.graph_root_id not in parent_todo.children:
                    parent_todo.children.append(self.graph_root_id)

                # 4) 挂载树节点
                refresh_gate = getattr(tree_manager, "_refresh_gate", None)
                tree = getattr(tree_manager, "tree", None)
                if refresh_gate is not None and tree is not None:
                    refresh_gate.set_refreshing(True)
                    tree.setUpdatesEnabled(False)
                    try:
                        _attach_expanded_graph_to_tree(
                            tree_manager,
                            existing_graph_root,
                            self.context,
                            todos_list,
                        )
                    finally:
                        # 兜底：后台展开回填阶段若抛异常，Qt 只会打印错误但不会自动恢复 updatesEnabled，
                        # 会导致树后续交互“怎么点都没反应”的假死体验。
                        tree.setUpdatesEnabled(True)
                        viewport = tree.viewport()
                        if viewport is not None:
                            viewport.update()
                        refresh_gate.set_refreshing(False)

                # 5) 更新统计徽章（叶子数/完成度会随展开变化）
                host = tree_manager.parent() if hasattr(tree_manager, "parent") else None
                update_stats = getattr(host, "_update_stats", None) if host is not None else None
                if callable(update_stats):
                    update_stats()

                success = True

        # 成功时补齐 100%（避免最后一次 progress 信号因节流/时序被跳过）
        if bool(success):
            host = tree_manager.parent() if hasattr(tree_manager, "parent") else None
            if host is not None:
                current_todo_id = str(getattr(host, "current_todo_id", "") or "")
                if current_todo_id == self.graph_root_id:
                    detail_panel = getattr(host, "detail_panel", None)
                    if detail_panel is not None and hasattr(detail_panel, "set_generation_progress"):
                        detail_panel.set_generation_progress(100, "完成")

        # --- 清理 inflight / 回调
        inflight = getattr(tree_manager, "_graph_expand_inflight", {})
        if isinstance(inflight, dict):
            inflight.pop(self.graph_root_id, None)

        appliers = getattr(tree_manager, "_graph_expand_appliers", {})
        if isinstance(appliers, dict):
            appliers.pop(self.graph_root_id, None)

        callbacks_map = getattr(tree_manager, "_graph_expand_callbacks", {})
        callbacks = callbacks_map.pop(self.graph_root_id, []) if isinstance(callbacks_map, dict) else []
        if isinstance(callbacks, list):
            for callback in callbacks:
                if callable(callback):
                    callback(bool(success))

        self.deleteLater()

    @QtCore.pyqtSlot()
    def on_worker_finished(self) -> None:
        """兜底清理：当后台线程异常退出且未发射 expanded 时，确保 inflight/占位项不会卡死。"""
        if bool(self._handled):
            return

        tree_manager = self.tree_manager

        # 移除占位项（同样做“扫描兜底”，防止 placeholders 丢失）
        _remove_graph_expand_placeholder_item(tree_manager, self.graph_root_id)

        # 清理 inflight 与 applier
        inflight = getattr(tree_manager, "_graph_expand_inflight", {})
        if isinstance(inflight, dict):
            inflight.pop(self.graph_root_id, None)

        appliers = getattr(tree_manager, "_graph_expand_appliers", {})
        if isinstance(appliers, dict):
            appliers.pop(self.graph_root_id, None)

        # 若是“节点图资源无法加载/解析”导致未发射 expanded：给出明确提示。
        # 注意：仅在上下文仍属于当前包时提示，避免切存档后弹出旧图错误。
        current_package_id = ""
        dependency_getter = getattr(tree_manager, "_graph_expand_dependency_getter", None)
        if callable(dependency_getter):
            dependencies = dependency_getter()
            if isinstance(dependencies, tuple) and len(dependencies) >= 1:
                current_package = dependencies[0]
                current_package_id = str(getattr(current_package, "package_id", "") or "")
        expected_package_id = str(self.expected_package_id or "")
        if expected_package_id and current_package_id and current_package_id != expected_package_id:
            # 切包后不提示旧错误
            pass
        else:
            graph_id = str(getattr(self.context, "graph_id", "") or "")
            resource_manager = getattr(self.context, "resource_manager", None)
            package_index_manager = getattr(self.context, "package_index_manager", None)
            if graph_id and resource_manager is not None:
                graph_data_service = get_shared_graph_data_service(resource_manager, package_index_manager)
                error_text = graph_data_service.get_graph_load_error(graph_id)
                if isinstance(error_text, str) and error_text.strip():
                    tree = getattr(tree_manager, "tree", None)
                    show_warning_dialog(
                        tree if isinstance(tree, QtWidgets.QWidget) else None,
                        "无法生成节点图步骤",
                        error_text.strip(),
                    )

        # 回调：失败
        callbacks_map = getattr(tree_manager, "_graph_expand_callbacks", {})
        callbacks = callbacks_map.pop(self.graph_root_id, []) if isinstance(callbacks_map, dict) else []
        if isinstance(callbacks, list):
            for callback in callbacks:
                if callable(callback):
                    callback(False)

        self.deleteLater()


def expand_graph_on_demand(
    tree_manager: Any,
    graph_root: TodoItem,
    *,
    on_finished: Optional[Callable[[bool], None]] = None,
) -> None:
    """在首次展开模板图根时，按需生成其子步骤并补充到树与 todo 列表中。

    设计目标：
    - 在 UI 线程只做“占位/挂载/信号调度”；重计算（解析 GraphModel、生成大量 Todo）放到后台线程；
    - 同一图根重复触发时去重；
    - 支持可选回调：用于“点击执行但尚未展开”时的自动续航。
    """
    if graph_root.children:
        if callable(on_finished):
            on_finished(True)
        return

    context = _resolve_graph_expand_context(tree_manager, graph_root)
    if context is None:
        if callable(on_finished):
            on_finished(False)
        return

    inflight: dict[str, _GraphExpandWorker] = getattr(tree_manager, "_graph_expand_inflight", None)
    if not isinstance(inflight, dict):
        inflight = {}
        setattr(tree_manager, "_graph_expand_inflight", inflight)

    callbacks_map: dict[str, list[Callable[[bool], None]]] = getattr(tree_manager, "_graph_expand_callbacks", None)
    if not isinstance(callbacks_map, dict):
        callbacks_map = {}
        setattr(tree_manager, "_graph_expand_callbacks", callbacks_map)

    placeholders: dict[str, QtWidgets.QTreeWidgetItem] = getattr(tree_manager, "_graph_expand_placeholders", None)
    if not isinstance(placeholders, dict):
        placeholders = {}
        setattr(tree_manager, "_graph_expand_placeholders", placeholders)

    appliers: dict[str, _GraphExpandResultApplier] = getattr(tree_manager, "_graph_expand_appliers", None)
    if not isinstance(appliers, dict):
        appliers = {}
        setattr(tree_manager, "_graph_expand_appliers", appliers)

    graph_root_id = str(graph_root.todo_id or "")
    if not graph_root_id:
        if callable(on_finished):
            on_finished(False)
        return

    if callable(on_finished):
        callbacks_map.setdefault(graph_root_id, []).append(on_finished)

    # 去重：同一图根只允许一个后台展开任务在跑
    if graph_root_id in inflight:
        return

    # 占位子项：让用户在展开期间仍能流畅操作树与右侧面板
    item_map: Dict[str, QtWidgets.QTreeWidgetItem] = getattr(tree_manager, "_item_map", {})
    root_item = item_map.get(graph_root_id) if isinstance(item_map, dict) else None
    existing_placeholder = placeholders.get(graph_root_id)
    if existing_placeholder is not None and not _is_tree_item_alive(existing_placeholder):
        placeholders.pop(graph_root_id, None)
        existing_placeholder = None

    if _is_tree_item_alive(root_item) and existing_placeholder is None:
        placeholder_item = QtWidgets.QTreeWidgetItem()
        placeholder_item.setText(0, "正在生成节点图步骤… 0%")
        marker_role = getattr(tree_manager, "MARKER_ROLE", None)
        if isinstance(marker_role, int):
            placeholder_item.setData(0, marker_role, _GRAPH_EXPAND_PLACEHOLDER_MARKER)
        placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        placeholder_item.setData(0, Qt.ItemDataRole.UserRole, None)
        root_item.addChild(placeholder_item)
        root_item.setExpanded(True)
        placeholders[graph_root_id] = placeholder_item

    expected_package_id = str(getattr(context.package, "package_id", "") or "")
    request_id = int(getattr(tree_manager, "_graph_expand_request_id", 0)) + 1
    setattr(tree_manager, "_graph_expand_request_id", request_id)

    worker = _GraphExpandWorker(
        request_id=request_id,
        graph_root_id=graph_root_id,
        package_id=expected_package_id,
        context=context,
        parent=tree_manager,
    )
    inflight[graph_root_id] = worker

    applier = _GraphExpandResultApplier(
        tree_manager=tree_manager,
        request_id=request_id,
        graph_root_id=graph_root_id,
        expected_package_id=expected_package_id,
        context=context,
    )
    appliers[graph_root_id] = applier

    worker.expanded.connect(applier.on_expanded)
    worker.progress.connect(applier.on_progress)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(applier.on_worker_finished)
    worker.start()


def _resolve_graph_expand_context(
    tree_manager: Any,
    graph_root: TodoItem,
) -> Optional[GraphExpandContext]:
    """解析模板图根懒加载所需的上下文。"""
    detail_info = graph_root.detail_info or {}
    parent_id = str(graph_root.parent_id or "")
    graph_id = get_graph_id(detail_info)
    if not parent_id or not graph_id:
        return None

    dependency_getter = getattr(tree_manager, "_graph_expand_dependency_getter", None)
    if dependency_getter is None:
        return None

    dependencies = dependency_getter()
    if not isinstance(dependencies, tuple) or len(dependencies) not in (2, 3):
        return None
    package = dependencies[0]
    resource_manager = dependencies[1]
    package_index_manager = dependencies[2] if len(dependencies) == 3 else None
    if not package or resource_manager is None:
        return None

    preview_template_id = str(detail_info.get("template_id", "") or "")

    return GraphExpandContext(
        parent_id=parent_id,
        graph_id=graph_id,
        preview_template_id=preview_template_id,
        package=package,
        resource_manager=resource_manager,
        package_index_manager=package_index_manager,
    )


def _attach_expanded_graph_to_tree(
    tree_manager: Any,
    graph_root: TodoItem,
    context: GraphExpandContext,
    new_todos: List[TodoItem],
) -> None:
    """基于最新 todo 结构，将懒加载得到的节点挂载到树上。"""
    item_map: Dict[str, QtWidgets.QTreeWidgetItem] = getattr(tree_manager, "_item_map", {})
    todo_map: Dict[str, TodoItem] = getattr(tree_manager, "todo_map", {})

    root_item = item_map.get(graph_root.todo_id)
    build_tree_recursive = getattr(tree_manager, "_build_tree_recursive", None)
    if root_item is not None and callable(build_tree_recursive):
        build_tree_recursive(graph_root, root_item)
        root_item.setExpanded(True)

    parent_item = item_map.get(context.parent_id)
    parent_todo = todo_map.get(context.parent_id)
    if parent_item is None or parent_todo is None:
        return

    create_tree_item = getattr(tree_manager, "_create_tree_item", None)
    if not callable(create_tree_item):
        return

    for child_id in parent_todo.children:
        if child_id in item_map:
            continue
        child_todo = todo_map.get(child_id)
        if not child_todo:
            continue
        child_item = create_tree_item(child_todo)
        parent_item.addChild(child_item)
        if child_todo.children and callable(build_tree_recursive):
            build_tree_recursive(child_todo, child_item)
        detail_type = (child_todo.detail_info or {}).get("type", "")
        should_expand = not StepTypeRules.is_event_flow_root(detail_type)
        child_item.setExpanded(should_expand)


