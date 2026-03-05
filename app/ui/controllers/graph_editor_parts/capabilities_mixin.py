"""GraphEditorController 的会话能力同步与兼容字段 mixin。"""

from __future__ import annotations

from typing import Optional

from app.models.edit_session_capabilities import EditSessionCapabilities


class GraphEditorCapabilitiesMixin:
    # === EditSessionCapabilities + save_status（单一真源：状态机） ===

    @property
    def edit_session_capabilities(self) -> EditSessionCapabilities:
        return self._session_state_machine.capabilities

    def set_edit_session_capabilities(self, capabilities: EditSessionCapabilities) -> None:
        current_hash = self.model.get_content_hash() if self.model is not None else None
        new_status = self._session_state_machine.set_capabilities(
            capabilities, current_content_hash=current_hash
        )
        self._apply_edit_session_capabilities_to_view_and_scene()
        self.save_status_changed.emit(new_status)

    def _apply_edit_session_capabilities_to_view_and_scene(self) -> None:
        capabilities = self._session_state_machine.capabilities
        if self.view is not None and hasattr(self.view, "set_edit_session_capabilities"):
            self.view.set_edit_session_capabilities(capabilities)
        if self.scene is not None and hasattr(self.scene, "set_edit_session_capabilities"):
            self.scene.set_edit_session_capabilities(capabilities)

        if self.view is not None:
            # “添加节点”入口仅在可交互会话开放
            self.view.on_add_node_callback = (
                self.add_node_at_position if capabilities.can_interact else None
            )

    # === 兼容字段：logic_read_only（历史语义） ===

    @property
    def logic_read_only(self) -> bool:
        """历史字段：映射为“不可保存到资源落盘”。

        说明：当前语义由 `EditSessionCapabilities.can_persist` 表达。
        """
        return not self._session_state_machine.capabilities.can_persist

    @logic_read_only.setter
    def logic_read_only(self, value: bool) -> None:
        # 兼容旧写法：只改“可保存”能力位；可保存要求可校验，交由 EditSessionCapabilities 自身约束。
        self.set_edit_session_capabilities(
            self._session_state_machine.capabilities.with_overrides(can_persist=not bool(value))
        )

    @property
    def current_graph_id(self) -> Optional[str]:
        """当前图 id：由状态机持有，避免与 save_status/baseline 分叉。"""
        return self._session_state_machine.current_graph_id

    @current_graph_id.setter
    def current_graph_id(self, value: Optional[str]) -> None:
        # 兼容旧代码：允许外部清空 current_graph_id（例如缓存清理回退逻辑）。
        if value is None:
            self._session_state_machine.on_graph_closed()
            return
        self._session_state_machine.current_graph_id = str(value)

