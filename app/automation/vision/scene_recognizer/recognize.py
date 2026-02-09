from __future__ import annotations

from typing import Dict, List, Optional

from PIL import Image

from .models import RecognizedNode, RecognizedPort, SceneRecognizerTuning
from .ocr_titles import _ocr_titles_for_rectangles
from .rectangle_detection import _detect_rectangles_from_canvas
from .template_matching import _load_template_images, _match_templates_in_rectangle


def recognize_scene(
    canvas_image: Image.Image,
    template_dir: str,
    header_height: int = 28,
    threshold: float = 0.7,
    tuning: Optional[SceneRecognizerTuning] = None,
    enable_ocr: bool = True,
) -> List[RecognizedNode]:
    """
    在一次调用中识别节点矩形、标题与端口。

    Args:
        canvas_image: 仅为“节点图布置区域”的图像（PIL.Image，RGB）。
        template_dir: 端口模板目录（PNG），例如 'assets/ocr_templates/4K-CN/Node'。
        header_height: 节点卡片顶部标题高度（像素）。
        threshold: 模板匹配阈值。

    Returns:
        List[RecognizedNode]:
            每个节点包含标题、矩形与端口。
    """
    effective_tuning = tuning or SceneRecognizerTuning()
    rectangles = _detect_rectangles_from_canvas(canvas_image, tuning=effective_tuning)
    if len(rectangles) == 0:
        return []

    from app.automation.vision.ocr_utils import extract_chinese

    titles_by_index: Dict[int, str] = {}
    if bool(enable_ocr):
        titles_by_index = _ocr_titles_for_rectangles(canvas_image, rectangles, header_height=header_height)
    templates = _load_template_images(template_dir)

    recognized_nodes: List[RecognizedNode] = []
    for idx, rect in enumerate(rectangles, 1):
        node_title = titles_by_index.get(idx, "")
        node_title_cn = extract_chinese(node_title)
        header_height_for_rect = int(rect.get("header_height", header_height) or header_height)
        rect_height_value = int(rect.get("height", 0) or 0)
        if rect_height_value > 0:
            header_height_for_rect = max(0, min(int(header_height_for_rect), int(rect_height_value)))
        template_matches = _match_templates_in_rectangle(
            canvas_image,
            rect,
            templates,
            header_height,
            threshold,
            None,
            effective_tuning,
        )
        recognized_ports: List[RecognizedPort] = []
        for match in template_matches:
            center_x = int(match["x"] + match["width"] / 2)
            center_y = int(match["y"] + match["height"] / 2)
            recognized_ports.append(
                RecognizedPort(
                    side=match["side"],
                    index=match.get("index"),
                    kind=str(match["template_name"]),
                    bbox=(int(match["x"]), int(match["y"]), int(match["width"]), int(match["height"])),
                    center=(center_x, center_y),
                    confidence=float(match["confidence"]),
                )
            )

        # Settings / Warning 行内重判规则使用统一的“装饰端口”判定
        y_tolerance = int(effective_tuning.port_same_row_y_tolerance_px)

        def is_decorative_port(port_obj: RecognizedPort) -> bool:
            """判定是否为行内装饰/控件类模板（不可连线）。"""
            kind_lower = str(port_obj.kind or "").lower()
            return (
                kind_lower.startswith("settings")
                or kind_lower.startswith("warning")
                or kind_lower.startswith("dictionary")
                or kind_lower.startswith("select")
            )

        def is_connectable_like_port(port_obj: RecognizedPort) -> bool:
            return not is_decorative_port(port_obj)

        def is_settings_like_port(port_obj: RecognizedPort) -> bool:
            return str(port_obj.kind or "").lower().startswith("settings")

        def is_warning_like_port(port_obj: RecognizedPort) -> bool:
            return str(port_obj.kind or "").lower().startswith("warning")

        def _has_connectable_neighbor_on_side(*, ports: List[RecognizedPort], row_center_y: int, side: str) -> bool:
            return any(
                (neighbor.side == side)
                and is_connectable_like_port(neighbor)
                and (abs(int(neighbor.center[1]) - int(row_center_y)) <= y_tolerance)
                for neighbor in ports
            )

        # Settings 侧别归因（绑定到可连线端口行）
        for settings_port in recognized_ports:
            if not is_settings_like_port(settings_port):
                continue
            row_center_y = int(settings_port.center[1])
            has_left_connectable = _has_connectable_neighbor_on_side(
                ports=recognized_ports,
                row_center_y=row_center_y,
                side="left",
            )
            has_right_connectable = _has_connectable_neighbor_on_side(
                ports=recognized_ports,
                row_center_y=row_center_y,
                side="right",
            )
            if has_left_connectable and (not has_right_connectable):
                settings_port.side = "left"
            elif has_right_connectable and (not has_left_connectable):
                settings_port.side = "right"

        # Warning 侧别重判规则
        if node_title_cn == "多分支":
            for warning_port in recognized_ports:
                if is_warning_like_port(warning_port):
                    has_right_neighbor = _has_connectable_neighbor_on_side(
                        ports=recognized_ports,
                        row_center_y=int(warning_port.center[1]),
                        side="right",
                    )
                    warning_port.side = "right" if has_right_neighbor else "left"
        else:
            for warning_port in recognized_ports:
                if is_warning_like_port(warning_port):
                    warning_port.side = "left"

        # Settings 行内装饰去重规则
        connectable_ports_by_side: Dict[str, List[RecognizedPort]] = {"left": [], "right": []}
        for port_obj in recognized_ports:
            if not is_connectable_like_port(port_obj):
                continue
            if port_obj.side in ("left", "right"):
                connectable_ports_by_side[port_obj.side].append(port_obj)

        def _pick_best_settings_candidate(*, existing: RecognizedPort, candidate: RecognizedPort, side: str) -> RecognizedPort:
            if float(candidate.confidence) > float(existing.confidence):
                return candidate
            if float(candidate.confidence) < float(existing.confidence):
                return existing
            existing_x = int(existing.center[0])
            candidate_x = int(candidate.center[0])
            if side == "right":
                return candidate if candidate_x > existing_x else existing
            return candidate if candidate_x < existing_x else existing

        kept_settings_by_side_and_index: Dict[tuple[str, int], RecognizedPort] = {}
        for settings_port in [p for p in recognized_ports if is_settings_like_port(p)]:
            side_text = str(settings_port.side or "")
            if side_text not in ("left", "right"):
                continue
            row_center_y = int(settings_port.center[1])
            same_side_connectables = connectable_ports_by_side.get(side_text, [])
            best_match: Optional[RecognizedPort] = None
            best_dy: Optional[int] = None
            for neighbor in same_side_connectables:
                dy = abs(int(neighbor.center[1]) - int(row_center_y))
                if dy > y_tolerance:
                    continue
                if best_dy is None or dy < best_dy:
                    best_dy = int(dy)
                    best_match = neighbor
            if best_match is None:
                continue
            if best_match.index is None:
                continue
            key = (side_text, int(best_match.index))
            existing = kept_settings_by_side_and_index.get(key)
            if existing is None:
                kept_settings_by_side_and_index[key] = settings_port
            else:
                kept_settings_by_side_and_index[key] = _pick_best_settings_candidate(
                    existing=existing,
                    candidate=settings_port,
                    side=side_text,
                )

        if len(kept_settings_by_side_and_index) > 0:
            settings_keep_set = set(id(obj) for obj in kept_settings_by_side_and_index.values())
            recognized_ports = [
                port_obj
                for port_obj in recognized_ports
                if (not is_settings_like_port(port_obj)) or (id(port_obj) in settings_keep_set)
            ]

        # Warning 行内装饰模板去重（仅影响普通端口识别结果）
        filtered_ports: List[RecognizedPort] = []
        for port_obj in recognized_ports:
            if is_warning_like_port(port_obj):
                has_non_decorative_same_row = any(
                    (neighbor is not port_obj)
                    and (neighbor.side == port_obj.side)
                    and is_connectable_like_port(neighbor)
                    and (abs(int(neighbor.center[1]) - int(port_obj.center[1])) <= y_tolerance)
                    for neighbor in recognized_ports
                )
                if has_non_decorative_same_row:
                    continue
            filtered_ports.append(port_obj)
        recognized_ports = filtered_ports

        recognized_nodes.append(
            RecognizedNode(
                title_cn=node_title_cn,
                rect=(int(rect["x"]), int(rect["y"]), int(rect["width"]), int(rect["height"])),
                ports=recognized_ports,
                header_height_px=int(header_height_for_rect),
            )
        )

    return recognized_nodes



