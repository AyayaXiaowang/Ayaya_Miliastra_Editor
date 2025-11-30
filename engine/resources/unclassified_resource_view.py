"""未分类资源视图 - 仅显示未被任何存档引用的资源"""

from __future__ import annotations
from typing import Dict, Optional, List

from engine.resources.resource_manager import ResourceManager
from engine.configs.resource_types import ResourceType
from engine.resources.management_view_helpers import (
    MANAGEMENT_FIELD_TO_RESOURCE_TYPE,
    SINGLE_CONFIG_MANAGEMENT_FIELDS,
)
from engine.graph.models.package_model import (
    TemplateConfig,
    InstanceConfig,
    CombatPresets,
    ManagementData,
)
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.ingame_save_template_schema_view import (
    get_default_ingame_save_template_schema_view,
)


class UnclassifiedResourceView:
    """未分类资源视图 - 显示所有未被任何存档纳入的资源
    
    该视图与 GlobalResourceView/PackageView 对齐接口，便于 UI 复用。
    """

    def __init__(self, resource_manager: ResourceManager, package_index_manager: PackageIndexManager):
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager

        # 模拟存档必要字段
        self.package_id = "unclassified_view"
        self.name = "<未分类资源>"
        self.description = "未分类资源浏览模式"
        self.created_at = ""
        self.updated_at = ""
        self.todo_states: Dict[str, bool] = {}

        # 缓存
        self._templates_cache: Optional[Dict[str, TemplateConfig]] = None
        self._instances_cache: Optional[Dict[str, InstanceConfig]] = None
        self._combat_presets_cache: Optional[CombatPresets] = None
        self._management_cache: Optional[ManagementData] = None
        self._signals_cache: Optional[Dict] = None
        self._level_entity_cache: Optional[InstanceConfig] = None

        # 预构建已归类资源ID集合
        self._classified_ids: Dict[str, set[str]] = self._build_classified_id_sets()

        # 图的未分类集合延迟计算
        self._unclassified_graph_ids: Optional[set[str]] = None

    def _build_classified_id_sets(self) -> Dict[str, set[str]]:
        """汇总所有存档索引中的资源ID，形成分类集合
        
        返回：按逻辑域划分的 ID 集合字典。
        键包括：templates、instances、graphs、combat:<type>、management:<type>
        """
        id_sets: Dict[str, set[str]] = {}
        for key in [
            "templates", "instances", "graphs",
            "combat:player_templates", "combat:player_classes", "combat:unit_statuses", "combat:skills",
            "combat:projectiles", "combat:items",
            "management:timers", "management:level_variables", "management:preset_points",
            "management:skill_resources", "management:currency_backpack", "management:equipment_data",
            "management:shop_templates", "management:ui_layouts", "management:ui_widget_templates",
            "management:multi_language", "management:main_cameras", "management:light_sources",
            "management:background_music", "management:paths", "management:entity_deployment_groups",
            "management:unit_tags", "management:scan_tags", "management:shields",
            "management:peripheral_systems", "management:save_points", "management:chat_channels",
            "management:level_settings",
        ]:
            id_sets[key] = set()

        packages = self.package_index_manager.list_packages()
        for pkg_info in packages:
            pkg_index = self.package_index_manager.load_package_index(pkg_info["package_id"]) 
            if not pkg_index:
                continue

            # 基础资源
            for rid in pkg_index.resources.templates:
                id_sets["templates"].add(rid)
            for rid in pkg_index.resources.instances:
                id_sets["instances"].add(rid)
            for rid in pkg_index.resources.graphs:
                id_sets["graphs"].add(rid)

            # 战斗预设
            combat = pkg_index.resources.combat_presets
            id_sets["combat:player_templates"].update(combat.get("player_templates", []))
            id_sets["combat:player_classes"].update(combat.get("player_classes", []))
            id_sets["combat:unit_statuses"].update(combat.get("unit_statuses", []))
            id_sets["combat:skills"].update(combat.get("skills", []))
            id_sets["combat:projectiles"].update(combat.get("projectiles", []))
            id_sets["combat:items"].update(combat.get("items", []))

            # 管理配置
            mgmt = pkg_index.resources.management
            for field in list(id_sets.keys()):
                if field.startswith("management:"):
                    key = field.split(":", 1)[1]
                    id_sets[field].update(mgmt.get(key, []))

        return id_sets

    def get_unclassified_graph_ids(self) -> set[str]:
        """获取未被任何存档引用或纳入的节点图ID集合

        判定标准：
        - 若图被任何包的 `resources.graphs` 纳入，视为已分类
        - 若图被任何模板的 `default_graphs` 或实例/关卡实体的 `additional_graphs` 引用，视为已分类
        其余视为未分类
        """
        if self._unclassified_graph_ids is not None:
            return self._unclassified_graph_ids

        # 已分类：来自 resources.graphs
        classified: set[str] = set(self._classified_ids.get("graphs", set()))

        # 收集模板/实例引用
        packages = self.package_index_manager.list_packages()
        for pkg_info in packages:
            pkg_id = pkg_info.get("package_id", "")
            pkg_index = self.package_index_manager.load_package_index(pkg_id)
            if not pkg_index:
                continue

            # 模板 default_graphs
            for template_id in pkg_index.resources.templates:
                data = self.resource_manager.load_resource(ResourceType.TEMPLATE, template_id)
                if data:
                    default_graphs = data.get("default_graphs", [])
                    for gid in default_graphs:
                        classified.add(gid)

            # 实例 additional_graphs
            for instance_id in pkg_index.resources.instances:
                data = self.resource_manager.load_resource(ResourceType.INSTANCE, instance_id)
                if data:
                    additional_graphs = data.get("additional_graphs", [])
                    for gid in additional_graphs:
                        classified.add(gid)

            # 关卡实体 additional_graphs
            if pkg_index.level_entity_id:
                le_data = self.resource_manager.load_resource(ResourceType.INSTANCE, pkg_index.level_entity_id)
                if le_data:
                    additional_graphs = le_data.get("additional_graphs", [])
                    for gid in additional_graphs:
                        classified.add(gid)

        # 全量图ID
        all_graph_ids = set(self.resource_manager.list_resources(ResourceType.GRAPH))
        self._unclassified_graph_ids = all_graph_ids - classified
        return self._unclassified_graph_ids

    @property
    def templates(self) -> Dict[str, TemplateConfig]:
        if self._templates_cache is None:
            self._templates_cache = {}
            all_ids = self.resource_manager.list_resources(ResourceType.TEMPLATE)
            for template_id in all_ids:
                if template_id in self._classified_ids["templates"]:
                    continue
                data = self.resource_manager.load_resource(ResourceType.TEMPLATE, template_id)
                if data:
                    self._templates_cache[template_id] = TemplateConfig.deserialize(data)
        return self._templates_cache

    @property
    def instances(self) -> Dict[str, InstanceConfig]:
        if self._instances_cache is None:
            self._instances_cache = {}
            all_ids = self.resource_manager.list_resources(ResourceType.INSTANCE)
            for instance_id in all_ids:
                if instance_id in self._classified_ids["instances"]:
                    continue
                data = self.resource_manager.load_resource(ResourceType.INSTANCE, instance_id)
                if data:
                    self._instances_cache[instance_id] = InstanceConfig.deserialize(data)
        return self._instances_cache

    @property
    def level_entity(self) -> Optional[InstanceConfig]:
        """获取未分类视图下的关卡实体（若存在）。

        设计约定：
        - 仅返回尚未被任何功能包纳入的关卡实体（metadata.is_level_entity 为 True 且未被索引为实例）
        - 便于在“未分类资源”模式下为新建的关卡实体设置“所属存档”并完成首次绑定
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
        if self._combat_presets_cache is None:
            combat_presets_data = {
                "player_templates": {},
                "player_classes": {},
                "unit_statuses": {},
                "skills": {},
                "projectiles": {},
                "items": {}
            }

            def load_unclassified(resource_type: ResourceType, bucket_key: str, id_key: str) -> None:
                all_ids = self.resource_manager.list_resources(resource_type)
                classified = self._classified_ids[id_key]
                for rid in all_ids:
                    if rid in classified:
                        continue
                    data = self.resource_manager.load_resource(resource_type, rid)
                    if data:
                        combat_presets_data[bucket_key][rid] = data

            load_unclassified(ResourceType.PLAYER_TEMPLATE, "player_templates", "combat:player_templates")
            load_unclassified(ResourceType.PLAYER_CLASS, "player_classes", "combat:player_classes")
            load_unclassified(ResourceType.UNIT_STATUS, "unit_statuses", "combat:unit_statuses")
            load_unclassified(ResourceType.SKILL, "skills", "combat:skills")
            load_unclassified(ResourceType.PROJECTILE, "projectiles", "combat:projectiles")
            load_unclassified(ResourceType.ITEM, "items", "combat:items")

            self._combat_presets_cache = CombatPresets.deserialize(combat_presets_data)

        return self._combat_presets_cache

    @property
    def management(self) -> ManagementData:
        if self._management_cache is None:
            management_data: Dict[str, object] = {}

            # 映射与“单一配置体”字段集合由 management_view_helpers 统一维护，
            # 这里在未分类视图下基于“已归类 ID 集合”推导出未分类资源视图。
            for management_field_name, resource_type in MANAGEMENT_FIELD_TO_RESOURCE_TYPE.items():
                classified_key = f"management:{management_field_name}"
                all_resource_ids = self.resource_manager.list_resources(resource_type)
                classified_ids = self._classified_ids[classified_key]
                unclassified_ids = [
                    resource_id
                    for resource_id in all_resource_ids
                    if resource_id not in classified_ids
                ]

                # 局内存档管理：在未分类视图下，同样以“全局元配置 + 未归档模板列表”的方式呈现。
                if management_field_name == "save_points":
                    management_data[management_field_name] = (
                        self._build_save_points_config_for_unclassified_view(
                            classified_ids,
                        )
                    )
                    continue

                # 单配置字段：在“未分类资源”视图中，同样只关心一份聚合配置体。
                # 约定：优先选择 global_view_<field> 这类全局配置资源（若仍未被任何包引用），
                # 否则在存在多份未归档配置时保持空字典，由 UI 决定是否新建。
                if management_field_name in SINGLE_CONFIG_MANAGEMENT_FIELDS:
                    preferred_id = f"global_view_{management_field_name}"
                    selected_payload: dict | None = None

                    if preferred_id in unclassified_ids:
                        candidate = self.resource_manager.load_resource(
                            resource_type,
                            preferred_id,
                        )
                        if isinstance(candidate, dict):
                            selected_payload = candidate

                    management_data[management_field_name] = selected_payload or {}
                    continue

                # 多配置字段：聚合所有“未被任何包引用”的资源为 {id: payload}
                unclassified_resources: Dict[str, dict] = {}
                for resource_id in unclassified_ids:
                    data = self.resource_manager.load_resource(resource_type, resource_id)
                    if isinstance(data, dict):
                        unclassified_resources[resource_id] = data
                management_data[management_field_name] = unclassified_resources

            self._management_cache = ManagementData.deserialize(management_data)

        return self._management_cache

    def _build_save_points_config_for_unclassified_view(
        self,
        classified_ids: set[str],
    ) -> dict:
        """构建未分类视图下的局内存档聚合配置。

        - 模板来源：所有代码级局内存档模板中未被任何包引用的记录；
        - 元配置：与全局视图共用 `global_view_save_points` 资源中的启用状态与当前模板 ID。
        """
        aggregator_id = "global_view_save_points"

        # 读取全局元配置（与 GlobalResourceView 共用）
        meta_payload: dict = {}
        if self.resource_manager.resource_exists(ResourceType.SAVE_POINT, aggregator_id):
            candidate = self.resource_manager.load_resource(ResourceType.SAVE_POINT, aggregator_id)
            if isinstance(candidate, dict):
                meta_payload = {
                    "enabled": bool(candidate.get("enabled", False)),
                    "active_template_id": str(candidate.get("active_template_id", "")).strip(),
                    "updated_at": str(candidate.get("updated_at", "")),
                }

        # 从代码级模板中筛选出“未被任何包引用”的模板
        schema_view = get_default_ingame_save_template_schema_view()
        all_templates = schema_view.get_all_templates()

        templates: list[dict] = []
        for template_id, original_payload in all_templates.items():
            if template_id in classified_ids:
                continue
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

        def _template_sort_key(payload: dict) -> tuple[str, str]:
            name_text = str(payload.get("template_name", "")).strip().lower()
            id_text = str(payload.get("template_id", "")).strip().lower()
            return name_text, id_text

        templates.sort(key=_template_sort_key)

        enabled_flag = bool(meta_payload.get("enabled", False))
        active_template_id = str(meta_payload.get("active_template_id", "")).strip()
        updated_at_text = str(meta_payload.get("updated_at", "")).strip()

        # active_template_id 不在当前未分类集合中时，仅在视图层关闭启用状态
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
    def signals(self) -> Dict:
        # 未分类视图没有存档级信号配置
        if self._signals_cache is None:
            self._signals_cache = {}
        return self._signals_cache

    def get_template(self, template_id: str) -> Optional[TemplateConfig]:
        return self.templates.get(template_id)

    def get_instance(self, instance_id: str) -> Optional[InstanceConfig]:
        return self.instances.get(instance_id)

    def add_template(self, template: TemplateConfig) -> None:
        # 保存到资源管理器；不加入任何存档
        self.resource_manager.save_resource(
            ResourceType.TEMPLATE, template.template_id, template.serialize()
        )
        self._templates_cache = None

    def remove_template(self, template_id: str) -> None:
        # 未分类视图不删除文件，仅清理缓存
        self._templates_cache = None

    def add_instance(self, instance: InstanceConfig) -> None:
        self.resource_manager.save_resource(
            ResourceType.INSTANCE, instance.instance_id, instance.serialize()
        )
        self._instances_cache = None

    def remove_instance(self, instance_id: str) -> None:
        self._instances_cache = None

    def serialize(self) -> dict:
        return {"error": "未分类资源视图不支持导出，请选择具体的存档"}

    def clear_cache(self) -> None:
        self._templates_cache = None
        self._instances_cache = None
        self._combat_presets_cache = None
        self._management_cache = None
        self._signals_cache = None


