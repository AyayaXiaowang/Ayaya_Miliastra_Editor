"""TodoItem数据类定义"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict


@dataclass
class TodoItem:
    """任务项"""
    todo_id: str  # 唯一标识
    title: str  # 标题
    description: str  # 描述
    level: int  # 层级深度（0=根，1=一级，2=二级...）
    parent_id: Optional[str]  # 父任务ID
    children: List[str]  # 子任务ID列表
    task_type: str  # 任务类型：template/instance/combat/management/category
    target_id: str  # 对应的模板/实例ID
    detail_info: dict  # 详细信息（用于右侧显示）
    
    def is_completed(self, todo_states: Dict[str, bool]) -> bool:
        """检查任务是否完成"""
        if not self.children:
            # 叶子节点：直接查看状态
            return todo_states.get(self.todo_id, False)
        else:
            # 父节点：所有子任务都完成才算完成
            return all(todo_states.get(child_id, False) for child_id in self.children)
    
    def get_progress(self, todo_states: Dict[str, bool]) -> tuple[int, int]:
        """获取子任务完成进度 (已完成数, 总数)"""
        if not self.children:
            return (0, 0)
        completed = sum(1 for child_id in self.children if todo_states.get(child_id, False))
        return (completed, len(self.children))


