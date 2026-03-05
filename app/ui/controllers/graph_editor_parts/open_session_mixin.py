"""GraphEditorController 的“打开/关闭编辑会话”相关 mixin。"""

from __future__ import annotations

from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.graph.graph_scene import GraphScene


class GraphEditorOpenSessionMixin:
    def open_graph_for_editing(self, graph_id: str, graph_data: dict, container=None) -> None:
        """打开节点图进行编辑（从属性面板触发）"""
        from engine.configs.settings import settings as _settings_ui

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[EDITOR] open_graph_for_editing: graph_id={graph_id}, container={'Y' if container else 'N'}")
        # 保存当前节点图
        if self.current_graph_id and self.current_graph_container:
            self.save_current_graph()

        # 切换到节点图编辑页面
        self.switch_to_editor_requested.emit()
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print("[EDITOR] 已发出 switch_to_editor_requested 信号")

        # 进入编辑器时确保能力回到“可交互 + 可校验”，避免从 TODO 预览/清缓存等路径残留只读，
        # 导致自动排版按钮被隐藏且场景仍处于只读。
        self._ensure_interactive_capabilities_for_editor()

        # 标记：本次为“用户显式打开图”，加载完成后应用镜头策略（在 _finalize_after_graph_loaded 中统一执行）
        self._pending_post_load_camera_graph_id = str(graph_id or "")

        # 加载节点图：超大图走“非阻塞”管线，避免 UI 卡死；小图保留同步加载以维持内部链路兼容性
        if self._should_use_non_blocking_load(graph_data):
            self.load_graph_non_blocking(graph_id, graph_data, container)
            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("[EDITOR] 已发起加载请求（非阻塞）")
        else:
            self.load_graph(graph_id, graph_data, container)
            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("[EDITOR] 已加载图数据到编辑视图（同步）")

    def _ensure_interactive_capabilities_for_editor(self) -> None:
        """确保编辑器会话至少处于“可交互 + 可校验”的能力集合。

        背景：
        - Todo 预览会将会话能力切到 `read_only_preview()` 以隐藏自动排版入口并禁用编辑；
        - 设置页“清除所有缓存”会关闭编辑会话并重置为只读；
        - 若随后打开节点图但能力未被恢复，右上角“自动排版”按钮会消失。
        """
        capabilities = self._session_state_machine.capabilities
        if capabilities.can_interact and capabilities.can_validate:
            return
        self.set_edit_session_capabilities(EditSessionCapabilities.interactive_preview())

    def open_independent_graph(self, graph_id: str, graph_data: dict, graph_name: str) -> None:
        """打开独立节点图（从节点图库触发）"""
        # 如目标与当前相同：直接切换到编辑器，避免重复装载
        if self.current_graph_id == graph_id:
            self.switch_to_editor_requested.emit()
            self._ensure_interactive_capabilities_for_editor()
            self.title_update_requested.emit(f"节点图: {graph_name}")
            return

        # 保存当前节点图
        if self.current_graph_id and self.current_graph_container:
            self.save_current_graph()

        # 加载节点图配置
        graph_config = GraphConfig.deserialize(graph_data)

        # 切换到节点图编辑页面
        self.switch_to_editor_requested.emit()

        # 进入编辑器时确保能力回到“可交互 + 可校验”，避免从只读路径残留只读导致编辑器按钮缺失。
        self._ensure_interactive_capabilities_for_editor()

        # 标记：本次为“用户显式打开图”，加载完成后应用镜头策略（在 _finalize_after_graph_loaded 中统一执行）
        self._pending_post_load_camera_graph_id = str(graph_id or "")

        # 加载节点图数据（独立节点图没有容器）
        if self._should_use_non_blocking_load(graph_config.data):
            self.load_graph_non_blocking(graph_id, graph_config.data, container=None)
        else:
            self.load_graph(graph_id, graph_config.data, container=None)

        # 更新窗口标题
        self.title_update_requested.emit(f"节点图: {graph_name}")

    def close_editor_session(self) -> None:
        """关闭当前节点图编辑会话并恢复空场景，用于清理缓存或强制返回列表。"""
        # 关闭会话属于“强制清理”：同时释放运行期 scene 缓存，避免占用大量内存
        self._cancel_pending_auto_layout_reparse()
        self._clear_scene_lru_cache()
        had_graph = bool(self.current_graph_id)
        if had_graph:
            self.save_current_graph()
        if self._save_debounce_timer and self._save_debounce_timer.isActive():
            self._save_debounce_timer.stop()
        if self.scene:
            self.scene.clear()
            if hasattr(self.scene, "node_items"):
                self.scene.node_items.clear()
            if hasattr(self.scene, "edge_items"):
                self.scene.edge_items.clear()
            if hasattr(self.scene, "undo_manager") and self.scene.undo_manager:
                self.scene.undo_manager.clear()
        self.model = GraphModel()
        self.scene = GraphScene(
            self.model,
            read_only=True,
            node_library=self.node_library,
            edit_session_capabilities=EditSessionCapabilities.read_only_preview(),
        )
        self.scene.undo_manager.on_change_callback = None
        self.scene.on_data_changed = None
        if self.view is not None:
            self.view.setScene(self.scene)
            self.view.resetTransform()
            self.view.viewport().update()
        self._session_state_machine.on_graph_closed()
        self.current_graph_container = None
        self._force_reparse_on_next_auto_layout = False
        self.set_edit_session_capabilities(EditSessionCapabilities.read_only_preview())
        self.title_update_requested.emit("节点图: 未打开")

    def get_current_model(self) -> GraphModel:
        """获取当前模型"""
        return self.model

    def get_current_scene(self) -> GraphScene:
        """获取当前场景"""
        return self.scene

    def set_scene_extra_options(self, options: dict) -> None:
        """设置场景额外参数（例如复合节点编辑上下文）

        Args:
            options: 传入 GraphScene 的关键字参数字典
        """
        self._scene_extra_options = options or {}

