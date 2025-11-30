"""
战斗设置和能力单元配置
基于知识库：战斗设置.md 和 能力单元.md
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


# ============================================================================
# 战斗设置 (战斗设置.md)
# ============================================================================

class EffectAssetType(str, Enum):
    """特效资产类型"""
    LOOP_EFFECT = "循环特效"
    TIMED_EFFECT = "限时特效"


@dataclass
class EffectConfig:
    """特效配置"""
    effect_asset_type: EffectAssetType
    effect_asset_id: int
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "战斗设置.md:15-21"


@dataclass
class CombatSettingsConfig:
    """
    战斗设置配置
    参考：战斗设置.md:1-21
    """
    # 基础设置
    cannot_be_element_attached: bool = False  # 不可被元素附着
    cannot_be_target_locked: bool = False  # 不可被目标锁定
    
    # 特效设置
    hit_effect: Optional[EffectConfig] = None  # 受击特效
    knockdown_effect: Optional[EffectConfig] = None  # 被击倒特效
    
    doc_reference: str = "战斗设置.md:7-12"
    notes: str = "提供自定义战斗玩法设计更详细的配置"


# ============================================================================
# 能力单元 (能力单元.md)
# ============================================================================

class AbilityUnitType(str, Enum):
    """能力单元类型"""
    ATTACK_BOX_ATTACK = "攻击盒攻击"  # 以目标/位置为基准，发起攻击盒攻击
    DIRECT_ATTACK = "直接攻击"  # 对指定目标发起直接攻击
    PLAY_EFFECT = "播放特效"  # 播放一次性特效
    CREATE_PROJECTILE = "创建本地投射物"  # 创生本地投射物
    ADD_UNIT_STATE = "添加单位状态"  # 添加单位状态
    REMOVE_UNIT_STATE = "移除单位状态"  # 移除单位状态
    DESTROY_SELF = "销毁自身"  # 销毁自身
    RESTORE_HEALTH = "恢复生命"  # 恢复生命


class AbilityInvokeType(str, Enum):
    """能力单元调用类型"""
    SERVER_NODE_GRAPH = "服务端节点图直接调用"
    HIT_DETECTION_COMPONENT = "命中检测组件的命中时事件调用"
    PROJECTILE_HIT = "本地投射物的命中时事件调用"
    PROJECTILE_DESTROY = "本地投射物的销毁时事件调用"


# 能力单元类型与调用类型的兼容性矩阵 (能力单元.md:22-27)
ABILITY_INVOKE_COMPATIBILITY = {
    AbilityInvokeType.SERVER_NODE_GRAPH: [
        AbilityUnitType.ATTACK_BOX_ATTACK,
        AbilityUnitType.DIRECT_ATTACK,
        AbilityUnitType.RESTORE_HEALTH
    ],
    AbilityInvokeType.HIT_DETECTION_COMPONENT: [
        AbilityUnitType.ATTACK_BOX_ATTACK,
        AbilityUnitType.DIRECT_ATTACK,
        AbilityUnitType.RESTORE_HEALTH
    ],
    AbilityInvokeType.PROJECTILE_HIT: [
        AbilityUnitType.ATTACK_BOX_ATTACK,
        AbilityUnitType.DIRECT_ATTACK,
        AbilityUnitType.PLAY_EFFECT,
        AbilityUnitType.CREATE_PROJECTILE,
        AbilityUnitType.ADD_UNIT_STATE,
        AbilityUnitType.REMOVE_UNIT_STATE,
        AbilityUnitType.DESTROY_SELF,
        AbilityUnitType.RESTORE_HEALTH
    ],
    AbilityInvokeType.PROJECTILE_DESTROY: [
        AbilityUnitType.ATTACK_BOX_ATTACK,
        AbilityUnitType.DIRECT_ATTACK,
        AbilityUnitType.PLAY_EFFECT,
        AbilityUnitType.CREATE_PROJECTILE
    ]
}


@dataclass
class AttackBoxAbilityConfig:
    """攻击盒攻击能力配置"""
    attack_box_shape: str  # 攻击盒形状
    attack_box_size: Tuple[float, float, float]  # 攻击盒尺寸
    mount_point: str  # 挂接点
    damage_coefficient: float = 1.0  # 伤害系数
    damage_increment: float = 0.0  # 伤害增量
    position_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "能力单元.md:9"


@dataclass
class DirectAttackAbilityConfig:
    """直接攻击能力配置"""
    damage_coefficient: float = 1.0
    damage_increment: float = 0.0
    position_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "能力单元.md:10"


@dataclass
class PlayEffectAbilityConfig:
    """播放特效能力配置"""
    effect_asset_id: int
    position_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    
    doc_reference: str = "能力单元.md:11"


@dataclass
class CreateProjectileAbilityConfig:
    """创建本地投射物能力配置"""
    projectile_template_id: int
    spawn_point: str  # 挂接点
    position_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "能力单元.md:12"


@dataclass
class AddUnitStateAbilityConfig:
    """添加单位状态能力配置"""
    unit_state_id: int
    duration: float = -1.0  # -1表示永久
    stack_count: int = 1
    
    doc_reference: str = "能力单元.md:13"


@dataclass
class RemoveUnitStateAbilityConfig:
    """移除单位状态能力配置"""
    unit_state_id: int
    remove_all_stacks: bool = True
    
    doc_reference: str = "能力单元.md:14"


@dataclass
class RestoreHealthAbilityConfig:
    """恢复生命能力配置"""
    restore_amount: float  # 恢复量
    restore_coefficient: float = 1.0  # 恢复系数
    
    doc_reference: str = "能力单元.md:16, 66-76"


@dataclass
class AbilityUnitDefinition:
    """
    能力单元定义
    参考：能力单元.md:1-17
    """
    ability_name: str
    ability_type: AbilityUnitType
    
    # 根据类型选择对应的配置
    attack_box_config: Optional[AttackBoxAbilityConfig] = None
    direct_attack_config: Optional[DirectAttackAbilityConfig] = None
    play_effect_config: Optional[PlayEffectAbilityConfig] = None
    create_projectile_config: Optional[CreateProjectileAbilityConfig] = None
    add_unit_state_config: Optional[AddUnitStateAbilityConfig] = None
    remove_unit_state_config: Optional[RemoveUnitStateAbilityConfig] = None
    restore_health_config: Optional[RestoreHealthAbilityConfig] = None
    
    doc_reference: str = "能力单元.md:5-17"
    notes: str = "能力单元是纯数据，需要其他系统调用"


@dataclass
class AbilityInvokeConfig:
    """能力单元调用配置"""
    invoke_type: AbilityInvokeType
    ability_name: str  # 引用的能力单元名称
    
    # 节点图调用特定参数 (能力单元.md:48-65)
    override_config: bool = False  # 是否覆写能力单元配置
    custom_damage_coefficient: Optional[float] = None
    custom_damage_increment: Optional[float] = None
    custom_position_offset: Optional[Tuple[float, float, float]] = None
    custom_rotation_offset: Optional[Tuple[float, float, float]] = None
    custom_attacker: Optional[int] = None  # 攻击发起者实体ID
    
    doc_reference: str = "能力单元.md:46-77"


# ============================================================================
# 验证函数
# ============================================================================

def validate_ability_invoke_compatibility(
    ability_type: AbilityUnitType,
    invoke_type: AbilityInvokeType
) -> List[str]:
    """验证能力单元调用兼容性"""
    errors = []
    
    allowed_abilities = ABILITY_INVOKE_COMPATIBILITY.get(invoke_type, [])
    if ability_type not in allowed_abilities:
        errors.append(
            f"[能力单元调用错误] 调用类型'{invoke_type.value}'不支持能力单元'{ability_type.value}'\n"
            f"该调用类型支持的能力单元：{[a.value for a in allowed_abilities]}\n"
            f"参考：能力单元.md:22-27"
        )
    
    return errors


def validate_ability_config_complete(ability: AbilityUnitDefinition) -> List[str]:
    """验证能力单元配置完整性"""
    errors = []
    
    # 检查对应类型的配置是否存在
    config_map = {
        AbilityUnitType.ATTACK_BOX_ATTACK: ability.attack_box_config,
        AbilityUnitType.DIRECT_ATTACK: ability.direct_attack_config,
        AbilityUnitType.PLAY_EFFECT: ability.play_effect_config,
        AbilityUnitType.CREATE_PROJECTILE: ability.create_projectile_config,
        AbilityUnitType.ADD_UNIT_STATE: ability.add_unit_state_config,
        AbilityUnitType.REMOVE_UNIT_STATE: ability.remove_unit_state_config,
        AbilityUnitType.RESTORE_HEALTH: ability.restore_health_config,
    }
    
    required_config = config_map.get(ability.ability_type)
    if required_config is None:
        errors.append(
            f"[能力单元配置错误] 能力单元'{ability.ability_name}'类型为'{ability.ability_type.value}'但缺少对应配置"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 战斗与能力单元配置测试 ===\n")
    
    # 测试战斗设置
    print("1. 战斗设置：")
    combat_settings = CombatSettingsConfig(
        cannot_be_element_attached=True,
        hit_effect=EffectConfig(
            effect_asset_type=EffectAssetType.TIMED_EFFECT,
            effect_asset_id=1001,
            scale=(1.5, 1.5, 1.5)
        )
    )
    print(f"   不可被元素附着：{combat_settings.cannot_be_element_attached}")
    print(f"   受击特效：{combat_settings.hit_effect.effect_asset_id if combat_settings.hit_effect else '无'}")
    
    # 测试能力单元
    print("\n2. 攻击盒攻击能力：")
    attack_box = AbilityUnitDefinition(
        ability_name="横扫攻击",
        ability_type=AbilityUnitType.ATTACK_BOX_ATTACK,
        attack_box_config=AttackBoxAbilityConfig(
            attack_box_shape="长方体",
            attack_box_size=(3.0, 1.0, 2.0),
            mount_point="weapon_point",
            damage_coefficient=1.5
        )
    )
    print(f"   能力名称：{attack_box.ability_name}")
    print(f"   类型：{attack_box.ability_type.value}")
    if attack_box.attack_box_config:
        print(f"   攻击盒尺寸：{attack_box.attack_box_config.attack_box_size}")
    
    # 测试调用兼容性
    print("\n3. 调用兼容性验证：")
    errors = validate_ability_invoke_compatibility(
        AbilityUnitType.PLAY_EFFECT,
        AbilityInvokeType.SERVER_NODE_GRAPH
    )
    if errors:
        for err in errors:
            print(f"   {err}")
    else:
        print("   验证通过")
    
    # 测试配置完整性
    print("\n4. 配置完整性验证：")
    incomplete_ability = AbilityUnitDefinition(
        ability_name="测试攻击",
        ability_type=AbilityUnitType.DIRECT_ATTACK,
        # 缺少 direct_attack_config
    )
    errors = validate_ability_config_complete(incomplete_ability)
    if errors:
        for err in errors:
            print(f"   {err}")
    
    print("\n✅ 战斗与能力单元配置测试完成")

