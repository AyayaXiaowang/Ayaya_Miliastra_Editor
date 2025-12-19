# -*- coding: utf-8 -*-
"""
编辑器执行器模块
实现坐标校准和节点图步骤自动执行
"""

import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Callable, List
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor import editor_nodes
from app.automation.editor import editor_connect
from app.automation.ports._ports import normalize_kind_text, is_non_connectable_kind
from app.automation.input.common import (
    log_start,
    log_ok,
    log_fail,
    safe_print,
    DEFAULT_DRAG_MOUSE_UP_MS,
    compute_position_thresholds,
    sleep_seconds,
)
from app.automation.editor import executor_utils as _exec_utils
from engine.graph.models.graph_model import GraphModel, NodeModel
from app.automation.vision import list_nodes
from app.automation.editor.view_mapping import (
    estimate_content_motion,
    compute_clamped_step,
)
from app.automation.vision import get_last_raw_titles as _get_raw_titles
from app.automation.vision import get_last_raw_title_rects as _get_raw_title_rects
from app.automation.vision.node_detection import find_best_node_bbox as _find_best_node_bbox_ext, extract_chinese as _extract_chinese_ext
from app.automation.ports._type_utils import infer_type_from_value
from . import editor_mapping as _map
from . import editor_zoom as _zoom
from . import editor_exec_steps as _steps
from . import editor_recognition as _rec
from .node_snapshot import GraphSceneSnapshot
from engine.utils.text.text_similarity import chinese_similar
from app.automation.editor.node_library_provider import set_default_workspace_path
from app.automation.vision.ocr_template_profile import (
    resolve_ocr_template_profile_selection,
    set_default_ocr_template_profile,
)

from .editor_executor_debug import EditorExecutorDebugMixin
from .editor_executor_hooks import EditorExecutorHooksMixin
from .editor_executor_node_library import EditorExecutorNodeLibraryMixin
from .editor_executor_view_state import EditorExecutorViewStateMixin
from .editor_executor_visual import EditorExecutorVisualMixin


class EditorExecutor(
    EditorExecutorViewStateMixin,
    EditorExecutorHooksMixin,
    EditorExecutorVisualMixin,
    EditorExecutorNodeLibraryMixin,
    EditorExecutorDebugMixin,
):
    """编辑器自动执行器"""
    
    def __init__(self, workspace_path: Path, window_title: str = "千星沙箱"):
        self.workspace_path = workspace_path
        self.window_title = window_title

        # 统一在自动化入口设置默认 workspace，供视觉与节点库缓存复用
        set_default_workspace_path(workspace_path)

        # 初始化 DPI 感知（影响截图像素与系统分辨率读取）
        editor_capture.set_dpi_awareness()

        # OCR 模板 profile：根据当前显示设置自动选择（如 4K-100-CN / 4K-125-CN）
        selection = resolve_ocr_template_profile_selection(workspace_path)
        self.ocr_template_profile = selection.selected_profile_name
        self.ocr_template_profile_selection = selection
        # 也写入全局默认，供 vision_backend 等无法显式注入 executor 的路径复用
        set_default_ocr_template_profile(workspace_path, self.ocr_template_profile)
        
        # 坐标校准信息
        self.scale_ratio: Optional[float] = None  # 程序坐标到编辑器坐标的比例
        self.origin_node_pos: Optional[Tuple[float, float]] = None  # 原点节点在编辑器中的位置
        self.drag_distance_per_pixel: Optional[float] = None  # 每次拖动1像素对应的程序坐标距离
        
        # 模板路径（基于选定的 profile）
        templates_root = workspace_path / "assets" / "ocr_templates" / self.ocr_template_profile
        node_templates_root = templates_root / "Node"
        self.search_bar_template_path = templates_root / "search.png"
        self.search_bar_template_path2 = templates_root / "search2.png"
        self.node_settings_template_path = node_templates_root / "Settings.png"
        self.node_warning_template_path = node_templates_root / "Warning.png"
        self.node_add_template_path = node_templates_root / "Add.png"
        self.node_add_multi_template_path = node_templates_root / "Add_Multi.png"
        self.node_signal_template_path = node_templates_root / "Signal.png"

        # 节点定义库（懒加载）
        self._node_library = None
        self._node_defs_by_name: Dict[str, List[Any]] = {}

        # 最近一次右键呼出上下文菜单的编辑器坐标（用于定位节点搜索弹窗）
        self._last_context_click_editor_pos: Optional[Tuple[int, int]] = None

        # 快速模式开关（默认开启）：
        # - fast_mapping_mode: 优先使用"识别+几何拟合"直接建立比例与原点，成功则跳过锚点创建校准
        # - fast_create_mode: 创建节点时输入后直接回车确认首项，随后用可见性+位置阈值校验；失败再回退OCR候选点击
        # - skip_color_snap_if_allowed: 右键位置若已落在允许背景色上，则跳过颜色吸附扫描，直接在目标点右键
        self.fast_mapping_mode: bool = True
        self.fast_create_mode: bool = False
        self.skip_color_snap_if_allowed: bool = True
        # 连续执行期间的缩放一致性标记：当已在启动阶段确认过 50% 时为 True
        self.zoom_50_confirmed: bool = False
        # 快速链模式：连续执行连接/配置等步骤时跳过鼠标缓冲与等待
        self.fast_chain_mode: bool = False
        self._fast_chain_step_type: str = ""
        # 连续连线步骤的截图/OCR复用上下文
        self._connect_chain_context: Optional[Dict[str, Any]] = None
        self._connect_chain_dirty: bool = False
        # 可见节点同步后记录的坐标漂移（单步模式用于邻居参考）
        self._recent_node_position_deltas: Dict[str, Tuple[float, float]] = {}
        self._position_delta_token: int = -1
        # 节点创建顺序记录：供“最近锚点”策略使用
        self._created_node_history: list[str] = []
        self._created_node_lookup: set[str] = set()
        # 最近一次“创建节点”步骤的坐标推断信息（用于调试截图叠加）
        self._last_create_position_debug: Dict[str, Any] = {}
        # 视口同步缓存
        self._view_state_token: int = 0
        self._last_synced_view_state_token: int = -1
        self._last_connect_prepare_token: int = -1
        # 场景级截图与节点检测缓存：用于在无视口变更的前提下，跨步骤复用同一帧识别结果
        self.enable_scene_snapshot_optimization: bool = True
        self._scene_snapshot: Optional[GraphSceneSnapshot] = None
        # 识别阶段最近一次视图拟合策略与截图/检测缓存（由 editor_recognition 维护）
        self._last_view_mapping_strategy: str = ""
        self._last_recognition_screenshot: Optional[Image.Image] = None
        self._last_recognition_detected: Optional[list] = None
        # 步骤执行上下文（由执行线程按需写入）
        self._current_step_index: int = -1
        self._node_first_create_step_index: Dict[str, int] = {}
        self._single_step_target_todo_id: str = ""
        # 标记是否已通过锚点显式校准比例（区分于 RANSAC 推断）
        self._scale_calibrated_by_anchor: bool = False

    # ===== 快速链辅助 =====
    def set_fast_chain_step_type(self, step_type: str) -> None:
        """由执行线程注入当前步骤类型，用于限制快速链的生效范围。"""
        return super().set_fast_chain_step_type(step_type)

    def reset_fast_chain_step_type(self) -> None:
        return super().reset_fast_chain_step_type()

    def is_fast_chain_step_enabled(self) -> bool:
        """仅当快速链开启且当前步骤属于连接/配置类时才跳过等待。"""
        return super().is_fast_chain_step_enabled()

    # ===== 连续连线缓存 =====
    def invalidate_connect_chain_context(self, reason: str = "") -> None:
        return super().invalidate_connect_chain_context(reason)

    def begin_connect_chain_step(self) -> Optional[Dict[str, Any]]:
        return super().begin_connect_chain_step()

    def complete_connect_chain_step(self, context: Optional[Dict[str, Any]], success: bool) -> None:
        return super().complete_connect_chain_step(context, success)
    
    def _reset_view_state(self, reason: str = "") -> None:
        """重置与当前编辑器视口绑定的缓存状态。

        - 自增视口 token，并清空最近一次“识别预热”与“已同步视口”的 token
        - 失效场景级截图与节点检测缓存
        - 清空连续连线上下文与节点位移缓存
        - 清空识别阶段的首帧截图与检测结果缓存，避免在视口变化后误用旧画面
        """
        return super()._reset_view_state(reason)

    def mark_view_changed(self, reason: str = "") -> None:
        """标记视口发生变化，由执行步骤或上层在拖拽/缩放后调用。"""
        return super().mark_view_changed(reason)

    def get_scene_snapshot(self) -> GraphSceneSnapshot:
        """获取当前执行器绑定的场景级快照实例（按需懒初始化）。"""
        return super().get_scene_snapshot()

    def invalidate_scene_snapshot(self, reason: str = "") -> None:
        """显式失效场景级快照，用于执行完具有拖拽/布局变更效果的步骤后触发重识别。"""
        return super().invalidate_scene_snapshot(reason)

    # ===== 公共小工具（去重：等待/点击/输入 与 暂停/终止钩子） =====
    def _wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback=None,
    ) -> bool:
        """委托通用工具，统一等待钩子逻辑。"""
        return super()._wait_with_hooks(
            total_seconds,
            pause_hook,
            allow_continue,
            interval_seconds,
            log_callback,
        )

    def wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback=None,
    ) -> bool:
        """
        公开的分段等待接口：语义与 `_wait_with_hooks` 一致。

        跨模块调用推荐使用本方法，便于静态检查约束私有方法访问。
        """
        return super().wait_with_hooks(
            total_seconds=total_seconds,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            interval_seconds=interval_seconds,
            log_callback=log_callback,
        )


    def reset_mapping_state(self, log_callback=None) -> None:
        """清空上次执行残留的坐标映射与识别缓存，用于从根步骤开始全量执行前的干净环境。
        - 清空 scale_ratio / origin_node_pos / drag_distance_per_pixel
        - 清空最近一次上下文右键位置
        - 失效视觉识别一步式缓存
        """
        return super().reset_mapping_state(log_callback)

    def _ensure_node_library(self) -> None:
        return super()._ensure_node_library()

    def _resolve_node_def_by_name(self, node_name: str, preferred_category: str):
        return super()._resolve_node_def_by_name(node_name, preferred_category)

    def _get_node_def_for_model(self, node: NodeModel):
        """根据 NodeModel 获取 NodeDef（支持复合节点）。找不到则返回 None。"""
        return super()._get_node_def_for_model(node)

    # === 统一可视化输出 ===
    def _build_reference_panel_image(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
    ) -> Image.Image:
        """基于 overlays 中的 reference_panel 信息构造带参考面板的截图。

        会在 overlays['reference_panel'] 上打 '_embedded' 标记，以避免在同一帧重复合成。
        """
        return super()._build_reference_panel_image(screenshot, overlays)

    def _emit_visual(self, screenshot: Image.Image, overlays: Optional[dict], visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]]) -> None:
        """统一的可视化输出入口：所有涉及截图的步骤通过此方法将叠加层推送到监控面板。
        overlays 结构：{'rects': [...], 'circles': [...]}，与 UI 层保持一致。
        """
        return super()._emit_visual(screenshot, overlays, visual_callback)

    # 轻薄委托：文本输入（带暂停/终止钩子）
    def _input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
    ) -> bool:
        return super()._input_text_with_hooks(text, pause_hook, allow_continue, log_callback)

    def _right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        *,
        linger_seconds: float = 0.0,
    ) -> bool:
        return super()._right_click_with_hooks(
            screen_x,
            screen_y,
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            linger_seconds=linger_seconds,
        )

    def capture_and_emit(
        self,
        label: str = "",
        overlays_builder: Optional[Callable[[Image.Image], Optional[dict]]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        *,
        use_strict_window_capture: bool = False,
    ) -> Image.Image:
        """一次性完成：窗口截图 → 叠加区域 → 推送到监控。

        规范：至少叠加"节点图布置区域"矩形；调用方可通过 overlays_builder 追加叠加内容。
        返回本次截图，以便调用方继续使用。
        """
        return super().capture_and_emit(
            label=label,
            overlays_builder=overlays_builder,
            visual_callback=visual_callback,
            use_strict_window_capture=use_strict_window_capture,
        )

    def emit_visual(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    ) -> None:
        """
        公开的可视化输出接口：语义与 `_emit_visual` 一致。

        跨模块调用推荐使用本方法，而不是直接访问私有实现。
        """
        return super().emit_visual(screenshot, overlays, visual_callback)

    def _ensure_program_point_visible(
        self,
        program_x: float,
        program_y: float,
        margin_ratio: float = 0.10,
        max_steps: int = 8,
        pan_step_pixels: int = 400,
        log_callback: Optional[Callable[[str], None]] = None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        graph_model: Optional[GraphModel] = None,
        force_pan_if_inside_margin: bool = False,
    ) -> None:
        return _map.ensure_program_point_visible(
            self,
            program_x,
            program_y,
            margin_ratio,
            max_steps,
            pan_step_pixels,
            log_callback,
            pause_hook,
            allow_continue,
            visual_callback,
            graph_model,
            force_pan_if_inside_margin,
        )

    def ensure_program_point_visible(
        self,
        program_x: float,
        program_y: float,
        margin_ratio: float = 0.10,
        max_steps: int = 8,
        pan_step_pixels: int = 400,
        log_callback: Optional[Callable[[str], None]] = None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        graph_model: Optional[GraphModel] = None,
        force_pan_if_inside_margin: bool = False,
    ) -> None:
        """
        公共视口对齐入口：跨模块调用请使用本方法，而不要直接调用私有的
        `_ensure_program_point_visible`。
        """
        self._ensure_program_point_visible(
            program_x=program_x,
            program_y=program_y,
            margin_ratio=margin_ratio,
            max_steps=max_steps,
            pan_step_pixels=pan_step_pixels,
            log_callback=log_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            visual_callback=visual_callback,
            graph_model=graph_model,
            force_pan_if_inside_margin=force_pan_if_inside_margin,
        )

    def debug_capture_create_node_position(
        self,
        graph_model: GraphModel,
        node: NodeModel,
        program_x: float,
        program_y: float,
        log_callback=None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> None:
        return super().debug_capture_create_node_position(
            graph_model,
            node,
            program_x,
            program_y,
            log_callback,
            visual_callback,
        )

    def debug_capture_visible_node_ids(
        self,
        graph_model: GraphModel,
        log_callback=None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> None:
        return super().debug_capture_visible_node_ids(graph_model, log_callback, visual_callback)

    def _log(self, message: str, log_callback=None) -> None:
        """统一日志输出：控制台实时打印 + UI监控窗口回调"""
        safe_print(message)
        if log_callback:
            log_callback(message)

    def log(self, message: str, log_callback=None) -> None:
        """
        公开日志输出接口：语义与 `_log` 一致。

        跨模块调用推荐使用本方法，而非直接访问 `_log`。
        """
        self._log(message, log_callback)

    def _extract_chinese(self, text: str) -> str:
        return _extract_chinese_ext(text)

    def extract_chinese(self, text: str) -> str:
        """
        公开中文提取接口：语义与 `_extract_chinese` 一致。
        """
        return self._extract_chinese(text)

    def _poll_node_candidates(
        self,
        node_title: str,
        timeout_seconds: float,
        log_callback=None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        match_predicate: Optional[Callable[[str, str], bool]] = None,
    ) -> Tuple[Optional[Image.Image], List[Tuple[int, int, int, int, int, int]]]:
        """轮询截图，直到目标中文节点出现或超时。

        实际轮询次数为 ceil(timeout_seconds / interval)，至少为 1 次。
        """
        from app.automation.input.common import DEFAULT_WAIT_POLL_INTERVAL_SECONDS

        interval = DEFAULT_WAIT_POLL_INTERVAL_SECONDS
        attempts = max(1, int(math.ceil(timeout_seconds / interval)))
        normalized_target = self._extract_chinese(node_title)
        if not normalized_target:
            return None, []

        def _matched(det_cn: str) -> bool:
            if not det_cn:
                return False
            if match_predicate is not None:
                return bool(match_predicate(det_cn, normalized_target))
            return det_cn == normalized_target or normalized_target in det_cn or det_cn in normalized_target

        for _ in range(attempts):
            if pause_hook is not None:
                pause_hook()
            if allow_continue is not None and not allow_continue():
                self._log("用户终止/暂停，放弃等待锚点", log_callback)
                return None, []
            screenshot = editor_capture.capture_window_strict(self.window_title)
            if screenshot is None:
                screenshot = editor_capture.capture_window(self.window_title)
            if not screenshot:
                self._log("  ✗ 窗口截图失败(视觉识别)", log_callback)
                return None, []
            nodes = list_nodes(screenshot)
            self._log(f"  [方法] 视觉识别(list_nodes)：检测到 {len(nodes)} 个色块节点", log_callback)
            candidates: List[Tuple[int, int, int, int, int, int]] = []
            for nd in nodes:
                det_cn = self._extract_chinese(getattr(nd, "name_cn", "") or "")
                if not _matched(det_cn):
                    continue
                x, y, w, h = nd.bbox
                cx, cy = nd.center
                candidates.append((int(x), int(y), int(w), int(h), int(cx), int(cy)))
            if candidates:
                return screenshot, candidates
            if not self._wait_with_hooks(interval, pause_hook, allow_continue, 0.1, log_callback):
                return None, []
        return None, []

    def poll_node_candidates(
        self,
        node_title: str,
        timeout_seconds: float,
        log_callback=None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        match_predicate: Optional[Callable[[str, str], bool]] = None,
    ) -> Tuple[Optional[Image.Image], List[Tuple[int, int, int, int, int, int]]]:
        """
        公开节点候选轮询接口：语义与 `_poll_node_candidates` 一致。

        跨模块调用应通过本方法，而不是直接访问 `_poll_node_candidates`。
        """
        return self._poll_node_candidates(
            node_title,
            timeout_seconds,
            log_callback,
            pause_hook,
            allow_continue,
            match_predicate,
        )

    def _find_node_by_cn_window(self, name_cn: str, timeout_seconds: float, log_callback=None,
                                pause_hook: Optional[Callable[[], None]] = None,
                                allow_continue: Optional[Callable[[], bool]] = None):
        """在编辑器窗口截图中，使用统一视觉识别(list_nodes)查找指定中文名的节点。
        返回 (x, y, w, h, center_x, center_y)（均为窗口内相对坐标）；未找到返回 None。
        """
        screenshot, candidates = self._poll_node_candidates(
            name_cn,
            timeout_seconds,
            log_callback,
            pause_hook,
            allow_continue,
            match_predicate=lambda det, target: chinese_similar(det, target),
        )
        if not screenshot or not candidates:
            return None
        rel_x, rel_y, match_w, match_h, rel_cx, rel_cy = candidates[0]
        return (rel_x, rel_y, match_w, match_h, rel_cx, rel_cy)
    
    
    
    def calibrate_coordinates(self,
                              anchor_node_title: str,
                              anchor_program_pos: Tuple[float, float],
                              log_callback=None,
                              create_anchor_node: bool = True,
                              pause_hook: Optional[Callable[[], None]] = None,
                              allow_continue: Optional[Callable[[], bool]] = None,
                              visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
                              graph_model: Optional[GraphModel] = None) -> bool:
        return _map.calibrate_coordinates(
            self,
            anchor_node_title,
            anchor_program_pos,
            log_callback,
            create_anchor_node,
            pause_hook,
            allow_continue,
            visual_callback,
            graph_model,
        )

    def prepare_for_connect(self, log_callback=None) -> None:
        """进入连接前的识别预热（委托识别模块）"""
        return _rec.prepare_for_connect(self, log_callback)
    
    def verify_and_update_view_mapping_by_recognition(
        self,
        graph_model: GraphModel,
        log_callback=None,
        visual_callback=None,
        allow_degraded_fallback: bool = True,
    ) -> bool:
        return _rec.verify_and_update_view_mapping_by_recognition(
            self,
            graph_model,
            log_callback=log_callback,
            visual_callback=visual_callback,
            allow_degraded_fallback=allow_degraded_fallback,
        )
    
    def convert_program_to_editor_coords(self, program_x: float, program_y: float) -> Tuple[int, int]:
        return _map.convert_program_to_editor_coords(self, program_x, program_y)
    
    def convert_editor_to_screen_coords(self, editor_x: int, editor_y: int) -> Tuple[int, int]:
        return _map.convert_editor_to_screen_coords(self, editor_x, editor_y)
    
    def get_program_viewport_rect(self) -> Tuple[float, float, float, float]:
        return _map.get_program_viewport_rect(self)

    def recognize_visible_nodes(self, graph_model: GraphModel) -> Dict[str, Dict[str, Any]]:
        return _rec.recognize_visible_nodes(self, graph_model)

    def sync_visible_nodes_positions(
        self,
        graph_model: GraphModel,
        threshold_px: float = 40.0,
        log_callback=None,
    ) -> int:
        return _rec.synchronize_visible_nodes_positions(
            self,
            graph_model,
            threshold_px=threshold_px,
            log_callback=log_callback,
        )
    
    def will_connect_too_far(self, graph_model: GraphModel, src_node_id: str, dst_node_id: str, margin_ratio: float = 0.10) -> tuple[bool, str]:
        return _map.will_connect_too_far(self, graph_model, src_node_id, dst_node_id, margin_ratio)
    
    def is_node_visible_by_id(self, graph_model: GraphModel, node_id: str) -> bool:
        return _rec.is_node_visible_by_id(self, graph_model, node_id)
    
    def execute_step(self, todo_item: Dict[str, Any], graph_model: GraphModel, log_callback=None, pause_hook: Optional[Callable[[], None]] = None, allow_continue: Optional[Callable[[], bool]] = None, visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None) -> bool:
        return _steps.execute_step(self, todo_item, graph_model, log_callback, pause_hook, allow_continue, visual_callback)
    
    def _execute_create_node(self, todo_item: Dict[str, Any], graph_model: GraphModel, log_callback=None, pause_hook: Optional[Callable[[], None]] = None, allow_continue: Optional[Callable[[], bool]] = None, visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None) -> bool:
        return editor_nodes.execute_create_node(self, todo_item, graph_model, log_callback, pause_hook, allow_continue, visual_callback)

    def _find_best_node_bbox(
        self,
        screenshot: Image.Image,
        title_cn: str,
        program_pos: Tuple[float, float],
        debug: Optional[Dict[str, Any]] = None,
        detected_nodes: Optional[list] = None,
    ) -> Tuple[int, int, int, int]:
        return _rec._find_best_node_bbox(self, screenshot, title_cn, program_pos, debug, detected_nodes)

    def find_best_node_bbox(
        self,
        screenshot: Image.Image,
        title_cn: str,
        program_pos: Tuple[float, float],
        debug: Optional[Dict[str, Any]] = None,
        detected_nodes: Optional[list] = None,
    ) -> Tuple[int, int, int, int]:
        """
        公开节点 bbox 查找接口：语义与 `_find_best_node_bbox` 一致。
        """
        return self._find_best_node_bbox(
            screenshot=screenshot,
            title_cn=title_cn,
            program_pos=program_pos,
            debug=debug,
            detected_nodes=detected_nodes,
        )

    # ===== 画布缩放一致性（每步前强制检查/校正到 50%） =====
    def ensure_zoom_ratio_50(
        self,
        log_callback=None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> bool:
        return _zoom.ensure_zoom_ratio_50(self, log_callback, pause_hook, allow_continue, visual_callback)

    
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
        return super()._debug_log_branch_ambiguity(
            graph_model=graph_model,
            name_to_model_nodes=name_to_model_nodes,
            name_to_detections=name_to_detections,
            s=s,
            tx=tx,
            ty=ty,
            epsilon_px=epsilon_px,
            log_callback=log_callback,
        )

    def get_node_def_for_model(self, node: NodeModel):
        """
        公开节点定义查询接口：语义与 `_get_node_def_for_model` 一致。
        """
        return self._get_node_def_for_model(node)

    def right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        *,
        linger_seconds: float = 0.0,
    ) -> bool:
        """
        公开的右键点击接口：语义与 `_right_click_with_hooks` 一致。
        """
        return self._right_click_with_hooks(
            screen_x=screen_x,
            screen_y=screen_y,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            log_callback=log_callback,
            visual_callback=visual_callback,
            linger_seconds=linger_seconds,
        )

    def input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
    ) -> bool:
        """
        公开的文本输入接口：语义与 `_input_text_with_hooks` 一致。
        """
        return self._input_text_with_hooks(
            text=text,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            log_callback=log_callback,
        )

    def get_last_context_click_editor_pos(self) -> Optional[Tuple[int, int]]:
        """
        获取最近一次用于弹出上下文菜单的编辑器坐标。
        """
        return self._last_context_click_editor_pos

    def set_last_context_click_editor_pos(self, editor_x: int, editor_y: int) -> None:
        """
        更新最近一次用于弹出上下文菜单的编辑器坐标。
        """
        self._last_context_click_editor_pos = (int(editor_x), int(editor_y))


