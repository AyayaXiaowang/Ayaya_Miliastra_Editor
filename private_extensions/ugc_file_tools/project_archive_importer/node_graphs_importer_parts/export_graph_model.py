from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ugc_file_tools.graph.node_graph.pos_scale import ensure_positive_finite_node_pos_scale, set_node_pos_scale_in_graph_json
from ugc_file_tools.graph.port_types import enrich_graph_model_with_port_types
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .gg_context import _GGContext


def _export_graph_model_json_from_graph_code_with_context(
    *,
    ctx: _GGContext,
    graph_code_file: Path,
    output_json_file: Path,
    ui_export_record_id: str | None = None,
    ui_guid_registry_snapshot_path: Path | None = None,
    node_pos_scale: float | None = None,
) -> Dict[str, Any]:
    code_path = Path(graph_code_file).resolve()
    if not code_path.is_file():
        raise FileNotFoundError(str(code_path))

    graph_meta = ctx.load_graph_metadata_from_file(code_path)
    graph_id = str(getattr(graph_meta, "graph_id", "") or "").strip()
    if not graph_id:
        raise ValueError(f"节点图源码未声明 graph_id（docstring metadata）：{str(code_path)!r}")

    # 解析并确保 graph_cache 生成（不重建索引）
    ctx.resource_manager.invalidate_graph_for_reparse(graph_id)
    loaded = ctx.resource_manager.load_resource(ctx.ResourceType.GRAPH, graph_id)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"加载节点图失败或不在当前作用域索引中：graph_id={graph_id!r}")

    result_data = ctx.cache_manager.read_persistent_graph_cache_result_data(graph_id)
    if not isinstance(result_data, dict):
        raise RuntimeError(f"未生成持久化 graph_cache result_data：graph_id={graph_id!r}")

    graph_model_payload = result_data.get("data")
    if not isinstance(graph_model_payload, dict):
        raise TypeError("graph_cache result_data['data'] must be dict")

    graph_model = ctx.GraphModel.deserialize(graph_model_payload)
    graph_scope = str(
        result_data.get("graph_type") or (graph_model_payload.get("metadata") or {}).get("graph_type") or "server"
    )
    node_defs_by_name = ctx.node_defs_by_scope.get(str(graph_scope), ctx.node_defs_by_scope["server"])
    node_defs_by_key = ctx.node_defs_by_key_by_scope.get(str(graph_scope), ctx.node_defs_by_key_by_scope["server"])
    composite_node_def_by_id = ctx.composite_node_def_by_id_by_scope.get(
        str(graph_scope),
        ctx.composite_node_def_by_id_by_scope["server"],
    )
    enrich_graph_model_with_port_types(
        graph_model=graph_model,
        graph_model_payload=graph_model_payload,
        node_defs_by_name=node_defs_by_name,
        node_defs_by_key=node_defs_by_key,
        composite_node_def_by_id=composite_node_def_by_id,
    )

    output_payload = dict(result_data)
    output_payload["graph_code_file"] = str(code_path)
    output_payload["graph_generater_root"] = str(ctx.gg_root)
    output_payload["active_package_id"] = str(ctx.package_id or "")
    if node_pos_scale is not None:
        normalized_node_pos_scale = ensure_positive_finite_node_pos_scale(
            value=node_pos_scale,
            source="node_pos_scale",
        )
        set_node_pos_scale_in_graph_json(
            graph_json_object=output_payload,
            node_pos_scale=float(normalized_node_pos_scale),
        )
        graph_model_meta = graph_model_payload.get("metadata")
        if not isinstance(graph_model_meta, dict):
            graph_model_meta = {}
            graph_model_payload["metadata"] = graph_model_meta
        graph_model_meta["node_pos_scale"] = float(normalized_node_pos_scale)
    if str(ui_export_record_id or "").strip() != "":
        output_payload["ui_export_record_id"] = str(ui_export_record_id).strip()
    if ui_guid_registry_snapshot_path is not None:
        output_payload["ui_guid_registry_snapshot_path"] = str(Path(ui_guid_registry_snapshot_path).resolve())

    output_path = resolve_output_file_path_in_out_dir(Path(output_json_file))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "graph_code_file": str(code_path),
        "output_json": str(output_path),
        "graph_name": str(result_data.get("name") or ""),
        "graph_id": str(graph_id),
        "active_package_id": str(ctx.package_id or ""),
        "nodes_count": len(getattr(graph_model, "nodes", {}) or {}),
        "edges_count": len(getattr(graph_model, "edges", {}) or {}),
    }


def export_graph_model_json_from_graph_code_with_context(
    *,
    ctx: _GGContext,
    graph_code_file: Path,
    output_json_file: Path,
    ui_export_record_id: str | None = None,
    ui_guid_registry_snapshot_path: Path | None = None,
    node_pos_scale: float | None = None,
) -> Dict[str, Any]:
    return _export_graph_model_json_from_graph_code_with_context(
        ctx=ctx,
        graph_code_file=graph_code_file,
        output_json_file=output_json_file,
        ui_export_record_id=ui_export_record_id,
        ui_guid_registry_snapshot_path=ui_guid_registry_snapshot_path,
        node_pos_scale=node_pos_scale,
    )

