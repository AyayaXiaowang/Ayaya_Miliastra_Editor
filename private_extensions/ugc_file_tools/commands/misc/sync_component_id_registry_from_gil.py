from __future__ import annotations

"""
sync_component_id_registry_from_gil.py

目标：
- 从 base `.gil` 中抽取“元件名 → 元件ID”的映射，并写入运行时缓存 `component_id_registry.json`；
- 用于节点图写回/导出阶段支持 `component_key:<元件名>` 占位符自动回填元件ID，避免手填 1000xxxx。

特点：
- 不写回 `.gil` 本体，只会更新 registry（带历史留档 component_id_registry_history/）。
"""

import argparse
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ugc_file_tools.component_id_registry import save_component_id_registry_file
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import repo_root


def _resolve_registry_path(*, workspace_root: Path, package_id: str, registry_path: Optional[str]) -> Path:
    if registry_path is not None and str(registry_path).strip() != "":
        return Path(registry_path).resolve()

    from engine.utils.cache.cache_paths import get_component_id_registry_cache_file

    return get_component_id_registry_cache_file(Path(workspace_root).resolve(), str(package_id)).resolve()


def _first_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _try_extract_component_name_from_record(record: Dict[str, Any]) -> Optional[str]:
    """
    从 dump-json record 中抽取“实例名称”。

    经验结构（从样本对照抽取）：
    - record['1'] 为模板条目 ID（prefab_id / template_entry_id；通常为 10 位整数）
    - record['2'] 为模板类型码（template_type_code；常见为 1000xxxx/2000xxxx，同类型模板会重复）
    - record['6'] 为 repeated message 列表
      - 某个条目包含 record['11']['1'] 的字符串（名称）
    """
    v6 = record.get("6")
    items = v6 if isinstance(v6, list) else ([v6] if isinstance(v6, dict) else [])
    for it in items:
        if not isinstance(it, dict):
            continue
        inner11 = _first_dict(it.get("11"))
        if not isinstance(inner11, dict):
            continue
        name_val = inner11.get("1")
        if isinstance(name_val, str):
            name = str(name_val).strip()
            if name != "":
                return name
    return None


def _collect_component_name_to_id_from_payload_root(payload_root: Dict[str, Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return

        # 候选：包含 (template_entry_id, template_type_code, name)
        # 注意：节点图 `元件ID` 端口需要的是“模板条目 ID”（field_1），而不是“模板类型码”（field_2）。
        template_type_code = value.get("2")
        template_entry_id = value.get("1")
        if isinstance(template_type_code, int) and isinstance(template_entry_id, int):
            if int(template_entry_id) > 1_000_000_000 and 1 <= int(template_type_code) <= 999_999_999:
                name = _try_extract_component_name_from_record(value)
                if name is not None:
                    if name in mapping and int(mapping[name]) != int(template_entry_id):
                        raise ValueError(
                            f"同名元件映射到不同ID：name={name!r} a={mapping[name]} b={int(template_entry_id)}"
                        )
                    mapping[name] = int(template_entry_id)

        for _k, v in value.items():
            visit(v)

    visit(payload_root)
    return mapping


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="基于 base .gil 抽取“元件名→元件ID”并写入 component_id_registry.json（用于 component_key 回填）。"
    )
    parser.add_argument("--gil", required=True, help="输入 base .gil 文件路径（以其元件记录为准）")
    parser.add_argument("--package-id", required=True, help="项目存档 package_id（用于定位运行时缓存 component_id_registry.json）")
    parser.add_argument(
        "--workspace-root",
        default=str(repo_root()),
        help="Graph_Generater 仓库根目录（默认自动定位）",
    )
    parser.add_argument(
        "--registry-path",
        default=None,
        help="可选：显式指定 component_id_registry.json 路径（不传则按 workspace_root+package_id 推断）",
    )
    parser.add_argument(
        "--print-names",
        default="",
        help="可选：写回后打印这些元件名对应的 id（逗号分隔）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    workspace_root = Path(args.workspace_root).resolve()
    package_id = str(args.package_id).strip()
    if package_id == "":
        raise ValueError("package_id 不能为空")

    registry_path = _resolve_registry_path(
        workspace_root=workspace_root,
        package_id=package_id,
        registry_path=args.registry_path,
    )

    from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object

    base_raw_dump_object = dump_gil_to_raw_json_object(Path(args.gil))
    payload_root = base_raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump 对象缺少根字段 '4'（期望为 dict）。")

    name_to_id = _collect_component_name_to_id_from_payload_root(payload_root)
    if not name_to_id:
        raise ValueError("未从该 .gil 中识别到任何元件名→元件ID 记录（可能样本结构不同或未导入元件包）。")

    save_component_id_registry_file(registry_path, name_to_id)

    print("=" * 80)
    print("component_id_registry 写回完成：")
    print(f"- package_id: {package_id}")
    print(f"- base_gil:   {str(Path(args.gil).resolve())}")
    print(f"- registry:   {str(registry_path)}")
    print(f"- mapping_total: {len(name_to_id)}")

    names_text = str(args.print_names or "").strip()
    if names_text != "":
        names = [n.strip() for n in names_text.split(",") if n.strip() != ""]
        if names:
            print("- selected_names:")
            for n in names:
                print(f"  - {n}: {name_to_id.get(n)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



