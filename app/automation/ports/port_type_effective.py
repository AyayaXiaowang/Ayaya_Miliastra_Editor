from __future__ import annotations

"""port_type_effective: 端口“有效类型”综合推断逻辑（无 UI 操作）。

职责：
- 在不触碰截图、坐标换算、点击等 UI 行为的前提下，综合参数值、声明类型、连线与动态类型，
  为输入/输出端口计算“最终应当采用的具体数据类型”；
- 封装“值推断 vs. 连线推断 vs. 声明/动态类型”的优先级规则，并统一打点日志，便于在
  自动化执行与 Todo UI 中共享同一套类型选择策略。

注意：
- 本模块仅依赖执行器的日志输出能力（`executor.log`），不做任何窗口操作或坐标计算，
  以便在需要时通过替身/假对象在不依赖真实编辑器的环境下进行单元测试。
"""

from typing import Dict, Optional

from engine.graph.models.graph_model import GraphModel, NodeModel

from app.automation.editor.executor_protocol import EditorExecutorWithViewport
from app.automation.ports._type_utils import infer_type_from_value
from app.automation.ports.port_type_inference import (
    build_port_type_overrides,
    get_non_empty_str,
    infer_input_type_from_edges,
    infer_output_type_from_edges,
    infer_output_type_from_self_inputs,
    is_generic_type_name,
    is_list_like_type_name,
    resolve_port_type_with_overrides,
    upgrade_to_list_type,
)


def _should_override_with_edge_type(
    current_type_text: Optional[str],
    candidate_type_text: Optional[str],
) -> bool:
    """判断是否应该使用连线推断的类型覆盖当前候选类型。

    规则：
    - 候选类型必须是非空且非泛型类型；
    - 当当前类型为空或空白字符串时，总是允许覆盖；
    - 当当前类型以“字符串”开头（包括“字符串列表”等）时，视为值推断可信度较低，
      若候选类型不同则允许覆盖。
    """
    candidate_text = get_non_empty_str(candidate_type_text)
    if candidate_text == "":
        return False
    if is_generic_type_name(candidate_text):
        return False
    current_text = get_non_empty_str(current_type_text) if current_type_text is not None else ""
    if current_text == "":
        return True
    # 仅在值推断回落到“字符串/字符串列表”时被视为低可信，允许连线类型覆盖
    if current_text.startswith("字符串") and candidate_text != current_text:
        return True
    return False


def infer_effective_input_type(
    executor: EditorExecutorWithViewport,
    node: NodeModel,
    node_def,
    mapped_name: str,
    declared_input_type: str,
    param_values_by_name: Dict[str, str],
    graph_model: GraphModel,
    edge_lookup,
    log_callback,
) -> str:
    """根据参数值、声明、连线及动态类型综合推断输入端口的有效类型。

    推断顺序：
    1. 参数值推断：若参数值非空，则先通过值→类型映射，并在声明为列表类型时进行列表提升；
    2. 列表派生：在声明为列表/泛型列表时，从同节点的泛型标量入参派生基础类型并映射到列表；
    3. 回退声明：若仍无结果且显式声明为非泛型类型，则采用声明类型；
    4. 连线推断：结合图模型与入边推断类型，必要时覆盖“字符串/字符串列表”这类低可信结果；
    5. 动态类型：节点定义提供了非泛型的 `dynamic_port_type` 时采用之；
    6. 无法推断：若以上路径均失败，则返回空字符串，由调用方决定是否跳过该端口的类型设置。
    """
    parameter_value_text = param_values_by_name.get(mapped_name, "")
    effective_input_type: Optional[str] = None

    # 1) 优先：从参数值推断
    param_text = get_non_empty_str(parameter_value_text)
    if param_text:
        effective_input_type = infer_type_from_value(param_text)
        effective_input_type = upgrade_to_list_type(declared_input_type, effective_input_type)

    # 2) 额外：列表类型从同节点泛型标量入参派生
    if (
        not effective_input_type
        and isinstance(declared_input_type, str)
        and is_list_like_type_name(declared_input_type)
    ):
        if node_def is not None:
            for peer_name, peer_type in (getattr(node_def, "input_types", {}) or {}).items():
                if not isinstance(peer_name, str) or not isinstance(peer_type, str):
                    continue
                if get_non_empty_str(peer_type) != "泛型":
                    continue
                peer_value_text_raw = param_values_by_name.get(peer_name, "")
                peer_value_text = get_non_empty_str(peer_value_text_raw)
                if not peer_value_text:
                    continue
                base_candidate_type = infer_type_from_value(peer_value_text)
                upgraded_type = upgrade_to_list_type(declared_input_type, base_candidate_type)
                upgraded_text = get_non_empty_str(upgraded_type)
                # 仅当确实发生了“标量→列表”的提升时才采纳该结果，避免将基础标量或泛型原样返回
                if (
                    upgraded_text
                    and upgraded_text != get_non_empty_str(base_candidate_type)
                    and not is_generic_type_name(upgraded_text)
                ):
                    effective_input_type = upgraded_text
                    break

    # 3) 回退：定义/连线/动态/默认
    declared_input_text = get_non_empty_str(declared_input_type)
    if not effective_input_type and declared_input_text and not is_generic_type_name(declared_input_text):
        effective_input_type = declared_input_text

    edge_inferred_type: Optional[str] = infer_input_type_from_edges(
        mapped_name,
        node,
        graph_model,
        executor,
        log_callback,
        edge_lookup=edge_lookup,
    )
    if _should_override_with_edge_type(effective_input_type, edge_inferred_type):
        if get_non_empty_str(effective_input_type):
            executor.log(
                f"[端口类型/输入] 连线推断类型 '{edge_inferred_type}' 覆盖值推断 '{effective_input_type}'（端口 '{mapped_name}'）",
                log_callback,
            )
        effective_input_type = edge_inferred_type
    edge_text = get_non_empty_str(edge_inferred_type)
    if not effective_input_type and edge_text:
        effective_input_type = edge_text
    if not effective_input_type and node_def is not None:
        dynamic_input_type_text = get_non_empty_str(getattr(node_def, "dynamic_port_type", ""))
        if dynamic_input_type_text and not is_generic_type_name(dynamic_input_type_text):
            effective_input_type = dynamic_input_type_text
    if not effective_input_type:
        effective_input_type = ""

    executor.log(
        f"[端口类型/输入] 端口 '{mapped_name}' 显式='{declared_input_type}' → 选择='{effective_input_type}'",
        log_callback,
    )
    return effective_input_type


def infer_effective_output_type(
    executor: EditorExecutorWithViewport,
    node: NodeModel,
    node_def,
    mapped_name: str,
    declared_output_type: str,
    graph_model: GraphModel,
    edge_lookup,
    log_callback,
) -> str:
    """根据 overrides、本节点输入、出边及动态类型综合推断输出端口的目标类型。

    推断顺序：
    0. GraphModel.metadata 覆盖：优先读取 `metadata['port_type_overrides']` 中的端口类型；
    1. 本节点输入常量：通过 `infer_output_type_from_self_inputs` 从本节点输入推导输出类型；
    2. 出边推断：结合图变量规则与出边信息，按 `infer_output_type_from_edges` 计算类型；
    3. 回退声明/动态：无结果时优先声明类型，其次 `dynamic_port_type`；
    4. 无法推断：若仍无结果则返回空字符串，由调用方决定是否跳过该端口的类型设置。
    """
    target_type: Optional[str] = None

    # 0) 优先：GraphModel.metadata 中的端口类型覆盖
    port_type_overrides: Dict[str, Dict[str, str]] = build_port_type_overrides(graph_model)
    override_text = resolve_port_type_with_overrides(
        overrides_mapping=port_type_overrides,
        node_identifier=getattr(node, "id", ""),
        port_name=mapped_name,
    )
    if isinstance(override_text, str):
        target_type = get_non_empty_str(override_text) or override_text

    # 1) 基于本节点输入常量派生
    if (not get_non_empty_str(target_type)) and isinstance(declared_output_type, str):
        derived_type_text = infer_output_type_from_self_inputs(
            node,
            node_def,
            declared_output_type,
            executor,
            log_callback,
        )
        derived_text = get_non_empty_str(derived_type_text)
        if derived_text:
            target_type = derived_text

    # 2) 次优：从出边连线推断（含图变量规则）
    if not get_non_empty_str(target_type):
        inferred_from_edges = infer_output_type_from_edges(
            mapped_name,
            node,
            graph_model,
            executor,
            log_callback,
            edge_lookup=edge_lookup,
        )
        inferred_text = get_non_empty_str(inferred_from_edges)
        if inferred_text:
            target_type = inferred_text

    # 3) 回退：定义/动态（不再默认回退为“字符串”）
    if not get_non_empty_str(target_type):
        declared_output_text = get_non_empty_str(declared_output_type)
        if declared_output_text and not is_generic_type_name(declared_output_text):
            target_type = declared_output_text
        elif node_def is not None:
            dynamic_output_type_text = get_non_empty_str(getattr(node_def, "dynamic_port_type", ""))
            if dynamic_output_type_text and not is_generic_type_name(dynamic_output_type_text):
                target_type = dynamic_output_type_text
            else:
                target_type = ""
        else:
            target_type = ""
        if get_non_empty_str(target_type):
            executor.log(
                f"[端口类型] 输出端口 '{mapped_name}' 使用回退类型 '{target_type}'",
                log_callback,
            )
        else:
            executor.log(
                f"[端口类型] 输出端口 '{mapped_name}' 无法推断具体类型：跳过该端口类型设置",
                log_callback,
            )

    return target_type


__all__ = [
    "infer_effective_input_type",
    "infer_effective_output_type",
]


