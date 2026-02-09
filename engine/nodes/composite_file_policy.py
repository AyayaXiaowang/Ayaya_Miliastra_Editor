from __future__ import annotations

from pathlib import Path
from typing import List

from engine.utils.resource_library_layout import (
    PROJECT_ARCHIVE_LIBRARY_DIRNAME,
    SHARED_LIBRARY_DIRNAME,
    discover_scoped_resource_root_directories,
    discover_resource_root_directories,
)
from engine.utils.runtime_scope import get_active_package_id

_RESOURCE_LIBRARY_PARTS = ("assets", "资源库")
_COMPOSITE_LIBRARY_DIRNAME = "复合节点库"


def is_composite_definition_file(path: Path) -> bool:
    """
    判断给定路径是否为“复合节点定义文件”。

    约定（与资源库目录规则保持一致）：
    - 仅根据**所在目录**判定：位于任一资源根目录下的 `复合节点库/`（含子目录）下的 `.py` 文件即视为候选；
      资源根目录包括：`assets/资源库/共享/`、`assets/资源库/项目存档/<package_id>/`；
    - 文件名**不再要求**以特定前缀命名；
    - 仍跳过 `__init__.py`（模块初始化文件不应被视为复合节点定义）。
    """
    if not isinstance(path, Path):
        raise TypeError("path 必须是 pathlib.Path 实例")
    if path.suffix != ".py":
        return False
    if path.name == "__init__.py":
        return False

    parts = path.parts
    if len(parts) < len(_RESOURCE_LIBRARY_PARTS) + 1:
        return False

    # 允许绝对/相对路径；只要路径片段中出现连续的以下任一结构，即判定为复合节点库文件：
    # - assets/资源库/共享/复合节点库
    # - assets/资源库/项目存档/<package_id>/复合节点库
    for idx in range(0, len(parts) - len(_RESOURCE_LIBRARY_PARTS) + 1):
        if parts[idx : idx + len(_RESOURCE_LIBRARY_PARTS)] != _RESOURCE_LIBRARY_PARTS:
            continue

        # shared：assets/资源库/共享/复合节点库
        if (
            idx + 3 < len(parts)
            and parts[idx + 2] == SHARED_LIBRARY_DIRNAME
            and parts[idx + 3] == _COMPOSITE_LIBRARY_DIRNAME
        ):
            return True

        # packages：assets/资源库/项目存档/<package_id>/复合节点库
        if (
            idx + 4 < len(parts)
            and parts[idx + 2] == PROJECT_ARCHIVE_LIBRARY_DIRNAME
            and parts[idx + 4] == _COMPOSITE_LIBRARY_DIRNAME
        ):
            return True

    return False


def discover_composite_library_dirs(workspace_path: Path) -> List[Path]:
    """发现工作区中所有“复合节点库根目录”。

    返回的每个目录都形如：
    - assets/资源库/共享/复合节点库
    - assets/资源库/项目存档/<package_id>/复合节点库
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")

    workspace_root = workspace_path.resolve()
    resource_library_root = (workspace_root / "assets" / "资源库").resolve()
    resource_roots = discover_resource_root_directories(resource_library_root)
    composite_dirs = []
    for resource_root in resource_roots:
        composite_dir = (resource_root / _COMPOSITE_LIBRARY_DIRNAME).resolve()
        if composite_dir.exists() and composite_dir.is_dir():
            composite_dirs.append(composite_dir)
    return sorted(composite_dirs, key=lambda p: str(p.as_posix()).lower())


def discover_scoped_composite_library_dirs(
    workspace_path: Path,
    *,
    active_package_id: str | None,
) -> List[Path]:
    """按作用域发现工作区中所有“复合节点库根目录”。

    约定：
    - active_package_id=None：仅共享根目录下的 `复合节点库/`；
    - active_package_id=str：共享根 + 指定项目存档根目录下的 `复合节点库/`。
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")

    workspace_root = workspace_path.resolve()
    resource_library_root = (workspace_root / "assets" / "资源库").resolve()
    resource_roots = discover_scoped_resource_root_directories(
        resource_library_root,
        active_package_id=active_package_id,
    )
    composite_dirs: List[Path] = []
    for resource_root in resource_roots:
        composite_dir = (resource_root / _COMPOSITE_LIBRARY_DIRNAME).resolve()
        if composite_dir.exists() and composite_dir.is_dir():
            composite_dirs.append(composite_dir)
    # 保持资源根目录顺序：共享根在前，项目存档根在后（用于覆盖语义与稳定输出）。
    return composite_dirs


def discover_composite_definition_files(workspace_path: Path) -> List[Path]:
    """
    发现工作区中的复合节点定义文件（不导入）。

    注意：复合节点发现默认遵循运行期作用域 `active_package_id`（共享根 + 当前项目存档根），
    避免跨项目存档全量聚合导致复合节点同名/同 ID 覆盖或串包。
    """
    active_package_id = get_active_package_id()
    return discover_scoped_composite_definition_files(
        workspace_path,
        active_package_id=active_package_id,
    )


def discover_scoped_composite_definition_files(
    workspace_path: Path,
    *,
    active_package_id: str | None,
) -> List[Path]:
    """按作用域发现工作区中的复合节点定义文件（不导入）。

    扫描范围：
    - `assets/资源库/共享/复合节点库/**/*.py`
    - （可选）`assets/资源库/项目存档/<active_package_id>/复合节点库/**/*.py`
    """
    files: List[Path] = []
    for composites_dir in discover_scoped_composite_library_dirs(
        workspace_path,
        active_package_id=active_package_id,
    ):
        py_paths = sorted(
            (path for path in composites_dir.rglob("*.py") if path.is_file()),
            key=lambda p: str(p.as_posix()).lower(),
        )
        for py in py_paths:
            if not is_composite_definition_file(py):
                continue
            files.append(py)
    # 保持“共享根在前、项目存档根在后”的顺序，供调用侧实现稳定的覆盖语义。
    return files


