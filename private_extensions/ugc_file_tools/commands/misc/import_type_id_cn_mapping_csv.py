from __future__ import annotations

"""
import_type_id_cn_mapping_csv.py

目标：
- 将“人工整理的 ID→中文名→英文名”CSV 批量导入到 `graph_ir/node_type_semantic_map.json`。

设计原则：
- 不使用 try/except；失败直接抛错，便于定位。
- 不做“猜测翻译”：以 CSV 提供的中文名为准。
- 会基于 Graph_Generater 节点库做一次可选校验：中文名是否能在对应 scope 的 NodeDef 中找到。
  - 默认不包含“复合节点”（Composite Nodes），以避免把非 `plugins/nodes/**` 的节点混入映射表。

输入 CSV 约定：
- 表头至少包含：ID, 中文名称（英文名称可选，用于备注）
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.node_data_index import load_node_entry_by_id_map, resolve_default_node_data_index_path
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


def _resolve_workspace_root_from_this_file() -> Path:
    return repo_root()


def _parse_int(text: Any) -> int:
    if isinstance(text, int):
        return int(text)
    s = str(text or "").strip()
    if s == "":
        raise ValueError("empty int field")
    return int(s)


def _normalize_scope_from_node_data_entry(node_data_entry: Optional[Dict[str, Any]]) -> str:
    if not isinstance(node_data_entry, dict):
        return "server"
    range_text = str(node_data_entry.get("Range") or "").strip().lower()
    if range_text == "server":
        return "server"
    if range_text == "client":
        return "client"
    return "server"


def _load_graph_generater_node_name_and_semantic_id_by_scope(
    *, workspace_root: Path, include_composite: bool
) -> Dict[str, Dict[str, str]]:
    from ugc_file_tools.repo_paths import resolve_graph_generater_root

    graph_generater_root = resolve_graph_generater_root(Path(workspace_root))
    if str(graph_generater_root) not in sys.path:
        sys.path.insert(0, str(graph_generater_root))

    from engine.nodes.node_registry import get_node_registry

    registry = get_node_registry(graph_generater_root, include_composite=bool(include_composite))
    library = registry.get_library()

    result: Dict[str, Dict[str, str]] = {"server": {}, "client": {}}
    for nd in (library or {}).values():
        if nd is None:
            continue
        name = str(getattr(nd, "name", "") or "").strip()
        if name == "":
            continue
        semantic_id = str(getattr(nd, "semantic_id", "") or "").strip()

        for scope in ("server", "client"):
            if hasattr(nd, "is_available_in_scope") and not nd.is_available_in_scope(scope):
                continue
            # 若同名节点多次出现，要求 semantic_id 一致；否则视为环境问题直接报错
            old = result[scope].get(name)
            if old is not None and old != semantic_id:
                raise ValueError(f"node semantic_id conflict for name={name!r}: {old!r} vs {semantic_id!r}")
            result[scope][name] = semantic_id

    return result


def _read_mapping_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    csv_path = Path(csv_path).resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(str(csv_path))

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: List[Dict[str, str]] = []
        for row in reader:
            if not isinstance(row, dict):
                continue
            rows.append({str(k or ""): str(v or "") for k, v in row.items()})
        return rows


def _sorted_mapping_keys(mapping: Dict[str, Any]) -> List[str]:
    numeric: List[str] = []
    other: List[str] = []
    for k in mapping.keys():
        if isinstance(k, str) and k.lstrip("-").isdigit():
            numeric.append(k)
        else:
            other.append(str(k))
    numeric.sort(key=lambda x: int(x))
    other.sort()
    return numeric + other


def apply_csv_to_mapping(
    *,
    input_csv_path: Path,
    mapping_json_path: Path,
    report_json_path: Optional[Path],
    validate_against_graph_generater: bool,
    include_composite: bool,
) -> Dict[str, Any]:
    mapping_path = Path(mapping_json_path).resolve()
    mapping_obj = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.is_file() else {}
    if not isinstance(mapping_obj, dict):
        raise TypeError("node_type_semantic_map.json must be dict")

    node_entry_by_id = load_node_entry_by_id_map(resolve_default_node_data_index_path())

    workspace_root = _resolve_workspace_root_from_this_file()
    semantic_id_by_scope_and_name = _load_graph_generater_node_name_and_semantic_id_by_scope(
        workspace_root=workspace_root, include_composite=bool(include_composite)
    )

    rows = _read_mapping_csv_rows(Path(input_csv_path))
    if not rows:
        raise ValueError("CSV is empty")

    updated_new = 0
    updated_existing = 0
    overwritten_name = 0
    invalid_node_names: List[Dict[str, Any]] = []

    for row in rows:
        id_text = row.get("ID") or row.get("id") or row.get("Id") or row.get("type_id") or row.get("typeId")
        cn_name = (
            row.get("中文名称")
            or row.get("中文名")
            or row.get("cn")
            or row.get("cn_name")
            or row.get("CN_Name (Chinese)")
            or row.get("CN_Name")
            or row.get("CN_Name(Chinese)")
        )
        en_name = (
            row.get("英文名称")
            or row.get("英文名")
            or row.get("en")
            or row.get("display_en")
            or row.get("Internal_Name (English)")
            or row.get("Internal_Name")
            or row.get("InternalName")
        )
        category_text = (
            row.get("Category")
            or row.get("category")
            or row.get("类别")
            or row.get("分类")
        )

        type_id_int = _parse_int(id_text)
        cn_name_text = str(cn_name or "").strip()
        en_name_text = str(en_name or "").strip()
        category_note_text = str(category_text or "").strip()
        if cn_name_text == "":
            raise ValueError(f"missing 中文名称 for ID={type_id_int}")

        node_data_entry = node_entry_by_id.get(int(type_id_int))
        scope = _normalize_scope_from_node_data_entry(node_data_entry)

        if bool(validate_against_graph_generater):
            if cn_name_text not in semantic_id_by_scope_and_name.get(scope, {}):
                invalid_node_names.append(
                    {
                        "type_id": int(type_id_int),
                        "scope": scope,
                        "cn_name": cn_name_text,
                        "en_name": en_name_text,
                    }
                )

        key = str(int(type_id_int))
        old = mapping_obj.get(key)

        if old is None:
            updated_new += 1
            old_entry: Dict[str, Any] = {}
        elif not isinstance(old, dict):
            raise TypeError(f"existing mapping entry is not dict: type_id={key}")
        else:
            updated_existing += 1
            old_entry = dict(old)

        old_name = str(old_entry.get("graph_generater_node_name") or "").strip()
        if old_name != "" and old_name != cn_name_text:
            overwritten_name += 1

        merged = dict(old_entry)
        merged["scope"] = scope
        merged["graph_generater_node_name"] = cn_name_text

        # semantic_id：若已有则保留；否则尽量从 NodeDef 里补齐
        if str(merged.get("semantic_id") or "").strip() == "":
            merged["semantic_id"] = str(semantic_id_by_scope_and_name.get(scope, {}).get(cn_name_text, "") or "")

        if str(merged.get("confidence") or "").strip() == "":
            merged["confidence"] = "manual"

        if str(merged.get("notes") or "").strip() == "":
            note_parts: List[str] = []
            if en_name_text != "":
                note_parts.append(f"internal_or_en={en_name_text}")
            if category_note_text != "":
                note_parts.append(f"category={category_note_text}")
            merged["notes"] = (
                ("人工映射：" + ", ".join(note_parts)) if note_parts else "人工映射：批量导入"
            )

        mapping_obj[key] = merged

    # 写回（按数值 key 排序，便于 diff/检索）
    ordered: Dict[str, Any] = {}
    for k in _sorted_mapping_keys(mapping_obj):
        ordered[str(k)] = mapping_obj.get(k)
    mapping_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "input_csv": str(Path(input_csv_path).resolve()),
        "mapping_json": str(mapping_path),
        "rows": len(rows),
        "updated_new": int(updated_new),
        "updated_existing": int(updated_existing),
        "overwritten_name": int(overwritten_name),
        "invalid_node_names_count": len(invalid_node_names),
        "invalid_node_names_sample": invalid_node_names[:50],
    }

    if report_json_path is not None:
        out_path = resolve_output_file_path_in_out_dir(Path(report_json_path))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="导入 ID→中文名 CSV 到 node_type_semantic_map.json")
    parser.add_argument("--input-csv", required=True, help="输入 CSV（列：ID, 中文名称, 英文名称）")
    parser.add_argument(
        "--mapping-json",
        dest="mapping_json_path",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="node_type_semantic_map.json 路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument("--report-json", dest="report_json_path", default=None, help="可选：输出导入报告 JSON")
    parser.add_argument("--no-validate", dest="no_validate", action="store_true", help="可选：跳过与 Graph_Generater 节点库的名称校验")
    parser.add_argument(
        "--include-composite",
        dest="include_composite",
        action="store_true",
        help="可选：校验时包含复合节点（默认不包含；通常不要开）",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = apply_csv_to_mapping(
        input_csv_path=Path(args.input_csv),
        mapping_json_path=Path(args.mapping_json_path),
        report_json_path=(Path(args.report_json_path) if args.report_json_path is not None else None),
        validate_against_graph_generater=(not bool(args.no_validate)),
        include_composite=bool(args.include_composite),
    )

    print("=" * 80)
    print("导入完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




