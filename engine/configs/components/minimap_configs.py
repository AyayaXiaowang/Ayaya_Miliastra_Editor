"""
组件配置 - 小地图标识
基于知识库文档定义的小地图标识组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class MinimapMarkType(Enum):
    """小地图标识类型（小地图标识.md 第41行）"""
    ICON = "图标"
    RANGE = "范围"
    POINT = "点"
    PLAYER_MARK = "玩家标记"
    CREATURE_AVATAR = "造物头像"


class MinimapColorLogic(Enum):
    """逻辑颜色类型（小地图标识.md 第51行）"""
    ENEMY_FRIEND = "敌友关系"
    FOLLOW_SELF_CAMP = "跟随自身阵营"
    FOLLOW_OWNER_CAMP = "跟随所有者阵营"


@dataclass
class MinimapMarkDefinition:
    """
    单个小地图标识定义
    来源：小地图标识.md (第26-80行)
    """
    # 小地图标识序号
    mark_index: int
    # 标记名称
    mark_name: str = ""
    # 初始生效
    initially_active: bool = True
    # 初始所有玩家可见
    visible_to_all_players: bool = True
    # 跟随物体可见性
    follow_object_visibility: bool = True
    # 显示优先级（数字越大优先级越高）
    display_priority: int = 0
    # 选择类型
    mark_type: MinimapMarkType = MinimapMarkType.ICON
    # 显示高低差
    show_height_difference: bool = False
    # 是否可点击（图标、造物头像类型）
    clickable: bool = False
    # 文本内容（可点击时显示）
    text_content: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "小地图标识序号": self.mark_index,
            "标记名称": self.mark_name,
            "初始生效": self.initially_active,
            "初始所有玩家可见": self.visible_to_all_players,
            "跟随物体可见性": self.follow_object_visibility,
            "显示优先级": self.display_priority,
            "选择类型": self.mark_type.value,
            "显示高低差": self.show_height_difference,
            "是否可点击": self.clickable,
            "文本内容": self.text_content
        }


@dataclass
class MinimapComponentConfig:
    """
    小地图标识组件配置
    来源：小地图标识.md (第1-26行)
    """
    # 小地图标识列表
    marks: List[MinimapMarkDefinition] = field(default_factory=list)
    # 初始生效的标识序号列表
    initially_active_marks: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "小地图标识列表": [mark.to_dict() for mark in self.marks],
            "初始生效": self.initially_active_marks
        }

