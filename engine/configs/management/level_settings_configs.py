"""
关卡设置配置模块
包含关卡设置、阵营、出生点、复苏点、玩家分组、胜利失败条件等配置
"""

from dataclasses import dataclass, field
from typing import List, Any


# ============================================================================
# 阵营配置
# ============================================================================

@dataclass
class FactionConfig:
    """阵营配置"""
    faction_id: str
    faction_name: str
    player_count: int = 1
    enemy_factions: List[str] = field(default_factory=list)  # 敌对阵营ID列表


# ============================================================================
# 出生点配置
# ============================================================================

@dataclass
class SpawnPointConfig:
    """出生点配置"""
    spawn_id: str
    spawn_name: str
    preset_point_id: str = ""  # 关联的预设点ID
    character_templates: List[str] = field(default_factory=list)  # 应用的角色模版
    shared: bool = False  # 是否共享


# ============================================================================
# 复苏点配置
# ============================================================================

@dataclass
class RespawnPointConfig:
    """复苏点配置"""
    respawn_id: str
    priority: int = 0  # 优先级，数字越大越优先
    preset_point_id: str = ""  # 关联的预设点ID


# ============================================================================
# 玩家分组配置
# ============================================================================

@dataclass
class PlayerGroupConfig:
    """玩家分组配置"""
    group_id: str
    count_type: str = "fixed"  # fixed/custom
    player_count: int = 1
    included_players: List[int] = field(default_factory=list)  # 玩家ID列表
    is_required: bool = True  # 是否为必要分组


# ============================================================================
# 胜利失败条件
# ============================================================================

@dataclass
class VictoryCondition:
    """胜利条件"""
    condition_type: str  # kill_all/survive/collect/custom
    target_value: Any = None
    description: str = ""


@dataclass
class DefeatCondition:
    """失败条件"""
    condition_type: str  # time_out/all_dead/custom
    target_value: Any = None
    description: str = ""


# ============================================================================
# 关卡设置配置
# ============================================================================

@dataclass
class LevelSettingsConfig:
    """关卡设置配置 - 完整版本"""
    config_id: str = "default"
    
    # 基础设置
    scene_range: str = "全场景"  # 场景生效范围
    environment_level: int = 1  # 环境等级(1-120)
    initial_time_hour: int = 12  # 初始时间（小时）
    time_flow_ratio: float = 1.0  # 时间流逝比例
    load_optimization: bool = False  # 负载优化
    out_of_range_disabled: bool = False  # 超出范围不运行
    hatred_type: str = "默认"  # 仇恨类型：默认/自定义
    shield_calc_mode: str = "统一计算"  # 护盾计算：统一计算/独立计算
    
    # 阵营
    factions: List[FactionConfig] = field(default_factory=list)
    
    # 出生点
    spawn_shared: bool = False  # 是否共享出生点
    spawn_points: List[SpawnPointConfig] = field(default_factory=list)
    
    # 复苏点
    respawn_points: List[RespawnPointConfig] = field(default_factory=list)
    
    # 人数设置
    player_groups: List[PlayerGroupConfig] = field(default_factory=list)
    
    # 加载界面
    loading_bg_image: str = ""  # 加载背景图
    loading_title: str = ""  # 加载标题
    loading_description: str = ""  # 加载简介
    
    # 结算
    settlement_type: str = "个人结算"  # 个人结算/阵营结算
    enable_ranking: bool = False  # 启用游戏内排名
    
    # 旧字段（兼容）
    level_name: str = "未命名关卡"
    level_description: str = ""
    max_players: int = 4
    min_players: int = 1
    time_limit: float = 0.0
    victory_conditions: List[VictoryCondition] = field(default_factory=list)
    defeat_conditions: List[DefeatCondition] = field(default_factory=list)
    difficulty: str = "normal"
    recommended_level: int = 1
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "config_id": self.config_id,
            # 基础设置
            "scene_range": self.scene_range,
            "environment_level": self.environment_level,
            "initial_time_hour": self.initial_time_hour,
            "time_flow_ratio": self.time_flow_ratio,
            "load_optimization": self.load_optimization,
            "out_of_range_disabled": self.out_of_range_disabled,
            "hatred_type": self.hatred_type,
            "shield_calc_mode": self.shield_calc_mode,
            # 阵营
            "factions": [
                {
                    "faction_id": f.faction_id,
                    "faction_name": f.faction_name,
                    "player_count": f.player_count,
                    "enemy_factions": f.enemy_factions
                }
                for f in self.factions
            ],
            # 出生点
            "spawn_shared": self.spawn_shared,
            "spawn_points": [
                {
                    "spawn_id": s.spawn_id,
                    "spawn_name": s.spawn_name,
                    "preset_point_id": s.preset_point_id,
                    "character_templates": s.character_templates,
                    "shared": s.shared
                }
                for s in self.spawn_points
            ],
            # 复苏点
            "respawn_points": [
                {
                    "respawn_id": r.respawn_id,
                    "priority": r.priority,
                    "preset_point_id": r.preset_point_id
                }
                for r in self.respawn_points
            ],
            # 人数设置
            "player_groups": [
                {
                    "group_id": g.group_id,
                    "count_type": g.count_type,
                    "player_count": g.player_count,
                    "included_players": g.included_players,
                    "is_required": g.is_required
                }
                for g in self.player_groups
            ],
            # 加载界面
            "loading_bg_image": self.loading_bg_image,
            "loading_title": self.loading_title,
            "loading_description": self.loading_description,
            # 结算
            "settlement_type": self.settlement_type,
            "enable_ranking": self.enable_ranking,
            # 旧字段（兼容）
            "level_name": self.level_name,
            "level_description": self.level_description,
            "max_players": self.max_players,
            "min_players": self.min_players,
            "time_limit": self.time_limit,
            "victory_conditions": [
                {
                    "condition_type": vc.condition_type,
                    "target_value": vc.target_value,
                    "description": vc.description
                }
                for vc in self.victory_conditions
            ],
            "defeat_conditions": [
                {
                    "condition_type": dc.condition_type,
                    "target_value": dc.target_value,
                    "description": dc.description
                }
                for dc in self.defeat_conditions
            ],
            "difficulty": self.difficulty,
            "recommended_level": self.recommended_level,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'LevelSettingsConfig':
        # 阵营
        factions = [
            FactionConfig(
                faction_id=f["faction_id"],
                faction_name=f["faction_name"],
                player_count=f.get("player_count", 1),
                enemy_factions=f.get("enemy_factions", [])
            )
            for f in data.get("factions", [])
        ]
        
        # 出生点
        spawn_points = [
            SpawnPointConfig(
                spawn_id=s["spawn_id"],
                spawn_name=s["spawn_name"],
                preset_point_id=s.get("preset_point_id", ""),
                character_templates=s.get("character_templates", []),
                shared=s.get("shared", False)
            )
            for s in data.get("spawn_points", [])
        ]
        
        # 复苏点
        respawn_points = [
            RespawnPointConfig(
                respawn_id=r["respawn_id"],
                priority=r.get("priority", 0),
                preset_point_id=r.get("preset_point_id", "")
            )
            for r in data.get("respawn_points", [])
        ]
        
        # 人数分组
        player_groups = [
            PlayerGroupConfig(
                group_id=g["group_id"],
                count_type=g.get("count_type", "fixed"),
                player_count=g.get("player_count", 1),
                included_players=g.get("included_players", []),
                is_required=g.get("is_required", True)
            )
            for g in data.get("player_groups", [])
        ]
        
        # 胜利条件
        victory_conditions = [
            VictoryCondition(
                condition_type=vc["condition_type"],
                target_value=vc.get("target_value"),
                description=vc.get("description", "")
            )
            for vc in data.get("victory_conditions", [])
        ]
        
        # 失败条件
        defeat_conditions = [
            DefeatCondition(
                condition_type=dc["condition_type"],
                target_value=dc.get("target_value"),
                description=dc.get("description", "")
            )
            for dc in data.get("defeat_conditions", [])
        ]
        
        return LevelSettingsConfig(
            config_id=data.get("config_id", "default"),
            # 基础设置
            scene_range=data.get("scene_range", "全场景"),
            environment_level=data.get("environment_level", 1),
            initial_time_hour=data.get("initial_time_hour", 12),
            time_flow_ratio=data.get("time_flow_ratio", 1.0),
            load_optimization=data.get("load_optimization", False),
            out_of_range_disabled=data.get("out_of_range_disabled", False),
            hatred_type=data.get("hatred_type", "默认"),
            shield_calc_mode=data.get("shield_calc_mode", "统一计算"),
            # 阵营
            factions=factions,
            # 出生点
            spawn_shared=data.get("spawn_shared", False),
            spawn_points=spawn_points,
            # 复苏点
            respawn_points=respawn_points,
            # 人数设置
            player_groups=player_groups,
            # 加载界面
            loading_bg_image=data.get("loading_bg_image", ""),
            loading_title=data.get("loading_title", ""),
            loading_description=data.get("loading_description", ""),
            # 结算
            settlement_type=data.get("settlement_type", "个人结算"),
            enable_ranking=data.get("enable_ranking", False),
            # 旧字段（兼容）
            level_name=data.get("level_name", "未命名关卡"),
            level_description=data.get("level_description", ""),
            max_players=data.get("max_players", 4),
            min_players=data.get("min_players", 1),
            time_limit=data.get("time_limit", 0.0),
            victory_conditions=victory_conditions,
            defeat_conditions=defeat_conditions,
            difficulty=data.get("difficulty", "normal"),
            recommended_level=data.get("recommended_level", 1),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 关卡设置配置测试 ===\n")
    
    # 测试关卡设置
    print("1. 关卡设置配置:")
    level_settings = LevelSettingsConfig(
        config_id="level_001",
        level_name="第一章",
        scene_range="全场景",
        environment_level=1,
        initial_time_hour=12,
        max_players=4,
        min_players=1,
        difficulty="normal"
    )
    
    # 添加阵营
    level_settings.factions.append(
        FactionConfig(
            faction_id="faction_1",
            faction_name="玩家阵营",
            player_count=4,
            enemy_factions=["faction_2"]
        )
    )
    level_settings.factions.append(
        FactionConfig(
            faction_id="faction_2",
            faction_name="敌人阵营",
            player_count=0,
            enemy_factions=["faction_1"]
        )
    )
    
    # 添加出生点
    level_settings.spawn_points.append(
        SpawnPointConfig(
            spawn_id="spawn_1",
            spawn_name="玩家出生点",
            preset_point_id="preset_001"
        )
    )
    
    # 添加胜利条件
    level_settings.victory_conditions.append(
        VictoryCondition(
            condition_type="kill_all",
            target_value="faction_2",
            description="击败所有敌人"
        )
    )
    
    print(f"   关卡名: {level_settings.level_name}")
    print(f"   难度: {level_settings.difficulty}")
    print(f"   最大玩家: {level_settings.max_players}")
    print(f"   阵营数量: {len(level_settings.factions)}")
    print(f"   出生点数量: {len(level_settings.spawn_points)}")
    print(f"   胜利条件数量: {len(level_settings.victory_conditions)}")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    data = level_settings.serialize()
    restored = LevelSettingsConfig.deserialize(data)
    print(f"   序列化成功: {level_settings.level_name == restored.level_name}")
    print(f"   阵营恢复: {len(level_settings.factions) == len(restored.factions)}")
    
    print("\n✅ 关卡设置配置测试完成")

