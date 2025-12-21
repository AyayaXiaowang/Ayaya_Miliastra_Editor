from __future__ import annotations

"""
视觉识别后端实现（核心逻辑）。

职责：
- 统一客户区截图上的节点/端口识别、一步式识别缓存与标题近似映射；
- 为运行时自动化与工具脚本提供共享实现，避免在 `tools/` 中承载核心逻辑。

说明：
- 运行时代码与 CLI 均应通过门面 `app.automation.vision` 访问本模块提供的能力。
"""

from typing import List, Tuple, Optional, Dict
import hashlib
import numpy as np
import cv2
from PIL import Image

from pathlib import Path

from tools.color_block_detector_internal import NodeDetected
from app.automation.ports.port_types import PortDetected
from tools.one_shot_scene_recognizer import recognize_scene, RecognizedNode, RecognizedPort
from engine.nodes.port_index_mapper import map_port_index_to_name
from app.automation import capture as editor_capture
from engine.nodes import NodeDef
from app.automation.vision.ocr_utils import extract_chinese
from engine.utils.text.text_similarity import levenshtein_distance
from app.automation.editor.node_library_provider import (
    get_node_library,
    get_workspace_root,
)
from app.automation.vision.ocr_template_profile import resolve_ocr_template_profile_name
from app.automation.vision.ui_profile_params import get_port_header_height_px


def _fallback_project_root() -> Path:
    """在未设置默认 workspace 时，根据目录结构推断根目录。"""
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "assets").exists() and (parent / "tools").exists():
            return parent
    return current_file.parent.parent


def _resolve_workspace_root() -> Path:
    """优先使用 node_library_provider 注册的 workspace，再退回旧推断策略。"""
    try:
        return get_workspace_root()
    except ValueError:
        return _fallback_project_root()


# ============================
# 一步式识别缓存
# ============================

_recognition_cache: Optional[Dict] = None
_title_mapping_logs: List[Dict[str, object]] = []
_chinese_lookup_cache: Optional[Dict[str, List[str]]] = None
_chinese_lookup_source_id: Optional[int] = None
_chinese_length_index: Optional[Dict[int, List[str]]] = None
_title_mapping_cache: Dict[str, Tuple[str, Optional[int], bool]] = {}
_title_mapping_source_id: Optional[int] = None
_chinese_bigram_index: Optional[Dict[str, List[str]]] = None
_chinese_initial_index: Optional[Dict[str, List[str]]] = None
_MAX_TITLE_CANDIDATES = 128


def invalidate_cache() -> None:
    """显式失效一步式识别缓存。"""
    global _recognition_cache
    _recognition_cache = None
    # 不清理库缓存；仅清理一步式识别缓存


def get_template_dir() -> str:
    """返回节点模板目录路径。"""
    project_root = _resolve_workspace_root()
    profile_name = resolve_ocr_template_profile_name(project_root, preferred_locale="CN")
    template_dir = project_root / "assets" / "ocr_templates" / profile_name / "Node"
    return str(template_dir)


def _get_workspace_path() -> Path:
    return _resolve_workspace_root()


def _ensure_node_library() -> Dict[str, NodeDef]:
    workspace = _get_workspace_path()
    return get_node_library(workspace)


def _get_chinese_lookup(lib: Dict[str, NodeDef]) -> Dict[str, List[str]]:
    global _chinese_lookup_cache, _chinese_lookup_source_id, _chinese_length_index, _title_mapping_cache, _title_mapping_source_id
    if _chinese_lookup_cache is None or _chinese_lookup_source_id != id(lib):
        chinese_to_full_names: Dict[str, List[str]] = {}
        length_index: Dict[int, List[str]] = {}
        for node_def in lib.values():
            full_name = node_def.name
            cn_name = extract_chinese(full_name)
            if not cn_name:
                continue
            chinese_to_full_names.setdefault(cn_name, []).append(full_name)
            length_index.setdefault(len(cn_name), []).append(cn_name)
        _chinese_lookup_cache = chinese_to_full_names
        _chinese_length_index = length_index
        _chinese_lookup_source_id = id(lib)
        _rebuild_chinese_name_indices(chinese_to_full_names)
        _title_mapping_cache = {}
        _title_mapping_source_id = _chinese_lookup_source_id
    return _chinese_lookup_cache


def _get_length_index() -> Dict[int, List[str]]:
    return _chinese_length_index or {}


def _extract_bigrams(value: str) -> List[str]:
    normalized = (value or "").strip()
    if len(normalized) <= 1:
        return [normalized] if normalized else []
    seen: set[str] = set()
    grams: List[str] = []
    for index in range(len(normalized) - 1):
        gram = normalized[index:index + 2]
        if gram not in seen:
            seen.add(gram)
            grams.append(gram)
    return grams


def _rebuild_chinese_name_indices(chinese_lookup: Dict[str, List[str]]) -> None:
    global _chinese_bigram_index, _chinese_initial_index
    bigram_index: Dict[str, List[str]] = {}
    initial_index: Dict[str, List[str]] = {}
    for name in chinese_lookup.keys():
        if not name:
            continue
        for gram in _extract_bigrams(name):
            bigram_index.setdefault(gram, []).append(name)
        initial_index.setdefault(name[0], []).append(name)
    _chinese_bigram_index = bigram_index
    _chinese_initial_index = initial_index


def _get_bigram_index() -> Dict[str, List[str]]:
    return _chinese_bigram_index or {}


def _get_initial_index() -> Dict[str, List[str]]:
    return _chinese_initial_index or {}


def _collect_length_based_candidates(target_len: int) -> List[str]:
    if target_len <= 0:
        return []
    length_index = _get_length_index()
    tolerance = 1 if target_len <= 4 else 2
    names: List[str] = []
    seen: set[str] = set()
    for delta in range(-tolerance, tolerance + 1):
        bucket_len = target_len + delta
        if bucket_len <= 0:
            continue
        for name in length_index.get(bucket_len, []):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _extend_candidates(buffer: List[str], seen: set[str], items: List[str]) -> None:
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        buffer.append(item)
        if len(buffer) >= _MAX_TITLE_CANDIDATES:
            break


def _collect_candidate_names(title_cn: str, chinese_lookup: Dict[str, List[str]]) -> List[str]:
    target_len = len(title_cn)
    candidates: List[str] = []
    seen: set[str] = set()
    grams = _extract_bigrams(title_cn)
    bigram_index = _get_bigram_index()
    for gram in grams:
        _extend_candidates(candidates, seen, bigram_index.get(gram, []))
        if len(candidates) >= _MAX_TITLE_CANDIDATES:
            break
    if len(candidates) < 4 and title_cn:
        initial_list = _get_initial_index().get(title_cn[0], [])
        _extend_candidates(candidates, seen, initial_list)
    if len(candidates) < 4:
        length_candidates = _collect_length_based_candidates(target_len)
        _extend_candidates(candidates, seen, length_candidates)
    if not candidates:
        _extend_candidates(candidates, seen, list(chinese_lookup.keys()))
    return candidates


def _map_title_to_library(title_cn: str) -> Tuple[str, Optional[int], bool]:
    """将 OCR 标题（仅中文）映射为库内“完整正式名”。

    返回 (mapped_full_name, distance_or_None, used_fallback)。
    规则：
    - 先按“库名取中文”做精确匹配且唯一 → 返回完整库名（含英文/符号）。
    - 否则做变长近似匹配（Levenshtein）：选全局最小且唯一；相似度≥0.83 或 距离≤1 才接受。
    - 多解或跨类别重名时放弃回退，维持原中文标题。
    """
    global _title_mapping_cache, _title_mapping_source_id
    lib = _ensure_node_library()
    chinese_lookup = _get_chinese_lookup(lib)
    if not title_cn:
        return (title_cn, None, False)

    lib_id = _chinese_lookup_source_id
    if _title_mapping_source_id != lib_id:
        _title_mapping_cache = {}
        _title_mapping_source_id = lib_id

    cached = _title_mapping_cache.get(title_cn)
    if cached is not None:
        return cached

    def _finalize(mapped: str, distance_value: Optional[int], used: bool) -> Tuple[str, Optional[int], bool]:
        result = (mapped, distance_value, used)
        _title_mapping_cache[title_cn] = result
        return result

    # 1) 中文精确匹配（唯一）
    # 注意：同名节点可能在不同类别/端（client/server）重复注册，导致候选列表里出现重复字符串。
    # 这里以“唯一字符串”判定是否可安全回退，避免误判为多解从而放弃纠错。
    exact_fulls = chinese_lookup.get(title_cn, [])
    exact_unique = sorted({str(x) for x in exact_fulls if str(x)})
    if len(exact_unique) == 1:
        return _finalize(exact_unique[0], None, True)

    # 2) 变长近似匹配（全局唯一最优）
    best_cn: Optional[str] = None
    best_dist: Optional[int] = None
    tie = False
    candidate_names = _collect_candidate_names(title_cn, chinese_lookup)

    for cn_name in candidate_names:
        distance_value = levenshtein_distance(title_cn, cn_name)
        if best_dist is None or distance_value < int(best_dist):
            best_dist = int(distance_value)
            best_cn = cn_name
            tie = False
        elif best_dist is not None and int(distance_value) == int(best_dist):
            tie = True

    if best_cn is None or tie:
        return _finalize(title_cn, None, False)

    # 接受阈值：相似度≥0.83（例如 6→5），或距离≤1
    max_len = max(len(title_cn), len(best_cn))
    similarity = 1.0 - (float(best_dist) / float(max_len if max_len > 0 else 1))
    accept = (similarity >= 0.83) or (int(best_dist) <= 1)
    if not accept:
        return _finalize(title_cn, None, False)

    # 中文名对应的完整库名必须唯一（避免跨类别重名）
    # 同上：对候选做去重后再判唯一，避免因为重复注册导致 len>1 进而放弃纠错。
    full_candidates = chinese_lookup.get(best_cn, [])
    full_unique = sorted({str(x) for x in full_candidates if str(x)})
    if len(full_unique) != 1:
        return _finalize(title_cn, None, False)

    return _finalize(full_unique[0], int(best_dist) if best_dist is not None else None, True)


def _compute_window_digest(window_image: Image.Image) -> str:
    """计算窗口截图的内容摘要，用于识别缓存判定。"""
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(window_image.tobytes())
    hasher.update(str(window_image.size).encode("ascii"))
    return hasher.hexdigest()


def _ensure_cache(window_image: Image.Image) -> None:
    """确保缓存可用：若无或尺寸变化，则对画布区域执行一次一步式识别。"""
    global _recognition_cache
    window_digest = _compute_window_digest(window_image)
    if _recognition_cache is not None:
        cached_digest = _recognition_cache.get("window_digest")
        if cached_digest == window_digest:
            return

    # 计算节点图布置区域
    region_rect = editor_capture.get_region_rect(window_image, "节点图布置区域")
    region_x, region_y, region_w, region_h = region_rect
    canvas_image = window_image.crop((region_x, region_y, region_x + region_w, region_y + region_h))

    template_dir = get_template_dir()
    header_height_px = int(get_port_header_height_px(workspace_root=_get_workspace_path()))
    recognized_nodes_canvas = recognize_scene(
        canvas_image,
        template_dir,
        header_height=header_height_px,
        threshold=0.80,
    )

    # 将坐标转回窗口相对坐标（加上画布偏移）
    window_level_nodes: List[RecognizedNode] = []
    # 保留“原始 OCR 中文标题（未映射）+ 窗口相对矩形”用于调试与日志
    raw_title_rects_window: List[Tuple[str, Tuple[int, int, int, int]]] = []
    # 端口过滤调试信息已移除，仅保留最终端口结果

    for index, recognized in enumerate(recognized_nodes_canvas):
        rect_x, rect_y, rect_w, rect_h = recognized.rect
        shifted_rect = (int(rect_x + region_x), int(rect_y + region_y), int(rect_w), int(rect_h))
        shifted_ports: List[RecognizedPort] = []
        for port in recognized.ports:
            port_x, port_y, port_w, port_h = port.bbox
            shifted_bbox = (int(port_x + region_x), int(port_y + region_y), int(port_w), int(port_h))
            shifted_center = (int(port.center[0] + region_x), int(port.center[1] + region_y))
            shifted_ports.append(
                RecognizedPort(
                    side=port.side,
                    index=port.index,
                    kind=port.kind,
                    bbox=shifted_bbox,
                    center=shifted_center,
                    confidence=port.confidence,
                )
            )
        # 记录原始标题（仅中文，未做库映射）
        raw_title_rects_window.append((str(recognized.title_cn or ""), shifted_rect))
        # 标题近似回退映射（统一在 OCR 根源做归一化）
        mapped_title, distance_value, used = _map_title_to_library(recognized.title_cn)
        if used:
            _title_mapping_logs.append(
                {
                    "input_title": str(recognized.title_cn),
                    "mapped_title": str(mapped_title),
                    "hamming": None if distance_value is None else int(distance_value),
                    "distance": None if distance_value is None else int(distance_value),
                }
            )
        window_level_nodes.append(
            RecognizedNode(
                title_cn=mapped_title,
                rect=shifted_rect,
                ports=shifted_ports,
            )
        )

    _recognition_cache = {
        "window_size": window_image.size,
        "window_digest": window_digest,
        "region_rect": region_rect,
        "recognized_nodes": window_level_nodes,
        "raw_title_rects": raw_title_rects_window,
    }


def list_nodes(image: Image.Image) -> List[NodeDetected]:
    """列出窗口图像中的节点（名称+矩形中心），数据来自一步式识别缓存。"""
    _ensure_cache(image)
    if _recognition_cache is None:
        return []
    recognized_nodes: List[RecognizedNode] = _recognition_cache.get("recognized_nodes", [])
    nodes: List[NodeDetected] = []
    for recognized in recognized_nodes:
        rect_x, rect_y, rect_w, rect_h = recognized.rect
        center_x = int(rect_x + rect_w / 2)
        center_y = int(rect_y + rect_h / 2)
        area = int(rect_w * rect_h)
        nodes.append(
            NodeDetected(
                name_cn=recognized.title_cn,
                bbox=(int(rect_x), int(rect_y), int(rect_w), int(rect_h)),
                center=(center_x, center_y),
                area=area,
            )
        )
    return nodes


def get_last_raw_titles() -> List[str]:
    """返回最近一次一步式识别中的“原始中文标题”（未做库映射），顺序与检测顺序一致。"""
    if _recognition_cache is None:
        return []
    items = _recognition_cache.get("raw_title_rects", [])
    return [str(item[0]) for item in items]


def get_last_raw_title_rects() -> List[Tuple[str, Tuple[int, int, int, int]]]:
    """返回最近一次一步式识别中的“原始中文标题+窗口矩形”（未做库映射）。"""
    if _recognition_cache is None:
        return []
    items = _recognition_cache.get("raw_title_rects", [])
    # 明确转换为期望类型
    output: List[Tuple[str, Tuple[int, int, int, int]]] = []
    for title, rect in items:
        rect_x, rect_y, rect_w, rect_h = rect
        output.append((str(title), (int(rect_x), int(rect_y), int(rect_w), int(rect_h))))
    return output


def _iou(rect_a: Tuple[int, int, int, int], rect_b: Tuple[int, int, int, int]) -> float:
    rect_a_x, rect_a_y, rect_a_w, rect_a_h = rect_a
    rect_b_x, rect_b_y, rect_b_w, rect_b_h = rect_b
    rect_a_x2 = rect_a_x + rect_a_w
    rect_a_y2 = rect_a_y + rect_a_h
    rect_b_x2 = rect_b_x + rect_b_w
    rect_b_y2 = rect_b_y + rect_b_h
    inter_x1 = max(rect_a_x, rect_b_x)
    inter_y1 = max(rect_a_y, rect_b_y)
    inter_x2 = min(rect_a_x2, rect_b_x2)
    inter_y2 = min(rect_a_y2, rect_b_y2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = rect_a_w * rect_a_h
    area_b = rect_b_w * rect_b_h
    union_area = area_a + area_b - inter_area
    return float(inter_area) / float(union_area) if union_area > 0 else 0.0


def list_ports(image: Image.Image, node_bbox: Tuple[int, int, int, int]) -> List[PortDetected]:
    """返回与给定节点矩形最匹配的端口列表（来自一步式识别缓存）。"""
    _ensure_cache(image)
    if _recognition_cache is None:
        return []
    recognized_nodes: List[RecognizedNode] = _recognition_cache.get("recognized_nodes", [])
    best_match: Optional[RecognizedNode] = None
    best_iou = 0.0
    for recognized in recognized_nodes:
        score = _iou(recognized.rect, node_bbox)
        if score > float(best_iou):
            best_iou = float(score)
            best_match = recognized
    if best_match is None:
        return []
    ports: List[PortDetected] = []
    for port in best_match.ports:
        port_x, port_y, port_w, port_h = port.bbox
        # 名称映射：按节点名+侧别+序号求定义中的正式端口名
        mapped_name: Optional[str] = None
        if port.index is not None:
            mapped_name = map_port_index_to_name(best_match.title_cn, port.side, int(port.index))
        ports.append(
            PortDetected(
                name_cn=mapped_name or "",
                bbox=(int(port_x), int(port_y), int(port_w), int(port_h)),
                center=(int(port.center[0]), int(port.center[1])),
                side=port.side,
                kind=str(port.kind or "unknown"),
                index=int(port.index) if port.index is not None else None,
                confidence=float(port.confidence) if getattr(port, "confidence", None) is not None else None,
            )
        )
    # 按 y 排序，保持上到下的顺序
    ports.sort(key=lambda port_item: port_item.center[1])
    return ports


def phase_correlation_delta(prev_image: Image.Image, next_image: Image.Image) -> Tuple[float, float]:
    """
    估计从 prev 到 next 的内容位移（像素，next - prev）。
    使用相位相关，输入为相同尺寸的客户区截图。
    """
    prev_gray = cv2.cvtColor(np.array(prev_image), cv2.COLOR_RGB2GRAY)
    next_gray = cv2.cvtColor(np.array(next_image), cv2.COLOR_RGB2GRAY)
    prev_f32 = np.float32(prev_gray)
    next_f32 = np.float32(next_gray)
    shift, response = cv2.phaseCorrelate(prev_f32, next_f32)
    dx = float(shift[0])
    dy = float(shift[1])
    # response 越接近 1 表示越可信；纹理不足/遮挡/闪烁 UI 等情况下 response 可能很低，
    # 这时 shift 往往是随机噪声，直接返回会导致上层坐标映射（origin）快速漂移。
    min_response = 0.15
    if float(response) < float(min_response):
        return 0.0, 0.0
    return dx, dy


def get_and_clear_title_mapping_logs() -> List[Dict[str, object]]:
    """返回并清空最近一次一步式识别期间的标题近似回退日志。"""
    global _title_mapping_logs
    logs = list(_title_mapping_logs)
    _title_mapping_logs = []
    return logs



