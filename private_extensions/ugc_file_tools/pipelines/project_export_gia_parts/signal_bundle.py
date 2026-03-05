from __future__ import annotations


def build_per_graph_signal_bundle(
    *,
    shared_signal_bundle: object | None,
    used_signal_names: set[str],
) -> dict[str, object]:
    """
    从共享自包含信号 bundle 中按“本图用到的信号名集合”裁剪出：
    - 映射 dict（signal_name -> node_def_id / port indices / var type ids）
    - dependencies GraphUnits（仅本图所需的 node_def GraphUnits）
    - relatedIds（同上）
    """
    used_signal_names2 = {str(x).strip() for x in used_signal_names if str(x).strip() != ""}

    # per-graph signal bundle（从共享 bundle 按 node_def_id 过滤出本图所需的 3 类 node_def 单元）
    signal_send_node_def_id_by_signal_name: dict[str, int] | None = None
    signal_send_signal_name_port_index_by_signal_name: dict[str, int] | None = None
    signal_send_param_port_indices_by_signal_name: dict[str, list[int]] | None = None
    signal_send_param_var_type_ids_by_signal_name: dict[str, list[int]] | None = None
    listen_node_def_id_by_signal_name: dict[str, int] | None = None
    listen_signal_name_port_index_by_signal_name: dict[str, int] | None = None
    listen_param_port_indices_by_signal_name: dict[str, list[int]] | None = None
    extra_dependency_graph_units: list[dict[str, object]] | None = None
    graph_related_ids: list[dict[str, object]] | None = None

    if shared_signal_bundle is not None and used_signal_names2:
        needed_node_def_ids: set[int] = set()
        for sn in sorted(used_signal_names2):
            base_id = shared_signal_bundle.send_node_def_id_by_signal_name.get(str(sn))
            if isinstance(base_id, int) and int(base_id) > 0:
                needed_node_def_ids.add(int(base_id))
                needed_node_def_ids.add(int(base_id) + 1)
                needed_node_def_ids.add(int(base_id) + 2)

        # mapping dicts：仅保留本图用到的信号名
        signal_send_node_def_id_by_signal_name = {
            k: int(v)
            for k, v in shared_signal_bundle.send_node_def_id_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, int)
        }
        signal_send_signal_name_port_index_by_signal_name = {
            k: int(v)
            for k, v in shared_signal_bundle.send_signal_name_port_index_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, int)
        }
        signal_send_param_port_indices_by_signal_name = {
            k: [int(x) for x in v if isinstance(x, int)]
            for k, v in shared_signal_bundle.send_param_port_indices_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, list)
        }
        signal_send_param_var_type_ids_by_signal_name = {
            k: [int(x) for x in v if isinstance(x, int)]
            for k, v in shared_signal_bundle.send_param_var_type_ids_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, list)
        }
        listen_node_def_id_by_signal_name = {
            k: int(v)
            for k, v in shared_signal_bundle.listen_node_def_id_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, int)
        }
        listen_signal_name_port_index_by_signal_name = {
            k: int(v)
            for k, v in shared_signal_bundle.listen_signal_name_port_index_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, int)
        }
        listen_param_port_indices_by_signal_name = {
            k: [int(x) for x in v if isinstance(x, int)]
            for k, v in shared_signal_bundle.listen_param_port_indices_by_signal_name.items()
            if str(k) in used_signal_names2 and isinstance(v, list)
        }

        # dependencies + relatedIds：按 node_def_id 过滤（只保留本图用到的信号）
        deps: list[dict[str, object]] = []
        for unit in list(shared_signal_bundle.dependency_units):
            if not isinstance(unit, dict):
                continue
            unit_id = unit.get("1")
            if not isinstance(unit_id, dict):
                continue
            rid_id = unit_id.get("4")
            if isinstance(rid_id, int) and int(rid_id) in needed_node_def_ids:
                deps.append(dict(unit))
        extra_dependency_graph_units = deps

        rids: list[dict[str, object]] = []
        for rid in list(shared_signal_bundle.related_ids):
            if not isinstance(rid, dict):
                continue
            rid_id = rid.get("4")
            if isinstance(rid_id, int) and int(rid_id) in needed_node_def_ids:
                rids.append({"2": int(rid.get("2") or 0), "4": int(rid_id)})
        graph_related_ids = rids

    return {
        "signal_send_node_def_id_by_signal_name": signal_send_node_def_id_by_signal_name,
        "signal_send_signal_name_port_index_by_signal_name": signal_send_signal_name_port_index_by_signal_name,
        "signal_send_param_port_indices_by_signal_name": signal_send_param_port_indices_by_signal_name,
        "signal_send_param_var_type_ids_by_signal_name": signal_send_param_var_type_ids_by_signal_name,
        "listen_node_def_id_by_signal_name": listen_node_def_id_by_signal_name,
        "listen_signal_name_port_index_by_signal_name": listen_signal_name_port_index_by_signal_name,
        "listen_param_port_indices_by_signal_name": listen_param_port_indices_by_signal_name,
        "extra_dependency_graph_units": extra_dependency_graph_units,
        "graph_related_ids": graph_related_ids,
    }

