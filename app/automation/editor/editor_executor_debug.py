# -*- coding: utf-8 -*-
"""
EditorExecutor Debug Mixin

收敛创建位置、可见节点、视口映射等调试截图与调试日志入口。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor.ui_constants import NODE_VIEW_WIDTH_PX, NODE_VIEW_HEIGHT_PX
from engine.graph.models.graph_model import GraphModel, NodeModel

from .debug_utils import log_branch_ambiguity_report


class EditorExecutorDebugMixin:
    window_title: str
    scale_ratio: Optional[float]
    origin_node_pos: Optional[Tuple[float, float]]

    def debug_capture_create_node_position(
        self,
        graph_model: GraphModel,
        node: NodeModel,
        program_x: float,
        program_y: float,
        log_callback=None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> None:
        rect_items: list[dict] = []
        circle_items: list[dict] = []

        debug_info = getattr(self, "_last_create_position_debug", None)
        source_label = "图中原始坐标"
        anchor_node_ids: list[str] = []
        if isinstance(debug_info, dict):
            raw_source = str(debug_info.get("source") or "")
            if raw_source == "anchor":
                anchor_id_value = debug_info.get("anchor_node_id")
                anchor_id = str(anchor_id_value or "")
                if anchor_id:
                    anchor_node_ids = [anchor_id]
                source_label = "创建锚点"
            elif raw_source == "neighbor_offsets":
                neighbor_ids_value = debug_info.get("neighbor_node_ids")
                if isinstance(neighbor_ids_value, list):
                    for value in neighbor_ids_value:
                        value_str = str(value or "")
                        if value_str:
                            anchor_node_ids.append(value_str)
                if anchor_node_ids:
                    source_label = "邻居偏移"
            elif raw_source == "nearest_delta":
                anchor_id_value = debug_info.get("anchor_node_id")
                anchor_id = str(anchor_id_value or "")
                if anchor_id:
                    anchor_node_ids = [anchor_id]
                source_label = "最近偏移节点"

        anchor_display = ""
        if anchor_node_ids:
            primary_anchor_id = anchor_node_ids[0]
            primary_anchor = graph_model.nodes.get(primary_anchor_id)
            if primary_anchor is not None:
                primary_title_text = ""
                if getattr(primary_anchor, "title", None) is not None:
                    primary_title_text = str(primary_anchor.title).strip()
                if primary_title_text:
                    anchor_display = f"{primary_title_text} (id={primary_anchor_id})"
                else:
                    anchor_display = f"(id={primary_anchor_id})"

        node_title_text = ""
        if getattr(node, "title", None) is not None:
            node_title_text = str(node.title).strip()
        base_label = f"创建节点: {node_title_text} (id={node.id})" if node_title_text else f"创建节点 (id={node.id})"
        label_text = base_label
        if source_label and anchor_display:
            label_text = f"{base_label}\n来源: {source_label} → {anchor_display}"
        elif source_label:
            label_text = f"{base_label}\n来源: {source_label}"

        editor_x, editor_y = self.convert_program_to_editor_coords(float(program_x), float(program_y))
        circle_items.append(
            {
                "center": (int(editor_x), int(editor_y)),
                "radius": 8,
                "color": (255, 220, 0),
                "label": label_text,
            }
        )

        visible_map = self.recognize_visible_nodes(graph_model)

        max_anchor_count = 3
        for anchor_node_id in anchor_node_ids:
            if len(rect_items) >= max_anchor_count:
                break
            anchor_model = graph_model.nodes.get(anchor_node_id)
            if anchor_model is None:
                continue
            anchor_info = visible_map.get(anchor_node_id)
            bbox_left: int
            bbox_top: int
            bbox_width: int
            bbox_height: int
            if (
                isinstance(anchor_info, dict)
                and bool(anchor_info.get("visible"))
                and isinstance(anchor_info.get("bbox"), (list, tuple))
                and len(anchor_info["bbox"]) == 4
            ):
                bbox = anchor_info["bbox"]
                bbox_left, bbox_top, bbox_width, bbox_height = (
                    int(bbox[0]),
                    int(bbox[1]),
                    int(bbox[2]),
                    int(bbox[3]),
                )
            else:
                anchor_prog_x = float(anchor_model.pos[0])
                anchor_prog_y = float(anchor_model.pos[1])
                anchor_editor_x, anchor_editor_y = self.convert_program_to_editor_coords(
                    anchor_prog_x,
                    anchor_prog_y,
                )
                scale_value = 1.0
                if self.scale_ratio is not None:
                    scale_value = float(self.scale_ratio) if abs(float(self.scale_ratio)) > 1e-6 else 1.0
                bbox_width = int(NODE_VIEW_WIDTH_PX * scale_value)
                bbox_height = int(NODE_VIEW_HEIGHT_PX * scale_value)
                bbox_left = int(anchor_editor_x)
                bbox_top = int(anchor_editor_y)
            anchor_title_text = ""
            if getattr(anchor_model, "title", None) is not None:
                anchor_title_text = str(anchor_model.title).strip()
            anchor_label = f"锚点: {anchor_title_text} (id={anchor_node_id})" if anchor_title_text else f"锚点 (id={anchor_node_id})"
            rect_items.append(
                {
                    "bbox": (
                        int(bbox_left),
                        int(bbox_top),
                        int(bbox_width),
                        int(bbox_height),
                    ),
                    "color": (80, 220, 120),
                    "label": anchor_label,
                }
            )

        overlays: dict = {"rects": rect_items}
        if circle_items:
            overlays["circles"] = circle_items
        screenshot = editor_capture.capture_window_strict(self.window_title)
        if screenshot is None:
            screenshot = editor_capture.capture_window(self.window_title)
        if not screenshot:
            self._log("✗ 截图失败（创建节点调试可视化）", log_callback)
            return
        self._emit_visual(screenshot, overlays, visual_callback)

    def debug_capture_visible_node_ids(
        self,
        graph_model: GraphModel,
        log_callback=None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> None:
        # 可见节点调试依赖稳定的程序↔编辑器坐标映射；若尚未建立映射则直接跳过，
        # 避免在单步首创建等“未校准场景”中触发坐标相关异常。
        if self.scale_ratio is None or self.origin_node_pos is None:
            self._log(
                "· 可见节点调试：当前尚未完成坐标映射（scale_ratio / origin_node_pos 为空），"
                "跳过可见节点识别；请先执行快速映射或锚点坐标校准后再重试。",
                log_callback,
            )
            return

        visible_map = self.recognize_visible_nodes(graph_model)
        if not isinstance(visible_map, dict) or not visible_map:
            self._log("· 可见节点调试：当前画面中未识别到任何节点", log_callback)
            return

        def _build_overlay(_image: Image.Image) -> dict:
            rect_items: list[dict] = []
            for node_id, info in visible_map.items():
                if not bool(info.get("visible")):
                    continue
                bbox = info.get("bbox")
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue
                bx, by, bw, bh = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                node_model = graph_model.nodes.get(node_id)
                node_title_text = ""
                if node_model is not None and getattr(node_model, "title", None) is not None:
                    node_title_text = str(node_model.title).strip()
                if node_title_text:
                    label_text = f"{node_title_text} ({node_id})"
                else:
                    label_text = str(node_id)
                rect_items.append(
                    {
                        "bbox": (bx, by, bw, bh),
                        "color": (80, 220, 120),
                        "label": label_text,
                    }
                )
            return {"rects": rect_items}

        self.capture_and_emit(
            label="执行前-可见节点ID",
            overlays_builder=_build_overlay,
            visual_callback=visual_callback,
        )

    def _debug_log_branch_ambiguity(
        self,
        graph_model: GraphModel,
        name_to_model_nodes: Dict[str, list[NodeModel]],
        name_to_detections: Dict[str, list[tuple[int, int, int, int]]],
        s: float,
        tx: float,
        ty: float,
        epsilon_px: float,
        log_callback=None,
    ) -> None:
        """输出分支歧义调试报告。

        参数含义：
        - s: 识别得到的缩放因子（scale）
        - tx / ty: 从程序坐标到屏幕坐标的平移量（translation_x / translation_y）
        - epsilon_px: 判定样本点是否为“内点”的像素误差阈值
        """
        log_branch_ambiguity_report(
            logger=self._log,
            graph_model=graph_model,
            name_to_model_nodes=name_to_model_nodes,
            name_to_detections=name_to_detections,
            scale=s,
            tx=tx,
            ty=ty,
            epsilon_px=epsilon_px,
            log_callback=log_callback,
        )


