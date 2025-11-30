# -*- coding: utf-8 -*-
"""
config_params: 节点参数配置功能（重构版本）
将庞大的execute_config_node_merged拆分为清晰的步骤函数。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, List
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.ports._type_utils import infer_type_from_value
from engine.graph.models.graph_model import GraphModel

from app.automation.config.config_node_steps import (
    visualize_node_and_ports,
    log_port_candidates_debug,
    locate_input_port,
    handle_boolean_param,
    find_warning_region_for_port,
    handle_regular_param_with_warning,
    handle_regular_param_fallback,
)
from app.automation.ports.vector3_input_handler import input_vector3_by_geometry
from app.automation.core.node_snapshot import NodePortsSnapshotCache


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
    - 普通类型：查找Warning图标点击后输入
    
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
        executor._log("✗ 参数配置缺少节点或节点不存在", log_callback)
        return False
    
    node = graph_model.nodes[node_id]
    
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
    
    # 可视化：节点图区域、所有节点、当前节点端口
    visualize_node_and_ports(executor, snapshot.screenshot, node_bbox, node.title, visual_callback)
    
    # 输出节点信息
    node_def = executor._get_node_def_for_model(node)
    executor._log(f"[参数配置] 节点 '{node.title}'({node.id}) 参数项数={len(params_list)}", log_callback)
    
    # 无参数时跳过
    if len(params_list) == 0:
        executor._log("[参数配置] 无参数项：跳过类型识别与设置（请使用独立步骤 graph_set_port_types_merged）", log_callback)
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
            executor._log("用户终止/暂停，放弃参数配置", log_callback)
            return False

        if not snapshot.ensure(reason=f"参数配置#{param_index}", require_bbox=True):
            return False
        screenshot = snapshot.screenshot
        node_bbox = snapshot.node_bbox
        frame_id = id(screenshot)
        
        param_name = str(param.get("param_name") or "")
        param_value = str(param.get("param_value") or "")
        
        if not param_name:
            continue
        
        # 获取端口类型，若节点未声明则回退至值推断
        port_type = "泛型"
        if node_def is not None:
            try:
                port_type = node_def.get_port_type(param_name, is_input=True)
            except ValueError as exc:
                executor._log(f"[参数配置] 输入端口 '{param_name}' 未声明类型：{exc} -> 使用值推断", log_callback)
        
        # 推断有效类型（用于布尔/向量等判定）
        if (not port_type) or (isinstance(port_type, str) and (port_type == "泛型" or port_type.startswith("泛型"))):
            effective_type = infer_type_from_value(param_value)
        else:
            effective_type = port_type
        
        executor._log(
            f"[参数配置] 处理输入端口: '{param_name}' 原始值='{param_value}' 声明类型='{port_type or ''}' → 有效类型='{effective_type}'",
            log_callback
        )
        
        # 跳过实体类型
        if isinstance(effective_type, str) and ("实体" in effective_type):
            executor._log(f"· 跳过实体类型输入端口『{param_name}』", log_callback)
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
            ports_snapshot=snapshot.ports
        )
        
        if port_center is None:
            return False
        
        # 记录已使用端口
        configured_centers.append((int(port_center[0]), int(port_center[1])))
        
        # 可视化：当前端口
        if visual_callback is not None:
            rects = [{
                'bbox': (int(node_bbox[0]), int(node_bbox[1]), int(node_bbox[2]), int(node_bbox[3])),
                'color': (120, 200, 255),
                'label': f"参数: {param_name}"
            }]
            circles = [{
                'center': (int(port_center[0]), int(port_center[1])),
                'radius': 6,
                'color': (255, 200, 0),
                'label': ''
            }]
            visual_callback(screenshot, {'rects': rects, 'circles': circles})
        
        # ========== 3. 处理布尔参数 ==========
        if isinstance(effective_type, str) and ("布尔" in effective_type):
            should_continue = handle_boolean_param(executor, port_center, param_name, param_value, log_callback)
            snapshot.mark_dirty(require_bbox=False)
            if not should_continue:
                continue  # 布尔处理完毕，跳到下一个参数
        
        # ========== 4. 处理普通/向量参数 ==========
        width, height = screenshot.size
        executor._log(f"[截图] 当前画面={width}x{height}", log_callback)
        
        # 查找Warning搜索区域
        cache_key = (frame_id, param_name)
        cached_region = warning_region_cache.get(cache_key, None)
        if cached_region is False:
            warning_region_result = None
        elif cached_region is not None:
            warning_region_result = cached_region  # type: ignore[assignment]
        else:
            warning_region_result = find_warning_region_for_port(
                executor,
                screenshot,
                node_bbox,
                port_center,
                param_name,
                log_callback,
                ports_snapshot=snapshot.ports,
            )
            warning_region_cache[cache_key] = warning_region_result if warning_region_result is not None else False

        if warning_region_result is None:
            return False
        
        search_region, current_port, next_port = warning_region_result
        
        # 尝试通过Warning模板处理
        is_vector = isinstance(effective_type, str) and ("三维向量" in effective_type)
        
        if is_vector:
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
                    executor, screenshot, warning_bbox, node_bbox, current_port_bbox,
                    param_value, pause_hook, allow_continue, log_callback, visual_callback
                )
                
                if ok:
                    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
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
        
        # 普通参数：先尝试Warning，失败则Fallback
        ok_warning = handle_regular_param_with_warning(
            executor, screenshot, search_region, param_value,
            pause_hook, allow_continue, log_callback, visual_callback
        )
        
        if ok_warning:
            snapshot.mark_dirty(require_bbox=True)
            continue  # 成功，处理下一个参数
        
        # Warning未命中，使用Fallback
        ok_fallback = handle_regular_param_fallback(
            executor, port_center, param_value, effective_type, node_bbox, current_port,
            pause_hook, allow_continue, log_callback, visual_callback
        )
        
        if not ok_fallback:
            return False
        
        snapshot.mark_dirty(require_bbox=True)
    
    # 所有参数处理完毕
    return True

