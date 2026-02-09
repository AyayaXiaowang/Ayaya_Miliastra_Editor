from __future__ import annotations

from typing import Any, Dict, Optional

from app.automation.ports.port_type_inference import is_generic_type_name, lookup_struct_field_type_by_name
from app.automation.ports.port_type_resolver import resolve_effective_port_type_for_model
from app.models import TodoItem
from app.models.todo_node_type_helper import NodeTypeHelper
from engine.graph.models.graph_model import GraphModel


class PortTypeExecutorAdapter:
    """为端口类型推断提供最小 executor 适配器。

    复用 `NodeTypeHelper` 的节点库，并实现 `get_node_def_for_model` / `log`
    及其对应的私有变体，以兼容端口类型推断工具期望的 executor 接口。
    不依赖 Qt，仅承担适配作用。
    """

    def __init__(self, type_helper: NodeTypeHelper) -> None:
        self._type_helper = type_helper

    def _get_node_def_for_model(self, node_model: Any) -> Any:
        return self._type_helper.get_node_def_for_model(node_model)

    def get_node_def_for_model(self, node_model: Any) -> Any:
        """公开节点定义查询接口，语义与 `_get_node_def_for_model` 一致。"""
        return self._get_node_def_for_model(node_model)

    def _log(self, message: str, log_callback=None) -> None:
        # UI 场景下不输出日志；仅满足推断工具的接口要求
        if callable(log_callback):
            log_callback(str(message))

    def log(self, message: str, log_callback=None) -> None:
        """公开日志接口，语义与 `_log` 一致。"""
        self._log(message, log_callback)


def _infer_output_type_from_struct_field_for_dict_lookup(
    *,
    param_name: str,
    node_model: Any,
) -> str:
    """针对“以键查询字典值”节点，基于结构体字段名推断输出端口的具体类型。

    规则：
    - 仅在节点标题为“以键查询字典值”且端口名为“值”时生效；
    - 从输入常量“键”中读取字段名，并在结构体定义中查找对应字段类型；
    - 若查不到或存在歧义，则返回空字符串，交由通用推断逻辑处理。
    """
    if node_model is None:
        return ""

    title = getattr(node_model, "title", "")
    if not isinstance(title, str) or title != "以键查询字典值":
        return ""

    if param_name != "值":
        return ""

    constants = getattr(node_model, "input_constants", {}) or {}
    key_raw = constants.get("键")
    key_name = str(key_raw) if key_raw is not None else ""
    if not key_name:
        return ""

    return lookup_struct_field_type_by_name(key_name)


def infer_concrete_port_type_for_step(
    *,
    param_name: str,
    raw_value: Any,
    todo: TodoItem,
    graph_model: Optional[GraphModel],
    type_helper: NodeTypeHelper,
    type_helper_executor: PortTypeExecutorAdapter,
) -> str:
    """为类型设置步骤推断端口的具体数据类型。

    统一以 GraphModel 级“有效端口类型”推断为准（单一真源）。
    该函数不依赖 Qt，仅依赖 TodoItem 与 GraphModel。
    """
    detail_info = todo.detail_info or {}
    node_identifier = str(detail_info.get("node_id", "") or "")
    if not node_identifier:
        return ""
    if graph_model is None:
        return ""

    node_model = graph_model.nodes.get(node_identifier)
    if node_model is None:
        return ""

    # 判定端口属于输入侧还是输出侧
    side = ""
    for port in getattr(node_model, "inputs", []) or []:
        name = getattr(port, "name", "")
        if isinstance(name, str) and name == param_name:
            side = "input"
            break
    if not side:
        for port in getattr(node_model, "outputs", []) or []:
            name = getattr(port, "name", "")
            if isinstance(name, str) and name == param_name:
                side = "output"
                break
    if not side:
        return ""

    node_def = type_helper.get_node_def_for_model(node_model)
    if node_def is None:
        return ""

    if side == "input":
        resolved = resolve_effective_port_type_for_model(
            port_name=param_name,
            node_model=node_model,
            graph_model=graph_model,
            executor=type_helper_executor,
            is_input=True,
            is_flow=False,
            default_when_unknown="",
        )
        resolved_text = str(resolved or "").strip()
        if resolved_text and not is_generic_type_name(resolved_text):
            return resolved_text
        return "字符串"

    # 输出端口
    # 先尝试：基于结构体字段名的专用推断（以键查询字典值）
    struct_based_type = _infer_output_type_from_struct_field_for_dict_lookup(
        param_name=param_name,
        node_model=node_model,
    )
    if struct_based_type:
        return struct_based_type

    resolved = resolve_effective_port_type_for_model(
        port_name=param_name,
        node_model=node_model,
        graph_model=graph_model,
        executor=type_helper_executor,
        is_input=False,
        is_flow=False,
        default_when_unknown="",
    )
    resolved_text = str(resolved or "").strip()
    if resolved_text and not is_generic_type_name(resolved_text):
        return resolved_text

    return "字符串"


