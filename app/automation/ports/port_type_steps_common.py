from __future__ import annotations

"""port_type_steps_common: 输入/输出侧端口类型设置的通用 UI 小流程。

职责:
- 在已有 `NodePortsSnapshotCache` 的前提下，围绕“按端口名定位端口中心并执行类型设置 UI 流程”
  提供可复用骨架，避免在输入/输出步骤模块中复制粘贴同一套逻辑；
- 统一 `typed_side_once` 与 `NodePortsSnapshotCache.mark_dirty` 的行为，让
  “同侧仅设置一次” 与 “首个数据端口保留帧缓存” 规则只在一处维护。

说明:
- 本模块只关心 UI 层面的共性步骤：快照获取 → 端口定位 → 调用回调 → 脏标记与 typed_side_once；
  具体“如何计算目标类型”与“是否需要为该端口设置类型”仍由调用方在各自模块中决定。
"""

from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from engine.graph.models.graph_model import NodeModel

from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.core.node_snapshot import NodePortsSnapshotCache
from app.automation.ports.port_type_ui_steps import locate_port_center, is_first_data_port


def apply_type_setting_with_port_center(
    executor: EditorExecutorWithViewport,
    snapshot_cache: NodePortsSnapshotCache,
    node: NodeModel,
    node_bbox: Tuple[int, int, int, int],
    mapped_name: str,
    side: str,
    is_operation_node: bool,
    typed_side_once: Dict[str, bool],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    *,
    ensure_reason: str,
    locate_failed_message: str,
    apply_ui_callback: Callable[[Image.Image, List, Tuple[int, int]], bool],
) -> bool:
    """在快照缓存基础上，为单个端口执行“定位中心 + 调用 UI 设置回调”的通用流程。

    返回:
        - False: 表示快照获取失败（caller 通常需要整体中止本侧类型设置流程）；
        - True:  表示本端口的处理已完成（无论是否真正成功设置类型），可以继续后续端口。
    """
    if not isinstance(mapped_name, str) or mapped_name == "":
        executor.log("[端口类型] 端口名为空，跳过类型设置流程", log_callback)
        return True

    if not snapshot_cache.ensure(reason=ensure_reason, require_bbox=False):
        return False

    screenshot = snapshot_cache.screenshot
    current_ports = snapshot_cache.ports

    port_center = locate_port_center(
        executor,
        screenshot,
        node,
        node_bbox,
        mapped_name,
        side=side,
        ports_list=current_ports,
        log_callback=log_callback,
    )

    if port_center == (0, 0):
        executor.log(locate_failed_message, log_callback)
        return True

    success = apply_ui_callback(screenshot, current_ports, port_center)

    keep_cached_frame = is_first_data_port(node, mapped_name, side)
    snapshot_cache.mark_dirty(
        require_bbox=False,
        keep_cached_frame=keep_cached_frame,
    )

    if success and is_operation_node:
        typed_side_once[side] = True

    return True


__all__ = [
    "apply_type_setting_with_port_center",
]


