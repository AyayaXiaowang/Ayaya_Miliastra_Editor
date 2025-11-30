from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional, Iterable

from engine.graph.models import GraphModel, NodeModel, EdgeModel, PortModel


class Command(ABC):
    """纯逻辑命令基类

    - 只负责数据层变更（GraphModel/NodeModel/EdgeModel 等）
    - 不依赖任何 UI / QGraphicsScene / GraphScene
    - 通过 UndoRedoManager 统一调度
    """

    #: 是否影响需要持久化的内容
    #: - True: 计入 has_changes()，触发 on_change_callback（例如自动保存）
    #: - False: 仅影响临时状态（例如节点位置），不计入持久化变更
    affects_persistence: bool = True

    @abstractmethod
    def execute(self) -> None:
        """执行命令"""

    @abstractmethod
    def undo(self) -> None:
        """撤销命令"""


class UndoRedoManager:
    """通用撤销/重做管理器（纯逻辑版本）

    - 与 UI 解耦，仅依赖 Command 抽象
    - 通过 `affects_persistence` 区分是否算“需要保存的修改”
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []
        self.on_change_callback: Optional[Callable[[], None]] = None

    def _push_undo(self, command: Command) -> None:
        self.undo_stack.append(command)
        # 清空重做栈
        self.redo_stack.clear()
        # 限制撤销记录大小
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def execute_command(self, command: Command) -> None:
        """执行命令并加入撤销栈"""
        command.execute()
        self._push_undo(command)
        # 触发变更回调（用于自动保存）
        if self.on_change_callback and command.affects_persistence:
            self.on_change_callback()

    def undo(self) -> bool:
        """撤销上一个操作"""
        if not self.undo_stack:
            return False
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        # 触发变更回调（用于自动保存）
        if self.on_change_callback and command.affects_persistence:
            self.on_change_callback()
        return True

    def redo(self) -> bool:
        """重做上一个撤销的操作"""
        if not self.redo_stack:
            return False
        command = self.redo_stack.pop()
        command.execute()
        self._push_undo(command)
        # 触发变更回调（用于自动保存）
        if self.on_change_callback and command.affects_persistence:
            self.on_change_callback()
        return True

    def can_undo(self) -> bool:
        """是否可以撤销"""
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """是否可以重做"""
        return len(self.redo_stack) > 0

    def clear(self) -> None:
        """清空撤销/重做记录"""
        self.undo_stack.clear()
        self.redo_stack.clear()

    def _iter_meaningful_commands(self) -> Iterable[Command]:
        return (cmd for cmd in self.undo_stack if cmd.affects_persistence)

    def has_changes(self) -> bool:
        """检查是否有未保存的修改

        仅统计 `affects_persistence=True` 的命令。
        """
        return any(self._iter_meaningful_commands())


# === GraphModel 级别的基础命令 ===


class AddNodeModelCommand(Command):
    """在 GraphModel 中添加一个节点（不涉及任何 UI）"""

    def __init__(
        self,
        model: GraphModel,
        node_id: str,
        title: str,
        category: str,
        input_names: list[str],
        output_names: list[str],
        pos: tuple[float, float],
    ):
        self.model = model
        self.node_id = node_id
        self.title = title
        self.category = category
        self.input_names = input_names
        self.output_names = output_names
        self.pos = pos
        self.node: NodeModel | None = None

    def execute(self) -> None:
        node = NodeModel(id=self.node_id, title=self.title, category=self.category, pos=self.pos)
        node.inputs = [PortModel(name=n, is_input=True) for n in self.input_names]
        node.outputs = [PortModel(name=n, is_input=False) for n in self.output_names]
        node._rebuild_port_maps()
        self.model.nodes[self.node_id] = node
        self.node = node

    def undo(self) -> None:
        self.model.nodes.pop(self.node_id, None)
        self.node = None


class DeleteNodeModelCommand(Command):
    """在 GraphModel 中删除一个节点及其相关连线"""

    def __init__(self, model: GraphModel, node_id: str):
        self.model = model
        self.node_id = node_id
        self.node: NodeModel | None = model.nodes.get(node_id)
        # 保存相关的连线
        self.related_edges: list[tuple[str, EdgeModel]] = []
        for edge_id, edge in model.edges.items():
            if edge.src_node == node_id or edge.dst_node == node_id:
                self.related_edges.append((edge_id, edge))

    def execute(self) -> None:
        # 删除相关连线
        for edge_id, _ in self.related_edges:
            self.model.edges.pop(edge_id, None)
        # 删除节点
        self.model.nodes.pop(self.node_id, None)

    def undo(self) -> None:
        # 恢复节点
        if self.node is not None:
            self.model.nodes[self.node_id] = self.node
        # 恢复连线
        for edge_id, edge in self.related_edges:
            self.model.edges[edge_id] = edge


class AddEdgeModelCommand(Command):
    """在 GraphModel 中添加一条连线"""

    def __init__(
        self,
        model: GraphModel,
        edge_id: str,
        src_node: str,
        src_port: str,
        dst_node: str,
        dst_port: str,
    ):
        self.model = model
        self.edge_id = edge_id
        self.src_node = src_node
        self.src_port = src_port
        self.dst_node = dst_node
        self.dst_port = dst_port
        self.edge: EdgeModel | None = None

    def execute(self) -> None:
        edge = EdgeModel(
            id=self.edge_id,
            src_node=self.src_node,
            src_port=self.src_port,
            dst_node=self.dst_node,
            dst_port=self.dst_port,
        )
        self.model.edges[self.edge_id] = edge
        self.edge = edge

    def undo(self) -> None:
        self.model.edges.pop(self.edge_id, None)
        self.edge = None


class DeleteEdgeModelCommand(Command):
    """在 GraphModel 中删除一条连线"""

    def __init__(self, model: GraphModel, edge_id: str):
        self.model = model
        self.edge_id = edge_id
        self.edge: EdgeModel | None = model.edges.get(edge_id)

    def execute(self) -> None:
        self.edge = self.model.edges.pop(self.edge_id, None)

    def undo(self) -> None:
        if self.edge is not None:
            self.model.edges[self.edge_id] = self.edge


class MoveNodeModelCommand(Command):
    """仅更新 GraphModel 中节点的位置（不触发持久化变更）"""

    affects_persistence = False

    def __init__(
        self,
        model: GraphModel,
        node_id: str,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ):
        self.model = model
        self.node_id = node_id
        self.old_pos = old_pos
        self.new_pos = new_pos

    def _set_pos(self, pos: tuple[float, float]) -> None:
        node = self.model.nodes.get(self.node_id)
        if node is not None:
            node.pos = pos

    def execute(self) -> None:
        self._set_pos(self.new_pos)

    def undo(self) -> None:
        self._set_pos(self.old_pos)



