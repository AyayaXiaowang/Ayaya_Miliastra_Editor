"""
能力单元配置
基于知识库：能力单元.md, 能力单元效果.md
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple
from enum import Enum


# ============================================================================
# 能力单元 (能力单元.md, 能力单元效果.md)
# ============================================================================

class AbilityUnitType(str, Enum):
    """能力单元类型"""
    ATTACK_BOX = "攻击盒攻击"
    DIRECT_ATTACK = "直接攻击"
    PLAY_EFFECT = "播放特效"
    CREATE_PROJECTILE = "创建本地投射物"
    ADD_UNIT_STATUS = "添加单位状态"
    REMOVE_UNIT_STATUS = "移除单位状态"
    DESTROY_SELF = "销毁自身"
    RESTORE_HEALTH = "恢复生命"


class AttackBoxShape(str, Enum):
    """攻击盒形状"""
    CUBOID = "长方体"
    SPHERE = "球体"
    CYLINDER = "圆柱体"


class BasePosition(str, Enum):
    """基准位置"""
    SELF = "自身"
    HIT_LOCATION = "命中位置"


class CampFilter(str, Enum):
    """阵营筛选"""
    NO_TARGET = "不找目标"
    FRIENDLY = "友善阵营"
    HOSTILE = "敌对阵营"
    SELF = "自身"
    SELF_CAMP = "自身所在阵营"
    ALL = "全部"
    ALL_EXCEPT_SELF = "除自身外全部"
    FRIENDLY_INCLUDING_SELF = "友善阵营包括自身"


class AttackLayerFilter(str, Enum):
    """攻击层筛选"""
    HITBOX_ONLY = "只命中受击盒"
    SCENE_ONLY = "只命中场景"
    ALL_LAYERS = "全部命中"


class TriggerType(str, Enum):
    """触发类型"""
    ONCE_PER_LIFETIME = "生命周期只触发一次"
    ONCE_PER_ENTITY = "每个实体只触发一次"


class ElementType(str, Enum):
    """元素类型"""
    NONE = "无元素"
    FIRE = "火"
    WATER = "水"
    WIND = "风"
    ELECTRIC = "电"
    ICE = "冰"
    ROCK = "岩"
    GRASS = "草"


class HitType(str, Enum):
    """打击类型"""
    NONE = "无"
    DEFAULT = "默认"
    SLASH = "斩击"
    BLUNT = "钝击"
    PROJECTILE = "投射物"
    PIERCE = "刺击攻击"


class AttackType(str, Enum):
    """攻击类型"""
    NONE = "无"
    MELEE = "近战攻击"
    RANGED = "远程攻击"
    DEFAULT = "默认"


class DamageCurveType(str, Enum):
    """伤害变化曲线类型"""
    NO_CHANGE = "无变化"
    CUSTOM = "自定义变化曲线"
    PRESET_DECAY = "预制衰减曲线"
    PRESET_GROWTH = "预制增长曲线"


class DistanceCalculationType(str, Enum):
    """距离计算方式"""
    FROM_CURRENT_POSITION = "与当前位置的距离"
    FROM_SPAWN_POSITION = "与创生位置的距离"


class HitReactionType(str, Enum):
    """受击表现类型"""
    LIGHT = "轻"
    MEDIUM = "中"
    HEAVY = "重"
    CUSTOM = "自定义"


class KnockbackDirection(str, Enum):
    """受击击退朝向"""
    ATTACKER_TO_HIT = "攻击者与受击点的连线"
    ATTACK_BOX_DIRECTION = "攻击盒命中朝向"
    ATTACKER_OWNER_TO_HIT = "攻击者主人与受击点连线"
    ATTACKER_TO_HIT_TANGENT = "攻击者与受击点连线切线"
    HIT_REVERSE = "受击反朝向"
    ATTACKER_FACING = "攻击者面朝朝向"
    ATTACKER_TO_HIT_REVERSE = "攻击者与受击点连线反朝向"


class HealthRestoreBaseType(str, Enum):
    """百分比恢复基准方式"""
    TARGET_MAX_HEALTH = "基于目标最大生命"
    TARGET_CURRENT_HEALTH = "基于目标当前生命"
    CASTER_MAX_HEALTH = "基于释放者最大生命"
    CASTER_ATTACK = "基于释放者攻击力"


@dataclass
class AttackBoxConfig:
    """攻击盒配置"""
    base_position: BasePosition = BasePosition.SELF
    shape: AttackBoxShape = AttackBoxShape.SPHERE
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    position_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "能力单元效果.md:3-12"


@dataclass
class TargetFilterConfig:
    """目标筛选配置"""
    camp_filter: CampFilter = CampFilter.HOSTILE
    entity_type_filter: List[str] = field(default_factory=lambda: ["角色", "造物"])  # 物件、角色、造物
    attack_layer_filter: AttackLayerFilter = AttackLayerFilter.HITBOX_ONLY
    trigger_type: TriggerType = TriggerType.ONCE_PER_ENTITY
    
    doc_reference: str = "能力单元效果.md:13-21"


@dataclass
class AttackParametersConfig:
    """攻击参数配置"""
    damage_coefficient: float = 1.0  # 伤害系数
    damage_increment: float = 0.0  # 伤害增量
    element_type: ElementType = ElementType.NONE
    element_amount: float = 0.0  # 元素含量
    hit_type: HitType = HitType.DEFAULT
    attack_type: AttackType = AttackType.DEFAULT
    interrupt_value: float = 0.0  # 打断值
    is_absolute_damage: bool = False  # 是否是绝对伤害
    damage_curve_type: DamageCurveType = DamageCurveType.NO_CHANGE
    distance_calculation: DistanceCalculationType = DistanceCalculationType.FROM_CURRENT_POSITION
    extra_shield_break: float = 0.0  # 额外破盾值
    shield_penetration_rate: float = 0.0  # 护盾穿透率(0-1)
    
    doc_reference: str = "能力单元效果.md:22-38"


@dataclass
class HitPresentationConfig:
    """命中表现配置"""
    hit_scene_effect: Optional[str] = None  # 命中场景特效（资产ID）
    hit_target_effect: Optional[str] = None  # 命中目标特效（资产ID）
    hit_reaction_type: HitReactionType = HitReactionType.MEDIUM
    hit_level: int = 1  # 受击等级
    horizontal_impulse: float = 0.0  # 水平冲量
    vertical_impulse: float = 0.0  # 垂直冲量
    knockback_direction: KnockbackDirection = KnockbackDirection.ATTACKER_TO_HIT
    hide_damage_number: bool = False  # 屏蔽伤害跳字
    
    doc_reference: str = "能力单元效果.md:42-53"


@dataclass
class AttackBoxAttackAbility:
    """攻击盒攻击能力单元"""
    ability_name: str = ""
    attack_box: AttackBoxConfig = field(default_factory=AttackBoxConfig)
    target_filter: TargetFilterConfig = field(default_factory=TargetFilterConfig)
    attack_parameters: AttackParametersConfig = field(default_factory=AttackParametersConfig)
    hit_presentation: HitPresentationConfig = field(default_factory=HitPresentationConfig)
    attack_tags: List[str] = field(default_factory=list)
    
    doc_reference: str = "能力单元效果.md:1-61"


@dataclass
class DirectAttackAbility:
    """直接攻击能力单元"""
    ability_name: str = ""
    attack_parameters: AttackParametersConfig = field(default_factory=AttackParametersConfig)
    hit_presentation: HitPresentationConfig = field(default_factory=HitPresentationConfig)
    attack_tags: List[str] = field(default_factory=list)
    
    doc_reference: str = "能力单元效果.md:63-73"


@dataclass
class PlayEffectAbility:
    """播放特效能力单元"""
    ability_name: str = ""
    effect_asset: str = ""  # 限时特效资产
    create_position: BasePosition = BasePosition.SELF
    scale: float = 1.0
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "能力单元效果.md:75-84"


@dataclass
class CreateProjectileAbility:
    """创建投射物能力单元"""
    ability_name: str = ""
    projectile_asset: str = ""  # 投射物资产ID
    create_position: BasePosition = BasePosition.SELF
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "能力单元效果.md:86-94"


@dataclass
class AddUnitStatusAbility:
    """添加单位状态能力单元"""
    ability_name: str = ""
    unit_status_asset: str = ""  # 单位状态资产ID
    stack_count: int = 1  # 层数
    
    doc_reference: str = "能力单元效果.md:96-102"


@dataclass
class RemoveUnitStatusAbility:
    """移除单位状态能力单元"""
    ability_name: str = ""
    unit_status_asset: str = ""  # 单位状态资产ID
    
    doc_reference: str = "能力单元效果.md:104-109"


@dataclass
class DestroySelfAbility:
    """销毁自身能力单元"""
    ability_name: str = ""
    delay_time: float = 0.0  # 延迟时间(秒)
    
    doc_reference: str = "能力单元效果.md:111-116"


@dataclass
class RestoreHealthAbility:
    """恢复生命能力单元"""
    ability_name: str = ""
    restore_base_type: HealthRestoreBaseType = HealthRestoreBaseType.TARGET_MAX_HEALTH
    percentage: float = 0.0  # 百分比(0-1)
    extra_fixed_value: float = 0.0  # 额外固定恢复值
    ignore_restore_adjustment: bool = False  # 是否忽略恢复调整
    heal_tags: List[str] = field(default_factory=list)  # 治疗标签
    
    doc_reference: str = "能力单元效果.md:118-127"


@dataclass
class AbilityUnitConfig:
    """能力单元配置"""
    unit_type: AbilityUnitType
    config: Any  # 具体类型根据unit_type决定
    
    doc_reference: str = "能力单元.md"
    
    def serialize(self) -> dict:
        result = {
            "unit_type": self.unit_type.value
        }
        
        if isinstance(self.config, (AttackBoxAttackAbility, DirectAttackAbility, PlayEffectAbility,
                                     CreateProjectileAbility, AddUnitStatusAbility, RemoveUnitStatusAbility,
                                     DestroySelfAbility, RestoreHealthAbility)):
            # 序列化dataclass
            from dataclasses import asdict
            result["config"] = asdict(self.config)
        else:
            result["config"] = self.config
        
        return result
    
    @staticmethod
    def deserialize(data: dict) -> 'AbilityUnitConfig':
        unit_type = AbilityUnitType(data["unit_type"])
        config_data = data.get("config", {})
        
        # 根据类型创建对应的配置对象
        if unit_type == AbilityUnitType.ATTACK_BOX:
            config = AttackBoxAttackAbility(**config_data)
        elif unit_type == AbilityUnitType.DIRECT_ATTACK:
            config = DirectAttackAbility(**config_data)
        elif unit_type == AbilityUnitType.PLAY_EFFECT:
            config = PlayEffectAbility(**config_data)
        elif unit_type == AbilityUnitType.CREATE_PROJECTILE:
            config = CreateProjectileAbility(**config_data)
        elif unit_type == AbilityUnitType.ADD_UNIT_STATUS:
            config = AddUnitStatusAbility(**config_data)
        elif unit_type == AbilityUnitType.REMOVE_UNIT_STATUS:
            config = RemoveUnitStatusAbility(**config_data)
        elif unit_type == AbilityUnitType.DESTROY_SELF:
            config = DestroySelfAbility(**config_data)
        elif unit_type == AbilityUnitType.RESTORE_HEALTH:
            config = RestoreHealthAbility(**config_data)
        else:
            config = config_data
        
        return AbilityUnitConfig(unit_type=unit_type, config=config)


if __name__ == "__main__":
    print("=== 能力单元配置测试 ===\n")
    
    # 测试攻击盒攻击能力
    print("1. 攻击盒攻击能力：")
    attack_box = AttackBoxAttackAbility(
        ability_name="横扫攻击",
        attack_box=AttackBoxConfig(
            shape=AttackBoxShape.CUBOID,
            scale=(3.0, 1.0, 2.0)
        ),
        attack_parameters=AttackParametersConfig(
            damage_coefficient=1.5,
            element_type=ElementType.FIRE
        )
    )
    print(f"   能力名称：{attack_box.ability_name}")
    print(f"   攻击盒形状：{attack_box.attack_box.shape.value}")
    print(f"   伤害系数：{attack_box.attack_parameters.damage_coefficient}")
    
    print("\n[OK] 能力单元配置测试完成")

