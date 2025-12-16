from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime


@dataclass
class PortModel:
    name: str
    is_input: bool


@dataclass
class BasicBlock:
    """基本块数据结构
    
    基本块是编译原理中的概念，指从一个入口到一个出口的顺序执行序列。
    在节点图中，基本块是从一个非分支节点开始，到下一个分支节点为止的连续节点序列。
    """
    nodes: List[str] = field(default_factory=list)  # 节点ID列表
    color: str = "#FF5E9C"  # RGB颜色（如 "#FF5E9C"）
    alpha: float = 0.2  # 透明度 (0.0-1.0)


@dataclass
class NodeModel:
    id: str
    title: str
    category: str
    inputs: List[PortModel] = field(default_factory=list)
    outputs: List[PortModel] = field(default_factory=list)
    pos: Tuple[float, float] = (0.0, 0.0)
    # 输入常量（用于在UI上显示齿轮并可编辑）
    input_constants: Dict[str, Any] = field(default_factory=dict)
    
    # 复合节点ID（仅当category="复合节点"时有效）
    composite_id: str = ""  # 复合节点的唯一标识符，用于精确引用复合节点定义
    
    # 虚拟引脚标记（用于复合节点内部）
    is_virtual_pin: bool = False  # 是否是虚拟引脚节点
    virtual_pin_index: int = 0  # 虚拟引脚序号（仅当is_virtual_pin=True时有效）
    virtual_pin_type: str = ""  # 虚拟引脚数据类型
    is_virtual_pin_input: bool = True  # True为输入虚拟引脚，False为输出虚拟引脚
    
    # 双向无痛编辑：用户自定义信息
    custom_var_names: Dict[str, str] = field(default_factory=dict)  # 自定义变量名映射 {output_port_name: var_name}
    custom_comment: str = ""  # 自定义注释（节点前的注释块）
    inline_comment: str = ""  # 行内注释（代码同行的注释）
    # 源代码行范围（用于验证与错误定位）。当节点来源于类结构Python时可用；否则默认为0。
    source_lineno: int = 0
    source_end_lineno: int = 0
    
    # 数据节点副本标识（用于跨块复制）
    is_data_node_copy: bool = False  # 是否是数据节点副本
    original_node_id: str = ""  # 原始节点ID（仅副本有效）
    copy_block_id: str = ""  # 副本所属块ID（如"block_2"）
    
    # 端口映射缓存（O(1) 查询，布局/树打印复用）
    _in_port_map: Optional[Dict[str, PortModel]] = field(default=None, repr=False, compare=False)
    _out_port_map: Optional[Dict[str, PortModel]] = field(default=None, repr=False, compare=False)
    _out_port_index_map: Optional[Dict[str, int]] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # 延迟构建，保持与反序列化/外部赋值流程的兼容
        self._in_port_map = None
        self._out_port_map = None
        self._out_port_index_map = None

    # -------- 端口映射（缓存）--------
    @property
    def inPortMap(self) -> Dict[str, PortModel]:
        if self._in_port_map is None:
            self._in_port_map = {port.name: port for port in (self.inputs or [])}
        return self._in_port_map

    @property
    def outPortMap(self) -> Dict[str, PortModel]:
        if self._out_port_map is None:
            self._out_port_map = {port.name: port for port in (self.outputs or [])}
        return self._out_port_map

    @property
    def outPortIndexMap(self) -> Dict[str, int]:
        if self._out_port_index_map is None:
            self._out_port_index_map = {port.name: idx for idx, port in enumerate(self.outputs or [])}
        return self._out_port_index_map

    def _rebuild_port_maps(self) -> None:
        self._in_port_map = {port.name: port for port in (self.inputs or [])}
        self._out_port_map = {port.name: port for port in (self.outputs or [])}
        self._out_port_index_map = {port.name: idx for idx, port in enumerate(self.outputs or [])}

    def get_input_port(self, port_name: str) -> Optional[PortModel]:
        return self.inPortMap.get(port_name)

    def get_output_port(self, port_name: str) -> Optional[PortModel]:
        return self.outPortMap.get(port_name)
    
    def add_input_port(self, port_name: str) -> bool:
        """动态添加输入端口
        
        Args:
            port_name: 端口名称
            
        Returns:
            是否成功添加（如果端口已存在则返回False）
        """
        if any(port.name == port_name for port in self.inputs):
            return False
        
        new_port = PortModel(name=port_name, is_input=True)
        self.inputs.append(new_port)
        self._rebuild_port_maps()
        return True
    
    def remove_input_port(self, port_name: str) -> bool:
        """动态删除输入端口
        
        Args:
            port_name: 端口名称
            
        Returns:
            是否成功删除（如果端口不存在则返回False）
        """
        for index, port in enumerate(self.inputs):
            if port.name == port_name:
                self.inputs.pop(index)
                self._rebuild_port_maps()
                return True
        return False
    
    def has_input_port(self, port_name: str) -> bool:
        """检查是否存在指定名称的输入端口"""
        return any(port.name == port_name for port in self.inputs)
    
    def add_output_port(self, port_name: str) -> bool:
        """动态添加输出端口
        
        Args:
            port_name: 端口名称
            
        Returns:
            是否成功添加（如果端口已存在则返回False）
        """
        if any(port.name == port_name for port in self.outputs):
            return False
        
        new_port = PortModel(name=port_name, is_input=False)
        self.outputs.append(new_port)
        self._rebuild_port_maps()
        return True
    
    def remove_output_port(self, port_name: str) -> bool:
        """动态删除输出端口
        
        Args:
            port_name: 端口名称
            
        Returns:
            是否成功删除（如果端口不存在则返回False）
        """
        for index, port in enumerate(self.outputs):
            if port.name == port_name:
                self.outputs.pop(index)
                self._rebuild_port_maps()
                return True
        return False
    
    def has_output_port(self, port_name: str) -> bool:
        """检查是否存在指定名称的输出端口"""
        return any(port.name == port_name for port in self.outputs)
    
    def sync_ports_from_def(self, node_def) -> bool:
        """从节点定义同步端口信息（用于复合节点引脚更新）
        
        Args:
            node_def: NodeDef对象
            
        Returns:
            是否发生了变化
        """
        from engine.graph.models.graph_port_sync import sync_ports_from_def
        return sync_ports_from_def(self, node_def)


@dataclass
class EdgeModel:
    id: str
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str


class GraphModel:
    def __init__(self, graph_id: str = "", graph_name: str = "", description: str = "") -> None:
        self.graph_id = graph_id
        self.graph_name = graph_name
        self.description = description
        self.nodes: Dict[str, NodeModel] = {}
        self.edges: Dict[str, EdgeModel] = {}
        # 连线版本号：用于让依赖 edges 的缓存具备可靠失效条件。
        # 注意：若外部直接原地修改 EdgeModel 字段（而非通过 GraphModel API），
        # 需要调用 `touch_edges_revision()` 主动触发失效。
        self._edges_revision: int = 0
        self.graph_variables: List[dict] = []  # 节点图变量列表（存储序列化后的GraphVariableConfig）
        # 元数据（所属模板、实例、信号绑定、结构体绑定等）
        self.metadata: Dict[str, Any] = {}
        self._next_id = 1
        
        # 双向无痛编辑：用户自定义信息
        self.event_flow_comments: Dict[int, str] = {}  # 事件流注释 {event_flow_index: comment_text}
        self.preserve_formatting: bool = True  # 是否保留用户格式（默认True）
        
        # 事件流顺序：保存事件节点ID的顺序列表，用于保持生成代码时的事件流顺序一致
        self.event_flow_order: List[str] = []  # 事件节点ID列表，按原始文件中的出现顺序
        # 事件流标题顺序：保存事件标题（名称）的顺序，作为ID缺失或变更时的稳定回退
        self.event_flow_titles: List[str] = []  # 事件标题列表，按原始文件中的顺序
        
        # 基本块列表：用于可视化显示（半透明矩形框）
        self.basic_blocks: List[BasicBlock] = []  # 基本块列表
        
        # 自动生成ID（如果未提供）
        if not self.graph_id:
            self.graph_id = datetime.now().strftime("graph_%Y%m%d_%H%M%S_%f")

    def gen_id(self, prefix: str) -> str:
        new_id = f"{prefix}_{self._next_id}"
        self._next_id += 1
        return new_id

    # -------- 变更版本号（用于缓存失效）--------
    def _touch_edges_revision(self) -> None:
        self._edges_revision += 1

    def touch_edges_revision(self) -> None:
        """显式触发“连线已变更”的版本号递增。

        用途：
        - 当外部代码直接原地修改 EdgeModel 字段或直接操作 `self.edges` 字典时，
          需要主动调用本方法，避免 `engine.graph.common` 等模块复用旧缓存。
        """
        self._touch_edges_revision()

    def get_edges_revision(self) -> int:
        """获取当前连线版本号（用于调试与缓存策略）。"""
        return int(self._edges_revision)
    
    def add_node(self, title: str, category: str, input_names: List[str], output_names: List[str], pos=(0.0, 0.0)) -> NodeModel:
        node_id = self.gen_id("node")
        node = NodeModel(id=node_id, title=title, category=category, pos=pos)
        node.inputs = [PortModel(name=name, is_input=True) for name in input_names]
        node.outputs = [PortModel(name=name, is_input=False) for name in output_names]
        self.nodes[node_id] = node
        node._rebuild_port_maps()
        return node
    
    def add_edge(self, src_node: str, src_port: str, dst_node: str, dst_port: str) -> EdgeModel:
        edge_id = self.gen_id("edge")
        edge = EdgeModel(id=edge_id, src_node=src_node, src_port=src_port, dst_node=dst_node, dst_port=dst_port)
        self.edges[edge_id] = edge
        self._touch_edges_revision()
        return edge
    
    def add_edge_if_absent(self, src_node: str, src_port: str, dst_node: str, dst_port: str) -> Optional[EdgeModel]:
        """若相同连线不存在则添加，否则返回None。"""
        for existing_edge in self.edges.values():
            if (
                existing_edge.src_node == src_node
                and existing_edge.src_port == src_port
                and existing_edge.dst_node == dst_node
                and existing_edge.dst_port == dst_port
            ):
                return None
        return self.add_edge(src_node, src_port, dst_node, dst_port)
    
    # -------- 信号绑定辅助（GraphModel.metadata["signal_bindings"]）--------
    def get_signal_bindings(self) -> Dict[str, Dict[str, str]]:
        """获取当前图的信号绑定字典。
        
        结构约定：
        metadata["signal_bindings"] = {node_id: {"signal_id": "<signal_xxx>"}, ...}
        """
        bindings = self.metadata.get("signal_bindings")
        if not isinstance(bindings, dict):
            bindings = {}
            self.metadata["signal_bindings"] = bindings
        return bindings
    
    def set_node_signal_binding(self, node_id: str, signal_id: str) -> None:
        """为指定节点绑定信号ID（覆盖同一节点的旧绑定）。"""
        bindings = self.get_signal_bindings()
        bindings[str(node_id)] = {"signal_id": str(signal_id)}
    
    def get_node_signal_id(self, node_id: str) -> Optional[str]:
        """获取指定节点当前绑定的信号ID（若未绑定则返回None）。"""
        bindings = self.metadata.get("signal_bindings")
        if not isinstance(bindings, dict):
            return None
        info = bindings.get(str(node_id))
        if not isinstance(info, dict):
            return None
        signal_id = info.get("signal_id")
        return str(signal_id) if signal_id is not None else None
    
    # -------- 结构体绑定辅助（GraphModel.metadata["struct_bindings"]）--------
    def get_struct_bindings(self) -> Dict[str, Dict[str, Any]]:
        """获取当前图的结构体绑定字典。
        
        结构约定：
        metadata["struct_bindings"] = {
            node_id: {
                "struct_id": "<struct_xxx>",
                "struct_name": "<显示名称>",
                "field_names": ["字段1", "字段2", ...],
            },
            ...
        }
        """
        bindings = self.metadata.get("struct_bindings")
        if not isinstance(bindings, dict):
            bindings = {}
            self.metadata["struct_bindings"] = bindings
        return bindings
    
    def set_node_struct_binding(self, node_id: str, binding: Dict[str, Any]) -> None:
        """为指定节点写入结构体绑定信息（覆盖同一节点的旧绑定）。"""
        bindings = self.get_struct_bindings()
        bindings[str(node_id)] = dict(binding)
    
    def get_node_struct_binding(self, node_id: str) -> Optional[Dict[str, Any]]:
        """获取指定节点当前绑定的结构体信息（若未绑定则返回None）。"""
        bindings = self.metadata.get("struct_bindings")
        if not isinstance(bindings, dict):
            return None
        info = bindings.get(str(node_id))
        if not isinstance(info, dict):
            return None
        return dict(info)
    
    def clear_node_struct_binding(self, node_id: str) -> None:
        """移除指定节点的结构体绑定信息（若不存在则忽略）。"""
        bindings = self.metadata.get("struct_bindings")
        if not isinstance(bindings, dict):
            return
        bindings.pop(str(node_id), None)

    def remove_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            return
        # remove edges connected
        to_del = [eid for eid, e in self.edges.items() if e.src_node == node_id or e.dst_node == node_id]
        for eid in to_del:
            self.edges.pop(eid, None)
        self.nodes.pop(node_id, None)
        if to_del:
            self._touch_edges_revision()
    
    def has_port_connections(self, node_id: str, port_name: str, is_input: bool) -> bool:
        """检查指定端口是否有连线
        
        Args:
            node_id: 节点ID
            port_name: 端口名称
            is_input: 是否为输入端口
            
        Returns:
            是否有连线连接到该端口
        """
        for edge in self.edges.values():
            if is_input:
                if edge.dst_node == node_id and edge.dst_port == port_name:
                    return True
            else:
                if edge.src_node == node_id and edge.src_port == port_name:
                    return True
        return False
    
    def remove_port_connections(self, node_id: str, port_name: str, is_input: bool) -> List[str]:
        """删除指定端口的所有连线
        
        Args:
            node_id: 节点ID
            port_name: 端口名称
            is_input: 是否为输入端口
            
        Returns:
            被删除的边的ID列表
        """
        removed_edges = []
        to_del = []
        
        for edge_id, edge in self.edges.items():
            if is_input:
                if edge.dst_node == node_id and edge.dst_port == port_name:
                    to_del.append(edge_id)
            else:
                if edge.src_node == node_id and edge.src_port == port_name:
                    to_del.append(edge_id)
        
        for edge_id in to_del:
            self.edges.pop(edge_id, None)
            removed_edges.append(edge_id)
        if removed_edges:
            self._touch_edges_revision()
        return removed_edges
    
    def sync_composite_nodes_from_library(self, node_library: Dict) -> int:
        """从节点库同步所有复合节点的端口定义
        
        当复合节点的虚拟引脚被修改后，调用此方法更新节点图中的实例。
        
        Args:
            node_library: 节点库字典 {key: NodeDef}
            
        Returns:
            同步更新的节点数量
        """
        from engine.graph.models.graph_port_sync import sync_composite_nodes_from_library
        return sync_composite_nodes_from_library(self, node_library)

    def serialize(self) -> dict:
        """序列化节点图为字典"""
        from engine.graph.models.graph_serialization import serialize_graph
        return serialize_graph(self)
    
    def get_content_hash(self) -> str:
        """计算节点图内容的哈希值（不包含位置信息）
        
        用于判断节点图内容是否真正发生变化。
        只计算有意义的数据：节点结构、连线、常量、变量、注释等，不包含节点位置。
        
        Returns:
            内容的MD5哈希值
        """
        from engine.graph.models.graph_hash import get_content_hash
        return get_content_hash(self)

    @staticmethod
    def deserialize(data: dict) -> "GraphModel":
        """从字典反序列化节点图
        
        Args:
            data: 序列化的字典数据
            
        Returns:
            节点图模型实例
        """
        from engine.graph.models.graph_serialization import deserialize_graph
        return deserialize_graph(data)

    # 高效结构化克隆：避免 serialize/deserialize 的 JSON 往返开销
    def clone(self) -> "GraphModel":
        import copy
        cloned = GraphModel(graph_id=self.graph_id, graph_name=self.graph_name, description=self.description)
        # nodes：逐节点重建，复制必要可变字段，跳过缓存字段
        new_nodes: Dict[str, NodeModel] = {}
        for node_id, n in self.nodes.items():
            new_node = NodeModel(
                id=n.id,
                title=n.title,
                category=n.category,
                inputs=[PortModel(name=p.name, is_input=True) for p in (n.inputs or [])],
                outputs=[PortModel(name=p.name, is_input=False) for p in (n.outputs or [])],
                pos=n.pos,
                input_constants=dict(n.input_constants) if n.input_constants else {},
                composite_id=n.composite_id,
                is_virtual_pin=n.is_virtual_pin,
                virtual_pin_index=n.virtual_pin_index,
                virtual_pin_type=n.virtual_pin_type,
                is_virtual_pin_input=n.is_virtual_pin_input,
                custom_var_names=dict(n.custom_var_names) if n.custom_var_names else {},
                custom_comment=n.custom_comment,
                inline_comment=n.inline_comment,
                source_lineno=n.source_lineno,
                source_end_lineno=n.source_end_lineno,
                is_data_node_copy=n.is_data_node_copy,
                original_node_id=n.original_node_id,
                copy_block_id=n.copy_block_id,
            )
            new_node._rebuild_port_maps()
            new_nodes[node_id] = new_node
        cloned.nodes = new_nodes
        # edges：只含标量字段，重建实例避免共享
        cloned.edges = {
            edge_id: EdgeModel(
                id=e.id,
                src_node=e.src_node,
                src_port=e.src_port,
                dst_node=e.dst_node,
                dst_port=e.dst_port,
            )
            for edge_id, e in self.edges.items()
        }
        # graph_variables / metadata：暂保深拷贝（若确认扁平可降级）
        cloned.graph_variables = copy.deepcopy(self.graph_variables)
        cloned.metadata = copy.deepcopy(self.metadata)
        cloned._next_id = self._next_id
        # 双向无痛编辑相关：浅复制为新容器
        cloned.event_flow_comments = dict(self.event_flow_comments)
        cloned.preserve_formatting = bool(self.preserve_formatting)
        cloned.event_flow_order = list(self.event_flow_order)
        cloned.event_flow_titles = list(self.event_flow_titles)
        # 基本块：重建对象 + 列表浅复制
        cloned.basic_blocks = [
            BasicBlock(nodes=list(b.nodes), color=b.color, alpha=b.alpha) for b in self.basic_blocks
        ]
        return cloned


