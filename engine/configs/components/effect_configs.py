"""
组件配置 - 特效播放
基于知识库文档定义的特效播放组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class EffectAssetType(Enum):
    """特效资产类型（特效播放.md 第24行）"""
    LOOP = "循环特效"
    TIMED = "限时特效"


@dataclass
class EffectPlayDefinition:
    """
    单个特效播放配置
    来源：特效播放.md (第18-31行)
    """
    # 特效播放器序号
    player_index: int
    # 特效播放器名称（同一实体上不可重复）
    player_name: str
    # 特效资产类型
    asset_type: EffectAssetType = EffectAssetType.LOOP
    # 特效资产
    asset: str = ""
    # 跟随位置
    follow_position: bool = True
    # 跟随旋转（仅当跟随位置为是时生效）
    follow_rotation: bool = True
    # 挂接点
    attach_point: str = ""
    # 缩放比例
    scale: float = 1.0
    # 偏移
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "特效播放器序号": self.player_index,
            "特效播放器名称": self.player_name,
            "特效资产类型": self.asset_type.value,
            "特效资产": self.asset,
            "跟随位置": self.follow_position,
            "跟随旋转": self.follow_rotation,
            "挂接点": self.attach_point,
            "缩放比例": self.scale,
            "偏移": self.offset,
            "旋转": self.rotation
        }


@dataclass
class EffectPlayConfig:
    """
    特效播放组件配置
    来源：特效播放.md (第1-31行)
    注意：特效播放组件是所有单位的默认挂载组件（第12行）
    """
    # 特效播放器列表
    effect_players: List[EffectPlayDefinition] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "特效播放器": [player.to_dict() for player in self.effect_players]
        }

