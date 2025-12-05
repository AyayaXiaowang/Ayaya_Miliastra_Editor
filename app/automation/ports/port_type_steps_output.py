from __future__ import annotations

"""port_type_steps_output: 输出侧端口类型设置步骤。

职责：
- 在已有 `NodePortsSnapshotCache` 的前提下，遍历右侧“数据”端口行；
- 结合节点定义、图模型出边与覆盖表推断输出端口的目标类型；
- 调用通用 UI 步骤模块完成端口类型设置，并根据运算节点策略控制“同侧仅设置一次”。

依赖：
- 纯推断逻辑：`port_type_effective.infer_effective_output_type`；
- 覆盖表构建：`port_type_inference.build_port_type_overrides`；
- UI 定位与设置：`port_type_ui_steps.locate_port_center/apply_port_type_via_ui`。
"""

from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from engine.graph.models.graph_model import GraphModel, NodeModel

from app.automation.core.executor_protocol import (
    EditorExecutorProtocol,
    EditorExecutorWithViewport,
    AutomationStepContext,
)
from app.automation.core.node_snapshot import NodePortsSnapshotCache
from app.automation.ports._ports import get_port_category
from app.automation.ports.port_type_effective import infer_effective_output_type
from app.automation.ports.port_type_inference import is_generic_type_name
from app.automation.ports.port_type_steps_common import apply_type_setting_with_port_center
from app.automation.ports.port_type_ui_steps import apply_port_type_via_ui
from engine.nodes.port_index_mapper import map_port_index_to_name


def process_output_ports_type_setting(
    executor: EditorExecutorWithViewport,
    node: NodeModel,
    node_def,
    node_bbox: Tuple[int, int, int, int],
    snapshot_cache: NodePortsSnapshotCache,
    graph_model: GraphModel,
    edge_lookup,
    is_operation_node: bool,
    typed_side_once: Dict[str, bool],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    """处理输出侧端口类型设置。

    为所有 "泛型/未声明/动态类型" 的数据端口选择类型。

    Returns:
        成功返回 True
    """
    if not snapshot_cache.ensure(reason="输出类型设置", require_bbox=False):
        return False

    step_ctx = AutomationStepContext(
        log_callback=log_callback,
        visual_callback=visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )

    right_data_rows = [
        port_snapshot
        for port_snapshot in snapshot_cache.ports
        if get_port_category(port_snapshot) == "data_output"
    ]

    for port_out in right_data_rows:
        if is_operation_node and typed_side_once.get("right", False):
            executor.log("[端口类型/输出] 运算节点：同侧仅需设置一次，跳过剩余输出端口", log_callback)
            break

        port_index = getattr(port_out, "index", None)
        mapped_name = None
        if isinstance(port_index, int):
            mapped_name = map_port_index_to_name(node.title, "right", port_index)

        if not isinstance(mapped_name, str) or mapped_name == "":
            executor.log("[端口类型] 无法映射输出端口名称，跳过该项", log_callback)
            continue

        # 获取显式声明类型
        declared_output_type = ""
        if node_def is not None:
            declared_output_type = str(node_def.output_types.get(mapped_name, "") or "")

        # 若已为非泛型具体类型，跳过
        if declared_output_type and not is_generic_type_name(declared_output_type):
            executor.log(
                f"[端口类型/输出] 跳过非泛型声明端口 '{mapped_name}' (声明='{declared_output_type}')",
                log_callback,
            )
            continue

        target_type = infer_effective_output_type(
            executor,
            node,
            node_def,
            mapped_name,
            declared_output_type,
            graph_model,
            edge_lookup,
            log_callback,
        )

        def apply_output_type(
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
                target_type,
                "right",
                ports_inner,
                step_ctx,
            )

        ok_output = apply_type_setting_with_port_center(
            executor=executor,
            snapshot_cache=snapshot_cache,
            node=node,
            node_bbox=node_bbox,
            mapped_name=mapped_name,
            side="right",
            is_operation_node=is_operation_node,
            typed_side_once=typed_side_once,
            log_callback=log_callback,
            visual_callback=visual_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            ensure_reason="输出类型：定位端口",
            locate_failed_message=f"✗ 未能定位输出端口: {mapped_name}",
            apply_ui_callback=apply_output_type,
        )
        if not ok_output:
            return False

    return True


__all__ = [
    "process_output_ports_type_setting",
]


