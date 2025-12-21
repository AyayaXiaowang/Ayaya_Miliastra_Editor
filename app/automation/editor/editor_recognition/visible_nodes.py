# -*- coding: utf-8 -*-
"""
editor_recognition.visible_nodes

节点可见性识别：输出当前画面中可见的模型节点及其 bbox/屏幕坐标。

注意：所有“节点位置”的语义统一采用 bbox 左上角作为锚点（与 GraphModel.NodeModel.pos 保持一致）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.input.common import compute_position_thresholds
from app.automation.vision import list_nodes
from engine.graph.models.graph_model import GraphModel


def recognize_visible_nodes(executor, graph_model: GraphModel) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    log = getattr(executor, "_log", None)
    total_node_count = int(len(getattr(graph_model, "nodes", {}) or {}))
    if callable(log):
        log(f"[可见节点] 开始统计可见节点：模型节点={total_node_count}")

    screenshot: Image.Image | None = None
    detected_nodes: list | None = None

    # 1) 优先尝试场景级快照（视口未变化时跨步骤复用同一帧识别结果）
    used_scene_snapshot: bool = False
    scene_snapshot = None
    get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
    if callable(get_scene_snapshot) and bool(
        getattr(executor, "enable_scene_snapshot_optimization", True)
    ):
        scene_snapshot = get_scene_snapshot()
        can_reuse = getattr(scene_snapshot, "can_reuse_for_current_view", None)
        if callable(can_reuse) and bool(can_reuse()):
            snapshot_image = getattr(scene_snapshot, "screenshot", None)
            snapshot_detections = getattr(scene_snapshot, "detected_nodes", None)
            if snapshot_image is not None and isinstance(snapshot_detections, list):
                screenshot = snapshot_image
                detected_nodes = snapshot_detections
                used_scene_snapshot = True
                if callable(log):
                    log(
                        f"[可见节点] 复用场景快照：检测节点={int(len(detected_nodes))}"
                    )

    # 2) 次优：复用上一次识别缓存（视口拟合阶段产生的一次性结果）
    if screenshot is None or detected_nodes is None:
        cached_screenshot = getattr(executor, "_last_recognition_screenshot", None)
        cached_detected = getattr(executor, "_last_recognition_detected", None)
        if cached_screenshot is not None and cached_detected is not None:
            screenshot = cached_screenshot
            detected_nodes = cached_detected
            if callable(log):
                log(
                    f"[可见节点] 复用上一次识别缓存：检测节点={int(len(detected_nodes))}"
                )
            # 使用后立即清除缓存，确保缓存只在同一操作内有效
            if hasattr(executor, "__dict__"):
                setattr(executor, "_last_recognition_screenshot", None)
                setattr(executor, "_last_recognition_detected", None)

    # 3) 兜底：重新截图并识别节点
    if screenshot is None or detected_nodes is None:
        screenshot = editor_capture.capture_window(executor.window_title)
        if not screenshot:
            if callable(log):
                log("[可见节点] 截图失败，全部节点标记为不可见")
            for node_id in graph_model.nodes.keys():
                result[node_id] = {
                    "visible": False,
                    "bbox": None,
                    "center": None,
                    "screen_center": None,
                }
            return result
        detected_nodes = list_nodes(screenshot)
        if callable(log):
            log(f"[可见节点] 新截图识别：检测节点={int(len(detected_nodes))}")

    # 将本次使用到的 screenshot + detections 回写到场景快照（若尚未由场景快照提供）
    if (not used_scene_snapshot) and (scene_snapshot is not None):
        update_method = getattr(scene_snapshot, "update_from_detection", None)
        if callable(update_method):
            update_method(screenshot, detected_nodes)

    if not detected_nodes:
        if callable(log):
            log("[可见节点] list_nodes 返回空，全部节点标记为不可见")
        for node_id in graph_model.nodes.keys():
            result[node_id] = {
                "visible": False,
                "bbox": None,
                "center": None,
                "screen_center": None,
            }
        return result

    # 预构建 bbox → 检测下标 映射，便于后续通过 bbox 反查唯一检测
    bbox_to_indices: Dict[tuple[int, int, int, int], list[int]] = {}
    # 使用 id(detection) 作为键，避免 NodeDetected 实例不可哈希的问题
    detection_index_by_id: Dict[int, int] = {}
    for det_index, detection in enumerate(detected_nodes):
        bbox_x, bbox_y, bbox_w, bbox_h = detection.bbox
        key = (int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h))
        bbox_to_indices.setdefault(key, []).append(int(det_index))
        detection_index_by_id[id(detection)] = int(det_index)

    # 按中文标题分桶候选检测，沿用原有的“标题优先”策略
    title_to_detections: Dict[str, list] = {}
    for detection in detected_nodes:
        det_title = executor.extract_chinese(getattr(detection, "name_cn", "") or "")
        if not det_title:
            continue
        title_to_detections.setdefault(det_title, []).append(detection)

    # 第一步：为每个节点各自选出“最佳 bbox + 代价”，记录候选对 (node_id, det_index, dist2)
    node_candidates: Dict[str, Dict[str, Any]] = {}
    skipped_no_bbox = 0
    skipped_no_det_index = 0
    skipped_fallback_too_far = 0
    for node_id, node in graph_model.nodes.items():
        title_cn = executor.extract_chinese(node.title)
        program_pos = (float(node.pos[0]), float(node.pos[1]))
        detection_pool = title_to_detections.get(title_cn) if title_cn else None
        candidates = detection_pool if detection_pool else detected_nodes

        debug_info: Dict[str, Any] = {}
        bx, by, bw, bh = _find_best_node_bbox(
            executor,
            screenshot,
            title_cn,
            program_pos,
            debug=debug_info,
            detected_nodes=candidates,
        )
        if int(bw) <= 0 or int(bh) <= 0:
            skipped_no_bbox += 1
            if callable(log) and skipped_no_bbox <= 5:
                failed_reason = str(debug_info.get("failed_reason", "unknown"))
                log(
                    f"[可见节点] 跳过 '{str(getattr(node, 'title', '')).strip()}'(id={node_id})："
                    f"未找到有效bbox（原因={failed_reason}）"
                )
            continue

        bbox_key = (int(bx), int(by), int(bw), int(bh))
        det_indices = bbox_to_indices.get(bbox_key)
        if not det_indices:
            skipped_no_det_index += 1
            if callable(log) and skipped_no_det_index <= 5:
                log(
                    f"[可见节点] 跳过 '{str(getattr(node, 'title', '')).strip()}'(id={node_id})："
                    "bbox 未在检测集中找到匹配索引"
                )
            continue

        det_index = det_indices[0]
        expected_editor_x, expected_editor_y = executor.convert_program_to_editor_coords(
            program_pos[0],
            program_pos[1],
        )
        delta_x = float(bx) - float(expected_editor_x)
        delta_y = float(by) - float(expected_editor_y)
        distance_sq = delta_x * delta_x + delta_y * delta_y

        # 仅对“回退匹配（fallback_used=True）”启用距离过滤：
        # 正常在 ROI 范围内找到的匹配不过滤；
        # 对于跨视口的全局回退结果，当偏移远大于当前位置容差时直接丢弃该候选，
        # 避免将明显不在同一局部结构内的远端节点强行绑定到当前检测框上。
        fallback_used = bool(debug_info.get("fallback_used"))
        if fallback_used:
            scale_value = float(executor.scale_ratio or 1.0)
            pos_threshold_x, pos_threshold_y = compute_position_thresholds(scale_value)
            max_allowed_dist2 = float(pos_threshold_x * pos_threshold_x + pos_threshold_y * pos_threshold_y)
            if distance_sq > max_allowed_dist2:
                skipped_fallback_too_far += 1
                if callable(log) and skipped_fallback_too_far <= 5:
                    log(
                        f"[可见节点] 跳过 '{str(getattr(node, 'title', '')).strip()}'(id={node_id})："
                        f"fallback 匹配距离过大，dist2={distance_sq:.1f} 阈值={max_allowed_dist2:.1f}"
                    )
                continue

        node_candidates[node_id] = {
            "det_index": det_index,
            "bbox": bbox_key,
            "distance_sq": distance_sq,
        }

    # 针对同名多实例节点，按预期坐标与检测框的相对顺序做一次局部重排，
    # 减少“相邻同名节点被错误对调”的情况。
    for title, detections_with_title in title_to_detections.items():
        if len(detections_with_title) < 2:
            continue
        # 收集当前图中具有相同中文标题且已有候选的节点
        same_title_nodes: list[tuple[str, object]] = []
        for node_id, node in graph_model.nodes.items():
            if node_id not in node_candidates:
                continue
            node_title_cn = executor.extract_chinese(getattr(node, "title", "") or "")
            if node_title_cn == title:
                same_title_nodes.append((node_id, node))
        if len(same_title_nodes) < 2:
            continue

        # 仅当第一阶段中“同一检测框被多个节点竞争使用”时才启用重排逻辑；
        # 若每个节点已经拥有唯一的检测索引，则保留第一阶段的结果避免无谓洗牌。
        det_to_nodes_local: Dict[int, list[str]] = {}
        for node_id, _node in same_title_nodes:
            candidate = node_candidates.get(node_id)
            if not candidate:
                continue
            det_index_value = candidate.get("det_index")
            if det_index_value is None:
                continue
            det_index_int = int(det_index_value)
            if det_index_int < 0:
                continue
            det_to_nodes_local.setdefault(det_index_int, []).append(node_id)
        conflict_exists = False
        for _det_index, node_list in det_to_nodes_local.items():
            if len(node_list) > 1:
                conflict_exists = True
                break
        if not conflict_exists:
            # 当前同名多实例在第一阶段已形成一一对应的检测分配，无需重排。
            continue

        # 计算这些节点在编辑器坐标中的预期位置
        expected_positions: list[tuple[str, float, float]] = []
        for node_id, node in same_title_nodes:
            prog_x = float(node.pos[0])
            prog_y = float(node.pos[1])
            editor_x, editor_y = executor.convert_program_to_editor_coords(prog_x, prog_y)
            expected_positions.append((node_id, float(editor_x), float(editor_y)))

        if not expected_positions:
            continue

        xs = [pos[1] for pos in expected_positions]
        ys = [pos[2] for pos in expected_positions]
        spread_x = max(xs) - min(xs)
        spread_y = max(ys) - min(ys)
        use_x_axis = bool(spread_x >= spread_y)

        # 收集该标题下所有检测框及其索引
        detection_entries: list[tuple[int, float, float]] = []
        for det in detections_with_title:
            det_index = detection_index_by_id.get(id(det))
            if det_index is None:
                continue
            bbox_x, bbox_y, _w, _h = det.bbox
            detection_entries.append((int(det_index), float(bbox_x), float(bbox_y)))

        if len(detection_entries) < 2:
            continue

        if use_x_axis:
            expected_sorted = sorted(expected_positions, key=lambda item: item[1])
            detection_sorted = sorted(detection_entries, key=lambda item: item[1])
        else:
            expected_sorted = sorted(expected_positions, key=lambda item: item[2])
            detection_sorted = sorted(detection_entries, key=lambda item: item[2])

        pair_count = min(len(expected_sorted), len(detection_sorted))
        for index in range(pair_count):
            node_id, exp_x, exp_y = expected_sorted[index]
            det_index, det_x, det_y = detection_sorted[index]
            _ = det_x, det_y
            detection_obj = detected_nodes[det_index]
            bx, by, bw, bh = detection_obj.bbox
            delta_x = float(bx) - float(exp_x)
            delta_y = float(by) - float(exp_y)
            distance_sq = delta_x * delta_x + delta_y * delta_y
            node_candidates[node_id] = {
                "det_index": int(det_index),
                "bbox": (int(bx), int(by), int(bw), int(bh)),
                "distance_sq": distance_sq,
            }

    if callable(log):
        log(
            f"[可见节点] 第一阶段匹配完成：有候选节点={int(len(node_candidates))}，"
            f"无bbox={int(skipped_no_bbox)}，无索引={int(skipped_no_det_index)}，"
            f"fallback超距={int(skipped_fallback_too_far)}"
        )

    # 第二步：以“距离平方最小”作为代价，对每个检测框只保留一个最佳节点，形成全局一对一分配
    det_to_best: Dict[int, tuple[str, float]] = {}
    for node_id, candidate in node_candidates.items():
        det_index = candidate["det_index"]
        dist2 = float(candidate["distance_sq"])
        existing = det_to_best.get(det_index)
        if existing is None or dist2 < existing[1]:
            det_to_best[det_index] = (node_id, dist2)

    assigned_node_to_detection: Dict[str, Dict[str, Any]] = {}
    for det_index, (best_node_id, _) in det_to_best.items():
        detection = detected_nodes[det_index]
        bx, by, bw, bh = detection.bbox
        recognized_title = executor.extract_chinese(getattr(detection, "name_cn", "") or "")
        assigned_node_to_detection[best_node_id] = {
            "det_index": int(det_index),
            "bbox": (int(bx), int(by), int(bw), int(bh)),
            "recognized_title": str(recognized_title or "").strip(),
        }

    if callable(log):
        log(
            f"[可见节点] 第二阶段分配完成：参与分配的节点数={int(len(assigned_node_to_detection))}，"
            f"检测节点数={int(len(detected_nodes))}"
        )

    # 第三步：构建最终可见性映射；未参与分配或无检测的节点一律标记为不可见
    visible_ids: list[str] = []
    for node_id in graph_model.nodes.keys():
        assigned = assigned_node_to_detection.get(node_id)
        if not isinstance(assigned, dict):
            result[node_id] = {
                "visible": False,
                "bbox": None,
                "center": None,
                "screen_center": None,
                "recognized_title": "",
            }
            continue

        bbox = assigned.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            result[node_id] = {
                "visible": False,
                "bbox": None,
                "center": None,
                "screen_center": None,
                "recognized_title": "",
            }
            continue

        bx, by, bw, bh = bbox
        # 对外暴露的节点位置语义仍然采用 bbox 左上角作为锚点；
        # 如需绘制圆形高亮，可在 UI 层自行根据宽高计算几何中心。
        anchor_x = int(bx)
        anchor_y = int(by)
        screen_x, screen_y = executor.convert_editor_to_screen_coords(
            int(anchor_x),
            int(anchor_y),
        )
        result[node_id] = {
            "visible": True,
            "bbox": (int(bx), int(by), int(bw), int(bh)),
            "center": (int(anchor_x), int(anchor_y)),
            "screen_center": (int(screen_x), int(screen_y)),
            "recognized_title": str(assigned.get("recognized_title", "") or "").strip(),
        }
        visible_ids.append(node_id)

    if callable(log):
        preview_titles: list[str] = []
        for vid in visible_ids[:10]:
            node_model = graph_model.nodes.get(vid)
            if node_model is not None and getattr(node_model, "title", None) is not None:
                preview_titles.append(str(node_model.title).strip())
        log(
            f"[可见节点] 最终可见节点={int(len(visible_ids))}/{total_node_count}"
            + (f"：{preview_titles}" if preview_titles else "")
        )

    return result


def is_node_visible_by_id(executor, graph_model: GraphModel, node_id: str) -> bool:
    if node_id not in graph_model.nodes:
        return False
    mapping = recognize_visible_nodes(executor, graph_model)
    info = mapping.get(node_id)
    return bool(info and info.get("visible"))


def _find_best_node_bbox(
    executor,
    screenshot: Image.Image,
    title_cn: str,
    program_pos: tuple[float, float],
    debug: Optional[Dict[str, Any]] = None,
    detected_nodes: Optional[list] = None,
) -> tuple[int, int, int, int]:
    from app.automation.vision.node_detection import find_best_node_bbox as _find_best_node_bbox_ext

    return _find_best_node_bbox_ext(executor, screenshot, title_cn, program_pos, debug, detected_nodes)


