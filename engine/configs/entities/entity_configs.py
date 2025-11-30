"""
实体配置数据类
基于知识库文档定义的所有实体配置项
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


# ============== 枚举类型定义 ==============

class RevivePointSelectionRule(Enum):
    """复苏点选取规则（复苏.md:35）"""
    NEAREST = "最近的复苏点"
    LATEST_ACTIVATED = "最新激活的复苏点"
    HIGHEST_PRIORITY = "优先级最高的复苏点"
    RANDOM = "随机复苏点"


class SkillType(Enum):
    """技能类型"""
    NORMAL = "普通技能"
    ULTIMATE = "终极技能"
    PASSIVE = "被动技能"


class ResourceType(Enum):
    """资源消耗类型"""
    MANA = "法力值"
    ENERGY = "能量"
    HEALTH = "生命值"
    CUSTOM = "自定义资源"


# ============== 复苏配置（复苏.md 第19-37行）==============

@dataclass
class ReviveConfig:
    """
    复苏配置
    """
    # 允许复苏（布尔值）
    allow_revive: bool = True
    
    # 显示复苏界面（布尔值）
    show_revive_ui: bool = True
    
    # 复苏耗时(s)（浮点数）
    revive_duration: float = 0.0
    
    # 自动复苏（布尔值）
    auto_revive: bool = False
    
    # 复苏次数限制（整数，-1表示无限制）
    revive_count_limit: int = -1
    
    # 复苏点列表（预设点GUID列表）
    revive_point_list: List[str] = field(default_factory=list)
    
    # 复苏点选取规则
    revive_point_selection_rule: RevivePointSelectionRule = RevivePointSelectionRule.NEAREST
    
    # 复苏后生命比例(%)（浮点数，不可为0）
    revive_health_percentage: float = 100.0
    
    # 特殊被击倒损伤-扣除最大生命比例(%)（浮点数）
    special_knockdown_damage_percentage: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "允许复苏": self.allow_revive,
            "显示复苏界面": self.show_revive_ui,
            "复苏耗时(s)": self.revive_duration,
            "自动复苏": self.auto_revive,
            "复苏次数限制": self.revive_count_limit,
            "复苏点列表": self.revive_point_list,
            "复苏点选取规则": self.revive_point_selection_rule.value,
            "复苏后生命比例(%)": self.revive_health_percentage,
            "特殊被击倒损伤-扣除最大生命比例(%)": self.special_knockdown_damage_percentage
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviveConfig':
        rule_str = data.get("复苏点选取规则", RevivePointSelectionRule.NEAREST.value)
        rule = RevivePointSelectionRule(rule_str)
        
        return cls(
            allow_revive=data.get("允许复苏", True),
            show_revive_ui=data.get("显示复苏界面", True),
            revive_duration=data.get("复苏耗时(s)", 0.0),
            auto_revive=data.get("自动复苏", False),
            revive_count_limit=data.get("复苏次数限制", -1),
            revive_point_list=data.get("复苏点列表", []),
            revive_point_selection_rule=rule,
            revive_health_percentage=data.get("复苏后生命比例(%)", 100.0),
            special_knockdown_damage_percentage=data.get("特殊被击倒损伤-扣除最大生命比例(%)", 0.0)
        )


# ============== 本地投射物配置（本地投射物.md）==============

@dataclass
class LocalProjectileBaseSettings:
    """本地投射物基础设置（本地投射物.md 第23-27行）"""
    # 模型配置
    model_config: str = ""
    # xyz缩放
    scale_x: float = 1.0
    scale_y: float = 1.0
    scale_z: float = 1.0


@dataclass
class LocalProjectileCombatParams:
    """本地投射物战斗参数（本地投射物.md 第29-33行）"""
    # 属性设置
    attribute_settings: Dict[str, Any] = field(default_factory=dict)
    # 是否受创建者影响
    affected_by_creator: bool = True


@dataclass
class LocalProjectileLifecycle:
    """本地投射物生命周期设置（本地投射物.md 第35-43行）"""
    # 永久持续
    permanent: bool = False
    # 持续时长(s)
    duration: float = 5.0
    # 达到xz轴最大距离后销毁
    destroy_at_xz_max_distance: bool = False
    xz_max_distance: float = 100.0
    # 达到y轴最大距离后销毁
    destroy_at_y_max_distance: bool = False
    y_max_distance: float = 50.0
    # 生命周期结束行为（能力单元列表）
    lifecycle_end_behavior: List[str] = field(default_factory=list)


@dataclass
class LocalProjectileConfig:
    """本地投射物完整配置"""
    base_settings: LocalProjectileBaseSettings = field(default_factory=LocalProjectileBaseSettings)
    combat_params: LocalProjectileCombatParams = field(default_factory=LocalProjectileCombatParams)
    lifecycle: LocalProjectileLifecycle = field(default_factory=LocalProjectileLifecycle)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "基础设置": {
                "模型配置": self.base_settings.model_config,
                "xyz缩放": {
                    "x": self.base_settings.scale_x,
                    "y": self.base_settings.scale_y,
                    "z": self.base_settings.scale_z
                }
            },
            "战斗参数": {
                "属性设置": self.combat_params.attribute_settings,
                "是否受创建者影响": self.combat_params.affected_by_creator
            },
            "生命周期设置": {
                "永久持续": self.lifecycle.permanent,
                "持续时长(s)": self.lifecycle.duration,
                "达到xz轴最大距离后销毁": self.lifecycle.destroy_at_xz_max_distance,
                "xz轴最大距离": self.lifecycle.xz_max_distance,
                "达到y轴最大距离后销毁": self.lifecycle.destroy_at_y_max_distance,
                "y轴最大距离": self.lifecycle.y_max_distance,
                "生命周期结束行为": self.lifecycle.lifecycle_end_behavior
            }
        }


# ============== 玩家配置 ==============

@dataclass
class PlayerConfig:
    """
    玩家实体配置
    """
    # 生效目标
    effective_target: str = "全部玩家"
    # 等级
    level: int = 1
    # 出生点（预设点GUID）
    spawn_point: str = ""
    # 初始职业
    initial_profession: str = ""
    # 复苏配置
    revive_config: ReviveConfig = field(default_factory=ReviveConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "生效目标": self.effective_target,
            "等级": self.level,
            "出生点": self.spawn_point,
            "初始职业": self.initial_profession,
            "复苏配置": self.revive_config.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlayerConfig':
        revive_config_data = data.get("复苏配置", {})
        return cls(
            effective_target=data.get("生效目标", "全部玩家"),
            level=data.get("等级", 1),
            spawn_point=data.get("出生点", ""),
            initial_profession=data.get("初始职业", ""),
            revive_config=ReviveConfig.from_dict(revive_config_data)
        )


# ============== 技能配置（技能.md）==============

@dataclass
class SkillConfig:
    """
    技能配置
    """
    # 技能类型
    skill_type: SkillType = SkillType.NORMAL
    # 启用运动坠崖保护
    enable_fall_protection: bool = False
    # 是否可以在空中释放
    can_cast_in_air: bool = True
    # 技能备注
    skill_note: str = ""
    
    # 冷却配置
    has_cooldown: bool = True
    cooldown_time: float = 0.0
    
    # 次数配置
    has_usage_limit: bool = False
    usage_count: int = 1
    
    # 消耗配置
    has_cost: bool = False
    cost_type: ResourceType = ResourceType.MANA
    cost_amount: float = 0.0
    
    # 索敌范围
    lock_range: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "技能类型": self.skill_type.value,
            "启用运动坠崖保护": self.enable_fall_protection,
            "是否可以在空中释放": self.can_cast_in_air,
            "技能备注": self.skill_note,
            "是否有冷却时间": self.has_cooldown,
            "冷却时间(s)": self.cooldown_time,
            "是否有次数限制": self.has_usage_limit,
            "使用次数": self.usage_count,
            "是否有消耗": self.has_cost,
            "消耗类型": self.cost_type.value,
            "消耗量": self.cost_amount,
            "索敌范围": self.lock_range
        }


# ============== 基础战斗属性配置 ==============

@dataclass
class BaseCombatAttributes:
    """基础战斗属性配置（角色、造物通用）"""
    # 等级
    level: int = 1
    # 基础生命值
    base_health: float = 100.0
    # 基础攻击力
    base_attack: float = 10.0
    # 属性成长（每级增加的属性）
    health_growth: float = 0.0
    attack_growth: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "等级": self.level,
            "基础生命值": self.base_health,
            "基础攻击力": self.base_attack,
            "生命值成长": self.health_growth,
            "攻击力成长": self.attack_growth
        }


# ============== 造物配置 ==============

@dataclass
class CreatureConfig:
    """
    造物实体配置
    """
    # 基础战斗属性
    combat_attributes: BaseCombatAttributes = field(default_factory=BaseCombatAttributes)
    # 仇恨配置
    hatred_config: Dict[str, Any] = field(default_factory=dict)
    # 常规设置
    general_settings: Dict[str, Any] = field(default_factory=dict)
    # 行为模式
    behavior_mode: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "基础战斗属性": self.combat_attributes.to_dict(),
            "仇恨配置": self.hatred_config,
            "常规设置": self.general_settings,
            "行为模式": self.behavior_mode
        }


# ============== 角色配置 ==============

@dataclass
class CharacterConfig:
    """
    角色实体配置
    """
    # 基础战斗属性
    combat_attributes: BaseCombatAttributes = field(default_factory=BaseCombatAttributes)
    # 装备栏配置
    equipment_slots: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "基础战斗属性": self.combat_attributes.to_dict(),
            "装备栏": self.equipment_slots
        }


# ============== 物件配置 ==============

@dataclass
class ObjectConfig:
    """
    物件实体配置
    """
    # 是否为静态物件
    is_static: bool = True
    # 预设状态（仅动态物件）
    preset_state: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "是否为静态物件": self.is_static,
            "预设状态": self.preset_state if not self.is_static else ""
        }

