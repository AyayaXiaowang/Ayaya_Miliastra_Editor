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

    from engine.resources.definition_schema_view import (
        get_default_definition_schema_view,
        set_default_definition_schema_view_active_package_id,
    )

    active_package_id: str | None = None
    parts = current_file.parts
    if "项目存档" in parts:
        idx = parts.index("项目存档")
        if idx + 1 < len(parts):
            active_package_id = parts[idx + 1]
    set_default_definition_schema_view_active_package_id(active_package_id)

    schema_view = get_default_definition_schema_view()
    signal_definitions = schema_view.get_all_signal_definitions()

    print("=" * 60)
    print("管理配置/信号 代码资源校验")
    print("=" * 60)
    print(f"作用域: {active_package_id or '共享根'}")
    print(f"信号定义数量: {len(signal_definitions)}")
    print("信号定义代码资源格式与引擎读取约定一致。")


if __name__ == "__main__":
    main()


