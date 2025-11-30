"""
战斗设置与战斗特效配置
基于知识库：战斗设置.md
"""
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum


# ============================================================================
# 战斗设置 (战斗设置.md)
# ============================================================================

class EffectAssetType(str, Enum):
    """特效资产类型"""
    TIMED = "限时特效"
    LOOP = "循环特效"


@dataclass
class CombatEffectConfig:
    """战斗特效配置（用于战斗设置，定义受击特效和击倒特效）"""
    effect_asset_type: EffectAssetType = EffectAssetType.TIMED
    effect_asset: str = ""  # 特效资产ID
    scale: float = 1.0  # 缩放比例
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 位置偏移
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 旋转
    
    doc_reference: str = "战斗设置.md:15-21"


@dataclass
class CombatSettingsConfig:
    """战斗设置配置"""
    cannot_be_element_attached: bool = False  # 不可被元素附着
    cannot_be_target_locked: bool = False  # 不可被目标锁定
    hit_effect: Optional[CombatEffectConfig] = None  # 受击特效
    knockdown_effect: Optional[CombatEffectConfig] = None  # 被击倒特效
    
    doc_reference: str = "战斗设置.md:1-13"
    
    def serialize(self) -> dict:
        return {
            "cannot_be_element_attached": self.cannot_be_element_attached,
            "cannot_be_target_locked": self.cannot_be_target_locked,
            "hit_effect": {
                "effect_asset_type": self.hit_effect.effect_asset_type.value,
                "effect_asset": self.hit_effect.effect_asset,
                "scale": self.hit_effect.scale,
                "offset": self.hit_effect.offset,
                "rotation": self.hit_effect.rotation
            } if self.hit_effect else None,
            "knockdown_effect": {
                "effect_asset_type": self.knockdown_effect.effect_asset_type.value,
                "effect_asset": self.knockdown_effect.effect_asset,
                "scale": self.knockdown_effect.scale,
                "offset": self.knockdown_effect.offset,
                "rotation": self.knockdown_effect.rotation
            } if self.knockdown_effect else None
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'CombatSettingsConfig':
        hit_effect = None
        if data.get("hit_effect"):
            he = data["hit_effect"]
            hit_effect = CombatEffectConfig(
                effect_asset_type=EffectAssetType(he.get("effect_asset_type", "限时特效")),
                effect_asset=he.get("effect_asset", ""),
                scale=he.get("scale", 1.0),
                offset=tuple(he.get("offset", [0.0, 0.0, 0.0])),
                rotation=tuple(he.get("rotation", [0.0, 0.0, 0.0]))
            )
        
        knockdown_effect = None
        if data.get("knockdown_effect"):
            ke = data["knockdown_effect"]
            knockdown_effect = CombatEffectConfig(
                effect_asset_type=EffectAssetType(ke.get("effect_asset_type", "限时特效")),
                effect_asset=ke.get("effect_asset", ""),
                scale=ke.get("scale", 1.0),
                offset=tuple(ke.get("offset", [0.0, 0.0, 0.0])),
                rotation=tuple(ke.get("rotation", [0.0, 0.0, 0.0]))
            )
        
        return CombatSettingsConfig(
            cannot_be_element_attached=data.get("cannot_be_element_attached", False),
            cannot_be_target_locked=data.get("cannot_be_target_locked", False),
            hit_effect=hit_effect,
            knockdown_effect=knockdown_effect
        )


if __name__ == "__main__":
    print("=== 战斗设置配置测试 ===\n")
    
    # 测试战斗设置
    print("1. 战斗设置：")
    combat_settings = CombatSettingsConfig(
        cannot_be_element_attached=True,
        hit_effect=CombatEffectConfig(
            effect_asset_type=EffectAssetType.TIMED,
            effect_asset="hit_effect_001",
            scale=1.5
        )
    )
    print(f"   不可被元素附着：{combat_settings.cannot_be_element_attached}")
    print(f"   受击特效：{combat_settings.hit_effect.effect_asset if combat_settings.hit_effect else '无'}")
    
    print("\n[OK] 战斗设置配置测试完成")

