"""
造物信息配置（技能、行为模式、单位状态效果）。
从 `extended_configs.py` 聚合文件中拆分而来，现作为专门模块使用。
"""
from dataclasses import dataclass


# ============================================================================
# 单位状态效果与造物相关
# ============================================================================

@dataclass
class UnitStateEffect:
    """
    单位状态效果
    参考：单位状态效果池.md
    
    定义各种单位状态效果及其影响
    """
    effect_name: str = ""
    effect_type: str = ""  # 变更量、调整率、倍率、修正值
    description: str = ""
    
    # 效果参数
    effect_value: float = 0.0
    
    doc_reference: str = "单位状态效果池.md"


@dataclass
class CreatureSkillInfo:
    """
    造物技能信息
    参考：造物技能说明.md
    """
    creature_name: str = ""
    skill_name: str = ""
    skill_description: str = ""
    
    doc_reference: str = "造物技能说明.md"


@dataclass
class CreatureBehaviorMode:
    """
    造物行为模式
    参考：造物行为模式图鉴.md, 造物行为模式的未入战行为.md
    """
    creature_name: str = ""
    behavior_mode: str = "常规"  # 常规、仅追击、仅地面等
    mode_description: str = ""
    
    # 未入战行为
    non_combat_behavior: str = "站立"  # 站立、游荡、坐着、睡觉、跳舞、躲藏、钻地、浮空
    
    doc_reference: str = "造物行为模式图鉴.md, 造物行为模式的未入战行为.md"

