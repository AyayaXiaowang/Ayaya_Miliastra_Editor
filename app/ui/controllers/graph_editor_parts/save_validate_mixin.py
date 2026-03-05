"""GraphEditorController 的保存/校验/编辑操作 mixin。"""

from __future__ import annotations

from PyQt6 import QtCore

from app.ui.controllers.graph_editor_flow import derive_initial_input_names_for_new_node
from app.ui.graph.graph_undo import AddNodeCommand
from engine.configs.settings import settings as _settings
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.logging.logger import log_error


class GraphEditorSaveValidateMixin:
    def save_current_graph(self) -> None:
        """保存当前节点图（仅当内容变化时）

        统一保存入口：所有节点图保存必须通过此方法
        - 保存前：验证数据完整性
        - 保存中：序列化并生成代码
        - 保存后：验证结果并更新UI
        """
        if not self.current_graph_id:
            return

        # 计算当前内容哈希（不含位置信息）
        current_hash = self.model.get_content_hash()
        if not self._session_state_machine.has_unsaved_changes(current_content_hash=current_hash):
            return

        # 不可保存会话：不写入资源（避免“看起来能保存”），仅维持基线与只读提示。
        if not self._session_state_machine.capabilities.can_persist:
            if getattr(_settings, "GRAPH_UI_VERBOSE", False):
                print(f"[保存] 当前会话不可保存（不落盘），跳过写入: {self.current_graph_id}")
            new_status = self._session_state_machine.on_modified(current_content_hash=current_hash)
            self.save_status_changed.emit(new_status)
            return

        # 非只读：正常保存
        if getattr(_settings, "GRAPH_UI_VERBOSE", False):
            print(f"[保存] 检测到内容变化，开始保存: {self.current_graph_id}")
        self.save_status_changed.emit(self._session_state_machine.on_save_started())

        save_result = self._save_service.save_graph(
            resource_manager=self.resource_manager,
            graph_id=str(self.current_graph_id),
            model=self.model,
        )
        if not save_result.success:
            error_message = save_result.error_message or "节点图保存失败"
            log_error(
                "[保存] 保存被阻止: {} (code={})",
                str(self.current_graph_id),
                str(save_result.error_code or "unknown_error"),
            )
            self.save_status_changed.emit(self._session_state_machine.on_save_failed())
            self.error_tracker.mark_error(
                self.current_graph_id,
                error_message,
                str(save_result.error_code or "save_failed"),
            )
            return

        self.save_status_changed.emit(
            self._session_state_machine.on_save_succeeded(new_baseline_content_hash=current_hash)
        )
        if getattr(_settings, "GRAPH_UI_VERBOSE", False):
            print(f"✅ [保存] 完成: {self.current_graph_id}")
        self.error_tracker.clear_error(self.current_graph_id)
        if self._session_state_machine.capabilities.can_validate:
            self.validate_current_graph()
        self.graph_saved.emit(self.current_graph_id)

    def validate_current_graph(self) -> None:
        """验证当前编辑的节点图并更新UI显示"""
        if not self._session_state_machine.capabilities.can_validate:
            return
        if not self.get_current_package or not self.get_property_panel_object_type:
            return

        current_package = self.get_current_package()
        if not current_package or not self.current_graph_container:
            return

        # 确定实体类型（由验证服务推导）
        object_type = self.get_property_panel_object_type()

        issues = self._validate_service.validate_for_ui(
            model=self.model,
            resource_manager=self.resource_manager,
            current_package=current_package,
            current_container=self.current_graph_container,
            object_type=str(object_type or ""),
            graph_id=str(self.current_graph_id or ""),
        )

        self.scene.update_validation(issues)
        self.graph_validated.emit(issues)

    def add_node_at_position(self, node_def: NodeDef, scene_pos: QtCore.QPointF) -> None:
        """添加节点"""
        if getattr(_settings, "GRAPH_UI_VERBOSE", False):
            print(f"[添加节点] 准备添加节点: {node_def.name}")
            print(f"[添加节点] 添加前Model中有 {len(self.model.nodes)} 个节点")

        node_id = self.model.gen_id("node")

        # 新建节点的“初始端口策略”统一收敛到 flow service，避免控制器硬编码业务分支。
        input_names = derive_initial_input_names_for_new_node(node_def)

        cmd = AddNodeCommand(
            self.model,
            self.scene,
            node_id,
            node_def.name,
            node_def.category,
            input_names,
            node_def.outputs,
            pos=(scene_pos.x(), scene_pos.y()),
        )
        self.scene.undo_manager.execute_command(cmd)

        if getattr(_settings, "GRAPH_UI_VERBOSE", False):
            print(f"[添加节点] 添加后Model中有 {len(self.model.nodes)} 个节点")
            print(f"[添加节点] Scene.model中有 {len(self.scene.model.nodes)} 个节点")

    def _on_graph_modified(self) -> None:
        """节点图被修改时的回调 - 触发自动保存"""
        current_hash = self.model.get_content_hash()
        if not self._session_state_machine.capabilities.can_persist:
            # 不落盘会话：保持“只读/不落盘”提示，并将当前快照视为基线，避免把包标记为脏。
            self.save_status_changed.emit(
                self._session_state_machine.on_modified(current_content_hash=current_hash)
            )
            return

        # 可保存会话：标记为脏状态并按全局设置触发自动保存
        self.save_status_changed.emit(
            self._session_state_machine.on_modified(current_content_hash=current_hash)
        )

        # 基于全局设置的自动保存防抖（单位：秒；0 表示立即保存）
        interval_seconds = float(getattr(_settings, "AUTO_SAVE_INTERVAL", 0.0) or 0.0)
        if interval_seconds <= 0.0:
            self.save_current_graph()
            return
        # 延迟保存：合并短时间内的频繁修改
        if self._save_debounce_timer is None:
            self._save_debounce_timer = QtCore.QTimer(self)
            self._save_debounce_timer.setSingleShot(True)
            self._save_debounce_timer.timeout.connect(self.save_current_graph)
        # 重启计时器
        self._save_debounce_timer.start(int(interval_seconds * 1000))

    def mark_as_dirty(self) -> None:
        """标记节点图为未保存状态"""
        if not self._session_state_machine.capabilities.can_persist:
            return
        current_hash = self.model.get_content_hash()
        self.save_status_changed.emit(
            self._session_state_machine.on_modified(current_content_hash=current_hash)
        )

    def mark_as_saved(self) -> None:
        """标记节点图为已保存状态"""
        current_hash = self.model.get_content_hash()
        self.save_status_changed.emit(
            self._session_state_machine.on_save_succeeded(new_baseline_content_hash=current_hash)
        )

    @property
    def is_dirty(self) -> bool:
        """判断是否有未保存的修改"""
        current_hash = self.model.get_content_hash() if self.model is not None else None
        return self._session_state_machine.has_unsaved_changes(current_content_hash=current_hash)

