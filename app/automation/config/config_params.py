# -*- coding: utf-8 -*-
"""
config_params: 节点参数配置功能（重构版本）
将庞大的execute_config_node_merged拆分为清晰的步骤函数。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, List
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor.executor_protocol import EditorExecutorWithViewport, AutomationStepContext
from app.automation.editor import executor_utils as _exec_utils
from app.automation.input.common import sleep_seconds
from app.automation.ports._type_utils import infer_type_from_value
from engine.graph.models.graph_model import GraphModel

from app.automation.config.config_node_steps import (
    visualize_node_and_ports,
    log_port_candidates_debug,
    locate_input_port,
    handle_boolean_param,
    handle_enum_param,
    find_warning_region_for_port,
    handle_regular_param_by_port_gap,
    find_vertical_context_for_input_port,
    handle_regular_param_fallback,
)
from app.automation.config.config_params_helpers import filter_screen_input_candidates, format_candidates_brief
from app.automation.config.enum_dropdown_utils import normalize_dropdown_option_text
from app.automation.ports.vector3_input_handler import input_vector3_by_geometry
from app.automation.editor.node_snapshot import NodePortsSnapshotCache


def _resolve_level_variable_name_from_variable_id(variable_id: str) -> str:
    variable_id_text = str(variable_id or "").strip()
    if not variable_id_text:
        return ""
    if not variable_id_text.startswith("var_"):
        return ""

    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    schema_view = get_default_level_variable_schema_view()
    payload = schema_view.get_all_variables().get(variable_id_text)
    if not isinstance(payload, dict):
        return ""

    name_value = payload.get("variable_name", payload.get("name", ""))
    if not isinstance(name_value, str):
        return ""
    return name_value.strip()


def _normalize_custom_variable_name_for_execution(*, node_title: str, port_name: str, raw_value: str) -> str:
    """将旧格式的关卡变量标识（var_xxx）归一化为中文 variable_name，以便真实执行阶段输入更直观。"""
    from engine.graph.common import VARIABLE_NAME_PORT_NAME

    if str(port_name or "").strip() != VARIABLE_NAME_PORT_NAME:
        return raw_value

    excluded_titles = {
        "设置节点图变量",
        "获取节点图变量",
        "设置局部变量",
        "获取局部变量",
    }
    if str(node_title or "").strip() in excluded_titles:
        return raw_value

    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return raw_value

    # 1) 直接为 variable_id（典型旧数据）
    resolved = _resolve_level_variable_name_from_variable_id(raw_text)
    if resolved:
        return resolved

    # 2) 兼容旧展示格式：name (var_xxx)
    if "(" in raw_text and raw_text.endswith(")"):
        left_text = raw_text[: raw_text.rfind("(")].strip()
        inside = raw_text[raw_text.rfind("(") + 1 : -1].strip()
        resolved_inside = _resolve_level_variable_name_from_variable_id(inside)
        if resolved_inside:
            return resolved_inside
        if left_text:
            return left_text

    return raw_value


def execute_config_node_merged(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """节点参数配置主函数（重构版）。
    
    功能：为节点的输入端口注入参数值
    - 布尔类型：点击两次切换
    - 三维向量：OCR识别X/Y/Z标签或几何法定位
    - 普通类型：基于端口间距几何定位输入框并输入（不依赖 Warning）；失败则直接返回 False 暴露问题（不做端口偏移兜底）
    
    Args:
        executor: 执行器实例
        todo_item: 待办项，包含 node_id 和 params 列表
        graph_model: 图模型
        log_callback: 日志回调
        pause_hook: 暂停钩子
        allow_continue: 继续判断钩子
        visual_callback: 可视化回调
    
    Returns:
        成功返回True，失败返回False
    """
    # ========== 1. 初始化与准备 ==========
    node_id = todo_item.get("node_id")
    params_list = todo_item.get("params") or []
    
    if not node_id or node_id not in graph_model.nodes:
        executor.log("✗ 参数配置缺少节点或节点不存在", log_callback)
        return False
    
    node = graph_model.nodes[node_id]

    step_ctx = AutomationStepContext(
        log_callback=log_callback,
        visual_callback=visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    
    # 确保节点在可见区域
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
    
    snapshot = NodePortsSnapshotCache(executor, node, log_callback)
    if not snapshot.ensure(reason="参数配置初始截图", require_bbox=True):
        return False
    node_bbox = snapshot.node_bbox

    # 固定“端口快照”：参数配置过程中保持使用首帧识别到的端口位置，避免输入过程导致每帧识别漂移
    stable_node_bbox = tuple(int(v) for v in node_bbox)
    stable_ports_snapshot = list(snapshot.ports)
    stable_frame_token = getattr(snapshot, "frame_token", None)
    stable_input_candidates_text = format_candidates_brief(
        filter_screen_input_candidates(stable_ports_snapshot, "data")
    )
    executor.log(
        f"[参数配置] 固定端口快照: frame_token={stable_frame_token} bbox={stable_node_bbox} ports={len(stable_ports_snapshot)}",
        log_callback,
    )
    executor.log(f"[参数配置] 固定端口候选(输入-从上到下): {stable_input_candidates_text}", log_callback)
    
    # 可视化：节点图区域、所有节点、当前节点端口
    visualize_node_and_ports(executor, snapshot.screenshot, node_bbox, node.title, visual_callback)
    
    # 输出节点信息
    node_def = executor.get_node_def_for_model(node)
    executor.log(f"[参数配置] 节点 '{node.title}'({node.id}) 参数项数={len(params_list)}", log_callback)
    
    # 无参数时跳过
    if len(params_list) == 0:
        executor.log("[参数配置] 无参数项：跳过类型识别与设置（请使用独立步骤 graph_set_port_types_merged）", log_callback)
        return True
    
    # 记录已配置的端口中心（避免重复使用）
    configured_centers: List[tuple[int, int]] = []
    warning_region_cache: dict[tuple[int, str], object] = {}
    warning_match_cache: dict[tuple[int, tuple[int, int, int, int]], object] = {}
    
    # ========== 2. 遍历处理每个参数 ==========
    for param_index, param in enumerate(params_list):
        # 检查暂停/终止
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            executor.log("用户终止/暂停，放弃参数配置", log_callback)
            return False

        # 参数配置阶段不再每个参数都触发“节点 bbox/端口识别”刷新（会导致 1~2s 的额外停顿），
        # 仅获取一张当前窗口截图用于可视化与模板匹配；端口定位与上下文统一使用首帧快照。
        screenshot = None
        window_title = getattr(executor, "window_title", None)
        if isinstance(window_title, str) and window_title:
            screenshot = editor_capture.capture_window_strict(window_title)
            if screenshot is None:
                screenshot = editor_capture.capture_window(window_title)

        if not screenshot:
            # 离线/测试执行器：复用首帧快照中的 screenshot（不刷新 bbox/端口）
            if not snapshot.ensure(reason=f"参数配置#{param_index}", require_bbox=False):
                return False
            screenshot = snapshot.screenshot

        node_bbox = stable_node_bbox
        frame_id = id(screenshot)
        
        param_name = str(param.get("param_name") or "")
        param_value = str(param.get("param_value") or "")
        param_value = _normalize_custom_variable_name_for_execution(
            node_title=str(getattr(node, "title", "") or ""),
            port_name=param_name,
            raw_value=param_value,
        )
        
        if not param_name:
            continue
        
        # 获取端口类型，若节点未声明则回退至值推断
        port_type = "泛型"
        if node_def is not None:
            has_explicit_type = False
            if param_name in (node_def.input_types or {}):
                port_type = node_def.input_types[param_name]
                has_explicit_type = True
        
        # 推断有效类型（用于布尔/枚举/向量等判定）
        if (not port_type) or (isinstance(port_type, str) and (port_type == "泛型" or port_type.startswith("泛型"))):
            effective_type = infer_type_from_value(param_value)
        else:
            effective_type = port_type

        executor.log(
            f"[参数配置] 处理输入端口: '{param_name}' 原始值='{param_value}' 声明类型='{port_type or ''}' → 有效类型='{effective_type}'",
            log_callback,
        )

        is_enum_type = isinstance(effective_type, str) and ("枚举" in effective_type)
        enum_index_for_param: Optional[int] = None
        options_for_param: Optional[List[str]] = None
        if is_enum_type and node_def is not None:
            input_enum_options = getattr(node_def, "input_enum_options", {}) or {}
            options_any = input_enum_options.get(param_name)
            if isinstance(options_any, list):
                options_for_param = [str(value) for value in options_any]
                desired_value_normalized = normalize_dropdown_option_text(param_value)
                for option_position, option_text in enumerate(options_for_param, start=1):
                    if normalize_dropdown_option_text(option_text) == desired_value_normalized:
                        enum_index_for_param = int(option_position)
                        break

        is_boolean_type = isinstance(effective_type, str) and ("布尔" in effective_type)
        
        # 跳过实体类型
        if isinstance(effective_type, str) and ("实体" in effective_type):
            executor.log(f"· 跳过实体类型输入端口『{param_name}』", log_callback)
            continue
        
        # 输出调试信息
        log_port_candidates_debug(executor, node, param_name, 'data', log_callback)
        
        # 定位输入端口
        port_center = locate_input_port(
            executor,
            screenshot,
            node,
            node_bbox,
            param_name,
            'data',
            configured_centers,
            log_callback,
            ports_snapshot=stable_ports_snapshot,
        )
        
        if port_center is None:
            return False
        
        # 记录已使用端口
        configured_centers.append((int(port_center[0]), int(port_center[1])))
        
        # 可视化：当前端口
        if visual_callback is not None:
            rects = [
                {
                    "bbox": (int(node_bbox[0]), int(node_bbox[1]), int(node_bbox[2]), int(node_bbox[3])),
                    "color": (120, 200, 255),
                    "label": f"参数: {param_name}",
                }
            ]
            circles = [
                {
                    "center": (int(port_center[0]), int(port_center[1])),
                    "radius": 6,
                    "color": (255, 200, 0),
                    "label": "",
                }
            ]
            visual_callback(screenshot, {"rects": rects, "circles": circles})

        # ========== 3. 处理普通/向量/枚举/布尔参数 ==========
        width, height = screenshot.size
        executor.log(f"[截图] 当前画面={width}x{height}", log_callback)

        open_click_editor = (int(port_center[0]) + 50, int(port_center[1]) + 25)

        def _get_warning_region_for_special_types() -> Optional[tuple]:
            """仅在三维向量/枚举/布尔需要时计算 Warning 搜索区域（避免普通参数日志误导与无谓开销）。"""
            cache_key = (frame_id, param_name)
            cached_region = warning_region_cache.get(cache_key, None)
            if cached_region is False:
                return None
            if cached_region is not None:
                return cached_region  # type: ignore[return-value]
            warning_region_result = find_warning_region_for_port(
                executor,
                screenshot,
                node_bbox,
                port_center,
                param_name,
                log_callback,
                ports_snapshot=stable_ports_snapshot,
            )
            warning_region_cache[cache_key] = warning_region_result if warning_region_result is not None else False
            return warning_region_result  # type: ignore[return-value]
        
        # 优先处理布尔/枚举/向量等特殊类型
        if is_boolean_type:
            # 将布尔视为“双选枚举”：True 视为第 1 项，False 视为第 2 项
            value_text = str(param_value or "").strip()
            value_lower = value_text.lower()
            is_true = (value_text == "是") or (value_lower == "true") or (value_text == "1")
            bool_enum_index = 1 if is_true else 2
            desired_bool_text = "是" if is_true else "否"

            ok_bool_enum = handle_enum_param(
                executor,
                screenshot,
                None,
                bool_enum_index,
                pause_hook,
                allow_continue,
                log_callback,
                visual_callback,
                log_prefix="[参数配置/布尔]",
                enum_options=["是", "否"],
                desired_text=desired_bool_text,
                open_click_editor=open_click_editor,
            )

            if not ok_bool_enum:
                warning_region_result = _get_warning_region_for_special_types()
                search_region = None
                if warning_region_result is not None:
                    search_region = warning_region_result[0]

            if not ok_bool_enum and search_region is not None:
                executor.log(
                    "[参数配置/布尔] 端口偏移展开失败，改用 Warning 展开重试（仍按OCR点击选项）",
                    log_callback,
                )
                ok_bool_enum = handle_enum_param(
                    executor,
                    screenshot,
                    search_region,
                    bool_enum_index,
                    pause_hook,
                    allow_continue,
                    log_callback,
                    visual_callback,
                    log_prefix="[参数配置/布尔]",
                    enum_options=["是", "否"],
                    desired_text=desired_bool_text,
                    open_click_editor=None,
                )

            if not ok_bool_enum:
                return False

            snapshot.mark_dirty(require_bbox=True)
            continue

        # 尝试通过Warning模板处理（向量 / 普通参数 / 显式枚举）
        is_vector = isinstance(effective_type, str) and ("三维向量" in effective_type)

        # 优先：枚举类型统一走“下拉识别 + OCR 点击”
        if is_enum_type:
            enum_index_to_use = int(enum_index_for_param) if enum_index_for_param is not None else 1
            ok_enum = handle_enum_param(
                executor,
                screenshot,
                None,
                enum_index_to_use,
                pause_hook,
                allow_continue,
                log_callback,
                visual_callback,
                enum_options=list(options_for_param) if isinstance(options_for_param, list) else None,
                desired_text=str(param_value or ""),
                open_click_editor=open_click_editor,
            )

            if not ok_enum:
                warning_region_result = _get_warning_region_for_special_types()
                search_region = None
                if warning_region_result is not None:
                    search_region = warning_region_result[0]

            if not ok_enum and search_region is not None:
                executor.log(
                    "[参数配置/枚举] 枚举选择未完成，改用 Warning 展开重试（仍按OCR点击选项）",
                    log_callback,
                )
                ok_enum = handle_enum_param(
                    executor,
                    screenshot,
                    search_region,
                    enum_index_to_use,
                    pause_hook,
                    allow_continue,
                    log_callback,
                    visual_callback,
                    enum_options=list(options_for_param) if isinstance(options_for_param, list) else None,
                    desired_text=str(param_value or ""),
                    open_click_editor=None,
                )
            if not ok_enum:
                return False
            snapshot.mark_dirty(require_bbox=True)
            continue
        
        if is_vector:
            warning_region_result = _get_warning_region_for_special_types()
            if warning_region_result is None:
                return False
            search_region, current_port, _next_port = warning_region_result
            if search_region is None or current_port is None:
                return False
            # 三维向量：先尝试Warning几何法
            match_cache_key = (frame_id, tuple(int(v) for v in search_region))
            cached_match = warning_match_cache.get(match_cache_key, None)
            if cached_match is False:
                warning_match = None
            elif cached_match is not None:
                warning_match = cached_match  # type: ignore[assignment]
            else:
                warning_match = editor_capture.match_template(
                    screenshot,
                    str(executor.node_warning_template_path),
                    search_region=search_region
                )
                warning_match_cache[match_cache_key] = warning_match if warning_match else False
            
            if warning_match:
                # Warning命中：使用几何法
                match_x, match_y, match_w, match_h, conf = warning_match
                warning_bbox = (match_x, match_y, match_w, match_h, conf)
                current_port_bbox = tuple(int(v) for v in getattr(current_port, 'bbox', (0, 0, 0, 0)))
                
                ok = input_vector3_by_geometry(
                    executor,
                    screenshot,
                    warning_bbox,
                    node_bbox,
                    current_port_bbox,
                    param_value,
                    step_ctx,
                )
                
                if ok:
                    # 优先使用统一的执行器等待工具；若当前环境未注入 `_exec_utils`，则退化为固定 sleep，避免 NameError
                    if "_exec_utils" in globals():
                        _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
                    else:
                        sleep_seconds(0.1)
                    snapshot.mark_dirty(require_bbox=True)
                    continue
            
            # 未命中：Fallback处理（会重新截图并使用OCR）
            ok_fallback = handle_regular_param_fallback(
                executor, port_center, param_value, effective_type, node_bbox, current_port,
                pause_hook, allow_continue, log_callback, visual_callback
            )
            if not ok_fallback:
                return False
            snapshot.mark_dirty(require_bbox=True)
            continue
        
        # 普通参数：优先使用“端口间距法”定位输入框；失败则直接失败暴露（不做端口偏移 fallback）
        port_context = find_vertical_context_for_input_port(
            executor,
            screenshot,
            node_bbox,
            port_center,
            param_name,
            log_callback,
            ports_snapshot=stable_ports_snapshot,
            log_prefix="[参数配置/非布尔]",
        )
        if port_context is None:
            return False
        current_port, next_port = port_context

        ok_by_ports = handle_regular_param_by_port_gap(
            executor,
            screenshot,
            node_bbox,
            current_port,
            next_port,
            param_value,
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            log_prefix="[参数配置/非布尔]",
        )

        if not ok_by_ports:
            return False

        snapshot.mark_dirty(require_bbox=True)
        continue
    
    # 所有参数处理完毕
    return True

