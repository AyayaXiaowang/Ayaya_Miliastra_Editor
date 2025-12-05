# -*- coding: utf-8 -*-
"""
vector3_click_strategy: 三维向量输入点击策略。

职责：
- 在 OCR 识别出轴标签后，根据几何位置规划每个轴的点击中心；
- 在 Warning 模板命中后，基于节点与端口几何推导 X/Y/Z 输入框的大致位置；
- 生成供 UI 层执行的点击计划 (axis_label, editor_x, editor_y, value_text)。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from app.automation.config.config_params_helpers import clip_to_node_bounds


AxisLabel = str
BBox = Tuple[int, int, int, int]


def build_ocr_click_plan_for_vector3(
    label_to_bbox: Dict[AxisLabel, BBox],
    search_region: Tuple[int, int, int, int],
    node_bbox: Tuple[int, int, int, int],
    x_value: str,
    y_value: str,
    z_value: str,
) -> Tuple[List[Tuple[AxisLabel, int, int, str]], Dict[AxisLabel, BBox]]:
    """基于 OCR 轴标签 bbox 规划每个轴的点击中心与高亮区域。"""
    search_left, search_top, _search_width, _search_height = search_region

    axis_to_value = {
        "X": x_value,
        "Y": y_value,
        "Z": z_value,
    }

    click_plan: List[Tuple[AxisLabel, int, int, str]] = []
    highlight_bboxes: Dict[AxisLabel, BBox] = {}

    for axis_label in ("X", "Y", "Z"):
        bbox_left, bbox_top, bbox_width, bbox_height = label_to_bbox[axis_label]

        # 点击标签中心略向右 12 像素以进入对应输入框
        click_editor_x = search_left + bbox_left + max(1, bbox_width) // 2 + 12
        click_editor_y = search_top + bbox_top + max(1, bbox_height) // 2

        clipped_x, clipped_y = clip_to_node_bounds(
            click_editor_x,
            click_editor_y,
            node_bbox,
        )

        click_plan.append(
            (axis_label, clipped_x, clipped_y, axis_to_value[axis_label]),
        )

        # 高亮使用全局坐标，便于与其他可视化叠加
        highlight_bboxes[axis_label] = (
            search_left + bbox_left,
            search_top + bbox_top,
            bbox_width,
            bbox_height,
        )

    return click_plan, highlight_bboxes


def build_geometry_click_plan_for_vector3(
    warning_bbox: Tuple[int, int, int, int, float],
    node_bbox: Tuple[int, int, int, int],
    current_port_bbox: Tuple[int, int, int, int],
    x_value: str,
    y_value: str,
    z_value: str,
) -> List[Tuple[AxisLabel, int, int, str]]:
    """基于 Warning 与端口位置推导三维向量各轴的点击中心。"""
    warning_left, warning_top, warning_width, warning_height, _conf = warning_bbox

    # Z：使用 Warning 模板的左下角作为中心点
    z_center_x = int(warning_left)
    z_center_y = int(warning_top + warning_height)

    # 端口几何信息
    port_right_edge = int(current_port_bbox[0] + current_port_bbox[2])
    port_width = int(current_port_bbox[2]) if int(current_port_bbox[2]) > 0 else 60

    # X：从端口右侧边向右延伸一个端口宽度
    x_center_x = int(port_right_edge + port_width)
    x_center_y = int(z_center_y)

    # Y：X 与 Z 的中点
    y_center_x = int((x_center_x + z_center_x) / 2)
    y_center_y = int(z_center_y)

    # 裁剪到节点 bbox 内部
    x_center_x, x_center_y = clip_to_node_bounds(x_center_x, x_center_y, node_bbox)
    y_center_x, y_center_y = clip_to_node_bounds(y_center_x, y_center_y, node_bbox)
    z_center_x, z_center_y = clip_to_node_bounds(z_center_x, z_center_y, node_bbox)

    click_plan: List[Tuple[AxisLabel, int, int, str]] = [
        ("X", x_center_x, x_center_y, x_value),
        ("Y", y_center_x, y_center_y, y_value),
        ("Z", z_center_x, z_center_y, z_value),
    ]

    return click_plan


