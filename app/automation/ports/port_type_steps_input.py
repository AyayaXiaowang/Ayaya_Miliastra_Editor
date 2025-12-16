from __future__ import annotations

"""port_type_steps_input: 输入侧端口类型设置步骤。

职责：
- 在已有 `NodePortsSnapshotCache` 的前提下，遍历左侧“数据”端口行；
- 结合节点定义、参数值、图模型入边与字典别名推断输入端口的目标类型；
- 调用通用 UI 步骤模块完成端口类型设置，并根据运算节点策略控制“同侧仅设置一次”。

依赖：
- 纯推断逻辑：`port_type_effective.infer_effective_input_type`；
- 字典键/值推断：`port_type_inference.infer_dict_key_value_types_for_input`；
- UI 定位与设置：`port_type_ui_steps.locate_port_center/apply_port_type_via_ui` 与
  `dict_port_type_steps.set_dict_port_type_with_settings`。
"""

from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.nodes.port_index_mapper import map_port_index_to_name

from app.automation.editor.executor_protocol import (
    EditorExecutorProtocol,
    EditorExecutorWithViewport,
    AutomationStepContext,
)
from app.automation.editor.node_snapshot import NodePortsSnapshotCache
from app.automation.ports._ports import is_data_input_port
from app.automation.ports.port_type_effective import infer_effective_input_type
from app.automation.ports.port_type_inference import (
    infer_dict_key_value_types_for_input,
    is_generic_type_name,
)
from app.automation.ports.port_type_steps_common import apply_type_setting_with_port_center
from app.automation.ports.port_type_ui_steps import apply_port_type_via_ui


def process_input_ports_type_setting(
    executor: EditorExecutorWithViewport,
    node: NodeModel,
    node_def,
    node_bbox: Tuple[int, int, int, int],
    snapshot_cache: NodePortsSnapshotCache,
    params_list: list,
    graph_model: GraphModel,
    edge_lookup,
    is_operation_node: bool,
    typed_side_once: Dict[str, bool],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    """处理输入侧端口类型设置。

    仅在 params_list 非空时执行，为 "泛型/未声明/动态类型" 端口选择类型。

    Returns:
        成功返回 True
    """
    if not isinstance(params_list, list) or len(params_list) == 0:
        executor.log("[端口类型/输入] 无参数项：跳过输入侧类型设置", log_callback)
        return True

    step_ctx = AutomationStepContext(
        log_callback=log_callback,
        visual_callback=visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )

    # 构造参数名→值映射，并据此确定“本次步骤期望处理的输入端口集合”。
    param_values_by_name: Dict[str, str] = {}
    for param in params_list:
        param_name = str(param.get("param_name") or "")
        param_value = str(param.get("param_value") or "")
        if param_name:
            param_values_by_name[param_name] = param_value
    # 当提供了 params_list 时，仅对其中出现的输入端口执行类型设置，
    # 避免在 Todo 未声明的端口上额外尝试设置类型（例如未在步骤中列出的“字典”端口）。
    target_input_names = set(param_values_by_name.keys())

    if not snapshot_cache.ensure(reason="输入类型设置/遍历", require_bbox=False):
        return False

    left_data_rows = [
        port_snapshot
        for port_snapshot in snapshot_cache.ports
        if is_data_input_port(port_snapshot)
    ]

    # 遍历左侧数据端口行
    for port_in in left_data_rows:
        if is_operation_node and typed_side_once.get("left", False):
            executor.log("[端口类型/输入] 运算节点：同侧仅需设置一次，跳过剩余输入端口", log_callback)
            break

        port_index = getattr(port_in, "index", None)
        mapped_name = None
        if isinstance(port_index, int):
            mapped_name = map_port_index_to_name(node.title, "left", port_index)

        if not isinstance(mapped_name, str) or mapped_name == "":
            executor.log("[端口类型] 无法映射输入端口名称，跳过该项", log_callback)
            continue

        # 若步骤明确给出了需要处理的输入端口集合，则严格尊重该集合；
        # 未出现在 params_list 中的输入端口在本次步骤中一律跳过。
        if target_input_names and mapped_name not in target_input_names:
            executor.log(
                f"[端口类型/输入] 步骤参数未包含端口 '{mapped_name}'，跳过该端口类型设置",
                log_callback,
            )
            continue

        # 获取显式声明类型
        declared_input_type = ""
        if node_def is not None:
            declared_input_type = str(node_def.input_types.get(mapped_name, "") or "")

        # 字典端口：仅当能够从连线和别名字典类型中推断出明确的键/值类型时，才执行类型设置；
        # 否则直接跳过该端口的类型设置，避免随意回退为"字符串/字符串"。
        declared_text = declared_input_type.strip() if isinstance(declared_input_type, str) else ""
        if declared_text.endswith("字典"):
            dict_types = infer_dict_key_value_types_for_input(
                node,
                mapped_name,
                graph_model,
                executor,
                log_callback,
                edge_lookup=edge_lookup,
            )
            if dict_types is None:
                executor.log(
                    "[端口类型/字典] 未能从连线与别名字典类型中推断键/值类型，跳过字典端口类型设置",
                    log_callback,
                )
                continue

            key_type, value_type = dict_types
            alias_text = f"{key_type}_{value_type}字典"

            def apply_dict_type(
                screenshot_inner: Image.Image,
                ports_inner: List,
                port_center_inner: Tuple[int, int],
            ) -> bool:
                return apply_port_type_via_ui(
                    executor,
                    screenshot_inner,
                    node_bbox,
                    port_center_inner,
                    mapped_name,
                    alias_text,
                    "left",
                    ports_inner,
                    step_ctx,
                )

            ok_dict = apply_type_setting_with_port_center(
                executor=executor,
                snapshot_cache=snapshot_cache,
                node=node,
                node_bbox=node_bbox,
                mapped_name=mapped_name,
                side="left",
                is_operation_node=is_operation_node,
                typed_side_once=typed_side_once,
                log_callback=log_callback,
                visual_callback=visual_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
                ensure_reason="输入类型设置/字典",
                locate_failed_message="✗ 未能定位输入端口（字典）",
                apply_ui_callback=apply_dict_type,
            )
            if not ok_dict:
                return False
            # 无论成功与否，已尝试字典专用流程，不再走通用单一类型设置
            continue

        # 若已为非泛型具体类型，跳过
        if declared_input_type and not is_generic_type_name(declared_input_type):
            executor.log(
                f"[端口类型/输入] 跳过非泛型声明端口 '{mapped_name}' (声明='{declared_input_type}')",
                log_callback,
            )
            continue

        effective_in_type = infer_effective_input_type(
            executor,
            node,
            node_def,
            mapped_name,
            declared_input_type,
            param_values_by_name,
            graph_model,
            edge_lookup,
            log_callback,
        )
        if not isinstance(effective_in_type, str) or effective_in_type.strip() == "":
            executor.log(
                f"[端口类型/输入] 端口 '{mapped_name}' 无法推断具体类型：跳过该端口类型设置",
                log_callback,
            )
            continue

        def apply_input_type(
            screenshot_inner: Image.Image,
            ports_inner: List,
            port_center_inner: Tuple[int, int],
        ) -> bool:
            return apply_port_type_via_ui(
                executor,
                screenshot_inner,
                node_bbox,
                port_center_inner,
                mapped_name,
                effective_in_type,
                "left",
                ports_inner,
                step_ctx,
            )

        ok_input = apply_type_setting_with_port_center(
            executor=executor,
            snapshot_cache=snapshot_cache,
            node=node,
            node_bbox=node_bbox,
            mapped_name=mapped_name,
            side="left",
            is_operation_node=is_operation_node,
            typed_side_once=typed_side_once,
            log_callback=log_callback,
            visual_callback=visual_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            ensure_reason="输入类型设置",
            locate_failed_message=f"✗ 未能定位输入端口: {mapped_name}",
            apply_ui_callback=apply_input_type,
        )
        if not ok_input:
            return False

    return True


__all__ = [
    "process_input_ports_type_setting",
]


