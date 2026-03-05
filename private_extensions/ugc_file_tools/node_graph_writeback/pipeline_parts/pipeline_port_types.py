from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.graph.port_type_gap_report import build_port_type_gap_report
from ugc_file_tools.graph.port_types import standardize_graph_model_payload_inplace as _standardize_graph_model_payload_inplace


def _graph_model_missing_enriched_port_types(graph_model: Dict[str, Any]) -> bool:
    nodes = graph_model.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False
    for n in list(nodes):
        if not isinstance(n, dict):
            continue
        ipt = n.get("input_port_types")
        opt = n.get("output_port_types")
        if not isinstance(ipt, dict) or not isinstance(opt, dict):
            return True
    return False


def _ensure_graph_model_enriched_port_types_inplace(
    *,
    graph_model: Dict[str, Any],
    graph_variables: List[Dict[str, Any]],
    graph_generater_root: Path,
    scope: str,
) -> None:
    """
    写回前强制补齐 GraphModel(JSON) 的 `input_port_types/output_port_types`（有效类型快照），
    使写回链路不依赖 UI 预览态内存，且避免仅携带 `input_types/output_types` 时的字段形态分叉。
    """
    _standardize_graph_model_payload_inplace(
        graph_model_payload=graph_model,
        graph_variables=list(graph_variables),
        workspace_root=Path(graph_generater_root).resolve(),
        scope=str(scope),
        # 写回的正确性优先：即使已有快照也重新 enrich，避免历史/裁剪产物携带错误快照后被短路。
        force_reenrich=True,
        fill_missing_edge_ids=True,
    )


def _build_node_by_id(*, nodes: list[Any]) -> Dict[str, Dict[str, Any]]:
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for n in list(nodes):
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if nid:
            node_by_id[nid] = n
    return node_by_id


def _build_src_by_dst_and_port(*, edges_list: list[Any]) -> Dict[tuple[str, str], tuple[str, str]]:
    src_by_dst_and_port: Dict[tuple[str, str], tuple[str, str]] = {}
    for e in list(edges_list):
        if not isinstance(e, dict):
            continue
        dst = str(e.get("dst_node") or "").strip()
        dst_port = str(e.get("dst_port") or "").strip()
        src = str(e.get("src_node") or "").strip()
        src_port = str(e.get("src_port") or "").strip()
        if dst and dst_port and src and src_port:
            src_by_dst_and_port[(dst, dst_port)] = (src, src_port)
    return src_by_dst_and_port


def _pick_typed_dict_alias_from_node_port(
    *, node_payload: Dict[str, Any], port: str, is_input: bool, parse_typed_dict_alias: Any
) -> str:
    m = node_payload.get("input_port_types" if is_input else "output_port_types")
    if not isinstance(m, dict):
        return ""
    t = str(m.get(port) or "").strip()
    ok, _k, _v = parse_typed_dict_alias(t)
    return t if bool(ok) else ""


def _set_port_type_inplace(*, node_payload: Dict[str, Any], port: str, is_input: bool, type_text: str) -> None:
    key = "input_port_types" if bool(is_input) else "output_port_types"
    m = node_payload.get(key)
    if not isinstance(m, dict):
        m = {}
        node_payload[key] = m
    m[str(port)] = str(type_text)


def _maybe_infer_dict_alias_from_upstream_get_graph_variable(
    *,
    src_payload: Dict[str, Any],
    src_port: str,
    graph_variable_type_text_by_name: Dict[str, str],
    parse_typed_dict_alias: Any,
) -> str:
    src_title = str(src_payload.get("title") or "").strip()
    if src_title != "获取节点图变量" or str(src_port) != "变量值":
        return ""
    input_constants = src_payload.get("input_constants")
    if not isinstance(input_constants, dict):
        return ""
    var_name = input_constants.get("变量名")
    if not isinstance(var_name, str) or not var_name.strip():
        return ""
    gv_type = str(graph_variable_type_text_by_name.get(var_name.strip()) or "").strip()
    ok, _k, _v = parse_typed_dict_alias(gv_type)
    return gv_type if bool(ok) else ""


def _resolve_dict_alias_for_dict_mutation_node(
    *,
    node_id: str,
    node_payload: Dict[str, Any],
    node_by_id: Dict[str, Dict[str, Any]],
    src_by_dst_and_port: Dict[tuple[str, str], tuple[str, str]],
    graph_variable_type_text_by_name: Dict[str, str],
    parse_typed_dict_alias: Any,
) -> str:
    # dict type 真源优先级：
    # 1) 本节点 input_port_types['字典']（必须为别名字典）
    # 2) 上游连接 src 输出端口类型（必须为别名字典）
    # 3) 上游为【获取节点图变量】且其变量名命中 graph_variables 表
    dict_alias = _pick_typed_dict_alias_from_node_port(
        node_payload=node_payload, port="字典", is_input=True, parse_typed_dict_alias=parse_typed_dict_alias
    )
    if dict_alias:
        return dict_alias

    src = src_by_dst_and_port.get((node_id, "字典"))
    if not (isinstance(src, tuple) and len(src) == 2):
        return ""
    src_node_id, src_port = str(src[0]), str(src[1])
    src_payload = node_by_id.get(src_node_id)
    if not isinstance(src_payload, dict):
        return ""

    dict_alias = _pick_typed_dict_alias_from_node_port(
        node_payload=src_payload, port=str(src_port), is_input=False, parse_typed_dict_alias=parse_typed_dict_alias
    )
    if dict_alias:
        return dict_alias
    return _maybe_infer_dict_alias_from_upstream_get_graph_variable(
        src_payload=src_payload,
        src_port=str(src_port),
        graph_variable_type_text_by_name=graph_variable_type_text_by_name,
        parse_typed_dict_alias=parse_typed_dict_alias,
    )


def _apply_repaired_dict_mutation_port_types_inplace(
    *,
    node_payload: Dict[str, Any],
    title: str,
    dict_alias: str,
    key_type_text: str,
    value_type_text: str,
) -> None:
    # 修复并强制收敛：字典/键/值 端口类型必须一致
    _set_port_type_inplace(node_payload=node_payload, port="字典", is_input=True, type_text=dict_alias)
    _set_port_type_inplace(node_payload=node_payload, port="字典", is_input=False, type_text=dict_alias)
    if title in {"对字典设置或新增键值对", "对字典修改键值对"}:
        _set_port_type_inplace(node_payload=node_payload, port="键", is_input=True, type_text=str(key_type_text))
        _set_port_type_inplace(node_payload=node_payload, port="值", is_input=True, type_text=str(value_type_text))
    if title == "以键对字典移除键值对":
        _set_port_type_inplace(node_payload=node_payload, port="键", is_input=True, type_text=str(key_type_text))


def _repair_and_validate_dict_mutation_port_types_or_raise(
    *,
    graph_model: Dict[str, Any],
    graph_variable_type_text_by_name: Dict[str, str],
) -> None:
    """
    fail-closed：字典“原地修改”节点（K/V 双泛型）必须能得到明确的别名字典类型。
    """
    parse_typed_dict_alias = getattr(import_module("engine.type_registry"), "parse_typed_dict_alias")

    nodes = graph_model.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return
    edges = graph_model.get("edges")
    edges_list = edges if isinstance(edges, list) else []

    node_by_id = _build_node_by_id(nodes=nodes)
    src_by_dst_and_port = _build_src_by_dst_and_port(edges_list=edges_list)

    dict_mutation_titles = {
        "对字典设置或新增键值对",
        "以键对字典移除键值对",
        "清空字典",
        "对字典修改键值对",
    }

    for node_payload in list(nodes):
        if not isinstance(node_payload, dict):
            continue
        title = str(node_payload.get("title") or "").strip()
        if title not in dict_mutation_titles:
            continue
        node_id = str(node_payload.get("id") or "").strip()

        dict_alias = _resolve_dict_alias_for_dict_mutation_node(
            node_id=node_id,
            node_payload=node_payload,
            node_by_id=node_by_id,
            src_by_dst_and_port=src_by_dst_and_port,
            graph_variable_type_text_by_name=graph_variable_type_text_by_name,
            parse_typed_dict_alias=parse_typed_dict_alias,
        )

        ok, key_type_text, value_type_text = parse_typed_dict_alias(dict_alias)
        if not bool(ok):
            raise ValueError(
                "字典修改节点缺少可落地的别名字典类型（禁止回退写入）："
                f"title={title!r} node_id={node_id!r} dict_type={((node_payload.get('input_port_types') or {}).get('字典'))!r}"
            )

        _apply_repaired_dict_mutation_port_types_inplace(
            node_payload=node_payload,
            title=title,
            dict_alias=str(dict_alias),
            key_type_text=str(key_type_text),
            value_type_text=str(value_type_text),
        )


def _write_port_type_gap_report_and_fail_if_any_or_raise(
    *,
    graph_model: Dict[str, Any],
    graph_scope: str,
    graph_name: str,
    graph_id_int: int | None,
    output_gil_path: Path,
) -> str:
    report = build_port_type_gap_report(
        graph_model_payload=dict(graph_model),
        graph_scope=str(graph_scope),
        graph_name=str(graph_name),
        graph_id_int=(int(graph_id_int) if isinstance(graph_id_int, int) else None),
    )
    counts = report.get("counts") if isinstance(report, dict) else None
    if not isinstance(counts, dict):
        raise TypeError(f"invalid port type gap report: {type(report)!r}")
    total = int(counts.get("total") or 0)
    if total <= 0:
        return ""

    report_dir = (Path(output_gil_path).resolve().parent / "reports" / "port_type_gaps").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = sanitize_file_stem(str(graph_name))
    gid = int(graph_id_int) if isinstance(graph_id_int, int) else 0
    report_path = (report_dir / f"{str(graph_scope)}__{gid}__{safe_stem}.json").resolve()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    first_items: list[str] = []
    items = report.get("items") if isinstance(report, dict) else None
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            first_items.append(
                f"{str(it.get('severity') or '')}:{str(it.get('node_title') or '')}.{str(it.get('port_name') or '')} reason={str(it.get('reason') or '')}"
            )
            if len(first_items) >= 5:
                break
    raise ValueError(
        "端口类型缺口报告非空（写回禁止继续）："
        f"graph={str(graph_name)!r} scope={str(graph_scope)!r} total={int(total)} report_file={str(report_path)!r} first={first_items!r}"
    )

