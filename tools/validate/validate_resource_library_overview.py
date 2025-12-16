from __future__ import annotations

"""
资源库总览校验（CLI）

用途：
- 构建 ResourceManager / PackageIndexManager 的索引上下文；
- 输出资源类型数量、资源总数量、功能包数量等概览信息；
- 作为“资源库与索引结构能否被引擎正常读取”的快速烟雾校验入口。

用法（项目根目录运行）：
  python -X utf8 -m tools.validate.validate_resource_library_overview
"""

import io
import sys
from pathlib import Path


def _configure_stdout_for_windows() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]


def main() -> None:
    _configure_stdout_for_windows()

    if not __package__:
        raise SystemExit(
            "请从项目根目录使用模块方式运行：\n"
            "  python -X utf8 -m tools.validate.validate_resource_library_overview\n"
            "（不再支持通过脚本内 sys.path.insert 的方式运行）"
        )

    workspace_path = Path(__file__).resolve().parents[2]
    from engine.resources import build_resource_index_context

    resource_manager, package_index_manager = build_resource_index_context(workspace_path)

    all_resources = resource_manager.list_all_resources()
    package_infos = package_index_manager.list_packages()

    total_resource_count = sum(len(resource_ids) for resource_ids in all_resources.values())
    package_count = len(package_infos)

    print("=" * 60)
    print("资源库 总览校验")
    print("=" * 60)
    print(f"资源类型数量: {len(all_resources)}")
    print(f"资源总数量: {total_resource_count}")
    print(f"功能包数量: {package_count}")
    print("资源索引与功能包索引已成功构建，基础结构与引擎读取约定一致。")


if __name__ == "__main__":
    main()


