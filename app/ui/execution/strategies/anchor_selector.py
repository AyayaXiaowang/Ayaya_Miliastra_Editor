# -*- coding: utf-8 -*-
"""
锚点选择器：从步骤列表中选择合适的锚点节点用于坐标校准。

职责：
    - 优先选择创建类步骤的节点
    - 多层退化策略：创建 → 连接 → 合并连接 → 参数配置
    - 返回锚点信息与跳过标记
"""

from __future__ import annotations

from engine.graph.common import (
    get_builtin_anchor_titles_for_client_graph,
)


class AnchorInfo:
    """锚点信息封装"""
    def __init__(self, title: str | None = None, prog_pos: tuple[float, float] | None = None,
                 node_id: str | None = None, skip_first_todo_id: str | None = None):
        self.title = title
        self.prog_pos = prog_pos
        self.node_id = node_id
        self.skip_first_todo_id = skip_first_todo_id

    @property
    def is_valid(self) -> bool:
        """是否找到有效锚点"""
        return self.title is not None and self.prog_pos is not None


class AnchorSelector:
    """锚点选择器：多层退化策略选择锚点节点"""

    def __init__(self, graph_model):
        self.graph_model = graph_model

    def select_anchor(self, steps: list) -> AnchorInfo:
        """从步骤列表选择锚点

        Args:
            steps: TodoItem 列表

        Returns:
            AnchorInfo: 锚点信息（可能为空）
        """
        # 策略0: client 图的“模板锚点节点”优先（这些节点在新建时由编辑器自动生成）
        anchor_info = self._select_from_builtin_client_graph_anchor()
        if anchor_info.is_valid:
            return anchor_info

        # 策略1: 优先取创建类步骤节点
        anchor_info = self._select_from_create_steps(steps)
        if anchor_info.is_valid:
            return anchor_info

        # 策略2: 退化到连接步骤的源/目标节点
        anchor_info = self._select_from_connect_steps(steps)
        if anchor_info.is_valid:
            return anchor_info

        # 策略3: 再退化到合并连线步骤
        anchor_info = self._select_from_merged_connect_steps(steps)
        if anchor_info.is_valid:
            return anchor_info

        # 策略4: 三次退化到参数配置/动态端口步骤
        anchor_info = self._select_from_config_steps(steps)
        return anchor_info

    def _select_from_builtin_client_graph_anchor(self) -> AnchorInfo:
        """策略0：优先使用 client 图在“新建时默认存在”的锚点节点。

        约定：
        - 技能节点图：节点图开始
        - 整数过滤器节点图：节点图结束（整数）
        - 布尔过滤器节点图：节点图结束（布尔型）
        """
        model = self.graph_model
        meta = getattr(model, "metadata", None) or {}
        graph_type = str(meta.get("graph_type", "") or "").strip().lower()
        if graph_type != "client":
            return AnchorInfo()
        folder_path = str(meta.get("folder_path", "") or "")
        anchor_titles = get_builtin_anchor_titles_for_client_graph(folder_path=folder_path)
        if not anchor_titles:
            return AnchorInfo()

        best_node_id: str | None = None
        best_node = None
        for expected_title in anchor_titles:
            candidates: list[tuple[str, object]] = []
            for node_id, node in (getattr(model, "nodes", {}) or {}).items():
                if getattr(node, "title", "") == expected_title:
                    candidates.append((str(node_id), node))
            if not candidates:
                continue

            def _pos_key(pair: tuple[str, object]) -> tuple[float, float, str]:
                nid, node_obj = pair
                pos = getattr(node_obj, "pos", (0.0, 0.0))
                x_val = float(pos[0]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
                y_val = float(pos[1]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
                return (y_val, x_val, nid)

            best_node_id, best_node = sorted(candidates, key=_pos_key)[0]
            break

        if not best_node_id or best_node is None:
            return AnchorInfo()
        return AnchorInfo(
            title=str(getattr(best_node, "title", "") or ""),
            prog_pos=getattr(best_node, "pos", None),
            node_id=str(best_node_id),
        )

    def _select_from_create_steps(self, steps: list) -> AnchorInfo:
        """策略1: 从创建类步骤选择锚点"""
        for step in steps:
            info = step.detail_info
            step_type = info.get("type")
            if step_type in ("graph_create_node", "graph_create_and_connect"):
                node_id = info.get("node_id")
                if node_id and node_id in self.graph_model.nodes:
                    node = self.graph_model.nodes[node_id]
                    return AnchorInfo(
                        title=node.title,
                        prog_pos=node.pos,
                        node_id=node_id,
                        skip_first_todo_id=step.todo_id
                    )
        return AnchorInfo()

    def _select_from_connect_steps(self, steps: list) -> AnchorInfo:
        """策略2: 从连接步骤选择源或目标节点作为锚点"""
        for step in steps:
            info = step.detail_info
            if info.get("type") == "graph_connect":
                src_id = info.get("src_node") or info.get("prev_node_id")
                dst_id = info.get("dst_node") or info.get("node_id")
                pick_id = None
                if src_id and src_id in self.graph_model.nodes:
                    pick_id = src_id
                elif dst_id and dst_id in self.graph_model.nodes:
                    pick_id = dst_id
                if pick_id:
                    node = self.graph_model.nodes[pick_id]
                    return AnchorInfo(title=node.title, prog_pos=node.pos)
        return AnchorInfo()

    def _select_from_merged_connect_steps(self, steps: list) -> AnchorInfo:
        """策略3: 从合并连线步骤选择节点作为锚点"""
        for step in steps:
            info = step.detail_info
            if info.get("type") == "graph_connect_merged":
                n1 = info.get("node1_id")
                n2 = info.get("node2_id")
                pick_id = None
                if n1 and n1 in self.graph_model.nodes:
                    pick_id = n1
                elif n2 and n2 in self.graph_model.nodes:
                    pick_id = n2
                if pick_id:
                    node = self.graph_model.nodes[pick_id]
                    return AnchorInfo(title=node.title, prog_pos=node.pos)
        return AnchorInfo()

    def _select_from_config_steps(self, steps: list) -> AnchorInfo:
        """策略4: 从参数配置/动态端口步骤选择目标节点作为锚点"""
        for step in steps:
            info = step.detail_info
            if info.get("type") in (
                "graph_config_node", "graph_config_node_merged",
                "graph_add_variadic_inputs", "graph_add_dict_pairs", "graph_add_branch_outputs",
            ):
                node_id = info.get("node_id")
                if node_id and node_id in self.graph_model.nodes:
                    node = self.graph_model.nodes[node_id]
                    return AnchorInfo(title=node.title, prog_pos=node.pos)
        return AnchorInfo()

