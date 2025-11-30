"""
组件配置 - 扫描标签
基于知识库文档定义的扫描标签组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class ScanState(Enum):
    """扫描状态（扫描标签.md 第32-35行）"""
    ACTIVE = "激活状态"
    AVAILABLE = "可用状态"
    DISABLED = "禁用状态"


@dataclass
class ScanTagDefinition:
    """
    扫描标签定义
    来源：扫描标签.md (第74-82行)
    """
    # 扫描标签序号
    tag_index: int
    # 初始生效
    initially_active: bool = False
    # 引用扫描标签（配置ID）
    scan_tag_template: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "扫描标签序号": self.tag_index,
            "初始生效": self.initially_active,
            "引用扫描标签": self.scan_tag_template
        }


@dataclass
class ScanTagComponentConfig:
    """
    扫描标签组件配置
    来源：扫描标签.md (第68-82行)
    注意：可配置多个扫描标签，但运行时只有一个可以生效（第75行）
    """
    # 扫描标签列表
    scan_tags: List[ScanTagDefinition] = field(default_factory=list)
    # 初始生效的标签序号
    initially_active_tag: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "扫描标签列表": [tag.to_dict() for tag in self.scan_tags],
            "初始生效": self.initially_active_tag
        }

