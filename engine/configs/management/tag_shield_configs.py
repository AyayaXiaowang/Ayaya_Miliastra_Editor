"""
标签与护盾配置模块
包含单位标签、护盾和扫描标签管理配置
"""

from dataclasses import dataclass, field
from typing import List


# ============================================================================
# 单位标签管理配置
# ============================================================================

@dataclass
class UnitTagConfig:
    """单位标签配置"""
    tag_id: str
    tag_name: str
    tag_category: str = "general"  # general/combat/quest/special
    color: str = "#FFFFFF"
    icon: str = ""
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "tag_id": self.tag_id,
            "tag_name": self.tag_name,
            "tag_category": self.tag_category,
            "color": self.color,
            "icon": self.icon,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'UnitTagConfig':
        return UnitTagConfig(
            tag_id=data["tag_id"],
            tag_name=data["tag_name"],
            tag_category=data.get("tag_category", "general"),
            color=data.get("color", "#FFFFFF"),
            icon=data.get("icon", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 护盾管理配置
# ============================================================================

@dataclass
class ShieldConfig:
    """护盾配置 - 按官方文档"""
    shield_id: str  # 配置ID（唯一标识）
    shield_name: str  # 护盾名称
    
    # 核心配置
    absorbable_damage_types: List[str] = field(default_factory=list)  # 可吸收伤害类型（空=全部）
    remove_when_depleted: bool = True  # 护盾值耗尽时移除
    show_ui: bool = True  # 显示UI（护盾条）
    ui_color: str = "#00FFFF"  # UI颜色
    damage_ratio: float = 1.0  # 承伤比例（受到伤害时应用至该护盾的比例）
    shield_value: float = 100.0  # 护盾值（每层单位状态提供的护盾值）
    
    # 高级配置
    ignore_shield_amplification: bool = False  # 忽略护盾强效
    infinite_absorption: bool = False  # 无限吸收（每次只扣1点护盾值）
    absorption_ratio: float = 1.0  # 吸收比例（每1点护盾值可吸收的伤害值）
    settlement_priority: int = 0  # 结算优先级（多护盾时的优先级）
    layer_based_effect: bool = False  # 按层生效（多层时只取最早一层）
    nullify_overflow_damage: bool = False  # 吸收溢出时伤害归零
    attack_tags: List[str] = field(default_factory=list)  # 攻击标签（空=全部生效）
    
    # 描述与兼容
    description: str = ""
    
    # 兼容旧字段
    shield_type: str = "absorb"
    duration: float = 0.0
    absorb_types: List[str] = field(default_factory=list)
    visual_effect: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "shield_id": self.shield_id,
            "shield_name": self.shield_name,
            "absorbable_damage_types": self.absorbable_damage_types,
            "remove_when_depleted": self.remove_when_depleted,
            "show_ui": self.show_ui,
            "ui_color": self.ui_color,
            "damage_ratio": self.damage_ratio,
            "shield_value": self.shield_value,
            "ignore_shield_amplification": self.ignore_shield_amplification,
            "infinite_absorption": self.infinite_absorption,
            "absorption_ratio": self.absorption_ratio,
            "settlement_priority": self.settlement_priority,
            "layer_based_effect": self.layer_based_effect,
            "nullify_overflow_damage": self.nullify_overflow_damage,
            "attack_tags": self.attack_tags,
            "description": self.description,
            # 兼容旧字段
            "shield_type": self.shield_type,
            "duration": self.duration,
            "absorb_types": self.absorb_types,
            "visual_effect": self.visual_effect,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'ShieldConfig':
        return ShieldConfig(
            shield_id=data["shield_id"],
            shield_name=data["shield_name"],
            absorbable_damage_types=data.get("absorbable_damage_types", data.get("absorb_types", [])),
            remove_when_depleted=data.get("remove_when_depleted", True),
            show_ui=data.get("show_ui", True),
            ui_color=data.get("ui_color", "#00FFFF"),
            damage_ratio=data.get("damage_ratio", 1.0),
            shield_value=data.get("shield_value", 100.0),
            ignore_shield_amplification=data.get("ignore_shield_amplification", False),
            infinite_absorption=data.get("infinite_absorption", False),
            absorption_ratio=data.get("absorption_ratio", 1.0),
            settlement_priority=data.get("settlement_priority", 0),
            layer_based_effect=data.get("layer_based_effect", False),
            nullify_overflow_damage=data.get("nullify_overflow_damage", False),
            attack_tags=data.get("attack_tags", []),
            description=data.get("description", ""),
            # 兼容
            shield_type=data.get("shield_type", "absorb"),
            duration=data.get("duration", 0.0),
            absorb_types=data.get("absorb_types", []),
            visual_effect=data.get("visual_effect", ""),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 扫描标签管理配置
# ============================================================================

@dataclass
class ScanTagConfig:
    """扫描标签配置"""
    scan_tag_id: str
    scan_tag_name: str
    scannable: bool = True  # 是否可被扫描
    scan_range: float = 10.0  # 扫描范围
    scan_highlight_color: str = "#00FF00"
    scan_info_text: str = ""  # 扫描后显示的信息
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "scan_tag_id": self.scan_tag_id,
            "scan_tag_name": self.scan_tag_name,
            "scannable": self.scannable,
            "scan_range": self.scan_range,
            "scan_highlight_color": self.scan_highlight_color,
            "scan_info_text": self.scan_info_text,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'ScanTagConfig':
        return ScanTagConfig(
            scan_tag_id=data["scan_tag_id"],
            scan_tag_name=data["scan_tag_name"],
            scannable=data.get("scannable", True),
            scan_range=data.get("scan_range", 10.0),
            scan_highlight_color=data.get("scan_highlight_color", "#00FF00"),
            scan_info_text=data.get("scan_info_text", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 标签与护盾配置测试 ===\n")
    
    # 测试单位标签
    print("1. 单位标签配置:")
    tag = UnitTagConfig(
        tag_id="tag_001",
        tag_name="boss",
        tag_category="combat",
        color="#FF0000"
    )
    print(f"   标签名: {tag.tag_name}")
    print(f"   分类: {tag.tag_category}")
    print(f"   颜色: {tag.color}")
    
    # 测试护盾配置
    print("\n2. 护盾配置:")
    shield = ShieldConfig(
        shield_id="shield_001",
        shield_name="魔法护盾",
        shield_value=200.0,
        absorbable_damage_types=["magic", "elemental"],
        show_ui=True,
        ui_color="#00FFFF"
    )
    print(f"   护盾名: {shield.shield_name}")
    print(f"   护盾值: {shield.shield_value}")
    print(f"   可吸收伤害类型: {shield.absorbable_damage_types}")
    
    # 测试扫描标签
    print("\n3. 扫描标签配置:")
    scan_tag = ScanTagConfig(
        scan_tag_id="scan_001",
        scan_tag_name="可交互物体",
        scannable=True,
        scan_range=15.0,
        scan_info_text="按E交互"
    )
    print(f"   扫描标签名: {scan_tag.scan_tag_name}")
    print(f"   扫描范围: {scan_tag.scan_range}米")
    print(f"   信息文本: {scan_tag.scan_info_text}")
    
    print("\n✅ 标签与护盾配置测试完成")

