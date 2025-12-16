from __future__ import annotations

import io
import sys
from pathlib import Path

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root
else:
    from _bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root

# Windows 控制台输出编码为 UTF-8（与其他 tools 保持一致）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

# 允许 `python tools/print_node_counts.py` 直接运行（脚本目录在 sys.path，但 workspace root 不一定在）
ensure_workspace_root_on_sys_path()

from engine.nodes import get_node_registry  # noqa: E402


def compute_workspace_path() -> Path:
    # 与 tools/_bootstrap.py 中的推导保持一致
    return get_workspace_root()


def main() -> None:
    workspace_path = compute_workspace_path()
    node_registry = get_node_registry(workspace_path, include_composite=True)
    node_library = node_registry.get_library()
    print(f"NODE_COUNT: {len(node_library)}")
    categories = sorted({node_key.split("/")[0] for node_key in node_library.keys()})
    print("CATEGORIES:", ", ".join(categories))


if __name__ == '__main__':
    main()


