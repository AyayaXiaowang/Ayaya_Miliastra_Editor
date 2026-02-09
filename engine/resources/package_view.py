"""存档视图 - 基于 PackageIndex 从资源管理器聚合存档内引用的数据。

术语澄清（目录即项目存档模式）：
- `PackageIndex` 在运行期通常是“从项目存档目录派生出来的内存快照”（不再写回 pkg_*.json）。
- `PackageIndex.resources.*` 表达的是“当前项目存档目录内”有哪些资源（本质上等价于文件位于
  `assets/资源库/项目存档/<package_id>/...` 的集合），而不是一个可独立落盘的引用表。
- 因此：
  - 编辑已有资源：直接保存资源文件（保持其所在资源根目录不变）；
  - 新建资源：需要明确写入到当前项目存档根目录，避免落入默认归档项目；
  - 变更资源“所属存档/归属位置”：应通过 `PackageIndexManager.move_resource_to_root(...)` 做文件移动。
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

from engine.resources.resource_manager import ResourceManager
from engine.configs.resource_types import ResourceType
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir
from engine.resources.management_view_helpers import (
    MANAGEMENT_FIELD_TO_RESOURCE_TYPE,
    SINGLE_CONFIG_MANAGEMENT_FIELDS,
)
from engine.resources.package_index import PackageIndex
from engine.resources.global_resource_view import GlobalResourceView
from engine.signal import get_default_signal_repository
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


class PackageView:
    """存档视图：以 PackageIndex 为索引，从资源管理器聚合模板/实例/管理配置等数据。"""
    
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
        self._templates_loaded_all: bool = False
        self._instances_cache: Optional[Dict[str, InstanceConfig]] = None
        self._instances_loaded_all: bool = False
        self._level_entity_cache: Optional[InstanceConfig] = None
        self._combat_presets_cache: Optional[CombatPresets] = None
        self._management_cache: Optional[ManagementData] = None
        self._signals_cache: Optional[Dict] = None
    
    def clear_cache(self) -> None:
        """清空当前视图缓存，使下次访问时从 ResourceManager 重新加载。"""
        self._templates_cache = None
        self._templates_loaded_all = False
        self._instances_cache = None
        self._instances_loaded_all = False
        self._level_entity_cache = None
        self._combat_presets_cache = None
        self._management_cache = None
        self._signals_cache = None

    @staticmethod
    def _is_path_under(root_dir: Path, file_path: Path) -> bool:
        """判断 file_path 是否位于 root_dir 子树下（兼容 Python < 3.9）。"""
        resolved_root = root_dir.resolve()
        resolved_file = file_path.resolve()
        if hasattr(resolved_file, "is_relative_to"):
            return resolved_file.is_relative_to(resolved_root)  # type: ignore[attr-defined]
        root_parts = resolved_root.parts
        file_parts = resolved_file.parts
        return len(file_parts) >= len(root_parts) and file_parts[: len(root_parts)] == root_parts

    def _get_shared_and_package_root_dirs(self) -> tuple[Path | None, Path | None]:
        """返回 (shared_root_dir, package_root_dir)。

        - shared_root_dir: assets/资源库/共享
        - package_root_dir: assets/资源库/项目存档/<package_id>
        """
        resource_library_dir = getattr(self.resource_manager, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            return None, None
        shared_root_dir = get_shared_root_dir(resource_library_dir)
        package_root_dir = get_packages_root_dir(resource_library_dir) / str(self.package_id)
        return shared_root_dir, package_root_dir

    def _collect_shared_resource_ids(self, resource_type: ResourceType) -> list[str]:
        """收集当前作用域下“位于共享根目录”的资源 ID 列表（稳定排序）。"""
        shared_root_dir, _package_root_dir = self._get_shared_and_package_root_dirs()
        if shared_root_dir is None:
            return []

        shared_ids: list[str] = []
        resource_paths = self.resource_manager.list_resource_file_paths(resource_type)
        for resource_id, file_path in resource_paths.items():
            if not isinstance(resource_id, str) or not resource_id:
                continue
            if not isinstance(file_path, Path):
                continue
            if self._is_path_under(shared_root_dir, file_path):
                shared_ids.append(resource_id)

        shared_ids.sort(key=lambda text: text.casefold())
        return shared_ids
    
    @property
    def templates(self) -> Dict[str, TemplateConfig]:
        """获取模板字典（懒加载）"""
        if self._templates_cache is None:
            self._templates_cache = {}
            self._templates_loaded_all = False

        if not self._templates_loaded_all:
            # 具体存档视图下：列表展示需要包含（当前存档 + 共享）两类根目录下的模板。
            # 注意：PackageIndex.resources.templates 仍只表示“存档目录内的模板集合”。
            visible_template_ids: list[str] = []
            for template_id in self.package_index.resources.templates:
                if template_id not in visible_template_ids:
                    visible_template_ids.append(template_id)

            for template_id in self._collect_shared_resource_ids(ResourceType.TEMPLATE):
                if template_id not in visible_template_ids:
                    visible_template_ids.append(template_id)

            for template_id in visible_template_ids:
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
        """获取实例字典（懒加载）"""
        if self._instances_cache is None:
            self._instances_cache = {}
            self._instances_loaded_all = False

        if not self._instances_loaded_all:
            # 具体存档视图下：实体摆放列表需要包含（当前存档 + 共享）两类根目录下的实例。
            visible_instance_ids: list[str] = []
            for instance_id in self.package_index.resources.instances:
                if instance_id not in visible_instance_ids:
                    visible_instance_ids.append(instance_id)

            for instance_id in self._collect_shared_resource_ids(ResourceType.INSTANCE):
                if instance_id not in visible_instance_ids:
                    visible_instance_ids.append(instance_id)

            for instance_id in visible_instance_ids:
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
        """获取关卡实体。

        设计约定：
        - 仅按 PackageIndex.level_entity_id 从资源库加载关卡实体。
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
                level_entity_obj = InstanceConfig.deserialize(level_entity_data)
                source_mtime = self.resource_manager.get_resource_file_mtime(
                    ResourceType.INSTANCE,
                    str(level_entity_id),
                )
                if source_mtime is not None:
                    setattr(level_entity_obj, "_source_mtime", float(source_mtime))
                self._level_entity_cache = level_entity_obj
                return self._level_entity_cache

        # 3. 当前存档确实不存在关卡实体
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
                if management_field_name == "level_variables":
                    schema_view = get_default_level_variable_schema_view()
                    # 关卡变量（代码资源）：在具体存档视图下应可见“共享 + 当前存档”两类资源根目录下的变量文件。
                    package_file_ids = self.package_index.resources.management.get(
                        management_field_name,
                        [],
                    )
                    resource_ids: list[str] = []
                    if isinstance(package_file_ids, list):
                        for file_id in package_file_ids:
                            if isinstance(file_id, str) and file_id.strip() and file_id not in resource_ids:
                                resource_ids.append(file_id.strip())

                    shared_root_dir, _package_root_dir = self._get_shared_and_package_root_dirs()
                    if shared_root_dir is not None:
                        shared_base_dir = shared_root_dir / "管理配置" / "关卡变量"
                        variable_files = schema_view.get_all_variable_files() or {}
                        shared_file_ids: list[str] = []
                        for file_id, info in variable_files.items():
                            absolute_path = getattr(info, "absolute_path", None)
                            if not isinstance(absolute_path, Path):
                                continue
                            if self._is_path_under(shared_base_dir, absolute_path):
                                shared_file_ids.append(str(file_id))
                        shared_file_ids.sort(key=lambda text: text.casefold())
                        for file_id in shared_file_ids:
                            if file_id not in resource_ids:
                                resource_ids.append(file_id)

                    if not resource_ids:
                        management_data[management_field_name] = {}
                        continue

                    # 现行语义：存档索引中记录的是“变量文件 ID（VARIABLE_FILE_ID）”，
                    # 需要从这些文件中收敛出 {variable_id: payload} 的平铺视图。
                    variable_files = schema_view.get_all_variable_files() or {}

                    flattened: Dict[str, dict] = {}
                    for referenced_id in resource_ids:
                        if not isinstance(referenced_id, str) or not referenced_id.strip():
                            continue
                        referenced_id_text = referenced_id.strip()

                        # 1) 变量文件 ID
                        file_info = variable_files.get(referenced_id_text)
                        if file_info is not None:
                            for variable_payload in file_info.variables:
                                if not isinstance(variable_payload, dict):
                                    continue
                                variable_id = variable_payload.get("variable_id")
                                if isinstance(variable_id, str) and variable_id.strip():
                                    flattened[variable_id.strip()] = variable_payload
                            continue

                    management_data[management_field_name] = flattened
                    continue

                # 局内存档管理：在具体存档视图下仅通过“所属存档”多选行维护模板归属，
                # 聚合编辑仍在 <共享资源>/<未分类资源> 视图中完成，这里提供一个空配置体。
                if management_field_name == "save_points":
                    management_data[management_field_name] = {}
                    continue

                package_ids_raw = self.package_index.resources.management.get(
                    management_field_name,
                    [],
                )
                resource_ids: list[str] = []
                if isinstance(package_ids_raw, list):
                    for value in package_ids_raw:
                        if isinstance(value, str) and value.strip() and value.strip() not in resource_ids:
                            resource_ids.append(value.strip())

                # 具体存档视图下：管理配置同样需要包含共享根目录下的资源。
                for shared_id in self._collect_shared_resource_ids(resource_type):
                    if shared_id not in resource_ids:
                        resource_ids.append(shared_id)
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
        - 具体存档视图下需要同时可见：共享根 + 当前存档根目录下的信号定义。
        """
        if self._signals_cache is None:
            self._signals_cache = {}

            # 以当前 ResourceManager 的索引作用域为准：共享根 + 当前存档根目录。
            signal_ids = self.resource_manager.list_resources(ResourceType.SIGNAL)
            normalized_ids = [str(value) for value in signal_ids if isinstance(value, str) and value]
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

        # 允许在具体存档视图下直接获取共享根目录中的模板（所有存档可见）。
        if template_id not in self.package_index.resources.templates:
            shared_root_dir, package_root_dir = self._get_shared_and_package_root_dirs()
            file_path = self.resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(template_id)
            if (
                shared_root_dir is None
                or package_root_dir is None
                or not isinstance(file_path, Path)
                or not (
                    self._is_path_under(shared_root_dir, file_path)
                    or self._is_path_under(package_root_dir, file_path)
                )
            ):
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

        # 允许在具体存档视图下直接获取共享根目录中的实例（所有存档可见）。
        if instance_id not in self.package_index.resources.instances:
            shared_root_dir, package_root_dir = self._get_shared_and_package_root_dirs()
            file_path = self.resource_manager.list_resource_file_paths(ResourceType.INSTANCE).get(instance_id)
            if (
                shared_root_dir is None
                or package_root_dir is None
                or not isinstance(file_path, Path)
                or not (
                    self._is_path_under(shared_root_dir, file_path)
                    or self._is_path_under(package_root_dir, file_path)
                )
            ):
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
        """添加模板（新建资源）。

        注意（目录即项目存档模式）：
        - 新建资源如果不指定 `resource_root_dir`，资源层会把它写入默认归档项目（例如 “测试项目”），
          从而导致当前项目存档视图不可见；
        - 因此这里需要把“新建模板”的落点明确写到当前项目存档根目录下。
        """
        template_data = template.serialize()

        existing_file = self.resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(
            str(template.template_id)
        )
        if existing_file is None:
            _shared_root_dir, package_root_dir = self._get_shared_and_package_root_dirs()
            if package_root_dir is None:
                raise ValueError("无法解析当前项目存档根目录，无法写入新建模板资源")
            self.resource_manager.save_resource(
                ResourceType.TEMPLATE,
                template.template_id,
                template_data,
                resource_root_dir=package_root_dir,
            )
        else:
            # 已存在的模板：保持其原有资源根目录不变（由资源层根据 existing_file 自动推断）。
            self.resource_manager.save_resource(
                ResourceType.TEMPLATE,
                template.template_id,
                template_data,
            )

        # 更新当前 PackageView 的内存快照（用于 UI 立即反馈）。
        self.package_index.add_template(template.template_id)
        self._templates_cache = None
    
    def remove_template(self, template_id: str) -> None:
        """移除模板（仅更新当前 PackageView 的内存快照）。

        注意：
        - 目录模式下，模板是否“属于当前项目存档”由其物理文件所在根目录决定；
        - 真正改变归属（从当前项目移出/移动到共享/移动到其它项目）应通过 `PackageIndexManager`
          做文件移动；本方法不做文件操作。
        """
        self.package_index.remove_template(template_id)
        self._templates_cache = None
    
    def add_instance(self, instance: InstanceConfig) -> None:
        """添加实例（新建资源）。

        说明同 `add_template`：新建实例需要明确写入当前项目存档根目录，避免落入默认归档项目。
        """
        instance_data = instance.serialize()

        existing_file = self.resource_manager.list_resource_file_paths(ResourceType.INSTANCE).get(
            str(instance.instance_id)
        )
        if existing_file is None:
            _shared_root_dir, package_root_dir = self._get_shared_and_package_root_dirs()
            if package_root_dir is None:
                raise ValueError("无法解析当前项目存档根目录，无法写入新建实体摆放资源")
            self.resource_manager.save_resource(
                ResourceType.INSTANCE,
                instance.instance_id,
                instance_data,
                resource_root_dir=package_root_dir,
            )
        else:
            self.resource_manager.save_resource(
                ResourceType.INSTANCE,
                instance.instance_id,
                instance_data,
            )

        self.package_index.add_instance(instance.instance_id)
        self._instances_cache = None
    
    def remove_instance(self, instance_id: str) -> None:
        """移除实例（仅更新当前 PackageView 的内存快照）。

        注意：与 `remove_template` 相同，本方法不做文件删除/移动。
        """
        # 不允许删除关卡实体
        if instance_id == self.package_index.level_entity_id:
            raise ValueError("不允许删除关卡实体")
        
        # 从存档索引移除
        self.package_index.remove_instance(instance_id)
        
        # 清除缓存
        self._instances_cache = None
    
    def update_level_entity(self, level_entity: InstanceConfig) -> None:
        """更新关卡实体（保存资源文件并清除缓存）。

        注意：
        - 关卡实体属于当前项目存档；若是首次创建（磁盘上尚无该 instance_id 对应文件），
          需要显式写入到当前项目存档根目录，避免落入默认归档项目。
        """
        level_entity_data = level_entity.serialize()

        existing_file = self.resource_manager.list_resource_file_paths(ResourceType.INSTANCE).get(
            str(level_entity.instance_id)
        )
        if existing_file is None:
            _shared_root_dir, package_root_dir = self._get_shared_and_package_root_dirs()
            if package_root_dir is None:
                raise ValueError("无法解析当前项目存档根目录，无法写入关卡实体资源")
            self.resource_manager.save_resource(
                ResourceType.INSTANCE,
                level_entity.instance_id,
                level_entity_data,
                resource_root_dir=package_root_dir,
            )
        else:
            self.resource_manager.save_resource(
                ResourceType.INSTANCE,
                level_entity.instance_id,
                level_entity_data,
            )

        self._level_entity_cache = None
    
    def serialize(self) -> dict:
        """序列化（用于导出）。

        当前导出采用“索引型”格式：仅导出 `PackageIndex.serialize()` 的结果，不嵌入资源 payload。
        """
        return self.package_index.serialize()

