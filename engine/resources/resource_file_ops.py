"""资源文件操作服务 - 封装路径、文件名与目录管理。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from engine.configs.resource_types import ResourceType
from engine.utils.name_utils import sanitize_resource_filename


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
        return folder_path.replace("\\", "/").strip("/")

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

    def get_resource_directory(self, resource_type: ResourceType) -> Path:
        """获取资源类型对应的根目录。"""
        return self.resource_library_dir / resource_type.value

    def get_resource_file_path(
        self,
        resource_type: ResourceType,
        resource_id: str,
        id_to_filename_cache: Dict[ResourceType, Dict[str, str]],
        extension: Optional[str] = None,
        graph_metadata: Optional[dict] = None,
        resource_name: Optional[str] = None,
    ) -> Path:
        """获取资源文件的完整路径（优先使用 name，其次使用 ID）。

        对于节点图，会结合 graph_type 和 folder_path 生成分层目录。
        """
        resource_dir = self.get_resource_directory(resource_type)

        if extension is None:
            extension = ".py" if resource_type == ResourceType.GRAPH else ".json"

        filename: Optional[str] = None
        cached_bucket = id_to_filename_cache.get(resource_type, {})

        # 默认行为：若已有文件名缓存，则继续沿用，避免因为显示名称调整导致物理文件频繁重命名。
        use_cached_filename = resource_id in cached_bucket

        # 一些资源在保存时显式以“业务名称”驱动物理文件名，便于在资源库中按名称直接识别 JSON。
        # 这里包含：
        # - 部分战斗预设与管理配置：聊天频道、装备数据、主镜头、预设点、外围系统、局内存档管理
        # - 以及典型多记录管理配置：计时器、关卡变量、技能资源、商店模板、路径、背景音乐、光源、
        #   实体布设组、单位标签、护盾、扫描标签、UI 布局与 UI 控件模板等。
        resources_prefer_name_over_cached = {
            ResourceType.CHAT_CHANNEL,
            ResourceType.EQUIPMENT_DATA,
            ResourceType.MAIN_CAMERA,
            ResourceType.PRESET_POINT,
            ResourceType.PERIPHERAL_SYSTEM,
            ResourceType.SAVE_POINT,
            # 多条记录的管理配置
            ResourceType.TIMER,
            ResourceType.LEVEL_VARIABLE,
            ResourceType.SKILL_RESOURCE,
            ResourceType.SHOP_TEMPLATE,
            ResourceType.PATH,
            ResourceType.BACKGROUND_MUSIC,
            ResourceType.LIGHT_SOURCE,
            ResourceType.ENTITY_DEPLOYMENT_GROUP,
            ResourceType.UNIT_TAG,
            ResourceType.SCAN_TAG,
            ResourceType.SHIELD,
            ResourceType.UI_LAYOUT,
            ResourceType.UI_WIDGET_TEMPLATE,
        }
        if resource_name and resource_type in resources_prefer_name_over_cached:
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

    def ensure_graph_folder(self, graph_type: str, folder_path: str) -> Path:
        """创建（或确保存在）给定 graph_type 与 folder_path 对应的文件夹。"""
        folder_dir = self.resource_library_dir / "节点图" / graph_type / folder_path
        folder_dir.mkdir(parents=True, exist_ok=True)
        return folder_dir

    def rename_graph_directory(self, graph_type: str, old_folder_path: str, new_folder_path: str) -> None:
        """物理重命名节点图目录结构（不触碰图数据本身）。"""
        old_dir = self.resource_library_dir / "节点图" / graph_type / old_folder_path
        new_dir = self.resource_library_dir / "节点图" / graph_type / new_folder_path
        if old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            old_dir.rename(new_dir)

    def remove_empty_graph_folder_tree(self, graph_type: str, folder_path: str) -> bool:
        """尝试删除空的节点图文件夹及其空父目录。"""
        folder_dir = self.resource_library_dir / "节点图" / graph_type / folder_path
        if not folder_dir.exists():
            return False

        if any(folder_dir.iterdir()):
            return False

        folder_dir.rmdir()

        parent = folder_dir.parent
        type_dir = self.resource_library_dir / "节点图" / graph_type
        while parent != type_dir and parent.exists():
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        return True


