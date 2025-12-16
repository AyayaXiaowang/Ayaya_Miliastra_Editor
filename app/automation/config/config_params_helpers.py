# -*- coding: utf-8 -*-
"""
config_params_helpers: 参数配置辅助工具
从 config_params.py 提取的可复用函数，提高可测试性。
"""

from __future__ import annotations

from typing import Optional, Tuple, List, Dict, Any
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor import executor_utils as _exec_utils
from app.automation.ports._ports import normalize_kind_text, is_non_connectable_kind
from app.automation.ports.port_picker import filter_screen_port_candidates as _filter_port_candidates
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.graph.common import is_selection_input_port
from engine.graph.models.graph_model import NodeModel
from app.automation.vision.ocr_utils import normalize_ocr_bbox


def compute_port_ordinal_in_model(
    node_model: NodeModel,
    target_port_name: str,
    expected_kind: Optional[str]
) -> Optional[int]:
    """计算端口在模型中的序号（仅统计指定kind的端口）。
    
    Args:
        node_model: 节点模型
        target_port_name: 目标端口名称
        expected_kind: 期望的端口类型 ('flow'/'data'/None)
    
    Returns:
        端口序号（0-based），未找到返回None
    """
    if not isinstance(target_port_name, str) or target_port_name == "":
        return None
    
    names_all_inputs = [p.name for p in (node_model.inputs or [])]

    if expected_kind == 'flow':
        # 仅统计流程端口
        names_filtered = [n for n in names_all_inputs if is_flow_port_name(n)]
    elif expected_kind == 'data':
        # 数据端口：排除流程端口以及“选择端口”（如发送/监听信号的“信号名”、结构体节点的“结构体名”），
        # 这些选择端口在 UI 中通常以独立对话框或行内选择控件呈现，不参与常规参数配置与连线。
        names_filtered = [
            n for n in names_all_inputs
            if (not is_flow_port_name(n)) and (not is_selection_input_port(node_model, n))
        ]
    else:
        # 未指定 kind 时，保留全部输入端口名称
        names_filtered = names_all_inputs
    
    if target_port_name in names_filtered:
        return int(names_filtered.index(target_port_name))
    return None


def filter_screen_input_candidates(
    all_ports: list,
    expected_kind: Optional[str]
) -> list:
    """筛选并排序屏幕上的输入端口候选。"""
    return _filter_port_candidates(all_ports, preferred_side='left', expected_kind=expected_kind)


def format_candidates_brief(candidates: list) -> str:
    """格式化候选端口列表为简要文本（用于日志）。
    
    Args:
        candidates: 候选端口列表
    
    Returns:
        格式化的文本，如 "#0:端口名[data], #1:..."
    """
    values = []
    for index, port_obj in enumerate(candidates):
        mapped_name = str(getattr(port_obj, 'name_cn', '') or '')
        kind_norm = normalize_kind_text(getattr(port_obj, 'kind', ''))
        values.append(f"#{index}:{mapped_name or '?'}[{kind_norm}]")
    return ", ".join(values)


def check_center_used(center_xy: Tuple[int, int], used_centers: List[Tuple[int, int]]) -> bool:
    """判断端口中心是否已被使用（像素级近邻视为同一端口）。
    
    Args:
        center_xy: 要检查的中心坐标
        used_centers: 已使用的中心坐标列表
    
    Returns:
        True表示已被使用
    """
    for used_x, used_y in used_centers:
        if abs(int(center_xy[0]) - int(used_x)) <= 4 and abs(int(center_xy[1]) - int(used_y)) <= 4:
            return True
    return False


def pick_unused_port_center(
    screen_candidates: list,
    preferred_ordinal: Optional[int],
    used_centers: List[Tuple[int, int]]
) -> Optional[Tuple[int, int]]:
    """在屏幕候选中选择未被使用的端口中心。
    
    优先使用 preferred_ordinal 对应的端口，若已被使用则向后顺延，
    再全量扫描寻找首个未使用项。
    
    Args:
        screen_candidates: 屏幕候选端口列表（已排序）
        preferred_ordinal: 优选序号（0-based）
        used_centers: 已使用的中心坐标列表
    
    Returns:
        未使用的端口中心坐标，找不到返回None
    """
    if len(screen_candidates) == 0:
        return None
    
    # 优先从 preferred_ordinal 开始向后扫描
    if preferred_ordinal is not None:
        start = int(preferred_ordinal) if int(preferred_ordinal) >= 0 else 0
        if start >= len(screen_candidates):
            start = len(screen_candidates) - 1
        
        for index in range(start, len(screen_candidates)):
            center_x, center_y = int(screen_candidates[index].center[0]), int(screen_candidates[index].center[1])
            if not check_center_used((center_x, center_y), used_centers):
                return (center_x, center_y)
    
    # 全量扫描
    for index in range(len(screen_candidates)):
        center_x, center_y = int(screen_candidates[index].center[0]), int(screen_candidates[index].center[1])
        if not check_center_used((center_x, center_y), used_centers):
            return (center_x, center_y)
    
    return None


def parse_vector3_text(text: str) -> Tuple[str, str, str]:
    """解析三维向量文本为 (x, y, z) 三元组。
    
    支持格式：
    - (x, y, z) 或 [x, y, z]
    - x, y, z
    - x y z（空格分隔）
    
    Args:
        text: 向量文本
    
    Returns:
        (x_val, y_val, z_val) 三元组，缺失分量填充 "0"
    """
    raw = str(text or "").strip()
    
    # 移除外层括号
    if len(raw) >= 2 and ((raw[0] == '(' and raw[-1] == ')') or (raw[0] == '[' and raw[-1] == ']')):
        raw = raw[1:-1].strip()
    
    # 统一分隔符
    raw = raw.replace('，', ',')
    
    # 按逗号分隔
    parts = [p.strip() for p in raw.split(',') if p.strip() != ""]
    
    # 若不足3个分量，尝试按空白分隔
    if len(parts) < 3:
        more = [p.strip() for p in raw.split() if p.strip() != ""]
        parts = more
    
    x_val = parts[0] if len(parts) > 0 else "0"
    y_val = parts[1] if len(parts) > 1 else "0"
    z_val = parts[2] if len(parts) > 2 else "0"
    
    return (x_val, y_val, z_val)


def clip_to_node_bounds(
    editor_x: int,
    editor_y: int,
    node_bbox: Tuple[int, int, int, int]
) -> Tuple[int, int]:
    """将坐标裁剪到节点边界内（留1像素边距）。
    
    Args:
        editor_x: 编辑器坐标X
        editor_y: 编辑器坐标Y
        node_bbox: 节点边界框 (left, top, width, height)
    
    Returns:
        裁剪后的坐标 (x, y)
    """
    node_left = int(node_bbox[0])
    node_top = int(node_bbox[1])
    node_right = int(node_bbox[0] + node_bbox[2])
    node_bottom = int(node_bbox[1] + node_bbox[3])
    
    clipped_x = editor_x
    clipped_y = editor_y
    
    if clipped_x < node_left + 1:
        clipped_x = node_left + 1
    if clipped_x > node_right - 1:
        clipped_x = node_right - 1
    if clipped_y < node_top + 1:
        clipped_y = node_top + 1
    if clipped_y > node_bottom - 1:
        clipped_y = node_bottom - 1
    
    return (int(clipped_x), int(clipped_y))

