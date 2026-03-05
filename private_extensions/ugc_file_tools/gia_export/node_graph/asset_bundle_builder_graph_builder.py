from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia.container import wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .asset_bundle_builder_composite import _build_composite_dependency_units_for_graph
from .asset_bundle_builder_graph_context import build_node_graph_build_context
from .asset_bundle_builder_proto_helpers import _make_resource_locator
from .asset_bundle_builder_types import GiaAssetBundleGraphExportHints


def build_asset_bundle_message_from_graph_model_json(
    *,
    graph_json_object: Dict[str, Any],
    hints: GiaAssetBundleGraphExportHints,
) -> Dict[str, Any]:
    ctx = build_node_graph_build_context(graph_json_object=graph_json_object, hints=hints)
    consts = ctx.consts
    graph_model = ctx.graph_model
    node_graph_container = ctx.node_graph_container

    asset_locator = _make_resource_locator(
        origin=int(consts["AssetsOrigin"]),
        category=int(consts["AssetsCategory"]),
        kind=int(consts["AssetsKind"]),
        guid=int(hints.graph_id_int),
        runtime_id=0,
    )
    resource_entry: Dict[str, Any] = {
        "1": asset_locator,
        "3": str(hints.graph_name),
        "5": int(consts["AssetsWhich"]),
        "13": node_graph_container,
    }

    composite_dependency_units: List[Dict[str, Any]] = []
    composite_related_ids: List[Dict[str, Any]] = []
    if bool(hints.include_composite_nodes):
        try_nodes = graph_model.get("nodes") if isinstance(graph_model, dict) else None
        if isinstance(try_nodes, list) and try_nodes:
            composite_dependency_units, composite_related_ids = _build_composite_dependency_units_for_graph(
                graph_nodes=[dict(n) for n in try_nodes if isinstance(n, dict)],
                hints=hints,
            )

    merged_related_ids: List[Dict[str, Any]] = []
    if isinstance(hints.graph_related_ids, list) and hints.graph_related_ids:
        merged_related_ids.extend(list(hints.graph_related_ids))
    if composite_related_ids:
        merged_related_ids.extend(list(composite_related_ids))
    if merged_related_ids:
        dedup: List[Dict[str, Any]] = []
        seen: set[Tuple[int, int]] = set()
        for rid in list(merged_related_ids):
            if not isinstance(rid, dict):
                continue
            cls = rid.get("2")
            rid_id = rid.get("4")
            if not isinstance(cls, int) or not isinstance(rid_id, int):
                continue
            key = (int(cls), int(rid_id))
            if key in seen:
                continue
            seen.add(key)
            dedup.append({"2": int(cls), "4": int(rid_id)})
        if dedup:
            # 稳定排序：避免依赖上游扫描顺序导致 dependencies/relatedIds 在不同机器上抖动。
            dedup.sort(key=lambda d: (int(d.get("2") or 0), int(d.get("4") or 0)))
            resource_entry["2"] = dedup

    uid = int(hints.export_uid)
    timestamp = int(time.time())
    file_stem = sanitize_file_stem(str(hints.graph_name))
    export_tag = f"{uid}-{timestamp}-{int(hints.graph_id_int)}-\\\\{file_stem}.gia"

    merged_deps: List[Dict[str, Any]] = []
    if isinstance(hints.extra_dependency_graph_units, list) and hints.extra_dependency_graph_units:
        merged_deps.extend(list(hints.extra_dependency_graph_units))
    if composite_dependency_units:
        merged_deps.extend(list(composite_dependency_units))
    if merged_deps:
        dedup2: List[Dict[str, Any]] = []
        seen2: set[Tuple[int, int]] = set()
        for unit in list(merged_deps):
            if not isinstance(unit, dict):
                continue
            unit_id = unit.get("1")
            if not isinstance(unit_id, dict):
                continue
            cls = unit_id.get("2")
            rid_id = unit_id.get("4")
            if not isinstance(cls, int) or not isinstance(rid_id, int):
                continue
            key = (int(cls), int(rid_id))
            if key in seen2:
                continue
            seen2.add(key)
            dedup2.append(dict(unit))
        dedup2.sort(key=lambda u: (int(((u.get("1") or {}).get("2")) or 0), int(((u.get("1") or {}).get("4")) or 0)))
        merged_deps = dedup2

    asset_bundle: Dict[str, Any] = {
        "1": resource_entry,
        "2": list(merged_deps) if merged_deps else [],
        "3": export_tag,
        "5": str(hints.game_version or "6.3.0"),
    }
    return asset_bundle


def create_gia_file_from_graph_model_json(
    *,
    graph_json_object: Dict[str, Any],
    hints: GiaAssetBundleGraphExportHints,
    output_gia_path: Path,
) -> Dict[str, Any]:
    asset_bundle_message = build_asset_bundle_message_from_graph_model_json(graph_json_object=graph_json_object, hints=hints)
    proto_bytes = encode_message(asset_bundle_message)
    out_bytes = wrap_gia_container(proto_bytes)
    output_gia_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)
    return {
        "mode": "new_asset_bundle",
        "output_gia_file": str(output_gia_path),
        "graph_id_int": int(hints.graph_id_int),
        "resource_class": str(hints.resource_class),
    }

