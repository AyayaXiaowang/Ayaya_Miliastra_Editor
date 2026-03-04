from __future__ import annotations

"""
export_graph_model_json_from_graph_code.py

目标：
- 将 Graph_Generater 的“节点图代码（Graph Code, 类结构 .py）”解析为 GraphModel，并输出“已自动布局”的 JSON。

用途：
- 为“Graph Code → GraphModel(JSON,含坐标/连线) → 写回 .gil 节点图”链路提供中间产物。

说明：
- 本脚本只做 Graph_Generater 侧解析与序列化，不做任何 `.gil` 写回。
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from importlib import import_module

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.port_types import (
    enrich_graph_model_with_port_types,
    load_node_library_maps_from_registry,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root


def _infer_package_id_from_graph_file(*, workspace_root: Path, graph_file: Path) -> str:
    """从节点图文件路径推断所属项目存档 package_id（仅支持标准资源库目录布局）。"""
    root = Path(workspace_root).resolve()
    file = Path(graph_file).resolve()
    root_parts = root.parts
    file_parts = file.parts
    if len(file_parts) < len(root_parts) or file_parts[: len(root_parts)] != root_parts:
        return ""
    rel_parts = list(file_parts[len(root_parts) :])
    # assets/资源库/项目存档/<package_id>/...
    if len(rel_parts) >= 4 and rel_parts[0] == "assets" and rel_parts[1] == "资源库" and rel_parts[2] == "项目存档":
        return str(rel_parts[3] or "").strip()
    return ""


def export_graph_model_json_from_graph_code(
    *,
    graph_code_file: Path,
    output_json_file: Path,
    graph_generater_root: Path,
    strict: bool = True,
) -> Dict[str, Any]:
    gg_root = Path(graph_generater_root).resolve()
    if not (gg_root / "engine").is_dir():
        raise FileNotFoundError(f"invalid Graph_Generater root (missing engine/): {str(gg_root)!r}")
    if not (gg_root / "app").is_dir():
        raise FileNotFoundError(f"invalid Graph_Generater root (missing app/): {str(gg_root)!r}")

    code_path = Path(graph_code_file).resolve()
    if not code_path.is_file():
        raise FileNotFoundError(str(code_path))

    if str(gg_root) not in sys.path:
        sys.path.insert(0, str(gg_root))
    if str(gg_root / "assets") not in sys.path:
        sys.path.insert(1, str(gg_root / "assets"))

    strict_flag = bool(strict)

    # ===== 严格入口：走 Graph_Generater 的标准链路（解析 → LayoutService → graph_cache）=====
    ensure_settings_workspace_root = getattr(import_module("engine.utils.workspace"), "ensure_settings_workspace_root")
    workspace_root = ensure_settings_workspace_root(
        explicit_root=gg_root,
        start_paths=[code_path, gg_root],
        load_user_settings=True,
    )

    load_graph_metadata_from_file = getattr(import_module("engine.graph.utils.metadata_extractor"), "load_graph_metadata_from_file")
    graph_meta = load_graph_metadata_from_file(code_path)
    graph_id = str(getattr(graph_meta, "graph_id", "") or "").strip()
    if not graph_id:
        raise ValueError(f"节点图源码未声明 graph_id（docstring metadata）：{str(code_path)!r}")

    # 作用域：优先按文件路径推断 package_id（项目存档）
    package_id = _infer_package_id_from_graph_file(workspace_root=Path(workspace_root), graph_file=code_path)

    result_data: Dict[str, Any]
    graph_model_payload: Dict[str, Any]

    if strict_flag:
        ResourceType = getattr(import_module("engine.configs.resource_types"), "ResourceType")
        ResourceManager = getattr(import_module("engine.resources.resource_manager"), "ResourceManager")

        resource_manager = ResourceManager(Path(workspace_root))
        resource_manager.set_active_package_id(package_id or None)
        resource_manager.rebuild_index()
        resource_manager.invalidate_graph_for_reparse(graph_id)
        loaded = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not isinstance(loaded, dict):
            raise RuntimeError(f"加载节点图失败或不在当前作用域索引中：graph_id={graph_id!r}")

        # 从 graph_cache 读取 result_data（作为坐标/增强布局的单一真源）
        PersistentGraphCacheManager = getattr(import_module("engine.resources.persistent_graph_cache_manager"), "PersistentGraphCacheManager")
        cache_manager = PersistentGraphCacheManager(Path(workspace_root))
        result_data = cache_manager.read_persistent_graph_cache_result_data(graph_id)
        if not isinstance(result_data, dict):
            raise RuntimeError(f"未生成持久化 graph_cache result_data：graph_id={graph_id!r}")

        graph_model_payload = result_data.get("data")
        if not isinstance(graph_model_payload, dict):
            raise TypeError("graph_cache result_data['data'] must be dict")
    else:
        # ===== 非严格入口：尽力解析（允许结构校验不通过），用于批量诊断/差异分析 =====
        get_node_registry = getattr(import_module("engine"), "get_node_registry")
        GraphCodeParser = getattr(import_module("engine"), "GraphCodeParser")
        LayoutService = getattr(import_module("engine.layout"), "LayoutService")
        apply_augmented_layout_merge = getattr(import_module("engine.layout.utils.augmented_layout_merge"), "apply_augmented_layout_merge")

        registry = get_node_registry(Path(workspace_root), include_composite=True)
        node_library = registry.get_library()

        parser = GraphCodeParser(Path(workspace_root), node_library=node_library, strict=False)
        graph_model, metadata = parser.parse_file(code_path)

        # 与资源层 GraphLoader 对齐：计算增强布局并差分合并到模型
        layout_result = LayoutService.compute_layout(
            graph_model,
            node_library=node_library,
            include_augmented_model=True,
            workspace_path=Path(workspace_root),
        )
        apply_augmented_layout_merge(
            graph_model,
            layout_result,
            allow_fallback_without_augmented=True,
        )

        graph_model_payload = graph_model.serialize()
        graph_scope = str(metadata.get("graph_type") or metadata.get("scope") or graph_model_payload.get("metadata", {}).get("graph_type") or "server")

        # 为工具链提供与 graph_cache 近似的 result_data 结构（只保留必要字段）
        result_data = {
            "id": str(graph_id),
            "name": str(metadata.get("graph_name") or metadata.get("name") or ""),
            "graph_type": str(graph_scope or "server"),
            "data": graph_model_payload,
            "metadata": {
                "graph_code_file": str(code_path),
                "graph_generater_root": str(gg_root),
                "active_package_id": str(package_id or ""),
                "strict": False,
            },
        }

    # 为写回 `.gil` 等外部工具补充“端口类型”（含泛型端口的具体类型推断）
    GraphModel = getattr(import_module("engine.graph.models.graph_model"), "GraphModel")
    graph_model = GraphModel.deserialize(graph_model_payload)
    graph_scope = str(result_data.get("graph_type") or (graph_model_payload.get("metadata") or {}).get("graph_type") or "server")
    # 端口类型补齐需要完整的 NodeDef 定位映射：
    # - builtin: canonical_key -> NodeDef
    # - composite: composite_id -> NodeDef
    # 仅传 node_defs_by_name 会导致 composite 节点在运行态 strict 模式下无法定位 NodeDef（禁止 title fallback）。
    node_defs_by_name_map, node_defs_by_key_map, composite_node_def_by_id_map = load_node_library_maps_from_registry(
        workspace_root=Path(workspace_root),
        scope=graph_scope,
        include_composite=True,
    )
    enrich_graph_model_with_port_types(
        graph_model=graph_model,
        graph_model_payload=graph_model_payload,
        node_defs_by_name=dict(node_defs_by_name_map or {}),
        node_defs_by_key=dict(node_defs_by_key_map or {}),
        composite_node_def_by_id=dict(composite_node_def_by_id_map or {}),
    )

    output_payload = dict(result_data)
    output_payload["graph_code_file"] = str(code_path)
    output_payload["graph_generater_root"] = str(gg_root)
    output_payload["active_package_id"] = str(package_id or "")
    output_payload["strict"] = bool(strict_flag)

    output_path = resolve_output_file_path_in_out_dir(Path(output_json_file))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "graph_code_file": str(code_path),
        "output_json": str(output_path),
        "graph_name": str(result_data.get("name") or ""),
        "graph_id": str(graph_id),
        "active_package_id": str(package_id or ""),
        "nodes_count": len(getattr(graph_model, "nodes", {}) or {}),
        "edges_count": len(getattr(graph_model, "edges", {}) or {}),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="将 Graph Code 解析为 GraphModel(JSON,含自动布局)，写入到 .json 文件。")
    parser.add_argument("--graph-code", required=True, help="输入 Graph Code 文件路径（Graph_Generater 资源库内 .py）")
    parser.add_argument("--output-json", required=True, help="输出 JSON（强制写入 ugc_file_tools/out/）")
    parser.add_argument(
        "--graph-generater-root",
        default=str(repo_root()),
        help="Graph_Generater 工程根目录（默认自动定位到包含 engine/assets/tools 的目录）",
    )
    parser.add_argument(
        "--non-strict",
        dest="non_strict",
        action="store_true",
        help="非严格解析：允许图结构校验不通过（用于批量诊断/差异分析；默认严格 fail-closed）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = export_graph_model_json_from_graph_code(
        graph_code_file=Path(args.graph_code),
        output_json_file=Path(args.output_json),
        graph_generater_root=Path(args.graph_generater_root),
        strict=(not bool(getattr(args, "non_strict", False))),
    )

    print("=" * 80)
    print("Graph Code → GraphModel(JSON) 导出完成：")
    for key in sorted(report.keys()):
        print(f"- {key}: {report.get(key)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




