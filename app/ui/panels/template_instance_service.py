"""Service helpers for TemplateInstancePanel."""

from __future__ import annotations

from typing import Any, Optional, Union

from engine.graph.models.package_model import (
    ComponentConfig,
    InstanceConfig,
    TemplateConfig,
    VariableConfig,
)

ConfigType = Union[TemplateConfig, InstanceConfig]


class TemplateInstanceService:
    """集中处理模板/实例面板的保存逻辑，便于复用与测试。"""

    _COMPONENT_COLLECTIONS = {
        "template": "default_components",
        "instance": "additional_components",
        "level_entity": "additional_components",
    }
    _VARIABLE_COLLECTIONS = {
        "template": "default_variables",
        "instance": "override_variables",
        "level_entity": "override_variables",
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

    # ------------------------------------------------------------------ Variables
    def add_variable(
        self,
        target: ConfigType,
        object_type: str,
        variable: VariableConfig,
    ) -> bool:
        if not target or not variable:
            return False
        collection = self._ensure_collection(target, object_type, self._VARIABLE_COLLECTIONS, create=True)
        if collection is None:
            return False
        for index, existing in enumerate(collection):
            if existing.name == variable.name:
                collection[index] = variable
                return True
        collection.append(variable)
        return True

    def remove_variable(
        self,
        target: ConfigType,
        object_type: str,
        variable: Optional[VariableConfig],
        source: str,
    ) -> bool:
        if not target or variable is None:
            return False
        collection = self._ensure_collection(target, object_type, self._VARIABLE_COLLECTIONS)
        if collection is None:
            return False
        if object_type != "template":
            if source == "inherited":
                return False
            if source == "overridden":
                updated = [v for v in collection if v.name != variable.name]
                if len(updated) != len(collection):
                    setattr(target, self._VARIABLE_COLLECTIONS[object_type], updated)
                    return True
                return False
        if variable in collection:
            collection.remove(variable)
            return True
        return False

    def update_variable(
        self,
        target: ConfigType,
        object_type: str,
        original_variable: VariableConfig,
        updated_variable: VariableConfig,
        source: str,
    ) -> bool:
        """在保持变量顺序稳定的前提下更新变量配置。

        设计约定：
        - 模板上下文：直接在 default_variables 中原位替换记录，避免因“删后再追加”导致序号变化。
        - 实例/关卡实体上下文：
          - 继承变量（source == "inherited"）：在 override_variables 中创建或更新覆写记录，不改动模板定义；
          - 覆写/额外变量：在 override_variables 中按对象身份查找并原位替换，同样不打乱顺序。
        """
        if not target or not original_variable or not updated_variable:
            return False
        collection = self._ensure_collection(
            target,
            object_type,
            self._VARIABLE_COLLECTIONS,
            create=True,
        )
        if collection is None:
            return False

        # 实例或关卡实体中编辑“继承变量”：在覆写列表中创建/更新记录，保持模板定义不变。
        if object_type != "template" and source == "inherited":
            for index, existing in enumerate(collection):
                if existing.name == updated_variable.name:
                    collection[index] = updated_variable
                    return True
            collection.append(updated_variable)
            return True

        # 其余来源：优先按对象身份匹配，在原位置替换记录，保证列表顺序稳定。
        for index, existing in enumerate(collection):
            if existing is original_variable:
                collection[index] = updated_variable
                return True

        # 回退逻辑：在无法通过对象身份匹配时退回到按旧名称匹配，兼容少量迁移场景。
        for index, existing in enumerate(collection):
            if existing.name == original_variable.name:
                collection[index] = updated_variable
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