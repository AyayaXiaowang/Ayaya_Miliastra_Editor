from __future__ import annotations

from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Dict, List, Optional

from engine.configs.resource_types import ResourceType
from engine.resources.management_naming_rules import (
    get_display_name_field_for_type,
    get_id_field_for_type,
)
from engine.utils.logging.logger import log_warn

from .resource_file_ops import ResourceFileOps


class ResourceManagerIoMixin:
    """ResourceManager 的资源读写/枚举相关方法。"""

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

    def save_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        data: dict,
        *,
        expected_mtime: float | None = None,
        allow_overwrite_external: bool = False,
        resource_root_dir: Path | None = None,
    ) -> bool:
        """保存单个资源

        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            data: 资源数据（字典格式）
            expected_mtime: 期望的“磁盘版本”（文件 mtime）。用于检测外部修改并阻止静默覆盖。
            allow_overwrite_external: 若为 True，则在检测到外部修改时仍允许覆盖写入。
            resource_root_dir: 可选的资源根目录写入落点（用于“目录即存档”模式下把新建资源写入当前项目存档目录）。

        Returns:
            是否保存成功
        """
        normalized_expected_mtime: float | None = None
        if isinstance(expected_mtime, (int, float)) and float(expected_mtime) > 0:
            normalized_expected_mtime = float(expected_mtime)

        # VSCode 风格的“保存冲突”检测：文件在磁盘上发生过外部修改时，默认拒绝覆盖。
        if normalized_expected_mtime is not None and not allow_overwrite_external:
            existing_file = self._state.get_file_path(resource_type, resource_id)
            if existing_file is None:
                if resource_type == ResourceType.GRAPH:
                    existing_file = self.get_graph_file_path(resource_id)
                else:
                    existing_file = self._file_ops.get_resource_file_path(
                        resource_type,
                        resource_id,
                        self.id_to_filename_cache,
                    )
            if existing_file is not None and existing_file.exists():
                current_mtime = float(existing_file.stat().st_mtime)
                if abs(current_mtime - normalized_expected_mtime) >= 0.001:
                    log_warn(
                        "[SAVE-CONFLICT] 资源在磁盘上已变化，已阻止保存覆盖：type={}, id={}, expected_mtime={}, actual_mtime={}, path={}",
                        resource_type,
                        resource_id,
                        normalized_expected_mtime,
                        current_mtime,
                        str(existing_file),
                    )
                    return False

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
            ResourceType.UI_PAGE,
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
            success, resource_file = self._graph_service.save_graph(
                resource_id,
                data,
                resource_root_dir=resource_root_dir,
            )
            if not success:
                return False
        else:
            resource_file = self._resource_store.save(
                resource_type,
                resource_id,
                data,
                resource_root_dir=resource_root_dir,
            )
            # 模板资源保存后，清理指向同一物理文件的旧模板 ID（仅当未被任何存档引用）。
            if resource_type == ResourceType.TEMPLATE:
                self._cleanup_stale_template_ids_for_file(resource_id, resource_file)

        # ===== 清除缓存（新增）- 保存后数据已变化，缓存失效 =====
        self.clear_cache(resource_type, resource_id)
        # 更新索引持久化缓存
        self._save_persistent_resource_index()
        # 标记指纹为脏，延迟到下次需要时再计算，避免频繁 I/O
        self.invalidate_fingerprint()

        return True

    def load_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        *,
        copy_mode: "ResourceCacheService.CopyMode" = "deep",
    ) -> Optional[dict]:
        """加载单个资源（带缓存）

        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            copy_mode:
                - "deep"：缓存命中时 deep copy（默认）
                - "shallow"：缓存命中时浅拷贝（更快）
                - "none"：缓存命中时不拷贝（最快，仅限严格只读调用）

        Returns:
            资源数据（字典格式），如果不存在返回None
        """
        # 代码级资源：信号/结构体定义以 .py 文件形式存在（目录即存档模式）。
        # 这些类型不应走 JsonResourceStore，否则会把 .py 当作 JSON 解析并抛出 JSONDecodeError。
        if resource_type in {ResourceType.SIGNAL, ResourceType.STRUCT_DEFINITION}:
            resource_id_text = str(resource_id or "").strip()
            if not resource_id_text:
                return None
            return self._load_code_resource_from_py_file(resource_type, resource_id_text)
        if resource_type == ResourceType.GRAPH:
            return self._graph_service.load_graph(resource_id)
        return self._resource_store.load(resource_type, resource_id, copy_mode=copy_mode)

    def _load_code_resource_from_py_file(
        self,
        resource_type: ResourceType,
        resource_id: str,
    ) -> Optional[dict]:
        """加载代码级资源（.py），返回 payload 字典。

        支持资源类型：
        - ResourceType.SIGNAL：读取模块中的 `SIGNAL_PAYLOAD`
        - ResourceType.STRUCT_DEFINITION：读取模块中的 `STRUCT_PAYLOAD`

        说明：
        - 该加载路径尊重当前 ResourceManager 的索引作用域（共享 + 当前项目存档），
          仅从资源索引中解析文件路径；避免直接从“全局 SchemaView”取值导致跨项目混入。
        - 结果会使用 ResourceCacheService 按 (type, id, mtime) 做缓存。
        """
        if resource_type not in {ResourceType.SIGNAL, ResourceType.STRUCT_DEFINITION}:
            raise ValueError(f"不支持的代码级资源类型: {resource_type}")

        resource_id_text = str(resource_id or "").strip()
        if not resource_id_text:
            return None

        file_path = self._state.get_file_path(resource_type, resource_id_text)
        if file_path is None:
            file_path = self.resource_index.get(resource_type, {}).get(resource_id_text)
        if file_path is None:
            return None
        if not file_path.exists():
            return None

        file_mtime = float(file_path.stat().st_mtime)
        cache_key = (resource_type, resource_id_text)
        cached = self._cache_service.get(cache_key, file_mtime)
        if cached is not None:
            return cached

        payload_attr = "SIGNAL_PAYLOAD" if resource_type == ResourceType.SIGNAL else "STRUCT_PAYLOAD"
        # mtime 纳入 module_name，确保外部修改文件后不会复用旧模块对象。
        module_name = (
            f"code_resource_{resource_type.name.lower()}_"
            f"{abs(hash(file_path.as_posix()))}_{int(file_mtime * 1000)}"
        )
        loader = SourceFileLoader(module_name, str(file_path))
        module = loader.load_module()

        payload_value = getattr(module, payload_attr, None)
        if not isinstance(payload_value, dict):
            raise ValueError(f"{file_path} 未导出有效的 {payload_attr}（期望 dict）")

        payload = dict(payload_value)
        self._cache_service.add(cache_key, payload, file_mtime)
        return payload

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

    def list_resource_file_paths(self, resource_type: ResourceType) -> Dict[str, Path]:
        """返回指定资源类型的 {resource_id: file_path} 快照。

        说明：
        - 该映射来自资源索引（不触发资源解析/加载）。
        - 主要用于“按项目存档目录归属”这类基于文件路径的聚合视图与校验逻辑。
        """
        bucket = self._state.resource_paths.get(resource_type)
        return dict(bucket) if isinstance(bucket, dict) else {}

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

        # 标记指纹为脏，延迟到下次需要时再计算，避免频繁 I/O
        self.invalidate_fingerprint()

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



