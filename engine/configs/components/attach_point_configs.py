"""
组件配置 - 挂接点
基于知识库文档定义的挂接点组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class UnitAttachPointConfig:
    """单位挂接点组件配置（待完善）"""
    # 挂接点列表
    attach_points: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "挂接点列表": self.attach_points
        }


@dataclass
class CustomAttachPoint:
    """
    自定义挂接点定义
    来源：自定义挂接点.md (第17-20行)
    """
    # 挂点名称
    point_name: str
    # 偏移（相对实体/元件中心）
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转（相对实体/元件中心）
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "挂点名称": self.point_name,
            "偏移": self.offset,
            "旋转": self.rotation
        }


@dataclass
class CustomAttachPointComponentConfig:
    """
    自定义挂接点组件配置
    来源：自定义挂接点.md (第1-20行)
    """
    # 自定义挂接点列表（可添加多个）
    attach_points: List[CustomAttachPoint] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "自定义挂接点列表": [point.to_dict() for point in self.attach_points]
        }

