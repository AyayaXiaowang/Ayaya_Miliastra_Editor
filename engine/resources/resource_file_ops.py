"""资源文件操作服务 - 封装路径、文件名与目录管理。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from engine.configs.resource_types import ResourceType
from engine.utils.graph_path_inference import infer_graph_type_and_folder_path
from engine.utils.name_utils import sanitize_resource_filename
from engine.utils.path_utils import normalize_slash
from .resource_filename_policy import resource_type_prefers_name_over_cached_filename


class ResourceFileOps:
    """封装资源相关的文件系统操作（路径构造、文件名规范与目录管理）。"""

    def __init__(self, resource_library_dir: Path) -> None:
        self.resource_library_dir = resource_library_dir

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """清理文件名，移除 Windows 不允许的特殊字符。"""
        return sanitize_resource_filename(name)

    @staticmethod
    def sanitize_folder_path(folder_path: str) -> str:
        """标准化文件夹路径（统一使用 / 作为分隔符）。"""
        return normalize_slash(folder_path).strip("/")

    @staticmethod
    def is_valid_folder_name(name: str) -> bool:
        """检查文件夹名称是否合法（Windows 规范）。"""
        if not name or name.strip() != name:
            return False

        invalid_chars = r'\/:*?"<>|'
        for char in invalid_chars:
            if char in name:
                return False

        if name.endswith("."):
            return False

        return True

    def get_resource_directory(self, resource_type: ResourceType, resource_root_dir: Path | None = None) -> Path:
        """获取资源类型对应的根目录。"""
        base_root = resource_root_dir or self.resource_library_dir
        return base_root / resource_type.value

    def get_resource_file_path(
        self,
        resource_type: ResourceType,
        resource_id: str,
        id_to_filename_cache: Dict[ResourceType, Dict[str, str]],
        extension: Optional[str] = None,
        graph_metadata: Optional[dict] = None,
        resource_name: Optional[str] = None,
        resource_root_dir: Optional[Path] = None,
    ) -> Path:
        """获取资源文件的完整路径（优先使用 name，其次使用 ID）。

        对于节点图，会结合 graph_type 和 folder_path 生成分层目录。
        """
        resource_dir = self.get_resource_directory(resource_type, resource_root_dir=resource_root_dir)

        if extension is None:
            extension = ".py" if resource_type == ResourceType.GRAPH else ".json"

        filename: Optional[str] = None
        cached_bucket = id_to_filename_cache.get(resource_type, {})

        # 默认行为：若已有文件名缓存，则继续沿用，避免因为显示名称调整导致物理文件频繁重命名。
        use_cached_filename = resource_id in cached_bucket

        # 一些资源在保存时显式以“业务名称”驱动物理文件名（覆盖缓存文件名），便于在资源库中按名称直接识别 JSON。
        # 规则的单一真源在 `resource_filename_policy.py`，避免与索引扫描的 name 同步策略漂移。
        if resource_name and resource_type_prefers_name_over_cached_filename(resource_type):
            use_cached_filename = False

        if use_cached_filename:
            filename = cached_bucket[resource_id]
        elif resource_name:
            filename = self.sanitize_filename(resource_name)
        else:
            filename = resource_id

        if resource_type == ResourceType.GRAPH and graph_metadata:
            graph_type = graph_metadata.get("graph_type", "server")
            folder_path = graph_metadata.get("folder_path", "")

            graph_dir = resource_dir / graph_type
            if folder_path:
                graph_dir = graph_dir / folder_path

            return graph_dir / f"{filename}{extension}"

        return resource_dir / f"{filename}{extension}"

    def infer_graph_type_and_folder_path(self, graph_file: Path) -> tuple[str, str]:
        """从节点图文件路径推断 (graph_type, folder_path)。

        约定节点图位于：
        - `<resource_library_dir>/节点图/<server|client>/<folder...>/<file>.py`

        返回：
        - graph_type: "server"/"client"（若无法推断则返回空字符串）
        - folder_path: 相对 type 目录的文件夹路径（例如 "模板示例/子目录"，根目录返回空字符串）
        """
        graph_type, folder_path = infer_graph_type_and_folder_path(graph_file)
        return graph_type, folder_path

    def ensure_graph_folder(
        self,
        graph_type: str,
        folder_path: str,
        *,
        resource_root_dir: Path | None = None,
    ) -> Path:
        """创建（或确保存在）给定 graph_type 与 folder_path 对应的文件夹。"""
        base_root = resource_root_dir or self.resource_library_dir
        folder_dir = base_root / "节点图" / graph_type / folder_path
        folder_dir.mkdir(parents=True, exist_ok=True)
        return folder_dir

    def rename_graph_directory(
        self,
        graph_type: str,
        old_folder_path: str,
        new_folder_path: str,
        *,
        resource_root_dir: Path | None = None,
    ) -> None:
        """物理重命名节点图目录结构（不触碰图数据本身）。"""
        base_root = resource_root_dir or self.resource_library_dir
        old_dir = base_root / "节点图" / graph_type / old_folder_path
        new_dir = base_root / "节点图" / graph_type / new_folder_path
        if old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            old_dir.rename(new_dir)

    def remove_empty_graph_folder_tree(
        self,
        graph_type: str,
        folder_path: str,
        *,
        resource_root_dir: Path | None = None,
    ) -> bool:
        """尝试删除空的节点图文件夹及其空父目录。"""
        base_root = resource_root_dir or self.resource_library_dir
        folder_dir = base_root / "节点图" / graph_type / folder_path
        if not folder_dir.exists():
            return False

        if any(folder_dir.iterdir()):
            return False

        folder_dir.rmdir()

        parent = folder_dir.parent
        type_dir = base_root / "节点图" / graph_type
        while parent != type_dir and parent.exists():
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        return True


