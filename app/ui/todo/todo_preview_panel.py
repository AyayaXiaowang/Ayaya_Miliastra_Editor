from __future__ import annotations

from typing import Optional, Tuple
from pathlib import Path

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from engine.graph.models.graph_model import GraphModel
from ui.graph.graph_scene import GraphScene
from ui.graph.graph_view import GraphView
from ui.composite.composite_node_preview_widget import CompositeNodePreviewWidget
from ui.todo.todo_config import TodoStyles, LayoutConstants, StepTypeRules
from ui.todo.todo_preview_controller import TodoPreviewController
from ui.todo.todo_widgets import create_execute_button
from engine.configs.settings import settings


class TodoPreviewPanel(QtWidgets.QWidget):
    """右侧预览面板：加载/缓存、聚焦/高亮，并与控制器内聚。

    对外暴露：
    - preview_view: GraphView（供主窗口连接 jump_to_graph_element 信号）
    - execute_clicked、back_to_detail 请求信号
    - edit_requested(graph_id, graph_data, container)
    - recognition_focus_succeeded 透传（供执行桥接层联动）
    """

    execute_clicked = QtCore.pyqtSignal()
    execute_remaining_clicked = QtCore.pyqtSignal()
    back_to_detail_requested = QtCore.pyqtSignal()
    edit_requested = QtCore.pyqtSignal(str, dict, object)
    recognition_focus_succeeded = QtCore.pyqtSignal(list)
    # 预览中的节点/连线/空白单击信号（主要用于任务清单联动）
    node_clicked = QtCore.pyqtSignal(str)
    related_edge_clicked = QtCore.pyqtSignal(str, str, str)
    background_clicked = QtCore.pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_graph_id: Optional[str] = None
        self.current_graph_data: Optional[dict] = None
        self.current_template_or_instance = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        toolbar = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)

        self.back_button = QtWidgets.QPushButton("← 返回详情")
        self.back_button.setStyleSheet(TodoStyles.back_button_qss())
        self.back_button.clicked.connect(self.back_to_detail_requested.emit)
        toolbar_layout.addWidget(self.back_button)

        self.execute_button = create_execute_button(
            toolbar,
            self.execute_clicked.emit,
        )
        toolbar_layout.addWidget(self.execute_button)

        # 执行剩余步骤（预览工具条版本）
        self.execute_remaining_button = QtWidgets.QPushButton("执行剩余步骤")
        self.execute_remaining_button.setStyleSheet(TodoStyles.execute_button_qss())
        self.execute_remaining_button.setVisible(False)
        # 将按钮点击转发为自身信号（供宿主连接）
        self.execute_remaining_button.clicked.connect(self.execute_remaining_clicked.emit)
        toolbar_layout.addWidget(self.execute_remaining_button)

        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        # 预览视图（只读）
        self.preview_model = GraphModel()
        self.preview_scene = GraphScene(self.preview_model, read_only=True)
        self.preview_view = GraphView(self.preview_scene)
        self.preview_view.setObjectName("previewGraphView")
        self.preview_view.setMinimumHeight(LayoutConstants.PREVIEW_VIEW_MIN_HEIGHT)
        self.preview_view.read_only = True
        # 只读预览下开启“单击图元素”信号，供任务清单联动使用
        self.preview_view.enable_click_signals = True
        self.preview_view.show_coordinates = True
        self.preview_view.node_library = {}
        if hasattr(self.preview_view, 'auto_layout_button'):
            self.preview_view.auto_layout_button.setVisible(False)

        # 右上角“编辑”按钮
        self.preview_edit_button = QtWidgets.QPushButton("编辑", self.preview_view)
        self.preview_edit_button.setObjectName("previewEditButton")
        self.preview_edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_edit_button.setStyleSheet(TodoStyles.execute_button_qss())
        self.preview_edit_button.clicked.connect(self._emit_edit_requested)
        if hasattr(self.preview_view, 'set_extra_top_right_button'):
            self.preview_view.set_extra_top_right_button(self.preview_edit_button)
        else:
            self.preview_edit_button.move(self.preview_view.width() - self.preview_edit_button.sizeHint().width() - 10, 10)

        layout.addWidget(self.preview_view)

        # 复合节点预览子卡片（外部控制是否切换到此卡片）
        self.composite_preview_widget = CompositeNodePreviewWidget()

        self.preview_controller = TodoPreviewController(self.preview_view)

        # 将底层视图的点击事件转成更语义化的预览信号
        if hasattr(self.preview_view, "graph_element_clicked"):
            self.preview_view.graph_element_clicked.connect(self._on_graph_element_clicked)

    # === 预览內部交互映射 ===

    def _on_graph_element_clicked(self, info: dict) -> None:
        if not isinstance(info, dict):
            return
        element_type = info.get("type", "")
        if element_type == "node":
            node_id = str(info.get("node_id") or "")
            if node_id:
                self.node_clicked.emit(node_id)
        elif element_type == "edge":
            edge_id = str(info.get("edge_id") or "")
            src_node = str(info.get("src_node") or "")
            dst_node = str(info.get("dst_node") or "")
            if edge_id and src_node and dst_node:
                self.related_edge_clicked.emit(edge_id, src_node, dst_node)
        elif element_type == "background":
            self.background_clicked.emit()

    # === 外部交互 ===

    def set_execute_visible(self, visible: bool) -> None:
        self.execute_button.setVisible(visible)

    def set_execute_remaining_visible(self, visible: bool) -> None:
        self.execute_remaining_button.setVisible(visible)

    def set_execute_text(self, text: str) -> None:
        self.execute_button.setText(text)

    def set_execute_remaining_text(self, text: str) -> None:
        self.execute_remaining_button.setText(text)

    def get_current_graph_info(self) -> Tuple[Optional[str], Optional[dict], object]:
        return (self.current_graph_id, self.current_graph_data, self.current_template_or_instance)

    def bind_monitor_panel(self, monitor_panel, workspace_path: Path, recognition_slot=None) -> None:
        if monitor_panel and hasattr(monitor_panel, 'set_context') and callable(getattr(monitor_panel, 'set_context')):
            monitor_panel.set_context(workspace_path, self.preview_model, self.preview_view)
            if hasattr(monitor_panel, 'recognition_focus_succeeded'):
                if recognition_slot is not None:
                    # 直接连到外部槽，或透传到自身信号
                    monitor_panel.recognition_focus_succeeded.connect(recognition_slot)
                else:
                    monitor_panel.recognition_focus_succeeded.connect(self.recognition_focus_succeeded.emit)

    # === 预览加载 ===

    def handle_graph_preview(self, todo, todo_map: dict[str, object], main_window) -> bool:
        """根据 todo 切换/加载预览并聚焦。
        返回是否显示预览（True → 应切换到预览页）。
        """
        info = todo.detail_info or {}
        detail_type = info.get("type", "")

        # 非图相关步骤直接回退到详情页；图相关但显式标记为“仅详情展示”的同样不切到预览。
        if not StepTypeRules.is_graph_step(detail_type):
            return False
        if not StepTypeRules.should_preview_graph(detail_type):
            return False

        # 注入节点库：供类型相关的高亮使用（例如仅高亮“泛型家族”端口）
        if main_window and hasattr(main_window, 'library') and getattr(main_window, 'library'):
            self.preview_view.node_library = main_window.library
            if hasattr(self, 'preview_scene') and self.preview_scene:
                self.preview_scene.node_library = main_window.library
        # 缓存 todo_map 供事件流聚焦时收集节点ID
        self.todo_map = todo_map

        # 父级：事件流/图根也应进入预览（事件流 → 聚焦相关节点组；图根 → 适应全图）
        if StepTypeRules.is_graph_root(detail_type):
            graph_data, graph_id, template_or_instance = self.preview_controller.get_graph_data_id_and_container(
                todo,
                todo_map,
                main_window,
                getattr(main_window, "todo_tree_manager", None) if main_window is not None else None,
            )
            if graph_data:
                previous_graph_id = self.current_graph_id
                previous_graph_data = self.current_graph_data

                is_same_graph_id = (
                    (previous_graph_id == graph_id)
                    or (previous_graph_id is None and (graph_id is None or graph_id == ""))
                )
                is_same_graph = (
                    bool(getattr(self, "preview_scene", None))
                    and is_same_graph_id
                    and (previous_graph_data is graph_data)
                )

                self.current_graph_id = graph_id
                self.current_template_or_instance = template_or_instance
                self.current_graph_data = graph_data

                if not is_same_graph:
                    if settings.PREVIEW_VERBOSE:
                        print(
                            "[PREVIEW] (root) 预览切换 → 重建场景: "
                            f"prev_id={previous_graph_id}, curr_id={graph_id}"
                        )
                    self._load_graph_preview(graph_data)
                    # 重建场景后同步节点库
                    if main_window and hasattr(main_window, 'library') and getattr(main_window, 'library'):
                        self.preview_view.node_library = main_window.library
                        if hasattr(self, 'preview_scene') and self.preview_scene:
                            self.preview_scene.node_library = main_window.library
                else:
                    if settings.PREVIEW_VERBOSE:
                        print(f"[PREVIEW] (root) 复用现有预览场景: graph_id={graph_id}")

                # 聚焦：事件流 -> 收集子步骤节点组；图根 -> 适应全图
                self._focus_and_highlight_task(todo)
                return True
            return False

        if StepTypeRules.should_preview_graph(detail_type):
            graph_data, graph_id, template_or_instance = self.preview_controller.get_graph_data_id_and_container(
                todo,
                todo_map,
                main_window,
                getattr(main_window, "todo_tree_manager", None) if main_window is not None else None,
            )
            # 放宽条件：只要有 graph_data 即可展示预览；graph_id 可为空
            if graph_data:
                previous_graph_id = self.current_graph_id
                previous_graph_data = self.current_graph_data

                is_same_graph_id = (
                    (previous_graph_id == graph_id)
                    or (previous_graph_id is None and (graph_id is None or graph_id == ""))
                )
                is_same_graph = (
                    bool(getattr(self, "preview_scene", None))
                    and is_same_graph_id
                    and (previous_graph_data is graph_data)
                )

                self.current_graph_id = graph_id
                self.current_template_or_instance = template_or_instance
                self.current_graph_data = graph_data

                if not is_same_graph:
                    if settings.PREVIEW_VERBOSE:
                        print(
                            "[PREVIEW] 预览切换 → 重建场景: "
                            f"prev_id={previous_graph_id}, curr_id={graph_id}"
                        )
                    self._load_graph_preview(graph_data)
                    # 重建场景后同步节点库
                    if main_window and hasattr(main_window, 'library') and getattr(main_window, 'library'):
                        self.preview_view.node_library = main_window.library
                        if hasattr(self, 'preview_scene') and self.preview_scene:
                            self.preview_scene.node_library = main_window.library
                else:
                    if settings.PREVIEW_VERBOSE:
                        print(f"[PREVIEW] 复用现有预览场景: graph_id={graph_id}")

                self._focus_and_highlight_task(todo)
                return True
            return False
        return False

    def handle_composite_preview(self, todo, main_window) -> bool:
        detail_type = todo.detail_info.get("type", "")
        if not StepTypeRules.is_composite_step(detail_type):
            return False
        info = todo.detail_info
        composite_id = info.get("composite_id", "") or (getattr(todo, 'target_id', ""))
        if not composite_id:
            return False
        workspace_path = None
        if main_window and hasattr(main_window, 'workspace_path'):
            workspace_path = Path(main_window.workspace_path)
        if not workspace_path:
            return False
        graph_data, composite_obj = self.preview_controller.load_composite_internal_graph(composite_id, workspace_path)
        if graph_data and isinstance(graph_data, dict) and ("nodes" in graph_data or "edges" in graph_data):
            self._load_graph_preview(graph_data)
            self.preview_controller.focus_composite_task(todo, composite_obj)
            return True
        return False

    # === 内部 ===

    def _emit_edit_requested(self) -> None:
        gid, gdata, container = self.get_current_graph_info()
        if gid and isinstance(gdata, dict):
            self.edit_requested.emit(gid, gdata, container)

    def _load_graph_preview(self, graph_data: dict) -> None:
        self.preview_model, self.preview_scene = self.preview_controller.load_graph_preview(graph_data)

        # 为预览场景注入信号编辑上下文，使“发送信号/监听信号”节点在只读预览中也能补全参数端口，
        # 保持与节点图编辑器/节点图库中看到的节点形态一致。
        main_window = self.window()
        if main_window is None:
            return
        if not hasattr(main_window, "package_controller"):
            return

        # signal_edit_context 约定：
        # - get_current_package: Callable[[], PackageView | None]
        # - main_window: QMainWindow（可选，用于对话框父窗口）
        signal_edit_context = {
            "get_current_package": lambda: main_window.package_controller.current_package,  # type: ignore[attr-defined]
            "main_window": main_window,
        }
        if hasattr(self.preview_scene, "signal_edit_context"):
            self.preview_scene.signal_edit_context = signal_edit_context  # type: ignore[attr-defined]

        # 根据信号定义为当前图中的信号节点补全参数端口，仅新增缺失端口，不主动删除。
        from ui.graph.signal_node_service import on_signals_updated_from_manager

        on_signals_updated_from_manager(self.preview_scene)

    def _focus_and_highlight_task(self, todo) -> None:
        detail_type = todo.detail_info.get("type", "")
        if StepTypeRules.is_event_flow_root(detail_type):
            # 极少用到：此处仅保留逻辑完整
            node_ids = self._collect_nodes_from_subtasks(todo, getattr(self, 'todo_map', {}))
            todo.detail_info["_flow_node_ids"] = node_ids
        self.preview_controller.focus_and_highlight_task(todo)

    def _collect_nodes_from_subtasks(self, todo, todo_map: dict) -> list[str]:
        node_ids: list[str] = []
        def collect_from_task(task_id: str):
            task = todo_map.get(task_id)
            if not task:
                return
            node_id = task.detail_info.get("node_id")
            if node_id and node_id not in node_ids:
                node_ids.append(node_id)
            src_node = task.detail_info.get("src_node")
            dst_node = task.detail_info.get("dst_node")
            if src_node and src_node not in node_ids:
                node_ids.append(src_node)
            if dst_node and dst_node not in node_ids:
                node_ids.append(dst_node)
            prev_node_id = task.detail_info.get("prev_node_id")
            if prev_node_id and prev_node_id not in node_ids:
                node_ids.append(prev_node_id)
            branch_node_id = task.detail_info.get("branch_node_id")
            if branch_node_id and branch_node_id not in node_ids:
                node_ids.append(branch_node_id)
            for child_id in task.children:
                collect_from_task(child_id)
        collect_from_task(todo.todo_id)
        return node_ids


