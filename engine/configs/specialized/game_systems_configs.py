"""
高级游戏系统配置（技能资源、聊天、成就、排行榜、竞技段位）。
从 `extended_configs.py` 聚合文件中拆分而来，现作为专门模块使用。
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


# ============================================================================
# 技能资源系统
# ============================================================================

class SkillResourceGrowthType(Enum):
    """技能资源增长类型"""
    UNCONDITIONAL = "无条件增长"
    FOLLOW_SKILL_RETAIN = "跟随技能（保留值）"
    FOLLOW_SKILL_NO_RETAIN = "跟随技能（不保留值）"


@dataclass
class SkillResourceConfig:
    """
    技能资源配置
    参考：技能资源.md
    
    技能资源是特定技能释放时需要扣除的资源
    """
    resource_name: str = ""
    config_id: str = ""
    growth_type: SkillResourceGrowthType = SkillResourceGrowthType.UNCONDITIONAL
    max_obtainable_value: float = 100.0  # 可获取最大值
    reference_info: List[str] = field(default_factory=list)  # 引用信息
    
    doc_reference: str = "技能资源.md"


# ============================================================================
# 文字聊天系统
# ============================================================================

@dataclass
class ExtendedChatChannelConfig:
    """
    扩展的文字聊天频道配置（重命名以避免与management.ChatChannelConfig冲突）
    参考：文字聊天.md
    
    与 management.chat_configs.ChatChannelConfig 语义不同：
    - 本类：扩展的频道配置，包含应用玩家/阵营、快捷消息等高级特性
    - management 版本：简化的频道配置，用于基础管理
    
    原名：ChatChannelConfig
    """
    channel_name: str = ""
    channel_index: str = ""  # 频道唯一标识
    initial_active: bool = True  # 初始生效
    channel_application_type: str = "按玩家"  # 按玩家、按阵营
    applied_players_or_camps: List[str] = field(default_factory=list)  # 应用玩家/阵营
    display_priority: int = 0  # 显示优先级
    channel_icon: str = ""  # 图标
    quick_messages: List[str] = field(default_factory=list)  # 快捷消息
    
    doc_reference: str = "文字聊天.md"


@dataclass
class ChatSystemConfig:
    """
    文字聊天系统配置
    参考：文字聊天.md
    """
    chat_enabled: bool = True  # 是否开启文字聊天功能
    channels: List[ExtendedChatChannelConfig] = field(default_factory=list)
    
    doc_reference: str = "文字聊天.md"


# ============================================================================
# 成就系统
# ============================================================================

class AchievementRarity(Enum):
    """成就稀有度"""
    GOLD = "耀金"
    SILVER = "星银"
    COPPER = "辉铜"


@dataclass
class AchievementConfig:
    """
    成就配置
    参考：成就.md
    
    成就用于记录玩家在游戏中达成的特定目标或里程碑
    """
    achievement_name: str = ""
    achievement_index: str = ""  # 序号（唯一标识）
    rarity: Optional[AchievementRarity] = None  # 稀有度（普通成就）
    achievement_count: int = 0  # 成就计数（普通成就）
    description: str = ""  # 成就描述
    icon: str = ""  # 成就图标
    is_ultimate: bool = False  # 是否为极致成就
    
    doc_reference: str = "成就.md"
    
    notes: str = """
    成就特点：
    1. 累积进度可以跨对局继承
    2. 极致成就会在所有普通成就完成后自动达成
    3. 至少需要5个普通成就才能启用极致成就
    """


# ============================================================================
# 排行榜系统
# ============================================================================

@dataclass
class LeaderboardConfig:
    """
    排行榜配置
    参考：排行榜.md
    """
    leaderboard_name: str = ""
    leaderboard_index: str = ""  # 序号（唯一标识）
    display_priority: int = 0  # 显示优先级
    display_format: str = "纯数值"  # 显示格式：纯数值、时间、百分比
    reset_type: str = "不重置"  # 榜单重置类型：不重置、随赛季重置
    score_sort_rule: str = "越大越靠前"  # 成绩排序规则
    max_records: int = 1000  # 最大记录数
    
    doc_reference: str = "排行榜.md"
    
    notes: str = "排行榜功能与竞技段位功能仅可选择一项开放"


# ============================================================================
# 竞技段位系统
# ============================================================================

@dataclass
class CompetitiveRankScoreGroup:
    """
    竞技段位计分组配置
    参考：竞技段位.md
    """
    group_name: str = ""
    group_index: str = ""  # 序号（唯一标识）
    victory_score: int = 20  # 胜利分数
    defeat_score: int = -5  # 失败分数
    unsettled_score: int = 0  # 未结算分数
    escape_score: int = -20  # 逃跑分数
    included_players: List[str] = field(default_factory=list)  # 包含的玩家
    
    doc_reference: str = "竞技段位.md"


@dataclass
class CompetitiveRankConfig:
    """
    竞技段位配置
    参考：竞技段位.md
    """
    rank_enabled: bool = False  # 是否开启竞技段位
    room_play_allowed: bool = False  # 房间游玩准许记录竞技段位
    rank_announcement: str = ""  # 段位公告
    score_groups: List[CompetitiveRankScoreGroup] = field(default_factory=list)
    
    doc_reference: str = "竞技段位.md"
    
    notes: str = "排行榜和段位功能择一开放"

