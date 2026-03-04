from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_private_extensions_importable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = (repo_root / "private_extensions").resolve()
    if str(private_extensions_root) not in sys.path:
        sys.path.insert(0, str(private_extensions_root))


def _map_control_type_text_to_var_type_id(type_text: str) -> int:
    t = str(type_text or "").strip()
    if t in {"整数", "整数值", "int", "Int"}:
        return 3
    if t in {"字符串", "str", "Str"}:
        return 6
    # 多分支节点当前只支持 整数/字符串；测试侧默认按字符串兜底以避免误判为其它类型。
    return 6


def _map_list_var_type_id_for_control_vt(control_vt: int) -> int:
    if int(control_vt) == 3:
        return 8  # IntList
    return 11  # StrList


def test_gia_export_multibranch_cases_and_outflows_are_aligned(tmp_path: Path) -> None:
    """
    回归：导出 `.gia`（AssetBundle/NodeGraph）时，Multiple_Branches(type_id=3) 必须满足：

    - InParam(index=1) 为 cases 列表（L<R<T>>），其长度决定 outflows-1；
    - OutFlow 必须严格生成 1 + len(cases) 个（index=0..len(cases)），不得从 NodeEditorPack 画像补齐出“最大分支数”。
    """
    _ensure_private_extensions_importable()

    repo_root = Path(__file__).resolve().parents[2]
    graph_code_file = (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_踏板开关_信号广播.py"
    )

    from ugc_file_tools.commands.export_graph_model_json_from_graph_code import export_graph_model_json_from_graph_code
    from ugc_file_tools.gia_export.node_graph.asset_bundle_builder_graph_builder import (
        build_asset_bundle_message_from_graph_model_json,
    )
    from ugc_file_tools.gia_export.node_graph.asset_bundle_builder_types import GiaAssetBundleGraphExportHints

    # node_type_semantic_map.json: {type_id: {graph_generater_node_name, scope, ...}}
    node_type_semantic_map_path = (
        repo_root / "private_extensions" / "ugc_file_tools" / "graph_ir" / "node_type_semantic_map.json"
    )
    semantic_map = json.loads(node_type_semantic_map_path.read_text(encoding="utf-8"))
    node_type_id_by_title: dict[str, int] = {}
    for type_id_text, entry in (semantic_map or {}).items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("scope") or "").strip().lower() != "server":
            continue
        title = str(entry.get("graph_generater_node_name") or "").strip()
        if title == "":
            continue
        if str(type_id_text).strip().isdigit():
            node_type_id_by_title[title] = int(type_id_text)

    # ExportHints 需要的是 “NodeDef canonical key → node_type_id(int)” 映射，而不是 title。
    # 这里使用节点库把 name/title 反查到 canonical key，并仅保留 server 可用节点。
    from engine.nodes.node_registry import get_node_registry

    registry = get_node_registry(Path(repo_root), include_composite=True)
    node_library = registry.get_library()
    node_type_id_by_node_def_key: dict[str, int] = {}
    for _key, node_def in (node_library or {}).items():
        title = str(getattr(node_def, "name", "") or "").strip()
        if not title:
            continue
        if not bool(getattr(node_def, "is_available_in_scope", lambda _scope: True)("server")):
            continue
        type_id = node_type_id_by_title.get(title)
        if type_id is None:
            continue
        canonical_key = str(getattr(node_def, "canonical_key", "") or "").strip() or str(_key)
        if canonical_key:
            node_type_id_by_node_def_key.setdefault(canonical_key, int(type_id))

    report = export_graph_model_json_from_graph_code(
        graph_code_file=Path(graph_code_file),
        output_json_file=Path(tmp_path / "multibranch_cases.graph_model.json"),
        graph_generater_root=Path(repo_root),
    )
    exported_graph_model_json_path = Path(str(report["output_json"])).resolve()
    exported = json.loads(exported_graph_model_json_path.read_text(encoding="utf-8"))

    # export_graph_model_json_from_graph_code 的落盘格式以 `data` 为 GraphModel 主体（对齐缓存/导出链路）。
    graph_model = exported.get("data") if isinstance(exported.get("data"), dict) else exported
    nodes = graph_model.get("nodes") if isinstance(graph_model, dict) else None
    assert isinstance(nodes, list) and nodes, "graph_model.nodes missing"

    # 用 GraphModel（Graph_Generater 单一真源）推断 cases：
    # - cases = 动态 outflow 端口（排除 “默认”）
    multibranch_node = None
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if str(n.get("title") or "").strip() == "多分支":
            multibranch_node = n
            break
    assert isinstance(multibranch_node, dict), "expected at least one '多分支' node in template graph"

    out_ports = multibranch_node.get("outputs")
    assert isinstance(out_ports, list) and out_ports, "multibranch.outputs missing"
    out_types = multibranch_node.get("effective_output_types")
    assert isinstance(out_types, dict), "multibranch.effective_output_types missing"

    flow_out_ports = [str(p) for p in out_ports if str(out_types.get(str(p)) or "").strip() == "流程"]
    assert "默认" in flow_out_ports, "multibranch flow outputs should include '默认'"
    case_labels = [p for p in flow_out_ports if str(p).strip() != "默认"]
    expected_outflow_count = 1 + len(case_labels)
    assert expected_outflow_count >= 2, "template should have at least one non-default branch"

    in_types = multibranch_node.get("effective_input_types")
    assert isinstance(in_types, dict), "multibranch.effective_input_types missing"
    control_vt = _map_control_type_text_to_var_type_id(str(in_types.get("控制表达式") or ""))
    cases_vt = _map_list_var_type_id_for_control_vt(control_vt)

    meta = exported.get("metadata") if isinstance(exported.get("metadata"), dict) else {}
    graph_name = str(meta.get("graph_name") or exported.get("name") or exported.get("graph_name") or "untitled")
    graph_id_int = 0x40000001

    hints = GiaAssetBundleGraphExportHints(
        graph_id_int=int(graph_id_int),
        graph_name=str(graph_name),
        graph_scope="server",
        resource_class="ENTITY_NODE_GRAPH",
        graph_generater_root=Path(repo_root),
        node_type_id_by_node_def_key=node_type_id_by_node_def_key,
        export_uid=0,
        game_version="6.3.0",
        include_composite_nodes=False,
    )

    asset_bundle = build_asset_bundle_message_from_graph_model_json(graph_json_object=exported, hints=hints)
    primary = asset_bundle.get("1") or {}
    node_graph_container_inner = (primary.get("13") or {}).get("1") or {}
    node_graph = node_graph_container_inner.get("1") or {}
    exported_nodes = node_graph.get("3") or []
    assert isinstance(exported_nodes, list) and exported_nodes, "exported NodeGraph nodes missing"

    mb_instances = []
    for n in exported_nodes:
        if not isinstance(n, dict):
            continue
        locator = n.get("2") or {}
        if not isinstance(locator, dict):
            continue
        if int(locator.get("5") or 0) == 3:
            mb_instances.append(n)
    assert mb_instances, "expected at least one Multiple_Branches(node_id=3) node instance in exported graph"

    mb = mb_instances[0]
    pins = mb.get("4") or []
    assert isinstance(pins, list) and pins

    outflow_indices: set[int] = set()
    inparam_by_index: dict[int, dict] = {}
    for p in pins:
        if not isinstance(p, dict):
            continue
        sig = p.get("1") or {}
        if not isinstance(sig, dict):
            continue
        kind_int = int(sig.get("1") or 0)
        index_int = int(sig.get("2") or 0)
        if kind_int == 2:
            outflow_indices.add(index_int)
        elif kind_int == 3:
            inparam_by_index[index_int] = p

    assert outflow_indices == set(range(expected_outflow_count)), (
        "Multiple_Branches OUT_FLOW indices mismatch: "
        f"expected=0..{expected_outflow_count - 1} got={sorted(outflow_indices)}"
    )

    p0 = inparam_by_index.get(0)
    p1 = inparam_by_index.get(1)
    assert isinstance(p0, dict), "Multiple_Branches missing InParam index=0 (control expression)"
    assert isinstance(p1, dict), "Multiple_Branches missing InParam index=1 (cases)"

    assert int(p0.get("4") or 0) == int(control_vt)
    assert int(p1.get("4") or 0) == int(cases_vt)

    # 导出侧 message 为“protobuf-like string-key dict”，不直接复用解码侧的 extract_varbase_value（其输入为 int-key FieldMap）。
    # 这里用“包含性”做轻量契约断言：cases pin 必须携带 VarBase(field_3) 且包含所有 case label。
    var_base = p1.get("3")
    assert isinstance(var_base, dict) and var_base, "cases pin missing VarBase(field_3)"
    dumped = json.dumps(var_base, ensure_ascii=False)
    for label in list(case_labels):
        assert str(label) in dumped, f"cases VarBase does not contain label: {label!r}"

