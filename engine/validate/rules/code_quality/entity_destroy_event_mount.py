"""节点挂载相关的代码质量规则：实体销毁事件挂载语义提醒与同图冲突检测。"""

from __future__ import annotations

import ast
from typing import List, Set, Tuple

from engine.configs.rules import NODE_ENTITY_RESTRICTIONS, can_node_mount_on_entity

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import get_cached_module
from .graph_model_utils import _get_or_parse_graph_model, _span_for_graph_nodes


class EntityDestroyEventMountRule(ValidationRule):
    """实体销毁事件挂载语义提醒 + 混用冲突检测（面向类结构节点图源码）。

    需求背景：
    - 【实体销毁时】事件用于监听“关卡内物件/造物等实体被销毁”的广播语义；
    - 该事件仅在【关卡】实体上可触发；若节点图挂载在其他实体上等同于无效；
    - 因此它不能与“要求挂载在其他实体类型上才能触发/生效”的节点放在同一个节点图里，
      否则同一份节点图无法同时满足多种挂载前提，属于结构性设计错误。
    """

    rule_id = "engine_code_entity_destroy_event_mount"
    category = "节点挂载"
    default_level = "warning"

    _DESTROY_EVENT_NAMES: Set[str] = {"实体销毁时"}
    _LEVEL_ENTITY_TYPE: str = "关卡"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        destroy_event_nodes = [
            node
            for node in graph_model.nodes.values()
            if (str(getattr(node, "category", "") or "") == "事件节点")
            and (str(getattr(node, "title", "") or "").strip() in self._DESTROY_EVENT_NAMES)
        ]
        if not destroy_event_nodes:
            return []

        issues: List[EngineIssue] = []

        # 1) 立即提醒：该事件仅在关卡实体可触发（即便后续不构成冲突，也要明确告知语义）
        #
        # 允许作者在节点图 docstring 中显式声明挂载目标，以消除重复提醒噪声：
        # - mount_entity_type: 关卡
        # - owner_entity_type: 关卡
        # - mount_entity: 关卡
        #
        # 注意：即使声明了挂载目标，也仍然会继续执行“同图冲突检测”（error）。
        declared_mount_entity_type = ""
        tree = get_cached_module(ctx)
        docstring = ast.get_docstring(tree) or ""
        for raw_line in str(docstring).splitlines():
            line = str(raw_line).strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            normalized_key = key.strip().lower()
            if normalized_key in {"mount_entity_type", "owner_entity_type", "mount_entity"}:
                declared_mount_entity_type = value.strip()
                break

        should_emit_level_only_warning = True
        if declared_mount_entity_type:
            normalized_mount = declared_mount_entity_type.strip()
            if normalized_mount in {self._LEVEL_ENTITY_TYPE, f"{self._LEVEL_ENTITY_TYPE}实体"}:
                should_emit_level_only_warning = False

        restriction = NODE_ENTITY_RESTRICTIONS.get("实体销毁时", {})
        reference = str(restriction.get("line_ref") or "").strip() or None
        if should_emit_level_only_warning:
            for destroy_node in destroy_event_nodes:
                span = _span_for_graph_nodes(graph_model, [destroy_node.id])
                issues.append(
                    EngineIssue(
                        level="warning",
                        category=self.category,
                        code="CODE_ENTITY_DESTROY_EVENT_LEVEL_ONLY",
                        message=(
                            "检测到使用事件节点【实体销毁时】。\n"
                            "- 该事件：关卡内物件和造物被销毁时触发\n"
                            "- 限制：仅在【关卡】实体上可以触发；节点图挂载在其他实体上不会触发\n"
                            "建议：请确认该节点图的挂载目标为关卡实体；若需要通知玩家/角色等，请由关卡节点图通过信号/变量转发。"
                        ),
                        file=str(ctx.file_path),
                        line_span=span,
                        node_id=str(getattr(destroy_node, "id", "") or "") or None,
                        reference=reference,
                        detail={
                            "event_name": "实体销毁时",
                            "required_entity_type": self._LEVEL_ENTITY_TYPE,
                            "declared_mount_entity_type": declared_mount_entity_type or None,
                        },
                    )
                )

        # 2) 冲突检测：当节点图包含【实体销毁时】时，整张图必须能够挂载在关卡实体上。
        #    因此任何“已知挂载限制”且不能挂在关卡上的节点，都会与该事件构成同图冲突。
        incompatible_nodes: List[Tuple[str, str]] = []
        incompatible_node_ids: List[str] = []
        for node in graph_model.nodes.values():
            node_title = str(getattr(node, "title", "") or "").strip()
            if not node_title:
                continue
            if node_title not in NODE_ENTITY_RESTRICTIONS:
                continue
            can_mount, error_msg = can_node_mount_on_entity(node_title, self._LEVEL_ENTITY_TYPE)
            if can_mount:
                continue
            incompatible_nodes.append((node_title, error_msg))
            incompatible_node_ids.append(str(getattr(node, "id", "") or ""))

        if not incompatible_nodes:
            return issues

        # 去重（保持稳定顺序）
        unique_titles: List[str] = []
        seen_titles: Set[str] = set()
        for node_title, _ in incompatible_nodes:
            if node_title in seen_titles:
                continue
            seen_titles.add(node_title)
            unique_titles.append(node_title)

        related_node_ids: List[str] = []
        related_node_ids.extend([str(getattr(n, "id", "") or "") for n in destroy_event_nodes])
        related_node_ids.extend([node_id for node_id in incompatible_node_ids if node_id])
        span = _span_for_graph_nodes(graph_model, related_node_ids[:12])

        issues.append(
            EngineIssue(
                level="error",
                category=self.category,
                code="CODE_ENTITY_DESTROY_EVENT_MOUNT_CONFLICT",
                message=(
                    "节点图同时包含【实体销毁时】以及与【关卡】实体挂载不兼容的节点，属于结构性冲突：\n"
                    f"- 冲突节点：{', '.join(unique_titles)}\n"
                    "原因：同一节点图只能挂载在一种实体类型上；【实体销毁时】要求挂载在关卡实体，"
                    "而上述节点要求挂载在其他实体类型才会触发/生效，因此它们不能放在同一张节点图中。\n"
                    "修复建议：将【实体销毁时】相关逻辑拆分到关卡实体节点图；需要与玩家/角色/物件/造物交互时，"
                    "请通过信号系统或自定义变量等方式进行转发与同步。"
                ),
                file=str(ctx.file_path),
                line_span=span,
                reference=reference,
                detail={
                    "required_entity_type": self._LEVEL_ENTITY_TYPE,
                    "conflicting_nodes": list(unique_titles),
                    "conflicting_node_details": [
                        {"node_name": name, "mount_error": msg} for name, msg in incompatible_nodes
                    ],
                },
            )
        )

        return issues













