from __future__ import annotations

import sys
from pathlib import Path
from typing import List


def _infer_toolchain_root() -> Path:
    """推断“工具链根目录”。

    目的：支持“工作区=外置 assets 目录”场景下，仍能找到节点实现库 `plugins/nodes`：
    - 源码运行：工具链根目录=当前仓库根目录
    - PyInstaller 便携版：工具链根目录=exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    start = Path(__file__).resolve()
    for candidate in (start.parent, *start.parents):
        if (candidate / "plugins" / "nodes").is_dir():
            return candidate
    # 兜底：engine/nodes/pipeline/discovery.py -> repo_root 为 parents[3]
    return start.parents[3]


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
        toolchain_root = _infer_toolchain_root()
        fallback_impl_root = (toolchain_root / "plugins" / "nodes").resolve()
        if fallback_impl_root.exists():
            impl_root = fallback_impl_root
        else:
            return []

    discovered: List[Path] = []
    for py in impl_root.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        # 排除 shared 下的辅助模块
        if (impl_root / "shared") in py.parents:
            continue
        discovered.append(py)

    def _priority(p: Path) -> int:
        lower = str(p.as_posix()).lower()
        if "/server/" in lower or "/server_" in lower or lower.endswith("/server.py"):
            return 0
        return 1

    return sorted(discovered, key=_priority)


