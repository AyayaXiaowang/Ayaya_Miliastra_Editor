from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from pathlib import Path


def find_workspace_root(current_path: Path) -> Path:
    search_directories = [current_path.parent] + list(current_path.parents)
    for directory in search_directories:
        marker_file = directory / "pyrightconfig.json"
        if marker_file.is_file():
            return directory
    return current_path.parent


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="节点图代码资源校验（资源库专用）")
    parser.add_argument(
        "--cache",
        dest="use_cache",
        action="store_true",
        help="启用校验缓存（默认禁用，避免规则升级后缓存掩盖新错误）",
    )
    parser.add_argument(
        "--strict",
        "--strict-entity-wire-only",
        dest="strict_entity_wire_only",
        action="store_true",
        help="实体入参严格模式，仅允许连线/事件参数（默认关闭）",
    )
    return parser.parse_args(argv)


def main() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

    args = parse_args(sys.argv[1:])

    current_file = Path(__file__).resolve()
    workspace_path = find_workspace_root(current_file)
    if str(workspace_path) not in sys.path:
        sys.path.insert(0, str(workspace_path))

    # 为布局/注册表上下文等依赖 workspace_root 的模块提供入口信息
    from engine.configs.settings import settings
    settings.set_config_path(workspace_path)

    from engine.validate import validate_files

    # 约定：本脚本与被校验的节点图目录同级（<package>/节点图/校验节点图.py）
    graphs_root = current_file.parent
    if not graphs_root.exists():
        print("节点图目录不存在，跳过校验。")
        return

    # 节点图目录中允许存在辅助脚本（如校验脚本本身），
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

    report = validate_files(
        target_files,
        workspace_path,
        strict_entity_wire_only=args.strict_entity_wire_only,
        use_cache=args.use_cache,
    )
    issues = list(report.issues)
    error_count = len([issue for issue in issues if issue.level == "error"])
    warning_count = len([issue for issue in issues if issue.level == "warning"])

    print(f"验证完成：错误 {error_count} 条，警告 {warning_count} 条。")

    issues_by_file: dict[str, list[object]] = defaultdict(list)
    for issue in issues:
        issue_file = str(getattr(issue, "file", "") or "<unknown>")
        issues_by_file[issue_file].append(issue)

    # 输出明细（按文件分组）
    for issue_file, grouped in sorted(issues_by_file.items(), key=lambda item: item[0]):
        error_items = [i for i in grouped if getattr(i, "level", "") == "error"]
        warning_items = [i for i in grouped if getattr(i, "level", "") == "warning"]
        if not error_items and not warning_items:
            continue
        status = "FAILED" if error_items else "WARN"
        print(f"\n[{status}] {issue_file} (errors: {len(error_items)}, warnings: {len(warning_items)})")
        for item in error_items + warning_items:
            level = str(getattr(item, "level", "") or "")
            category = str(getattr(item, "category", "") or "")
            code = str(getattr(item, "code", "") or "")
            message = str(getattr(item, "message", "") or "")
            print(f"  - [{level}] [{category}/{code}] {message}")

    if error_count == 0 and warning_count == 0:
        print("\n节点图代码资源在引擎校验下通过。")
        return

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()


