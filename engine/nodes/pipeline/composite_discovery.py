from __future__ import annotations

from pathlib import Path
from typing import List


def discover_composite_files(workspace_path: Path) -> List[Path]:
    """
    发现复合节点定义文件（不导入）。

    路径约定：工作区下 `assets/资源库/复合节点库/**/*.py`
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")
    root = workspace_path.resolve()
    composites_dir = (root / "assets" / "资源库" / "复合节点库").resolve()
    if not composites_dir.exists():
        return []
    files: List[Path] = []
    for py in composites_dir.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        files.append(py)
    # 稳定排序
    return sorted(files, key=lambda p: str(p.as_posix()).lower())

