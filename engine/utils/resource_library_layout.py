from __future__ import annotations

from pathlib import Path
from typing import List


# 新命名：项目存档（一个项目存档一个文件夹）。
PROJECT_ARCHIVE_LIBRARY_DIRNAME = "项目存档"

# 对外常量：保持历史常量名不变，但语义升级为“项目存档”。
PACKAGE_LIBRARY_DIRNAME = PROJECT_ARCHIVE_LIBRARY_DIRNAME

SHARED_LIBRARY_DIRNAME = "共享"

# 默认未归属项目存档：用于承载无法推断归属的“新建资源”落点。
# 约定使用中文目录名，便于直接作为项目目录管理与归档。
DEFAULT_UNCLASSIFIED_PACKAGE_ID = "测试项目"


def get_shared_root_dir(resource_library_root: Path) -> Path:
    """返回共享资源根目录（位于资源库根目录下）。"""
    return resource_library_root / SHARED_LIBRARY_DIRNAME


def get_packages_root_dir(resource_library_root: Path) -> Path:
    """返回项目存档资源根目录（位于资源库根目录下）。
    """
    return resource_library_root / PROJECT_ARCHIVE_LIBRARY_DIRNAME


def get_default_unclassified_package_root_dir(resource_library_root: Path) -> Path:
    """返回“默认未归属项目存档”的资源根目录。

    约定：当保存资源时无法推断其应落在哪个项目存档根目录，统一落到该目录，避免写入 `共享/` 或误落到资源库根目录。
    """
    return get_packages_root_dir(resource_library_root) / DEFAULT_UNCLASSIFIED_PACKAGE_ID


def discover_package_resource_roots(resource_library_root: Path) -> List[Path]:
    """发现所有项目存档的资源根目录列表（每个 package_id 一个子目录）。"""
    packages_root = get_packages_root_dir(resource_library_root)
    if not packages_root.exists():
        return []
    if not packages_root.is_dir():
        return []

    package_dirs = [path for path in packages_root.iterdir() if path.is_dir()]
    # 稳定排序，避免扫描顺序随文件系统变化导致缓存/输出不稳定
    return sorted(package_dirs, key=lambda path: path.name.casefold())


def discover_resource_root_directories(resource_library_root: Path) -> List[Path]:
    """发现资源库中需要参与扫描的“资源根目录”集合。

    约定：
    - shared 根：<resource_library_root>/共享
    - package 根：<resource_library_root>/项目存档/<package_id>
    """
    roots: List[Path] = []

    shared_root = get_shared_root_dir(resource_library_root)
    if shared_root.exists() and shared_root.is_dir():
        roots.append(shared_root)

    roots.extend(discover_package_resource_roots(resource_library_root))
    return roots


def normalize_active_package_id(package_id: str | None) -> str | None:
    """归一化“当前项目存档作用域”的 package_id。

    约定：
    - None / ""：表示仅共享根；
    - UI 特殊视图 ID（global_view/unclassified_view）不绑定任何项目存档，等同于仅共享根；
    - 其它非空字符串：表示共享根 + 指定项目存档根目录。
    """
    normalized = str(package_id or "").strip()
    if normalized in {"global_view", "unclassified_view"}:
        return None
    return normalized or None


def discover_scoped_resource_root_directories(
    resource_library_root: Path,
    *,
    active_package_id: str | None,
) -> List[Path]:
    """按“共享根 + 当前项目存档根”的作用域收敛资源根目录列表。

    设计目标：与 ResourceManager/ResourceIndexBuilder 的作用域语义保持一致，避免在全局聚合视图中
    混入其它项目存档目录导致重复 ID 或归属错觉。
    """
    roots: List[Path] = []

    shared_root = get_shared_root_dir(resource_library_root)
    if shared_root.exists() and shared_root.is_dir():
        roots.append(shared_root)

    normalized = normalize_active_package_id(active_package_id)
    if normalized:
        package_root = get_packages_root_dir(resource_library_root) / normalized
        if package_root.exists() and package_root.is_dir():
            roots.append(package_root)

    return roots










def find_containing_resource_root(resource_library_root: Path, file_path: Path) -> Path | None:
    """根据给定文件路径，找到其所属的资源根目录（共享/项目存档/<package_id>）。

    说明：
    - 返回“最深”的匹配根目录，避免在未来出现更深层嵌套时误判为 legacy 根。
    - 找不到匹配时返回 None。
    """
    resolved_file_path = file_path.resolve()
    resolved_parts = resolved_file_path.parts
    candidate_roots = discover_resource_root_directories(resource_library_root)
    candidate_roots_sorted = sorted(
        candidate_roots,
        key=lambda path: len(path.resolve().parts),
        reverse=True,
    )
    for resource_root in candidate_roots_sorted:
        root_parts = resource_root.resolve().parts
        if len(resolved_parts) < len(root_parts):
            continue
        if resolved_parts[: len(root_parts)] == root_parts:
            return resource_root
    return None


