"""
组件配置 - 单位状态
基于知识库文档定义的单位状态组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class UnitStatusConfig:
    """单位状态组件配置（待完善）"""
    # 状态列表
    statuses: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "状态列表": self.statuses
        }

