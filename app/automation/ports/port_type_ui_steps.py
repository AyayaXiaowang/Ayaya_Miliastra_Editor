from __future__ import annotations

"""port_type_ui_steps: 端口类型设置相关的通用 UI 步骤。

职责：
- 在给定节点截图与端口列表的前提下，定位指定端口中心；
- 通过 Settings 图标或模板搜索找到类型设置入口并完成点击；
- 根据目标类型决定走普通类型设置流程还是字典键/值类型设置流程。

注意：
- 本模块不直接参与“类型推断”决策，仅根据调用方给出的目标类型在 UI 上完成设置；
- 入参中涉及的截图与端口列表由上层控制流（例如 `port_type_setter` 与
  输入/输出侧步骤模块）统一管理与缓存。
"""

from typing import Callable, List, Optional, Tuple

from PIL import Image

from engine.graph.models.graph_model import NodeModel
from engine.utils.graph.graph_utils import is_flow_port_name

from app.automation.editor.executor_protocol import EditorExecutorWithViewport, AutomationStepContext
from app.automation.ports.port_picker import pick_port_center_for_node
from app.automation.ports.port_type_inference import parse_typed_dict_alias
from app.automation.ports.dict_port_type_steps import set_dict_port_type_with_settings
from app.automation.ports.port_type_ui_core import (
    apply_type_in_open_search_dialog,
    set_port_type_with_settings,
)


def compute_planned_ordinal(node: NodeModel, mapped_name: str, side: str) -> Optional[int]:
    """计算在过滤掉流程端口后的“计划序号”（ordinal）索引。

    Args:
        node: 当前节点模型
        mapped_name: 通过索引映射得到的端口名称
        side: 'left' 或 'right'，分别表示输入/输出侧

    Returns:
        若在同侧非流程端口序列中存在该端口名，则返回其索引；否则返回 None。
    """
    if not isinstance(mapped_name, str) or mapped_name == "":
        return None

    if side == "left":
        ports = getattr(node, "inputs", None) or []
    elif side == "right":
        ports = getattr(node, "outputs", None) or []
    else:
        ports = getattr(node, "inputs", None) or []

    names_all: List[str] = [getattr(port_obj, "name", "") for port_obj in ports]
    names_filtered: List[str] = [name for name in names_all if not is_flow_port_name(name)]

    if mapped_name not in names_filtered:
        return None

    return int(names_filtered.index(mapped_name))


def is_first_data_port(node: NodeModel, mapped_name: str, side: str) -> bool:
    """判断给定端口是否为该节点某侧第一个“数据”端口。

    该判断基于 `compute_planned_ordinal` 的过滤结果，确保“什么算数据端口”的规则
    只在一处维护：若未来需要调整过滤规则，仅需修改 `compute_planned_ordinal`。
    """
    if not isinstance(mapped_name, str) or mapped_name == "":
        return False
    ordinal_index = compute_planned_ordinal(node, mapped_name, side=side)
    if ordinal_index is None:
        return False
    return int(ordinal_index) == 0


def locate_port_center(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node: NodeModel,
    node_bbox: Tuple[int, int, int, int],
    mapped_name: str,
    side: str,
    ports_list: list,
    log_callback,
    ordinal_fallback_index: Optional[int] = None,
) -> Tuple[int, int]:
    """在给定截图与端口列表上定位指定端口的中心坐标。"""
    if ordinal_fallback_index is None:
        ordinal_fallback_index = compute_planned_ordinal(node, mapped_name, side=side)

    port_center = pick_port_center_for_node(
        executor,
        screenshot,
        node_bbox,
        mapped_name,
        want_output=(side == "right"),
        expected_kind="data",
        log_callback=log_callback,
        ordinal_fallback_index=ordinal_fallback_index,
        ports_list=ports_list,
    )
    return port_center


def apply_port_type_via_ui(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    target_type: str,
    side: str,
    ports_list: list,
    ctx: AutomationStepContext,
) -> bool:
    """根据目标类型走通用 UI 流程设置端口类型。

    规则：
    - 当 `target_type` 解析为“别名字典类型”（例如 `字符串_GUID列表字典` 或 `字符串-GUID列表字典`）时，
      统一通过 `dict_port_type_steps.set_dict_port_type_with_settings` 打开 Dictionary 对话框，
      为键/值两侧分别设置类型；
    - 其余情况走基础的 Settings 类型设置流程，仅设置单一类型字符串。
    """
    is_dict_alias, key_type, value_type = parse_typed_dict_alias(target_type)
    if is_dict_alias:
        return set_dict_port_type_with_settings(
            executor,
            screenshot,
            node_bbox,
            port_center,
            port_name,
            key_type,
            value_type,
            side,
            ports_list,
            ctx,
        )

    return set_port_type_with_settings(
        executor,
        screenshot,
        node_bbox,
        port_center,
        port_name,
        target_type,
        side,
        ports_list,
        ctx,
    )


__all__ = [
    "compute_planned_ordinal",
    "is_first_data_port",
    "locate_port_center",
    "apply_type_in_open_search_dialog",
    "set_port_type_with_settings",
    "apply_port_type_via_ui",
]


