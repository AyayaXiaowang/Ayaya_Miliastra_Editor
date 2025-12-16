from __future__ import annotations

"""
UI 级导航请求模型。

本模块定义一个与具体 UI 技术无关的轻量数据结构 `UiNavigationRequest`，
用于描述“要跳到哪个资源、希望聚焦到哪里、是谁发起的”这类导航意图。

设计目标：
- 集中表达从资源 ID → 视图模式 → 具体焦点（树 / 列表 / 图视图 / 节点 / 连线）的路径信息；
- 不依赖 PyQt，只作为数据载体，供 `ui.controllers.NavigationCoordinator` 消费；
- 通过小量 helper 统一构造常见导航场景（图节点/连线、模板/实例、管理面板 Section 等）。
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class UiNavigationRequest:
    """
    UI 级导航请求。

    字段约定：
    - resource_kind: 资源大类
        - "template" / "instance" / "level_entity"
        - "graph" / "graph_task"
        - "composite"
        - "management_section"
        - "validation_issue"
        - "combat"
    - resource_id:
        - 对于实体：模板 ID / 实例 ID / 关卡实体标识
        - 对于图：graph_id
        - 对于管理：section key 或条目 ID
    - desired_focus:
        - 表达 UI 层希望最终聚焦到的位置：
          "tree" / "list" / "graph_view" / "graph_node" / "graph_edge" /
          "management_item" / "validation_source" 等。
    - origin:
        - 表达是哪一块 UI 触发的请求：
          "todo" / "validation" / "graph_property" / "graph_library" /
          "package_library" / "management" / "external" 等。
    - payload:
        - 附带的原始上下文（如 todo.detail_info / validation_issue.detail），
          由 `NavigationCoordinator` 解释，不在模型层做任何逻辑。
    """

    resource_kind: str
    resource_id: Optional[str] = None
    desired_focus: Optional[str] = None
    origin: Optional[str] = None

    graph_id: Optional[str] = None
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None

    package_id: Optional[str] = None

    management_section_key: Optional[str] = None
    management_item_id: Optional[str] = None

    payload: Optional[Dict[str, object]] = None

    # === 工厂方法 ===

    @staticmethod
    def for_graph_view(
        graph_id: str,
        *,
        container_kind: Optional[str] = None,
        container_id: Optional[str] = None,
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """
        打开图并聚焦到整体画面（不指定具体节点/连线）。

        container_kind:
            - "template" / "instance" / "level_entity" / None
        container_id:
            - 对应的模板/实例/关卡实体 ID（若存在）
        """
        return UiNavigationRequest(
            resource_kind="graph",
            resource_id=graph_id,
            graph_id=graph_id,
            desired_focus="graph_view",
            origin=origin,
            package_id=None,
            payload=payload,
        )

    @staticmethod
    def for_graph_node(
        graph_id: str,
        node_id: str,
        *,
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """在指定图中聚焦到单个节点。"""
        return UiNavigationRequest(
            resource_kind="graph_task",
            resource_id=graph_id,
            graph_id=graph_id,
            node_id=node_id,
            desired_focus="graph_node",
            origin=origin,
            payload=payload,
        )

    @staticmethod
    def for_graph_edge(
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        *,
        edge_id: Optional[str] = None,
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """在指定图中聚焦到一条连线。"""
        return UiNavigationRequest(
            resource_kind="graph_task",
            resource_id=graph_id,
            graph_id=graph_id,
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            desired_focus="graph_edge",
            origin=origin,
            payload=payload,
        )

    @staticmethod
    def for_template(
        template_id: str,
        *,
        desired_focus: str = "tree",
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """聚焦到某个模板（通常对应元件库树/列表 + 右侧属性面板）。"""
        return UiNavigationRequest(
            resource_kind="template",
            resource_id=template_id,
            desired_focus=desired_focus,
            origin=origin,
            payload=payload,
        )

    @staticmethod
    def for_instance(
        instance_id: str,
        *,
        desired_focus: str = "list",
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """聚焦到某个实例（实体摆放列表 + 右侧属性面板）。"""
        return UiNavigationRequest(
            resource_kind="instance",
            resource_id=instance_id,
            desired_focus=desired_focus,
            origin=origin,
            payload=payload,
        )

    @staticmethod
    def for_composite(
        composite_name: str,
        *,
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """聚焦到复合节点管理器中的某个复合节点。"""
        return UiNavigationRequest(
            resource_kind="composite",
            resource_id=composite_name,
            desired_focus="composite",
            origin=origin,
            payload=payload,
        )

    @staticmethod
    def for_management_section(
        section_key: str,
        *,
        item_id: Optional[str] = None,
        origin: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
    ) -> "UiNavigationRequest":
        """跳转到管理配置库中的某个 Section（以及可选的具体条目）。"""
        return UiNavigationRequest(
            resource_kind="management_section",
            resource_id=section_key,
            desired_focus="management_item" if item_id else "management_section",
            origin=origin,
            management_section_key=section_key,
            management_item_id=item_id,
            payload=payload,
        )

    @staticmethod
    def for_validation_issue(
        detail: Dict[str, object],
        *,
        origin: str = "validation",
    ) -> "UiNavigationRequest":
        """
        从验证问题 detail 构造导航请求。

        约定：
        - detail["type"] in {"template", "instance", "level_entity"}
        - 其余字段（template_id / instance_id / graph_name 等）原样放入 payload，
          由 `NavigationCoordinator` 解释。
        """
        issue_type = str(detail.get("type", ""))
        resource_kind = "validation_issue"
        resource_id = None
        if issue_type in ("template", "instance", "level_entity"):
            resource_id = str(detail.get(f"{issue_type}_id", "") or "") or None
        return UiNavigationRequest(
            resource_kind=resource_kind,
            resource_id=resource_id,
            desired_focus="validation_source",
            origin=origin,
            payload=dict(detail),
        )

    @staticmethod
    def for_property_panel_entity(
        *,
        entity_type: str,
        entity_id: str,
        package_id: str,
        origin: Optional[str] = None,
    ) -> "UiNavigationRequest":
        """从各类“跳到实体”请求构造导航请求（右侧属性面板聚焦）。"""
        return UiNavigationRequest(
            resource_kind=entity_type,
            resource_id=entity_id,
            package_id=package_id,
            desired_focus="property_panel",
            origin=origin,
        )

    @staticmethod
    def for_open_player_editor(*, origin: Optional[str] = None) -> "UiNavigationRequest":
        """打开战斗预设的玩家编辑器页面。"""
        return UiNavigationRequest(
            resource_kind="combat",
            resource_id=None,
            desired_focus="player_editor",
            origin=origin,
        )

    @staticmethod
    def for_todo_task(
        detail_info: Dict[str, object],
        *,
        origin: Optional[str] = None,
    ) -> "UiNavigationRequest":
        """从 Todo 的 detail_info 构造“跳到任务相关节点图”的导航请求。"""
        graph_id = str(detail_info.get("graph_id") or "")
        return UiNavigationRequest(
            resource_kind="graph_task",
            resource_id=graph_id,
            graph_id=graph_id or None,
            desired_focus="graph_task",
            origin=origin,
            payload=dict(detail_info),
        )

    @staticmethod
    def for_todo_preview_jump(
        jump_info: Dict[str, object],
        *,
        origin: Optional[str] = None,
    ) -> Optional["UiNavigationRequest"]:
        """从 Todo 预览跳转信息构造导航请求。

        约定：jump_info["type"] in {"node", "edge"}。
        """
        jump_type = str(jump_info.get("type") or "")
        if jump_type == "node":
            node_id = jump_info.get("node_id")
            return UiNavigationRequest(
                resource_kind="graph_preview",
                resource_id=None,
                desired_focus="graph_node",
                origin=origin,
                node_id=str(node_id) if node_id else None,
                payload=dict(jump_info),
            )
        if jump_type == "edge":
            edge_id = jump_info.get("edge_id")
            source_node_id = jump_info.get("src_node")
            target_node_id = jump_info.get("dst_node")
            return UiNavigationRequest(
                resource_kind="graph_preview",
                resource_id=None,
                desired_focus="graph_edge",
                origin=origin,
                edge_id=str(edge_id) if edge_id else None,
                source_node_id=str(source_node_id) if source_node_id else None,
                target_node_id=str(target_node_id) if target_node_id else None,
                payload=dict(jump_info),
            )
        return None


