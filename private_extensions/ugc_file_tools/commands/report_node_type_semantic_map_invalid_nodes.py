from __future__ import annotations

"""
report_node_type_semantic_map_invalid_nodes.py

目标：
- 校验 `ugc_file_tools/graph_ir/node_type_semantic_map.json` 中已填写的中文节点名，
  是否都能在 Graph_Generater 的“实现节点库”（plugins/nodes/** 的 @node_spec）中找到。

背景：
- Graph_Generater 的 NodeRegistry 会把实现节点 +（可选）复合节点加载到同一 NodeDef 库；
- 同时实现库可能会注入“别名键”（`类别/别名`）指向同一个 NodeDef，容易在导出时出现重复；
- 本脚本默认：
  - 排除复合节点（include_composite=False）
  - 排除别名键（仅接受 canonical key：`类别/名称`）

约束：
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


def _resolve_workspace_root_from_this_file() -> Path:
    return repo_root()


def _build_impl_node_name_set_by_scope(*, graph_generater_root: Path) -> Dict[str, Set[str]]:
    graph_generater_root = Path(graph_generater_root).resolve()
    if str(graph_generater_root) not in sys.path:
        sys.path.insert(0, str(graph_generater_root))

    from engine.nodes.node_registry import get_node_registry

    registry = get_node_registry(graph_generater_root, include_composite=False)
    library = registry.get_library()
    index = registry.get_node_library_index()
    by_key = index.get("by_key", {}) if isinstance(index, dict) else {}
    impl_key_set = set(by_key.keys()) if isinstance(by_key, dict) else set()

    names_by_scope: Dict[str, Set[str]] = {"server": set(), "client": set()}
    for key, nd in (library or {}).items():
        if nd is None:
            continue
        # 仅接受 V2 管线 by_key 中的实现条目，避免 alias 注入键导致重复；
        # 同时保留 `#client/#server` 等后缀 key（用于区分同名不同作用域实现）。
        if str(key) not in impl_key_set:
            continue
        name = str(getattr(nd, "name", "") or "").strip()
        if name == "":
            continue

        for scope in ("server", "client"):
            if hasattr(nd, "is_available_in_scope") and not nd.is_available_in_scope(scope):
                continue
            names_by_scope[scope].add(name)

    return names_by_scope


def report_invalid_nodes(
    *,
    mapping_json_path: Path,
    graph_generater_root: Path,
    output_json_path: Optional[Path],
    output_csv_path: Optional[Path],
) -> Dict[str, Any]:
    mapping_obj = json.loads(Path(mapping_json_path).read_text(encoding="utf-8"))
    if not isinstance(mapping_obj, dict):
        raise TypeError("node_type_semantic_map.json must be dict")

    impl_names_by_scope = _build_impl_node_name_set_by_scope(graph_generater_root=graph_generater_root)

    invalid_rows: List[Dict[str, Any]] = []
    for type_id, entry in mapping_obj.items():
        if not isinstance(entry, dict):
            continue
        cn_name = str(entry.get("graph_generater_node_name") or "").strip()
        if cn_name == "":
            continue
        scope = str(entry.get("scope") or "").strip().lower() or "server"
        if scope not in {"server", "client"}:
            scope = "server"
        if cn_name not in impl_names_by_scope.get(scope, set()):
            invalid_rows.append(
                {
                    "type_id": str(type_id),
                    "scope": scope,
                    "cn_name": cn_name,
                    "confidence": str(entry.get("confidence") or ""),
                    "semantic_id": str(entry.get("semantic_id") or ""),
                    "notes": str(entry.get("notes") or ""),
                }
            )

    def _sort_key(r: Dict[str, Any]) -> tuple:
        tid = str(r.get("type_id") or "")
        tid_num = int(tid) if tid.lstrip("-").isdigit() else 10**18
        return (str(r.get("scope") or ""), tid_num)

    invalid_rows.sort(key=_sort_key)

    report = {
        "mapping_json": str(Path(mapping_json_path).resolve()),
        "graph_generater_root": str(Path(graph_generater_root).resolve()),
        "invalid_count": len(invalid_rows),
        "rows": invalid_rows,
    }

    if output_json_path is not None:
        out_json = resolve_output_file_path_in_out_dir(Path(output_json_path))
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if output_csv_path is not None:
        out_csv = resolve_output_file_path_in_out_dir(Path(output_csv_path))
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(
                f, fieldnames=["type_id", "scope", "cn_name", "confidence", "semantic_id", "notes"]
            )
            w.writeheader()
            for r in invalid_rows:
                w.writerow({k: r.get(k, "") for k in w.fieldnames})

    return report


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="校验 node_type_semantic_map.json 的中文节点名是否都存在于 plugins/nodes 实现节点库（排除复合节点/别名键）。"
    )
    parser.add_argument(
        "--mapping-json",
        dest="mapping_json_path",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="node_type_semantic_map.json 路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=None,
        help="可选：Graph_Generater 根目录（默认自动定位到 workspace/Graph_Generater）",
    )
    parser.add_argument(
        "--output-json",
        dest="output_json_path",
        default="node_type_semantic_map.invalid_nodes_in_plugins.json",
        help="输出 JSON 报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument(
        "--output-csv",
        dest="output_csv_path",
        default="node_type_semantic_map.invalid_nodes_in_plugins.csv",
        help="输出 CSV 报告文件名（强制写入 ugc_file_tools/out/）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    workspace_root = _resolve_workspace_root_from_this_file()
    graph_generater_root = (
        Path(args.graph_generater_root).resolve()
        if args.graph_generater_root is not None and str(args.graph_generater_root).strip() != ""
        else workspace_root.resolve()
    )

    report = report_invalid_nodes(
        mapping_json_path=Path(args.mapping_json_path),
        graph_generater_root=graph_generater_root,
        output_json_path=(Path(args.output_json_path) if args.output_json_path is not None else None),
        output_csv_path=(Path(args.output_csv_path) if args.output_csv_path is not None else None),
    )

    print("=" * 80)
    print("校验完成：")
    print(f"- invalid_count: {report.get('invalid_count')}")
    print(f"- mapping_json: {report.get('mapping_json')}")
    print(f"- graph_generater_root: {report.get('graph_generater_root')}")
    print("=" * 80)

    invalid_count = int(report.get("invalid_count") or 0)
    if invalid_count > 0:
        out_json = resolve_output_file_path_in_out_dir(Path(str(args.output_json_path)))
        out_csv = resolve_output_file_path_in_out_dir(Path(str(args.output_csv_path)))
        raise ValueError(
            "node_type_semantic_map.json 存在无效节点名（未在 Graph_Generater 实现节点库中找到），请先修复映射表：\n"
            f"- invalid_count: {invalid_count}\n"
            f"- report_json: {str(out_json)}\n"
            f"- report_csv: {str(out_csv)}"
        )


if __name__ == "__main__":
    main()




