"""
战斗预设数据模型
基于内部战斗预设设计文档整理的数据结构
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ============================================================================
# 玩家模板与职业配置
# ============================================================================

@dataclass
class PlayerTemplateConfig:
    """玩家模板配置（战斗预设中的玩家基线设定，与职业解耦）"""
    template_id: str
    template_name: str
    description: str = ""
    level: int = 1
    default_profession_id: str = ""
    metadata: dict = field(default_factory=dict)

    doc_reference: str = "战斗预设.md:2"

    def serialize(self) -> dict:
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "description": self.description,
            "level": self.level,
            "default_profession_id": self.default_profession_id,
            "metadata": self.metadata,
        }

    @staticmethod
    def deserialize(data: dict) -> "PlayerTemplateConfig":
        return PlayerTemplateConfig(
            template_id=data["template_id"],
            template_name=data["template_name"],
            description=data.get("description", ""),
            level=data.get("level", 1),
            default_profession_id=data.get("default_profession_id", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PlayerClassConfig:
    """玩家职业配置（职业定义，与玩家模板分离）"""
    class_id: str
    class_name: str
    description: str = ""
    base_health: float = 100.0
    base_attack: float = 10.0
    base_defense: float = 5.0
    base_speed: float = 5.0
    skill_list: List[str] = field(default_factory=list)  # 技能ID列表
    metadata: dict = field(default_factory=dict)
    
    doc_reference: str = "战斗预设.md:3-7"
    
    def serialize(self) -> dict:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "description": self.description,
            "base_health": self.base_health,
            "base_attack": self.base_attack,
            "base_defense": self.base_defense,
            "base_speed": self.base_speed,
            "skill_list": self.skill_list,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'PlayerClassConfig':
        return PlayerClassConfig(
            class_id=data["class_id"],
            class_name=data["class_name"],
            description=data.get("description", ""),
            base_health=data.get("base_health", 100.0),
            base_attack=data.get("base_attack", 10.0),
            base_defense=data.get("base_defense", 5.0),
            base_speed=data.get("base_speed", 5.0),
            skill_list=data.get("skill_list", []),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 单位状态配置
# ============================================================================

@dataclass
class UnitStatusConfig:
    """单位状态配置"""
    status_id: str
    status_name: str
    description: str = ""
    duration: float = 0.0  # 持续时间（秒），0表示永久
    is_stackable: bool = False  # 是否可堆叠
    max_stacks: int = 1  # 最大堆叠层数
    effect_type: str = "buff"  # buff/debuff/特殊
    effect_values: Dict[str, float] = field(default_factory=dict)  # 效果数值
    icon: str = ""
    metadata: dict = field(default_factory=dict)
    
    doc_reference: str = "战斗预设.md:4"
    
    def serialize(self) -> dict:
        return {
            "status_id": self.status_id,
            "status_name": self.status_name,
            "description": self.description,
            "duration": self.duration,
            "is_stackable": self.is_stackable,
            "max_stacks": self.max_stacks,
            "effect_type": self.effect_type,
            "effect_values": self.effect_values,
            "icon": self.icon,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'UnitStatusConfig':
        return UnitStatusConfig(
            status_id=data["status_id"],
            status_name=data["status_name"],
            description=data.get("description", ""),
            duration=data.get("duration", 0.0),
            is_stackable=data.get("is_stackable", False),
            max_stacks=data.get("max_stacks", 1),
            effect_type=data.get("effect_type", "buff"),
            effect_values=data.get("effect_values", {}),
            icon=data.get("icon", ""),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 技能配置（增强）
# ============================================================================

@dataclass
class SkillConfig:
    """技能配置"""
    skill_id: str
    skill_name: str
    description: str = ""
    cooldown: float = 5.0  # 冷却时间（秒）
    cost_type: str = "mana"  # 消耗类型：mana/stamina/health/none
    cost_value: float = 10.0  # 消耗值
    damage: float = 20.0  # 伤害
    damage_type: str = "physical"  # physical/magical
    range_value: float = 5.0  # 范围
    cast_time: float = 0.0  # 施法时间（秒）
    animation: str = ""  # 动画资源
    effects: List[str] = field(default_factory=list)  # 特效列表
    ability_units: List[str] = field(default_factory=list)  # 能力单元列表
    metadata: dict = field(default_factory=dict)
    
    doc_reference: str = "战斗预设.md:5"
    
    def serialize(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "description": self.description,
            "cooldown": self.cooldown,
            "cost_type": self.cost_type,
            "cost_value": self.cost_value,
            "damage": self.damage,
            "damage_type": self.damage_type,
            "range_value": self.range_value,
            "cast_time": self.cast_time,
            "animation": self.animation,
            "effects": self.effects,
            "ability_units": self.ability_units,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'SkillConfig':
        return SkillConfig(
            skill_id=data["skill_id"],
            skill_name=data["skill_name"],
            description=data.get("description", ""),
            cooldown=data.get("cooldown", 5.0),
            cost_type=data.get("cost_type", "mana"),
            cost_value=data.get("cost_value", 10.0),
            damage=data.get("damage", 20.0),
            damage_type=data.get("damage_type", "physical"),
            range_value=data.get("range_value", 5.0),
            cast_time=data.get("cast_time", 0.0),
            animation=data.get("animation", ""),
            effects=data.get("effects", []),
            ability_units=data.get("ability_units", []),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 本地投射物配置
# ============================================================================

@dataclass
class ProjectileConfig:
    """本地投射物配置"""
    projectile_id: str
    projectile_name: str
    description: str = ""
    speed: float = 10.0  # 速度
    lifetime: float = 5.0  # 生命周期（秒）
    gravity: float = 0.0  # 重力系数
    model: str = ""  # 模型资源
    trail_effect: str = ""  # 轨迹特效
    hit_detection_enabled: bool = True  # 命中检测
    hit_ability_units: List[str] = field(default_factory=list)  # 命中时触发的能力单元
    destroy_ability_units: List[str] = field(default_factory=list)  # 销毁时触发的能力单元
    bounce_count: int = 0  # 弹跳次数
    pierce_count: int = 0  # 穿透次数
    metadata: dict = field(default_factory=dict)
    
    doc_reference: str = "战斗预设.md:6"
    
    def serialize(self) -> dict:
        return {
            "projectile_id": self.projectile_id,
            "projectile_name": self.projectile_name,
            "description": self.description,
            "speed": self.speed,
            "lifetime": self.lifetime,
            "gravity": self.gravity,
            "model": self.model,
            "trail_effect": self.trail_effect,
            "hit_detection_enabled": self.hit_detection_enabled,
            "hit_ability_units": self.hit_ability_units,
            "destroy_ability_units": self.destroy_ability_units,
            "bounce_count": self.bounce_count,
            "pierce_count": self.pierce_count,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'ProjectileConfig':
        return ProjectileConfig(
            projectile_id=data["projectile_id"],
            projectile_name=data["projectile_name"],
            description=data.get("description", ""),
            speed=data.get("speed", 10.0),
            lifetime=data.get("lifetime", 5.0),
            gravity=data.get("gravity", 0.0),
            model=data.get("model", ""),
            trail_effect=data.get("trail_effect", ""),
            hit_detection_enabled=data.get("hit_detection_enabled", True),
            hit_ability_units=data.get("hit_ability_units", []),
            destroy_ability_units=data.get("destroy_ability_units", []),
            bounce_count=data.get("bounce_count", 0),
            pierce_count=data.get("pierce_count", 0),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 道具配置
# ============================================================================

@dataclass
class ItemConfig:
    """道具配置（战斗预设版，用于战斗预设数据模型）
    
    注：这是战斗预设系统的道具配置，侧重于序列化与战斗属性。
    如需运行时资源系统的道具配置，请使用 combat.resource_system_configs.ItemConfig
    如需编辑器级的道具模板，请使用 specialized.resource_system_extended_configs.ItemTemplateConfig
    """
    item_id: str
    item_name: str
    description: str = ""
    item_type: str = "consumable"  # consumable/equipment/material/quest
    rarity: str = "common"  # common/uncommon/rare/epic/legendary
    max_stack: int = 99  # 最大堆叠数量
    icon: str = ""
    use_effect: str = ""  # 使用效果（节点图或能力单元）
    cooldown: float = 0.0  # 使用冷却
    attributes: Dict[str, float] = field(default_factory=dict)  # 属性加成
    requirements: Dict[str, Any] = field(default_factory=dict)  # 使用要求
    # 纯数据意义上的“配置ID”，通常用于与外部系统或表格对齐，区别于 item_id（资源主键）。
    # 推荐使用仅包含数字的字符串，例如 "1001"、"20001"；留空表示未设置。
    config_id: str = ""
    metadata: dict = field(default_factory=dict)
    
    doc_reference: str = "战斗预设.md:7"
    
    def serialize(self) -> dict:
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "description": self.description,
            "item_type": self.item_type,
            "rarity": self.rarity,
            "max_stack": self.max_stack,
            "icon": self.icon,
            "use_effect": self.use_effect,
            "cooldown": self.cooldown,
            "attributes": self.attributes,
            "requirements": self.requirements,
            "config_id": self.config_id,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'ItemConfig':
        return ItemConfig(
            item_id=data["item_id"],
            item_name=data["item_name"],
            description=data.get("description", ""),
            item_type=data.get("item_type", "consumable"),
            rarity=data.get("rarity", "common"),
            max_stack=data.get("max_stack", 99),
            icon=data.get("icon", ""),
            use_effect=data.get("use_effect", ""),
            cooldown=data.get("cooldown", 0.0),
            attributes=data.get("attributes", {}),
            requirements=data.get("requirements", {}),
            config_id=str(data.get("config_id", "")),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("=== 战斗预设数据模型测试 ===\n")
    
    # 测试玩家职业
    print("1. 玩家职业配置:")
    player_class = PlayerClassConfig(
        class_id="warrior_001",
        class_name="战士",
        description="近战职业",
        base_health=150.0,
        base_attack=20.0,
        skill_list=["slash_001", "charge_001"]
    )
    print(f"   职业名: {player_class.class_name}")
    print(f"   基础生命: {player_class.base_health}")
    print(f"   技能数: {len(player_class.skill_list)}")
    
    # 测试技能
    print("\n2. 技能配置:")
    skill = SkillConfig(
        skill_id="fireball_001",
        skill_name="火球术",
        description="投掷一个火球",
        cooldown=3.0,
        damage=50.0,
        range_value=15.0
    )
    print(f"   技能名: {skill.skill_name}")
    print(f"   冷却: {skill.cooldown}秒")
    print(f"   伤害: {skill.damage}")
    
    # 测试投射物
    print("\n3. 投射物配置:")
    projectile = ProjectileConfig(
        projectile_id="arrow_001",
        projectile_name="箭矢",
        speed=20.0,
        lifetime=3.0
    )
    print(f"   投射物名: {projectile.projectile_name}")
    print(f"   速度: {projectile.speed}m/s")
    
    # 测试序列化
    print("\n4. 序列化测试:")
    skill_data = skill.serialize()
    skill_restored = SkillConfig.deserialize(skill_data)
    print(f"   序列化成功: {skill.skill_name == skill_restored.skill_name}")
    
    print("\n✅ 战斗预设数据模型测试完成")

