from __future__ import annotations

"""
repo_paths.py

集中管理“路径真源”，避免在各脚本里用 `Path(__file__).parents[n]` 这种对目录层级敏感的写法。

约定：
- ugc_file_tools_root(): 返回 `ugc_file_tools/` 目录（本包根目录）
- private_extensions_root(): 返回承载 `ugc_file_tools/` 的父目录（通常为 `private_extensions/`）
- graph_generater_root(): 返回 Graph_Generater 工程根目录（至少包含 engine/assets；通常也包含 app/plugins）
- repo_root(): 兼容别名，等价于 graph_generater_root()

不使用 try/except；路径不存在时由调用方自行校验并抛错。
"""

from pathlib import Path
from typing import Optional


def ugc_file_tools_root() -> Path:
    """返回 `ugc_file_tools/` 的绝对路径。"""
    return Path(__file__).resolve().parent


def ugc_file_tools_builtin_resources_root() -> Path:
    """返回 `ugc_file_tools/builtin_resources/` 的绝对路径。"""
    return ugc_file_tools_root() / "builtin_resources"


def private_extensions_root() -> Path:
    """返回承载 `ugc_file_tools/` 的父目录（通常为 `private_extensions/`）。"""
    return ugc_file_tools_root().parent


def _is_graph_generater_root(path: Path) -> bool:
    p = Path(path)
    # Graph_Generater 根目录的“最小锚点”：
    # - 必须包含 engine/ 与 assets/（这是 ugc_file_tools 写回/读取共享资源所需的稳定目录）
    # - tools/ 在当前仓库结构中并非必需（历史脚本可能存在）；因此仅作为可选锚点。
    # - 为避免误判，额外要求存在 app/ 或 plugins/ 或 tools/ 任一标记目录。
    if not (p / "engine").is_dir():
        return False
    if not (p / "assets").is_dir():
        return False
    if (p / "app").is_dir() or (p / "plugins").is_dir() or (p / "tools").is_dir():
        return True
    return False


def try_find_graph_generater_root(start_path: Optional[Path] = None) -> Path | None:
    """
    尝试定位 Graph_Generater 工程根目录（至少包含 engine/assets；通常也包含 app/plugins）。

    - 优先从 start_path（默认 ugc_file_tools_root）向上扫描。
    - 兼容：当 ugc_file_tools 作为独立仓库时，Graph_Generater 可能位于 sibling 目录 `../Graph_Generater/`。
    """
    start = Path(start_path).resolve() if start_path is not None else ugc_file_tools_root()

    for parent in [start, *start.parents]:
        if _is_graph_generater_root(parent):
            return parent

    candidate = start.parent / "Graph_Generater"
    if _is_graph_generater_root(candidate):
        return candidate

    return None


def graph_generater_root() -> Path:
    """返回 Graph_Generater 工程根目录（找不到则抛错）。"""
    found = try_find_graph_generater_root()
    if found is None:
        raise FileNotFoundError(
            "无法定位 Graph_Generater 根目录（需要包含 engine/assets；通常包含 app/plugins）："
            f"start={str(ugc_file_tools_root())!r}"
        )
    return found


def resolve_graph_generater_root(workspace_root: Path | None = None) -> Path:
    """
    将“工作区根目录”归一化为 Graph_Generater 工程根目录。

    支持两种常见布局：
    - workspace_root 本身就是 Graph_Generater 根目录（至少包含 engine/assets）
    - workspace_root 之下存在子目录 Graph_Generater/（用于历史脚本/外层工作区）
    """
    if workspace_root is None:
        return graph_generater_root()

    root = Path(workspace_root).resolve()
    if _is_graph_generater_root(root):
        return root

    candidate = (root / "Graph_Generater").resolve()
    if _is_graph_generater_root(candidate):
        return candidate

    for parent in [root, *root.parents]:
        if _is_graph_generater_root(parent):
            return parent

    raise FileNotFoundError(
        "无法从 workspace_root 定位 Graph_Generater 根目录（需要包含 engine/assets；通常包含 app/plugins）："
        f"workspace_root={str(root)!r}"
    )


def repo_root() -> Path:
    """兼容：返回 Graph_Generater 工程根目录。"""
    return graph_generater_root()


