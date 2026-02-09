from __future__ import annotations

"""共享 GraphView 的租约服务（集中管理跨页面复用画布的状态机）。

背景：
- 应用中存在全局唯一的 `app_state.graph_view`；
- 该画布会在 `ViewMode.GRAPH_EDITOR` 与 `ViewMode.TODO` 的预览页之间移动复用；
- 画布复用必须同时管理：Host 容器归属、会话能力（只读/可编辑）、右上角浮动按钮、联动点击信号等。

约束：
- 不吞异常：状态机违规应立即抛错暴露；
- 仅管理“共享画布”的租约，不涉及复合节点的独立预览画布。
"""

from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.graph.graph_canvas_host import GraphCanvasHost
from app.ui.graph.graph_view_impl import GraphView


@dataclass(frozen=True)
class _CapabilitySnapshot:
    graph_controller: object
    previous: EditSessionCapabilities


@dataclass(frozen=True)
class _ViewStateSnapshot:
    """共享画布的视图状态快照（用于跨页面借还时恢复缩放/镜头）。"""

    transform: QtGui.QTransform
    center_scene_pos: QtCore.QPointF


class SharedGraphViewLeaseManager:
    """全局唯一 GraphView 的租约管理器。"""

    OWNER_GRAPH_EDITOR = "GRAPH_EDITOR"
    OWNER_TODO_PREVIEW = "TODO_PREVIEW"

    def __init__(self) -> None:
        self._owner: str | None = None
        self._graph_editor_host: GraphCanvasHost | None = None
        self._todo_preview_host: GraphCanvasHost | None = None
        self._capability_snapshot: _CapabilitySnapshot | None = None
        # 视图状态快照：用于避免 TODO 预览侧的 fit_all/聚焦改变“污染”编辑器视图缩放。
        self._graph_editor_view_snapshot: _ViewStateSnapshot | None = None
        self._todo_preview_view_snapshot: _ViewStateSnapshot | None = None

    # --------------------------------------------------------------------- View state snapshot/restore
    def _snapshot_view_state(self, graph_view: GraphView) -> _ViewStateSnapshot | None:
        if graph_view is None:
            return None
        scene = graph_view.scene()
        viewport = graph_view.viewport()
        if scene is None or viewport is None:
            return None
        center_scene_pos = graph_view.mapToScene(viewport.rect().center())
        transform_copy = QtGui.QTransform(graph_view.transform())
        return _ViewStateSnapshot(transform=transform_copy, center_scene_pos=center_scene_pos)

    def _restore_view_state(self, graph_view: GraphView, snapshot: _ViewStateSnapshot) -> None:
        if graph_view is None or snapshot is None:
            return
        old_anchor = graph_view.transformationAnchor()
        old_resize_anchor = graph_view.resizeAnchor()
        graph_view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        graph_view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        graph_view.setTransform(snapshot.transform)
        graph_view.centerOn(snapshot.center_scene_pos)
        graph_view.setTransformationAnchor(old_anchor)
        graph_view.setResizeAnchor(old_resize_anchor)

    def _ensure_reasonable_scale(self, graph_view: GraphView) -> None:
        """避免共享画布处于极小缩放（典型：预览侧 fit_all 后借回编辑器）。"""
        if graph_view is None:
            return
        scale = float(graph_view.transform().m11())
        if scale < 0.10:
            graph_view.resetTransform()

    # --------------------------------------------------------------------- Introspection
    @property
    def owner(self) -> str | None:
        return self._owner

    # --------------------------------------------------------------------- Acquire / release
    def acquire_for_todo_preview(
        self,
        *,
        graph_view: GraphView,
        todo_preview_host: GraphCanvasHost,
        graph_controller: object | None,
        preview_edit_button: object | None,
        node_library: object | None,
    ) -> None:
        """将共享画布借给 Todo 预览页，并切只读能力与联动开关。"""
        if self._owner == self.OWNER_TODO_PREVIEW:
            if self._todo_preview_host is todo_preview_host:
                return
            raise RuntimeError("共享画布已被 Todo 预览占用，但 host 不一致：疑似重复构造或跨窗口复用。")

        # 记录 host（用于后续 release 做一致性校验）
        self._todo_preview_host = todo_preview_host
        self._owner = self.OWNER_TODO_PREVIEW

        # 0) 快照编辑器视图状态（缩放/镜头），避免预览侧 fit_all 导致回到编辑器仍处于“压缩状态”
        editor_snapshot = self._snapshot_view_state(graph_view)
        if editor_snapshot is not None:
            self._graph_editor_view_snapshot = editor_snapshot

        # 1) 挂载到 Todo Host
        todo_preview_host.attach_view(graph_view)

        # 1.5) 恢复上一次预览视图状态（若存在），保持预览体验一致
        if self._todo_preview_view_snapshot is not None:
            self._restore_view_state(graph_view, self._todo_preview_view_snapshot)

        # 2) 注入节点库（供只读预览高亮/端口类型推断等能力使用）
        if node_library is not None and hasattr(graph_view, "node_library"):
            graph_view.node_library = node_library
            current_scene = graph_view.scene()
            if current_scene is not None and hasattr(current_scene, "node_library"):
                current_scene.node_library = node_library

        # 3) 预览页需要图元素点击信号与坐标显示
        if hasattr(graph_view, "enable_click_signals"):
            graph_view.enable_click_signals = True
        if hasattr(graph_view, "show_coordinates"):
            graph_view.show_coordinates = True

        # 4) 右上角按钮切到“编辑”（按钮的 parent 会被 GraphView 接管）
        if preview_edit_button is not None and hasattr(preview_edit_button, "setVisible"):
            preview_edit_button.setVisible(True)
        if preview_edit_button is not None and hasattr(graph_view, "set_extra_top_right_button"):
            graph_view.set_extra_top_right_button(preview_edit_button)
        # 4.5) 预览场景隐藏插件扩展按钮，避免出现不相关入口
        set_extensions_visible = getattr(graph_view, "set_top_right_extensions_visible", None)
        if callable(set_extensions_visible):
            set_extensions_visible(False)

        # 5) 切只读会话能力（并记录快照用于回切）
        if graph_controller is None:
            return
        current_capabilities = getattr(graph_controller, "edit_session_capabilities", None)
        if isinstance(current_capabilities, EditSessionCapabilities):
            self._capability_snapshot = _CapabilitySnapshot(
                graph_controller=graph_controller,
                previous=current_capabilities,
            )
            set_capabilities = getattr(graph_controller, "set_edit_session_capabilities", None)
            if callable(set_capabilities):
                set_capabilities(EditSessionCapabilities.read_only_preview())

    def release_to_graph_editor(
        self,
        *,
        graph_view: GraphView,
        graph_editor_host: GraphCanvasHost,
        graph_controller: object | None,
        graph_editor_todo_button: object | None,
        todo_preview_edit_button: object | None,
    ) -> None:
        """将共享画布归还给图编辑器，并恢复交互能力与编辑器右上角按钮。"""
        if self._owner == self.OWNER_GRAPH_EDITOR:
            if self._graph_editor_host is graph_editor_host:
                return
            raise RuntimeError("共享画布已归属图编辑器，但 host 不一致：疑似重复构造或跨窗口复用。")

        self._graph_editor_host = graph_editor_host
        self._owner = self.OWNER_GRAPH_EDITOR

        # 0) 快照预览页视图状态（用于下次回到预览时恢复）
        preview_snapshot = self._snapshot_view_state(graph_view)
        if preview_snapshot is not None:
            self._todo_preview_view_snapshot = preview_snapshot

        # 1) 挂回编辑器 Host
        graph_editor_host.attach_view(graph_view)

        # 1.5) 恢复编辑器视图状态（缩放/镜头）。若缺失快照，则至少避免极小缩放。
        if self._graph_editor_view_snapshot is not None:
            self._restore_view_state(graph_view, self._graph_editor_view_snapshot)
        else:
            self._ensure_reasonable_scale(graph_view)

        # 2) 关闭 Todo 预览联动开关，并清理预览遗留的视觉状态
        if hasattr(graph_view, "enable_click_signals"):
            graph_view.enable_click_signals = False
        if hasattr(graph_view, "restore_all_opacity"):
            graph_view.restore_all_opacity()
        overlay_manager = getattr(graph_view, "overlay_manager", None)
        if overlay_manager is not None and hasattr(overlay_manager, "stop_all_animations"):
            overlay_manager.stop_all_animations()

        # 3) 隐藏 Todo 预览右上角按钮，并恢复编辑器按钮
        if todo_preview_edit_button is not None and hasattr(todo_preview_edit_button, "setVisible"):
            todo_preview_edit_button.setVisible(False)
        if graph_editor_todo_button is not None and hasattr(graph_view, "set_extra_top_right_button"):
            graph_view.set_extra_top_right_button(graph_editor_todo_button)
        # 3.5) 编辑器场景恢复插件扩展按钮可见性
        set_extensions_visible = getattr(graph_view, "set_top_right_extensions_visible", None)
        if callable(set_extensions_visible):
            set_extensions_visible(True)

        # 4) 恢复会话能力（至少允许交互与校验）
        if graph_controller is None:
            self._capability_snapshot = None
            return

        restored_capabilities: EditSessionCapabilities | None = None
        if (
            self._capability_snapshot is not None
            and self._capability_snapshot.graph_controller is graph_controller
        ):
            restored_capabilities = self._capability_snapshot.previous
        self._capability_snapshot = None

        current_capabilities = getattr(graph_controller, "edit_session_capabilities", None)
        base_capabilities = (
            restored_capabilities
            if restored_capabilities is not None
            else (current_capabilities if isinstance(current_capabilities, EditSessionCapabilities) else None)
        )
        if base_capabilities is None:
            return
        set_capabilities = getattr(graph_controller, "set_edit_session_capabilities", None)
        if not callable(set_capabilities):
            return
        if base_capabilities.can_interact and base_capabilities.can_validate:
            set_capabilities(base_capabilities)
            return
        set_capabilities(
            base_capabilities.with_overrides(
                can_interact=True,
                can_validate=True,
            )
        )


_shared_lease_manager: SharedGraphViewLeaseManager | None = None


def get_shared_graph_view_lease_manager() -> SharedGraphViewLeaseManager:
    global _shared_lease_manager
    if _shared_lease_manager is None:
        _shared_lease_manager = SharedGraphViewLeaseManager()
    return _shared_lease_manager


