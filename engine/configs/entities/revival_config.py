"""
复苏系统配置模块

本模块实现玩家和角色的复苏系统配置，包括：
- 复苏配置项
- 复苏点设置
- 复苏相关节点定义
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class RevivalPointSelectionRule(Enum):
    """复苏点选取规则"""
    NEAREST = "最近的复苏点"  # 选取距离倒下位置空间距离上最近的合法复苏点
    LATEST_ACTIVATED = "最新激活的复苏点"  # 时间上最新激活的复苏点
    HIGHEST_PRIORITY = "优先级最高的复苏点"  # 当前合法复苏点列表中优先级最高的复苏点
    RANDOM = "随机复苏点"  # 从当前的合法复苏点列表中随机选取一个


class DownReason(Enum):
    """倒下原因"""
    NODE_GRAPH = "节点图导致"  # 被节点图中的节点击倒
    NORMAL = "正常击倒"  # 因玩家队伍内所有角色生命值降为0所有角色倒下
    ABNORMAL = "非正常击倒"  # 因为坠落深渊、溺水等原因被击倒


@dataclass
class RevivalPoint:
    """复苏点配置"""
    point_id: str = ""
    position: tuple = (0.0, 0.0, 0.0)
    priority: int = 0  # 优先级，用于优先级最高的复苏点选取规则
    is_active: bool = True  # 是否激活
    activation_time: float = 0.0  # 激活时间戳
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "复苏点ID": self.point_id,
            "位置": list(self.position),
            "优先级": self.priority,
            "是否激活": self.is_active,
            "激活时间": self.activation_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RevivalPoint':
        return cls(
            point_id=data.get("复苏点ID", ""),
            position=tuple(data.get("位置", [0.0, 0.0, 0.0])),
            priority=data.get("优先级", 0),
            is_active=data.get("是否激活", True),
            activation_time=data.get("激活时间", 0.0)
        )


@dataclass
class RevivalConfig:
    """玩家复苏配置
    
    配置项说明：
    - allow_revival: 允许复苏。当配置为False时，该玩家无法复苏
    - show_revival_ui: 显示复苏界面。当配置为False时，该玩家倒下后不会弹出复苏界面
    - revival_time: 复苏耗时（秒）。玩家倒下后必须等待的时间
    - auto_revival: 自动复苏。在倒下后，等待复苏时间后自动复苏
    - revival_count_limit: 复苏次数限制。当复苏的次数超过限制后，无法复苏
    - revival_points: 复苏点列表。这名玩家默认的合法复苏点列表
    - point_selection_rule: 复苏点选取规则
    - revival_health_percent: 复苏后生命比例（%）。复苏后角色生命值百分比
    - special_down_damage_percent: 特殊被击倒损伤-扣除最大生命比例（%）。溺水、坠入深渊后扣除的生命值百分比
    """
    allow_revival: bool = True  # 允许复苏
    show_revival_ui: bool = True  # 显示复苏界面
    revival_time: float = 0.0  # 复苏耗时（秒）
    auto_revival: bool = False  # 自动复苏
    revival_count_limit: int = -1  # 复苏次数限制（-1表示无限制）
    revival_points: List[RevivalPoint] = field(default_factory=list)  # 复苏点列表
    point_selection_rule: RevivalPointSelectionRule = RevivalPointSelectionRule.NEAREST  # 复苏点选取规则
    revival_health_percent: float = 100.0  # 复苏后生命比例（%）
    special_down_damage_percent: float = 0.0  # 特殊被击倒损伤-扣除最大生命比例（%）
    
    # 运行时数据
    remaining_revival_count: int = -1  # 剩余复苏次数
    current_revival_time: float = 0.0  # 当前复苏耗时
    
    def __post_init__(self):
        """初始化后设置剩余复苏次数"""
        if self.remaining_revival_count == -1:
            self.remaining_revival_count = self.revival_count_limit
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "允许复苏": self.allow_revival,
            "显示复苏界面": self.show_revival_ui,
            "复苏耗时(s)": self.revival_time,
            "自动复苏": self.auto_revival,
            "复苏次数限制": self.revival_count_limit,
            "复苏点列表": [point.to_dict() for point in self.revival_points],
            "复苏点选取规则": self.point_selection_rule.value,
            "复苏后生命比例(%)": self.revival_health_percent,
            "特殊被击倒损伤-扣除最大生命比例(%)": self.special_down_damage_percent,
            "剩余复苏次数": self.remaining_revival_count,
            "当前复苏耗时": self.current_revival_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RevivalConfig':
        revival_points = [
            RevivalPoint.from_dict(point_data) 
            for point_data in data.get("复苏点列表", [])
        ]
        
        selection_rule_value = data.get("复苏点选取规则", "最近的复苏点")
        selection_rule = RevivalPointSelectionRule.NEAREST
        for rule in RevivalPointSelectionRule:
            if rule.value == selection_rule_value:
                selection_rule = rule
                break
        
        return cls(
            allow_revival=data.get("允许复苏", True),
            show_revival_ui=data.get("显示复苏界面", True),
            revival_time=data.get("复苏耗时(s)", 0.0),
            auto_revival=data.get("自动复苏", False),
            revival_count_limit=data.get("复苏次数限制", -1),
            revival_points=revival_points,
            point_selection_rule=selection_rule,
            revival_health_percent=data.get("复苏后生命比例(%)", 100.0),
            special_down_damage_percent=data.get("特殊被击倒损伤-扣除最大生命比例(%)", 0.0),
            remaining_revival_count=data.get("剩余复苏次数", -1),
            current_revival_time=data.get("当前复苏耗时", 0.0)
        )
    
    def validate(self) -> tuple[bool, str]:
        """验证复苏配置"""
        if self.revival_health_percent <= 0:
            return False, "复苏后生命比例必须大于0"
        
        if self.revival_health_percent > 100:
            return False, "复苏后生命比例不能超过100%"
        
        if self.revival_time < 0:
            return False, "复苏耗时不能为负数"
        
        if self.special_down_damage_percent < 0 or self.special_down_damage_percent > 100:
            return False, "特殊被击倒损伤比例必须在0-100%之间"
        
        return True, "验证通过"


# ==================== 复苏相关节点定义 ====================

REVIVAL_EXECUTION_NODES = {
    "复苏角色": {
        "类型": "执行节点",
        "功能": "复苏一个指定角色。在超限模式中，与【复苏玩家所有角色】功能相似，会复苏玩家的角色、并解除玩家的所有角色倒下状态。这次复苏不会扣除玩家的复苏次数",
        "输入引脚": [
            {"名称": "角色实体", "类型": "实体", "说明": "需要复苏的指定角色实体"}
        ],
        "输出引脚": []
    },
    
    "复苏玩家所有角色": {
        "类型": "执行节点",
        "功能": "复苏玩家的所有角色。在超限模式中，与【复苏角色】功能相似，会复苏玩家的角色并解除所有角色倒下状态，可以选择是否扣除玩家的复苏次数",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "需要所有角色复苏的玩家实体"},
            {"名称": "是否扣除复苏次数", "类型": "布尔值", "说明": "如果为【是】，则复苏时扣除1次复苏次数。如果复苏次数不足1次，则该节点无法执行"}
        ],
        "输出引脚": []
    },
    
    "击倒玩家所有角色": {
        "类型": "执行节点",
        "功能": "击倒玩家的所有角色，会使玩家进入所有角色倒下状态",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"}
        ],
        "输出引脚": []
    },
    
    "设置玩家复苏耗时": {
        "类型": "执行节点",
        "功能": "修改指定玩家的下次复苏耗时。如果玩家当前处于复苏计时中，不会修改当前的复苏耗时",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "时长", "类型": "浮点数", "说明": "设置的复苏时间，以秒为单位"}
        ],
        "输出引脚": []
    },
    
    "设置玩家剩余复苏次数": {
        "类型": "执行节点",
        "功能": "修改指定玩家剩余的复苏次数。设置为0会使这名玩家无法复苏",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "剩余次数", "类型": "整数", "说明": "设置的剩余复苏次数"}
        ],
        "输出引脚": []
    },
    
    "允许/禁止玩家复苏": {
        "类型": "执行节点",
        "功能": "修改指定玩家是否允许复苏",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "是否允许", "类型": "布尔值", "说明": "设置是否允许复苏"}
        ],
        "输出引脚": []
    },
    
    "激活复苏点": {
        "类型": "执行节点",
        "功能": "激活指定玩家的复苏点，将其添加到合法复苏点列表中",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "复苏点", "类型": "复苏点", "说明": "要激活的复苏点"}
        ],
        "输出引脚": []
    },
    
    "注销复苏点": {
        "类型": "执行节点",
        "功能": "注销指定玩家的复苏点，将其从合法复苏点列表中移除",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "复苏点", "类型": "复苏点", "说明": "要注销的复苏点"}
        ],
        "输出引脚": []
    }
}


REVIVAL_EVENT_NODES = {
    "玩家所有角色复苏时": {
        "类型": "事件节点",
        "功能": "当玩家所有角色解除倒下状态、复苏时触发。注意，因为角色复苏导致的玩家解除倒下状态不会触发这个事件",
        "输入引脚": [],
        "输出引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "被复苏的玩家实体"}
        ]
    },
    
    "玩家所有角色倒下时": {
        "类型": "事件节点",
        "功能": "玩家进入所有角色倒下状态时触发",
        "输入引脚": [],
        "输出引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "所有角色倒下的玩家实体"},
            {"名称": "原因", "类型": "枚举", "说明": "玩家所有角色倒下的原因"}
        ]
    },
    
    "玩家异常倒下并复苏时": {
        "类型": "事件节点",
        "功能": "玩家因坠落深渊、溺水等原因被击倒并复苏时",
        "输入引脚": [],
        "输出引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "因溺水、坠落深渊等原因被击倒的玩家实体"}
        ]
    },
    
    "角色倒下时": {
        "类型": "事件节点",
        "功能": "角色倒下时触发的事件。在当前模式中，因为玩家只有一名角色，因此之后会连续触发【玩家所有角色倒下时】",
        "输入引脚": [],
        "输出引脚": [
            {"名称": "角色实体", "类型": "实体", "说明": "倒下的角色实体"},
            {"名称": "原因", "类型": "枚举", "说明": "角色倒下的原因"}
        ]
    },
    
    "角色复苏时": {
        "类型": "事件节点",
        "功能": "角色复苏时触发的事件",
        "输入引脚": [],
        "输出引脚": [
            {"名称": "角色实体", "类型": "实体", "说明": "复苏的角色实体"}
        ]
    }
}


REVIVAL_QUERY_NODES = {
    "查询玩家角色是否全部倒下": {
        "类型": "查询节点",
        "功能": "查询玩家的所有角色是否已全部倒下",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "查询的目标玩家实体"}
        ],
        "输出引脚": [
            {"名称": "结果", "类型": "布尔值", "说明": "是否已全部倒下"}
        ]
    },
    
    "获取玩家复苏耗时": {
        "类型": "查询节点",
        "功能": "获取指定玩家的复苏耗时",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "查询的目标玩家实体"}
        ],
        "输出引脚": [
            {"名称": "时长", "类型": "浮点数", "说明": "获取的复苏耗时"}
        ]
    },
    
    "获取玩家剩余复苏次数": {
        "类型": "查询节点",
        "功能": "查询玩家的剩余复苏次数",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "查询的目标玩家实体"}
        ],
        "输出引脚": [
            {"名称": "剩余次数", "类型": "整数", "说明": "获取的剩余复苏次数"}
        ]
    }
}


# 导出所有复苏相关节点
REVIVAL_NODES = {
    **REVIVAL_EXECUTION_NODES,
    **REVIVAL_EVENT_NODES,
    **REVIVAL_QUERY_NODES
}

