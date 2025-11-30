"""实体验证器"""

from typing import List, Dict, Any

from engine.configs.rules import ENTITY_TYPES, validate_entity_transform
from .issue import EngineIssue
from .component_validator import ComponentValidator


class EntityValidator:
    """实体验证器

    验证实体配置是否符合 UGC 编辑器规范。
    """

    @staticmethod
    def validate_entity_type(entity_type: str) -> List[EngineIssue]:
        """验证实体类型是否存在"""
        issues: List[EngineIssue] = []
        if entity_type not in ENTITY_TYPES:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体类型",
                    code="ENTITY_TYPE_UNKNOWN",
                    message=f"实体类型'{entity_type}'不存在\n可用类型: {', '.join(ENTITY_TYPES.keys())}",
                )
            )
        return issues

    @staticmethod
    def validate_transform(
        entity_type: str,
        transform_config: Dict[str, Any],
        rules: Dict[str, Any] | None = None,
    ) -> List[EngineIssue]:
        """验证实体的变换信息"""
        issues: List[EngineIssue] = []

        resolved_rules = rules if rules is not None else _resolve_entity_rules(entity_type)
        if not resolved_rules:
            return issues

        rotation_value = transform_config.get("rotation")
        scale_value = transform_config.get("scale")
        position_present = "position" in transform_config

        base_transform_errors = validate_entity_transform(
            entity_type,
            has_rotation=bool(rotation_value),
            has_scale=bool(scale_value),
            has_position=position_present,
        )
        for message in base_transform_errors:
            issues.append(
                EngineIssue(
                    level="error",
                    category="变换",
                    code="TRANSFORM_RULE_VIOLATION",
                    message=message,
                    reference=resolved_rules.get("reference", ""),
                )
            )

        if rotation_value and resolved_rules.get("has_rotation") == "仅Y轴":
            rot = rotation_value
            if isinstance(rot, dict):
                if rot.get("x", 0) != 0 or rot.get("z", 0) != 0:
                    issues.append(
                        EngineIssue(
                            level="error",
                            category="变换",
                            code="TRANSFORM_ROTATION_XZ_NOT_ALLOWED",
                            message=(
                                f"实体类型'{entity_type}'仅支持Y轴旋转，不支持X、Z轴旋转\n"
                                f"当前旋转: X={rot.get('x')}, Y={rot.get('y')}, Z={rot.get('z')}"
                            ),
                            reference=resolved_rules.get("reference", ""),
                        )
                    )

        return issues

    @staticmethod
    def validate_components(
        entity_type: str,
        components: List[str],
        rules: Dict[str, Any] | None = None,
    ) -> List[EngineIssue]:
        """验证实体的组件配置"""
        issues: List[EngineIssue] = []

        resolved_rules = rules if rules is not None else _resolve_entity_rules(entity_type)
        if not resolved_rules:
            return issues

        # 静态物件不支持组件
        if _is_static_entity(entity_type) and components:
            issues.append(
                EngineIssue(
                    level="error",
                    category="组件",
                    code="STATIC_OBJECT_COMPONENTS_FORBIDDEN",
                    message="静态物件不支持添加组件，但发现了以下组件:\n  - " + "\n  - ".join(components),
                    reference=resolved_rules.get("reference", ""),
                )
            )
            return issues

        issues.extend(
            ComponentValidator.validate_components(
                components,
                entity_type,
            )
        )

        return issues

    @staticmethod
    def validate_node_graphs(
        entity_type: str,
        has_node_graphs: bool,
        rules: Dict[str, Any] | None = None,
    ) -> List[EngineIssue]:
        """验证实体是否可以有节点图"""
        issues: List[EngineIssue] = []

        resolved_rules = rules if rules is not None else _resolve_entity_rules(entity_type)
        if not resolved_rules:
            return issues

        # 静态物件不支持节点图
        if _is_static_entity(entity_type) and has_node_graphs:
            issues.append(
                EngineIssue(
                    level="error",
                    category="节点图",
                    code="STATIC_OBJECT_GRAPHS_FORBIDDEN",
                    message="静态物件不支持节点图",
                    reference=resolved_rules.get("reference", ""),
                )
            )

        return issues

    @staticmethod
    def validate_entity(entity_type: str, entity_config: Dict[str, Any]) -> List[EngineIssue]:
        """验证完整的实体配置

        Args:
            entity_type: 实体类型
            entity_config: 实体配置字典，包含：
                - transform: 变换信息 (可选)
                - components: 组件列表 (可选)
                - node_graphs: 节点图列表 (可选)

        Returns:
            验证问题列表（EngineIssue）
        """
        issues: List[EngineIssue] = []

        # 验证实体类型
        issues.extend(EntityValidator.validate_entity_type(entity_type))
        if issues:
            return issues

        rules = _resolve_entity_rules(entity_type)
        if not rules:
            issues.append(
                EngineIssue(
                    level="error",
                    category="实体类型",
                    code="ENTITY_RULES_MISSING",
                    message=f"实体类型'{entity_type}'缺少规则配置，无法继续验证",
                )
            )
            return issues

        # 验证变换信息
        if "transform" in entity_config:
            issues.extend(
                EntityValidator.validate_transform(
                    entity_type,
                    entity_config["transform"],
                    rules,
                )
            )

        # 验证组件
        if "components" in entity_config:
            components = entity_config["components"]
            if isinstance(components, list):
                component_names = ComponentValidator.collect_component_names(components)
                issues.extend(
                    EntityValidator.validate_components(
                        entity_type,
                        component_names,
                        rules,
                    )
                )

        # 验证节点图
        if "node_graphs" in entity_config or "default_graphs" in entity_config:
            graphs = entity_config.get("node_graphs") or entity_config.get("default_graphs", {})
            has_graphs = bool(graphs)
            issues.extend(
                EntityValidator.validate_node_graphs(
                    entity_type,
                    has_graphs,
                    rules,
                )
            )

        return issues


def _resolve_entity_rules(entity_type: str) -> Dict[str, Any] | None:
    return ENTITY_TYPES.get(entity_type)


def _is_static_entity(entity_type: str) -> bool:
    return entity_type == "物件-静态"

