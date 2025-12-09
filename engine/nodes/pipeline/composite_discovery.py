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
        # 仅将实际复合节点定义文件纳入解析范围：
        # - 跳过 `__init__.py` 与以“校验”命名的工具/校验脚本（例如 `校验复合节点库.py`）；
        # - 其余 *.py 文件需满足类格式复合节点约定（带 @composite_class 装饰器）。
        if py.name == "__init__.py":
            continue
        if "校验" in py.stem:
            continue
        files.append(py)
    # 稳定排序
    return sorted(files, key=lambda p: str(p.as_posix()).lower())

