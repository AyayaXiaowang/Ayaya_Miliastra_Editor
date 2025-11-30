# -*- coding: utf-8 -*-
"""
步骤汇总构建器：根据步骤信息生成可读的摘要文本。

职责：
    - 解析 step_info 并构造描述性摘要
    - 支持所有步骤类型（创建、连接、配置、动态端口等）
    - 从 GraphModel 获取节点标题等辅助信息
"""


class StepSummaryBuilder:
    """步骤汇总构建器：将步骤信息转换为可读文本"""

    def __init__(self, graph_model):
        self.graph_model = graph_model

    def build_summary(self, step_info: dict) -> str:
        """构造一步执行摘要文本，明确节点/端口/数量等关键信息

        Args:
            step_info: 步骤详情字典

        Returns:
            str: 摘要文本
        """
        step_type = step_info.get("type")
        if step_type == "graph_create_node":
            return self._build_create_node_summary(step_info)
        if step_type == "graph_create_and_connect":
            return self._build_create_and_connect_summary(step_info)
        if step_type == "graph_connect":
            return self._build_connect_summary(step_info)
        if step_type == "graph_connect_merged":
            return self._build_connect_merged_summary(step_info)
        if step_type == "graph_config_node_merged":
            return self._build_config_node_merged_summary(step_info)
        if step_type == "graph_set_port_types_merged":
            return self._build_set_port_types_merged_summary(step_info)
        if step_type == "graph_add_variadic_inputs":
            return self._build_add_variadic_inputs_summary(step_info)
        if step_type == "graph_add_dict_pairs":
            return self._build_add_dict_pairs_summary(step_info)
        if step_type == "graph_add_branch_outputs":
            return self._build_add_branch_outputs_summary(step_info)
        if step_type == "graph_config_branch_outputs":
            return self._build_config_branch_outputs_summary(step_info)
        if step_type == "graph_bind_signal":
            return self._build_bind_signal_summary(step_info)
        if step_type == "graph_create_and_connect_data":
            return self._build_create_and_connect_data_summary(step_info)
        return f"步骤类型：{step_type}"

    def _build_create_node_summary(self, step_info: dict) -> str:
        """创建节点步骤摘要"""
        node_id = step_info.get("node_id")
        title = step_info.get("node_title")
        if not title and node_id and node_id in self.graph_model.nodes:
            title = self.graph_model.nodes[node_id].title
        return f"创建节点：{title if title else ''} (id={node_id})"

    def _build_create_and_connect_summary(self, step_info: dict) -> str:
        """连线并创建步骤摘要"""
        prev_title = step_info.get("prev_node_title") or ""
        node_title = step_info.get("node_title") or ""
        edge_id = step_info.get("edge_id")
        return f"连线并创建：{prev_title} → {node_title} (edge={edge_id})"

    def _build_connect_summary(self, step_info: dict) -> str:
        """连接步骤摘要"""
        src_id = step_info.get("src_node") or step_info.get("prev_node_id")
        dst_id = step_info.get("dst_node") or step_info.get("node_id")
        src_title = step_info.get("node1_title") or ""
        dst_title = step_info.get("node2_title") or ""
        if not src_title and src_id and src_id in self.graph_model.nodes:
            src_title = self.graph_model.nodes[src_id].title
        if not dst_title and dst_id and dst_id in self.graph_model.nodes:
            dst_title = self.graph_model.nodes[dst_id].title
        src_port = step_info.get("src_port")
        dst_port = step_info.get("dst_port")
        left = f"{src_title}.{src_port}" if src_title and src_port else (src_title or str(src_id or ""))
        right = f"{dst_title}.{dst_port}" if dst_title and dst_port else (dst_title or str(dst_id or ""))
        edge_id = step_info.get("edge_id")
        return f"连接：{left} → {right}" + (f" (edge={edge_id})" if edge_id else "")

    def _build_connect_merged_summary(self, step_info: dict) -> str:
        """合并连接步骤摘要"""
        n1_title = step_info.get("node1_title") or ""
        n2_title = step_info.get("node2_title") or ""
        count = len(step_info.get("edges") or [])
        return f"连接：{n1_title} → {n2_title}（{count}条）"

    def _build_config_node_merged_summary(self, step_info: dict) -> str:
        """参数配置步骤摘要"""
        node_title = step_info.get("node_title") or ""
        cnt = len(step_info.get("params") or [])
        return f"配置参数：{node_title}（{cnt}项）"

    def _build_set_port_types_merged_summary(self, step_info: dict) -> str:
        """设置端口类型步骤摘要"""
        node_title = step_info.get("node_title") or ""
        cnt = len(step_info.get("params") or [])
        return f"设置端口类型：{node_title}（{cnt}项）"

    def _build_add_variadic_inputs_summary(self, step_info: dict) -> str:
        """新增变参端口步骤摘要"""
        node_title = step_info.get("node_title") or ""
        cnt = int(step_info.get("add_count") or 0)
        return f"新增动态端口（变参）：{node_title} × {cnt}"

    def _build_add_dict_pairs_summary(self, step_info: dict) -> str:
        """新增字典键值端口步骤摘要"""
        node_title = step_info.get("node_title") or ""
        cnt = int(step_info.get("add_count") or 0)
        return f"新增动态端口（字典键值）：{node_title} × {cnt}"

    def _build_add_branch_outputs_summary(self, step_info: dict) -> str:
        """新增分支输出步骤摘要"""
        node_title = step_info.get("node_title") or ""
        cnt = int(step_info.get("add_count") or 0)
        return f"新增分支输出：{node_title} × {cnt}"

    def _build_config_branch_outputs_summary(self, step_info: dict) -> str:
        """配置分支输出步骤摘要"""
        node_title = step_info.get("node_title") or ""
        branches = step_info.get("branches") or []
        cnt = int(len(branches))
        return f"配置分支输出：{node_title}（{cnt}项）"

    def _build_bind_signal_summary(self, step_info: dict) -> str:
        """设置信号步骤摘要"""
        node_title = step_info.get("node_title") or ""
        signal_id = step_info.get("signal_id") or ""
        signal_name = step_info.get("signal_name") or ""
        param_names = step_info.get("signal_param_names") or []
        param_count = len(param_names) if isinstance(param_names, list) else 0

        parts = []
        if signal_name:
            parts.append(str(signal_name))
        if signal_id and signal_id not in parts:
            parts.append(str(signal_id))
        signal_label = " / ".join(parts)

        base = "设置信号"
        if node_title:
            base += f"：{node_title}"
        if signal_label:
            base += f" → {signal_label}"
        if param_count > 0:
            base += f"（{param_count} 个参数）"
        return base

    def _build_create_and_connect_data_summary(self, step_info: dict) -> str:
        """连线并创建数据节点步骤摘要"""
        data_title = step_info.get("data_node_title") or ""
        target_title = step_info.get("target_node_title") or ""
        edge_id = step_info.get("edge_id")
        return f"连线并创建数据：{data_title} → {target_title} (edge={edge_id})"

