from __future__ import annotations

import io
import sys
from pathlib import Path


def find_workspace_root(current_path: Path) -> Path:
    search_directories = [current_path.parent] + list(current_path.parents)
    for directory in search_directories:
        marker_file = directory / "pyrightconfig.json"
        if marker_file.is_file():
            return directory
    return current_path.parent


def main() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

    current_file = Path(__file__).resolve()
    workspace_path = find_workspace_root(current_file)
    if str(workspace_path) not in sys.path:
        sys.path.insert(0, str(workspace_path))

    # 为布局/注册表上下文等依赖 workspace_root 的模块提供入口信息
    from engine.configs.settings import settings
    settings.set_config_path(workspace_path)

    from engine.validate import validate_files

    graphs_root = workspace_path / "assets" / "资源库" / "节点图"
    if not graphs_root.exists():
        print("节点图目录不存在，跳过校验。")
        return

    # 节点图目录中允许存在辅助文件（如 `_prelude.py`）与校验脚本本身，
    # 这些文件不符合“类结构节点图”格式，应在校验入口中显式跳过。
    target_files = sorted(
        [
            py_file
            for py_file in graphs_root.rglob("*.py")
            if not py_file.name.startswith("_") and "校验" not in py_file.stem
        ],
        key=lambda path: path.as_posix(),
    )

    print("=" * 60)
    print("节点图 代码资源校验")
    print("=" * 60)
    print(f"待校验节点图文件数量: {len(target_files)}")

    report = validate_files(target_files, workspace_path, strict_entity_wire_only=False, use_cache=True)
    error_count = len([issue for issue in report.issues if issue.level == "error"])
    warning_count = len([issue for issue in report.issues if issue.level == "warning"])

    print(f"验证完成：错误 {error_count} 条，警告 {warning_count} 条。")
    if error_count == 0:
        print("节点图代码资源在引擎校验下通过。")


if __name__ == "__main__":
    main()


