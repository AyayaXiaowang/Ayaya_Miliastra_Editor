from __future__ import annotations

from typing import Mapping


def _collect_used_signal_specs_from_graph_payload(
    *,
    graph_payload: object,
    signal_params_by_name: Mapping[str, list[dict[str, object]]],
    composite_mgr: object | None,
    composite_loaded: dict[str, object],
) -> list[dict[str, object]]:
    """
    从 GraphModel.payload 中收集“本图用到的信号规格”（用于构造自包含信号 node_def bundle）。

    约束：
    - 仅处理“信号名为字符串常量”的信号节点（动态信号名不做自包含）。
    - 支持递归：若图内包含复合节点实例，会继续遍历其子图 payload。
    """
    from ugc_file_tools.node_graph_semantics.var_base import map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id

    used_specs: list[dict[str, object]] = []
    used_names: set[str] = set()

    queue_graph_payloads: list[dict[str, object]] = []
    if isinstance(graph_payload, dict):
        queue_graph_payloads.append(dict(graph_payload))

    visited_composites: set[str] = set()

    while queue_graph_payloads:
        payload_obj = queue_graph_payloads.pop(0)
        nodes_value = payload_obj.get("nodes")
        if not isinstance(nodes_value, list):
            continue

        for n in nodes_value:
            if not isinstance(n, dict):
                continue

            # 递归：复合节点子图（若未提供 composite_mgr，则跳过递归）
            composite_id = str(n.get("composite_id") or "").strip()
            if composite_mgr is not None and composite_id != "" and composite_id not in visited_composites:
                visited_composites.add(composite_id)
                if composite_id not in composite_loaded:
                    load_ok = getattr(composite_mgr, "load_subgraph_if_needed")(composite_id)
                    if not load_ok:
                        raise ValueError(f"复合节点子图加载失败：composite_id={composite_id!r}")
                    composite_obj = getattr(composite_mgr, "get_composite_node")(composite_id)
                    if composite_obj is None:
                        raise ValueError(f"未找到复合节点定义：composite_id={composite_id!r}")
                    composite_loaded[composite_id] = composite_obj
                composite_obj2 = composite_loaded.get(composite_id)
                sub_graph = getattr(composite_obj2, "sub_graph", None)
                if isinstance(sub_graph, dict):
                    queue_graph_payloads.append(dict(sub_graph))

            # 本层：信号节点（仅处理“信号名为字符串常量”的情况；动态信号名不做自包含）
            title = str(n.get("title") or "").strip()
            if title not in {"发送信号", "监听信号", "向服务器节点图发送信号"}:
                continue
            input_constants = n.get("input_constants")
            if not isinstance(input_constants, dict):
                continue
            sig_name = input_constants.get("信号名")
            if not isinstance(sig_name, str) or str(sig_name).strip() == "":
                continue
            sig = str(sig_name).strip()
            if sig in used_names:
                continue
            used_names.add(sig)

            params = signal_params_by_name.get(sig)
            if params is None:
                # fallback：从节点端口类型推断参数列表（排除 流程/信号名/固定输出）
                inferred: list[dict[str, object]] = []
                if title in {"发送信号", "向服务器节点图发送信号"}:
                    inputs = n.get("inputs")
                    input_types = n.get("input_port_types")
                    if not isinstance(input_types, dict):
                        input_types = n.get("effective_input_types")
                    if isinstance(inputs, list) and isinstance(input_types, dict):
                        for p in inputs:
                            pn = str(p or "").strip()
                            if pn in {"流程入", "信号名"} or pn == "":
                                continue
                            type_text = input_types.get(pn)
                            if not isinstance(type_text, str) or type_text.strip() == "":
                                continue
                            vt = _map_server_port_type_to_var_type_id(str(type_text))
                            inferred.append({"param_name": pn, "type_id": int(vt)})
                elif title == "监听信号":
                    outputs = n.get("outputs")
                    output_types = n.get("output_port_types")
                    if not isinstance(output_types, dict):
                        output_types = n.get("effective_output_types")
                    fixed = {"流程出", "事件源实体", "事件源GUID", "信号来源实体"}
                    if isinstance(outputs, list) and isinstance(output_types, dict):
                        for p in outputs:
                            pn = str(p or "").strip()
                            if pn in fixed or pn == "":
                                continue
                            type_text = output_types.get(pn)
                            if not isinstance(type_text, str) or type_text.strip() == "":
                                continue
                            vt = _map_server_port_type_to_var_type_id(str(type_text))
                            inferred.append({"param_name": pn, "type_id": int(vt)})
                params = inferred

            used_specs.append({"signal_name": sig, "params": list(params)})

    return used_specs


# ---------------------------------------------------------------------------
# Public API (no leading underscores)
#
# Import policy: cross-module imports must not import underscored private names.


def collect_used_signal_specs_from_graph_payload(
    *,
    graph_payload: object,
    signal_params_by_name: Mapping[str, list[dict[str, object]]],
    composite_mgr: object | None,
    composite_loaded: dict[str, object],
) -> list[dict[str, object]]:
    return _collect_used_signal_specs_from_graph_payload(
        graph_payload=graph_payload,
        signal_params_by_name=signal_params_by_name,
        composite_mgr=composite_mgr,
        composite_loaded=composite_loaded,
    )
