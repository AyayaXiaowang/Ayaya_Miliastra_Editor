from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from engine.graph.models import GraphModel, NodeModel, EdgeModel
from engine.nodes.composite_virtual_pin_undo_helper import (
    CompositeVirtualPinSnapshot,
    snapshot_virtual_pins_for_node,
    restore_virtual_pins_from_snapshot,
)
from engine.utils.logging.logger import log_info, log_warn
from engine.utils.undo.undo_redo_core import (
    Command,
    UndoRedoManager as CoreUndoRedoManager,
    AddNodeModelCommand,
    DeleteNodeModelCommand,
    AddEdgeModelCommand,
    DeleteEdgeModelCommand,
    MoveNodeModelCommand,
)

if TYPE_CHECKING:
    from app.ui.graph.graph_scene import GraphScene


UndoRedoManager = CoreUndoRedoManager


class AddNodeCommand(Command):
    """添加节点命令（UI 封装）

    - 通过 AddNodeModelCommand 修改 GraphModel
    - 通过 GraphScene.add_node_item 更新 UI
    """

    def __init__(
        self,
        model: GraphModel,
        scene: GraphScene,
        node_id: str,
        title: str,
        category: str,
        input_names: list[str],
        output_names: list[str],
        pos: tuple[float, float],
    ):
        self.model = model
        self.scene = scene
        self.node_id = node_id
        self.title = title
        self.category = category
        self.input_names = input_names
        self.output_names = output_names
        self.pos = pos
        self._model_command = AddNodeModelCommand(
            model=model,
            node_id=node_id,
            title=title,
            category=category,
            input_names=input_names,
            output_names=output_names,
            pos=pos,
        )
        self.node: Optional[NodeModel] = None

    def _apply_composite_id_from_library(self) -> None:
        if not hasattr(self.scene, "node_library") or not self.scene.node_library:
            return
        node = self.node
        if node is None:
            return

        # 先尝试"复合节点"分类，再回退到当前 category
        node_key = f"复合节点/{self.title}"
        node_def = self.scene.node_library.get(node_key)

        if not node_def:
            node_key = f"{self.category}/{self.title}"
            node_def = self.scene.node_library.get(node_key)

        if node_def and hasattr(node_def, "composite_id") and node_def.composite_id:
            node.composite_id = node_def.composite_id
            log_info("[命令] 设置复合节点ID: {}", node_def.composite_id)

    def execute(self) -> None:
        log_info(
            "[命令] 添加节点: {} (输入:{}, 输出:{})",
            self.title,
            self.input_names,
            self.output_names,
        )
        self._model_command.execute()
        self.node = self._model_command.node
        self._apply_composite_id_from_library()
        if self.node is not None:
            self.scene.add_node_item(self.node)
            log_info("[命令] 节点添加完成: {}", self.node_id)

    def undo(self) -> None:
        if self.node is not None:
            self.scene._remove_node_graphics(self.node_id)
        self._model_command.undo()
        self.node = None


class DeleteNodeCommand(Command):
    """删除节点命令（UI 封装）

    - DeleteNodeModelCommand 负责 GraphModel 中删除节点及相关连线
    - 本命令负责：
      - 删除/恢复 QGraphicsItem
      - 复合节点编辑器中的虚拟引脚快照与恢复
      - 调用 GraphScene.cleanup_virtual_pins_for_deleted_node 刷新 UI
    """

    def __init__(self, model: GraphModel, scene: GraphScene, node_id: str):
        self.model = model
        self.scene = scene
        self.node_id = node_id
        self._model_command = DeleteNodeModelCommand(model, node_id)
        # 保存节点数据（用于 UI 恢复）
        self.node: Optional[NodeModel] = model.nodes.get(node_id)
        # 保存相关的连线（用于 UI 恢复）
        self.related_edges: list[tuple[str, EdgeModel]] = []
        for edge_id, edge in model.edges.items():
            if edge.src_node == node_id or edge.dst_node == node_id:
                self.related_edges.append((edge_id, edge))
        # 保存被删除的虚拟引脚快照（用于撤销）
        self.virtual_pin_snapshot: Optional[CompositeVirtualPinSnapshot] = None

    def _snapshot_virtual_pins_before_delete(self) -> None:
        """在删除节点前，为复合节点虚拟引脚生成撤销快照。"""
        if not getattr(self.scene, "is_composite_editor", False):
            return
        composite_context = getattr(self.scene, "composite_edit_context", None)
        if not isinstance(composite_context, dict):
            return
        composite_id = composite_context.get("composite_id")
        manager = composite_context.get("manager")
        if not composite_id or manager is None:
            return
        self.virtual_pin_snapshot = snapshot_virtual_pins_for_node(
            manager,
            composite_id,
            self.node_id,
        )

    def execute(self) -> None:
        # 先快照虚拟引脚状态（需要依赖当前 composite 节点）
        self._snapshot_virtual_pins_before_delete()

        # 删除模型中的节点与连线
        self._model_command.execute()

        # 删除相关连线的图形项
        for edge_id, _ in self.related_edges:
            edge_item = self.scene.edge_items.pop(edge_id, None)
            if edge_item:
                if hasattr(self.scene, "_unregister_edge_for_nodes"):
                    self.scene._unregister_edge_for_nodes(edge_item)
                self.scene.removeItem(edge_item)

        # 删除节点图形项
        self.scene._remove_node_graphics(self.node_id)

        # 清理虚拟引脚映射（在复合节点编辑器中）
        self.scene.cleanup_virtual_pins_for_deleted_node(self.node_id)

    def undo(self) -> None:
        # 恢复模型中的节点与连线
        self._model_command.undo()

        # 恢复节点图形项
        if self.node is not None:
            self.scene.add_node_item(self.node)

        # 恢复连线图形项
        for edge_id, edge in self.related_edges:
            self.scene.add_edge_item(edge)

        # 恢复虚拟引脚（在复合节点编辑器中）
        if getattr(self.scene, "is_composite_editor", False) and self.virtual_pin_snapshot is not None:
            composite_context = getattr(self.scene, "composite_edit_context", None) or {}
            composite_id = composite_context.get("composite_id")
            manager = composite_context.get("manager")
            is_read_only_context = bool(composite_context.get("read_only"))
            if composite_id and manager:
                affected_node_ids = restore_virtual_pins_from_snapshot(
                    manager,
                    composite_id,
                    self.virtual_pin_snapshot,
                    is_read_only=is_read_only_context,
                )
                self.scene._refresh_all_ports(affected_node_ids or None)


class AddEdgeCommand(Command):
    """添加连线命令（UI 封装）"""

    def __init__(
        self,
        model: GraphModel,
        scene: GraphScene,
        edge_id: str,
        src_node: str,
        src_port: str,
        dst_node: str,
        dst_port: str,
    ):
        self.model = model
        self.scene = scene
        self.edge_id = edge_id
        self.src_node = src_node
        self.src_port = src_port
        self.dst_node = dst_node
        self.dst_port = dst_port
        self._model_command = AddEdgeModelCommand(
            model=model,
            edge_id=edge_id,
            src_node=src_node,
            src_port=src_port,
            dst_node=dst_node,
            dst_port=dst_port,
        )
        self.edge: Optional[EdgeModel] = None

    def execute(self) -> None:
        log_info(
            "[命令] 执行添加连线: {}.{} -> {}.{}",
            self.src_node,
            self.src_port,
            self.dst_node,
            self.dst_port,
        )
        self._model_command.execute()
        self.edge = self._model_command.edge
        if self.edge is None:
            log_warn("[命令] 连线创建失败: EdgeModel 未创建")
            return
        edge_item = self.scene.add_edge_item(self.edge)
        if edge_item:
            log_info("[命令] 连线创建成功")
        else:
            log_warn("[命令] 连线创建失败: UI 未能创建 EdgeGraphicsItem")

    def undo(self) -> None:
        edge_item = self.scene.edge_items.pop(self.edge_id, None)
        affected_node_id: Optional[str] = None
        if edge_item is not None:
            affected_node_id = edge_item.dst.node_item.node.id
            if hasattr(self.scene, "_unregister_edge_for_nodes"):
                self.scene._unregister_edge_for_nodes(edge_item)
            self.scene.removeItem(edge_item)
        self._model_command.undo()
        if affected_node_id and affected_node_id in self.scene.node_items:
            self.scene.node_items[affected_node_id]._layout_ports()


class DeleteEdgeCommand(Command):
    """删除连线命令（UI 封装）"""

    def __init__(self, model: GraphModel, scene: GraphScene, edge_id: str):
        self.model = model
        self.scene = scene
        self.edge_id = edge_id
        self._model_command = DeleteEdgeModelCommand(model, edge_id)
        self.edge: Optional[EdgeModel] = model.edges.get(edge_id)

    def execute(self) -> None:
        # 删除图形项
        edge_item = self.scene.edge_items.pop(self.edge_id, None)
        affected_node_id: Optional[str] = None
        if edge_item is not None:
            affected_node_id = edge_item.dst.node_item.node.id
            if hasattr(self.scene, "_unregister_edge_for_nodes"):
                self.scene._unregister_edge_for_nodes(edge_item)
            self.scene.removeItem(edge_item)
        # 删除模型
        self._model_command.execute()
        # 重新布局受影响的节点，以显示之前被隐藏的输入框
        if affected_node_id and affected_node_id in self.scene.node_items:
            self.scene.node_items[affected_node_id]._layout_ports()

    def undo(self) -> None:
        self._model_command.undo()
        if self.edge is not None:
            self.scene.add_edge_item(self.edge)


class MoveNodeCommand(Command):
    """移动节点命令（UI 封装 + 纯模型命令）

    - MoveNodeModelCommand 更新 GraphModel 中节点的位置
    - 本命令更新 QGraphicsItem 位置
    - 节点位置不计入持久化变更
    """

    affects_persistence = False

    def __init__(
        self,
        model: GraphModel,
        scene: GraphScene,
        node_id: str,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ):
        self.model = model
        self.scene = scene
        self.node_id = node_id
        self.old_pos = old_pos
        self.new_pos = new_pos
        self._model_command = MoveNodeModelCommand(
            model=model,
            node_id=node_id,
            old_pos=old_pos,
            new_pos=new_pos,
        )

    def _apply_pos_to_item(self, pos: tuple[float, float]) -> None:
        node_item = self.scene.node_items.get(self.node_id)
        if node_item is not None:
            node_item.setPos(pos[0], pos[1])

    def execute(self) -> None:
        self._model_command.execute()
        self._apply_pos_to_item(self.new_pos)

    def undo(self) -> None:
        self._model_command.undo()
        self._apply_pos_to_item(self.old_pos)


class AddPortCommand(Command):
    """添加端口命令（UI + 模型）"""

    def __init__(
        self,
        model: GraphModel,
        scene: GraphScene,
        node_id: str,
        port_name: str,
        is_input: bool = False,
    ):
        self.model = model
        self.scene = scene
        self.node_id = node_id
        self.port_name = port_name
        self.is_input = is_input

    def execute(self) -> None:
        node = self.model.nodes.get(self.node_id)
        if node is None:
            return
        if self.is_input:
            if node.add_input_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()
        else:
            if node.add_output_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()

    def undo(self) -> None:
        node = self.model.nodes.get(self.node_id)
        if node is None:
            return
        if self.is_input:
            if node.remove_input_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()
        else:
            if node.remove_output_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()


class RemovePortCommand(Command):
    """删除端口命令（UI + 模型）

    目前仍在 UI 层同时处理模型与图形项的变更：
    - GraphModel.remove_port_connections 删除数据层连线
    - Scene 负责删除 EdgeGraphicsItem 与重新布局端口
    """

    def __init__(
        self,
        model: GraphModel,
        scene: GraphScene,
        node_id: str,
        port_name: str,
        is_input: bool = False,
    ):
        self.model = model
        self.scene = scene
        self.node_id = node_id
        self.port_name = port_name
        self.is_input = is_input
        self.removed_edges: list[tuple[str, str, str]] = []

    def execute(self) -> None:
        node = self.model.nodes.get(self.node_id)
        if node is None:
            return
        # 删除相关连线（数据层）
        removed_edge_ids = self.model.remove_port_connections(
            self.node_id,
            self.port_name,
            self.is_input,
        )
        # 删除相关连线（UI 层）并记录以备撤销
        self.removed_edges = []
        for edge_id in removed_edge_ids:
            edge_item = self.scene.edge_items.pop(edge_id, None)
            if edge_item is not None:
                if hasattr(self.scene, "_unregister_edge_for_nodes"):
                    self.scene._unregister_edge_for_nodes(edge_item)
                self.removed_edges.append(
                    (edge_id, edge_item.src.name, edge_item.dst.name)
                )
                self.scene.removeItem(edge_item)
        # 删除端口
        if self.is_input:
            if node.remove_input_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()
        else:
            if node.remove_output_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()

    def undo(self) -> None:
        node = self.model.nodes.get(self.node_id)
        if node is None:
            return
        # 恢复端口
        if self.is_input:
            if node.add_input_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()
        else:
            if node.add_output_port(self.port_name):
                node_item = self.scene.node_items.get(self.node_id)
                if node_item is not None:
                    node_item._layout_ports()

        # 恢复连线（数据层 + UI）
        for edge_id, src_port, dst_port in self.removed_edges:
            src_node = self.node_id if not self.is_input else self.node_id
            dst_node = self.node_id if self.is_input else self.node_id
            # 数据层恢复
            edge = EdgeModel(
                id=edge_id,
                src_node=src_node,
                src_port=src_port,
                dst_node=dst_node,
                dst_port=dst_port,
            )
            self.model.edges[edge_id] = edge
            # UI 层恢复
            self.scene.add_edge_item(edge)


class RenamePortCommand(Command):
    """重命名端口命令（UI + 模型）"""

    def __init__(
        self,
        model: GraphModel,
        scene: GraphScene,
        node_id: str,
        old_port_name: str,
        new_port_name: str,
        is_input: bool = False,
    ):
        self.model = model
        self.scene = scene
        self.node_id = node_id
        self.old_port_name = old_port_name
        self.new_port_name = new_port_name
        self.is_input = is_input
        self.affected_edges: list[str] = []

    def execute(self) -> None:
        if not self._rename_port(self.old_port_name, self.new_port_name):
            return
        self.affected_edges = self._retarget_edges(
            self.old_port_name,
            self.new_port_name,
        )
        self._refresh_node_item()

    def undo(self) -> None:
        if not self._rename_port(self.new_port_name, self.old_port_name):
            return
        self._retarget_edges(
            self.new_port_name,
            self.old_port_name,
            restrict_to=self.affected_edges,
        )
        self._refresh_node_item()

    def _rename_port(self, old_name: str, new_name: str) -> bool:
        node = self.model.nodes.get(self.node_id)
        if node is None:
            return False
        ports = node.inputs if self.is_input else node.outputs
        for port in ports:
            if port.name == old_name:
                port.name = new_name
                return True
        return False

    def _retarget_edges(
        self,
        old_name: str,
        new_name: str,
        restrict_to: Optional[list[str]] = None,
    ) -> list[str]:
        changed: list[str] = []
        for edge_id, edge in self.model.edges.items():
            if restrict_to and edge_id not in restrict_to:
                continue
            if self.is_input:
                if edge.dst_node == self.node_id and edge.dst_port == old_name:
                    edge.dst_port = new_name
                    changed.append(edge_id)
            else:
                if edge.src_node == self.node_id and edge.src_port == old_name:
                    edge.src_port = new_name
                    changed.append(edge_id)
        return changed

    def _refresh_node_item(self) -> None:
        node_item = self.scene.node_items.get(self.node_id)
        if node_item is not None:
            node_item._layout_ports()


__all__ = [
    "UndoRedoManager",
    "Command",
    "AddNodeCommand",
    "DeleteNodeCommand",
    "AddEdgeCommand",
    "DeleteEdgeCommand",
    "MoveNodeCommand",
    "AddPortCommand",
    "RemovePortCommand",
    "RenamePortCommand",
]


