"""
实体配置验证器
验证实体配置项是否符合知识库规范
"""
from typing import Any, Callable, Dict, List

from .issue import EngineIssue
from ..configs.entities.entity_configs import (
    BaseCombatAttributes,
    CharacterConfig,
    CreatureConfig,
    LocalProjectileBaseSettings,
    LocalProjectileCombatParams,
    LocalProjectileConfig,
    LocalProjectileLifecycle,
    ObjectConfig,
    PlayerConfig,
    ReviveConfig,
    SkillConfig,
)


def _validate_combat_attributes(
    combat_attributes: Any,
    *,
    level_error_code: str,
    health_error_code: str,
    attack_error_code: str,
) -> List[EngineIssue]:
    issues: List[EngineIssue] = []

    if combat_attributes.level < 1:
        issues.append(
            EngineIssue(
                level="error",
                category="实体配置",
                code=level_error_code,
                message="等级不能小于1",
                reference="",
            )
        )

    if combat_attributes.base_health <= 0:
        issues.append(
            EngineIssue(
                level="error",
                category="实体配置",
                code=health_error_code,
                message="基础生命值必须大于0",
                reference="",
            )
        )

    if combat_attributes.base_attack < 0:
        issues.append(
            EngineIssue(
                level="error",
                category="实体配置",
                code=attack_error_code,
                message="基础攻击力不能为负数",
                reference="",
            )
        )

    return issues


class EntityConfigValidator:
    """实体配置验证器"""

    @staticmethod
    def validate_revive_config(config: ReviveConfig) -> List[EngineIssue]:
        """
        验证复苏配置
        """
        issues: List[EngineIssue] = []

        # 验证复苏后生命比例不可为0（复苏.md 第36行）
        if config.revive_health_percentage <= 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="REVIVE_HEALTH_ZERO",
                    message=(
                        "复苏后生命比例(%)不可为0\n"
                        f"当前值: {config.revive_health_percentage}"
                    ),
                    reference="复苏.md:36 '复苏后角色生命值百分比，该值不可为0'",
                )
            )

        # 验证复苏后生命比例范围
        if config.revive_health_percentage > 100:
            issues.append(
                EngineIssue(
                    level="warning",
                    category="实体配置",
                    code="REVIVE_HEALTH_TOO_HIGH",
                    message=(
                        "复苏后生命比例(%)建议不超过100%\n"
                        f"当前值: {config.revive_health_percentage}"
                    ),
                    reference="",
                )
            )

        # 验证复苏时间不为负
        if config.revive_duration < 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="REVIVE_DURATION_NEGATIVE",
                    message=(
                        "复苏耗时(s)不能为负数\n"
                        f"当前值: {config.revive_duration}"
                    ),
                    reference="",
                )
            )

        # 验证逻辑一致性：不显示复苏界面时的提示
        if not config.show_revive_ui and config.allow_revive:
            issues.append(
                EngineIssue(
                    level="warning",
                    category="实体配置",
                    code="REVIVE_UI_HIDDEN_BUT_ALLOWED",
                    message=(
                        "当配置为【不显示复苏界面】时，该玩家倒下后不会弹出复苏界面\n"
                        "这意味着这名玩家无法通过游戏的内置逻辑进行复苏，需要为其制作自定义逻辑进行复苏\n"
                        "（例如：其他角色协助其复苏等），否则将无法复苏、只能退出当前关卡"
                    ),
                    reference="复苏.md:30",
                )
            )

        # 验证复苏点列表为空时的提示
        if config.allow_revive and len(config.revive_point_list) == 0:
            issues.append(
                EngineIssue(
                    level="warning",
                    category="实体配置",
                    code="REVIVE_POINTS_EMPTY",
                    message=(
                        "允许复苏但复苏点列表为空\n"
                        "建议配置至少一个复苏点，否则玩家可能无法正常复苏"
                    ),
                    reference="",
                )
            )

        return issues

    @staticmethod
    def validate_player_config(config: PlayerConfig) -> List[EngineIssue]:
        """验证玩家配置"""
        issues: List[EngineIssue] = []

        # 验证复苏配置
        revive_issues = EntityConfigValidator.validate_revive_config(config.revive_config)
        issues.extend(revive_issues)

        # 验证等级
        if config.level < 1:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="PLAYER_LEVEL_TOO_LOW",
                    message=f"玩家等级不能小于1\n当前值: {config.level}",
                    reference="",
                )
            )

        return issues

    @staticmethod
    def validate_local_projectile_config(config: LocalProjectileConfig) -> List[EngineIssue]:
        """
        验证本地投射物配置
        """
        issues: List[EngineIssue] = []

        # 验证缩放值
        if (
            config.base_settings.scale_x <= 0
            or config.base_settings.scale_y <= 0
            or config.base_settings.scale_z <= 0
        ):
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="PROJECTILE_SCALE_NONPOSITIVE",
                    message=(
                        "xyz缩放值必须大于0\n"
                        f"当前值: x={config.base_settings.scale_x}, "
                        f"y={config.base_settings.scale_y}, "
                        f"z={config.base_settings.scale_z}"
                    ),
                    reference="",
                )
            )

        # 验证生命周期设置
        if not config.lifecycle.permanent and config.lifecycle.duration <= 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="PROJECTILE_DURATION_NONPOSITIVE",
                    message=(
                        "非永久持续时，持续时长必须大于0\n"
                        f"当前值: {config.lifecycle.duration}"
                    ),
                    reference="",
                )
            )

        # 验证距离设置
        if config.lifecycle.destroy_at_xz_max_distance and config.lifecycle.xz_max_distance <= 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="PROJECTILE_XZ_DISTANCE_NONPOSITIVE",
                    message=(
                        "启用xz轴距离销毁时，最大距离必须大于0\n"
                        f"当前值: {config.lifecycle.xz_max_distance}"
                    ),
                    reference="",
                )
            )

        if config.lifecycle.destroy_at_y_max_distance and config.lifecycle.y_max_distance <= 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="PROJECTILE_Y_DISTANCE_NONPOSITIVE",
                    message=(
                        "启用y轴距离销毁时，最大距离必须大于0\n"
                        f"当前值: {config.lifecycle.y_max_distance}"
                    ),
                    reference="",
                )
            )

        return issues

    @staticmethod
    def validate_skill_config(config: SkillConfig) -> List[EngineIssue]:
        """
        验证技能配置
        """
        issues: List[EngineIssue] = []

        # 验证冷却时间
        if config.has_cooldown and config.cooldown_time < 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="SKILL_COOLDOWN_NEGATIVE",
                    message=(
                        "冷却时间不能为负数\n"
                        f"当前值: {config.cooldown_time}"
                    ),
                    reference="",
                )
            )

        # 验证使用次数
        if config.has_usage_limit and config.usage_count < 1:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="SKILL_USAGE_COUNT_TOO_LOW",
                    message=(
                        "使用次数限制不能小于1\n"
                        f"当前值: {config.usage_count}"
                    ),
                    reference="",
                )
            )

        # 验证消耗量
        if config.has_cost and config.cost_amount < 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="SKILL_COST_NEGATIVE",
                    message=(
                        "消耗量不能为负数\n"
                        f"当前值: {config.cost_amount}"
                    ),
                    reference="",
                )
            )

        # 验证索敌范围
        if config.lock_range < 0:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体配置",
                    code="SKILL_LOCK_RANGE_NEGATIVE",
                    message=(
                        "索敌范围不能为负数\n"
                        f"当前值: {config.lock_range}"
                    ),
                    reference="",
                )
            )

        return issues

    @staticmethod
    def validate_character_config(config: CharacterConfig) -> List[EngineIssue]:
        """验证角色配置"""
        issues: List[EngineIssue] = []

        issues.extend(
            _validate_combat_attributes(
                config.combat_attributes,
                level_error_code="CHARACTER_LEVEL_TOO_LOW",
                health_error_code="CHARACTER_HEALTH_NONPOSITIVE",
                attack_error_code="CHARACTER_ATTACK_NEGATIVE",
            )
        )

        return issues

    @staticmethod
    def validate_creature_config(config: CreatureConfig) -> List[EngineIssue]:
        """验证造物配置"""
        issues: List[EngineIssue] = []

        issues.extend(
            _validate_combat_attributes(
                config.combat_attributes,
                level_error_code="CREATURE_LEVEL_TOO_LOW",
                health_error_code="CREATURE_HEALTH_NONPOSITIVE",
                attack_error_code="CREATURE_ATTACK_NEGATIVE",
            )
        )

        return issues

    @staticmethod
    def validate_object_config(config: ObjectConfig) -> List[EngineIssue]:
        """
        验证物件配置
        """
        issues: List[EngineIssue] = []

        # 静态物件不应该有预设状态（物件.md 第8-10行）
        if config.is_static and config.preset_state:
            issues.append(
                EngineIssue(
                    level="warning",
                    category="实体配置",
                    code="STATIC_OBJECT_PRESET_STATE",
                    message="静态物件不支持预设状态",
                    reference="物件.md:8-10 '静态物件不支持组件、节点图等任何功能'",
                )
            )

        return issues

    @staticmethod
    def validate_entity_config_by_type(entity_type: str, config_dict: Dict[str, Any]) -> List[EngineIssue]:
        """根据实体类型验证配置"""
        if entity_type in {"物件-静态", "物件-动态"}:
            is_static = entity_type == "物件-静态"
            object_config = (
                ObjectConfig(is_static=is_static, **config_dict)
                if config_dict
                else ObjectConfig(is_static=is_static)
            )
            return EntityConfigValidator.validate_object_config(object_config)

        handler = _ENTITY_CONFIG_HANDLERS.get(entity_type)
        if handler is None:
            return []
        return handler(config_dict or {})


def _build_character_config(data: Dict[str, Any]) -> CharacterConfig:
    payload = dict(data or {})
    payload["combat_attributes"] = _build_combat_attributes(payload.get("combat_attributes"))
    payload["equipment_slots"] = payload.get("equipment_slots", [])
    return CharacterConfig(**payload)


def _build_creature_config(data: Dict[str, Any]) -> CreatureConfig:
    payload = dict(data or {})
    payload["combat_attributes"] = _build_combat_attributes(payload.get("combat_attributes"))
    payload["hatred_config"] = payload.get("hatred_config", {})
    payload["general_settings"] = payload.get("general_settings", {})
    payload["behavior_mode"] = payload.get("behavior_mode", "")
    return CreatureConfig(**payload)


def _build_local_projectile_config(data: Dict[str, Any]) -> LocalProjectileConfig:
    payload = dict(data or {})
    payload["base_settings"] = _build_local_projectile_section(
        LocalProjectileBaseSettings, payload.get("base_settings")
    )
    payload["combat_params"] = _build_local_projectile_section(
        LocalProjectileCombatParams, payload.get("combat_params")
    )
    payload["lifecycle"] = _build_local_projectile_section(
        LocalProjectileLifecycle, payload.get("lifecycle")
    )
    return LocalProjectileConfig(**payload)


def _build_local_projectile_section(section_cls, value):
    if isinstance(value, section_cls):
        return value
    if isinstance(value, dict):
        return section_cls(**value)
    return section_cls()


def _build_combat_attributes(value: Any) -> BaseCombatAttributes:
    if isinstance(value, BaseCombatAttributes):
        return value
    if isinstance(value, dict):
        return BaseCombatAttributes(**value)
    return BaseCombatAttributes()


_ENTITY_CONFIG_HANDLERS: Dict[str, Callable[[Dict[str, Any]], List[EngineIssue]]] = {
    "玩家": lambda data: EntityConfigValidator.validate_player_config(
        PlayerConfig.from_dict(data)
    ),
    "角色": lambda data: EntityConfigValidator.validate_character_config(
        _build_character_config(data)
    ),
    "造物": lambda data: EntityConfigValidator.validate_creature_config(
        _build_creature_config(data)
    ),
    "本地投射物": lambda data: EntityConfigValidator.validate_local_projectile_config(
        _build_local_projectile_config(data)
    ),
    "技能": lambda data: EntityConfigValidator.validate_skill_config(
        SkillConfig(**(data or {}))
    ),
}

