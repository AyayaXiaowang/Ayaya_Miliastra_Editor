# -*- coding: utf-8 -*-
"""
editor_recognition.mappings

构建可配对节点的检测映射、指纹过滤与配对点集合。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine.configs.settings import settings
from engine.utils.cache.fingerprint import (
    Fingerprint as _FP,
    build_fingerprints_for_detections,
    compare_fingerprints_l1,
    compute_layout_signature_for_model as _compute_layout_sig,
    load_cached_fingerprints,
)

from .models import MappingData, PairCollections


def build_detection_mappings(executor, graph_model, detected) -> MappingData:
    name_to_model_nodes: Dict[str, list] = {}
    for node in graph_model.nodes.values():
        title_cn = executor.extract_chinese(node.title)
        if not title_cn:
            continue
        name_to_model_nodes.setdefault(title_cn, []).append(node)

    name_to_detections: Dict[str, list[tuple[int, int, int, int]]] = {}
    name_to_det_indices: Dict[str, list[int]] = {}
    for idx, detection in enumerate(detected):
        title_cn = executor.extract_chinese(getattr(detection, 'name_cn', '') or '')
        if not title_cn:
            continue
        bbox_x, bbox_y, bbox_w, bbox_h = detection.bbox
        name_to_detections.setdefault(title_cn, []).append((int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)))
        name_to_det_indices.setdefault(title_cn, []).append(int(idx))

    shared_names = [name for name in name_to_model_nodes.keys() if name in name_to_detections]
    unique_model_names = sorted(name_to_model_nodes.keys())
    unique_detected_names = sorted(name_to_detections.keys())

    return MappingData(
        name_to_model_nodes=name_to_model_nodes,
        name_to_detections=name_to_detections,
        name_to_det_indices=name_to_det_indices,
        shared_names=shared_names,
        unique_model_names=unique_model_names,
        unique_detected_names=unique_detected_names,
    )


def build_fingerprint_filters(
    executor,
    graph_model,
    detected,
    mappings: MappingData,
    log_callback,
) -> tuple[Dict[str, set[tuple[str, int]]], bool]:
    allowed_pairs_by_title: Dict[str, set[tuple[str, int]]] = {}
    fingerprint_filter_enabled = False
    
    # [调试] 输出指纹过滤检查详情
    fingerprint_enabled_setting = bool(settings.FINGERPRINT_ENABLED)
    has_graph_id = hasattr(graph_model, "graph_id")
    graph_id_value = getattr(graph_model, "graph_id", None) if has_graph_id else None
    
    executor.log(
        f"[指纹检查] FINGERPRINT_ENABLED={fingerprint_enabled_setting} graph_id存在={has_graph_id} graph_id值={graph_id_value}",
        log_callback,
    )
    
    if settings.FINGERPRINT_ENABLED and hasattr(graph_model, "graph_id"):
        cached = load_cached_fingerprints(executor.workspace_path, str(graph_model.graph_id))
        
        # [调试] 输出缓存加载情况
        cache_exists = bool(cached and isinstance(cached, dict) and cached.get("items"))
        executor.log(
            f"[指纹检查] 缓存文件存在={cache_exists} 缓存项数={len(cached.get('items', {})) if cache_exists else 0}",
            log_callback,
        )
        
        if cached and isinstance(cached, dict) and cached.get("items"):
            try_nodes_for_sig = []
            for node in graph_model.nodes.values():
                node_id = getattr(node, "id", "")
                title_cn = executor.extract_chinese(node.title)
                pos_x, pos_y = float(node.pos[0]), float(node.pos[1])
                try_nodes_for_sig.append((node_id, title_cn, pos_x, pos_y))
            current_sig = _compute_layout_sig(try_nodes_for_sig)
            cached_sig = cached.get("layout_signature", "")
            signature_match = bool(current_sig == cached_sig)
            
            # [调试] 输出签名比对结果
            executor.log(
                f"[指纹检查] layout_signature匹配={signature_match} 当前签名={current_sig[:16]}... 缓存签名={cached_sig[:16] if cached_sig else 'None'}...",
                log_callback,
            )
            
            if current_sig == cached.get("layout_signature"):
                fingerprint_filter_enabled = True
                detections_xy = []
                for detection in detected:
                    bbox_x, bbox_y, _, _ = detection.bbox
                    detections_xy.append((float(bbox_x), float(bbox_y)))
                det_fp_map = build_fingerprints_for_detections(
                    detections_xy,
                    k_neighbors=int(settings.FINGERPRINT_K),
                    round_ratio_digits=int(settings.FINGERPRINT_ROUND_DIGITS),
                )
                for name in mappings.shared_names:
                    models = mappings.name_to_model_nodes.get(name, [])
                    detections = mappings.name_to_detections.get(name, [])
                    if len(models) <= 1 and len(detections) <= 1:
                        continue
                    det_indices = mappings.name_to_det_indices.get(name, [])
                    allowed: set[tuple[str, int]] = set()
                    for model in models:
                        model_id = getattr(model, "id", "")
                        cached_item = cached["items"].get(model_id)
                        if not cached_item:
                            continue
                        model_fp = _FP(
                            ratios=list(cached_item.get("ratios", [])),
                            nearest_distance=float(cached_item.get("nearest_distance", 0.0)),
                            neighbor_count=int(cached_item.get("neighbor_count", 0)),
                            neighbors_indices=None,
                            center=(
                                float(cached_item.get("center", [0.0, 0.0])[0]),
                                float(cached_item.get("center", [0.0, 0.0])[1]),
                            ),
                        )
                        for det_idx in det_indices:
                            detection_fp = det_fp_map.get(int(det_idx))
                            if not detection_fp:
                                continue
                            dist = compare_fingerprints_l1(
                                model_fp,
                                detection_fp,
                                min_overlap_neighbors=int(settings.FINGERPRINT_MIN_OVERLAP),
                            )
                            if dist <= float(settings.FINGERPRINT_MAX_DIST):
                                allowed.add((model_id, int(det_idx)))
                    if allowed:
                        allowed_pairs_by_title[name] = allowed
                        if settings.FINGERPRINT_DEBUG_LOG:
                            executor.log(
                                f"[重名过滤] '{name}': 模型={len(models)} 检测={len(detections)} → 允许配对={len(allowed)} "
                                f"(K={int(settings.FINGERPRINT_K)}, 阈值={float(settings.FINGERPRINT_MAX_DIST):.2f})",
                                log_callback,
                            )
            else:
                executor.log("[指纹检查] 指纹签名不一致，跳过本次过滤（节点位置可能已变化，需重新生成指纹缓存）", log_callback)
        else:
            executor.log("[指纹检查] 缓存文件不存在或无效，跳过指纹过滤（建议运行指纹缓存生成工具）", log_callback)
    else:
        if not fingerprint_enabled_setting:
            executor.log("[指纹检查] 指纹功能已禁用（FINGERPRINT_ENABLED=False）", log_callback)
        elif not has_graph_id:
            executor.log("[指纹检查] 图模型缺少graph_id，无法使用指纹过滤", log_callback)

    # [调试] 输出最终结果
    executor.log(
        f"[指纹检查] 指纹过滤最终状态: {'已启用' if fingerprint_filter_enabled else '未启用'}",
        log_callback,
    )
    
    return allowed_pairs_by_title, fingerprint_filter_enabled


def _check_relative_distance_ratio_match(
    model_node_pos: tuple[float, float],
    detected_node_pos: tuple[float, float],
    reference_model_positions: list[tuple[float, float]],
    reference_detected_positions: list[tuple[float, float]],
    tolerance: float = 0.30,
) -> bool:
    """
    使用相对距离比例检查节点是否匹配（X和Y分开计算）
    
    核心思想：
    - 计算待检查节点与所有参考节点的X间距和Y间距
    - 比较程序坐标系和检测坐标系中的距离比例
    - X间距只和X比较，Y间距只和Y比较
    - 允许一定容错（默认30%）
    
    Args:
        model_node_pos: 待检查的程序节点坐标
        detected_node_pos: 待检查的检测节点坐标
        reference_model_positions: 参考节点的程序坐标列表（唯一节点）
        reference_detected_positions: 参考节点的检测坐标列表（唯一节点）
        tolerance: 容错比例（0.30 = 30%）
    
    Returns:
        是否匹配
    """
    if len(reference_model_positions) < 2:
        return True  # 参考点不足，无法判断，放行
    
    # 计算与所有参考节点的X间距和Y间距
    model_x_distances = [abs(model_node_pos[0] - ref[0]) for ref in reference_model_positions]
    model_y_distances = [abs(model_node_pos[1] - ref[1]) for ref in reference_model_positions]
    
    detected_x_distances = [abs(detected_node_pos[0] - ref[0]) for ref in reference_detected_positions]
    detected_y_distances = [abs(detected_node_pos[1] - ref[1]) for ref in reference_detected_positions]
    
    # 检查X间距比例（分开检查）
    x_ratio_matches = 0
    x_ratio_checks = 0
    for i in range(len(reference_model_positions)):
        for j in range(i + 1, len(reference_model_positions)):
            model_dx_i = model_x_distances[i]
            model_dx_j = model_x_distances[j]
            detected_dx_i = detected_x_distances[i]
            detected_dx_j = detected_x_distances[j]
            
            # 跳过距离过小的（容易有噪声）
            if model_dx_i < 50 or model_dx_j < 50 or detected_dx_i < 10 or detected_dx_j < 10:
                continue
            
            x_ratio_checks += 1
            
            # 计算比例：距离i / 距离j
            model_ratio = model_dx_i / model_dx_j if model_dx_j > 0 else 0
            detected_ratio = detected_dx_i / detected_dx_j if detected_dx_j > 0 else 0
            
            # 检查比例是否一致（允许容错）
            max_ratio = max(model_ratio, detected_ratio, 0.01)
            if abs(model_ratio - detected_ratio) <= tolerance * max_ratio:
                x_ratio_matches += 1
    
    # 检查Y间距比例（分开检查）
    y_ratio_matches = 0
    y_ratio_checks = 0
    for i in range(len(reference_model_positions)):
        for j in range(i + 1, len(reference_model_positions)):
            model_dy_i = model_y_distances[i]
            model_dy_j = model_y_distances[j]
            detected_dy_i = detected_y_distances[i]
            detected_dy_j = detected_y_distances[j]
            
            # 跳过距离过小的
            if model_dy_i < 50 or model_dy_j < 50 or detected_dy_i < 10 or detected_dy_j < 10:
                continue
            
            y_ratio_checks += 1
            
            # 计算比例
            model_ratio = model_dy_i / model_dy_j if model_dy_j > 0 else 0
            detected_ratio = detected_dy_i / detected_dy_j if detected_dy_j > 0 else 0
            
            # 检查比例是否一致
            max_ratio = max(model_ratio, detected_ratio, 0.01)
            if abs(model_ratio - detected_ratio) <= tolerance * max_ratio:
                y_ratio_matches += 1
    
    # 判断：X和Y都要至少50%的比例检查通过
    x_pass = x_ratio_checks == 0 or (x_ratio_matches / x_ratio_checks >= 0.5)
    y_pass = y_ratio_checks == 0 or (y_ratio_matches / y_ratio_checks >= 0.5)
    
    return x_pass and y_pass


def collect_pair_collections(
    mappings: MappingData,
    allowed_pairs_by_title: Dict[str, set[tuple[str, int]]],
    fingerprint_filter_enabled: bool,
    executor=None,
    log_callback=None,
) -> PairCollections:
    base_pairs_prog: list[tuple[float, float]] = []
    base_pairs_win: list[tuple[float, float]] = []
    for name in mappings.shared_names:
        models = mappings.name_to_model_nodes.get(name, [])
        detections = mappings.name_to_detections.get(name, [])
        if len(models) == 1 and len(detections) == 1:
            model_item = models[0]
            detection_item = detections[0]
            base_pairs_prog.append((float(model_item.pos[0]), float(model_item.pos[1])))
            base_pairs_win.append((float(detection_item[0]), float(detection_item[1])))

    # 使用相对比例匹配进行筛选（替代旧的scale+offset方法）
    use_ratio_filter = len(base_pairs_prog) >= 2
    if use_ratio_filter and executor and log_callback:
        executor.log(
            f"[相对比例] 已启用（参考节点={len(base_pairs_prog)}个），X和Y独立检查，容错30%",
            log_callback,
        )
    
    all_pairs_prog: list[tuple[float, float]] = []
    all_pairs_win: list[tuple[float, float]] = []
    geometric_filtered_count = 0
    total_candidate_count = 0
    
    for name in mappings.shared_names:
        models = mappings.name_to_model_nodes.get(name, [])
        detections = mappings.name_to_detections.get(name, [])
        det_indices = mappings.name_to_det_indices.get(name, [])
        
        is_multi_instance = len(models) > 1 or len(detections) > 1
        
        for det_index, detection in enumerate(detections):
            det_global_index = int(det_indices[det_index]) if det_index < len(det_indices) else -1
            for model in models:
                total_candidate_count += 1
                
                # 第一步：指纹过滤（如果启用）
                if fingerprint_filter_enabled and name in allowed_pairs_by_title:
                    if (getattr(model, "id", ""), det_global_index) not in allowed_pairs_by_title[name]:
                        continue
                
                # 第二步：相对比例匹配（对多实例节点，即使通过了指纹过滤也再检查一次）
                if use_ratio_filter and is_multi_instance:
                    prog_x, prog_y = float(model.pos[0]), float(model.pos[1])
                    det_x, det_y = float(detection[0]), float(detection[1])
                    
                    # 使用相对距离比例检查是否匹配
                    is_match = _check_relative_distance_ratio_match(
                        model_node_pos=(prog_x, prog_y),
                        detected_node_pos=(det_x, det_y),
                        reference_model_positions=base_pairs_prog,
                        reference_detected_positions=base_pairs_win,
                        tolerance=0.30,  # 30%容错
                    )
                    
                    if not is_match:
                        geometric_filtered_count += 1
                        continue
                
                all_pairs_prog.append((float(model.pos[0]), float(model.pos[1])))
                all_pairs_win.append((float(detection[0]), float(detection[1])))
                
                # [调试] 记录保留的配对（用于诊断）
                if executor and log_callback and len(all_pairs_prog) <= 10:
                    executor.log(
                        f"  [配对{len(all_pairs_prog)}] '{name}': prog=({model.pos[0]:.1f},{model.pos[1]:.1f}) win=({detection[0]},{detection[1]})",
                        log_callback,
                    )
    
    # [调试] 输出配对统计信息
    if executor and log_callback:
        # 统计多实例节点
        multi_instance_names = [
            name for name in mappings.shared_names
            if len(mappings.name_to_model_nodes.get(name, [])) > 1 or len(mappings.name_to_detections.get(name, [])) > 1
        ]
        
        if multi_instance_names:
            executor.log(
                f"[配对统计] 多实例节点 {len(multi_instance_names)} 个: {sorted(multi_instance_names)[:5]}{'...' if len(multi_instance_names) > 5 else ''}",
                log_callback,
            )

        executor.log(
            f"[配对统计] 唯一节点对={len(base_pairs_prog)} 候选配对总数={total_candidate_count} 保留配对={len(all_pairs_prog)}",
            log_callback,
        )

        if use_ratio_filter:
            filter_mode = "二次筛选" if fingerprint_filter_enabled else "主要筛选"
            executor.log(
                f"[相对比例] 筛选完成({filter_mode}) 过滤={geometric_filtered_count}个配对",
                log_callback,
            )
        elif len(multi_instance_names) > 0:
            executor.log(
                f"[相对比例] 未启用（唯一节点对不足，需≥2，实际={len(base_pairs_prog)}）",
                log_callback,
            )
    
    return PairCollections(
        base_pairs_prog=base_pairs_prog,
        base_pairs_win=base_pairs_win,
        all_pairs_prog=all_pairs_prog,
        all_pairs_win=all_pairs_win,
    )

