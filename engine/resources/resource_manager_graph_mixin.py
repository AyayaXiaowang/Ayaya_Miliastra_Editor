from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import os

from engine.configs.resource_types import ResourceType
from engine.utils.logging.logger import log_error, log_info, log_warn
from engine.utils.path_utils import normalize_slash
from engine.utils.resource_library_layout import (
    discover_resource_root_directories,
    get_packages_root_dir,
    get_shared_root_dir,
)

from .resource_file_ops import ResourceFileOps


class ResourceManagerGraphMixin:
    """ResourceManager 的节点图列表/文件夹树/路径相关方法。"""

    def list_graphs_by_type(self, graph_type: str) -> List[dict]:
        """列出指定类型的所有节点图

        Args:
            graph_type: 节点图类型 ("server" | "client" | "all")

        Returns:
            节点图信息列表
        """
        graph_ids = self.list_resources(ResourceType.GRAPH)
        graphs = []

        for graph_id in graph_ids:
            graph_meta = self.load_graph_metadata(graph_id)
            if not graph_meta:
                continue
            data_graph_type = graph_meta.get("graph_type", "server")
            folder_path = graph_meta.get("folder_path", "")
            if not folder_path:
                folder_path = self._infer_graph_folder_path(graph_id, data_graph_type)
            folder_path = self.sanitize_folder_path(folder_path) if folder_path else ""
            if graph_type == "all" or data_graph_type == graph_type:
                graphs.append(
                    {
                        "graph_id": graph_id,
                        "name": graph_meta.get("name", "未命名"),
                        "graph_type": data_graph_type,
                        "folder_path": folder_path,
                        "description": graph_meta.get("description", ""),
                    }
                )

        return graphs

    def list_graphs_by_folder(self, folder_path: str) -> List[dict]:
        """列出指定文件夹下的所有节点图

        Args:
            folder_path: 文件夹路径

        Returns:
            节点图信息列表
        """
        target_folder = self.sanitize_folder_path(folder_path)
        graph_ids = self.list_resources(ResourceType.GRAPH)
        graphs = []

        for graph_id in graph_ids:
            graph_meta = self.load_graph_metadata(graph_id)
            if not graph_meta:
                continue
            data_graph_type = graph_meta.get("graph_type", "server")
            graph_folder = graph_meta.get("folder_path", "")
            if not graph_folder:
                graph_folder = self._infer_graph_folder_path(graph_id, data_graph_type)
            graph_folder = self.sanitize_folder_path(graph_folder) if graph_folder else ""
            if graph_folder != target_folder:
                continue
            graphs.append(
                {
                    "graph_id": graph_id,
                    "name": graph_meta.get("name", "未命名"),
                    "graph_type": data_graph_type,
                    "folder_path": target_folder,
                    "description": graph_meta.get("description", ""),
                }
            )

        return graphs

    def _infer_graph_folder_path(self, graph_id: str, graph_type: str) -> str:
        """基于文件路径推断节点图所在文件夹（用于旧图未写入 folder_path 的场景）。"""
        graph_paths = self.resource_index.get(ResourceType.GRAPH, {})
        file_path = graph_paths.get(graph_id)
        if not isinstance(file_path, Path):
            return ""
        inferred_graph_type, inferred_folder_path = self._file_ops.infer_graph_type_and_folder_path(file_path)
        if not inferred_graph_type:
            return ""
        if inferred_graph_type != graph_type:
            return ""
        return self.sanitize_folder_path(inferred_folder_path) if inferred_folder_path else ""

    def get_all_graph_folders(self, *, resource_roots: List[Path] | None = None) -> Dict[str, List[str]]:
        """获取节点图的文件夹结构（支持按资源根目录过滤）。

        Args:
            resource_roots: 可选的资源根目录列表（例如：共享根/某个项目存档根）。
                - None：扫描资源库下全部资源根（共享 + 全部项目存档）。
                - 非空：仅扫描传入的 resource_roots，避免 UI 在“当前项目视图”下看到其它项目的目录。

        Returns:
            {"server": [folder_paths], "client": [folder_paths]}
        """
        folders = {"server": set(), "client": set()}

        effective_roots = (
            list(discover_resource_root_directories(self.resource_library_dir))
            if resource_roots is None
            else [root for root in list(resource_roots) if isinstance(root, Path)]
        )
        resolved_roots = [root.resolve() for root in effective_roots]

        def _is_under_any_root(file_path: Path) -> bool:
            resolved_file = file_path.resolve()
            for root in resolved_roots:
                if hasattr(resolved_file, "is_relative_to"):
                    if resolved_file.is_relative_to(root):
                        return True
                else:
                    root_parts = root.parts
                    file_parts = resolved_file.parts
                    if len(file_parts) >= len(root_parts) and file_parts[: len(root_parts)] == root_parts:
                        return True
            return False

        # 1) 从节点图轻量元数据中收集文件夹路径（避免触发完整解析与自动布局）
        graph_file_paths = self.list_resource_file_paths(ResourceType.GRAPH)
        graph_ids = self.list_resources(ResourceType.GRAPH)
        for graph_id in graph_ids:
            if resource_roots is not None:
                file_path = graph_file_paths.get(str(graph_id))
                if not isinstance(file_path, Path):
                    continue
                if not _is_under_any_root(file_path):
                    continue

            graph_meta = self.load_graph_metadata(graph_id)
            if graph_meta:
                data_graph_type = graph_meta.get("graph_type", "server")
                folder_path = graph_meta.get("folder_path", "") or self._infer_graph_folder_path(
                    graph_id, data_graph_type
                )
                folder_path = self.sanitize_folder_path(folder_path) if folder_path else ""

                if folder_path and data_graph_type in folders:
                    folders[data_graph_type].add(folder_path)

        # 2) 扫描文件系统中的空文件夹（仅在 effective_roots 范围内枚举）
        ignored_folder_names = {"__pycache__"}

        for data_graph_type in ["server", "client"]:
            for resource_root in effective_roots:
                type_dir = resource_root / "节点图" / data_graph_type
                if not type_dir.exists():
                    continue
                # 这里不使用 Path.rglob：在 Windows 上若遇到异常目录项（权限/非法名/损坏符号链接等），
                # rglob 可能直接抛异常并中断，导致上层文件夹树被清空。
                # os.walk 内部会跳过不可访问的目录（可选 onerror），更适合用于“尽力枚举”型 UI 展示。
                for current_dir, sub_dirs, _file_names in os.walk(type_dir):
                    current_dir_path = Path(current_dir)
                    for sub_dir_name in list(sub_dirs):
                        candidate_dir = current_dir_path / sub_dir_name
                        rel_path = candidate_dir.relative_to(type_dir)
                        rel_parts = getattr(rel_path, "parts", ())
                        if not rel_parts:
                            continue
                        if any(part in ignored_folder_names for part in rel_parts):
                            continue
                        folder_path = normalize_slash(str(rel_path))
                        folders[data_graph_type].add(folder_path)

        # 转换为列表并排序
        return {
            "server": sorted(list(folders["server"])),
            "client": sorted(list(folders["client"])),
        }

    def create_graph_folder(self, graph_type: str, folder_path: str) -> bool:
        """创建节点图文件夹（即使为空）

        Args:
            graph_type: 节点图类型 ("server" 或 "client")
            folder_path: 文件夹路径（如 "角色/NPC"）

        Returns:
            是否创建成功
        """
        if graph_type not in ["server", "client"]:
            log_error("[错误] 无效的节点图类型: {}", graph_type)
            return False

        # 文件夹创建应尊重当前项目存档作用域：
        # - 在“具体项目存档”视图下：写入该项目存档根目录
        # - 在“共享资源”视图下：写入共享根目录
        active_package_id = str(self._active_package_id or "").strip()
        if active_package_id:
            write_root_dir = get_packages_root_dir(self.resource_library_dir) / active_package_id
        else:
            write_root_dir = get_shared_root_dir(self.resource_library_dir)
        folder_dir = self._file_ops.ensure_graph_folder(
            graph_type,
            folder_path,
            resource_root_dir=write_root_dir,
        )
        log_info("[OK] 创建文件夹: {}", folder_dir)
        return True

    def is_valid_folder_name(self, name: str) -> bool:
        """检查文件夹名称是否合法（Windows 规范）"""
        return ResourceFileOps.is_valid_folder_name(name)

    def sanitize_folder_path(self, folder_path: str) -> str:
        """标准化文件夹路径（统一使用 / 作为分隔符）"""
        return ResourceFileOps.sanitize_folder_path(folder_path)

    def move_graph_to_folder(self, graph_id: str, new_folder_path: str) -> None:
        """移动节点图到指定文件夹"""
        # 加载节点图数据
        graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            raise ValueError(f"节点图 {graph_id} 不存在")

        # 更新 folder_path
        new_folder_path = self.sanitize_folder_path(new_folder_path)
        graph_data["folder_path"] = new_folder_path
        graph_data["updated_at"] = datetime.now().isoformat()

        # 保存（save_resource 会自动处理物理移动）
        self.save_resource(ResourceType.GRAPH, graph_id, graph_data)
        log_info("[OK] 已将节点图 {} 移动到文件夹: {}", graph_id, new_folder_path or "<根>")

    def rename_graph_folder(self, graph_type: str, old_folder_path: str, new_folder_path: str) -> None:
        """重命名节点图文件夹（递归更新所有子图）"""
        old_folder_path = self.sanitize_folder_path(old_folder_path)
        new_folder_path = self.sanitize_folder_path(new_folder_path)

        if not old_folder_path:
            raise ValueError("不能重命名根目录")

        if old_folder_path == new_folder_path:
            return

        # 收集所有受影响的节点图（包括子文件夹）
        affected_graphs = []
        graph_ids = self.list_resources(ResourceType.GRAPH)

        for graph_id in graph_ids:
            graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
            if graph_data and graph_data.get("graph_type") == graph_type:
                folder_path = graph_data.get("folder_path", "")

                # 检查是否在目标文件夹或其子文件夹中
                if folder_path == old_folder_path or folder_path.startswith(old_folder_path + "/"):
                    affected_graphs.append((graph_id, graph_data, folder_path))

        log_info("[重命名文件夹] 受影响的节点图数量: {}", len(affected_graphs))

        # 批量更新所有受影响的节点图
        for graph_id, graph_data, old_path in affected_graphs:
            # 计算新路径
            if old_path == old_folder_path:
                updated_path = new_folder_path
            else:
                # 子路径：替换前缀
                relative_path = old_path[len(old_folder_path) + 1 :]
                updated_path = f"{new_folder_path}/{relative_path}" if new_folder_path else relative_path

            graph_data["folder_path"] = updated_path
            graph_data["updated_at"] = datetime.now().isoformat()
            self.save_resource(ResourceType.GRAPH, graph_id, graph_data)
            log_info("  - 更新 {}: {} -> {}", graph_id, old_path, updated_path)

        # 物理移动目录
        resource_roots = self.get_current_resource_roots()
        for resource_root in resource_roots:
            old_dir = resource_root / "节点图" / graph_type / old_folder_path
            new_dir = resource_root / "节点图" / graph_type / new_folder_path
            if not old_dir.exists():
                continue
            self._file_ops.rename_graph_directory(
                graph_type,
                old_folder_path,
                new_folder_path,
                resource_root_dir=resource_root,
            )
            log_info("[OK] 物理目录已重命名: {} -> {}", old_dir, new_dir)

    def get_graph_file_path(self, graph_id: str) -> Optional[Path]:
        """获取节点图的物理文件路径"""
        file_path = self._state.get_file_path(ResourceType.GRAPH, graph_id)
        if file_path:
            return file_path

        graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
        if graph_data:
            return self._state.get_file_path(ResourceType.GRAPH, graph_id)

        return None

    def get_resource_file_mtime(self, resource_type: ResourceType, resource_id: str) -> float | None:
        """获取资源文件的 mtime（用于保存冲突检测）。"""
        resource_file: Path | None

        if resource_type == ResourceType.GRAPH:
            resource_file = self.get_graph_file_path(str(resource_id))
        else:
            resource_file = self._state.get_file_path(resource_type, str(resource_id))
            if resource_file is None:
                resource_file = self._file_ops.get_resource_file_path(
                    resource_type,
                    str(resource_id),
                    self.id_to_filename_cache,
                )

        if resource_file is None or not resource_file.exists():
            return None

        return float(resource_file.stat().st_mtime)

    def remove_graph_folder_if_empty(self, graph_type: str, folder_path: str) -> bool:
        """删除空的节点图文件夹"""
        folder_path = self.sanitize_folder_path(folder_path)

        if not folder_path:
            raise ValueError("不能删除根目录")

        # 检查是否有节点图在此文件夹
        graphs = self.list_graphs_by_folder(folder_path)
        if graphs:
            log_warn("[警告] 文件夹 {} 非空，包含 {} 个节点图", folder_path, len(graphs))
            return False

        # 物理删除目录（仅当完全为空时）
        removed_any = False
        resource_roots = self.get_current_resource_roots()
        for resource_root in resource_roots:
            removed = self._file_ops.remove_empty_graph_folder_tree(
                graph_type,
                folder_path,
                resource_root_dir=resource_root,
            )
            if removed:
                removed_any = True
                log_info(
                    "[OK] 已删除空文件夹: {}",
                    resource_root / "节点图" / graph_type / folder_path,
                )
        if not removed_any:
            log_warn("[警告] 文件夹 {} 包含子文件夹或其他文件", folder_path)
        return removed_any



