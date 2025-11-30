"""
特化配置系统
基于知识库文档实现
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


# ============================================================================
# 基础战斗属性配置 (基础战斗属性.md)
# ============================================================================

class AttributeGrowthMode(str, Enum):
    """属性成长模式"""
    NO_GROWTH = "无成长"  # 基础属性不随等级变化
    PRESET_GROWTH = "预制成长"  # 使用预制成长曲线
    CUSTOM_GROWTH = "自定义成长曲线"  # 自定义成长曲线


@dataclass
class CombatAttributesConfig:
    """
    基础战斗属性配置 - 物件专用
    参考：基础战斗属性.md:3-7
    """
    level: int = 1  # 默认等级
    base_health: float = 100.0  # 基础生命值
    base_attack: float = 10.0  # 基础攻击力
    base_defense: float = 5.0  # 基础防御力
    
    doc_reference: str = "基础战斗属性.md:3-7"
    notes: str = "生命值为0时实体被击倒，触发销毁和移除事件"


@dataclass
class CreatureCombatAttributesConfig:
    """
    造物基础战斗属性配置 - 造物专用（有成长曲线）
    参考：基础战斗属性.md:9-28
    """
    level: int = 1
    base_health: float = 100.0
    base_attack: float = 10.0
    
    # 成长配置
    growth_mode: AttributeGrowthMode = AttributeGrowthMode.NO_GROWTH
    custom_growth_curve: Dict[int, Dict[str, float]] = field(default_factory=dict)
    # 格式：{level: {"health_multiplier": float, "attack_multiplier": float}}
    
    doc_reference: str = "基础战斗属性.md:15-27"
    calculation_formula: str = (
        "实际生命值 = 当前等级对应行的生命值倍率 * 基础生命值\n"
        "实际攻击力 = 当前等级对应行的攻击力倍率 * 基础攻击力"
    )


# ============================================================================
# 仇恨配置 (仇恨配置.md)
# ============================================================================

class AggroMode(str, Enum):
    """仇恨模式"""
    DEFAULT = "默认仇恨模式"  # 与经典模式一致
    CUSTOM = "自定义仇恨模式"  # 自定义仇恨规则


@dataclass
class AggroGlobalConfig:
    """
    全局仇恨配置
    参考：仇恨配置.md:106-109
    """
    aggro_mode: AggroMode = AggroMode.DEFAULT
    transfer_multiplier: float = 1.2  # 仇恨转移倍率（不能<=0）
    
    doc_reference: str = "仇恨配置.md:108-109"
    notes: str = "默认1.2，即超过当前仇恨目标1.2倍仇恨值时发生转移"


@dataclass
class ObjectAggroConfig:
    """
    物件仇恨配置
    参考：仇恨配置.md:113-116
    """
    aggro_multiplier: float = 1.0  # 产生仇恨的倍率
    enable_aggro_record: bool = False  # 是否开启仇恨记录（成为仇恨拥有者）
    sync_aggro_value: bool = False  # 是否同步仇恨值到客户端
    
    doc_reference: str = "仇恨配置.md:113-116"
    notes: str = "开启仇恨记录后，物件成为仇恨拥有者；同步仇恨值用于界面显示"


@dataclass
class ProfessionAggroConfig:
    """
    职业仇恨配置
    参考：仇恨配置.md:118-119
    """
    aggro_multiplier: float = 1.0  # 产生仇恨的倍率
    
    doc_reference: str = "仇恨配置.md:118-119"
    notes: str = "拥有该职业的角色通过攻击和治疗产生仇恨的倍率"


@dataclass
class CreatureAggroConfig:
    """
    造物仇恨配置
    参考：仇恨配置.md:121-124
    """
    aggro_multiplier: float = 1.0  # 产生仇恨的倍率
    sync_aggro_value: bool = False  # 是否同步仇恨值到客户端
    
    doc_reference: str = "仇恨配置.md:121-123"
    notes: str = "造物默认是仇恨拥有者；仇恨值在服务端计算，客户端取值不准确"


@dataclass
class AggroCalculation:
    """
    仇恨值计算规则
    参考：仇恨配置.md:39-46
    """
    damage_aggro_formula: str = (
        "产生的仇恨值 = (实际造成的伤害 × 本次攻击的仇恨倍率 + "
        "本次攻击的仇恨增量) × 实体/职业仇恨倍率"
    )
    heal_aggro_formula: str = (
        "产生的仇恨值 = (实际造成的恢复量 × 本次恢复的仇恨倍率 + "
        "本次恢复的仇恨增量) × 实体/职业仇恨倍率"
    )
    view_detection_aggro: int = 1  # 视野检测入战产生1点仇恨
    taunt_aggro: str = "嘲讽值 = 当前仇恨目标仇恨值 × 仇恨转移倍率"
    
    doc_reference: str = "仇恨配置.md:39-77"


# ============================================================================
# 受击盒设置（需要读取对应文档）
# ============================================================================

@dataclass
class HitboxConfig:
    """受击盒配置（占位）"""
    enabled: bool = True
    custom_hitbox_shape: Optional[str] = None
    doc_reference: str = "受击盒设置.md"


# ============================================================================
# 常规设置（需要读取对应文档）
# ============================================================================

@dataclass
class GeneralSettingsConfig:
    """常规设置配置（占位）"""
    doc_reference: str = "常规设置.md"


# ============================================================================
# 战斗设置（需要读取对应文档）
# ============================================================================

@dataclass
class CombatSettingsConfig:
    """战斗设置配置（占位）"""
    doc_reference: str = "战斗设置.md"


# ============================================================================
# 能力单元（需要读取对应文档）
# ============================================================================

@dataclass
class AbilityUnitConfig:
    """能力单元配置（占位）"""
    doc_reference: str = "能力单元.md"


# ============================================================================
# 验证函数
# ============================================================================

def validate_combat_attributes(entity_type: str, config: Any) -> List[str]:
    """验证战斗属性配置"""
    errors = []
    
    # 物件和造物才有战斗属性
    if entity_type not in ["物件-动态", "造物"]:
        errors.append(
            f"[战斗属性错误] 实体类型'{entity_type}'不支持战斗属性配置\n"
            "仅物件和造物支持战斗属性\n"
            "参考：基础战斗属性.md"
        )
        return errors
    
    # 造物专属成长曲线检查
    if entity_type == "造物":
        if not isinstance(config, CreatureCombatAttributesConfig):
            errors.append(
                "[战斗属性错误] 造物应使用CreatureCombatAttributesConfig\n"
                "参考：基础战斗属性.md:9-10 '造物可额外配置成长曲线'"
            )
    elif entity_type == "物件-动态":
        if not isinstance(config, CombatAttributesConfig):
            errors.append(
                "[战斗属性错误] 物件应使用CombatAttributesConfig\n"
                "参考：基础战斗属性.md:3-7"
            )
    
    return errors


def validate_aggro_config(entity_type: str, aggro_enabled: bool) -> List[str]:
    """验证仇恨配置"""
    errors = []
    
    # 角色无法成为仇恨拥有者 (仇恨配置.md:30)
    if entity_type == "角色" and aggro_enabled:
        errors.append(
            "[仇恨配置错误] 角色无法成为仇恨拥有者\n"
            "仇恨拥有者：造物默认是，物件可选，角色不能\n"
            "参考：仇恨配置.md:28-30"
        )
    
    return errors


def validate_aggro_mode_compatibility(
    aggro_mode: AggroMode, 
    using_custom_features: bool
) -> List[str]:
    """验证仇恨模式兼容性"""
    errors = []
    
    # 默认模式下不能使用自定义功能 (仇恨配置.md:19)
    if aggro_mode == AggroMode.DEFAULT and using_custom_features:
        errors.append(
            "[仇恨模式错误] 默认仇恨模式下无法使用自定义仇恨功能\n"
            "两个模式的功能是完全隔离的\n"
            "参考：仇恨配置.md:19 '功能是完全隔离的'"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 特化配置系统测试 ===\n")
    
    # 测试战斗属性
    print("1. 造物战斗属性：")
    creature_attr = CreatureCombatAttributesConfig(
        level=10,
        base_health=200.0,
        base_attack=25.0,
        growth_mode=AttributeGrowthMode.PRESET_GROWTH
    )
    print(f"   等级：{creature_attr.level}")
    print(f"   成长模式：{creature_attr.growth_mode.value}")
    print(f"   计算公式：\n   {creature_attr.calculation_formula}")
    
    # 测试仇恨配置
    print("\n2. 全局仇恨配置：")
    global_aggro = AggroGlobalConfig(
        aggro_mode=AggroMode.CUSTOM,
        transfer_multiplier=1.3
    )
    print(f"   仇恨模式：{global_aggro.aggro_mode.value}")
    print(f"   转移倍率：{global_aggro.transfer_multiplier}")
    
    # 测试验证
    print("\n3. 角色仇恨配置验证：")
    errors = validate_aggro_config("角色", aggro_enabled=True)
    if errors:
        for err in errors:
            print(f"   {err}")
    
    print("\n✅ 特化配置系统测试完成")
