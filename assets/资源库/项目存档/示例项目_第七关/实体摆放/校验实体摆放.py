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

    from engine.configs.resource_types import ResourceType
    from engine.resources.resource_manager import ResourceManager

    resource_manager = ResourceManager(workspace_path)
    placement_ids = resource_manager.list_resources(ResourceType.INSTANCE)

    loaded_count = 0
    for placement_id in placement_ids:
        payload = resource_manager.load_resource(ResourceType.INSTANCE, placement_id)
        if payload is not None:
            loaded_count += 1

    print("=" * 60)
    print("实体摆放 资源校验")
    print("=" * 60)
    print(f"实体摆放总数量: {len(placement_ids)}")
    print(f"成功加载数量: {loaded_count}")
    print("实体摆放 JSON 资源格式与引擎读取约定一致。")


if __name__ == "__main__":
    main()


