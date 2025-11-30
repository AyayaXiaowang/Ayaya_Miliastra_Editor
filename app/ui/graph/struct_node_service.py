from __future__ import annotations

"""结构体节点适配服务

本模块位于图编辑 UI 与结构体定义系统之间，集中负责：
- 基于 ResourceManager 中的结构体定义，为“拆分结构体 / 拼装结构体 / 修改结构体”节点构造带精确端口类型的 NodeDef 代理；
- 在图中为结构体节点绑定 struct_id，并记录选中的字段列表；
- 根据信息为节点动态补充分裂/构造/修改所需的输入/输出端口。

GraphScene 只负责：
- 提供 `model` / `node_items` / `signal_edit_context` 这些上下文（其中包含 `get_current_package`）；
- 在适配服务完成模型与端口更新后刷新 UI。
"""

from typing import Dict, List, Optional, TYPE_CHECKING, Sequence, Mapping, Tuple

from PyQt6 import QtWidgets

from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.graph.common import (
    STRUCT_NODE_TITLES,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_SPLIT_STATIC_INPUTS,
    STRUCT_SPLIT_STATIC_OUTPUTS,
    STRUCT_BUILD_STATIC_INPUTS,
    STRUCT_BUILD_STATIC_OUTPUTS,
    STRUCT_MODIFY_STATIC_INPUTS,
    STRUCT_MODIFY_STATIC_OUTPUTS,
)
from engine.resources.definition_schema_view import (
    get_default_definition_schema_view,
)
from ui.dialogs.struct_definition_types import param_type_to_canonical
from ui.dialogs.struct_binding_dialog import StructBindingDialog


if TYPE_CHECKING:
    from ui.graph.graph_scene import GraphScene


# ---------------------------------------------------------------------------
# 公共工具：获取当前包及其结构体定义
# ---------------------------------------------------------------------------


def _get_current_package(scene: "GraphScene"):
    """通过编辑上下文获取当前 PackageView。

    约定 `scene.signal_edit_context` 字段：
    - get_current_package: Callable[[], PackageView | None]
    """
    context = getattr(scene, "signal_edit_context", {}) or {}
    get_package = context.get("get_current_package")
    if not callable(get_package):
        return None
    package = get_package()
    return package


def get_current_package_structs(scene: "GraphScene") -> Optional[Dict[str, dict]]:
    """基于代码级结构体定义为当前场景提供可用结构体列表。

    返回 {struct_id: payload}，payload 为结构体定义的原始字典载荷，
    结构与早期 STRUCT_DEFINITION JSON 资源保持一致。
    """
    package = _get_current_package(scene)
    if package is None:
        return None

    schema_view = get_default_definition_schema_view()
    all_structs = schema_view.get_all_struct_definitions()

    structs: Dict[str, dict] = {}
    for struct_id, data in all_structs.items():
        if not isinstance(data, dict):
            continue
        type_value = data.get("type")
        if isinstance(type_value, str) and type_value != "Struct":
            continue
        structs[str(struct_id)] = dict(data)
    return structs


def _extract_struct_fields(struct_data: Mapping[str, object]) -> List[Tuple[str, str]]:
    """从结构体定义 JSON 中提取字段列表。

    返回 [(字段名, 规范中文类型名)]。
    """
    value_entries = struct_data.get("value")
    if not isinstance(value_entries, Sequence):
        return []

    fields: List[Tuple[str, str]] = []
    for entry in value_entries:
        if not isinstance(entry, Mapping):
            continue
        raw_name = entry.get("key")
        raw_param_type = entry.get("param_type")
        field_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
        param_type = str(raw_param_type).strip() if isinstance(raw_param_type, str) else ""
        if not field_name or not param_type:
            continue
        canonical_type = param_type_to_canonical(param_type)
        fields.append((field_name, canonical_type))
    return fields


# ---------------------------------------------------------------------------
# NodeDef 代理：为结构体节点叠加字段端口类型
# ---------------------------------------------------------------------------


def build_struct_node_def_proxy_for_scene(
    scene: "GraphScene",
    node: NodeModel,
    base_def: NodeDef,
) -> Optional[NodeDef]:
    """基于当前节点绑定的结构体，为 UI 构造带字段端口类型的 NodeDef 代理。

    仅用于视图层类型推断，不回写到节点库。
    """
    if base_def is None:
        return None

    node_title = getattr(node, "title", "") or ""
    if node_title not in STRUCT_NODE_TITLES:
        return None

    struct_bindings = scene.model.get_struct_bindings()
    binding = struct_bindings.get(str(node.id))
    if not isinstance(binding, dict):
        return None

    struct_id_value = binding.get("struct_id")
    struct_id = str(struct_id_value) if struct_id_value is not None else ""
    if not struct_id:
        return None

    structs = get_current_package_structs(scene)
    if not structs or struct_id not in structs:
        return None

    struct_data = structs[struct_id]
    all_fields = _extract_struct_fields(struct_data)
    if not all_fields:
        return None

    selected_names_value = binding.get("field_names") or []
    selected_names: List[str] = []
    if isinstance(selected_names_value, Sequence) and not isinstance(selected_names_value, (str, bytes)):
        for entry in selected_names_value:
            if isinstance(entry, str) and entry:
                selected_names.append(entry)

    # 若绑定中未显式记录字段列表，回退为“全部字段”
    if not selected_names:
        selected_names = [name for name, _ in all_fields]

    selected_set = set(selected_names)
    selected_fields: List[Tuple[str, str]] = [
        (name, type_name) for (name, type_name) in all_fields if name in selected_set
    ]
    if not selected_fields:
        return None

    input_types: Dict[str, str] = dict(getattr(base_def, "input_types", {}) or {})
    output_types: Dict[str, str] = dict(getattr(base_def, "output_types", {}) or {})

    if node_title == STRUCT_SPLIT_NODE_TITLE:
        static_outputs = set(STRUCT_SPLIT_STATIC_OUTPUTS)
        for field_name, field_type in selected_fields:
            if field_name in static_outputs:
                continue
            output_types.setdefault(field_name, field_type)
    elif node_title == STRUCT_BUILD_NODE_TITLE:
        static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
        for field_name, field_type in selected_fields:
            if field_name in static_inputs:
                continue
            input_types.setdefault(field_name, field_type)
    elif node_title == STRUCT_MODIFY_NODE_TITLE:
        static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
        for field_name, field_type in selected_fields:
            if field_name in static_inputs:
                continue
            input_types.setdefault(field_name, field_type)
    else:
        return None

    return NodeDef(
        name=base_def.name,
        category=base_def.category,
        inputs=list(base_def.inputs),
        outputs=list(base_def.outputs),
        description=base_def.description,
        scopes=list(base_def.scopes),
        mount_restrictions=list(base_def.mount_restrictions),
        doc_reference=base_def.doc_reference,
        input_types=input_types,
        output_types=output_types,
        input_generic_constraints=dict(base_def.input_generic_constraints),
        output_generic_constraints=dict(base_def.output_generic_constraints),
        dynamic_port_type=base_def.dynamic_port_type,
        is_composite=base_def.is_composite,
        composite_id=base_def.composite_id,
    )


def get_effective_node_def_for_scene(
    scene: "GraphScene",
    node: NodeModel,
    base_def: Optional[NodeDef],
) -> Optional[NodeDef]:
    """获取在当前场景上下文下生效的 NodeDef（含结构体字段类型重写）。"""
    if base_def is None:
        return None

    node_title = getattr(node, "title", "") or ""
    if node_title in STRUCT_NODE_TITLES:
        struct_specific_def = build_struct_node_def_proxy_for_scene(scene, node, base_def)
        if struct_specific_def is not None:
            return struct_specific_def

    return base_def


# ---------------------------------------------------------------------------
# 节点级操作：结构体绑定与端口同步
# ---------------------------------------------------------------------------


def bind_struct_for_node(scene: "GraphScene", node_id: str) -> None:
    """为指定节点弹出结构体选择对话框并写入绑定信息。"""
    node = scene.model.nodes.get(node_id)
    if not node:
        return

    node_title = getattr(node, "title", "") or ""
    if node_title not in STRUCT_NODE_TITLES:
        return

    structs = get_current_package_structs(scene)
    if not structs:
        parent_widget: Optional[QtWidgets.QWidget] = None
        views = scene.views()
        if views:
            parent_widget = views[0].window()
        from ui.foundation import dialog_utils

        dialog_utils.show_warning_dialog(
            parent_widget,
            "提示",
            "当前工程中尚未定义任何结构体，请先在“管理配置/结构体定义”中创建结构体。",
        )
        return

    struct_bindings = scene.model.get_struct_bindings()
    existing_binding = struct_bindings.get(str(node_id)) or {}
    existing_struct_id_value = existing_binding.get("struct_id", "")
    existing_struct_id = str(existing_struct_id_value) if existing_struct_id_value is not None else ""
    existing_field_names = existing_binding.get("field_names") or []

    parent: Optional[QtWidgets.QWidget] = None
    views = scene.views()
    if views:
        parent = views[0].window()

    dialog = StructBindingDialog(
        structs=structs,
        parent=parent,
        current_struct_id=existing_struct_id,
        current_field_names=existing_field_names,
    )
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return

    selected_struct_id, selected_field_names = dialog.get_result()
    if not selected_struct_id or not selected_field_names:
        return

    struct_data = structs.get(selected_struct_id)
    if not isinstance(struct_data, dict):
        return

    struct_name_value = struct_data.get("name")
    struct_name = str(struct_name_value).strip() if isinstance(struct_name_value, str) else selected_struct_id

    binding_payload: Dict[str, object] = {
        "struct_id": selected_struct_id,
        "struct_name": struct_name,
        "field_names": list(selected_field_names),
    }
    scene.model.set_node_struct_binding(node_id, binding_payload)

    # 基于最新绑定信息补全端口
    sync_struct_ports_for_node(scene, node_id, structs)

    if callable(getattr(scene, "on_data_changed", None)):
        scene.on_data_changed()


def sync_struct_ports_for_node(
    scene: "GraphScene",
    node_id: str,
    structs: Dict[str, dict],
) -> None:
    """根据信息为指定结构体节点补全字段端口（仅新增缺失端口，不主动删除）。"""
    node = scene.model.nodes.get(node_id)
    if not node:
        return

    binding = scene.model.get_node_struct_binding(node_id)
    if not isinstance(binding, dict):
        return

    struct_id_value = binding.get("struct_id")
    struct_id = str(struct_id_value) if struct_id_value is not None else ""
    if not struct_id or struct_id not in structs:
        return

    struct_data = structs[struct_id]
    all_fields = _extract_struct_fields(struct_data)
    if not all_fields:
        return

    selected_names_value = binding.get("field_names") or []
    selected_names: List[str] = []
    if isinstance(selected_names_value, Sequence) and not isinstance(selected_names_value, (str, bytes)):
        for entry in selected_names_value:
            if isinstance(entry, str) and entry:
                selected_names.append(entry)

    if not selected_names:
        selected_names = [name for name, _ in all_fields]

    selected_set = set(selected_names)
    selected_fields: List[Tuple[str, str]] = [
        (name, type_name) for (name, type_name) in all_fields if name in selected_set
    ]
    if not selected_fields:
        return

    node_title = getattr(node, "title", "") or ""

    if node_title == STRUCT_SPLIT_NODE_TITLE:
        static_outputs = set(STRUCT_SPLIT_STATIC_OUTPUTS)
        existing = {port.name for port in getattr(node, "outputs", []) or []}
        for field_name, _ in selected_fields:
            if field_name in static_outputs or field_name in existing:
                continue
            node.add_output_port(field_name)
    elif node_title == STRUCT_BUILD_NODE_TITLE:
        static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
        existing = {port.name for port in getattr(node, "inputs", []) or []}
        for field_name, _ in selected_fields:
            if field_name in static_inputs or field_name in existing:
                continue
            node.add_input_port(field_name)
    elif node_title == STRUCT_MODIFY_NODE_TITLE:
        static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
        existing = {port.name for port in getattr(node, "inputs", []) or []}
        for field_name, _ in selected_fields:
            if field_name in static_inputs or field_name in existing:
                continue
            node.add_input_port(field_name)
    else:
        return

    node_item = scene.node_items.get(node_id)
    if node_item is not None:
        node_item._layout_ports()


__all__ = [
    "get_current_package_structs",
    "build_struct_node_def_proxy_for_scene",
    "get_effective_node_def_for_scene",
    "bind_struct_for_node",
    "sync_struct_ports_for_node",
]


