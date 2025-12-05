# -*- coding: utf-8 -*-
"""
port_type_dicts: 字典端口与别名字典类型推断工具。

职责：
- 解析类似“字符串_GUID列表字典”或“字符串-GUID列表字典”的别名字典类型；
- 基于入边与 GraphModel.metadata['port_type_overrides'] 为字典输入端口推断键/值类型；
- 为自动化端口类型设置与 Todo UI 提供统一的字典键/值类型来源。

模块定位：
- 作为 `app.automation.ports` 包的内部实现模块，仅供本包内部使用；
- 包外调用方如需解析别名字典类型或推断字典端口键/值类型，应通过
  `app.automation.ports.port_type_inference` 导入公共函数（例如
  `parse_typed_dict_alias`、`infer_dict_key_value_types_for_input`），而不是直接
  依赖本模块。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.automation.ports.port_type_common import unique_preserve_order
from app.automation.ports.port_type_context import (
    EdgeLookup,
    build_port_type_overrides,
    get_node_port_type_overrides_for_id,
    _iter_incoming_edges,
)
from app.automation.ports.port_type_generics import safe_get_port_type_from_node_def
from engine.graph.models.graph_model import GraphModel, NodeModel


def parse_typed_dict_alias(type_name: object) -> tuple[bool, str, str]:
    """解析类似“字符串_GUID列表字典”或“字符串-GUID列表字典”的别名字典类型。

    约定格式：
    - 统一以“字典”结尾，例如：`字符串_GUID列表字典` 或 `字符串-GUID列表字典`
    - 以第一个“-”或“_”划分键/值类型名：左侧为键类型，右侧为值类型
    - 键/值类型名本身必须是已有的合法类型名（例如：整数、字符串、GUID列表等）
    """
    if not isinstance(type_name, str):
        return False, "", ""

    text = type_name.strip()
    if not text or not text.endswith("字典"):
        return False, "", ""

    body = text[: -len("字典")].strip()
    if not body:
        return False, "", ""

    dash_index = body.find("-")
    underscore_index = body.find("_")

    separator_index = -1
    if dash_index >= 0 and underscore_index >= 0:
        separator_index = min(dash_index, underscore_index)
    elif dash_index >= 0:
        separator_index = dash_index
    else:
        separator_index = underscore_index

    if separator_index <= 0 or separator_index >= len(body) - 1:
        return False, "", ""

    key_raw = body[:separator_index]
    value_raw = body[separator_index + 1 :]
    key_type = key_raw.strip()
    value_type = value_raw.strip()
    if not key_type or not value_type:
        return False, "", ""

    return True, key_type, value_type


def infer_dict_key_value_types_for_input(
    node_model: NodeModel,
    port_name: str,
    graph_model: GraphModel,
    executor,
    log_callback=None,
    edge_lookup: EdgeLookup | None = None,
) -> Optional[Tuple[str, str]]:
    """为输入端口推断字典键/值类型。

    当前策略：
    - 遍历指向该端口的所有入边；
    - 若上游端口的最终类型为“别名字典”（如“字符串_GUID列表字典”），
      则按别名解析出键/值类型并参与候选集合；
    - 多个来源给出不同键/值组合时，记录日志并优先取首个组合。
    """
    if not isinstance(port_name, str) or port_name == "":
        return None

    incoming_edges = _iter_incoming_edges(node_model.id, port_name, graph_model, edge_lookup)
    if not incoming_edges:
        return None

    candidates: List[Tuple[str, str]] = []

    # 别名字典路径：上游端口类型为“X_Y字典”/“X-Y字典”等别名时，从类型名中解析键/值类型
    port_type_overrides: Dict[str, Dict[str, str]] = build_port_type_overrides(graph_model)

    for edge in incoming_edges:
        src_node = graph_model.nodes.get(edge.src_node)
        if src_node is None:
            continue

        # 优先：使用 GraphModel.metadata.port_type_overrides 中的最终类型
        alias_type: str = ""
        node_overrides = get_node_port_type_overrides_for_id(port_type_overrides, src_node.id)
        if isinstance(node_overrides, dict):
            override_raw = node_overrides.get(edge.src_port)
            if isinstance(override_raw, str):
                alias_type = override_raw.strip()

        # 回退：从节点定义的输出端口类型中获取
        if not alias_type and executor is not None:
            src_def = executor.get_node_def_for_model(src_node)
            if src_def is not None:
                type_raw = safe_get_port_type_from_node_def(
                    src_def,
                    edge.src_port,
                    is_input=False,
                )
                if isinstance(type_raw, str):
                    alias_type = type_raw.strip()

        ok, key_type, value_type = parse_typed_dict_alias(alias_type)
        if ok:
            candidates.append((key_type, value_type))

    if len(candidates) == 0:
        return None

    # 去重保持顺序（同一键/值组合只保留首个出现的位置）。
    unique_candidates: List[Tuple[str, str]] = unique_preserve_order(candidates)

    if len(unique_candidates) > 1 and executor is not None:
        executor.log(
            f"[端口类型/字典] 键/值类型推断出现多种候选 {unique_candidates}，将使用首个 {unique_candidates[0]}",
            log_callback,
        )

    return unique_candidates[0]


__all__ = [
    "parse_typed_dict_alias",
    "infer_dict_key_value_types_for_input",
]


