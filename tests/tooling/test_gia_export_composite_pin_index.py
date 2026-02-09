from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_private_extensions_importable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = (repo_root / "private_extensions").resolve()
    if str(private_extensions_root) not in sys.path:
        sys.path.insert(0, str(private_extensions_root))


def test_gia_export_composite_node_pins_have_composite_pin_index() -> None:
    """
    回归：导出 `.gia`（AssetBundle/NodeGraph）时，调用复合节点（NodeKind=22001）的 pins 必须写入
    NodePin.compositePinIndex(field_7)，且其值应对齐对应 CompositeDef 的 pinIndex(field_8)。
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
        / "模板示例_多引脚_复合节点用法.py"
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
        output_json_file=Path("_pytest_composite_pin_index.graph_model.json"),
        graph_generater_root=Path(repo_root),
    )
    exported_graph_model_json_path = Path(str(report["output_json"])).resolve()
    exported = json.loads(exported_graph_model_json_path.read_text(encoding="utf-8"))

    meta = exported.get("metadata") if isinstance(exported.get("metadata"), dict) else {}
    graph_name = str(meta.get("graph_name") or exported.get("name") or exported.get("graph_name") or "untitled")
    # graph_id 在 graph_cache/result_data 中通常是字符串（如 server_xxx）；这里不依赖真实分配 id，
    # 只需确保 mask 属于 server 即可（与导出器的 scope 口径一致）。
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
        include_composite_nodes=True,
    )

    asset_bundle = build_asset_bundle_message_from_graph_model_json(graph_json_object=exported, hints=hints)

    primary = asset_bundle.get("1") or {}
    node_graph_container_inner = (primary.get("13") or {}).get("1") or {}
    node_graph = node_graph_container_inner.get("1") or {}
    nodes = node_graph.get("3") or []
    assert isinstance(nodes, list) and nodes, "graph nodes missing in exported asset bundle"

    composite_nodes = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        locator = n.get("2") or {}
        if not isinstance(locator, dict):
            continue
        if int(locator.get("3") or 0) == 22001:
            composite_nodes.append(n)
    assert composite_nodes, "expected at least one composite node (kind=22001) in exported graph"

    # Collect all CompositeDef pinIndex(field_8) for membership assertion.
    dep_units = asset_bundle.get("2") or []
    pin_index_pool: set[int] = set()
    if isinstance(dep_units, list):
        for unit in dep_units:
            if not isinstance(unit, dict):
                continue
            wrapper = unit.get("14")
            if not isinstance(wrapper, dict):
                continue
            inner = wrapper.get("1")
            if not isinstance(inner, dict):
                continue
            node_interface = inner.get("1")
            if not isinstance(node_interface, dict):
                continue
            for list_key in ("100", "101", "102", "103"):
                pins_list = node_interface.get(list_key)
                if not isinstance(pins_list, list):
                    continue
                for pin in pins_list:
                    if not isinstance(pin, dict):
                        continue
                    idx = pin.get("8")
                    if isinstance(idx, int) and idx > 0:
                        pin_index_pool.add(int(idx))
    assert pin_index_pool, "expected CompositeDef pinIndex pool to be non-empty"

    for n in composite_nodes:
        pins = n.get("4") or []
        assert isinstance(pins, list)
        for p in pins:
            if not isinstance(p, dict):
                continue
            sig = p.get("1") or {}
            if not isinstance(sig, dict):
                continue
            kind_int = int(sig.get("1") or 0)
            if kind_int not in {2, 3, 4}:
                continue
            composite_pin_index = p.get("7")
            assert isinstance(composite_pin_index, int) and int(composite_pin_index) > 0
            assert int(composite_pin_index) in pin_index_pool

