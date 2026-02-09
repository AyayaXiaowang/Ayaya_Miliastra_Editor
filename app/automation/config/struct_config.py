from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

from app.automation.editor import editor_nodes
from app.automation.editor import executor_utils as _exec_utils
from app.automation.editor.node_snapshot import NodePortsSnapshotCache
from app.automation.editor.executor_protocol import EditorExecutorWithViewport
from app.automation.ports.port_picker import pick_settings_center_by_recognition
from app.automation.ports.settings_locator import find_icon_center_on_row
from app.automation import capture as editor_capture
from engine.graph.common import STRUCT_NAME_PORT_NAME
from engine.graph.models.graph_model import GraphModel


def _resolve_struct_name_text(
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    node_id: str,
) -> str:
    """解析用于搜索选择的结构体名称文本。

    优先顺序：
    - Todo detail_info["struct_name"]
    - GraphModel.get_node_struct_binding(node_id)["struct_name"]
    - Todo detail_info["struct_id"]（作为兜底）
    - GraphModel.get_node_struct_binding(node_id)["struct_id"]（作为兜底）
    """
    struct_name_field = todo_item.get("struct_name")
    if isinstance(struct_name_field, str):
        struct_name_text = struct_name_field.strip()
        if struct_name_text:
            return struct_name_text

    binding = None
    get_binding = getattr(graph_model, "get_node_struct_binding", None)
    if callable(get_binding):
        binding = get_binding(node_id)

    if isinstance(binding, dict):
        raw_struct_name = binding.get("struct_name")
        if isinstance(raw_struct_name, str):
            struct_name_text = raw_struct_name.strip()
            if struct_name_text:
                return struct_name_text

    struct_id_field = todo_item.get("struct_id")
    if isinstance(struct_id_field, str):
        struct_id_text = struct_id_field.strip()
        if struct_id_text:
            return struct_id_text

    if isinstance(binding, dict):
        raw_struct_id = binding.get("struct_id")
        if isinstance(raw_struct_id, str):
            struct_id_text = raw_struct_id.strip()
            if struct_id_text:
                return struct_id_text
        if raw_struct_id is not None:
            struct_id_text = str(raw_struct_id)
            if struct_id_text:
                return struct_id_text

    return ""


def _find_struct_name_row_port(
    ports: list,
) -> Optional[Any]:
    """在一步式识别端口列表中找到“结构体名”这一行对应的端口对象（用于定位行 y）。"""
    matched: list[Any] = []
    for port_obj in ports or []:
        port_name = str(getattr(port_obj, "name_cn", "") or "")
        if port_name != STRUCT_NAME_PORT_NAME:
            continue
        matched.append(port_obj)
    if not matched:
        return None
    matched.sort(key=lambda p: int(getattr(p, "center", (0, 10**9))[1]))
    return matched[0]


def _pick_settings_center_for_struct_row(
    *,
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    ports: list,
    log_callback,
) -> Tuple[int, int]:
    """定位“结构体名”行的 Settings 图标中心点（editor 坐标系）。"""
    struct_row_port = _find_struct_name_row_port(list(ports or []))
    if struct_row_port is not None:
        row_center_y = int(getattr(struct_row_port, "center", (0, 0))[1])
        port_center = (
            int(getattr(struct_row_port, "center", (0, 0))[0]),
            int(getattr(struct_row_port, "center", (0, 0))[1]),
        )
        desired_side = str(getattr(struct_row_port, "side", "left") or "left")
        settings_x, settings_y = pick_settings_center_by_recognition(
            executor,
            screenshot,
            node_bbox,
            int(row_center_y),
            y_tolerance=14,
            desired_side=desired_side,
            ports_list=list(ports or []),
        )
        if (int(settings_x), int(settings_y)) != (0, 0):
            return (int(settings_x), int(settings_y))

        # 回退：行内模板搜索（与端口类型设置保持一致的几何与阈值策略）
        settings_x, settings_y = find_icon_center_on_row(
            executor,
            screenshot,
            node_bbox,
            port_center,
            desired_side,
            str(executor.node_settings_template_path),
            y_tolerance=12,
            log_callback=log_callback,
        )
        return (int(settings_x), int(settings_y))

    # 若无法定位“结构体名”行端口：回退为“节点内最上方的 Settings 模板命中”
    node_left, node_top, node_width, node_height = (
        int(node_bbox[0]),
        int(node_bbox[1]),
        int(node_bbox[2]),
        int(node_bbox[3]),
    )
    candidates = editor_capture.match_template_candidates(
        screenshot,
        str(executor.node_settings_template_path),
        search_region=(node_left, node_top, node_width, node_height),
        threshold=0.80,
    )
    if not candidates:
        return (0, 0)
    # 选择 y 最小（最靠上）的候选；y 相同则选置信度更高者
    candidates.sort(key=lambda item: (int(item[1]), -float(item[2])))
    best_center_x, best_center_y, _best_score = candidates[0]
    return (int(best_center_x), int(best_center_y))


def execute_bind_struct(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """执行“配置结构体”步骤：定位节点 → 点击“结构体名”行的 Settings 图标 → 在弹出的搜索框内输入结构体名并选择 → 点击画布空白收尾。"""
    node_id_field = todo_item.get("node_id")
    node_id = str(node_id_field or "")
    if not node_id or node_id not in graph_model.nodes:
        executor.log("✗ 结构体绑定步骤缺少节点或节点不存在", log_callback)
        return False

    node = graph_model.nodes[node_id]
    struct_name_text = _resolve_struct_name_text(todo_item, graph_model, node_id)
    if not struct_name_text:
        executor.log("✗ 结构体绑定步骤缺少可用的 struct_name / struct_id 文本", log_callback)
        return False

    # 1) 确保节点进入视口
    executor.ensure_program_point_visible(
        node.pos[0],
        node.pos[1],
        margin_ratio=0.10,
        max_steps=8,
        pan_step_pixels=420,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        graph_model=graph_model,
        force_pan_if_inside_margin=False,
    )

    # 2) 截图并定位节点 bbox + 端口列表
    snapshot = NodePortsSnapshotCache(executor, node, log_callback)
    if not snapshot.ensure(reason="结构体绑定-初始截图", require_bbox=True):
        return False
    screenshot = snapshot.screenshot
    node_bbox = snapshot.node_bbox
    ports_list = list(getattr(snapshot, "ports", []) or [])

    node_left, node_top, node_width, node_height = (
        int(node_bbox[0]),
        int(node_bbox[1]),
        int(node_bbox[2]),
        int(node_bbox[3]),
    )

    # 3) 找到“结构体名”行的 Settings 图标并点击
    settings_center_editor_x, settings_center_editor_y = _pick_settings_center_for_struct_row(
        executor=executor,
        screenshot=screenshot,
        node_bbox=(node_left, node_top, node_width, node_height),
        ports=ports_list,
        log_callback=log_callback,
    )
    if (int(settings_center_editor_x), int(settings_center_editor_y)) == (0, 0):
        executor.log("✗ 未能定位结构体行的 Settings 图标", log_callback)
        return False

    settings_center_screen_x, settings_center_screen_y = executor.convert_editor_to_screen_coords(
        int(settings_center_editor_x),
        int(settings_center_editor_y),
    )
    executor.log(
        f"[结构体绑定] 点击 Settings: editor=({int(settings_center_editor_x)},{int(settings_center_editor_y)}) "
        f"screen=({int(settings_center_screen_x)},{int(settings_center_screen_y)})",
        log_callback,
    )

    if visual_callback is not None:
        rects = [
            {
                "bbox": (node_left, node_top, node_width, node_height),
                "color": (120, 200, 255),
                "label": f"目标节点: {node.title}",
            }
        ]
        circles = [
            {
                "center": (int(settings_center_editor_x), int(settings_center_editor_y)),
                "radius": 6,
                "color": (0, 220, 0),
                "label": "Settings 点击",
            }
        ]
        visual_callback(screenshot, {"rects": rects, "circles": circles})

    _exec_utils.click_and_verify(
        executor,
        int(settings_center_screen_x),
        int(settings_center_screen_y),
        "[结构体绑定] 点击 Settings",
        log_callback,
    )
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    # 4) 在弹出的搜索框中输入结构体名并选择（复用“类型搜索框”交互）
    executor.log(f"[结构体绑定] 选择结构体: '{struct_name_text}'", log_callback)
    ok = editor_nodes.click_type_search_and_choose(
        executor,
        struct_name_text,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    if not ok:
        executor.log(f"✗ 未能在搜索框中选择结构体 '{struct_name_text}'", log_callback)
        return False

    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    # 5) 点击画布空白位置收尾
    blank_start_editor_x = int(node_left + node_width // 2)
    blank_start_editor_y = int(node_top + node_height // 2)
    blank_start_screen_x, blank_start_screen_y = executor.convert_editor_to_screen_coords(
        blank_start_editor_x,
        blank_start_editor_y,
    )
    _exec_utils.click_canvas_blank_near_screen_point(
        executor,
        int(blank_start_screen_x),
        int(blank_start_screen_y),
        log_prefix="[结构体绑定] 结构体选择完成，",
        wait_seconds=0.1,
        wait_message="等待 0.10 秒（结构体设置完成后画布状态稳定）",
        log_callback=log_callback,
        visual_callback=visual_callback,
    )

    snapshot.mark_dirty(require_bbox=True)
    return True



