from __future__ import annotations

"""
workspace_root 解析与初始化（唯一真源）。

目标：
- 统一推导工作区根目录（workspace_root），避免多套规则导致路径漂移/缓存跑偏。
- 覆盖三类形态：
  1) 源码仓库形态：包含 engine/、app/ 等目录（通常也包含 constraints.txt/pyrightconfig.json）
  2) 便携版形态：exe 同级外置 assets/资源库
  3) “直接运行节点图脚本”场景：从目标文件向上推断 workspace_root，并在必要时注入 settings。

注意：
- 本模块不吞异常；解析失败应尽早暴露。
- workspace_root 的“单一真源”仍为 Settings.set_config_path(workspace_root) 注入的 Settings._workspace_root。
"""

import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence


_DEFAULT_SEARCH_MAX_DEPTH = 25
_DEFAULT_BOOTSTRAP_MAX_DEPTH = 12


def is_frozen() -> bool:
    """是否处于 PyInstaller 冻结运行环境。"""
    return bool(getattr(sys, "frozen", False))


def get_frozen_workspace_root_or_none() -> Optional[Path]:
    """冻结运行时的默认工作区根目录：exe 所在目录。"""
    if not is_frozen():
        return None
    return Path(sys.executable).resolve().parent


def looks_like_workspace_root(candidate: Path) -> bool:
    """判断 candidate 是否像是“工作区根目录（workspace_root）”。

    判定规则（统一口径）：
    - 便携版：存在 `assets/资源库/`
    - 源码仓库：存在 `engine/` 与 `app/`，并且存在 `constraints.txt` 或 `pyrightconfig.json`
    """
    if not isinstance(candidate, Path):
        return False
    if not candidate.is_dir():
        return False

    portable_markers_ok = (candidate / "assets" / "资源库").is_dir()

    repo_dirs_ok = (candidate / "engine").is_dir() and (candidate / "app").is_dir()
    repo_sentinel_ok = (candidate / "constraints.txt").is_file() or (candidate / "pyrightconfig.json").is_file()
    repo_markers_ok = repo_dirs_ok and repo_sentinel_ok

    return bool(portable_markers_ok or repo_markers_ok)


def _iter_parent_dirs_inclusive(start_path: Path) -> Iterable[Path]:
    cursor = start_path if start_path.is_dir() else start_path.parent
    yield cursor
    for parent in cursor.parents:
        yield parent


def infer_workspace_root_or_none(
    start_path: Path,
    *,
    max_depth: int = _DEFAULT_SEARCH_MAX_DEPTH,
) -> Optional[Path]:
    """从 start_path 向上推断 workspace_root；找不到则返回 None。"""
    for depth, candidate in enumerate(_iter_parent_dirs_inclusive(start_path)):
        if depth > int(max_depth):
            break
        if looks_like_workspace_root(candidate):
            return candidate
    return None


def infer_workspace_root_from_paths_or_none(
    start_paths: Sequence[Path],
    *,
    max_depth: int = _DEFAULT_SEARCH_MAX_DEPTH,
) -> Optional[Path]:
    """从多个起点向上推断 workspace_root；按 start_paths 顺序优先。"""
    for start in list(start_paths):
        if not isinstance(start, Path):
            continue
        inferred = infer_workspace_root_or_none(start.resolve(), max_depth=max_depth)
        if inferred is not None:
            return inferred
    return None


def _normalize_explicit_root(explicit_root: Path) -> Path:
    candidate_root = explicit_root.expanduser()
    if not candidate_root.is_absolute():
        candidate_root = (Path.cwd() / candidate_root)
    return candidate_root.resolve()


def default_workspace_root() -> Path:
    """默认 workspace_root：冻结运行取 exe 目录；源码运行取仓库根目录（engine/utils/..）。"""
    frozen_root = get_frozen_workspace_root_or_none()
    if frozen_root is not None:
        return frozen_root
    # engine/utils/workspace.py -> <repo>/engine/utils/workspace.py
    return Path(__file__).resolve().parents[2]


def resolve_workspace_root(
    explicit_root: str | Path | None = None,
    *,
    start_paths: Optional[Sequence[Path]] = None,
) -> Path:
    """统一解析 workspace_root。

    优先级：
    1) 显式传入 explicit_root
    2) 冻结运行（exe 目录）
    3) 从 start_paths/cwd/本模块路径向上推断
    4) 兜底：默认 workspace_root（源码仓库根目录）
    """
    if isinstance(explicit_root, Path):
        return _normalize_explicit_root(explicit_root)
    if isinstance(explicit_root, str) and explicit_root.strip():
        return _normalize_explicit_root(Path(explicit_root.strip()))

    frozen_root = get_frozen_workspace_root_or_none()
    if frozen_root is not None:
        return frozen_root

    search_roots: list[Path] = []
    if start_paths:
        search_roots.extend([Path(p) for p in start_paths if isinstance(p, Path)])
    # 兼容部分调用方未显式提供 start_paths：依次尝试 cwd 与本模块路径。
    search_roots.append(Path.cwd())
    search_roots.append(Path(__file__).resolve())

    inferred = infer_workspace_root_from_paths_or_none(search_roots, max_depth=_DEFAULT_SEARCH_MAX_DEPTH)
    if inferred is not None:
        return inferred

    return default_workspace_root()


def get_injected_workspace_root_or_none() -> Optional[Path]:
    """从 settings 注入的单一真源读取 workspace_root（若未注入则返回 None）。"""
    from engine.configs.settings import Settings

    injected_root = getattr(Settings, "_workspace_root", None)
    return injected_root if isinstance(injected_root, Path) else None


def init_settings_for_workspace(*, workspace_root: Path, load_user_settings: bool = False) -> None:
    """统一初始化 settings 的 workspace_root，并可选加载用户设置。"""
    from engine.configs.settings import settings

    settings.set_config_path(Path(workspace_root).resolve())
    if load_user_settings:
        settings.load()


def ensure_settings_workspace_root(
    *,
    explicit_root: str | Path | None = None,
    start_paths: Optional[Sequence[Path]] = None,
    load_user_settings: bool = False,
) -> Path:
    """确保 settings 已注入 workspace_root，并返回最终使用的 workspace_root。

    说明：
    - 若未显式指定 explicit_root，且 Settings._workspace_root 已注入且看起来合法，则直接复用；
    - 否则按统一规则 resolve workspace_root，并写入 settings。
    """
    injected_root = get_injected_workspace_root_or_none()
    if explicit_root is None and injected_root is not None and looks_like_workspace_root(injected_root):
        # 重要：即便 workspace_root 已注入，也应尊重 load_user_settings=True 的请求。
        # 典型场景：某入口先注入了 workspace_root（未加载用户设置），随后另一入口希望加载用户设置以对齐 UI 配置。
        if load_user_settings:
            from engine.configs.settings import settings

            settings.load()
        return injected_root

    workspace_root = resolve_workspace_root(explicit_root, start_paths=start_paths)
    init_settings_for_workspace(workspace_root=workspace_root, load_user_settings=load_user_settings)
    return workspace_root


def render_workspace_bootstrap_lines(
    *,
    project_root_var: str = "PROJECT_ROOT",
    assets_root_var: str = "ASSETS_ROOT",
    max_depth: int = _DEFAULT_BOOTSTRAP_MAX_DEPTH,
) -> list[str]:
    """生成“向上找 workspace_root + 注入 sys.path”的源码行（供代码生成器复用）。

    备注：生成的代码不依赖 engine/app，保证在 sys.path 注入前也可执行。
    """
    depth = int(max_depth)
    if depth <= 0:
        depth = _DEFAULT_BOOTSTRAP_MAX_DEPTH

    lines: list[str] = []
    lines.append("# 让该文件可在任意工作目录下直接运行：推导 workspace_root 并注入 project_root/assets 到 sys.path（不要注入 app 目录）")
    lines.append("import sys")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append(f"if getattr(sys, 'frozen', False):")
    lines.append(f"    {project_root_var} = Path(sys.executable).resolve().parent")
    lines.append("else:")
    lines.append(f"    {project_root_var} = Path(__file__).resolve()")
    lines.append(f"    for _ in range({depth}):")
    lines.append(f"        _candidate = {project_root_var} if {project_root_var}.is_dir() else {project_root_var}.parent")
    lines.append("        # 便携版/资源库形态（assets/资源库 同级）")
    lines.append("        if (_candidate / 'assets' / '资源库').is_dir():")
    lines.append(f"            {project_root_var} = _candidate")
    lines.append("            break")
    lines.append("        # 源码仓库形态（engine/ + app/）")
    lines.append("        if (_candidate / 'engine').is_dir() and (_candidate / 'app').is_dir():")
    lines.append(f"            {project_root_var} = _candidate")
    lines.append("            break")
    lines.append(f"        {project_root_var} = _candidate.parent")
    lines.append(f"{assets_root_var} = {project_root_var} / 'assets'")
    lines.append(f"if str({project_root_var}) not in sys.path:")
    lines.append(f"    sys.path.insert(0, str({project_root_var}))")
    lines.append(f"if str({assets_root_var}) not in sys.path:")
    lines.append(f"    sys.path.insert(1, str({assets_root_var}))")
    return lines


