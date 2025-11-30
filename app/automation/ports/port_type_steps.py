# -*- coding: utf-8 -*-
"""
port_type_steps: 端口类型设置步骤拆分
将 execute_set_port_types_merged 的庞大逻辑拆分为可测试的小步骤。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, List, Callable
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core import executor_utils as _exec_utils
from app.automation.core import editor_nodes
from app.automation.core.node_snapshot import NodePortsSnapshotCache
from app.automation.ports._ports import (
    normalize_kind_text,
    is_non_connectable_kind,
    is_data_input_port,
)
from app.automation.ports.port_picker import (
    pick_settings_center_by_recognition,
    pick_port_center_for_node,
)
from app.automation.ports.settings_locator import find_icon_center_on_row
from engine.graph.models.graph_model import GraphModel, NodeModel
from app.automation.core.executor_protocol import EditorExecutorWithViewport

from app.automation.ports.port_type_inference import (
    is_generic_type_name,
    upgrade_to_list_type,
    infer_input_type_from_edges,
    infer_output_type_from_edges,
    infer_output_type_from_self_inputs,
    infer_dict_key_value_types_for_input,
    parse_typed_dict_alias,
    BASE_TO_LIST_MAP,
    LIST_TO_BASE_MAP,
    build_port_type_overrides,
)
from engine.utils.graph.graph_utils import is_flow_port_name
from app.automation.ports.dict_port_type_steps import set_dict_port_type_with_settings


def _is_first_data_input_port(node: NodeModel, port_name: str) -> bool:
    """判断给定端口是否为该节点左侧第一个“数据”输入端口。"""
    if not isinstance(port_name, str) or port_name == "":
        return False
    all_input_names: List[str] = [port.name for port in (node.inputs or [])]
    data_input_names: List[str] = [
        name for name in all_input_names if not is_flow_port_name(name)
    ]
    if port_name not in data_input_names:
        return False
    return int(data_input_names.index(port_name)) == 0


def _is_first_data_output_port(node: NodeModel, port_name: str) -> bool:
    """判断给定端口是否为该节点右侧第一个“数据”输出端口。"""
    if not isinstance(port_name, str) or port_name == "":
        return False
    all_output_names: List[str] = [port.name for port in (node.outputs or [])]
    data_output_names: List[str] = [
        name for name in all_output_names if not is_flow_port_name(name)
    ]
    if port_name not in data_output_names:
        return False
    return int(data_output_names.index(port_name)) == 0


def set_port_type_with_settings(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    target_type: str,
    side: str,
    ports_list: list,
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    """通过Settings按钮设置端口类型。
    
    优先使用识别到的Settings行，失败则回退到模板搜索。
    
    Args:
        executor: 执行器实例
        screenshot: 当前截图
        node_bbox: 节点边界框
        port_center: 端口中心坐标
        port_name: 端口名称
        target_type: 目标类型名称
        side: 'left' 或 'right'
        ports_list: 端口列表（用于识别）
        log_callback: 日志回调
        visual_callback: 可视化回调
    
    Returns:
        成功返回True
    """
    # 优先使用识别到的Settings行
    settings_x, settings_y = pick_settings_center_by_recognition(
        executor, screenshot, node_bbox, int(port_center[1]), y_tolerance=14,
        desired_side=side, ports_list=ports_list
    )
    
    if (settings_x, settings_y) == (0, 0):
        # 回退到模板搜索
        settings_x, settings_y = find_icon_center_on_row(
            executor,
            screenshot,
            node_bbox,
            port_center,
            side,
            str(executor.node_settings_template_path),
            y_tolerance=12,
            log_callback=log_callback,
        )
        if (settings_x, settings_y) == (0, 0):
            executor._log(f"[端口类型/{side}] 未发现设置按钮，跳过端口 '{port_name}'", log_callback)
            return False
    
    # 点击Settings按钮
    screen_x, screen_y = executor.convert_editor_to_screen_coords(settings_x, settings_y)
    executor._log(f"[端口类型/{side}] 点击设置按钮: editor=({settings_x},{settings_y}) screen=({screen_x},{screen_y})", log_callback)
    _exec_utils.click_and_verify(executor, screen_x, screen_y, f"[端口类型/{side}] 点击设置按钮", log_callback)
    
    _exec_utils.log_wait_if_needed(executor, 0.5, "等待 0.50 秒", log_callback, pause_hook, allow_continue)
    
    # 硬性防护：禁止将端口类型设置为"泛型家族"
    if is_generic_type_name(target_type):
        executor._log(f"[端口类型/{side}] 计算得到泛型类型 '{target_type}'，出于安全跳过设置（永不将类型设置为泛型）", log_callback)
        return False
    
    # 设置类型
    executor._log(f"[端口类型/{side}] 设置类型: '{target_type}'", log_callback)
    editor_nodes.click_type_search_and_choose(
        executor,
        target_type,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    
    _exec_utils.log_wait_if_needed(executor, 0.5, "等待 0.50 秒", log_callback, pause_hook, allow_continue)
    
    return True


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
    
    仅在params_list非空时执行，为"泛型/未声明/动态类型"端口选择类型。
    
    Returns:
        成功返回True
    """
    if not isinstance(params_list, list) or len(params_list) == 0:
        executor._log("[端口类型/输入] 无参数项：跳过输入侧类型设置", log_callback)
        return True
    
    # 构造参数名→值映射
    param_values_by_name: Dict[str, str] = {}
    for param in params_list:
        param_name = str(param.get("param_name") or "")
        param_value = str(param.get("param_value") or "")
        if param_name:
            param_values_by_name[param_name] = param_value
    
    if not snapshot_cache.ensure(reason="输入类型设置/遍历", require_bbox=False):
        return False
    
    left_data_rows = [p for p in snapshot_cache.ports if is_data_input_port(p)]
    
    # 导入端口索引映射
    from engine.nodes.port_index_mapper import map_port_index_to_name
    from app.automation.ports._type_utils import infer_type_from_value
    
    def _should_override_with_edge_type(current: Optional[str], candidate: Optional[str]) -> bool:
        if not isinstance(candidate, str) or candidate.strip() == "":
            return False
        if is_generic_type_name(candidate):
            return False
        if not current:
            return True
        current_text = str(current)
        if current_text.strip() == "":
            return True
        # 仅在值推断回落到“字符串/字符串列表”时被视为低可信，允许连线类型覆盖
        if current_text.startswith("字符串") and candidate != current_text:
            return True
        return False

    # 遍历左侧数据端口行
    for port_in in left_data_rows:
        if is_operation_node and typed_side_once.get('left', False):
            executor._log("[端口类型/输入] 运算节点：同侧仅需设置一次，跳过剩余输入端口", log_callback)
            break
        
        port_index = getattr(port_in, 'index', None)
        mapped_name = None
        if isinstance(port_index, int):
            mapped_name = map_port_index_to_name(node.title, 'left', port_index)
        
        if not isinstance(mapped_name, str) or mapped_name == "":
            executor._log("[端口类型] 无法映射输入端口名称，跳过该项", log_callback)
            continue

        is_first_left_data_port = _is_first_data_input_port(node, mapped_name)
        
        # 获取显式声明类型
        declared_input_type = ""
        if node_def is not None:
            declared_input_type = str(node_def.input_types.get(mapped_name, "") or "")

        # 字典端口：仅当能够从连线和别名字典类型中推断出明确的键/值类型时，才执行类型设置；
        # 否则直接跳过该端口的类型设置，避免随意回退为"字符串/字符串"。
        is_dict_port = False
        if isinstance(declared_input_type, str):
            declared_text = declared_input_type.strip()
            if declared_text.endswith("字典"):
                is_dict_port = True

        if is_dict_port:
            dict_types = infer_dict_key_value_types_for_input(
                node,
                mapped_name,
                graph_model,
                executor,
                log_callback,
                edge_lookup=edge_lookup,
            )
            if dict_types is None:
                executor._log(
                    "[端口类型/字典] 未能从连线与别名字典类型中推断键/值类型，跳过字典端口类型设置",
                    log_callback,
                )
                continue

            key_type, value_type = dict_types

            if not snapshot_cache.ensure(reason="输入类型设置/字典", require_bbox=False):
                return False
            screenshot = snapshot_cache.screenshot
            current_ports = snapshot_cache.ports

            from engine.utils.graph.graph_utils import is_flow_port_name

            names_all = [p.name for p in (node.inputs or [])]
            names_filtered = [n for n in names_all if not is_flow_port_name(n)]
            planned_ordinal = (
                int(names_filtered.index(mapped_name)) if mapped_name in names_filtered else None
            )

            port_center = pick_port_center_for_node(
                executor,
                screenshot,
                node_bbox,
                mapped_name,
                want_output=False,
                expected_kind="data",
                log_callback=log_callback,
                ordinal_fallback_index=planned_ordinal,
                ports_list=current_ports,
            )
            if port_center == (0, 0):
                executor._log("✗ 未能定位输入端口（字典）", log_callback)
                continue

            success_dict = set_dict_port_type_with_settings(
                executor,
                screenshot,
                node_bbox,
                port_center,
                mapped_name,
                key_type,
                value_type,
                "left",
                current_ports,
                log_callback,
                visual_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
            )

            snapshot_cache.mark_dirty(
                require_bbox=False,
                keep_cached_frame=is_first_left_data_port,
            )
            if success_dict and is_operation_node:
                typed_side_once["left"] = True
            # 无论成功与否，已尝试字典专用流程，不再走通用单一类型设置
            continue

        # 若已为非泛型具体类型，跳过
        if declared_input_type and not is_generic_type_name(declared_input_type):
            executor._log(
                f"[端口类型/输入] 跳过非泛型声明端口 '{mapped_name}' (声明='{declared_input_type}')",
                log_callback,
            )
            continue
        
        param_val = param_values_by_name.get(mapped_name, "")
        
        # 计算有效类型
        effective_in_type: Optional[str] = None

        # 1) 优先：从参数值推断
        if isinstance(param_val, str) and param_val != "":
            effective_in_type = infer_type_from_value(param_val)
            effective_in_type = upgrade_to_list_type(declared_input_type, effective_in_type)
        
        # 2) 额外：列表类型从同节点泛型标量入参派生
        if (not effective_in_type) and isinstance(declared_input_type, str) and (("列表" in declared_input_type) or (declared_input_type.strip() == "泛型列表")):
            if node_def is not None:
                for peer_name, peer_type in (getattr(node_def, "input_types", {}) or {}).items():
                    if not isinstance(peer_name, str) or not isinstance(peer_type, str):
                        continue
                    if peer_type.strip() != "泛型":
                        continue
                    peer_val = str(param_values_by_name.get(peer_name, "") or "")
                    if not peer_val:
                        continue
                    base_candidate = infer_type_from_value(peer_val)
                    if isinstance(base_candidate, str) and base_candidate in BASE_TO_LIST_MAP:
                        effective_in_type = BASE_TO_LIST_MAP[base_candidate]
                        break
        
        # 3) 回退：定义/连线/动态/默认
        if not effective_in_type and (declared_input_type and not is_generic_type_name(declared_input_type)):
            effective_in_type = declared_input_type
        edge_inferred_type: Optional[str] = infer_input_type_from_edges(
            mapped_name,
            node,
            graph_model,
            executor,
            log_callback,
            edge_lookup=edge_lookup,
        )
        if _should_override_with_edge_type(effective_in_type, edge_inferred_type):
            if isinstance(effective_in_type, str) and effective_in_type.strip():
                executor._log(
                    f"[端口类型/输入] 连线推断类型 '{edge_inferred_type}' 覆盖值推断 '{effective_in_type}'（端口 '{mapped_name}'）",
                    log_callback,
                )
            effective_in_type = edge_inferred_type
        if not effective_in_type and edge_inferred_type:
            effective_in_type = edge_inferred_type
        if not effective_in_type and node_def is not None:
            dyn_t = str(getattr(node_def, "dynamic_port_type", "") or "")
            if dyn_t and not is_generic_type_name(dyn_t):
                effective_in_type = dyn_t
        if not effective_in_type:
            effective_in_type = "字符串"
        
        executor._log(
            f"[端口类型/输入] 端口 '{mapped_name}' 显式='{declared_input_type}' → 选择='{effective_in_type}'",
            log_callback
        )
        
        # 定位端口
        if not snapshot_cache.ensure(reason="输入类型设置", require_bbox=False):
            return False
        screenshot = snapshot_cache.screenshot
        current_ports = snapshot_cache.ports
        
        from engine.utils.graph.graph_utils import is_flow_port_name
        names_all = [p.name for p in (node.inputs or [])]
        names_filtered = [n for n in names_all if not is_flow_port_name(n)]
        planned_ordinal = int(names_filtered.index(mapped_name)) if mapped_name in names_filtered else None
        
        port_center = pick_port_center_for_node(
            executor,
            screenshot,
            node_bbox,
            mapped_name,
            want_output=False,
            expected_kind='data',
            log_callback=log_callback,
            ordinal_fallback_index=planned_ordinal,
            ports_list=current_ports,
        )
        
        if port_center == (0, 0):
            executor._log(f"✗ 未能定位输入端口: {mapped_name}", log_callback)
            continue

        # 设置类型：
        # - 对普通数据类型，直接使用通用 Settings 流程；
        # - 对“别名字典”类型（如“字符串_GUID列表字典”），改走字典专用流程，
        #   先将端口类型切换为“字典”，再在字典面板中分别设置键/值类型。
        is_alias_dict, key_type_alias, value_type_alias = parse_typed_dict_alias(effective_in_type)
        if is_alias_dict:
            success = set_dict_port_type_with_settings(
                executor,
                screenshot,
                node_bbox,
                port_center,
                mapped_name,
                key_type_alias,
                value_type_alias,
                "left",
                current_ports,
                log_callback,
                visual_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
            )
        else:
            success = set_port_type_with_settings(
                executor,
                screenshot,
                node_bbox,
                port_center,
                mapped_name,
                effective_in_type,
                'left',
                current_ports,
                log_callback,
                visual_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
            )

        snapshot_cache.mark_dirty(
            require_bbox=False,
            keep_cached_frame=is_first_left_data_port,
        )
        
        if success and is_operation_node:
            typed_side_once['left'] = True
    
    return True


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
    
    为所有"泛型/未声明/动态类型"的数据端口选择类型。
    
    Returns:
        成功返回True
    """
    if not snapshot_cache.ensure(reason="输出类型设置", require_bbox=False):
        return False
    
    right_data_rows = [
        p for p in snapshot_cache.ports
        if getattr(p, 'side', '') == 'right'
        and not is_non_connectable_kind(getattr(p, 'kind', ''))
        and normalize_kind_text(getattr(p, 'kind', '')) == 'data'
    ]
    
    from engine.nodes.port_index_mapper import map_port_index_to_name

    # 统一读取一次 GraphModel 中的端口类型覆盖信息（如来自节点图代码中的类型注解）。
    port_type_overrides: Dict[str, Dict[str, str]] = build_port_type_overrides(graph_model)
    
    for port_out in right_data_rows:
        if is_operation_node and typed_side_once.get('right', False):
            executor._log("[端口类型/输出] 运算节点：同侧仅需设置一次，跳过剩余输出端口", log_callback)
            break
        
        port_index = getattr(port_out, 'index', None)
        mapped_name = None
        if isinstance(port_index, int):
            mapped_name = map_port_index_to_name(node.title, 'right', port_index)
        
        if not isinstance(mapped_name, str) or mapped_name == "":
            executor._log("[端口类型] 无法映射输出端口名称，跳过该项", log_callback)
            continue

        is_first_right_data_port = _is_first_data_output_port(node, mapped_name)
        
        # 获取显式声明类型
        declared_output_type = ""
        if node_def is not None:
            declared_output_type = str(node_def.output_types.get(mapped_name, "") or "")
        
        # 若已为非泛型具体类型，跳过
        if declared_output_type and not is_generic_type_name(declared_output_type):
            executor._log(f"[端口类型/输出] 跳过非泛型声明端口 '{mapped_name}' (声明='{declared_output_type}')", log_callback)
            continue
        
        # 计算目标类型
        target_type: Optional[str] = None

        # 0) 优先：若 GraphModel.metadata 中存在端口类型覆盖信息，则直接采用
        if port_type_overrides:
            node_overrides = port_type_overrides.get(node.id)
            if isinstance(node_overrides, dict):
                override_raw = node_overrides.get(mapped_name)
                if isinstance(override_raw, str):
                    override_text = override_raw.strip()
                    if override_text and (not is_generic_type_name(override_text)):
                        target_type = override_text

        # 1) 基于本节点输入常量派生
        if (not isinstance(target_type, str) or target_type == "") and isinstance(declared_output_type, str):
            derived = infer_output_type_from_self_inputs(node, node_def, declared_output_type, executor, log_callback)
            if isinstance(derived, str) and derived:
                target_type = derived
        
        # 3) 次优：从出边连线推断（含图变量规则）
        if not isinstance(target_type, str) or target_type == "":
            target_type = infer_output_type_from_edges(
                mapped_name,
                node,
                graph_model,
                executor,
                log_callback,
                edge_lookup=edge_lookup,
            )
        
        # 4) 回退：定义/动态/默认字符串
        if not isinstance(target_type, str) or target_type == "":
            if declared_output_type and not is_generic_type_name(declared_output_type):
                target_type = declared_output_type
            elif node_def is not None:
                dyn_txt = str(getattr(node_def, "dynamic_port_type", "") or "")
                if dyn_txt and not is_generic_type_name(dyn_txt):
                    target_type = dyn_txt
                else:
                    target_type = "字符串"
            else:
                target_type = "字符串"
            executor._log(f"[端口类型] 输出端口 '{mapped_name}' 使用回退类型 '{target_type}'", log_callback)
        
        # 定位端口
        if not snapshot_cache.ensure(reason="输出类型：定位端口", require_bbox=False):
            return False
        screenshot1 = snapshot_cache.screenshot
        current_ports = snapshot_cache.ports
        
        port_center_out = pick_port_center_for_node(
            executor,
            screenshot1,
            node_bbox,
            mapped_name,
            want_output=True,
            expected_kind='data',
            log_callback=log_callback,
            ordinal_fallback_index=None,
            ports_list=current_ports,
        )
        
        if port_center_out == (0, 0):
            executor._log(f"✗ 未能定位输出端口: {mapped_name}", log_callback)
            continue

        # 若目标类型为“别名字典”（如“字符串_GUID列表字典”），则改走字典专用设置流程：
        # 1）先确保端口类型切换为“字典”；
        # 2）再通过 Dictionary 图标与“键/值”标签模板为字典分别设置键/值类型。
        success = False
        is_alias_dict, key_type, value_type = parse_typed_dict_alias(target_type)
        if is_alias_dict:
            success = set_dict_port_type_with_settings(
                executor,
                screenshot1,
                node_bbox,
                port_center_out,
                mapped_name,
                key_type,
                value_type,
                "right",
                current_ports,
                log_callback,
                visual_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
            )
        else:
            # 普通数据类型仍按通用 Settings 流程设置
            success = set_port_type_with_settings(
                executor,
                screenshot1,
                node_bbox,
                port_center_out,
                mapped_name,
                target_type,
                'right',
                current_ports,
                log_callback,
                visual_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
            )

        snapshot_cache.mark_dirty(
            require_bbox=False,
            keep_cached_frame=is_first_right_data_port,
        )
        
        if success and is_operation_node:
            typed_side_once['right'] = True
    
    return True

