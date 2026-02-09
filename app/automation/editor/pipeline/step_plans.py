# -*- coding: utf-8 -*-
"""
步骤计划表（step_type → plan）。

职责：
- 收敛步骤类型解析、计划表查找；
- 将 step_type 绑定到“仅做业务委托”的 handler；
- 为编排层提供统一的 plan 字段（视口同步/预热/缓存失效/回放记录开关）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from PIL import Image

from app.automation.config.signal_config import execute_bind_signal
from app.automation.config.struct_config import execute_bind_struct
from app.automation.editor import editor_connect, editor_nodes
from engine.graph.models.graph_model import GraphModel

from ..automation_step_types import (
    GRAPH_STEP_CREATE_NODE,
    GRAPH_STEP_CONNECT,
    GRAPH_STEP_CREATE_AND_CONNECT,
    GRAPH_STEP_CONNECT_MERGED,
    GRAPH_STEP_CONFIG_NODE_MERGED,
    GRAPH_STEP_SET_PORT_TYPES_MERGED,
    GRAPH_STEP_ADD_VARIADIC_INPUTS,
    GRAPH_STEP_ADD_DICT_PAIRS,
    GRAPH_STEP_ADD_BRANCH_OUTPUTS,
    GRAPH_STEP_CONFIG_BRANCH_OUTPUTS,
    GRAPH_STEP_BIND_SIGNAL,
    GRAPH_STEP_BIND_STRUCT,
)


StepHandler = Callable[
    [
        Any,
        Dict[str, Any],
        GraphModel,
        Optional[Callable[[str], None]],
        Optional[Callable[[], None]],
        Optional[Callable[[], bool]],
        Optional[Callable[[Image.Image, Optional[dict]], None]],
    ],
    bool,
]


@dataclass(frozen=True)
class StepExecutionPlan:
    """单个 graph_* 步骤类型的执行计划。"""

    handler: StepHandler
    requires_connect_prepare: bool = False
    invalidate_cache_on_success: bool = False
    requires_view_sync: bool = True
    mutates_layout: bool = False
    # 关键步骤输入输出落盘（用于回归定位/离线复现）
    record_replay_io: bool = False


def _handle_graph_create_node(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_nodes.execute_create_node(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_connect(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    # 连续连接：允许跨多个 graph_connect 步骤复用同一帧 screenshot + 节点/端口快照，
    # 避免“每连一条边就全图 OCR/模板匹配一次”。
    reuse_context = executor.begin_connect_chain_step()
    if not reuse_context:
        reuse_context = {
            "node_snapshots": {},
            "screenshot": None,
        }
    else:
        reuse_context.setdefault("node_snapshots", {})
        reuse_context.setdefault("screenshot", None)

    ok = editor_connect.execute_connect(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
        reuse_context=reuse_context,
    )
    executor.complete_connect_chain_step(reuse_context, ok)
    return bool(ok)


def _handle_graph_create_and_connect(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    created = editor_nodes.execute_create_node(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )
    if not created:
        return False
    # create 成功后强制失效视觉缓存，避免下一步复用旧识别结果
    from app.automation.vision import invalidate_cache

    invalidate_cache()
    return editor_connect.execute_connect(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_connect_merged(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    node1_id = todo_item.get("node1_id")
    node2_id = todo_item.get("node2_id")
    edges_list = todo_item.get("edges") or []
    if not node1_id or not node2_id or not isinstance(edges_list, list) or len(edges_list) == 0:
        executor.log("✗ 合并连线步骤缺少必要信息", log_callback)
        return False

    from app.automation import capture as editor_capture
    from app.automation.input import win_input

    orig_x, orig_y = editor_capture.get_cursor_pos()
    # 合并连线：允许在多条边之间复用同一帧 screenshot + 节点/端口快照，
    # 即使画面已出现连线变化也不强制重新识别（避免重复 OCR/模板匹配，并避免鼠标遮挡导致识别漂移）。
    # 若执行过程中发生视口调度/视口变化，底层 `editor_connect` 会显式清理 reuse_context，
    # 触发重新截图与重新定位，保证跨视口场景仍然可靠。
    reuse_context = executor.begin_connect_chain_step()
    if not reuse_context:
        reuse_context = {
            "node_snapshots": {},
            "screenshot": None,
        }
    else:
        reuse_context.setdefault("node_snapshots", {})
        reuse_context.setdefault("screenshot", None)

    ok_all = True
    for edge_info in edges_list:
        edge_payload = {
            "type": "graph_connect",
            "src_node": node1_id,
            "dst_node": node2_id,
            "src_port": edge_info.get("src_port"),
            "dst_port": edge_info.get("dst_port"),
            "edge_id": edge_info.get("edge_id"),
        }
        ok = editor_connect.execute_connect(
            executor,
            edge_payload,
            graph_model,
            log_callback,
            pause_hook,
            allow_continue,
            visual_callback,
            reuse_context=reuse_context,
        )
        if not ok:
            ok_all = False
            break

    win_input.move_mouse_absolute(int(orig_x), int(orig_y))
    executor.complete_connect_chain_step(reuse_context, ok_all)
    return ok_all


def _handle_graph_config_node_merged(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_config_node_merged(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_set_port_types(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_set_port_types_merged(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_add_variadic_inputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_add_variadic_inputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_add_dict_pairs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_add_dict_pairs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_add_branch_outputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_add_branch_outputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_config_branch_outputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_config_branch_outputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_bind_signal(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return execute_bind_signal(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_bind_struct(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return execute_bind_struct(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


STEP_PLANS: Dict[str, StepExecutionPlan] = {
    GRAPH_STEP_CREATE_NODE: StepExecutionPlan(
        handler=_handle_graph_create_node,
        mutates_layout=True,
        record_replay_io=True,
    ),
    GRAPH_STEP_CONNECT: StepExecutionPlan(
        handler=_handle_graph_connect,
        requires_connect_prepare=True,
        mutates_layout=True,
        record_replay_io=True,
    ),
    GRAPH_STEP_CREATE_AND_CONNECT: StepExecutionPlan(
        handler=_handle_graph_create_and_connect,
        mutates_layout=True,
        record_replay_io=True,
    ),
    GRAPH_STEP_CONNECT_MERGED: StepExecutionPlan(
        handler=_handle_graph_connect_merged,
        requires_connect_prepare=True,
        mutates_layout=True,
        record_replay_io=True,
    ),
    GRAPH_STEP_CONFIG_NODE_MERGED: StepExecutionPlan(
        handler=_handle_graph_config_node_merged,
        requires_connect_prepare=True,
        record_replay_io=True,
    ),
    GRAPH_STEP_SET_PORT_TYPES_MERGED: StepExecutionPlan(
        handler=_handle_graph_set_port_types,
        requires_connect_prepare=True,
        record_replay_io=True,
    ),
    GRAPH_STEP_ADD_VARIADIC_INPUTS: StepExecutionPlan(
        handler=_handle_graph_add_variadic_inputs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_ADD_DICT_PAIRS: StepExecutionPlan(
        handler=_handle_graph_add_dict_pairs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_ADD_BRANCH_OUTPUTS: StepExecutionPlan(
        handler=_handle_graph_add_branch_outputs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_CONFIG_BRANCH_OUTPUTS: StepExecutionPlan(
        handler=_handle_graph_config_branch_outputs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_BIND_SIGNAL: StepExecutionPlan(
        handler=_handle_graph_bind_signal,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_BIND_STRUCT: StepExecutionPlan(
        handler=_handle_graph_bind_struct,
        requires_connect_prepare=True,
    ),
}


def resolve_step_plan(step_type_raw: object, executor, log_callback=None) -> tuple[str, Optional[StepExecutionPlan]]:
    """仅做类型解析与 plan 查找，不触发任何副作用。"""
    step_type = str(step_type_raw or "")
    step_plan = STEP_PLANS.get(step_type or "")
    if step_plan is None:
        executor.log(f"✗ 不支持的步骤类型: {step_type}", log_callback)
    return step_type, step_plan


