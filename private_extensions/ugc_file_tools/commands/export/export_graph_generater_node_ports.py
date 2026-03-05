from __future__ import annotations

"""
export_graph_generater_node_ports.py

目标：
- 直接读取 Graph_Generater 的节点库（plugins/nodes/**.py 的 @node_spec 权威信息），
  导出每个节点的输入/输出端口清单（含端口类型、默认值、枚举候选项等）。
- 默认不包含“复合节点”（Composite Nodes），以保证清单只覆盖 `Graph_Generater/plugins/nodes/{server,client}` 内的节点实现。

用途：
- 生成“节点端口列表”，避免再从 .gil 侧反推“有哪些入口/出口”；
- 与 type_id→节点名 映射（ugc_file_tools/graph_ir/node_type_semantic_map.json）配合，
  可把“某个 type_id 对应节点的端口表”直接查出来；
- 也可用于生成校准图、覆盖报告、或做写回前的端口合法性检查。

约束：
- 不使用 try/except；失败直接抛错，便于定位环境/依赖问题。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root


def _to_sorted_list(values: Any) -> List[Any]:
    if not isinstance(values, list):
        return []
    return list(values)


def export_node_ports(
    *,
    graph_generater_root: Path,
    scope: str,
    category: Optional[str],
    include_composite: bool,
) -> List[Dict[str, Any]]:
    graph_generater_root = Path(graph_generater_root).resolve()
    if not graph_generater_root.is_dir():
        raise FileNotFoundError(str(graph_generater_root))

    if str(graph_generater_root) not in sys.path:
        sys.path.insert(0, str(graph_generater_root))

    from engine.nodes.node_registry import get_node_registry
    from engine.utils.name_utils import make_valid_identifier

    scope_text = str(scope or "").strip().lower()
    if scope_text not in {"server", "client"}:
        raise ValueError(f"scope must be 'server' or 'client', got: {scope!r}")

    registry = get_node_registry(graph_generater_root, include_composite=bool(include_composite))
    library = registry.get_library()
    index = registry.get_node_library_index()
    by_key = index.get("by_key", {}) if isinstance(index, dict) else {}
    impl_key_set = set(by_key.keys()) if isinstance(by_key, dict) else set()

    out: List[Dict[str, Any]] = []
    for _key, nd in (library or {}).items():
        if nd is None:
            continue

        # 过滤“实现库别名注入条目”：
        # - V2 管线产物 by_key 是实现侧权威 key 集合（可能包含 `#client/#server` 后缀用于区分同名不同作用域）。
        # - NodeRegistry 的 get_library 可能额外注入 alias key（`类别/别名`）指向同一 NodeDef。
        #   这里默认只导出 by_key 中的实现条目，避免重复；复合节点则由 include_composite 控制。
        is_composite = bool(getattr(nd, "is_composite", False))
        if is_composite:
            if not bool(include_composite):
                continue
        else:
            if str(_key) not in impl_key_set:
                continue
        if hasattr(nd, "is_available_in_scope") and not nd.is_available_in_scope(scope_text):
            continue

        node_category = str(getattr(nd, "category", "") or "")
        if category is not None and str(category).strip() != "":
            if node_category != str(category).strip():
                continue

        node_name = str(getattr(nd, "name", "") or "").strip()
        if node_name == "":
            continue

        inputs = list(getattr(nd, "inputs", []) or [])
        outputs = list(getattr(nd, "outputs", []) or [])

        input_types = dict(getattr(nd, "input_types", {}) or {})
        output_types = dict(getattr(nd, "output_types", {}) or {})
        input_defaults = dict(getattr(nd, "input_defaults", {}) or {})
        input_enum_options = dict(getattr(nd, "input_enum_options", {}) or {})
        output_enum_options = dict(getattr(nd, "output_enum_options", {}) or {})
        input_generic_constraints = dict(getattr(nd, "input_generic_constraints", {}) or {})
        output_generic_constraints = dict(getattr(nd, "output_generic_constraints", {}) or {})

        out.append(
            {
                "scope": scope_text,
                "category": node_category,
                "name": node_name,
                "semantic_id": str(getattr(nd, "semantic_id", "") or "").strip(),
                "callable_alias": make_valid_identifier(node_name),
                "callable_alias_slash_removed": make_valid_identifier(node_name.replace("/", "")),
                "inputs": [
                    {
                        "name": str(p),
                        "type": str(input_types.get(str(p), "")),
                        "default": input_defaults.get(str(p)),
                        "enum_options": _to_sorted_list(input_enum_options.get(str(p))),
                        "generic_constraints": _to_sorted_list(input_generic_constraints.get(str(p))),
                    }
                    for p in inputs
                ],
                "outputs": [
                    {
                        "name": str(p),
                        "type": str(output_types.get(str(p), "")),
                        "enum_options": _to_sorted_list(output_enum_options.get(str(p))),
                        "generic_constraints": _to_sorted_list(output_generic_constraints.get(str(p))),
                    }
                    for p in outputs
                ],
            }
        )

    out.sort(key=lambda x: (str(x.get("category")), str(x.get("name"))))
    return out


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="导出 Graph_Generater 节点库的端口清单（inputs/outputs/types/defaults）。")
    parser.add_argument("--scope", default="server", help="server/client（默认 server）")
    parser.add_argument("--category", default=None, help="可选：只导出某个 category（例如 执行节点）")
    parser.add_argument(
        "--include-composite",
        dest="include_composite",
        action="store_true",
        help="可选：包含复合节点（默认不包含；通常不要开）",
    )
    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=None,
        help="可选：Graph_Generater 根目录（默认自动定位到包含 engine/assets/tools 的目录）",
    )
    parser.add_argument("--output-json", required=True, help="输出 JSON（强制写入 ugc_file_tools/out/）")

    args = parser.parse_args(list(argv) if argv is not None else None)

    graph_generater_root = (
        Path(args.graph_generater_root).resolve()
        if args.graph_generater_root is not None and str(args.graph_generater_root).strip() != ""
        else repo_root().resolve()
    )

    payload = export_node_ports(
        graph_generater_root=graph_generater_root,
        scope=str(args.scope),
        category=(str(args.category).strip() if args.category is not None else None),
        include_composite=bool(args.include_composite),
    )

    out_path = resolve_output_file_path_in_out_dir(Path(args.output_json))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 80)
    print("节点端口清单导出完成：")
    print(f"- output_json: {str(out_path)}")
    print(f"- include_composite: {bool(args.include_composite)}")
    print(f"- nodes_count: {len(payload)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




