"""组件验证器"""

from typing import Any, Iterable, List

from engine.configs.rules import is_component_compatible
from .issue import EngineIssue


class ComponentValidator:
    """组件验证器
    
    验证组件与实体的兼容性。
    """

    @staticmethod
    def validate_component(component_name: str, entity_type: str) -> List[EngineIssue]:
        """验证单个组件与实体的兼容性

        Args:
            component_name: 组件名称
            entity_type: 实体类型

        Returns:
            验证问题列表（EngineIssue）
        """
        issues: List[EngineIssue] = []

        compatible, error_msg = is_component_compatible(component_name, entity_type)

        if not compatible:
            issues.append(
                EngineIssue(
                    level="error",
                    category="组件",
                    code="COMPONENT_INCOMPATIBLE",
                    message=error_msg,
                )
            )

        return issues

    @staticmethod
    def validate_components(components: List[str], entity_type: str) -> List[EngineIssue]:
        """验证多个组件与实体的兼容性

        Args:
            components: 组件名称列表
            entity_type: 实体类型

        Returns:
            验证问题列表（EngineIssue）
        """
        issues: List[EngineIssue] = []

        for component in components:
            issues.extend(ComponentValidator.validate_component(component, entity_type))

        return issues

    @staticmethod
    def collect_component_names(raw_components: Iterable[Any]) -> List[str]:
        """统一抽取组件名称，兼容字符串、dict 与对象写法。"""
        names: List[str] = []
        for component in raw_components:
            if isinstance(component, str):
                candidate = component
            elif hasattr(component, "component_type"):
                candidate = getattr(component, "component_type", "")
            elif isinstance(component, dict):
                candidate = component.get("component_type", "")
            else:
                candidate = ""
            if candidate:
                names.append(candidate)
        return names

