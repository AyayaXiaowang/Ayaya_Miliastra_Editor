"""全局资源视图 - 不依赖存档，直接浏览所有资源"""

from __future__ import annotations
from typing import Dict, Optional, List
from datetime import datetime

from engine.resources.resource_manager import ResourceManager
from engine.configs.resource_types import ResourceType
from engine.resources.management_view_helpers import (
    MANAGEMENT_FIELD_TO_RESOURCE_TYPE,
    SINGLE_CONFIG_MANAGEMENT_FIELDS,
)
from engine.resources.definition_schema_view import DefinitionSchemaView
from engine.resources.ingame_save_template_schema_view import (
    get_default_ingame_save_template_schema_view,
)
from engine.graph.models.package_model import (
    TemplateConfig,
    InstanceConfig,
    CombatPresets,
    ManagementData,
    SignalConfig,
)


class GlobalResourceView:
    """全局资源视图 - 显示所有可用资源"""
    
    def __init__(self, resource_manager: ResourceManager):
        self.resource_manager = resource_manager
        
        # 模拟存档接口
        self.package_id = "global_view"
        self.name = "<全部资源>"
        self.description = "全局资源浏览模式"
        self.created_at = ""
        self.updated_at = ""
        self.todo_states = {}
        
        # 缓存
        self._templates_cache: Optional[Dict[str, TemplateConfig]] = None
        self._instances_cache: Optional[Dict[str, InstanceConfig]] = None
        self._combat_presets_cache: Optional[CombatPresets] = None
        self._management_cache: Optional[ManagementData] = None
        self._signals_cache: Optional[Dict[str, SignalConfig]] = None
        self._level_entity_cache: Optional[InstanceConfig] = None
    
    @property
    def templates(self) -> Dict[str, TemplateConfig]:
        """获取所有模板"""
        if self._templates_cache is None:
            self._templates_cache = {}
            template_ids = self.resource_manager.list_resources(ResourceType.TEMPLATE)
            for template_id in template_ids:
                template_data = self.resource_manager.load_resource(
                    ResourceType.TEMPLATE,
                    template_id
                )
                if template_data:
                    self._templates_cache[template_id] = TemplateConfig.deserialize(template_data)
        return self._templates_cache
    
    @property
    def instances(self) -> Dict[str, InstanceConfig]:
        """获取所有实例"""
        if self._instances_cache is None:
            self._instances_cache = {}
            instance_ids = self.resource_manager.list_resources(ResourceType.INSTANCE)
            for instance_id in instance_ids:
                instance_data = self.resource_manager.load_resource(
                    ResourceType.INSTANCE,
                    instance_id
                )
                if instance_data:
                    self._instances_cache[instance_id] = InstanceConfig.deserialize(instance_data)
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
            for instance in self.instances.values():
                metadata = getattr(instance, "metadata", {}) or {}
                if isinstance(metadata, dict) and metadata.get("is_level_entity"):
                    self._level_entity_cache = instance
                    break
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

            # 映射与“单一配置体”字段集合由 management_view_helpers 统一维护，
            # 便于 PackageView/GlobalResourceView/UnclassifiedResourceView 共享一致语义。
            for management_field_name, resource_type in MANAGEMENT_FIELD_TO_RESOURCE_TYPE.items():
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
        """构建局内存档管理的聚合配置：全局元配置 + 所有代码级模板列表。

        设计约定：
        - 元配置存放在 ID 为 'global_view_save_points' 的 SAVE_POINT 资源中
          （enabled/active_template_id/updated_at）；
        - 每个局内存档模板以一份 Python 代码资源存在于
          `assets/资源库/管理配置/局内存档管理/` 目录下，由
          `IngameSaveTemplateSchemaView` 聚合为 {template_id: payload} 视图；
        - 本方法只负责将“元配置”与“模板定义视图”组合为管理页面使用的聚合结构，
          不再从 JSON SAVE_POINT 资源中还原模板本体。
        """
        aggregator_id = "global_view_save_points"

        # 1. 读取全局元配置
        meta_payload: dict = {}
        if self.resource_manager.resource_exists(ResourceType.SAVE_POINT, aggregator_id):
            candidate = self.resource_manager.load_resource(ResourceType.SAVE_POINT, aggregator_id)
            if isinstance(candidate, dict):
                meta_payload = {
                    "enabled": bool(candidate.get("enabled", False)),
                    "active_template_id": str(candidate.get("active_template_id", "")).strip(),
                    "updated_at": str(candidate.get("updated_at", "")),
                }

        # 2. 收集代码级模板资源
        schema_view = get_default_ingame_save_template_schema_view()
        all_templates = schema_view.get_all_templates()

        templates: list[dict] = []
        for template_id, original_payload in all_templates.items():
            if not isinstance(original_payload, dict):
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

        enabled_flag = bool(meta_payload.get("enabled", False))
        active_template_id = str(meta_payload.get("active_template_id", "")).strip()
        updated_at_text = str(meta_payload.get("updated_at", "")).strip()

        # 若元配置中的 active_template_id 已不在模板列表中，则在读取视图时回退为“未启用”
        if enabled_flag and active_template_id:
            if not any(
                str(t.get("template_id", "")).strip() == active_template_id for t in templates
            ):
                enabled_flag = False
                active_template_id = ""

        result: dict[str, object] = {
            "templates": templates,
            "enabled": enabled_flag,
            "active_template_id": active_template_id,
        }
        if updated_at_text:
            result["updated_at"] = updated_at_text
        return result
    
    @property
    def signals(self) -> Dict[str, SignalConfig]:
        """获取所有信号配置（基于代码级定义的全局聚合视图）。"""
        if self._signals_cache is None:
            schema_view = DefinitionSchemaView()
            all_signal_payloads = schema_view.get_all_signal_definitions()
            cache: Dict[str, SignalConfig] = {}

            for signal_id, payload in all_signal_payloads.items():
                if not isinstance(payload, dict):
                    continue
                cache[signal_id] = SignalConfig.deserialize(payload)

            self._signals_cache = cache

        return self._signals_cache
    
    def get_template(self, template_id: str) -> Optional[TemplateConfig]:
        """获取模板"""
        return self.templates.get(template_id)
    
    def get_instance(self, instance_id: str) -> Optional[InstanceConfig]:
        """获取实例"""
        return self.instances.get(instance_id)
    
    def add_template(self, template: TemplateConfig) -> None:
        """添加模板"""
        # 保存到资源管理器
        template_data = template.serialize()
        self.resource_manager.save_resource(
            ResourceType.TEMPLATE,
            template.template_id,
            template_data
        )
        
        # 清除缓存
        self._templates_cache = None
    
    def remove_template(self, template_id: str) -> None:
        """移除模板（只从缓存清除，不删除文件）"""
        # 在全局视图中，不实际删除资源
        self._templates_cache = None
    
    def add_instance(self, instance: InstanceConfig) -> None:
        """添加实例"""
        # 保存到资源管理器
        instance_data = instance.serialize()
        self.resource_manager.save_resource(
            ResourceType.INSTANCE,
            instance.instance_id,
            instance_data
        )
        
        # 清除缓存
        self._instances_cache = None
    
    def remove_instance(self, instance_id: str) -> None:
        """移除实例（只从缓存清除，不删除文件）"""
        # 在全局视图中，不实际删除资源
        self._instances_cache = None
    
    def serialize(self) -> dict:
        """序列化（全局视图不支持导出）"""
        return {
            "error": "全局视图不支持导出，请选择具体的存档"
        }
    
    def clear_cache(self) -> None:
        """清除所有缓存"""
        self._templates_cache = None
        self._instances_cache = None
        self._combat_presets_cache = None
        self._management_cache = None
        self._signals_cache = None

