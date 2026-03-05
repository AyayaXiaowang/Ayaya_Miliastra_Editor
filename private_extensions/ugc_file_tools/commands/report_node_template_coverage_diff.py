from __future__ import annotations

"""
report_node_template_coverage_diff.py

目标：
- 对齐 `graph_model_json_to_gil_node_graph.py` 的“节点模板库”机制，提供一个可重复的差异报告：
  - 写回节点图时，我们需要 `node type_id -> node template` 的样本（通常来自 template_gil 的某张模板图 + 可选 template_library_dir 里的额外样本库）。
  - 本工具会扫描模板库中已覆盖的 node type_id 集合；
  - 再扫描一组 GraphModel(JSON) 所需的节点（node.title），用 `node_type_semantic_map.json` 映射为 type_id；
  - 输出“缺失模板样本的节点/类型”与“缺失 title→type_id 映射”的报告。

特点：
- 不依赖 DLL：直接解码 `.gil` payload（protobuf-like）。
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.model_files import iter_graph_model_json_files_from_paths
from ugc_file_tools.graph.model_ir import normalize_nodes_list, pick_graph_model_payload_and_metadata
from ugc_file_tools.gil.graph_variable_scanner import (
    collect_node_type_ids_from_gil,
    collect_node_type_ids_from_gil_graph,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import ugc_file_tools_root
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root
from ugc_file_tools.node_graph_writeback.struct_node_type_map import build_struct_node_writeback_maps_from_payload_root
from ugc_file_tools.scope_utils import normalize_scope_or_default, normalize_scope_or_raise


_STRUCT_NODE_TITLES: set[str] = {"拼装结构体", "拆分结构体", "修改结构体"}


def _extract_struct_id_from_graph_node(node_obj: Dict[str, Any]) -> Optional[int]:
    """从 GraphModel.node.input_constants 中提取 struct_id（优先 __struct_id）。"""
    input_constants = node_obj.get("input_constants")
    if not isinstance(input_constants, dict):
        return None
    for key in ("__struct_id", "struct_id", "struct_def_id"):
        raw = input_constants.get(key)
        if isinstance(raw, int):
            return int(raw)
        if isinstance(raw, str):
            text = raw.strip()
            if text.isdigit():
                return int(text)
    return None


def _normalize_scope_text(text: str) -> str:
    # 兼容：保留旧函数名，底层实现收敛到 scope_utils 单一真源。
    return normalize_scope_or_raise(text)


def _load_name_to_type_ids_by_scope(mapping_path: Path) -> Dict[str, Dict[str, List[int]]]:
    """读取 node_type_semantic_map.json，返回 scope -> node_name -> [type_id_int, ...]。"""
    doc = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise TypeError("node_type_semantic_map.json must be dict")

    by_scope: Dict[str, Dict[str, List[int]]] = {"server": {}, "client": {}}
    for type_id_str, entry in doc.items():
        if not isinstance(entry, dict):
            continue
        scope = str(entry.get("scope") or "").strip().lower()
        if scope not in ("server", "client"):
            continue
        if not str(type_id_str).isdigit():
            continue
        name = str(entry.get("graph_generater_node_name") or "").strip()
        if name == "":
            continue
        by_scope.setdefault(scope, {}).setdefault(name, []).append(int(type_id_str))

    # 保持稳定：type_id 排序
    for scope, mp in by_scope.items():
        for name, ids in mp.items():
            mp[name] = sorted(set(int(v) for v in ids))
    return by_scope


@dataclass(frozen=True, slots=True)
class GraphMissingTemplateReport:
    graph_json: str
    graph_name: str
    scope: str
    nodes_total: int
    titles_unique: int
    missing_type_id_mapping_titles: Tuple[str, ...]
    ambiguous_title_mappings: Tuple[Tuple[str, Tuple[int, ...]], ...]
    missing_template_nodes: Tuple[Tuple[str, int], ...]  # (title, type_id)


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="报告 GraphModel 写回所需的 node template 覆盖缺口（对齐 graph_model_json_to_gil_node_graph 的模板库机制）。")
    parser.add_argument("--template-gil", required=True, help="用于写回的 template_gil（仅扫描 --template-graph-id 指定的那张图）。")
    parser.add_argument("--base-gil", default=None, help="可选：写回使用的 base_gil（用于解析结构体节点的 struct_id→node_type_id；默认等同于 template_gil）。")
    parser.add_argument("--template-graph-id", type=int, required=True, help="template_gil 中用于构建模板库的 graph_id_int（与写回脚本参数一致）。")
    parser.add_argument("--template-library-dir", default=None, help="可选：额外样本库目录（递归扫描 *.gil，扫描其所有节点图）。")
    parser.add_argument(
        "--mapping",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="node_type_semantic_map.json 路径（默认使用 ugc_file_tools/graph_ir/node_type_semantic_map.json）。",
    )
    parser.add_argument("--default-scope", default="server", help="当 GraphModel 未声明 graph_type 时使用的默认 scope（server/client）。")
    parser.add_argument(
        "graph_models",
        nargs="+",
        help="GraphModel(JSON) 文件或目录（目录会匹配 *.graph_model.typed*.json / *.graph_model.json）。",
    )
    parser.add_argument(
        "--output-json",
        default="node_template_coverage_diff.report.json",
        help="输出报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    template_gil_path = Path(args.template_gil).resolve()
    if not template_gil_path.is_file():
        raise FileNotFoundError(str(template_gil_path))
    template_graph_id_int = int(args.template_graph_id)

    base_gil_path = template_gil_path
    if args.base_gil is not None and str(args.base_gil).strip() != "":
        base_gil_path = Path(str(args.base_gil)).resolve()
    if not base_gil_path.is_file():
        raise FileNotFoundError(str(base_gil_path))

    mapping_path = Path(args.mapping).resolve()
    if not mapping_path.is_file():
        raise FileNotFoundError(str(mapping_path))

    default_scope = normalize_scope_or_default(str(args.default_scope), default_scope="server")
    name_to_ids_by_scope = _load_name_to_type_ids_by_scope(mapping_path)

    # ===== 1) 收集模板库已覆盖的 node type_id =====
    available_type_ids: Set[int] = set()
    available_type_ids |= collect_node_type_ids_from_gil_graph(gil_path=template_gil_path, graph_id_int=template_graph_id_int)

    template_library_dir = None
    if args.template_library_dir is not None:
        template_library_dir = Path(args.template_library_dir).resolve()
        if not template_library_dir.is_dir():
            raise FileNotFoundError(str(template_library_dir))
        for extra_gil in sorted(template_library_dir.rglob("*.gil")):
            if not extra_gil.is_file():
                continue
            available_type_ids |= collect_node_type_ids_from_gil(extra_gil)

    # ===== 结构体节点：从 base_gil 的 node_defs 推导 struct_id→node_type_id =====
    base_raw = dump_gil_to_raw_json_object(base_gil_path)
    base_payload_root = get_payload_root(base_raw)
    struct_node_maps = build_struct_node_writeback_maps_from_payload_root(base_payload_root)

    # ===== 2) 扫描 GraphModel(JSON) 所需节点并对比 =====
    graph_json_files = iter_graph_model_json_files_from_paths(list(args.graph_models))
    per_graph: List[GraphMissingTemplateReport] = []

    missing_template_type_ids_all: Set[int] = set()
    missing_mapping_titles_all: Set[str] = set()
    ambiguous_titles_all: Dict[str, Set[int]] = {}

    for json_path in graph_json_files:
        obj = json.loads(Path(json_path).read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise TypeError(f"GraphModel JSON 顶层必须是 dict：{str(json_path)!r}")

        metadata, graph_model = pick_graph_model_payload_and_metadata(obj)
        if not isinstance(graph_model, dict):
            raise TypeError(f"graph_model 不是 dict：{str(json_path)!r}")

        graph_name = str(metadata.get("graph_name") or graph_model.get("graph_name") or json_path.stem).strip()

        scope = str(metadata.get("graph_type") or metadata.get("graph_scope") or "").strip().lower()
        if scope not in ("server", "client"):
            scope = default_scope

        nodes = normalize_nodes_list(graph_model)
        titles = [str(n.get("title") or "").strip() for n in nodes if isinstance(n, dict)]
        titles = [t for t in titles if t]
        unique_titles = sorted(set(titles))

        name_to_ids = name_to_ids_by_scope.get(scope, {})

        missing_mapping: List[str] = []
        ambiguous: List[Tuple[str, Tuple[int, ...]]] = []
        missing_templates: List[Tuple[str, int]] = []

        # 注意：结构体节点的 type_id 依赖 struct_id，不能仅以 title 去重。
        required_pairs: Set[Tuple[str, int]] = set()

        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or "").strip()
            if title == "":
                continue

            node_def_ref = node.get("node_def_ref")
            node_def_kind = str(node_def_ref.get("kind") or "").strip().lower() if isinstance(node_def_ref, dict) else ""

            # 结构体节点：使用 base_gil.node_defs 解析的 struct_id→node_type_id
            if title in _STRUCT_NODE_TITLES:
                struct_id_int = _extract_struct_id_from_graph_node(node)
                if not isinstance(struct_id_int, int):
                    key = f"{title}(缺少__struct_id)"
                    missing_mapping.append(key)
                    missing_mapping_titles_all.add(key)
                    continue
                type_id_int = (struct_node_maps.node_type_id_by_title_and_struct_id.get(str(title)) or {}).get(int(struct_id_int))
                if not isinstance(type_id_int, int):
                    key = f"{title}(struct_id={int(struct_id_int)})"
                    missing_mapping.append(key)
                    missing_mapping_titles_all.add(key)
                    continue
                display = f"{title}(struct_id={int(struct_id_int)})"
                required_pairs.add((display, int(type_id_int)))
                continue

            # 普通节点：使用 node_type_semantic_map 映射
            ids = name_to_ids.get(title)
            if not ids:
                # 工程化：signal listen 事件节点的 title/node_def_ref.key 通常为“信号名”，不在语义映射表中。
                # 这类节点在 `.gil` 里仍是通用 runtime（server: 300001=监听信号），真正的信号名写在 META pins。
                # 因此：当 node_def_ref.kind=event 且 GraphModel 看起来是“信号事件”，回退到 监听信号。
                if scope == "server" and node_def_kind == "event":
                    outputs = node.get("outputs")
                    if isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs):
                        listen_ids = name_to_ids.get("监听信号") or []
                        if len(listen_ids) == 1:
                            required_pairs.add((title, int(listen_ids[0])))
                            continue

                missing_mapping.append(title)
                missing_mapping_titles_all.add(title)
                continue
            if len(ids) != 1:
                ids_tuple = tuple(int(v) for v in ids)
                ambiguous.append((title, ids_tuple))
                ambiguous_titles_all.setdefault(title, set()).update(set(ids_tuple))
                continue
            required_pairs.add((title, int(ids[0])))

        for title, type_id_int in sorted(required_pairs, key=lambda x: (x[1], x[0])):
            if int(type_id_int) not in available_type_ids:
                missing_templates.append((str(title), int(type_id_int)))
                missing_template_type_ids_all.add(int(type_id_int))

        per_graph.append(
            GraphMissingTemplateReport(
                graph_json=str(json_path),
                graph_name=str(graph_name),
                scope=str(scope),
                nodes_total=int(len(nodes)),
                titles_unique=int(len(unique_titles)),
                missing_type_id_mapping_titles=tuple(sorted(missing_mapping)),
                ambiguous_title_mappings=tuple(sorted(ambiguous, key=lambda x: x[0])),
                missing_template_nodes=tuple(sorted(missing_templates, key=lambda x: (x[1], x[0]))),
            )
        )

    # ===== 输出报告 =====
    report_obj: Dict[str, Any] = {
        "inputs": {
            "template_gil": str(template_gil_path),
            "template_graph_id_int": int(template_graph_id_int),
            "template_library_dir": str(template_library_dir) if template_library_dir is not None else "",
            "mapping": str(mapping_path),
            "graph_models": [str(p) for p in graph_json_files],
            "default_scope": str(default_scope),
        },
        "template_coverage": {
            "available_type_ids_count": int(len(available_type_ids)),
        },
        "summary": {
            "graphs": int(len(per_graph)),
            "missing_template_type_ids": sorted(list(missing_template_type_ids_all)),
            "missing_template_type_ids_count": int(len(missing_template_type_ids_all)),
            "missing_type_id_mapping_titles": sorted(list(missing_mapping_titles_all)),
            "missing_type_id_mapping_titles_count": int(len(missing_mapping_titles_all)),
            "ambiguous_title_mappings": [
                {"title": title, "type_ids": sorted(list(type_ids))}
                for title, type_ids in sorted(ambiguous_titles_all.items(), key=lambda kv: kv[0])
            ],
            "ambiguous_title_mappings_count": int(len(ambiguous_titles_all)),
        },
        "graphs": [
            {
                "graph_json": g.graph_json,
                "graph_name": g.graph_name,
                "scope": g.scope,
                "nodes_total": g.nodes_total,
                "titles_unique": g.titles_unique,
                "missing_type_id_mapping_titles": list(g.missing_type_id_mapping_titles),
                "ambiguous_title_mappings": [
                    {"title": t, "type_ids": list(ids)} for (t, ids) in g.ambiguous_title_mappings
                ],
                "missing_template_nodes": [{"title": t, "type_id_int": tid} for (t, tid) in g.missing_template_nodes],
            }
            for g in per_graph
        ],
    }

    out_path = resolve_output_file_path_in_out_dir(Path(str(args.output_json)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("================================================================================")
    print("节点模板覆盖差异报告已生成：")
    print(f"- template_gil: {str(template_gil_path)}")
    print(f"- template_graph_id_int: {int(template_graph_id_int)}")
    if template_library_dir is not None:
        print(f"- template_library_dir: {str(template_library_dir)}")
    print(f"- graphs: {len(per_graph)}")
    print(f"- output: {str(out_path)}")
    print("---- summary ----")
    print(f"missing_template_type_ids_count = {report_obj['summary']['missing_template_type_ids_count']}")
    print(f"missing_type_id_mapping_titles_count = {report_obj['summary']['missing_type_id_mapping_titles_count']}")
    print(f"ambiguous_title_mappings_count = {report_obj['summary']['ambiguous_title_mappings_count']}")
    print("================================================================================")


if __name__ == "__main__":
    main()




