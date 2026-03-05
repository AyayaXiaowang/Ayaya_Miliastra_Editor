from __future__ import annotations

"""
sync_ui_guid_registry_from_gil.py

目标：
- 将 base `.gil` 中现有的 UI record（控件/组件组）与运行时缓存 `ui_guid_registry.json` 做一次对齐校准；
- 解决“节点图里 ui_key 回填到的整数 ID 与存档里真实控件 GUID 不一致”的问题。

特点：
- 不写回 `.gil` 本体，只会更新 `app/runtime/cache/ui_artifacts/<package_id>/ui_guid_registry.json`；
- `ui_guid_registry.json` 的保存带历史留档（ui_guid_registry_history/ + history.jsonl）。
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import repo_root


def _resolve_registry_path(*, workspace_root: Path, package_id: str, registry_path: Optional[str]) -> Path:
    if registry_path is not None and str(registry_path).strip() != "":
        return Path(registry_path).resolve()

    from engine.utils.cache.cache_paths import get_ui_guid_registry_cache_file

    return get_ui_guid_registry_cache_file(Path(workspace_root).resolve(), str(package_id)).resolve()


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="基于 base .gil 的 UI records 校准 ui_guid_registry.json（用于修复 ui_key 回填错 ID）。"
    )
    parser.add_argument("--gil", required=True, help="输入 base .gil 文件路径（以其 UI records 为准）")
    parser.add_argument("--package-id", required=True, help="项目存档 package_id（用于定位运行时缓存 ui_guid_registry.json）")
    parser.add_argument(
        "--workspace-root",
        default=str(repo_root()),
        help="Graph_Generater 仓库根目录（默认自动定位）",
    )
    parser.add_argument(
        "--registry-path",
        default=None,
        help="可选：显式指定 ui_guid_registry.json 路径（不传则按 workspace_root+package_id 推断）",
    )
    parser.add_argument(
        "--print-keys",
        default="HTML导入_界面布局__btn_unselect__btn_item,HTML导入_界面布局__btn_unselect__group",
        help="可选：校准后打印这些 ui_key 的 guid（逗号分隔）",
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

    # 读取 base `.gil`（dump-json 风格对象）
    from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object

    base_raw_dump_object = dump_gil_to_raw_json_object(Path(args.gil))

    # 加载 registry（允许旧格式/手工格式）
    from ugc_file_tools.ui.guid_registry_format import load_ui_guid_registry_mapping

    ui_key_to_guid_registry: Dict[str, int] = load_ui_guid_registry_mapping(registry_path)

    before = dict(ui_key_to_guid_registry)

    # 复用写回链路的“保守自愈”算法（通过公开 API，避免跨模块导入私有符号）
    from ugc_file_tools.node_graph_writeback.pipeline import maybe_sync_ui_key_guid_registry_with_base_ui_records

    after = maybe_sync_ui_key_guid_registry_with_base_ui_records(
        ui_key_to_guid_registry=ui_key_to_guid_registry,
        registry_path=registry_path,
        base_raw_dump_object=base_raw_dump_object,
    )

    # after 可能是 None（例如 registry_path 不存在且不允许写回）；此处仍输出当前 in-memory
    effective_after = after if after is not None else ui_key_to_guid_registry

    changed_total = 0
    for k, v in effective_after.items():
        if int(before.get(k, 0)) != int(v):
            changed_total += 1

    print("=" * 80)
    print("UI GUID registry 校准完成：")
    print(f"- package_id: {package_id}")
    print(f"- base_gil:   {str(Path(args.gil).resolve())}")
    print(f"- registry:   {str(registry_path)}")
    print(f"- changed_total: {changed_total}")

    keys_text = str(args.print_keys or "").strip()
    if keys_text != "":
        keys = [k.strip() for k in keys_text.split(",") if k.strip() != ""]
        if keys:
            print("- selected_keys:")
            for k in keys:
                print(f"  - {k}: {effective_after.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



