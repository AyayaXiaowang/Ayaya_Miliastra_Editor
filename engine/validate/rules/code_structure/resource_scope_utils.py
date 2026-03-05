from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.utils.resource_library_layout import (
    find_containing_resource_root,
    get_packages_root_dir,
    get_shared_root_dir,
)


@dataclass(frozen=True)
class GraphResourceScope:
    """节点图文件的“资源根归属”信息（用于跨项目引用约束与报错提示）。"""

    workspace_path: Path
    resource_library_root: Path
    shared_root_dir: Path
    packages_root_dir: Path
    graph_resource_root_dir: Path
    graph_owner_root_id: str

    def is_definition_root_allowed(self, definition_root_dir: Path) -> bool:
        """允许：当前项目资源根 / 共享资源根。"""
        resolved_definition = definition_root_dir.resolve()
        return resolved_definition in {
            self.graph_resource_root_dir.resolve(),
            self.shared_root_dir.resolve(),
        }

    def suggest_current_project_signal_dir(self) -> Path:
        return self.graph_resource_root_dir / "管理配置" / "信号"

    def suggest_current_project_struct_dir(self, kind_dirname: str = "") -> Path:
        base = self.graph_resource_root_dir / "管理配置" / "结构体定义"
        if kind_dirname:
            return base / kind_dirname
        return base


def try_build_graph_resource_scope(workspace_path: Path, file_path: Path) -> GraphResourceScope | None:
    """根据节点图源码文件路径推断其所属资源根目录与“当前项目”。

    只有当文件位于资源库目录结构（共享/项目存档）下时才返回 scope；
    否则返回 None（例如 tests/ 临时文件）。
    """
    resource_library_root = workspace_path / "assets" / "资源库"
    if not resource_library_root.is_dir():
        return None

    graph_resource_root = find_containing_resource_root(resource_library_root, file_path)
    if graph_resource_root is None:
        return None

    shared_root_dir = get_shared_root_dir(resource_library_root)
    packages_root_dir = get_packages_root_dir(resource_library_root)
    graph_owner_root_id = resource_root_id(
        shared_root_dir=shared_root_dir,
        packages_root_dir=packages_root_dir,
        resource_root_dir=graph_resource_root,
    )
    return GraphResourceScope(
        workspace_path=workspace_path,
        resource_library_root=resource_library_root,
        shared_root_dir=shared_root_dir,
        packages_root_dir=packages_root_dir,
        graph_resource_root_dir=graph_resource_root,
        graph_owner_root_id=graph_owner_root_id,
    )


def resource_root_id(
    *,
    shared_root_dir: Path,
    packages_root_dir: Path,
    resource_root_dir: Path,
) -> str:
    """返回资源根目录的“归属 ID”：共享 / <package_id>。"""
    resolved_root = resource_root_dir.resolve()
    if resolved_root == shared_root_dir.resolve():
        return "共享"
    if resolved_root.parent == packages_root_dir.resolve():
        return resource_root_dir.name
    return resource_root_dir.name


def relative_path_text(workspace_path: Path, path: Path) -> str:
    """尽力生成相对于 workspace_root 的路径字符串（不使用 try/except）。"""
    workspace = workspace_path.resolve()
    target = path.resolve()
    workspace_parts = workspace.parts
    target_parts = target.parts
    if len(target_parts) >= len(workspace_parts) and target_parts[: len(workspace_parts)] == workspace_parts:
        rel_parts = target_parts[len(workspace_parts) :]
        return "/".join(rel_parts) if rel_parts else "."
    return target.as_posix()


__all__ = [
    "GraphResourceScope",
    "try_build_graph_resource_scope",
    "resource_root_id",
    "relative_path_text",
]


