from __future__ import annotations

from pathlib import Path
from typing import List


def discover_implementation_files(workspace_path: Path) -> List[Path]:
    """
    发现实现侧待解析的文件列表。
    
    约定：
    - 扫描 workspace/plugins/nodes/**.py（排除 __init__.py 与 shared 辅助模块、以及 registry.py）
    - 仅返回文件路径列表，不做导入，避免副作用
    - server 优先排序（便于后续合并策略保持一致性）
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")
    workspace_root = workspace_path.resolve()
    impl_root = (workspace_root / "plugins" / "nodes").resolve()
    if not impl_root.exists():
        return []

    discovered: List[Path] = []
    for py in impl_root.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        # 排除 shared 下的辅助模块
        if (impl_root / "shared") in py.parents:
            continue
        # 新位置下排除静态注册表文件（不作为实现源参与解析）
        if py.name == "registry.py" and (impl_root / "registry.py") == py:
            continue
        discovered.append(py)

    def _priority(p: Path) -> int:
        lower = str(p.as_posix()).lower()
        if "/server/" in lower or "/server_" in lower or lower.endswith("/server.py"):
            return 0
        return 1

    return sorted(discovered, key=_priority)


