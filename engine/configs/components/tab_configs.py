"""
组件配置 - 选项卡
基于知识库文档定义的选项卡组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from .collision_configs import TriggerArea


@dataclass
class TabDefinition:
    """
    选项卡定义
    来源：选项卡.md (第30-43行)
    对应编辑器中的“选项卡列表”区域：可以为同一个实体配置多个选项卡。
    每个选项卡都可以挂接一个本地过滤器节点图，用于在客户端按条件决定
    “对哪些玩家显示 / 对哪些玩家不显示”。
    """
    # 选项序号（在同一组件内唯一，节点图会通过该序号引用选项卡）
    tab_index: int
    # 选项卡图标（可选，美术资源 ID 或预设名称）
    tab_icon: str = ""
    # 初始生效：实体创建时该选项卡是否默认可用
    initially_active: bool = True
    # 排序等级（数字越大显示越靠前）
    sort_level: int = 0
    # 本地过滤器类型（例如“布尔过滤器”，留空表示不过滤）
    local_filter: str = ""
    # 过滤器节点图配置 ID，用于挂载客户端本地过滤器节点图（LOCAL_FILTER_GRAPH）
    # 例如：client_forge_hero_forge_tab_filter_01
    filter_graph_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "选项序号": self.tab_index,
            "选项卡图标": self.tab_icon,
            "初始生效": self.initially_active,
            "排序等级": self.sort_level,
            "本地过滤器": self.local_filter,
            "过滤器节点图": self.filter_graph_id,
        }


@dataclass
class TabComponentConfig:
    """
    选项卡组件配置
    来源：选项卡.md (第1-55行)
    注意：支持同时配置、生效多个选项卡（第3行）
    """
    # 选项卡列表
    tabs: List[TabDefinition] = field(default_factory=list)
    # 触发区域列表
    trigger_areas: List[TriggerArea] = field(default_factory=list)
    # 初始生效选项卡序号列表
    initially_active_tabs: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "选项卡列表": [tab.to_dict() for tab in self.tabs],
            "触发区域": [area.to_dict() for area in self.trigger_areas],
            "初始生效选项卡": self.initially_active_tabs
        }

