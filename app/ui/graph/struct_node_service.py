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
    STRUCT_NAME_PORT_NAME,
)
from engine.resources.definition_schema_view import (
    get_default_definition_schema_view,
)
from app.ui.dialogs.struct_binding_dialog import StructBindingDialog
from app.ui.graph.logic.struct_logic import (
    build_struct_node_def_proxy,
    plan_struct_port_sync,
    resolve_struct_binding,
)
from app.ui.foundation.context_menu_builder import ContextMenuBuilder


if TYPE_CHECKING:
    from app.ui.graph.graph_scene import GraphScene


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

    约定：
    - 仅暴露“基础结构体”（struct_ype == "basic" 或未显式标注 struct_ype）；
    - 跳过局内存档等运行期存档结构体（例如 struct_ype == "ingame_save"），
      避免在图编辑层直接操作存档内部结构。
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
        struct_type_raw = data.get("struct_ype")
        if isinstance(struct_type_raw, str):
            struct_type = struct_type_raw.strip()
            # 仅保留基础结构体；显式标记为其它类型（如 "ingame_save"）的结构体在
            # 图编辑层不提供为【拆分/拼装/修改结构体】节点绑定选项。
            if struct_type and struct_type != "basic":
                continue
        structs[str(struct_id)] = dict(data)
    return structs


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

    structs = get_current_package_structs(scene)
    if not structs:
        return None

    struct_bindings = scene.model.get_struct_bindings()
    binding_payload = struct_bindings.get(str(node.id)) or {}
    context = resolve_struct_binding(binding_payload, structs)
    if context is None:
        return None

    return build_struct_node_def_proxy(node_title, base_def, context)


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
# GraphScene 侧薄封装：预处理与菜单注入（下沉 GraphScene 的业务耦合点）
# ---------------------------------------------------------------------------


def prepare_node_model_for_scene(scene: "GraphScene", node: NodeModel) -> None:
    """在创建 NodeGraphicsItem 之前，对“结构体相关节点”做一次 UI 侧模型预处理。

    规则：
    - 若图模型中已存在 struct_bindings，则在创建图形项前基于当前包结构体定义补全字段端口；
    - 与“配置结构体…”对话框的端口同步语义保持一致。
    """
    node_title = getattr(node, "title", "") or ""
    if node_title not in STRUCT_NODE_TITLES:
        return

    struct_bindings = scene.model.get_struct_bindings()
    binding_payload = struct_bindings.get(str(node.id))
    if not isinstance(binding_payload, dict):
        return

    structs = get_current_package_structs(scene)
    if not structs:
        return

    sync_struct_ports_for_node(scene, str(node.id), structs)


def contribute_context_menu_for_node(
    scene: "GraphScene",
    menu_builder: ContextMenuBuilder,
    *,
    node_id: str,
    node_title: str,
    add_separator_before: bool,
) -> bool:
    """为节点注入“结构体相关”的右键菜单项。"""
    if node_title not in STRUCT_NODE_TITLES:
        return False

    if add_separator_before:
        menu_builder.add_separator()

    def _bind_struct() -> None:
        bind_struct_for_node(scene, node_id)

    menu_builder.add_action("配置结构体…", _bind_struct)
    return True


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
        from app.ui.foundation import dialog_utils

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

    # 若节点上存在“结构体名”输入端口，则同步其常量值，便于在 Graph Code 与 UI 中直观看到已绑定结构体。
    has_struct_name_port = any(
        getattr(port, "name", "") == STRUCT_NAME_PORT_NAME
        for port in getattr(node, "inputs", []) or []
    )
    if has_struct_name_port:
        if not isinstance(node.input_constants, dict):
            node.input_constants = {}
        node.input_constants[STRUCT_NAME_PORT_NAME] = struct_name

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

    binding_payload = scene.model.get_node_struct_binding(node_id)
    context = resolve_struct_binding(binding_payload, structs)
    if context is None:
        return

    plan = plan_struct_port_sync(node, context)
    node_title = getattr(node, "title", "") or ""
    if node_title not in STRUCT_NODE_TITLES:
        return

    has_struct_name_port = any(
        getattr(port, "name", "") == STRUCT_NAME_PORT_NAME
        for port in getattr(node, "inputs", []) or []
    )
    if has_struct_name_port and plan.struct_name_constant:
        if not isinstance(node.input_constants, dict):
            node.input_constants = {}
        node.input_constants[STRUCT_NAME_PORT_NAME] = plan.struct_name_constant

    for port_name in plan.add_inputs:
        node.add_input_port(port_name)
    for port_name in plan.add_outputs:
        node.add_output_port(port_name)

    node_item = scene.node_items.get(node_id)
    if node_item is not None:
        node_item._layout_ports()


__all__ = [
    "get_current_package_structs",
    "build_struct_node_def_proxy_for_scene",
    "get_effective_node_def_for_scene",
    "prepare_node_model_for_scene",
    "contribute_context_menu_for_node",
    "bind_struct_for_node",
    "sync_struct_ports_for_node",
]


