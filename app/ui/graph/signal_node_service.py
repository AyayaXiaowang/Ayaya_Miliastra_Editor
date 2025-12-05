from __future__ import annotations

"""信号节点适配服务

本模块位于图编辑 UI 与引擎信号系统之间，集中负责：
- 基于当前包视图的 `signals` 字段为“发送信号 / 监听信号”节点构造带精确端口类型的 NodeDef 代理；
- 在图中为信号节点绑定 signal_id，并同步“信号名”常量；
- 根据信号定义补全/同步发送与监听节点上的参数端口；
- 打开信号选择/管理对话框并在变更后刷新相关节点端口。

GraphScene 只负责：
- 提供 `model` / `node_items` / `signal_edit_context` 这些上下文；
- 在适配服务完成模型与端口更新后刷新 UI。
"""

from typing import Dict, Optional, Iterable, TYPE_CHECKING, List

from PyQt6 import QtWidgets

from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.graph.models.package_model import SignalConfig
from engine.nodes.node_definition_loader import NodeDef
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
    SIGNAL_LISTEN_STATIC_OUTPUTS,
    SIGNAL_NAME_PORT_NAME,
)
from engine.signal import get_default_signal_binding_service, compute_signal_schema_hash

if TYPE_CHECKING:
    from ui.graph.graph_scene import GraphScene


# ---------------------------------------------------------------------------
# 公共工具：获取当前包的信号字典
# ---------------------------------------------------------------------------


def get_current_package_signals(scene: "GraphScene") -> Optional[Dict[str, SignalConfig]]:
    """通过编辑上下文获取当前存档的信号字典。

    约定 `scene.signal_edit_context` 字段：
    - get_current_package: Callable[[], PackageView | None]
    """
    context = getattr(scene, "signal_edit_context", {}) or {}
    get_package = context.get("get_current_package")
    if not callable(get_package):
        return None
    package = get_package()
    if package is None:
        return None
    signals_dict = getattr(package, "signals", None)
    if not isinstance(signals_dict, dict):
        return None
    return signals_dict


# ---------------------------------------------------------------------------
# NodeDef 代理：为信号节点叠加参数类型
# ---------------------------------------------------------------------------


def build_signal_node_def_proxy_for_scene(
    scene: "GraphScene",
    node: NodeModel,
    base_def: NodeDef,
) -> Optional[NodeDef]:
    """基于当前节点绑定的信号，为 UI 构造带参数类型的 NodeDef 代理。

    仅用于视图层类型推断，不回写到节点库。
    """
    signals_dict = get_current_package_signals(scene)
    if not signals_dict:
        return None

    binding_service = get_default_signal_binding_service()
    bound_signal_id = binding_service.get_node_signal_id(scene.model, node.id)
    if not bound_signal_id:
        return None

    signal_config = signals_dict.get(bound_signal_id)
    if signal_config is None:
        return None

    parameters = getattr(signal_config, "parameters", []) or []
    param_type_map: Dict[str, str] = {}
    for parameter_config in parameters:
        param_name = getattr(parameter_config, "name", "")
        param_type = getattr(parameter_config, "parameter_type", "")
        if param_name and param_type:
            param_type_map[str(param_name)] = str(param_type)

    if not param_type_map:
        return None

    input_types: Dict[str, str] = dict(getattr(base_def, "input_types", {}) or {})
    output_types: Dict[str, str] = dict(getattr(base_def, "output_types", {}) or {})

    node_title = getattr(node, "title", "") or ""
    if node_title == SIGNAL_SEND_NODE_TITLE:
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
        for param_name, param_type in param_type_map.items():
            if param_name in static_inputs:
                continue
            input_types[param_name] = param_type
    elif node_title == SIGNAL_LISTEN_NODE_TITLE:
        static_outputs = set(SIGNAL_LISTEN_STATIC_OUTPUTS)
        for param_name, param_type in param_type_map.items():
            if param_name in static_outputs:
                continue
            output_types[param_name] = param_type
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
    """获取在当前场景上下文下生效的 NodeDef（含信号参数类型重写）。"""
    if base_def is None:
        return None

    node_title = getattr(node, "title", "") or ""
    if node_title in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
        signal_specific_def = build_signal_node_def_proxy_for_scene(scene, node, base_def)
        if signal_specific_def is not None:
            return signal_specific_def

    return base_def


# ---------------------------------------------------------------------------
# 节点级操作：信号绑定与端口同步
# ---------------------------------------------------------------------------


def _infer_signal_config_from_node_constants(
    node: NodeModel,
    signals_dict: Dict[str, SignalConfig],
) -> Optional[SignalConfig]:
    """基于节点上的“信号名”输入常量，从信号字典中推断 SignalConfig。

    规则约定（与代码级校验保持一致）：
    - “信号名”端口只接受『信号名称』（SignalConfig.signal_name），不接受信号 ID；
    - 当文本恰好等于某个信号名称时，视为有效匹配并返回对应的 SignalConfig；
    - 匹配成功仅影响当前场景内的 GraphModel.metadata 绑定，不写回磁盘。
    """
    if not isinstance(signals_dict, dict):
        return None

    input_constants = getattr(node, "input_constants", {}) or {}
    if not isinstance(input_constants, dict):
        return None

    raw_value = input_constants.get(SIGNAL_NAME_PORT_NAME)
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    # 仅按 SignalConfig.signal_name 文本匹配，不接受信号 ID。
    for candidate in signals_dict.values():
        signal_name_value = getattr(candidate, "signal_name", None)
        if str(signal_name_value or "").strip() == text:
            return candidate

    return None


def bind_signal_for_node(scene: "GraphScene", node_id: str) -> None:
    """为指定节点弹出信号选择对话框并写入绑定信息。"""
    node = scene.model.nodes.get(node_id)
    if not node:
        return
    node_title = getattr(node, "title", "") or ""
    if node_title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
        return

    signals_dict = get_current_package_signals(scene)
    if not signals_dict:
        return

    binding_service = get_default_signal_binding_service()
    current_signal_id = binding_service.get_node_signal_id(scene.model, node_id) or ""

    from ui.dialogs.signal_picker_dialog import SignalPickerDialog

    parent_widget: Optional[QtWidgets.QWidget] = None
    views = scene.views()
    if views:
        parent_widget = views[0].window()

    dialog = SignalPickerDialog(
        signals=signals_dict,
        parent=parent_widget,
        current_signal_id=current_signal_id,
    )
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return

    selected_signal_id = dialog.get_selected_signal_id()
    if not selected_signal_id or selected_signal_id == current_signal_id:
        return

    # 写入绑定
    binding_service.set_node_signal_id(scene.model, node_id, selected_signal_id)

    # 同步“信号名”输入常量（若存在）
    signal_config = signals_dict.get(selected_signal_id)
    if signal_config is not None:
        has_signal_name_port = any(
            getattr(port, "name", "") == SIGNAL_NAME_PORT_NAME
            for port in getattr(node, "inputs", []) or []
        )
        if has_signal_name_port:
            if not isinstance(node.input_constants, dict):
                node.input_constants = {}
            node.input_constants[SIGNAL_NAME_PORT_NAME] = signal_config.signal_name

    # 基于信号定义尝试补全动态端口
    sync_signal_ports_for_node(scene, node_id, signals_dict)

    on_changed = getattr(scene, "on_data_changed", None)
    if callable(on_changed):
        on_changed()


def open_signal_manager(scene: "GraphScene") -> None:
    """打开信号管理器对话框，并在信号定义变更后同步当前图中的信号端口。"""
    signals_dict = get_current_package_signals(scene)
    if signals_dict is None:
        return

    from ui.dialogs.signal_manager_dialog import SignalManagerDialog

    parent_widget: Optional[QtWidgets.QWidget] = None
    views = scene.views()
    if views:
        parent_widget = views[0].window()

    dialog = SignalManagerDialog(signals_dict, parent=parent_widget)
    dialog.signals_updated.connect(lambda: on_signals_updated_from_manager(scene))
    dialog.exec()


def on_signals_updated_from_manager(scene: "GraphScene") -> None:
    """当信号管理器中的信号定义被修改后，尝试同步当前图中相关节点的端口。"""
    signals_dict = get_current_package_signals(scene)
    if not signals_dict:
        return
    # 统一遍历当前图中所有发送/监听信号节点：无论是否已存在绑定，都尝试根据
    # 绑定信息或“信号名”常量补全端口与输入常量。
    target_node_ids: List[str] = []
    for node_id, node in scene.model.nodes.items():
        node_title = getattr(node, "title", "") or ""
        if node_title in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
            target_node_ids.append(str(node_id))

    affected_node_ids: List[str] = []
    for node_id in target_node_ids:
        if node_id in scene.model.nodes:
            sync_signal_ports_for_node(scene, node_id, signals_dict)
            affected_node_ids.append(node_id)

    if affected_node_ids:
        scene._refresh_all_ports(affected_node_ids)
        on_changed = getattr(scene, "on_data_changed", None)
        if callable(on_changed):
            on_changed()

    # 更新当前图的信号 schema 哈希：视为“已对齐到最新信号定义版本”
    if isinstance(signals_dict, dict):
        current_hash = compute_signal_schema_hash(signals_dict)
        scene.model.metadata.setdefault("signal_schema_hash", current_hash)
        scene.model.metadata["signal_schema_hash"] = current_hash


def sync_signal_ports_for_node(
    scene: "GraphScene",
    node_id: str,
    signals_dict: Dict,
) -> None:
    """根据信号定义为指定节点补全参数端口（仅新增缺失端口，不主动删除）。"""
    node = scene.model.nodes.get(node_id)
    if not node:
        return

    binding_service = get_default_signal_binding_service()
    bound_signal_id = binding_service.get_node_signal_id(scene.model, node_id)
    signal_config = None
    if bound_signal_id:
        signal_config = signals_dict.get(bound_signal_id)

    # 若尚未写入绑定或绑定已失效，则尝试基于“信号名”常量推断信号定义，并在当前图内补写绑定。
    if signal_config is None:
        inferred = _infer_signal_config_from_node_constants(node, signals_dict)
        if inferred is None:
            return
        signal_id_value = getattr(inferred, "signal_id", None)
        if isinstance(signal_id_value, str) and signal_id_value:
            binding_service.set_node_signal_id(scene.model, node_id, signal_id_value)
            bound_signal_id = signal_id_value
        signal_config = inferred

    # 同步“信号名”输入常量（若节点上存在该端口），用于在 UI 中展示已绑定信号名。
    signal_name_value = getattr(signal_config, "signal_name", "")
    if signal_name_value:
        has_signal_name_port = any(
            getattr(port, "name", "") == SIGNAL_NAME_PORT_NAME
            for port in getattr(node, "inputs", []) or []
        )
        if has_signal_name_port:
            if not isinstance(node.input_constants, dict):
                node.input_constants = {}
            node.input_constants[SIGNAL_NAME_PORT_NAME] = signal_name_value

    parameters = getattr(signal_config, "parameters", []) or []
    param_names = [getattr(param, "name", "") for param in parameters if getattr(param, "name", "")]
    if not param_names:
        return

    node_title = getattr(node, "title", "") or ""
    if node_title == SIGNAL_SEND_NODE_TITLE:
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
        existing_names = {getattr(port, "name", "") for port in getattr(node, "inputs", []) or []}
        for param_name in param_names:
            if param_name in existing_names or param_name in static_inputs:
                continue
            node.add_input_port(param_name)
    elif node_title == SIGNAL_LISTEN_NODE_TITLE:
        # 监听信号节点：确保左侧存在用于展示/选择的“信号名”输入端口（仅 UI 使用，不参与连线）。
        has_signal_name_input = any(
            getattr(port, "name", "") == SIGNAL_NAME_PORT_NAME
            for port in getattr(node, "inputs", []) or []
        )
        if not has_signal_name_input:
            node.add_input_port(SIGNAL_NAME_PORT_NAME)

        static_outputs = set(SIGNAL_LISTEN_STATIC_OUTPUTS)
        existing_names = {getattr(port, "name", "") for port in getattr(node, "outputs", []) or []}
        for param_name in param_names:
            if param_name in existing_names or param_name in static_outputs:
                continue
            node.add_output_port(param_name)
    else:
        return

    node_item = scene.node_items.get(node_id)
    if node_item is not None:
        # 补全端口后重新布局节点
        node_item._layout_ports()

        # 对于在模型层已存在、但由于端口缺失而未能创建 UI 连线的边：
        # 这里在端口补完后按需补一次 EdgeGraphicsItem，使“参数端口”上的连线在 UI 中可见。
        for edge_id, edge in list(scene.model.edges.items()):
            if edge.dst_node != node_id:
                continue
            if edge_id in scene.edge_items:
                continue
            # 仅处理目标端口名称与当前节点输入端口匹配的普通数据边
            has_matching_input = any(
                getattr(port, "name", "") == edge.dst_port
                for port in getattr(node, "inputs", []) or []
            )
            if not has_matching_input:
                continue
            # 复用 SceneModelOpsMixin.add_edge_item 的 UI 创建逻辑
            scene.add_edge_item(edge)


__all__ = [
    "get_current_package_signals",
    "build_signal_node_def_proxy_for_scene",
    "get_effective_node_def_for_scene",
    "bind_signal_for_node",
    "open_signal_manager",
    "on_signals_updated_from_manager",
    "sync_signal_ports_for_node",
]


