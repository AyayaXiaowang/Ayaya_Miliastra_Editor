from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engine.graph.models import NodeModel


@dataclass
class VarEnv:
    """变量/作用域与循环上下文环境。

    - 变量映射：变量名 → (节点ID, 输出端口名)
    - 节点序列：按创建顺序记录流程节点，用于局部兜底回溯
    - 循环栈：用于 break 连接到最近的循环节点
    - 当前事件节点：当无法找到局部前驱流程节点时的最终兜底
    - 复合节点实例映射：实例别名 → 复合节点ID
    """

    var_map: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    node_sequence: List[NodeModel] = field(default_factory=list)
    loop_stack: List[NodeModel] = field(default_factory=list)
    current_event_node: Optional[NodeModel] = None
    composite_instances: Dict[str, str] = field(default_factory=dict)

    def set_variable(self, name: str, source_node_id: str, source_port_name: str) -> None:
        self.var_map[name] = (source_node_id, source_port_name)

    def get_variable(self, name: str) -> Optional[Tuple[str, str]]:
        return self.var_map.get(name)

    def snapshot(self) -> Dict[str, Tuple[str, str]]:
        """快照当前变量表（用于 if/loop 分支内的作用域隔离）。"""
        return dict(self.var_map)

    def restore(self, snapshot: Dict[str, Tuple[str, str]]) -> None:
        self.var_map = dict(snapshot)

    def push_loop(self, loop_node: NodeModel) -> None:
        self.loop_stack.append(loop_node)

    def pop_loop(self) -> Optional[NodeModel]:
        return self.loop_stack.pop() if self.loop_stack else None
    
    def set_composite_instance(self, alias: str, composite_id: str) -> None:
        """注册复合节点实例
        
        Args:
            alias: 实例别名（如 self.延迟执行器 中的 "延迟执行器"）
            composite_id: 复合节点ID
        """
        self.composite_instances[alias] = composite_id
    
    def get_composite_instance(self, alias: str) -> Optional[str]:
        """获取复合节点实例ID
        
        Args:
            alias: 实例别名
            
        Returns:
            复合节点ID，若不存在则返回None
        """
        return self.composite_instances.get(alias)



