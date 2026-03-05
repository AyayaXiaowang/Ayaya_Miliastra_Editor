from __future__ import annotations

"""
report_node_type_semantic_map_coverage.py

目标：
- 读取 `ugc_file_tools/graph_ir/node_type_semantic_map.json`；
- 读取 Graph_Generater 的实现节点库（plugins/nodes/** 的 @node_spec），获取 server/client 节点名集合；
- 生成“映射覆盖率”报告：
  - Graph_Generater 已实现但映射表缺失的节点名（按 scope）
  - 同一 scope 下，一个节点名被映射到多个 type_id（歧义）

说明：
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


def _resolve_workspace_root_from_this_file() -> Path:
    return repo_root()


def _ensure_graph_generater_sys_path(graph_generater_root: Path) -> None:
    root = Path(graph_generater_root).resolve()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    assets_dir = root / "assets"
    assets_text = str(assets_dir)
    if assets_dir.is_dir() and assets_text not in sys.path:
        sys.path.insert(1, assets_text)


def _build_impl_node_name_set_by_scope(*, graph_generater_root: Path) -> Dict[str, Set[str]]:
    """
    从 Graph_Generater 的实现节点库构建 {scope: {node_name, ...}}。

    约束：
    - 排除复合节点（include_composite=False）
    - 排除 alias 注入键（仅接受 V2 管线 by_key 的实现条目）
    """
    _ensure_graph_generater_sys_path(graph_generater_root)
    from engine.nodes.node_registry import get_node_registry  # type: ignore[import-not-found]

    registry = get_node_registry(Path(graph_generater_root).resolve(), include_composite=False)
    library = registry.get_library()
    index = registry.get_node_library_index()
    by_key = index.get("by_key", {}) if isinstance(index, dict) else {}
    impl_key_set = set(by_key.keys()) if isinstance(by_key, dict) else set()

    names_by_scope: Dict[str, Set[str]] = {"server": set(), "client": set()}
    for key, nd in (library or {}).items():
        if nd is None:
            continue
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

    for scope, mp in by_scope.items():
        for name, ids in mp.items():
            mp[name] = sorted(set(int(v) for v in ids))
    return by_scope


def report_node_type_semantic_map_coverage(
    *,
    mapping_path: Path,
    graph_generater_root: Path,
    scopes: Sequence[str],
    output_json_path: Path,
    output_csv_path: Optional[Path],
    fail_on_missing: bool,
    fail_on_ambiguous: bool,
) -> Dict[str, Any]:
    mapping_path = Path(mapping_path).resolve()
    if not mapping_path.is_file():
        raise FileNotFoundError(str(mapping_path))

    gg_root = Path(graph_generater_root).resolve()
    if not gg_root.is_dir():
        raise FileNotFoundError(str(gg_root))

    scope_list = [str(s).strip().lower() for s in list(scopes)]
    for s in scope_list:
        if s not in ("server", "client"):
            raise ValueError(f"scope 不支持：{s!r}（可选：server/client）")

    impl_names_by_scope = _build_impl_node_name_set_by_scope(graph_generater_root=gg_root)
    name_to_ids_by_scope = _load_name_to_type_ids_by_scope(mapping_path)

    per_scope: Dict[str, Any] = {}
    missing_rows_for_csv: List[Dict[str, Any]] = []
    any_missing = False
    any_ambiguous = False

    for scope in scope_list:
        impl_names = set(impl_names_by_scope.get(scope, set()))
        name_to_ids = dict(name_to_ids_by_scope.get(scope, {}))
        mapped_names = set(name_to_ids.keys())

        missing_names = sorted(impl_names - mapped_names)
        ambiguous = {name: ids for name, ids in name_to_ids.items() if isinstance(ids, list) and len(ids) > 1}
        ambiguous_items = [
            {"name": name, "type_id_ints": list(ids)} for name, ids in sorted(ambiguous.items(), key=lambda kv: kv[0])
        ]

        per_scope[scope] = {
            "graph_generater_node_names_total": int(len(impl_names)),
            "mapped_node_names_total": int(len(mapped_names)),
            "missing_node_names_count": int(len(missing_names)),
            "missing_node_names": missing_names,
            "ambiguous_node_names_count": int(len(ambiguous_items)),
            "ambiguous_node_names": ambiguous_items,
        }

        if missing_names:
            any_missing = True
            for name in missing_names:
                missing_rows_for_csv.append({"scope": scope, "graph_generater_node_name": name})
        if ambiguous_items:
            any_ambiguous = True

    report_obj: Dict[str, Any] = {
        "mapping_json": str(mapping_path),
        "graph_generater_root": str(gg_root),
        "scopes": list(scope_list),
        "per_scope": per_scope,
    }

    out_json = resolve_output_file_path_in_out_dir(Path(output_json_path))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    report_obj["output_json"] = str(out_json)

    out_csv: Optional[Path] = None
    if output_csv_path is not None:
        out_csv = resolve_output_file_path_in_out_dir(Path(output_csv_path))
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["scope", "graph_generater_node_name"])
            w.writeheader()
            for r in missing_rows_for_csv:
                w.writerow({k: r.get(k, "") for k in w.fieldnames})
        report_obj["output_csv_missing_names"] = str(out_csv)

    if fail_on_missing and any_missing:
        raise ValueError(f"node_type_semantic_map 缺少映射：missing_node_names_count>0，详见：{str(out_json)}")
    if fail_on_ambiguous and any_ambiguous:
        raise ValueError(f"node_type_semantic_map 存在歧义映射：ambiguous_node_names_count>0，详见：{str(out_json)}")

    return report_obj


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="生成 node_type_semantic_map.json 覆盖率报告（Graph_Generater 已实现节点名 vs 映射表）。"
    )
    parser.add_argument(
        "--mapping",
        dest="mapping_path",
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
        "--scope",
        dest="scope",
        default="all",
        choices=["server", "client", "all"],
        help="统计范围（默认 all）",
    )
    parser.add_argument(
        "--output-json",
        dest="output_json_path",
        default="node_type_semantic_map.coverage.report.json",
        help="输出 JSON 报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument(
        "--output-csv-missing",
        dest="output_csv_path",
        default="node_type_semantic_map.coverage.missing_names.csv",
        help="输出 CSV（仅缺失节点名；强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument("--fail-on-missing", action="store_true", help="若存在缺失映射则抛错（用于 CI/护栏）。")
    parser.add_argument("--fail-on-ambiguous", action="store_true", help="若存在歧义映射则抛错（用于 CI/护栏）。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    workspace_root = _resolve_workspace_root_from_this_file()
    gg_root = (
        Path(args.graph_generater_root).resolve()
        if args.graph_generater_root is not None and str(args.graph_generater_root).strip() != ""
        else workspace_root.resolve()
    )

    scope_text = str(args.scope or "all").strip().lower()
    scopes = ("server", "client") if scope_text == "all" else (scope_text,)

    report = report_node_type_semantic_map_coverage(
        mapping_path=Path(args.mapping_path),
        graph_generater_root=gg_root,
        scopes=scopes,
        output_json_path=Path(args.output_json_path),
        output_csv_path=(Path(args.output_csv_path) if args.output_csv_path is not None else None),
        fail_on_missing=bool(args.fail_on_missing),
        fail_on_ambiguous=bool(args.fail_on_ambiguous),
    )

    out_json = str(report.get("output_json") or "")
    print("=" * 80)
    print("node_type_semantic_map 覆盖率报告已生成：")
    print(f"- scopes: {list(scopes)}")
    print(f"- mapping_json: {report.get('mapping_json')}")
    print(f"- graph_generater_root: {report.get('graph_generater_root')}")
    print(f"- output_json: {out_json}")
    if report.get("output_csv_missing_names"):
        print(f"- output_csv_missing_names: {report.get('output_csv_missing_names')}")
    for scope in scopes:
        info = (report.get("per_scope") or {}).get(scope, {})
        print(f"---- {scope} ----")
        print(f"graph_generater_node_names_total = {info.get('graph_generater_node_names_total')}")
        print(f"mapped_node_names_total = {info.get('mapped_node_names_total')}")
        print(f"missing_node_names_count = {info.get('missing_node_names_count')}")
        print(f"ambiguous_node_names_count = {info.get('ambiguous_node_names_count')}")
    print("=" * 80)


if __name__ == "__main__":
    main()




