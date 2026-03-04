from __future__ import annotations

"""
inspect_ui_guid.py

目标：
- 给定一个“运行时看到的 UI 相关整数”（通常为 107374xxxx），快速反查：
  - 它在 ui_guid_registry.json 中对应哪些 ui_key（若存在）
  - 它在 base `.gil` 的 UI record 列表中对应哪个 record（若存在）
  - 若它是某个组容器 guid：列出其直接子控件（parent==该 guid 的 records）

说明：
- 该工具只读：不会修改 `.gil` 或 registry。
"""

import argparse
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import repo_root
from ugc_file_tools.ui.guid_resolution import (
    extract_ui_record_component_type_ids as _extract_ui_record_component_type_ids,
    extract_ui_record_primary_guid as _extract_ui_record_primary_guid,
    extract_ui_record_primary_name as _extract_ui_record_primary_name,
)

def _load_registry(*, workspace_root: Path, package_id: str) -> tuple[dict[str, int], Path]:
    from engine.utils.cache.cache_paths import get_ui_guid_registry_cache_file
    from ugc_file_tools.ui.guid_registry_format import load_ui_guid_registry_mapping

    path = get_ui_guid_registry_cache_file(Path(workspace_root).resolve(), str(package_id)).resolve()
    mapping = load_ui_guid_registry_mapping(path)
    return mapping, path


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="反查 UI guid 对应的 ui_key / UI record 信息（只读）。")
    parser.add_argument("--guid", required=True, type=int, help="要查询的 guid（通常为 107374xxxx）")
    parser.add_argument("--package-id", required=True, help="项目存档 package_id（用于定位运行时缓存 registry）")
    parser.add_argument(
        "--workspace-root",
        default=str(repo_root()),
        help="Graph_Generater 仓库根目录（默认自动定位）",
    )
    parser.add_argument("--gil", default="", help="可选：提供 base .gil，用于从 UI records 中反查 name/parent")

    args = parser.parse_args(list(argv) if argv is not None else None)
    target_guid = int(args.guid)
    package_id = str(args.package_id).strip()
    if package_id == "":
        raise ValueError("package_id 不能为空")

    workspace_root = Path(args.workspace_root).resolve()

    registry, registry_path = _load_registry(workspace_root=workspace_root, package_id=package_id)

    matched_keys = sorted([k for k, v in registry.items() if int(v) == int(target_guid)], key=lambda s: s.casefold())

    print("=" * 80)
    print("UI GUID 反查：")
    print(f"- guid: {target_guid}")
    print(f"- package_id: {package_id}")
    print(f"- registry: {str(registry_path)}")
    print(f"- registry_matches_total: {len(matched_keys)}")
    for k in matched_keys[:50]:
        print(f"  - {k}")
    if len(matched_keys) > 50:
        print("  - ... (more)")

    gil_path_text = str(args.gil or "").strip()
    if gil_path_text == "":
        print("=" * 80)
        return

    gil_path = Path(gil_path_text).resolve()
    if not gil_path.is_file():
        raise FileNotFoundError(str(gil_path))

    from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object

    raw = dump_gil_to_raw_json_object(gil_path)
    root_data = raw.get("4")
    if not isinstance(root_data, dict):
        raise ValueError("gil dump 缺少根字段 '4'")
    field9 = root_data.get("9")
    if not isinstance(field9, dict):
        raise ValueError("gil dump 缺少字段 '4/9'")
    record_list = field9.get("502")
    if not isinstance(record_list, list):
        raise ValueError("gil dump 缺少字段 '4/9/502'")

    guid_to_record: Dict[int, Dict[str, Any]] = {}
    children_by_parent: Dict[int, list[int]] = {}

    for rec in record_list:
        if not isinstance(rec, dict):
            continue
        guid = _extract_ui_record_primary_guid(rec)
        if guid is None:
            continue
        guid_to_record[int(guid)] = rec
        parent = rec.get("504")
        if isinstance(parent, int):
            children_by_parent.setdefault(int(parent), []).append(int(guid))

    rec = guid_to_record.get(int(target_guid))
    if rec is None:
        print("- gil_record: <not found>")
    else:
        name = _extract_ui_record_primary_name(rec)
        parent = rec.get("504") if isinstance(rec.get("504"), int) else None
        types = sorted(_extract_ui_record_component_type_ids(rec))
        print("- gil_record:")
        print(f"  - name: {name}")
        print(f"  - parent_504: {parent}")
        print(f"  - component_type_ids: {types}")

    # 若该 guid 是父节点，列出子项
    children = sorted(children_by_parent.get(int(target_guid), []))
    print(f"- gil_children_total(parent==guid): {len(children)}")
    for child_guid in children[:50]:
        child = guid_to_record.get(int(child_guid))
        child_name = _extract_ui_record_primary_name(child) if isinstance(child, dict) else None
        child_types = sorted(_extract_ui_record_component_type_ids(child)) if isinstance(child, dict) else []
        print(f"  - {child_guid} name={child_name} component_type_ids={child_types}")
    if len(children) > 50:
        print("  - ... (more)")

    print("=" * 80)


if __name__ == "__main__":
    main()



