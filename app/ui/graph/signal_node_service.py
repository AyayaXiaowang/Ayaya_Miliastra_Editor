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
from ui.graph.core.signal_logic import (
    build_signal_node_def_proxy,
    plan_signal_port_sync,
    resolve_signal_binding,
)

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
    context = resolve_signal_binding(node, signals_dict, bound_signal_id)
    if context is None:
        return None

    return build_signal_node_def_proxy(getattr(node, "title", "") or "", base_def, context)


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
    context = resolve_signal_binding(node, signals_dict, bound_signal_id)
    if context is None:
        return

    plan = plan_signal_port_sync(node, context)

    if plan.bound_signal_id and plan.bound_signal_id != bound_signal_id:
        binding_service.set_node_signal_id(scene.model, node_id, plan.bound_signal_id)

    if plan.signal_name_constant:
        has_signal_name_port = any(
            getattr(port, "name", "") == SIGNAL_NAME_PORT_NAME
            for port in getattr(node, "inputs", []) or []
        )
        if has_signal_name_port:
            if not isinstance(node.input_constants, dict):
                node.input_constants = {}
            node.input_constants[SIGNAL_NAME_PORT_NAME] = plan.signal_name_constant

    for port_name in plan.add_inputs:
        node.add_input_port(port_name)
    for port_name in plan.add_outputs:
        node.add_output_port(port_name)

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


