"""节点挂载验证器"""

from typing import List

from engine.configs.rules import NODE_ENTITY_RESTRICTIONS, can_node_mount_on_entity
from .issue import EngineIssue

CLIENT_ENTITY_TYPES = {
    "UIWidget",
    "UI组件",
    "UIImage",
    "UI图片",
    "UIText",
    "UI文本",
    "UIButton",
    "UI按钮",
}


class NodeMountValidator:
    """节点挂载验证器

    验证节点是否可以挂载到指定实体类型上。
    """

    @staticmethod
    def validate_node_mount(node_name: str, entity_type: str) -> List[EngineIssue]:
        """验证节点挂载

        Args:
            node_name: 节点名称
            entity_type: 实体类型

        Returns:
            验证问题列表（EngineIssue）
        """
        issues: List[EngineIssue] = []

        can_mount, error_msg = can_node_mount_on_entity(node_name, entity_type)

        if not can_mount:
            issues.append(
                EngineIssue(
                    level="error",
                    category="节点挂载",
                    code="NODE_MOUNT_FORBIDDEN",
                    message=error_msg,
                )
            )

        return issues

    @staticmethod
    def validate_composite_node_scope(
        node_category: str,
        entity_type: str,
        node_name: str = "",
    ) -> List[EngineIssue]:
        """验证复合节点的作用域限制

        复合节点仅支持服务器节点，不能用于客户端。

        Args:
            node_category: 节点类别
            entity_type: 实体类型
            node_name: 节点名称（用于错误提示）

        Returns:
            验证问题列表（EngineIssue）
        """
        issues: List[EngineIssue] = []

        # 如果不是复合节点，直接返回
        if node_category != "复合节点":
            return issues

        if entity_type in CLIENT_ENTITY_TYPES:
            node_display_name = f"'{node_name}'" if node_name else "复合节点"
            issues.append(
                EngineIssue(
                    level="error",
                    category="复合节点作用域",
                    code="COMPOSITE_SCOPE_CLIENT_FORBIDDEN",
                    message=(
                        f"{node_display_name} 是复合节点，仅支持服务器节点图，不能用于客户端实体类型 '{entity_type}'。\n"
                        "建议：请在服务器实体（如角色、物体等）的节点图中使用复合节点。"
                    ),
                    reference="复合节点.md - 复合节点仅支持服务器节点",
                )
            )

        return issues


