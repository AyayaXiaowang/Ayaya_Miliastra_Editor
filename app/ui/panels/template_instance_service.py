"""Service helpers for TemplateInstancePanel."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Optional, Union

from engine.graph.models.package_model import (
    ComponentConfig,
    InstanceConfig,
    TemplateConfig,
)
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.utils.resource_library_layout import get_packages_root_dir

ConfigType = Union[TemplateConfig, InstanceConfig]


class TemplateInstanceService:
    """集中处理模板/实例面板的保存逻辑，便于复用与测试。"""

    _COMPONENT_COLLECTIONS = {
        "template": "default_components",
        "instance": "additional_components",
        "level_entity": "additional_components",
    }
    _GRAPH_COLLECTIONS = {
        "template": "default_graphs",
        "instance": "additional_graphs",
        "level_entity": "additional_graphs",
    }

    def apply_basic_info(self, target: Any, name: str, description: str) -> None:
        if not target:
            return
        target.name = name
        if hasattr(target, "description"):
            target.description = description

    def apply_drop_metadata(self, target: Any, metadata: Optional[dict]) -> None:
        """应用掉落物相关的元数据（例如 template_category / drop_model_id）。

        仅在 metadata 非空时更新，且以增量方式写回，避免覆盖其他字段。
        """
        if not target or not metadata:
            return
        existing = getattr(target, "metadata", None)
        if not isinstance(existing, dict):
            existing = {}
        for key, value in metadata.items():
            if value is None:
                existing.pop(key, None)
            else:
                existing[key] = value
        setattr(target, "metadata", existing)

    def apply_guid(self, target: Any, guid_text: Optional[str]) -> None:
        """应用基础信息中的 GUID 字段，统一写入 target.metadata['guid']。

        - guid_text 为空或仅包含空白时：从 metadata 中移除 guid 键；
        - guid_text 为非空字符串时：以原样字符串形式写入，保持对大整数/前导零的兼容。
        """
        if not target:
            return
        existing = getattr(target, "metadata", None)
        if not isinstance(existing, dict):
            existing = {}
        previous_guid = existing.get("guid")
        text = guid_text.strip() if guid_text is not None else ""
        if text:
            existing["guid"] = text
        else:
            existing.pop("guid", None)
        setattr(target, "metadata", existing)

        # 调试输出：记录 GUID 写入链路，便于排查“界面修改后是否真正写入模型”的问题。
        target_kind = "unknown"
        target_identifier = ""
        if hasattr(target, "template_id"):
            target_kind = "template"
            target_identifier = getattr(target, "template_id", "")
        elif hasattr(target, "instance_id"):
            target_kind = "instance"
            target_identifier = getattr(target, "instance_id", "")
        current_guid = existing.get("guid")
        print(
            "[GUID-APPLY] "
            f"kind={target_kind}, id={target_identifier!r}, "
            f"previous={previous_guid!r}, current={current_guid!r}"
        )

    # ---------------------------------------------------------------- Decorations
    @staticmethod
    def _sanitize_id_token(text: str) -> str:
        """将任意文本收敛为可读的 ID token（仅用于拼接新资源 ID）。"""
        raw = str(text or "").strip()
        if not raw:
            return "unknown"
        normalized = raw.replace("/", "_").replace("\\", "_").replace(" ", "_")
        normalized = re.sub(r"[^0-9a-zA-Z_]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized or "unknown"

    def split_decorations_to_templates(
        self,
        *,
        source: ConfigType,
        object_type: str,
        package: PackageView,
        resource_manager: ResourceManager,
        carrier_model_name: str = "空模型",
    ) -> list[str]:
        """将 `source.metadata.common_inspector.model.decorations` 打散为多个元件模板。

        约定：
        - 每个装饰物生成一个“空模型载体模板”，并把该装饰物作为唯一 decorations 写入
          `metadata.common_inspector.model.decorations`；
        - 新模板立即写盘到当前 package 的资源根目录（`assets/资源库/项目存档/<package_id>/元件库/`）；
        - 返回新建 template_id 列表（按 decorations 原始顺序）。
        """
        if source is None:
            return []
        if not isinstance(package, PackageView):
            raise TypeError(f"package 必须为 PackageView（got: {type(package).__name__}）")
        if not isinstance(resource_manager, ResourceManager):
            raise TypeError(
                f"resource_manager 必须为 ResourceManager（got: {type(resource_manager).__name__}）"
            )

        metadata = getattr(source, "metadata", None)
        if not isinstance(metadata, dict):
            return []
        inspector = metadata.get("common_inspector")
        if not isinstance(inspector, dict):
            return []
        model = inspector.get("model")
        if not isinstance(model, dict):
            return []

        raw_decorations = model.get("decorations")
        if not isinstance(raw_decorations, list):
            return []

        decorations: list[dict[str, object]] = []
        for entry in raw_decorations:
            if isinstance(entry, dict):
                decorations.append(entry)
            elif isinstance(entry, str) and entry.strip():
                # 兼容旧的字符串列表：将字符串视为 displayName，生成最小 decoration 形态
                decorations.append(
                    {
                        "instanceId": f"split_{len(decorations) + 1}",
                        "displayName": entry.strip(),
                        "isVisible": True,
                        "assetId": 0,
                        "parentId": "GI_RootNode",
                        "transform": {
                            "pos": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "rot": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                            "isLocked": False,
                        },
                        "physics": {
                            "enableCollision": True,
                            "isClimbable": True,
                            "showPreview": False,
                        },
                    }
                )

        if not decorations:
            return []

        resource_library_dir = getattr(resource_manager, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("ResourceManager.resource_library_dir 缺失，无法解析写入目录")

        package_id_text = str(getattr(package, "package_id", "") or "").strip()
        if not package_id_text:
            raise ValueError("package.package_id 为空，无法写入项目存档目录")

        package_root_dir = (get_packages_root_dir(resource_library_dir) / package_id_text).resolve()
        if not package_root_dir.exists() or not package_root_dir.is_dir():
            raise FileNotFoundError(f"未找到项目存档目录：{package_root_dir}")

        existing_template_ids = set(resource_manager.list_resources(ResourceType.TEMPLATE))

        source_identifier = ""
        if hasattr(source, "template_id"):
            source_identifier = str(getattr(source, "template_id") or "")
        elif hasattr(source, "instance_id"):
            source_identifier = str(getattr(source, "instance_id") or "")
        source_identifier = source_identifier.strip()
        if not source_identifier:
            source_identifier = "source"

        source_name = str(getattr(source, "name", "") or "").strip() or source_identifier

        source_ugc = metadata.get("ugc")
        ugc_base: dict[str, object] = dict(source_ugc) if isinstance(source_ugc, dict) else {}

        base_common_inspector = copy.deepcopy(inspector)
        created_template_ids: list[str] = []

        filename_bucket = resource_manager.id_to_filename_cache.setdefault(ResourceType.TEMPLATE, {})

        for index, deco in enumerate(decorations):
            raw_unit_key = str(deco.get("instanceId") or "").strip() or str(index + 1)
            source_token = self._sanitize_id_token(source_identifier)
            unit_token = self._sanitize_id_token(raw_unit_key)
            base_id = f"template_split_deco_{source_token}_{unit_token}"

            template_id = base_id
            bump = 2
            while template_id in existing_template_ids:
                template_id = f"{base_id}_{bump}"
                bump += 1
            existing_template_ids.add(template_id)
            created_template_ids.append(template_id)

            display_name = str(deco.get("displayName") or "").strip() or f"装饰物_{index + 1}"
            template_name = display_name

            ugc_meta = dict(ugc_base)
            ugc_meta["source"] = "split_decorations_to_templates"
            ugc_meta["split_from_object_type"] = str(object_type or "").strip() or "unknown"
            ugc_meta["split_from_id"] = source_identifier
            ugc_meta["split_from_name"] = source_name
            ugc_meta["split_from_decoration_instanceId"] = str(deco.get("instanceId") or "")
            ugc_meta["split_from_decoration_displayName"] = str(deco.get("displayName") or "")

            inspector_copy = copy.deepcopy(base_common_inspector)
            model_copy = inspector_copy.get("model")
            if not isinstance(model_copy, dict):
                model_copy = {}
                inspector_copy["model"] = model_copy
            model_copy["decorations"] = [copy.deepcopy(deco)]

            template_payload: dict[str, object] = {
                "template_id": str(template_id),
                "name": str(template_name),
                "entity_type": "物件",
                "description": f"由 {source_name} 装饰物打散生成",
                "default_graphs": [],
                "default_variables": [],
                "default_components": [],
                "entity_config": {
                    "render": {"model_name": str(carrier_model_name), "visible": True},
                },
                "metadata": {
                    "object_model_name": str(carrier_model_name),
                    "ugc": ugc_meta,
                    "common_inspector": inspector_copy,
                },
                "graph_variable_overrides": {},
            }

            safe_stem = resource_manager.sanitize_filename(str(template_name)) or "装饰物"
            filename_bucket[str(template_id)] = f"{safe_stem}_{template_id}"

            saved = resource_manager.save_resource(
                ResourceType.TEMPLATE,
                str(template_id),
                dict(template_payload),
                resource_root_dir=package_root_dir,
            )
            if not saved:
                raise RuntimeError(f"保存模板失败：template_id={template_id!r}")

        # 同步到 PackageView 的资源列表（目录即存档：语义等价于“写入了该目录”）
        resources = getattr(getattr(package, "package_index", None), "resources", None)
        template_ids_list = getattr(resources, "templates", None) if resources is not None else None
        if isinstance(template_ids_list, list):
            for template_id in created_template_ids:
                if template_id not in template_ids_list:
                    template_ids_list.append(template_id)
            template_ids_list.sort(key=lambda text: str(text).casefold())
            package.clear_cache()

        return created_template_ids

    # ------------------------------------------------------------------ Components
    def add_component(
        self,
        target: ConfigType,
        object_type: str,
        component: ComponentConfig,
    ) -> bool:
        if not target or not component:
            return False
        collection = self._ensure_collection(target, object_type, self._COMPONENT_COLLECTIONS)
        if collection is None:
            return False
        for existing in collection:
            if existing.component_type == component.component_type:
                existing.settings = dict(component.settings)
                existing.description = component.description
                return True
        collection.append(component)
        return True

    def remove_component(
        self,
        target: ConfigType,
        object_type: str,
        component: Optional[ComponentConfig],
        source: str,
    ) -> bool:
        if not target or component is None:
            return False
        collection = self._ensure_collection(target, object_type, self._COMPONENT_COLLECTIONS)
        if collection is None:
            return False
        if object_type != "template" and source == "inherited":
            return False
        if component in collection:
            collection.remove(component)
            return True
        return False

    # ------------------------------------------------------------------ Graphs
    def add_graph(self, target: ConfigType, object_type: str, graph_id: str) -> bool:
        graphs = self._ensure_collection(target, object_type, self._GRAPH_COLLECTIONS, create=True)
        if graphs is None or graph_id in graphs:
            return False
        graphs.append(graph_id)
        return True

    def remove_graph(
        self,
        target: ConfigType,
        object_type: str,
        graph_id: str,
        source: str,
    ) -> bool:
        if source == "inherited":
            return False
        graphs = self._ensure_collection(target, object_type, self._GRAPH_COLLECTIONS)
        if graphs is None or graph_id not in graphs:
            return False
        graphs.remove(graph_id)
        return True

    def set_graph_variable_override(
        self,
        target: ConfigType,
        graph_id: str,
        var_name: str,
        override_value: object,
    ) -> bool:
        if not target:
            return False
        overrides = getattr(target, "graph_variable_overrides", None)
        if overrides is None:
            overrides = {}
            setattr(target, "graph_variable_overrides", overrides)
        graph_overrides = overrides.setdefault(graph_id, {})

        should_clear = False
        if override_value is None:
            should_clear = True
        elif isinstance(override_value, str) and not override_value.strip():
            should_clear = True

        if not should_clear:
            previous = graph_overrides.get(var_name)
            graph_overrides[var_name] = override_value
            return previous != override_value

        if var_name in graph_overrides:
            graph_overrides.pop(var_name, None)
            if not graph_overrides:
                overrides.pop(graph_id, None)
            return True
        return False

    # ------------------------------------------------------------------ Helpers
    def _ensure_collection(
        self,
        target: ConfigType,
        object_type: str,
        mapping: dict[str, str],
        *,
        create: bool = False,
    ):
        if not target:
            return None
        attr = mapping.get(object_type)
        if not attr:
            return None
        collection = getattr(target, attr, None)
        if collection is None and create:
            collection = []
            setattr(target, attr, collection)
        return collection
        return collection