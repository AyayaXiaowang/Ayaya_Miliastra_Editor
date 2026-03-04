from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ugc_file_tools.var_type_map import try_map_var_type_id_to_server_port_type_text as _try_map_var_type_id_to_type_text


def _infer_output_port_type_by_src_node_and_port(
    *,
    edges: List[Dict[str, Any]],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
) -> Dict[Tuple[str, str], str]:
    """
    无样本节点的输出端口类型回退推断：
    - 从连线的 dst 输入端口类型（优先 `input_port_types`，其次 `effective_input_types` 快照）反推出 src 输出端口类型；
    - 仅当同一 (src_node,src_port) 的候选类型唯一时才采纳。
    """
    inferred_output_port_type_by_src_node_and_port: Dict[Tuple[str, str], str] = {}
    output_type_candidates: Dict[Tuple[str, str], set[str]] = {}

    def _infer_scalar_port_type_text_from_raw_constant(raw_value: Any) -> str:
        """
        从 GraphModel input_constants 的 raw 值推断“可用于类型反推”的端口类型文本（仅用于兜底推断）。

        约定：
        - 字符串常量一律视为“字符串”，避免把 "123" 误判为整数；
        - ui_key:/ui: 占位符视为“数值语义”，按整数处理（与写回侧 resolve_server_var_type_int_for_port 保持一致口径）；
        - 仅覆盖基础标量（不在此处推断列表/字典/结构体）。
        """
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered.startswith("ui_key:") or lowered.startswith("ui:"):
                return "整数"
            return "字符串"
        if isinstance(raw_value, bool):
            return "布尔值"
        if isinstance(raw_value, int):
            return "整数"
        if isinstance(raw_value, float):
            return "浮点数"
        return ""

    def _get_concrete_dst_input_type_text_for_inference(dst_payload: Dict[str, Any], dst_port: str) -> str:
        """
        从 dst 节点 payload 中提取“可用于推断的输入端口具体类型文本”。

        背景：
        - GraphModel(JSON) 在不同链路中可能只携带 `effective_input_types`（graph_cache 快照）而缺失 `input_port_types`；
        - 若只读取 `input_port_types`，会导致 inferred_out_type_text 缺失，从而让部分泛型输出端口推断退化。

        策略：
        - 优先 `input_port_types`（工具链 enrich 后的具体类型）
        - 其次 `effective_input_types`（GraphModel 快照）
        - 最后 `input_port_declared_types`（固定类型端口仍可提供证据；泛型会被过滤掉）
        """
        port = str(dst_port or "").strip()
        if port == "":
            return ""
        for key in ("input_port_types", "effective_input_types", "input_port_declared_types"):
            type_map = dst_payload.get(key)
            if not isinstance(type_map, dict):
                continue
            raw = type_map.get(port)
            if not isinstance(raw, str):
                continue
            text = str(raw).strip()
            if (not text) or text == "流程" or ("泛型" in text):
                continue
            return text

        # 兜底：字典(K/V)节点的 “字典” 端口常常停留在 “泛型字典”，无法直接用于反推上游输出端口类型。
        #
        # 但在大量真实图里，键/值会以常量形式出现（尤其是 UI 文本字典），这已经足够推断出别名字典(K,V)，
        # 进而避免上游【获取自定义变量】等泛型输出端口回退到 NodeEditorPack 默认（常见为整数）并写坏 `.gil`。
        #
        # 策略：
        # - 仅在 port=="字典" 且同时存在 “键/值” 端口时启用
        # - 键/值优先读 typed 快照；缺失时用常量 raw 值推断基础标量类型（字符串常量一律视为字符串）
        if port == "字典":
            inputs = dst_payload.get("inputs")
            has_key = isinstance(inputs, list) and "键" in [str(x) for x in inputs]
            has_val = isinstance(inputs, list) and "值" in [str(x) for x in inputs]
            if bool(has_key) and bool(has_val):
                key_text = _get_concrete_dst_input_type_text_for_inference(dst_payload, "键")
                val_text = _get_concrete_dst_input_type_text_for_inference(dst_payload, "值")

                input_constants = dst_payload.get("input_constants")
                if not key_text and isinstance(input_constants, dict) and "键" in input_constants:
                    key_text = _infer_scalar_port_type_text_from_raw_constant(input_constants.get("键"))
                if not val_text and isinstance(input_constants, dict) and "值" in input_constants:
                    val_text = _infer_scalar_port_type_text_from_raw_constant(input_constants.get("值"))

                if key_text and val_text:
                    # 统一用 “键类型_值类型字典” 作为别名字典文本（解析器兼容 "-" / "_" / "字典(→)" 三种形态）。
                    return f"{str(key_text).strip()}_{str(val_text).strip()}字典"
        return ""

    def _get_concrete_src_output_type_text_for_inference(src_payload: Dict[str, Any], src_port: str) -> str:
        """
        优先使用 src 自身的有效类型快照（output_port_types/effective_output_types），只有在缺失/仍为泛型时才回退到“从 dst 反推”。

        目的：
        - 写回/导出链路已经通过 EffectivePortTypeResolver enrich 得到 output_port_types；
        - 反推仅用于“极端裁剪/缺字段输入”的补洞，不能覆盖 effective，否则容易引入 NEP 默认类型污染。
        """
        port = str(src_port or "").strip()
        if port == "":
            return ""
        for key in ("output_port_types", "effective_output_types", "output_port_declared_types"):
            type_map = src_payload.get(key)
            if not isinstance(type_map, dict):
                continue
            raw = type_map.get(port)
            if not isinstance(raw, str):
                continue
            text = str(raw).strip()
            if (not text) or text == "流程" or ("泛型" in text):
                continue
            return text
        return ""

    for edge in list(edges):
        if not isinstance(edge, dict):
            continue
        src_node = str(edge.get("src_node") or "")
        dst_node = str(edge.get("dst_node") or "")
        src_port = str(edge.get("src_port") or "")
        dst_port = str(edge.get("dst_port") or "")
        if src_node == "" or dst_node == "" or src_port == "" or dst_port == "":
            continue
        src_payload = graph_node_by_graph_node_id.get(src_node)
        if isinstance(src_payload, dict):
            src_type_text = _get_concrete_src_output_type_text_for_inference(src_payload, src_port)
            if src_type_text != "":
                output_type_candidates.setdefault((src_node, src_port), set()).add(str(src_type_text))
                continue
        dst_payload = graph_node_by_graph_node_id.get(dst_node)
        if not isinstance(dst_payload, dict):
            continue
        dst_type_text = _get_concrete_dst_input_type_text_for_inference(dst_payload, dst_port)
        if dst_type_text == "":
            continue
        output_type_candidates.setdefault((src_node, src_port), set()).add(str(dst_type_text))
    for key, candidates in output_type_candidates.items():
        if len(candidates) == 1:
            inferred_output_port_type_by_src_node_and_port[key] = next(iter(candidates))
    return inferred_output_port_type_by_src_node_and_port


# ---------------------------------------------------------------------------
# Public API (no leading underscores)
#
# Import policy: cross-module imports must not import underscored private names.


def infer_output_port_type_by_src_node_and_port(
    *,
    edges: List[Dict[str, Any]],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
) -> Dict[Tuple[str, str], str]:
    return _infer_output_port_type_by_src_node_and_port(
        edges=edges,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
    )

