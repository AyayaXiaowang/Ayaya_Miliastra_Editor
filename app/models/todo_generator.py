"""任务生成器 - 负责组装分类、节点图入口，并将图内细节委托给 GraphTaskCoordinator。"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, TYPE_CHECKING

from engine.configs.rules import COMPONENT_DEFINITIONS
from engine.graph.models import InstanceConfig, TemplateConfig
from engine.resources.resource_manager import ResourceManager

from app.models import TodoItem
from app.models.package_loader import PackageLoader
from app.models.resource_task_configs import (
    COMBAT_RESOURCE_CONFIGS,
    MANAGEMENT_RESOURCE_CONFIGS,
    ResourceTaskConfig,
)
from app.models.todo_node_type_helper import NodeTypeHelper
from app.models.todo_pipeline.coordinator import GraphTaskCoordinator

if TYPE_CHECKING:
    from engine.resources.package_interfaces import PackageLike


_TYPE_HELPER_CACHE: Dict[str, NodeTypeHelper] = {}
_PACKAGE_LOADER_CACHE: Dict[Tuple[int, int], PackageLoader] = {}


class TodoGenerator:
    """任务生成器（仅 orchestrator，不关心 UI）"""

    def __init__(self, package: "PackageLike", resource_manager: Optional[ResourceManager] = None):
        self.package = package
        self.resource_manager = resource_manager
        self.todos: List[TodoItem] = []
        self.todo_map: Dict[str, TodoItem] = {}

        self.type_helper = _get_or_create_type_helper(resource_manager)
        self.package_loader = PackageLoader(package, resource_manager)
        self.graph_coordinator = GraphTaskCoordinator(
            type_helper=self.type_helper,
            resource_manager=resource_manager,
            add_todo=self._add_todo,
            todo_map=self.todo_map,
            package_loader=self.package_loader,
        )
        self._template_builder = _TemplateCategoryBuilder(
            add_todo=self._add_todo,
            graph_coordinator=self.graph_coordinator,
        )
        self._instance_builder = _InstanceCategoryBuilder(
            add_todo=self._add_todo,
            graph_coordinator=self.graph_coordinator,
        )
        self._resource_builder = _ResourceCategoryBuilder(add_todo=self._add_todo)
        self._standalone_builder = _StandaloneGraphCategoryBuilder(
            add_todo=self._add_todo,
            graph_coordinator=self.graph_coordinator,
            package_loader=self.package_loader,
            resource_manager=resource_manager,
        )

    def generate_todos(self) -> List[TodoItem]:
        """构造根节点及各类分类任务。"""
        self.todos.clear()
        self.todo_map.clear()
        self.package_loader.reset_cache()

        root = self._create_root_todo()
        categories: List[str] = []

        template_category = self._template_builder.build(package=self.package, parent_id=root.todo_id)
        if template_category:
            categories.append(template_category)

        instance_category = self._instance_builder.build(package=self.package, parent_id=root.todo_id)
        if instance_category:
            categories.append(instance_category)

        resource_categories = [
            {
                "category_id": "category:combat",
                "title": "战斗预设配置",
                "description": "配置战斗相关预设",
                "owner": self.package.combat_presets,
                "configs": COMBAT_RESOURCE_CONFIGS,
                "default_task_type": "combat",
            },
            {
                "category_id": "category:management",
                "title": "管理数据配置",
                "description": "配置管理数据",
                "owner": self.package.management,
                "configs": MANAGEMENT_RESOURCE_CONFIGS,
                "default_task_type": "management",
            },
        ]
        for cat in resource_categories:
            built = self._resource_builder.build(
                parent_id=root.todo_id,
                category_id=cat["category_id"],
                title=cat["title"],
                description=cat["description"],
                resource_owner=cat["owner"],
                resource_configs=cat["configs"],
                default_task_type=cat["default_task_type"],
            )
            if built:
                categories.append(built)

        standalone_cat = self._standalone_builder.build(
            parent_id=root.todo_id,
            used_graph_ids=self._collect_used_graph_ids(),
        )
        if standalone_cat:
            categories.append(standalone_cat)

        root.children = categories
        return self.todos

    def _create_root_todo(self) -> TodoItem:
        root = TodoItem(
            todo_id="root",
            title=f"存档：{self.package.name}",
            description=self.package.description or "完成存档的所有配置",
            level=0,
            parent_id=None,
            children=[],
            task_type="category",
            target_id="",
            detail_info={
                "type": "root",
                "package_name": self.package.name,
                "package_id": self.package.package_id,
            },
        )
        self._add_todo(root)
        return root

    def _add_todo(self, todo: TodoItem) -> None:
        self.todos.append(todo)
        self.todo_map[todo.todo_id] = todo

    def _collect_used_graph_ids(self) -> Set[str]:
        used: Set[str] = set()
        for template in self.package.templates.values():
            used.update(filter(None, template.default_graphs))
        for instance in self.package.instances.values():
            used.update(filter(None, instance.additional_graphs))
        return used

    @staticmethod
    def expand_graph_tasks(
        *,
        package: "PackageLike",
        resource_manager: ResourceManager,
        parent_id: str,
        graph_id: str,
        graph_name: str,
        graph_data: Dict[str, Any],
        preview_template_id: str = "",
        suppress_auto_jump: bool = False,
        graph_root: Optional[TodoItem] = None,
        attach_graph_root: bool = True,
    ) -> List[TodoItem]:
        """供 UI 懒加载时使用的静态入口，避免实例化完整 TodoGenerator。"""

        todos: List[TodoItem] = []
        todo_map: Dict[str, TodoItem] = {}

        def _add(todo: TodoItem) -> None:
            todos.append(todo)
            todo_map[todo.todo_id] = todo

        if graph_root is not None:
            todo_map[graph_root.todo_id] = graph_root

        coordinator = GraphTaskCoordinator(
            type_helper=_get_or_create_type_helper(resource_manager),
            resource_manager=resource_manager,
            add_todo=_add,
            todo_map=todo_map,
            package_loader=_get_or_create_package_loader(package, resource_manager),
        )
        coordinator.generate_graph_tasks(
            parent_id=parent_id,
            graph_id=graph_id,
            graph_name=graph_name,
            graph_data=graph_data,
            preview_template_id=preview_template_id,
            suppress_auto_jump=suppress_auto_jump,
            graph_root=graph_root,
            attach_graph_root=attach_graph_root,
        )
        return todos


class _TemplateCategoryBuilder:
    def __init__(
        self,
        *,
        add_todo: Callable[[TodoItem], None],
        graph_coordinator: GraphTaskCoordinator,
    ) -> None:
        self._add_todo = add_todo
        self._graph_coordinator = graph_coordinator

    def build(self, *, package: "PackageLike", parent_id: str) -> str:
        templates = sorted(package.templates.values(), key=self._template_sort_key)
        if not templates:
            return ""
        cat_id = "category:templates"
        category = TodoItem(
            todo_id=cat_id,
            title="元件库实施",
            description=f"创建和配置 {len(templates)} 个实体模板",
            level=1,
            parent_id=parent_id,
            children=[],
            task_type="category",
            target_id="",
            detail_info={"type": "category", "category": "templates", "count": len(templates)},
        )
        self._add_todo(category)
        for template in templates:
            category.children.append(self._build_template_tasks(template=template, parent_id=cat_id))
        return cat_id

    def _build_template_tasks(self, template: TemplateConfig, *, parent_id: str) -> str:
        todo_id = f"template:{template.template_id}"
        template_todo = TodoItem(
            todo_id=todo_id,
            title=f"[{template.entity_type}] {template.name}",
            description=template.description or f"配置模板：{template.name}",
            level=2,
            parent_id=parent_id,
            children=[],
            task_type="template",
            target_id=template.template_id,
            detail_info={
                "type": "template",
                "template_id": template.template_id,
                "name": template.name,
                "entity_type": template.entity_type,
                "description": template.description,
            },
        )
        self._add_todo(template_todo)

        child_ids: List[str] = []
        if template.entity_config:
            child_ids.append(self._create_basic_section(template, todo_id))
        if template.default_variables:
            child_ids.append(self._create_variables_section(template, todo_id))
        if template.default_components:
            child_ids.append(self._create_components_section(template, todo_id))

        graph_child_ids = self._graph_coordinator.create_graph_root_tasks(
            parent_id=todo_id,
            graph_ids=template.default_graphs,
            target_id=template.template_id,
            template_ctx_id=template.template_id,
            preview_template_id=template.template_id,
        )
        child_ids.extend(graph_child_ids)
        template_todo.children = child_ids
        return todo_id

    def _create_basic_section(self, template: TemplateConfig, parent_id: str) -> str:
        detail_info = {
            "type": "template_basic",
            "template_id": template.template_id,
            "config": template.entity_config,
        }
        return self._create_template_section(
            template=template,
            parent_id=parent_id,
            suffix="basic",
            title="设置基础属性",
            description="配置实体的基础属性和特殊设置",
            detail_info=detail_info,
        )

    def _create_variables_section(self, template: TemplateConfig, parent_id: str) -> str:
        variable_rows = [
            {
                "name": variable.name,
                "variable_type": variable.variable_type,
                "default_value": variable.default_value,
                "description": variable.description,
            }
            for variable in template.default_variables
        ]
        detail_info = {
            "type": "template_variables_table",
            "template_id": template.template_id,
            "variables": variable_rows,
        }
        return self._create_template_section(
            template=template,
            parent_id=parent_id,
            suffix="variables",
            title=f"配置 {len(template.default_variables)} 个自定义变量",
            description="为模板添加自定义变量",
            detail_info=detail_info,
        )

    def _create_components_section(self, template: TemplateConfig, parent_id: str) -> str:
        component_rows = []
        for component in template.default_components:
            component_type = component.component_type
            definition = COMPONENT_DEFINITIONS.get(component_type, {})
            description_text = str(definition.get("description") or component.description or "").strip()
            component_rows.append(
                {
                    "component_type": component_type,
                    "description": description_text,
                    "settings": component.settings,
                }
            )
        detail_info = {
            "type": "template_components_table",
            "template_id": template.template_id,
            "components": component_rows,
        }
        return self._create_template_section(
            template=template,
            parent_id=parent_id,
            suffix="components",
            title=f"添加 {len(template.default_components)} 个组件",
            description="为模板添加所需组件",
            detail_info=detail_info,
        )

    def _create_template_section(
        self,
        *,
        template: TemplateConfig,
        parent_id: str,
        suffix: str,
        title: str,
        description: str,
        detail_info: Dict[str, Any],
    ) -> str:
        todo_id = f"{parent_id}:{suffix}"
        todo = TodoItem(
            todo_id=todo_id,
            title=title,
            description=description,
            level=3,
            parent_id=parent_id,
            children=[],
            task_type="template",
            target_id=template.template_id,
            detail_info=detail_info,
        )
        self._add_todo(todo)
        return todo_id

    def _template_sort_key(self, template: TemplateConfig) -> Tuple[str, ...]:
        return _string_sort_key(template.name, template.entity_type, template.template_id)


class _InstanceCategoryBuilder:
    def __init__(
        self,
        *,
        add_todo: Callable[[TodoItem], None],
        graph_coordinator: GraphTaskCoordinator,
    ) -> None:
        self._add_todo = add_todo
        self._graph_coordinator = graph_coordinator

    def build(self, *, package: "PackageLike", parent_id: str) -> str:
        instances = sorted(package.instances.values(), key=self._instance_sort_key)
        if not instances:
            return ""
        cat_id = "category:instances"
        category = TodoItem(
            todo_id=cat_id,
            title="实体摆放实施",
            description=f"在场景中摆放 {len(instances)} 个实例",
            level=1,
            parent_id=parent_id,
            children=[],
            task_type="category",
            target_id="",
            detail_info={"type": "category", "category": "instances", "count": len(instances)},
        )
        self._add_todo(category)
        for instance in instances:
            category.children.append(self._build_instance_tasks(package=package, instance=instance, parent_id=cat_id))
        return cat_id

    def _build_instance_tasks(self, *, package: "PackageLike", instance: InstanceConfig, parent_id: str) -> str:
        todo_id = f"instance:{instance.instance_id}"
        template = package.get_template(instance.template_id)
        template_name = template.name if template else "未知模板"
        instance_todo = TodoItem(
            todo_id=todo_id,
            title=instance.name,
            description=f"基于模板：{template_name}",
            level=2,
            parent_id=parent_id,
            children=[],
            task_type="instance",
            target_id=instance.instance_id,
            detail_info={
                "type": "instance",
                "instance_id": instance.instance_id,
                "name": instance.name,
                "template_id": instance.template_id,
                "template_name": template_name,
            },
        )
        self._add_todo(instance_todo)

        properties_id = f"{todo_id}:properties"
        override_variables = [
            {"name": variable.name, "value": variable.default_value} for variable in instance.override_variables
        ]
        properties_todo = TodoItem(
            todo_id=properties_id,
            title="配置实例属性",
            description="设置位置、旋转和变量覆盖",
            level=3,
            parent_id=todo_id,
            children=[],
            task_type="instance",
            target_id=instance.instance_id,
            detail_info={
                "type": "instance_properties_table",
                "instance_id": instance.instance_id,
                "position": instance.position,
                "rotation": instance.rotation,
                "override_variables": override_variables,
            },
        )
        self._add_todo(properties_todo)

        graph_children = self._graph_coordinator.create_graph_root_tasks(
            parent_id=todo_id,
            graph_ids=instance.additional_graphs,
            target_id=instance.instance_id,
            instance_ctx_id=instance.instance_id,
        )
        instance_todo.children = [properties_id] + graph_children
        return todo_id

    def _instance_sort_key(self, instance: InstanceConfig) -> Tuple[str, ...]:
        return _string_sort_key(instance.name, instance.instance_id)


class _ResourceCategoryBuilder:
    def __init__(self, *, add_todo: Callable[[TodoItem], None]) -> None:
        self._add_todo = add_todo

    def build(
        self,
        *,
        parent_id: str,
        category_id: str,
        title: str,
        description: str,
        resource_owner: Any,
        resource_configs: Sequence[ResourceTaskConfig],
        default_task_type: str,
    ) -> str:
        entries_by_config = self._collect_entries(resource_owner, resource_configs)
        if not entries_by_config:
            return ""

        total_count = sum(len(entries) for _, entries in entries_by_config)
        category = TodoItem(
            todo_id=category_id,
            title=title,
            description=description,
            level=1,
            parent_id=parent_id,
            children=[],
            task_type="category",
            target_id="",
            detail_info={"type": "category", "category": category_id.split(":")[-1], "count": total_count},
        )
        self._add_todo(category)

        for config, entries in entries_by_config:
            for resource_id, resource_data in entries:
                str_id = str(resource_id)
                task_id = f"{config.task_prefix}:{str_id}"
                todo_item = TodoItem(
                    todo_id=task_id,
                    title=config.title_format.format(
                        name=self._resolve_resource_display_name(str_id, resource_data, config)
                    ),
                    description=config.description,
                    level=2,
                    parent_id=category_id,
                    children=[],
                    task_type=config.task_type or default_task_type,
                    target_id=str_id,
                    detail_info=self._build_detail_payload(str_id, resource_data, config),
                )
                self._add_todo(todo_item)
                category.children.append(task_id)
        return category_id

    def _collect_entries(
        self,
        resource_owner: Any,
        resource_configs: Sequence[ResourceTaskConfig],
    ) -> List[Tuple[ResourceTaskConfig, List[Tuple[str, Any]]]]:
        if not resource_owner:
            return []
        collected: List[Tuple[ResourceTaskConfig, List[Tuple[str, Any]]]] = []
        for config in resource_configs:
            source = getattr(resource_owner, config.attribute_name, None)
            normalized = list(self._iter_resource_entries(source, config))
            if not normalized:
                continue
            normalized.sort(key=lambda entry: self._resource_title_key(entry, config))
            collected.append((config, normalized))
        return collected

    def _iter_resource_entries(
        self,
        resource_items: Any,
        config: ResourceTaskConfig,
    ) -> Iterable[Tuple[str, Any]]:
        if not resource_items:
            return
        singleton_id = config.singleton_id or config.attribute_name
        if config.is_singleton:
            yield (str(singleton_id), resource_items)
            return
        if isinstance(resource_items, dict):
            for key in sorted(resource_items.keys(), key=lambda value: str(value).lower()):
                yield (str(key), resource_items[key])
            return
        if isinstance(resource_items, (list, tuple)):
            for index, item in enumerate(resource_items):
                yield (str(index), item)
            return
        if isinstance(resource_items, set):
            for index, item in enumerate(sorted(resource_items, key=lambda value: str(value).lower())):
                yield (str(index), item)
            return
        yield (str(singleton_id), resource_items)

    def _resolve_resource_display_name(
        self,
        resource_id: str,
        resource_data: Any,
        resource_config: ResourceTaskConfig,
    ) -> str:
        candidate_name: Optional[str] = None
        if isinstance(resource_data, dict):
            candidate_name = resource_data.get("name") or resource_data.get("title")
        elif hasattr(resource_data, "name"):
            name_attr = getattr(resource_data, "name")
            if isinstance(name_attr, str):
                candidate_name = name_attr
        elif hasattr(resource_data, "title"):
            title_attr = getattr(resource_data, "title")
            if isinstance(title_attr, str):
                candidate_name = title_attr
        fallback_name = resource_config.default_display_name or resource_id
        return str(candidate_name or fallback_name or resource_id)

    def _build_detail_payload(
        self,
        resource_id: str,
        resource_data: Any,
        resource_config: ResourceTaskConfig,
    ) -> Dict[str, Any]:
        payload = {
            "type": resource_config.detail_type,
            resource_config.id_field: resource_id,
            "data": resource_data,
        }
        if resource_config.guide:
            payload["guide"] = resource_config.guide
        return payload

    def _resource_title_key(self, entry: Tuple[str, Any], config: ResourceTaskConfig) -> Tuple[str, ...]:
        resource_id, resource_data = entry
        display_name = self._resolve_resource_display_name(resource_id, resource_data, config)
        return _string_sort_key(display_name, resource_id)


class _StandaloneGraphCategoryBuilder:
    def __init__(
        self,
        *,
        add_todo: Callable[[TodoItem], None],
        graph_coordinator: GraphTaskCoordinator,
        package_loader: PackageLoader,
        resource_manager: Optional[ResourceManager],
    ) -> None:
        self._add_todo = add_todo
        self._graph_coordinator = graph_coordinator
        self._package_loader = package_loader
        self._resource_manager = resource_manager

    def build(self, *, parent_id: str, used_graph_ids: Set[str]) -> str:
        if not self._resource_manager:
            return ""
        candidate_graphs = self._package_loader.list_standalone_graph_ids(used_graph_ids)
        candidate_graphs = sorted(candidate_graphs)
        if not candidate_graphs:
            return ""

        cat_id = "category:standalone_graphs"
        category = TodoItem(
            todo_id=cat_id,
            title="节点图",
            description=f"项目包含 {len(candidate_graphs)} 个节点图",
            level=1,
            parent_id=parent_id,
            children=[],
            task_type="category",
            target_id="",
            detail_info={"type": "category", "category": "standalone_graphs", "count": len(candidate_graphs)},
        )
        self._add_todo(category)

        preview_instance_id = self._package_loader.get_preview_instance_id()
        for graph_id in candidate_graphs:
            category.children.extend(
                self._graph_coordinator.create_graph_root_tasks(
                    parent_id=cat_id,
                    graph_ids=[graph_id],
                    target_id=graph_id,
                    instance_ctx_id=preview_instance_id or "",
                )
            )
        return cat_id


def _string_sort_key(*values: Optional[str]) -> Tuple[str, ...]:
    normalized: List[str] = []
    for value in values:
        normalized.append((value or "").lower())
    return tuple(normalized)


def _get_or_create_type_helper(resource_manager: Optional[ResourceManager]) -> NodeTypeHelper:
    workspace_path = getattr(resource_manager, "workspace_path", None) if resource_manager else None
    key = str(workspace_path or "__none__")
    cached = _TYPE_HELPER_CACHE.get(key)
    if cached is None:
        cached = NodeTypeHelper(workspace_path)
        _TYPE_HELPER_CACHE[key] = cached
    return cached


def _get_or_create_package_loader(package: "PackageLike", resource_manager: ResourceManager) -> PackageLoader:
    package_id = getattr(package, "package_id", "") or str(id(package))
    workspace_key = getattr(resource_manager, "workspace_path", None)
    cache_key = (package_id, str(workspace_key or "__none__"))
    cached = _PACKAGE_LOADER_CACHE.get(cache_key)
    if cached is None:
        cached = PackageLoader(package, resource_manager)
        _PACKAGE_LOADER_CACHE[cache_key] = cached
    return cached
