"""
高级概念配置
基于知识库文档定义的护盾、单位状态、职业等配置
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

# 从 management 和 entities 导入标准配置（避免重复定义）
from engine.configs.management.tag_shield_configs import ShieldConfig
from engine.configs.management.ingame_save_config import InGameSaveConfig, SaveScope
from engine.configs.entities.profession_config import ProfessionConfig, ProfessionType

# 为了向后兼容，创建别名
AdvancedShieldConfig = ShieldConfig


# ============== 护盾配置（护盾.md）==============
# 注意：AdvancedShieldConfig 已从 management.tag_shield_configs 导入（使用 ShieldConfig 并创建别名），避免重复定义


# ============== 单位状态配置（单位状态.md）==============

class StackRuleType(Enum):
    """叠加规则类型"""
    UPDATE_OVERFLOW = "更新过量叠加数据"
    DISCARD_OVERFLOW = "丢弃过量叠加数据"


class UpdateStrategy(Enum):
    """不同施加来源的更新策略"""
    CANNOT_UPDATE = "无法更新"
    SHORTEST_REMAINING = "最短剩余时长"
    EARLIEST_UPDATE = "最早更新时刻"
    EARLIEST_APPLY = "最早施加时刻"


@dataclass
class UnitStateStackRule:
    """
    单位状态叠加规则
    来源：单位状态.md (第22行)
    """
    # 叠加层数上限
    stack_limit: int = 1
    # 是否更新过量叠加数据
    update_overflow: bool = False


@dataclass
class UnitStateTimingRule:
    """
    单位状态计时规则
    来源：单位状态.md (第25-27行)
    """
    # 启用无限持续时间
    infinite_duration: bool = False
    # 初始运行时长(s)
    initial_duration: float = 10.0
    # 启用叠加共享时长
    share_duration_on_stack: bool = False
    # 延续时长(s)
    extend_duration: float = 0.0
    # 启用最大延续时长限制
    enable_max_extend: bool = False
    # 最大时长(s)
    max_duration: float = 30.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "启用无限持续时间": self.infinite_duration,
            "初始运行时长(s)": self.initial_duration,
            "启用叠加共享时长": self.share_duration_on_stack,
            "延续时长(s)": self.extend_duration,
            "启用最大延续时长限制": self.enable_max_extend,
            "最大时长(s)": self.max_duration
        }


@dataclass
class UnitStateCoexistenceRule:
    """
    单位状态并存规则
    来源：单位状态.md (第32-34行)
    """
    # 不同施加来源可叠加
    different_source_stackable: bool = True
    # 记录最新施加者
    record_latest_applier: bool = True
    # 并存上限
    coexistence_limit: int = 1
    # 更新策略
    update_strategy: UpdateStrategy = UpdateStrategy.CANNOT_UPDATE
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "不同施加来源可叠加": self.different_source_stackable,
            "记录最新施加者": self.record_latest_applier,
            "并存上限": self.coexistence_limit,
            "更新策略": self.update_strategy.value
        }


@dataclass
class UnitStateConfig:
    """
    单位状态配置
    来源：单位状态.md
    """
    # 命名与标识
    state_name: str
    config_id: str
    icon: str = ""
    
    # 叠加规则
    stack_rule: UnitStateStackRule = field(default_factory=UnitStateStackRule)
    
    # 计时规则
    timing_rule: UnitStateTimingRule = field(default_factory=UnitStateTimingRule)
    
    # 关联节点图
    associated_graph: str = ""
    
    # 状态并存规则
    coexistence_rule: UnitStateCoexistenceRule = field(default_factory=UnitStateCoexistenceRule)
    
    # 让位状态列表
    yield_states: List[str] = field(default_factory=list)
    
    # 顶替状态列表
    replace_states: List[str] = field(default_factory=list)
    
    # 额外效果列表
    effects: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "状态名称": self.state_name,
            "配置ID": self.config_id,
            "图标": self.icon,
            "叠加规则": {
                "叠加层数上限": self.stack_rule.stack_limit,
                "更新过量叠加数据": self.stack_rule.update_overflow
            },
            "计时规则": self.timing_rule.to_dict(),
            "关联节点图": self.associated_graph,
            "状态并存规则": self.coexistence_rule.to_dict(),
            "让位状态列表": self.yield_states,
            "顶替状态列表": self.replace_states,
            "额外效果列表": self.effects
        }


# ============== 关卡结算配置（关卡结算.md）==============

class SettlementResultType(Enum):
    """结算状态类型"""
    VICTORY = "胜利"
    DEFEAT = "失败"
    UNSETTLED = "未结算"


class SettlementInterfaceType(Enum):
    """结算界面类型（关卡结算.md 第18行）"""
    FACTION = "阵营结算"
    INDIVIDUAL = "个人结算"


class RankingSortOrder(Enum):
    """排名数值比较顺序（关卡结算.md 第22行）"""
    ASCENDING = "由小到大"
    DESCENDING = "由大到小"


@dataclass
class LevelSettlementConfig:
    """
    关卡结算配置
    来源：关卡结算.md (第13-24行)
    """
    # 试玩时运行
    run_in_playtest: bool = True
    # 结算界面类型
    interface_type: SettlementInterfaceType = SettlementInterfaceType.INDIVIDUAL
    # 启用游戏内排名
    enable_in_game_ranking: bool = False
    # 排名数值比较顺序
    ranking_sort_order: RankingSortOrder = RankingSortOrder.DESCENDING
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "试玩时运行": self.run_in_playtest,
            "结算界面类型": self.interface_type.value,
            "启用游戏内排名": self.enable_in_game_ranking,
            "排名数值比较顺序": self.ranking_sort_order.value
        }


if __name__ == "__main__":
    # 测试护盾配置
    print("=== 护盾配置测试 ===")
    shield = AdvancedShieldConfig(
        shield_name="火焰护盾",
        shield_id="shield_001",  # 使用 shield_id 而不是 config_id
        shield_value=500.0,
        absorption_ratio=1.5,
        settlement_priority=10
    )
    print(f"护盾名称: {shield.shield_name}")
    print(f"护盾值: {shield.shield_value}")
    print(f"吸收比例: {shield.absorption_ratio}")
    
    # 测试单位状态配置
    print("\n=== 单位状态配置测试 ===")
    state = UnitStateConfig(
        state_name="燃烧状态",
        config_id="state_burn_001"
    )
    state.stack_rule.stack_limit = 5
    state.timing_rule.initial_duration = 10.0
    print(f"状态名称: {state.state_name}")
    print(f"叠加上限: {state.stack_rule.stack_limit}")
    print(f"初始时长: {state.timing_rule.initial_duration}秒")
    
    # 测试关卡结算配置
    print("\n=== 关卡结算配置测试 ===")
    settlement = LevelSettlementConfig(
        enable_in_game_ranking=True,
        ranking_sort_order=RankingSortOrder.DESCENDING
    )
    print(f"结算界面类型: {settlement.interface_type.value}")
    print(f"启用排名: {settlement.enable_in_game_ranking}")


# ============================================================================
# 职业系统配置 (职业.md)
# ============================================================================
# 注意：ProfessionConfig 和 ProfessionType 已从 entities.profession_config 导入，避免重复定义


# ============================================================================
# 局内存档系统配置 (局内存档.md)
# ============================================================================
# 注意：InGameSaveConfig 和 SaveScope 已从 management.ingame_save_config 导入，避免重复定义

