"""资源容器写回服务（模板/实例/关卡实体）。"""

from __future__ import annotations

from typing import Callable

from engine.resources.resource_manager import ResourceManager, ResourceType


class ResourceContainerSaveService:
    def __init__(self, resource_manager: ResourceManager):
        self._resource_manager = resource_manager

    def save_container(self, container: object, object_type: str, *, verbose: bool) -> None:
        """统一保存资源容器（模板、实例或关卡实体）。"""
        if not container:
            return

        if object_type == "template":
            if hasattr(container, "template_id"):
                payload = container.serialize()  # type: ignore[attr-defined]
                metadata = payload.get("metadata", {}) or {}
                guid_value = None
                if isinstance(metadata, dict):
                    guid_value = metadata.get("guid")
                self._resource_manager.save_resource(
                    ResourceType.TEMPLATE,
                    container.template_id,  # type: ignore[attr-defined]
                    payload,
                )
                print(
                    "[RESOURCE-SAVE] 模板已保存："
                    f"name={getattr(container, 'name', '')!r}, "
                    f"id={container.template_id!r}, guid={guid_value!r}"  # type: ignore[attr-defined]
                )
                if verbose:
                    print(
                        f"已保存模板：{getattr(container, 'name', '')} ({container.template_id})"  # type: ignore[attr-defined]
                    )
            return

        if object_type in ("instance", "level_entity"):
            if hasattr(container, "instance_id"):
                payload = container.serialize()  # type: ignore[attr-defined]
                metadata = payload.get("metadata", {}) or {}
                guid_value = None
                if isinstance(metadata, dict):
                    guid_value = metadata.get("guid")
                self._resource_manager.save_resource(
                    ResourceType.INSTANCE,
                    container.instance_id,  # type: ignore[attr-defined]
                    payload,
                )
                print(
                    "[RESOURCE-SAVE] 实例已保存："
                    f"name={getattr(container, 'name', '')!r}, "
                    f"id={container.instance_id!r}, guid={guid_value!r}, "  # type: ignore[attr-defined]
                    f"is_level_entity={object_type == 'level_entity'}"
                )
                if verbose:
                    print(
                        f"已保存实例：{getattr(container, 'name', '')} ({container.instance_id})"  # type: ignore[attr-defined]
                    )

    def save_resources_for_ids(
        self,
        package: object,
        template_ids: set[str],
        instance_ids: set[str],
        save_level_entity: bool,
        *,
        verbose: bool,
    ) -> bool:
        """按 ID 集合保存模板/实例/关卡实体。"""
        saved_any = False

        if template_ids:
            template_getter = getattr(package, "get_template", None)
            if callable(template_getter):
                for template_id in template_ids:
                    template_obj = template_getter(template_id)
                    if template_obj is None:
                        continue
                    self.save_container(template_obj, "template", verbose=verbose)
                    saved_any = True

        if instance_ids:
            instance_getter = getattr(package, "get_instance", None)
            if callable(instance_getter):
                for instance_id in instance_ids:
                    instance_obj = instance_getter(instance_id)
                    if instance_obj is None:
                        continue
                    self.save_container(instance_obj, "instance", verbose=verbose)
                    saved_any = True

        if save_level_entity:
            level_entity_obj = getattr(package, "level_entity", None)
            if level_entity_obj is not None:
                self.save_container(level_entity_obj, "level_entity", verbose=verbose)
                saved_any = True

        return saved_any

    def save_current_property_context(
        self,
        get_current_graph_container: Callable[[], object | None] | None,
        get_property_panel_object_type: Callable[[], str | None] | None,
        *,
        verbose: bool,
    ) -> bool:
        """保存当前属性上下文对应的资源（供全量保存或特殊视图回退使用）。"""
        if get_current_graph_container is None or get_property_panel_object_type is None:
            return False

        current_graph_container = get_current_graph_container()
        object_type = get_property_panel_object_type()
        if current_graph_container is None or not object_type:
            return False

        self.save_container(current_graph_container, str(object_type), verbose=verbose)
        return True


