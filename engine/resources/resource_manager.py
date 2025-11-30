"""资源管理器 - 统一管理所有离散化资源的增删改查"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json

from engine.configs.resource_types import ResourceType
from engine.resources.graph_cache_manager import GraphCacheManager
from engine.resources.management_naming_rules import (
    get_display_name_field_for_type,
    get_id_field_for_type,
)
from engine.resources.resource_index_builder import ResourceIndexBuilder
from engine.utils.logging.logger import log_error, log_info, log_warn
from engine.utils.cache.cache_paths import get_node_cache_dir
from .graph_resource_service import GraphResourceService
from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_index_service import ResourceIndexService
from .resource_state import ResourceIndexState, ResourceReferenceIndex
from .resource_store import JsonResourceStore


class ResourceManager:
    """资源管理器 - 管理所有离散化存储的资源"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        index_state: Optional[ResourceIndexState] = None,
        reference_state: Optional[ResourceReferenceIndex] = None,
        cache_service: Optional[ResourceCacheService] = None,
        file_ops: Optional[ResourceFileOps] = None,
        index_builder: Optional[ResourceIndexBuilder] = None,
        graph_cache_manager: Optional[GraphCacheManager] = None,
        resource_store: Optional[JsonResourceStore] = None,
        index_service: Optional[ResourceIndexService] = None,
        graph_service: Optional[GraphResourceService] = None,
        max_cache_size: int = 500,
    ):
        """初始化资源管理器。

        Args:
            workspace_path: 工作空间路径（Graph_Generater目录）
            index_state: 可注入的索引状态，实现内存/Mock 替换
            reference_state: 可注入的引用索引实现
            cache_service: 自定义缓存服务（便于测试或注入空实现）
            file_ops: 自定义文件操作实现
            index_builder: 自定义索引构建器
            graph_cache_manager: 自定义图缓存管理器
            resource_store: JSON资源存储实现
            index_service: 自定义索引服务
            graph_service: 自定义图资源服务
            max_cache_size: 资源缓存最大尺寸
        """
        self.workspace_path = workspace_path
        self.resource_library_dir = workspace_path / "assets" / "资源库"

        self._state = index_state or ResourceIndexState()
        self.resource_index: Dict[ResourceType, Dict[str, Path]] = self._state.resource_paths
        self.name_to_id_index: Dict[ResourceType, Dict[str, str]] = self._state.name_to_id_map
        self.id_to_filename_cache: Dict[ResourceType, Dict[str, str]] = self._state.filename_cache

        self._references = reference_state or ResourceReferenceIndex()
        self.reference_index: Dict[str, List[str]] = self._references.references

        self._max_cache_size = max_cache_size

        self._resource_index_builder = index_builder or ResourceIndexBuilder(
            self.workspace_path, self.resource_library_dir
        )
        self._graph_cache_manager = graph_cache_manager or GraphCacheManager(self.workspace_path)

        self._cache_service = cache_service or ResourceCacheService(
            max_cache_size=self._max_cache_size
        )
        self._file_ops = file_ops or ResourceFileOps(self.resource_library_dir)
        self._resource_store = resource_store or JsonResourceStore(
            self._file_ops,
            self._cache_service,
            self._state,
        )
        self._index_service = index_service or ResourceIndexService(
            self.workspace_path,
            self._resource_index_builder,
            self._file_ops,
            self._state,
        )
        self._graph_service = graph_service or GraphResourceService(
            self.workspace_path,
            self._file_ops,
            self._cache_service,
            self._graph_cache_manager,
            self._state,
        )
        
        # 确保目录结构存在
        self._ensure_directories()
        
        # 加载“文件名同步提示”的去重状态并构建索引（委托索引服务）
        self._index_service.load_name_sync_state()
        self._index_service.build_index()

    # ===== 资源索引持久化缓存（启动加速） =====

    def _save_persistent_resource_index(self) -> None:
        """将当前内存中的资源索引写入磁盘缓存。

        注意：实际写入逻辑委托给 `ResourceIndexBuilder`，以保持职责单一。
        """
        self._index_service.save_persistent_index()

    def _ensure_directories(self) -> None:
        """确保所有资源目录存在"""
        self.resource_library_dir.mkdir(exist_ok=True)
        
        for resource_type in ResourceType:
            resource_dir = self._file_ops.get_resource_directory(resource_type)
            resource_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """清理文件名，移除Windows不允许的特殊字符。

        实现委托给 `ResourceFileOps.sanitize_filename`，保持资源层统一规则。
        """
        return ResourceFileOps.sanitize_filename(name)
    
    def _generate_unique_filename(self, directory: Path, base_name: str, extension: str) -> str:
        """生成唯一的文件名（避免冲突）
        
        Args:
            directory: 目标目录
            base_name: 基础文件名（不含扩展名）
            extension: 文件扩展名（含点号，如".json"）
        
        Returns:
            唯一的文件名（不含扩展名）
        """
        filename = base_name
        counter = 2
        while (directory / f"{filename}{extension}").exists():
            filename = f"{base_name}_{counter}"
            counter += 1
        return filename
    
    def clear_cache(self, resource_type: Optional[ResourceType] = None, resource_id: Optional[str] = None) -> None:
        """清除缓存
        
        Args:
            resource_type: 如果指定，只清除该类型的缓存；否则清除所有
            resource_id: 如果指定，只清除该资源的缓存
        """
        self._cache_service.clear(resource_type, resource_id)
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息
        
        Returns:
            缓存统计字典，包含：
            - cache_size: 当前缓存条目数
            - max_cache_size: 最大缓存条目数
            - cache_hits: 缓存命中次数
            - cache_misses: 缓存未命中次数
            - hit_rate: 缓存命中率（百分比）
        """
        return self._cache_service.get_stats()
    
    # ===== 缓存清理（公开API） =====
    def clear_persistent_graph_cache(self) -> int:
        """清空磁盘上的节点图持久化缓存（app/runtime/cache/graph_cache）。
        
        Returns:
            被删除的缓存文件数量
        """
        return self._graph_cache_manager.clear_all_persistent_graph_cache()
    
    def clear_persistent_resource_index_cache(self) -> int:
        """清空磁盘上的资源索引缓存（app/runtime/cache/resource_cache/resource_index.json）。"""
        return self._index_service.clear_persistent_cache()
    
    def clear_persistent_graph_cache_for(self, graph_id: str) -> int:
        """按图ID清除节点图的持久化缓存文件（app/runtime/cache/graph_cache/<graph_id>.json）。
        
        Returns:
            被删除的缓存文件数量（0或1）
        """
        return self._graph_cache_manager.clear_persistent_graph_cache_for(graph_id)
    
    def clear_persistent_node_cache(self) -> int:
        """清空磁盘上的节点库持久化缓存（app/runtime/cache/node_cache）。"""
        cache_dir = get_node_cache_dir(self.workspace_path)
        if not cache_dir.exists():
            return 0
        removed_files = 0
        for json_file in cache_dir.glob("*.json"):
            json_file.unlink()
            removed_files += 1
        if not any(cache_dir.iterdir()):
            cache_dir.rmdir()
        return removed_files

    def clear_all_caches(self) -> dict:
        """清除所有缓存（内存+磁盘节点图缓存）。
        
        - 内存缓存：资源数据LRU缓存、元数据缓存
        - 磁盘缓存：app/runtime/cache/graph_cache 下的持久化缓存
        
        Returns:
            {"removed_persistent_files": int, "memory_cache_cleared": bool}
        """
        removed_persistent_files = 0
        removed_persistent_files += self.clear_persistent_graph_cache()
        removed_persistent_files += self.clear_persistent_resource_index_cache()
        removed_persistent_files += self.clear_persistent_node_cache()
        self.clear_cache()
        return {"removed_persistent_files": removed_persistent_files, "memory_cache_cleared": True}
    
    def invalidate_cache_by_file_change(self, resource_type: ResourceType, resource_id: str) -> None:
        """文件修改时使缓存失效
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
        """
        self._cache_service.invalidate_by_file_change(resource_type, resource_id)

    # ===== 对外: 更新图的持久化缓存 =====
    def update_persistent_graph_cache(self, graph_id: str, result_data: dict, delta: Optional[dict] = None, layout_changed: Optional[bool] = None) -> None:
        """将当前内存中的图结果写入持久化缓存（app/runtime/cache/graph_cache）。
        
        用途：在不改动 .py 源文件的情况下（例如自动排版仅改变位置），
        也能刷新下一次加载所使用的持久化缓存内容。
        
        Args:
            graph_id: 节点图ID
            result_data: 按 `load_resource(ResourceType.GRAPH, ...)` 产出的结构组织的数据：
                {
                  "graph_id": str,
                  "name": str,
                  "graph_type": str,
                  "folder_path": str,
                  "description": str,
                  "data": dict,
                  "metadata": dict
                }
            delta: 可选的增量更新字典；若提供，将基于现有缓存进行合并，仅更新变更部分
            layout_changed: 布局是否发生变化；为 False 时将尽量复用旧的 fingerprints
        """
        file_path = self.get_graph_file_path(graph_id)
        if not file_path:
            raise ValueError(f"找不到节点图文件路径: {graph_id}")
        self._graph_service.update_persistent_graph_cache(
            graph_id,
            file_path,
            result_data,
            delta=delta,
            layout_changed=layout_changed,
        )
    
    def save_resource(self, resource_type: ResourceType, resource_id: str, data: dict) -> bool:
        """保存单个资源
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            data: 资源数据（字典格式）
        
        Returns:
            是否保存成功
        """
        # 添加元数据：大多数资源写入更新时间，结构体定义保持纯 Struct JSON（与运行时期望格式一致）
        if resource_type is not ResourceType.STRUCT_DEFINITION:
            if "updated_at" not in data:
                data["updated_at"] = datetime.now().isoformat()

        # ===== 管理配置与战斗预设：在写盘前统一补全 ID 与通用 name 字段 =====
        #
        # 约定：
        # - ID：优先使用各自的数据模型中的专用 ID 字段（如 timer_id / variable_id / resource_id），
        #   若该字段缺失则在保存前补写为 resource_id，保证 JSON 本体始终携带稳定 ID。
        # - name：优先使用各自领域内的 *name 字段（如 timer_name / variable_name / resource_name），
        #   若不存在或为空，则回退到 resource_id，保持行为与其他资源一致。
        #
        # 这样既能保证“用名字命名文件”（由 JsonResourceStore 使用 name 生成文件名），
        # 又能保证“用 ID 做引用”（由资源索引与管理页面统一使用 ID 字段作为主键）。
        id_field_name = get_id_field_for_type(resource_type)
        if id_field_name:
            if id_field_name not in data or not isinstance(data.get(id_field_name), str) or not data.get(id_field_name):
                data[id_field_name] = resource_id

        display_name_field = get_display_name_field_for_type(resource_type)
        resolved_display_name: str = ""

        if display_name_field:
            raw_display_name = data.get(display_name_field)
            if isinstance(raw_display_name, str):
                resolved_display_name = raw_display_name.strip()

        # SAVE_POINT 额外兼容：若 save_point_name 为空，则尝试使用 template_name 作为显示名。
        if resource_type == ResourceType.SAVE_POINT and not resolved_display_name:
            template_name_value = data.get("template_name")
            if isinstance(template_name_value, str):
                resolved_display_name = template_name_value.strip()

        if resolved_display_name:
            data.setdefault("name", resolved_display_name)
        elif resource_type in {
            ResourceType.CHAT_CHANNEL,
            ResourceType.EQUIPMENT_DATA,
            ResourceType.MAIN_CAMERA,
            ResourceType.PRESET_POINT,
            ResourceType.PERIPHERAL_SYSTEM,
            ResourceType.SAVE_POINT,
            ResourceType.TIMER,
            ResourceType.LEVEL_VARIABLE,
            ResourceType.UI_LAYOUT,
            ResourceType.UI_WIDGET_TEMPLATE,
            ResourceType.SKILL_RESOURCE,
            ResourceType.SHOP_TEMPLATE,
            ResourceType.BACKGROUND_MUSIC,
            ResourceType.LIGHT_SOURCE,
            ResourceType.PATH,
            ResourceType.ENTITY_DEPLOYMENT_GROUP,
            ResourceType.UNIT_TAG,
            ResourceType.SCAN_TAG,
            ResourceType.SHIELD,
            ResourceType.LEVEL_SETTINGS,
            ResourceType.CURRENCY_BACKPACK,
        }:
            # 仅对有业务意义名称的类型在缺少显示名时回退到 ID。
            data.setdefault("name", resource_id)
        
        # 节点图特殊处理：解析/验证/生成代码委托给 GraphResourceService
        if resource_type == ResourceType.GRAPH:
            success, resource_file = self._graph_service.save_graph(resource_id, data)
            if not success:
                return False
        else:
            resource_file = self._resource_store.save(resource_type, resource_id, data)
            # 模板资源保存后，清理指向同一物理文件的旧模板 ID（仅当未被任何存档引用）。
            if resource_type == ResourceType.TEMPLATE:
                self._cleanup_stale_template_ids_for_file(resource_id, resource_file)
        
        # ===== 清除缓存（新增）- 保存后数据已变化，缓存失效 =====
        self.clear_cache(resource_type, resource_id)
        # 更新索引持久化缓存
        self._save_persistent_resource_index()
        
        return True
    
    def load_resource(self, resource_type: ResourceType, resource_id: str) -> Optional[dict]:
        """加载单个资源（带缓存）
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
        
        Returns:
            资源数据（字典格式），如果不存在返回None
        """
        if resource_type == ResourceType.GRAPH:
            return self._graph_service.load_graph(resource_id)
        return self._resource_store.load(resource_type, resource_id)
    
    def load_graph_metadata(self, graph_id: str) -> Optional[dict]:
        """加载节点图的轻量级元数据（不执行节点图代码，用于列表显示）
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            元数据字典，包含：
            - graph_id: 节点图ID
            - name: 节点图名称
            - graph_type: 节点图类型（server/client）
            - folder_path: 文件夹路径
            - description: 描述
            - node_count: 节点数量（估算）
            - edge_count: 连线数量（估算）
            - modified_time: 修改时间（时间戳）
        """
        return self._graph_service.load_graph_metadata(graph_id)
    
    def list_resources(self, resource_type: ResourceType) -> List[str]:
        """列出某类型的所有资源ID
        
        Args:
            resource_type: 资源类型
        
        Returns:
            资源ID列表
        """
        return self._state.list_resource_ids(resource_type)
    
    def list_all_resources(self) -> Dict[ResourceType, List[str]]:
        """列出所有类型的所有资源
        
        Returns:
            {资源类型: [资源ID列表]}
        """
        result = {}
        for resource_type in ResourceType:
            resources = self.list_resources(resource_type)
            if resources:
                result[resource_type] = resources
        return result
    
    def delete_resource(self, resource_type: ResourceType, resource_id: str) -> bool:
        """删除资源
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
        
        Returns:
            是否删除成功
        """
        if resource_type == ResourceType.GRAPH:
            resource_file = self._state.get_file_path(resource_type, resource_id)
            if resource_file is None:
                resource_file = self._file_ops.get_resource_file_path(
                    resource_type,
                    resource_id,
                    self.id_to_filename_cache,
                )
            if resource_file.exists():
                resource_file.unlink()
            self._state.remove_file_path(resource_type, resource_id)
            self._state.remove_filename(resource_type, resource_id)
        else:
            self._resource_store.delete(resource_type, resource_id)

        self._references.clear_resource(resource_id)
        
        # ===== 清除缓存（新增）=====
        self.clear_cache(resource_type, resource_id)
        # 更新索引持久化缓存
        self._save_persistent_resource_index()
        
        return True
    
    def resource_exists(self, resource_type: ResourceType, resource_id: str) -> bool:
        """检查资源是否存在
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
        
        Returns:
            资源是否存在
        """
        if resource_type == ResourceType.GRAPH:
            resource_file = self._state.get_file_path(resource_type, resource_id)
            if resource_file is None:
                resource_file = self._file_ops.get_resource_file_path(
                    resource_type,
                    resource_id,
                    self.id_to_filename_cache,
                )
            return resource_file.exists()
        return self._resource_store.exists(resource_type, resource_id)
    
    def add_reference(self, resource_id: str, package_id: str) -> None:
        """添加资源引用
        
        Args:
            resource_id: 资源ID
            package_id: 存档ID
        """
        self._references.add_reference(resource_id, package_id)
    
    def remove_reference(self, resource_id: str, package_id: str) -> None:
        """移除资源引用
        
        Args:
            resource_id: 资源ID
            package_id: 存档ID
        """
        self._references.remove_reference(resource_id, package_id)
    
    def get_resource_references(self, resource_id: str) -> List[str]:
        """查询哪些存档引用了此资源
        
        Args:
            resource_id: 资源ID
        
        Returns:
            引用此资源的存档ID列表
        """
        return self._references.get_references(resource_id)
    
    def is_resource_referenced(self, resource_id: str) -> bool:
        """检查资源是否被引用
        
        Args:
            resource_id: 资源ID
        
        Returns:
            是否被引用
        """
        return self._references.is_referenced(resource_id)

    def _is_template_id_referenced_by_any_package(self, template_id: str) -> bool:
        """判断给定模板 ID 是否仍被任何功能包引用。

        约定：
        - 功能包索引位于 `assets/资源库/地图索引/pkg_*.json`。
        - 每个索引文件的 `resources.templates` 字段为模板 ID 列表。
        """
        index_dir = self.resource_library_dir / "地图索引"
        if not index_dir.exists():
            return False

        for json_file in index_dir.glob("pkg_*.json"):
            with open(json_file, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)

            resources = data.get("resources")
            if not isinstance(resources, dict):
                continue

            templates_value = resources.get("templates")
            if not isinstance(templates_value, list):
                continue

            for value in templates_value:
                if isinstance(value, str) and value == template_id:
                    return True

        return False

    def _cleanup_stale_template_ids_for_file(
        self,
        current_template_id: str,
        resource_file: Path,
    ) -> None:
        """清理指向同一模板文件的旧模板 ID。

        规则：
        - 仅针对 `ResourceType.TEMPLATE`。
        - 找出所有 `resource_index[TEMPLATE]` 中指向同一 `resource_file` 且 ID != 当前 ID 的条目；
        - 对于仍被任一功能包索引引用的 ID，予以保留；
        - 对于未被任何功能包引用的 ID：
          - 从资源索引与文件名缓存中移除；
          - 从名称映射中移除；
          - 清除对应的内存缓存条目。
        """
        template_bucket = self.resource_index.get(ResourceType.TEMPLATE)
        if not template_bucket:
            return

        stale_ids: List[str] = []
        for template_id, path in template_bucket.items():
            if template_id == current_template_id:
                continue
            if path == resource_file:
                stale_ids.append(template_id)

        if not stale_ids:
            return

        name_mapping = self.name_to_id_index.get(ResourceType.TEMPLATE)

        for stale_id in stale_ids:
            if self._is_template_id_referenced_by_any_package(stale_id):
                continue

            # 1. 从资源路径索引与文件名缓存中移除
            self._state.remove_file_path(ResourceType.TEMPLATE, stale_id)
            self._state.remove_filename(ResourceType.TEMPLATE, stale_id)

            # 2. 从名称映射中移除所有指向该 ID 的条目
            if name_mapping is not None:
                keys_to_delete: List[str] = []
                for key, value in name_mapping.items():
                    if value == stale_id:
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    del name_mapping[key]

            # 3. 清除对应的内存缓存
            self.clear_cache(ResourceType.TEMPLATE, stale_id)
    
    def get_resource_metadata(self, resource_type: ResourceType, resource_id: str) -> Optional[dict]:
        """获取资源的元数据（不加载完整数据）
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
        
        Returns:
            资源元数据（名称、描述等基本信息）
        """
        data = self.load_resource(resource_type, resource_id)
        if not data:
            return None

        # 计算用于 UI 展示与搜索的友好名称：
        # - 对战斗预设与管理配置，优先使用各自的 *_name 字段；
        # - 其次回退到通用的 "name" 字段；
        # - 再次回退到资源 ID。
        friendly_name = self._resolve_display_name(resource_type, resource_id, data)

        # 提取关键元数据
        metadata = {
            "resource_id": resource_id,
            "resource_type": resource_type.value,
            "name": friendly_name,
            "description": data.get("description", ""),
            "updated_at": data.get("updated_at", ""),
            "created_at": data.get("created_at", ""),
        }

        # 补充：从通用 metadata 或顶层字段中提取 GUID（若存在）
        guid_value = None
        raw_metadata = data.get("metadata")
        if isinstance(raw_metadata, dict):
            raw_guid = raw_metadata.get("guid")
            if raw_guid is not None:
                guid_value = str(raw_guid)
        if guid_value is None and "guid" in data:
            raw_guid = data.get("guid")
            if raw_guid is not None:
                guid_value = str(raw_guid)
        metadata["guid"] = guid_value or ""

        # 补充：收集挂载的节点图 ID（模板 default_graphs / 实例 additional_graphs 等）
        graph_ids: list[str] = []

        def _append_graph_id(value: object) -> None:
            if isinstance(value, str) and value and value not in graph_ids:
                graph_ids.append(value)

        default_graphs = data.get("default_graphs")
        if isinstance(default_graphs, list):
            for graph_id in default_graphs:
                _append_graph_id(graph_id)

        additional_graphs = data.get("additional_graphs")
        if isinstance(additional_graphs, list):
            for graph_id in additional_graphs:
                _append_graph_id(graph_id)

        # PlayerTemplate 专用：从 metadata.player_editor 中收集玩家/角色层级挂载的节点图
        if resource_type == ResourceType.PLAYER_TEMPLATE:
            raw_player_editor = {}
            if isinstance(raw_metadata, dict):
                candidate = raw_metadata.get("player_editor")
                if isinstance(candidate, dict):
                    raw_player_editor = candidate

            def _collect_from_section(section: object) -> None:
                if not isinstance(section, dict):
                    return
                section_graphs = section.get("graphs")
                if isinstance(section_graphs, list):
                    for graph_id in section_graphs:
                        _append_graph_id(graph_id)

            # 兼容当前实现的 player / role 结构
            _collect_from_section(raw_player_editor.get("player"))
            _collect_from_section(raw_player_editor.get("role"))

            # 也兼容未来可能出现的 roles 列表结构
            roles_value = raw_player_editor.get("roles")
            if isinstance(roles_value, list):
                for role_entry in roles_value:
                    _collect_from_section(role_entry)

        metadata["graph_ids"] = graph_ids

        return metadata

    def _resolve_display_name(
        self,
        resource_type: ResourceType,
        resource_id: str,
        payload: dict,
    ) -> str:
        """根据资源类型解析友好的显示名称。
        
        约定：
        - 战斗预设系列优先读取 *_name 字段：
          - PLAYER_TEMPLATE.template_name
          - PLAYER_CLASS.class_name
          - UNIT_STATUS.status_name
          - SKILL.skill_name
          - PROJECTILE.projectile_name
          - ITEM.item_name
        - 管理配置优先读取各自的数据模型中约定的 *_name 字段：
          - UI 布局: layout_name
          - UI 控件模板: template_name
          - 单位标签: tag_name
          - 护盾: shield_name
          - 扫描标签: scan_tag_name
          - 局内存档管理: save_point_name
          - 计时器: timer_name
          - 关卡变量: variable_name
          - 聊天频道: channel_name
          - 光源: light_name
          - 外围系统: system_name
          - 背景音乐: music_name
          - 关卡设置: level_name
        - 其余资源优先读取通用的 "name" 字段。
        - 若上述字段均不存在或为空，则回退到资源 ID。
        """
        # 通用候选列表，按优先级从高到低排列。
        preferred_keys: list[str] = []

        # 战斗预设系列
        if resource_type == ResourceType.PLAYER_TEMPLATE:
            preferred_keys.append("template_name")
        elif resource_type == ResourceType.PLAYER_CLASS:
            preferred_keys.append("class_name")
        elif resource_type == ResourceType.UNIT_STATUS:
            preferred_keys.append("status_name")
        elif resource_type == ResourceType.SKILL:
            preferred_keys.append("skill_name")
        elif resource_type == ResourceType.PROJECTILE:
            preferred_keys.append("projectile_name")
        elif resource_type == ResourceType.ITEM:
            preferred_keys.append("item_name")

        # 管理配置系列
        if resource_type == ResourceType.UI_LAYOUT:
            preferred_keys.append("layout_name")
        elif resource_type == ResourceType.UI_WIDGET_TEMPLATE:
            preferred_keys.append("template_name")
        elif resource_type == ResourceType.UNIT_TAG:
            preferred_keys.append("tag_name")
        elif resource_type == ResourceType.SHIELD:
            preferred_keys.append("shield_name")
        elif resource_type == ResourceType.SCAN_TAG:
            preferred_keys.append("scan_tag_name")
        elif resource_type == ResourceType.SAVE_POINT:
            # 局内存档管理资源（局内存档管理）：默认以 save_point_name 作为显示名
            preferred_keys.append("save_point_name")
        elif resource_type == ResourceType.TIMER:
            preferred_keys.append("timer_name")
        elif resource_type == ResourceType.LEVEL_VARIABLE:
            preferred_keys.append("variable_name")
        elif resource_type == ResourceType.CHAT_CHANNEL:
            preferred_keys.append("channel_name")
        elif resource_type == ResourceType.LIGHT_SOURCE:
            preferred_keys.append("light_name")
        elif resource_type == ResourceType.PERIPHERAL_SYSTEM:
            preferred_keys.append("system_name")
        elif resource_type == ResourceType.BACKGROUND_MUSIC:
            preferred_keys.append("music_name")
        elif resource_type == ResourceType.LEVEL_SETTINGS:
            preferred_keys.append("level_name")

        # 最后统一补充通用字段
        preferred_keys.append("name")

        for key in preferred_keys:
            raw_value = payload.get(key)
            if isinstance(raw_value, str):
                striped = raw_value.strip()
                if striped:
                    return striped

        return resource_id
    
    def search_resources(self, keyword: str, resource_type: Optional[ResourceType] = None) -> List[dict]:
        """搜索资源（按名称或描述）
        
        Args:
            keyword: 搜索关键词
            resource_type: 可选的资源类型过滤
        
        Returns:
            匹配的资源元数据列表
        """
        results = []
        keyword_lower = keyword.lower()
        
        resource_types = [resource_type] if resource_type else list(ResourceType)
        
        for rtype in resource_types:
            resource_ids = self.list_resources(rtype)
            for resource_id in resource_ids:
                metadata = self.get_resource_metadata(rtype, resource_id)
                if metadata:
                    if (keyword_lower in metadata["name"].lower() or 
                        keyword_lower in metadata.get("description", "").lower() or
                        keyword_lower in resource_id.lower()):
                        results.append(metadata)
        
        return results
    
    def rebuild_index(self) -> None:
        """重建资源索引（用于手动修改文件后的同步）"""
        self._index_service.rebuild_index()
    
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
            graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
            if not graph_data:
                continue
            data_graph_type = graph_data.get("graph_type", "server")
            folder_path = graph_data.get("folder_path", "")
            if not folder_path:
                folder_path = self._infer_graph_folder_path(graph_id, data_graph_type)
            folder_path = self.sanitize_folder_path(folder_path) if folder_path else ""
            graph_data["folder_path"] = folder_path
            if graph_type == "all" or data_graph_type == graph_type:
                graphs.append({
                    "graph_id": graph_id,
                    "name": graph_data.get("name", "未命名"),
                    "graph_type": data_graph_type,
                    "folder_path": folder_path,
                    "description": graph_data.get("description", "")
                })
        
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
            graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
            if not graph_data:
                continue
            data_graph_type = graph_data.get("graph_type", "server")
            graph_folder = graph_data.get("folder_path", "")
            if not graph_folder:
                graph_folder = self._infer_graph_folder_path(graph_id, data_graph_type)
            graph_folder = self.sanitize_folder_path(graph_folder) if graph_folder else ""
            graph_data["folder_path"] = graph_folder
            if graph_folder != target_folder:
                continue
            graphs.append({
                "graph_id": graph_id,
                "name": graph_data.get("name", "未命名"),
                "graph_type": data_graph_type,
                "folder_path": target_folder,
                "description": graph_data.get("description", "")
            })
        
        return graphs
    
    def _infer_graph_folder_path(self, graph_id: str, graph_type: str) -> str:
        """基于文件路径推断节点图所在文件夹（用于旧图未写入 folder_path 的场景）。"""
        graph_paths = self.resource_index.get(ResourceType.GRAPH, {})
        file_path = graph_paths.get(graph_id)
        if not isinstance(file_path, Path):
            return ""
        try:
            type_dir = self.resource_library_dir / "节点图" / graph_type
            relative_path = file_path.relative_to(type_dir)
        except ValueError:
            return ""
        parent = relative_path.parent
        if not str(parent) or str(parent) in {".", ""}:
            return ""
        return self.sanitize_folder_path(parent.as_posix())
    
    def get_all_graph_folders(self) -> Dict[str, List[str]]:
        """获取所有节点图的文件夹结构
        
        Returns:
            {"server": [folder_paths], "client": [folder_paths]}
        """
        folders = {"server": set(), "client": set()}
        
        # 1. 从节点图数据中收集文件夹路径
        graph_ids = self.list_resources(ResourceType.GRAPH)
        for graph_id in graph_ids:
            graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
            if graph_data:
                graph_type = graph_data.get("graph_type", "server")
                folder_path = graph_data.get("folder_path", "") or self._infer_graph_folder_path(graph_id, graph_type)
                folder_path = self.sanitize_folder_path(folder_path) if folder_path else ""
                
                if folder_path and graph_type in folders:
                    folders[graph_type].add(folder_path)
        
        # 2. 扫描文件系统中的空文件夹
        ignored_folder_names = {"__pycache__"}

        for graph_type in ["server", "client"]:
            type_dir = self.resource_library_dir / "节点图" / graph_type
            if type_dir.exists():
                for item in type_dir.rglob("*"):
                    if item.is_dir():
                        # 计算相对路径
                        rel_path = item.relative_to(type_dir)
                        rel_parts = getattr(rel_path, "parts", ())
                        if not rel_parts:
                            continue
                        if any(part in ignored_folder_names for part in rel_parts):
                            continue
                        folder_path = str(rel_path).replace("\\", "/")
                        folders[graph_type].add(folder_path)
        
        # 转换为列表并排序
        return {
            "server": sorted(list(folders["server"])),
            "client": sorted(list(folders["client"]))
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

        folder_dir = self._file_ops.ensure_graph_folder(graph_type, folder_path)
        log_info("[OK] 创建文件夹: {}", folder_dir)
        return True
    
    def is_valid_folder_name(self, name: str) -> bool:
        """检查文件夹名称是否合法（Windows 规范）
        
        Args:
            name: 文件夹名称
        
        Returns:
            是否合法
        """
        return ResourceFileOps.is_valid_folder_name(name)
    
    def sanitize_folder_path(self, folder_path: str) -> str:
        """标准化文件夹路径（统一使用 / 作为分隔符）
        
        Args:
            folder_path: 文件夹路径
        
        Returns:
            标准化后的路径
        """
        return ResourceFileOps.sanitize_folder_path(folder_path)
    
    def move_graph_to_folder(self, graph_id: str, new_folder_path: str) -> None:
        """移动节点图到指定文件夹
        
        Args:
            graph_id: 节点图 ID
            new_folder_path: 目标文件夹路径（空字符串表示根目录）
        """
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
        """重命名节点图文件夹（递归更新所有子图）
        
        Args:
            graph_type: 节点图类型 ("server" 或 "client")
            old_folder_path: 旧文件夹路径
            new_folder_path: 新文件夹路径
        """
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
                relative_path = old_path[len(old_folder_path) + 1:]
                updated_path = f"{new_folder_path}/{relative_path}" if new_folder_path else relative_path
            
            graph_data["folder_path"] = updated_path
            graph_data["updated_at"] = datetime.now().isoformat()
            self.save_resource(ResourceType.GRAPH, graph_id, graph_data)
            log_info("  - 更新 {}: {} -> {}", graph_id, old_path, updated_path)
        
        # 物理移动目录
        old_dir = self.resource_library_dir / "节点图" / graph_type / old_folder_path
        new_dir = self.resource_library_dir / "节点图" / graph_type / new_folder_path

        if old_dir.exists():
            self._file_ops.rename_graph_directory(graph_type, old_folder_path, new_folder_path)
            log_info("[OK] 物理目录已重命名: {} -> {}", old_dir, new_dir)
    
    def get_graph_file_path(self, graph_id: str) -> Optional[Path]:
        """获取节点图的物理文件路径
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            文件路径，如果不存在返回None
        """
        file_path = self._state.get_file_path(ResourceType.GRAPH, graph_id)
        if file_path:
            return file_path
        
        graph_data = self.load_resource(ResourceType.GRAPH, graph_id)
        if graph_data:
            return self._state.get_file_path(ResourceType.GRAPH, graph_id)
        
        return None
    
    def remove_graph_folder_if_empty(self, graph_type: str, folder_path: str) -> bool:
        """删除空的节点图文件夹
        
        Args:
            graph_type: 节点图类型 ("server" 或 "client")
            folder_path: 文件夹路径
        
        Returns:
            是否成功删除
        """
        folder_path = self.sanitize_folder_path(folder_path)
        
        if not folder_path:
            raise ValueError("不能删除根目录")
        
        # 检查是否有节点图在此文件夹
        graphs = self.list_graphs_by_folder(folder_path)
        if graphs:
            log_warn("[警告] 文件夹 {} 非空，包含 {} 个节点图", folder_path, len(graphs))
            return False
        
        # 物理删除目录（仅当完全为空时）
        removed = self._file_ops.remove_empty_graph_folder_tree(graph_type, folder_path)
        if removed:
            log_info(
                "[OK] 已删除空文件夹: {}",
                self.resource_library_dir / "节点图" / graph_type / folder_path,
            )
        else:
            log_warn("[警告] 文件夹 {} 包含子文件夹或其他文件", folder_path)
        return removed

