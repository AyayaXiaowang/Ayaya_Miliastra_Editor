"""地图视图 - 用于兼容旧UI，从资源管理器动态组装数据"""

from __future__ import annotations
from typing import Dict, Optional, List
from datetime import datetime

from engine.resources.resource_manager import ResourceManager
from engine.configs.resource_types import ResourceType
from engine.resources.management_view_helpers import (
    MANAGEMENT_FIELD_TO_RESOURCE_TYPE,
    SINGLE_CONFIG_MANAGEMENT_FIELDS,
)
from engine.resources.package_index import PackageIndex
from engine.resources.global_resource_view import GlobalResourceView
from engine.signal import get_default_signal_repository
from engine.graph.models.package_model import (
    TemplateConfig,
    InstanceConfig,
    CombatPresets,
    ManagementData,
    SignalConfig,
)


class PackageView:
    """地图视图 - 模拟旧的PackageModel接口，但数据来自资源管理器"""
    
    def __init__(
        self,
        package_index: PackageIndex,
        resource_manager: ResourceManager
    ):
        self.package_index = package_index
        self.resource_manager = resource_manager
        
        # 基本属性
        self.package_id = package_index.package_id
        self.name = package_index.name
        self.description = package_index.description
        self.created_at = package_index.created_at
        self.updated_at = package_index.updated_at
        self.todo_states = package_index.todo_states
        
        # 缓存的资源数据
        self._templates_cache: Optional[Dict[str, TemplateConfig]] = None
        self._instances_cache: Optional[Dict[str, InstanceConfig]] = None
        self._level_entity_cache: Optional[InstanceConfig] = None
        self._combat_presets_cache: Optional[CombatPresets] = None
        self._management_cache: Optional[ManagementData] = None
        self._signals_cache: Optional[Dict] = None
    
    def clear_cache(self) -> None:
        """清空当前视图缓存，使下次访问时从 ResourceManager 重新加载。"""
        self._templates_cache = None
        self._instances_cache = None
        self._level_entity_cache = None
        self._combat_presets_cache = None
        self._management_cache = None
        self._signals_cache = None
    
    @property
    def templates(self) -> Dict[str, TemplateConfig]:
        """获取模板字典（懒加载）"""
        if self._templates_cache is None:
            self._templates_cache = {}
            for template_id in self.package_index.resources.templates:
                template_data = self.resource_manager.load_resource(
                    ResourceType.TEMPLATE,
                    template_id
                )
                if template_data:
                    self._templates_cache[template_id] = TemplateConfig.deserialize(template_data)
        return self._templates_cache
    
    @property
    def instances(self) -> Dict[str, InstanceConfig]:
        """获取实例字典（懒加载）"""
        if self._instances_cache is None:
            self._instances_cache = {}
            for instance_id in self.package_index.resources.instances:
                instance_data = self.resource_manager.load_resource(
                    ResourceType.INSTANCE,
                    instance_id
                )
                if instance_data:
                    self._instances_cache[instance_id] = InstanceConfig.deserialize(instance_data)
        return self._instances_cache
    
    @property
    def level_entity(self) -> Optional[InstanceConfig]:
        """获取关卡实体。

        设计约定：
        - 优先按照 PackageIndex.level_entity_id 从资源库加载关卡实体；
        - 若索引尚未写入 level_entity_id，但实例中已存在带 is_level_entity 标记的实体，
          则自动补写索引并复用该实例（兼容旧数据或外部手动创建的关卡实体）。
        """
        # 1. 优先使用已缓存结果，避免重复反序列化
        if self._level_entity_cache is not None:
            return self._level_entity_cache

        # 2. 按索引中的 level_entity_id 从资源库加载
        level_entity_id = self.package_index.level_entity_id
        if isinstance(level_entity_id, str) and level_entity_id:
            level_entity_data = self.resource_manager.load_resource(
                ResourceType.INSTANCE,
                level_entity_id,
            )
            if isinstance(level_entity_data, dict):
                self._level_entity_cache = InstanceConfig.deserialize(level_entity_data)
                return self._level_entity_cache

        # 3. 兼容旧数据：若索引中尚未记录 level_entity_id，但实例中已有带 is_level_entity 标记的实体，
        #    则自动识别并补写索引，后续访问统一走索引路径。
        for instance_id, instance in self.instances.items():
            metadata = getattr(instance, "metadata", {}) or {}
            if isinstance(metadata, dict) and metadata.get("is_level_entity"):
                self._level_entity_cache = instance

                # 索引未记录时补写关卡实体 ID，并确保被视为当前存档的实例资源
                if not isinstance(self.package_index.level_entity_id, str) or not self.package_index.level_entity_id:
                    self.package_index.level_entity_id = instance_id
                    if instance_id not in self.package_index.resources.instances:
                        self.package_index.add_instance(instance_id)

                return self._level_entity_cache

        # 4. 当前存档确实不存在关卡实体
        return None
    
    @property
    def combat_presets(self) -> CombatPresets:
        """获取战斗预设（懒加载）"""
        if self._combat_presets_cache is None:
            combat_presets_data = {
                "player_templates": {},
                "player_classes": {},
                "unit_statuses": {},
                "skills": {},
                "projectiles": {},
                "items": {}
            }
            
            # 玩家模板：按索引引用的玩家模板资源聚合为字典
            for template_id in self.package_index.resources.combat_presets.get("player_templates", []):
                data = self.resource_manager.load_resource(ResourceType.PLAYER_TEMPLATE, template_id)
                if data:
                    combat_presets_data["player_templates"][template_id] = data
            
            # 加载各类战斗预设
            for class_id in self.package_index.resources.combat_presets.get("player_classes", []):
                data = self.resource_manager.load_resource(ResourceType.PLAYER_CLASS, class_id)
                if data:
                    combat_presets_data["player_classes"][class_id] = data
            
            for status_id in self.package_index.resources.combat_presets.get("unit_statuses", []):
                data = self.resource_manager.load_resource(ResourceType.UNIT_STATUS, status_id)
                if data:
                    combat_presets_data["unit_statuses"][status_id] = data
            
            for skill_id in self.package_index.resources.combat_presets.get("skills", []):
                data = self.resource_manager.load_resource(ResourceType.SKILL, skill_id)
                if data:
                    combat_presets_data["skills"][skill_id] = data
            
            for projectile_id in self.package_index.resources.combat_presets.get("projectiles", []):
                data = self.resource_manager.load_resource(ResourceType.PROJECTILE, projectile_id)
                if data:
                    combat_presets_data["projectiles"][projectile_id] = data
            
            for item_id in self.package_index.resources.combat_presets.get("items", []):
                data = self.resource_manager.load_resource(ResourceType.ITEM, item_id)
                if data:
                    combat_presets_data["items"][item_id] = data
            
            self._combat_presets_cache = CombatPresets.deserialize(combat_presets_data)
        
        return self._combat_presets_cache
    
    @property
    def management(self) -> ManagementData:
        """获取管理数据（懒加载）"""
        if self._management_cache is None:
            management_data: Dict[str, object] = {}

            # 映射与“单一配置体”字段集合由 management_view_helpers 统一维护，
            # 便于 PackageView/GlobalResourceView/UnclassifiedResourceView 共享一致语义。
            for management_field_name, resource_type in MANAGEMENT_FIELD_TO_RESOURCE_TYPE.items():
                # 局内存档管理：在具体存档视图下仅通过“所属存档”多选行维护模板归属，
                # 聚合编辑仍在 <全部资源>/<未分类资源> 视图中完成，这里提供一个空配置体。
                if management_field_name == "save_points":
                    management_data[management_field_name] = {}
                    continue

                resource_ids = self.package_index.resources.management.get(
                    management_field_name,
                    [],
                )
                management_resources: Dict[str, dict] = {}

                for resource_id in resource_ids:
                    data = self.resource_manager.load_resource(resource_type, resource_id)
                    if data:
                        management_resources[resource_id] = data

                if management_field_name in SINGLE_CONFIG_MANAGEMENT_FIELDS:
                    # 对于仅支持单一配置对象的管理项，直接取首个配置体
                    if management_resources:
                        # values() 顺序与 resource_ids 一致；只取第一份配置
                        management_data[management_field_name] = next(
                            iter(management_resources.values())
                        )
                    else:
                        management_data[management_field_name] = {}
                else:
                    # 常规管理项：使用 {resource_id: payload} 形式
                    management_data[management_field_name] = management_resources
            
            self._management_cache = ManagementData.deserialize(management_data)
        
        return self._management_cache
    
    @property
    def signals(self) -> Dict[str, SignalConfig]:
        """获取信号配置。

        新约定：
        - 信号定义的唯一真相源为 `assets/资源库/管理配置/信号` 目录下的代码级资源
          （通过 `SignalDefinitionRepository` / `DefinitionSchemaView` 聚合为只读视图）；
        - `PackageIndex.signals` 仅保存当前包“引用了哪些 signal_id”的摘要信息；
        - 若当前包未声明任意信号，则回退为全局视图中的所有信号。
        """
        if self._signals_cache is None:
            self._signals_cache = {}

            repo = get_default_signal_repository()
            all_signal_payloads = repo.get_all_payloads()

            if isinstance(self.package_index.signals, dict) and self.package_index.signals:
                for signal_id in self.package_index.signals.keys():
                    if not isinstance(signal_id, str) or not signal_id:
                        continue

                    payload = all_signal_payloads.get(str(signal_id))
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
            else:
                global_view = GlobalResourceView(self.resource_manager)
                self._signals_cache.update(global_view.signals)

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
        
        # 添加到地图索引
        self.package_index.add_template(template.template_id)
        
        # 清除缓存
        self._templates_cache = None
    
    def remove_template(self, template_id: str) -> None:
        """移除模板"""
        # 从地图索引移除
        self.package_index.remove_template(template_id)
        
        # 清除缓存
        self._templates_cache = None
        
        # 注意：不删除资源文件，因为可能被其他地图引用
    
    def add_instance(self, instance: InstanceConfig) -> None:
        """添加实例"""
        # 保存到资源管理器
        instance_data = instance.serialize()
        self.resource_manager.save_resource(
            ResourceType.INSTANCE,
            instance.instance_id,
            instance_data
        )
        
        # 添加到地图索引
        self.package_index.add_instance(instance.instance_id)
        
        # 清除缓存
        self._instances_cache = None
    
    def remove_instance(self, instance_id: str) -> None:
        """移除实例"""
        # 不允许删除关卡实体
        if instance_id == self.package_index.level_entity_id:
            raise ValueError("不允许删除关卡实体")
        
        # 从地图索引移除
        self.package_index.remove_instance(instance_id)
        
        # 清除缓存
        self._instances_cache = None
    
    def update_level_entity(self, level_entity: InstanceConfig) -> None:
        """更新关卡实体"""
        # 保存到资源管理器
        level_entity_data = level_entity.serialize()
        self.resource_manager.save_resource(
            ResourceType.INSTANCE,
            level_entity.instance_id,
            level_entity_data
        )
        
        # 清除缓存
        self._level_entity_cache = None
    
    def serialize(self) -> dict:
        """序列化为兼容格式（用于导出等）
        
        导出为旧格式（嵌入式），用于地图导出和向后兼容
        """
        return {
            "package_id": self.package_id,
            "name": self.name,
            "description": self.description,
            "templates": {tid: t.serialize() for tid, t in self.templates.items()},
            "instances": {iid: i.serialize() for iid, i in self.instances.items()},
            "level_entity": self.level_entity.serialize() if self.level_entity else None,
            "combat_presets": self.combat_presets.serialize(),
            "management": self.management.serialize(),
            "signals": {sid: s.serialize() for sid, s in self.signals.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

