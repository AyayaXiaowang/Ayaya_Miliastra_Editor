"""共享资源视图 - 不依赖项目存档，直接浏览共享根资源。

术语澄清（目录即项目存档模式）：
- GlobalResourceView 绑定的是共享根目录 `assets/资源库/共享/`（所有项目存档可见）。
- 新建资源若不指定 `resource_root_dir`，资源层会将其写入默认归档项目（例如 “测试项目”）；
  这会导致“共享视图中新建资源”落不到共享根目录，进而下一次刷新时不可见。
- 因此本视图中新建模板/实体摆放等资源时，应显式指定写入共享根目录。
"""

from __future__ import annotations
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path

from engine.resources.resource_manager import ResourceManager
from engine.configs.resource_types import ResourceType
from engine.resources.management_view_helpers import (
    MANAGEMENT_FIELD_TO_RESOURCE_TYPE,
    SINGLE_CONFIG_MANAGEMENT_FIELDS,
)
from engine.utils.resource_library_layout import get_shared_root_dir
from engine.resources.ingame_save_template_schema_view import (
    get_default_ingame_save_template_schema_view,
)
from engine.resources.level_variable_schema_view import (
    get_default_level_variable_schema_view,
)
from engine.graph.models.package_model import (
    TemplateConfig,
    InstanceConfig,
    CombatPresets,
    ManagementData,
    SignalConfig,
)


class GlobalResourceView:
    """共享资源视图 - 显示共享根中的可用资源。

    说明：
    - 当前资源库采用“目录即项目存档”布局，项目存档之间允许出现相同 resource_id；
    - 因此本视图仅绑定共享根目录（所有项目存档可见），避免跨项目存档聚合时产生歧义。
    """
    
    def __init__(self, resource_manager: ResourceManager):
        self.resource_manager = resource_manager
        
        # 模拟存档接口
        self.package_id = "global_view"
        self.name = "<共享资源>"
        self.description = "共享资源浏览模式"
        self.created_at = ""
        self.updated_at = ""
        self.todo_states = {}
        
        # 缓存
        self._templates_cache: Optional[Dict[str, TemplateConfig]] = None
        self._templates_loaded_all: bool = False
        self._instances_cache: Optional[Dict[str, InstanceConfig]] = None
        self._instances_loaded_all: bool = False
        self._combat_presets_cache: Optional[CombatPresets] = None
        self._management_cache: Optional[ManagementData] = None
        self._signals_cache: Optional[Dict[str, SignalConfig]] = None
        self._level_entity_cache: Optional[InstanceConfig] = None
    
    @property
    def templates(self) -> Dict[str, TemplateConfig]:
        """获取所有模板"""
        if self._templates_cache is None:
            self._templates_cache = {}
            self._templates_loaded_all = False

        if not self._templates_loaded_all:
            template_ids = self.resource_manager.list_resources(ResourceType.TEMPLATE)
            for template_id in template_ids:
                if template_id in self._templates_cache:
                    continue
                template_data = self.resource_manager.load_resource(
                    ResourceType.TEMPLATE,
                    template_id,
                )
                if not isinstance(template_data, dict):
                    continue
                template_obj = TemplateConfig.deserialize(template_data)
                source_mtime = self.resource_manager.get_resource_file_mtime(
                    ResourceType.TEMPLATE,
                    str(template_id),
                )
                if source_mtime is not None:
                    setattr(template_obj, "_source_mtime", float(source_mtime))
                self._templates_cache[template_id] = template_obj
            self._templates_loaded_all = True
        return self._templates_cache
    
    @property
    def instances(self) -> Dict[str, InstanceConfig]:
        """获取所有实例"""
        if self._instances_cache is None:
            self._instances_cache = {}
            self._instances_loaded_all = False

        if not self._instances_loaded_all:
            instance_ids = self.resource_manager.list_resources(ResourceType.INSTANCE)
            for instance_id in instance_ids:
                if instance_id in self._instances_cache:
                    continue
                instance_data = self.resource_manager.load_resource(
                    ResourceType.INSTANCE,
                    instance_id,
                )
                if not isinstance(instance_data, dict):
                    continue
                instance_obj = InstanceConfig.deserialize(instance_data)
                source_mtime = self.resource_manager.get_resource_file_mtime(
                    ResourceType.INSTANCE,
                    str(instance_id),
                )
                if source_mtime is not None:
                    setattr(instance_obj, "_source_mtime", float(source_mtime))
                self._instances_cache[instance_id] = instance_obj
            self._instances_loaded_all = True
        return self._instances_cache
    
    @property
    def level_entity(self) -> Optional[InstanceConfig]:
        """获取关卡实体（从全局实例集中按 metadata 标记扫描）。

        设计约定：
        - 关卡实体作为特殊实例存储在资源库中，通过 metadata.is_level_entity 标记
        - 全局视图下允许直接编辑关卡实体本体，但不代表其归属的具体存档
        - 具体归属由属性面板中的“所属存档”单选下拉控制（每个存档最多一个）
        """
        if self._level_entity_cache is None:
            instance_ids = self.resource_manager.list_resources(ResourceType.INSTANCE)

            # 优先使用“约定 ID”快速缩小候选（level_<package_id>），避免全量扫描。
            preferred_candidates = [value for value in instance_ids if str(value).startswith("level_")]
            preferred_candidates.sort(key=lambda text: str(text).casefold())

            def pick_from_candidates(candidates: list[str]) -> Optional[InstanceConfig]:
                for candidate_id in candidates:
                    instance_obj = self.get_instance(candidate_id)
                    if instance_obj is None:
                        continue
                    metadata = getattr(instance_obj, "metadata", {}) or {}
                    if isinstance(metadata, dict) and metadata.get("is_level_entity"):
                        return instance_obj
                return None

            self._level_entity_cache = pick_from_candidates(preferred_candidates)
            if self._level_entity_cache is None:
                # 兼容：若部分工程未使用 level_* 命名约定，则回退为“按 ID 列表逐个加载并检查标记”。
                # 注意：这在资源库体量很大时会较慢，因此尽量保持工程使用命名约定。
                normalized_ids = [str(value) for value in instance_ids if isinstance(value, str) and value]
                self._level_entity_cache = pick_from_candidates(normalized_ids)
        return self._level_entity_cache
    
    @property
    def combat_presets(self) -> CombatPresets:
        """获取所有战斗预设"""
        if self._combat_presets_cache is None:
            combat_presets_data = {
                "player_templates": {},
                "player_classes": {},
                "unit_statuses": {},
                "skills": {},
                "projectiles": {},
                "items": {}
            }
            
            # 加载所有战斗预设
            for template_id in self.resource_manager.list_resources(ResourceType.PLAYER_TEMPLATE):
                data = self.resource_manager.load_resource(ResourceType.PLAYER_TEMPLATE, template_id)
                if data:
                    combat_presets_data["player_templates"][template_id] = data

            for class_id in self.resource_manager.list_resources(ResourceType.PLAYER_CLASS):
                data = self.resource_manager.load_resource(ResourceType.PLAYER_CLASS, class_id)
                if data:
                    combat_presets_data["player_classes"][class_id] = data
            
            for status_id in self.resource_manager.list_resources(ResourceType.UNIT_STATUS):
                data = self.resource_manager.load_resource(ResourceType.UNIT_STATUS, status_id)
                if data:
                    combat_presets_data["unit_statuses"][status_id] = data
            
            for skill_id in self.resource_manager.list_resources(ResourceType.SKILL):
                data = self.resource_manager.load_resource(ResourceType.SKILL, skill_id)
                if data:
                    combat_presets_data["skills"][skill_id] = data
            
            for projectile_id in self.resource_manager.list_resources(ResourceType.PROJECTILE):
                data = self.resource_manager.load_resource(ResourceType.PROJECTILE, projectile_id)
                if data:
                    combat_presets_data["projectiles"][projectile_id] = data
            
            for item_id in self.resource_manager.list_resources(ResourceType.ITEM):
                data = self.resource_manager.load_resource(ResourceType.ITEM, item_id)
                if data:
                    combat_presets_data["items"][item_id] = data
            
            self._combat_presets_cache = CombatPresets.deserialize(combat_presets_data)
        
        return self._combat_presets_cache
    
    @property
    def management(self) -> ManagementData:
        """获取所有管理数据"""
        if self._management_cache is None:
            management_data: dict[str, object] = {}

            def _is_path_under(root_dir: Path, file_path: Path) -> bool:
                resolved_root = root_dir.resolve()
                resolved_file = file_path.resolve()
                if hasattr(resolved_file, "is_relative_to"):
                    return resolved_file.is_relative_to(resolved_root)  # type: ignore[attr-defined]
                root_parts = resolved_root.parts
                file_parts = resolved_file.parts
                return len(file_parts) >= len(root_parts) and file_parts[: len(root_parts)] == root_parts

            # 映射与“单一配置体”字段集合由 management_view_helpers 统一维护，
            # 便于 PackageView/GlobalResourceView/UnclassifiedResourceView 共享一致语义。
            for management_field_name, resource_type in MANAGEMENT_FIELD_TO_RESOURCE_TYPE.items():
                if management_field_name == "level_variables":
                    schema_view = get_default_level_variable_schema_view()
                    variable_files = schema_view.get_all_variable_files() or {}
                    current_roots = self.resource_manager.get_current_resource_roots()

                    flattened: dict[str, dict] = {}
                    for file_info in variable_files.values():
                        abs_path = getattr(file_info, "absolute_path", None)
                        if not isinstance(abs_path, Path):
                            continue
                        if not any(_is_path_under(root_dir, abs_path) for root_dir in current_roots):
                            continue

                        variables = getattr(file_info, "variables", None)
                        if not isinstance(variables, list):
                            continue
                        for payload in variables:
                            if not isinstance(payload, dict):
                                continue
                            variable_id = payload.get("variable_id")
                            if not isinstance(variable_id, str) or not variable_id.strip():
                                continue
                            flattened[variable_id.strip()] = payload

                    management_data[management_field_name] = flattened
                    continue

                resource_ids = self.resource_manager.list_resources(resource_type)

                # 局内存档管理：单一聚合配置体，由全局元配置 + 所有模板列表组成。
                if management_field_name == "save_points":
                    management_data[management_field_name] = (
                        self._build_save_points_config_for_global_view()
                    )
                    continue

                # 单配置字段：优先使用以 global_view_<field> 命名的全局配置资源，
                # 若尚未创建则返回一个空字典，交由上层 UI 初始化字段结构。
                if management_field_name in SINGLE_CONFIG_MANAGEMENT_FIELDS:
                    preferred_id = f"global_view_{management_field_name}"
                    selected_payload: dict | None = None

                    if preferred_id in resource_ids:
                        candidate = self.resource_manager.load_resource(
                            resource_type,
                            preferred_id,
                        )
                        if isinstance(candidate, dict):
                            selected_payload = candidate

                    management_data[management_field_name] = selected_payload or {}
                    continue

                # 多配置字段：聚合为 {resource_id: payload}
                management_resources: dict[str, dict] = {}
                for resource_id in resource_ids:
                    data = self.resource_manager.load_resource(resource_type, resource_id)
                    if isinstance(data, dict):
                        management_resources[resource_id] = data

                management_data[management_field_name] = management_resources

            self._management_cache = ManagementData.deserialize(management_data)
        
        return self._management_cache

    def _build_save_points_config_for_global_view(self) -> dict:
        """构建局内存档管理的聚合配置：全局状态 + 所有代码级模板列表。

        设计约定：
        - 每个局内存档模板以一份 Python 代码资源存在于
          `assets/资源库/管理配置/局内存档管理/` 目录下，由
          `IngameSaveTemplateSchemaView` 聚合为 {template_id: payload} 视图；
        - 模板 payload 中的可选字段 `is_default_template` 用于表达“当前工程默认/主模板”，
          当任意模板的该字段为 True 时，视图层认为局内存档整体处于启用状态；
        """
        # 1. 收集代码级模板资源（按 ResourceManager 当前作用域过滤，避免跨项目混入）
        schema_view = get_default_ingame_save_template_schema_view()
        all_templates = schema_view.get_all_templates()
        current_roots = self.resource_manager.get_current_resource_roots()

        def _is_path_under(root_dir: Path, file_path: Path) -> bool:
            resolved_root = root_dir.resolve()
            resolved_file = file_path.resolve()
            if hasattr(resolved_file, "is_relative_to"):
                return resolved_file.is_relative_to(resolved_root)  # type: ignore[attr-defined]
            root_parts = resolved_root.parts
            file_parts = resolved_file.parts
            return len(file_parts) >= len(root_parts) and file_parts[: len(root_parts)] == root_parts

        templates: list[dict] = []
        for template_id, original_payload in all_templates.items():
            if not isinstance(original_payload, dict):
                continue
            template_file = schema_view.get_template_file_path(str(template_id))
            if not isinstance(template_file, Path):
                continue
            if not any(_is_path_under(root_dir, template_file) for root_dir in current_roots):
                continue
            template_payload = dict(original_payload)

            raw_template_id = template_payload.get("template_id", template_id)
            normalized_template_id = str(raw_template_id).strip() or template_id
            template_payload["template_id"] = normalized_template_id

            raw_template_name = template_payload.get("template_name")
            if isinstance(raw_template_name, str) and raw_template_name.strip():
                normalized_template_name = raw_template_name.strip()
            else:
                normalized_template_name = normalized_template_id
            template_payload["template_name"] = normalized_template_name

            templates.append(template_payload)

        # 3. 归一化与排序
        def _template_sort_key(payload: dict) -> tuple[str, str]:
            name_text = str(payload.get("template_name", "")).strip().lower()
            id_text = str(payload.get("template_id", "")).strip().lower()
            return name_text, id_text

        templates.sort(key=_template_sort_key)

        # 2. 依据模板状态计算启用状态与当前模板 ID（以 is_default_template 为单一真源）
        default_template_id_from_templates = ""
        for template_payload in templates:
            is_default = bool(template_payload.get("is_default_template", False))
            if not is_default:
                continue
            raw_id = template_payload.get("template_id", "")
            template_id_text = str(raw_id).strip()
            if not template_id_text:
                continue
            default_template_id_from_templates = template_id_text
            break

        enabled_flag = bool(default_template_id_from_templates)
        active_template_id = default_template_id_from_templates if enabled_flag else ""

        result: dict[str, object] = {
            "templates": templates,
            "enabled": enabled_flag,
            "active_template_id": active_template_id,
        }
        return result
    
    @property
    def signals(self) -> Dict[str, SignalConfig]:
        """获取信号配置（按 ResourceManager 当前作用域聚合）。

        重要：目录即项目存档模式下，同一 signal_id 允许在不同项目存档中存在，
        因此全局视图也必须以 ResourceManager 的“共享根 + 当前项目存档根”作用域为准，
        避免跨项目聚合产生歧义。
        """
        if self._signals_cache is None:
            self._signals_cache = {}

            signal_ids = self.resource_manager.list_resources(ResourceType.SIGNAL)
            normalized_ids = [
                str(value) for value in signal_ids if isinstance(value, str) and value
            ]
            normalized_ids.sort(key=lambda text: text.casefold())

            for signal_id in normalized_ids:
                payload = self.resource_manager.load_resource(ResourceType.SIGNAL, str(signal_id))
                if isinstance(payload, dict):
                    config = SignalConfig.deserialize(payload)
                else:
                    config = SignalConfig(
                        signal_id=str(signal_id),
                        signal_name=str(signal_id),
                        parameters=[],
                        description="",
                    )
                self._signals_cache[config.signal_id] = config

        return self._signals_cache
    
    def get_template(self, template_id: str) -> Optional[TemplateConfig]:
        """获取模板"""
        if not isinstance(template_id, str) or not template_id:
            return None

        if self._templates_cache is not None and template_id in self._templates_cache:
            return self._templates_cache.get(template_id)

        template_data = self.resource_manager.load_resource(ResourceType.TEMPLATE, template_id)
        if not isinstance(template_data, dict):
            return None
        template_obj = TemplateConfig.deserialize(template_data)
        source_mtime = self.resource_manager.get_resource_file_mtime(
            ResourceType.TEMPLATE,
            str(template_id),
        )
        if source_mtime is not None:
            setattr(template_obj, "_source_mtime", float(source_mtime))

        if self._templates_cache is None:
            self._templates_cache = {}
            self._templates_loaded_all = False
        self._templates_cache[template_id] = template_obj
        return template_obj
    
    def get_instance(self, instance_id: str) -> Optional[InstanceConfig]:
        """获取实例"""
        if not isinstance(instance_id, str) or not instance_id:
            return None

        if self._instances_cache is not None and instance_id in self._instances_cache:
            return self._instances_cache.get(instance_id)

        instance_data = self.resource_manager.load_resource(ResourceType.INSTANCE, instance_id)
        if not isinstance(instance_data, dict):
            return None
        instance_obj = InstanceConfig.deserialize(instance_data)
        source_mtime = self.resource_manager.get_resource_file_mtime(
            ResourceType.INSTANCE,
            str(instance_id),
        )
        if source_mtime is not None:
            setattr(instance_obj, "_source_mtime", float(source_mtime))

        if self._instances_cache is None:
            self._instances_cache = {}
            self._instances_loaded_all = False
        self._instances_cache[instance_id] = instance_obj
        return instance_obj
    
    def add_template(self, template: TemplateConfig) -> None:
        """添加模板（新建共享资源）。"""
        template_data = template.serialize()

        existing_file = self.resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(
            str(template.template_id)
        )
        if existing_file is None:
            shared_root_dir = get_shared_root_dir(self.resource_manager.resource_library_dir)
            self.resource_manager.save_resource(
                ResourceType.TEMPLATE,
                template.template_id,
                template_data,
                resource_root_dir=shared_root_dir,
            )
        else:
            # 已存在：保持其原有资源根目录不变（通常仍为共享根）。
            self.resource_manager.save_resource(
                ResourceType.TEMPLATE,
                template.template_id,
                template_data,
            )

        self._templates_cache = None
    
    def remove_template(self, template_id: str) -> None:
        """移除模板（仅清理缓存，不做物理删除）。

        说明：
        - UI 中的“全局删除”应显式调用 `ResourceManager.delete_resource(...)` 才会删除磁盘文件；
        - 该方法仅用于让视图缓存失效，避免 UI 刷新后仍使用旧数据。
        """
        self._templates_cache = None
    
    def add_instance(self, instance: InstanceConfig) -> None:
        """添加实例（新建共享资源）。"""
        instance_data = instance.serialize()

        existing_file = self.resource_manager.list_resource_file_paths(ResourceType.INSTANCE).get(
            str(instance.instance_id)
        )
        if existing_file is None:
            shared_root_dir = get_shared_root_dir(self.resource_manager.resource_library_dir)
            self.resource_manager.save_resource(
                ResourceType.INSTANCE,
                instance.instance_id,
                instance_data,
                resource_root_dir=shared_root_dir,
            )
        else:
            self.resource_manager.save_resource(
                ResourceType.INSTANCE,
                instance.instance_id,
                instance_data,
            )

        self._instances_cache = None
    
    def remove_instance(self, instance_id: str) -> None:
        """移除实例（仅清理缓存，不做物理删除）。"""
        self._instances_cache = None
    
    def serialize(self) -> dict:
        """序列化（全局视图不支持导出）"""
        return {
            "error": "共享资源视图不支持导出，请选择具体的项目存档"
        }
    
    def clear_cache(self) -> None:
        """清除所有缓存"""
        self._templates_cache = None
        self._templates_loaded_all = False
        self._instances_cache = None
        self._instances_loaded_all = False
        self._combat_presets_cache = None
        self._management_cache = None
        self._signals_cache = None
        self._level_entity_cache = None

