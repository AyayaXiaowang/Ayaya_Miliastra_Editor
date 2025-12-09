from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from engine.graph.models import NodeModel


@dataclass
class VarEnv:
    """变量/作用域与循环上下文环境。
    
    - 变量映射：变量名 → (节点ID, 输出端口名)
    - 持久映射：用于"局部变量"句柄等需要跨分支恢复的映射
    - 节点序列：按创建顺序记录流程节点，用于局部兜底回溯
    - 循环栈：用于 break 连接到最近的循环节点
    - 当前事件节点：当无法找到局部前驱流程节点时的最终兜底
    - 复合节点实例映射：实例别名 → 复合节点ID
    - 预声明局部变量：在解析前已知需要建模为局部变量的名称集合
    - 多分支赋值提示栈：在分支体解析期间传递"该变量在其他分支也有赋值"的集合
    - 变量赋值计数：统计每个变量在方法体中被赋值的总次数
    - 分支赋值与使用信息：标记哪些变量在分支内被赋值、并在分支后被使用
    """
    
    var_map: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    persistent_var_map: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    node_sequence: List[NodeModel] = field(default_factory=list)
    loop_stack: List[NodeModel] = field(default_factory=list)
    current_event_node: Optional[NodeModel] = None
    composite_instances: Dict[str, str] = field(default_factory=dict)
    predeclared_locals: Set[str] = field(default_factory=set)
    multi_assign_stack: List[Set[str]] = field(default_factory=list)
    assignment_counts: Dict[str, int] = field(default_factory=dict)
    branch_assigned_names: Set[str] = field(default_factory=set)
    used_after_branch_names: Set[str] = field(default_factory=set)
    branch_assign_usage_candidates: Set[str] = field(default_factory=set)

    def set_variable(self, name: str, source_node_id: str, source_port_name: str) -> None:
        self.var_map[name] = (source_node_id, source_port_name)

    def set_variable_persistent(self, name: str, source_node_id: str, source_port_name: str) -> None:
        """记录变量映射并在分支恢复后保持。
        
        主要用于“获取/设置局部变量”模式下的句柄与值映射。
        """
        self.var_map[name] = (source_node_id, source_port_name)
        self.persistent_var_map[name] = (source_node_id, source_port_name)

    def get_variable(self, name: str) -> Optional[Tuple[str, str]]:
        return self.var_map.get(name)

    def add_predeclared_locals(self, names: Iterable[str]) -> None:
        """注册在解析前已声明的局部变量名称。"""
        for name in names:
            if isinstance(name, str) and name:
                self.predeclared_locals.add(name)

    def is_predeclared(self, name: str) -> bool:
        return name in self.predeclared_locals

    def push_multi_assign(self, names: Iterable[str]) -> None:
        name_set: Set[str] = set()
        for name in names:
            if isinstance(name, str) and name:
                name_set.add(name)
        self.multi_assign_stack.append(name_set)

    def pop_multi_assign(self) -> None:
        if self.multi_assign_stack:
            self.multi_assign_stack.pop()

    def is_multi_assign_candidate(self, name: str) -> bool:
        """判断变量是否需要多分支赋值建模（即是否在多个互斥分支中都被赋值）。
        
        规则：只有在 if-else 或 match 的多个分支**都**对同一变量赋值时，
        才需要转换为局部变量节点来合并不同分支的数据流。
        
        以下情况**不需要**局部变量节点：
        - 变量有初始值，但只在单个分支内被修改（如只有 if 没有 else）
        - 变量在顺序代码中多次赋值（非互斥分支）
        
        判断依据：只检查 branch_builder 正确计算的"多分支都赋值"变量集
        （通过 combined_assigned = assigned_true & assigned_false 或
        match 的所有 case 交集得到）。
        """
        if not name:
            return False
        # 检查分支提示栈：由 branch_builder 正确计算的"多分支都赋值"的变量集
        for hinted_names in reversed(self.multi_assign_stack):
            if name in hinted_names:
                return True
        return False

    def set_assignment_counts(self, counts: Dict[str, int]) -> None:
        """设置变量赋值计数（在解析方法体前预先扫描得到）。"""
        self.assignment_counts = counts

    def set_branch_assignment_info(
        self,
        assigned_in_branch: Iterable[str],
        used_after_branch: Iterable[str],
    ) -> None:
        """记录分支赋值与分支后使用的信息。
        
        - assigned_in_branch: 在 if/match/for 等分支结构内部被赋值的变量
        - used_after_branch: 在对应分支结构之后被使用的变量
        - branch_assign_usage_candidates: 两者的交集，表示需要跨分支合流的变量
        """
        assigned_set: Set[str] = set()
        for name in assigned_in_branch:
            if isinstance(name, str) and name:
                assigned_set.add(name)
        used_after_set: Set[str] = set()
        for name in used_after_branch:
            if isinstance(name, str) and name:
                used_after_set.add(name)

        self.branch_assigned_names = assigned_set
        self.used_after_branch_names = used_after_set
        self.branch_assign_usage_candidates = assigned_set & used_after_set

    def snapshot(self) -> Dict[str, Tuple[str, str]]:
        """快照当前变量表（用于 if/loop 分支内的作用域隔离）。"""
        return dict(self.var_map)

    def restore(self, snapshot: Dict[str, Tuple[str, str]]) -> None:
        self.var_map = dict(snapshot)
        # 需要跨快照保留的映射（例如局部变量句柄）在恢复后补回
        for key, value in self.persistent_var_map.items():
            self.var_map.setdefault(key, value)

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



