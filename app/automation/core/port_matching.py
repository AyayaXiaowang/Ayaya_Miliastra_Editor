from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

BBox = Tuple[int, int, int, int]
ScreenPoint = Tuple[int, int]

from app.automation import capture as editor_capture
from app.automation.core.editor_mapping import MIN_SCALE_RATIO, FIXED_SCALE_RATIO
from app.automation.core.node_snapshot import NodePortsSnapshotCache
from app.automation.core.structured_logging import StructuredLogger
from app.automation.core.ui_constants import NODE_VIEW_WIDTH_PX, NODE_VIEW_HEIGHT_PX
from app.automation.input.common import build_graph_region_overlay, compute_position_thresholds
from app.automation.ports._ports import normalize_kind_text
from app.automation.ports.port_picker import (
    filter_screen_port_candidates,
    pick_port_center_for_node,
)
from app.automation.ports.port_type_inference import safe_get_port_type_from_node_def
from app.automation.vision import list_nodes, list_ports as list_ports_for_bbox, invalidate_cache
from engine.graph.models.graph_model import NodeModel
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.graph.common import is_selection_input_port


def _is_within_position_threshold(
    executor,
    bbox: BBox,
    program_pos: Tuple[float, float],
) -> bool:
    """使用当前缩放比例计算位置容差，并判断识别到的位置框是否在可接受范围内。"""
    if bbox[2] <= 0:
        return False
    expected_x, expected_y = executor.convert_program_to_editor_coords(program_pos[0], program_pos[1])
    bbox_x, bbox_y, _, _ = bbox
    scale_value = float(executor.scale_ratio or 1.0)
    threshold_x, _ = compute_position_thresholds(scale_value)
    delta_x = float(bbox_x - expected_x)
    delta_y = float(bbox_y - expected_y)
    return (delta_x * delta_x + delta_y * delta_y) <= (threshold_x * threshold_x)


def _resolve_selection_kind(
    port_name: Optional[str],
    preferred_kind: Optional[str],
) -> Optional[str]:
    """综合“外部期望类型”和端口名推断最终用于筛选的端口类型。"""
    if isinstance(preferred_kind, str) and preferred_kind in ("flow", "data"):
        return preferred_kind
    if isinstance(port_name, str) and port_name:
        return "flow" if is_flow_port_name(port_name) else "data"
    return None


def _model_kind_for(node_obj: NodeModel, port_name: str, want_input: bool) -> str:
    """结合节点模型与端口名推断模型侧的端口类型标签（flow/data）。"""
    if (not want_input) and (node_obj.title == "多分支"):
        return "flow"
    return "flow" if is_flow_port_name(str(port_name or "")) else "data"


def _ordinal_in_model(
    node_obj: NodeModel,
    port_name: str,
    want_input: bool,
    kind_expect: Optional[str],
) -> Optional[int]:
    """根据端口名和期望类型，在模型定义中计算该端口的序号（用于序号回退策略）。

    约定：
    - 流程端口仅统计流程口；
    - 数据输入端口会显式排除“选择端口”（如发送/监听信号的“信号名”、结构体节点的“结构体名”），
      这些端口在 UI 中通过选择控件或对话框设置，不参与常规连线；
    - 其他场景按完整端口列表顺序参与序号计算。
    """
    if not isinstance(port_name, str) or port_name == "":
        return None

    if want_input:
        all_ports = list(node_obj.inputs or [])
    else:
        all_ports = list(node_obj.outputs or [])

    all_names = [port_def.name for port_def in all_ports]

    if kind_expect == "flow":
        filtered_names = [
            name
            for name in all_names
            if is_flow_port_name(name) or ((not want_input) and node_obj.title == "多分支")
        ]
    elif kind_expect == "data":
        if want_input:
            filtered_names = [
                name
                for name in all_names
                if (not is_flow_port_name(name))
                and (not is_selection_input_port(node_obj, name))
            ]
        else:
            filtered_names = [name for name in all_names if not is_flow_port_name(name)]
    else:
        filtered_names = all_names

    if port_name in filtered_names:
        return int(filtered_names.index(port_name))
    return None


def _brief_candidates(ports_list: List[Any]) -> str:
    """生成端口候选的简要描述字符串，便于日志查看。"""
    items: List[str] = []
    for index, port in enumerate(ports_list):
        mapped_name = str(getattr(port, "name_cn", "") or "")
        kind_text = normalize_kind_text(getattr(port, "kind", ""))
        items.append(f"#{index}:{mapped_name or '?'}[{kind_text}]")
    return ", ".join(items)


def _find_center_index(
    ports_list: List[Any],
    center: ScreenPoint,
) -> Optional[int]:
    """在端口列表中按中心点坐标精确查找命中序号。"""
    center_x, center_y = int(center[0]), int(center[1])
    for index, port in enumerate(ports_list):
        if int(port.center[0]) == center_x and int(port.center[1]) == center_y:
            return index
    return None


def _find_by_center(ports_list: List[Any], center: ScreenPoint) -> Optional[Any]:
    """在端口列表中按中心点坐标精确查找端口对象。"""
    hit_index = _find_center_index(ports_list, center)
    if hit_index is None:
        return None
    return ports_list[hit_index]


def _ordinal_of_screen_center(
    center_xy: ScreenPoint,
    ordered_ports: List[Any],
) -> Optional[int]:
    """在按屏幕顺序排序的端口列表中，查找给定中心点命中的序号。"""
    return _find_center_index(ordered_ports, center_xy)


@dataclass
class ConnectionFrameState:
    executor: Any
    reuse_context: Optional[Dict[str, Any]]
    screenshot: Image.Image
    screenshot_token: int
    node_snapshots: Dict[str, NodePortsSnapshotCache] = field(default_factory=dict)
    detected_nodes_cache: Optional[List[Any]] = None

    @classmethod
    def create(
        cls,
        executor,
        reuse_context: Optional[Dict[str, Any]],
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    ) -> Optional["ConnectionFrameState"]:
        screenshot = None
        if reuse_context is not None:
            screenshot = reuse_context.get("screenshot")
        if screenshot is None:
            screenshot = executor.capture_and_emit(
                label="连接-初始",
                overlays_builder=build_graph_region_overlay,
                visual_callback=visual_callback,
                use_strict_window_capture=True,
            )
            if reuse_context is not None:
                reuse_context["screenshot"] = screenshot
        if not screenshot:
            return None
        screenshot_token = id(screenshot)
        node_snapshots = {}
        if reuse_context is not None:
            reuse_context["screenshot_token"] = screenshot_token
            node_snapshots = reuse_context.get("node_snapshots") or {}
            reuse_context["node_snapshots"] = node_snapshots
        return cls(
            executor=executor,
            reuse_context=reuse_context,
            screenshot=screenshot,
            screenshot_token=screenshot_token,
            node_snapshots=node_snapshots,
        )

    def _get_cached_detected_nodes(self) -> Optional[list]:
        if self.reuse_context is None:
            return None
        ctx_token = self.reuse_context.get("detected_nodes_token")
        if isinstance(ctx_token, int) and ctx_token == self.screenshot_token:
            cached = self.reuse_context.get("detected_nodes")
            if isinstance(cached, list):
                return cached
        return None

    def _store_detected_nodes(self, nodes: list) -> None:
        if self.reuse_context is None:
            return
        self.reuse_context["detected_nodes"] = nodes
        self.reuse_context["detected_nodes_token"] = self.screenshot_token

    def ensure_detected_nodes(self) -> list:
        if self.detected_nodes_cache is None:
            cached = self._get_cached_detected_nodes()
            if cached is not None:
                self.detected_nodes_cache = cached
            else:
                self.detected_nodes_cache = list_nodes(self.screenshot)
                self._store_detected_nodes(self.detected_nodes_cache)
        return self.detected_nodes_cache

    def get_snapshot(
        self,
        node_id: str,
        node_obj: NodeModel,
        tag: str,
        dbg: Dict[str, Any],
        log_callback,
    ) -> Optional[NodePortsSnapshotCache]:
        cache = self.node_snapshots.get(node_id)
        if cache is None:
            cache = NodePortsSnapshotCache(self.executor, node_obj, log_callback)
            self.node_snapshots[node_id] = cache
        if cache.can_reuse_for_frame(self.screenshot):
            dbg["snapshot_reuse"] = True
            return cache
        ok = cache.refresh(
            reason=f"连接/{tag}",
            refresh_bbox=True,
            screenshot=self.screenshot,
            debug=dbg,
            detected_nodes=self.ensure_detected_nodes(),
        )
        if not ok:
            return None
        return cache


@dataclass
class PortSelectionResult:
    src_center: Tuple[int, int]
    dst_center: Tuple[int, int]
    src_selection_kind: Optional[str]
    dst_selection_kind: Optional[str]
    src_ports_all: List[Any]
    dst_ports_all: List[Any]
    src_screen_candidates: List[Any]
    dst_screen_candidates: List[Any]


class PortMatchingService:
    def __init__(
        self,
        executor,
        log_callback,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.executor = executor
        self.log_callback = log_callback
        self.visual_callback = visual_callback
        self.trace_context = dict(trace_context) if trace_context else {}
        self.logger = StructuredLogger(
            executor,
            log_callback,
            prefix="[连接] ",
            context=self.trace_context,
        )

    def _log_trace(self, category: str, message: str, **details: Any) -> None:
        self.logger.log(category, message, **details)

    def _log_bbox_side(
        self,
        tag: str,
        node_obj: NodeModel,
        bbox: BBox,
        dbg: Dict[str, Any],
    ) -> None:
        strict_mode = bool(dbg.get("strict_connect_mode"))
        expected_xy = dbg.get("expected_editor") or (0, 0)
        roi = dbg.get("roi") or (0, 0, 0, 0)
        pos_th = dbg.get("pos_threshold_px") or 0
        chosen = dbg.get("chosen") or {}
        failed_reason = dbg.get("failed_reason")
        in_roi_list = dbg.get("in_roi_candidates") or []
        out_roi_list = dbg.get("out_of_roi_named_candidates") or []
        status = "通过" if (bbox[2] > 0 and failed_reason is None) else "未通过"
        pos_th_y = dbg.get("pos_threshold_py") or pos_th
        self.logger.log(
            "定位",
            f"[{tag}] 标题: '{node_obj.title}'",
            expected=expected_xy,
            roi=roi,
            tol=(pos_th, pos_th_y),
            status=status,
        )
        if bbox[2] > 0:
            bx, by, bw, bh = bbox
            dx = int(bx - int(expected_xy[0]))
            dy = int(by - int(expected_xy[1]))
            dist2 = dx * dx + dy * dy
            self.logger.log(
                "定位",
                f"[{tag}] 检测到位置框",
                bbox=(bx, by, bw, bh),
                delta=(dx, dy),
                delta2=dist2,
            )
        else:
            self.logger.log("定位", f"[{tag}] 未在搜索范围内检测到有效位置框")
        self.logger.log(
            "定位",
            f"[{tag}] 搜索范围内同名候选",
            in_roi=len(in_roi_list),
            out_roi=len(out_roi_list),
        )
        if strict_mode and out_roi_list:
            self.logger.log(
                "定位",
                f"[{tag}] 连接严格模式：存在搜索范围外同名候选，已禁止回退到全局最近节点",
                out_of_roi_count=len(out_roi_list),
            )
        if chosen:
            cb = chosen.get("bbox") or (0, 0, 0, 0)
            self.logger.log(
                "定位",
                f"[{tag}] 选择评估",
                bbox=cb,
                dist2=chosen.get("dist2"),
                threshold2=chosen.get("threshold2"),
            )
        if failed_reason:
            self.logger.log("定位", f"[{tag}] 未通过原因", reason=str(failed_reason))
        if bbox[2] <= 0 and in_roi_list == [] and out_roi_list:
            for i, ob in enumerate(out_roi_list[:3]):
                self.logger.log("定位", f"[{tag}] 搜索范围外同名候选#{i+1}", bbox=ob)

    def _build_position_debug_overlays(
        self,
        frame_state: ConnectionFrameState,
        src_node: NodeModel,
        dst_node: NodeModel,
    ) -> Dict[str, Any]:
        rects: List[dict] = []
        circles: List[dict] = []

        def _roi_for(program_pos: Tuple[float, float], label: str, color: Tuple[int, int, int]) -> None:
            expected_x, expected_y = self.executor.convert_program_to_editor_coords(program_pos[0], program_pos[1])
            scale = float(self.executor.scale_ratio or 1.0)
            pos_threshold_px, pos_threshold_py = compute_position_thresholds(scale)
            roi_left = int(expected_x - pos_threshold_px)
            roi_top = int(expected_y - pos_threshold_py)
            roi_w = int(pos_threshold_px * 2)
            roi_h = int(pos_threshold_py * 2)
            rects.append({"bbox": (roi_left, roi_top, roi_w, roi_h), "color": color, "label": f"搜索范围-{label}"})
            center_x = int(expected_x + (NODE_VIEW_WIDTH_PX * scale) * 0.5)
            center_y = int(expected_y + (NODE_VIEW_HEIGHT_PX * scale) * 0.5)
            circles.append({"center": (center_x, center_y), "radius": 6, "color": color, "label": f"期望位置-{label}"})

        _roi_for(src_node.pos, "源", (255, 120, 120))
        _roi_for(dst_node.pos, "目标", (120, 200, 120))

        all_nodes = frame_state.ensure_detected_nodes()
        src_cn = self.executor.extract_chinese(src_node.title)
        dst_cn = self.executor.extract_chinese(dst_node.title)
        for detected in all_nodes:
            name_cn = self.executor.extract_chinese(str(getattr(detected, "name_cn", "") or ""))
            if name_cn and (
                name_cn == src_cn
                or src_cn in name_cn
                or name_cn in src_cn
                or name_cn == dst_cn
                or dst_cn in name_cn
                or name_cn in dst_cn
            ):
                bx, by, bw, bh = detected.bbox
                rects.append(
                    {
                        "bbox": (int(bx), int(by), int(bw), int(bh)),
                        "color": (140, 140, 140),
                        "label": f"同名: {str(detected.name_cn or '')}",
                    }
                )
        return {"rects": rects, "circles": circles}

    def _try_scale_reestimate(
        self,
        frame_state: ConnectionFrameState,
        src_node: NodeModel,
        dst_node: NodeModel,
        src_bbox: BBox,
        dst_bbox: BBox,
        src_snapshot: NodePortsSnapshotCache,
        dst_snapshot: NodePortsSnapshotCache,
        src_debug: Dict[str, Any],
        dst_debug: Dict[str, Any],
        src_ok: bool,
        dst_ok: bool,
    ) -> Optional[Tuple[BBox, BBox, Dict[str, Any], Dict[str, Any]]]:
        """在一端已通过、一端未通过的情况下，尝试基于两点距离回退缩放并重算原点。"""
        passed_side: Optional[str] = None
        failed_side: Optional[str] = None
        if src_ok and not dst_ok:
            passed_side = "src"
            failed_side = "dst"
        elif dst_ok and not src_ok:
            passed_side = "dst"
            failed_side = "src"
        if passed_side is None or failed_side is None:
            return None

        fail_dbg = dst_debug if failed_side == "dst" else src_debug
        out_list = fail_dbg.get("out_of_roi_named_candidates") or []
        if len(out_list) != 1:
            return None

        src_exp_x, src_exp_y = self.executor.convert_program_to_editor_coords(src_node.pos[0], src_node.pos[1])
        dst_exp_x, dst_exp_y = self.executor.convert_program_to_editor_coords(dst_node.pos[0], dst_node.pos[1])
        pass_bx, pass_by = (src_bbox[0], src_bbox[1]) if passed_side == "src" else (dst_bbox[0], dst_bbox[1])
        cand_bx, cand_by, _, _ = out_list[0]
        prog_dx = float(dst_node.pos[0] - src_node.pos[0])
        prog_dy = float(dst_node.pos[1] - src_node.pos[1])
        win_dx = float(cand_bx - pass_bx) if passed_side == "src" else float(pass_bx - cand_bx)
        win_dy = float(cand_by - pass_by) if passed_side == "src" else float(pass_by - cand_by)
        scale_candidates: List[float] = []
        if prog_dx != 0.0:
            sx = abs(win_dx / prog_dx)
            if 0.05 < sx < 10.0:
                scale_candidates.append(sx)
        if prog_dy != 0.0:
            sy = abs(win_dy / prog_dy)
            if 0.05 < sy < 10.0:
                scale_candidates.append(sy)
        if len(scale_candidates) == 0:
            return None

        s_new = sum(scale_candidates) / float(len(scale_candidates))
        if s_new <= MIN_SCALE_RATIO:
            self.logger.log("定位", "回退缩放估计异常（结果趋近0），放弃本次重估")
            return None

        old_s = float(self.executor.scale_ratio or FIXED_SCALE_RATIO)
        self.executor.scale_ratio = FIXED_SCALE_RATIO
        if passed_side == "src":
            self.executor.origin_node_pos = (
                int(pass_bx - src_node.pos[0] * self.executor.scale_ratio),
                int(pass_by - src_node.pos[1] * self.executor.scale_ratio),
            )
        else:
            self.executor.origin_node_pos = (
                int(pass_bx - dst_node.pos[0] * self.executor.scale_ratio),
                int(pass_by - dst_node.pos[1] * self.executor.scale_ratio),
            )
        self.logger.log(
            "定位",
            "回退：基于两点距离估计缩放并重算原点",
            estimated_scale=s_new,
            old_scale=old_s,
        )
        invalidate_cache()
        src_debug2: Dict[str, Any] = {}
        dst_debug2: Dict[str, Any] = {}
        if not src_snapshot.refresh(
            reason="连接/源-重估",
            refresh_bbox=True,
            screenshot=frame_state.screenshot,
            debug=src_debug2,
            detected_nodes=frame_state.ensure_detected_nodes(),
        ):
            return None
        if not dst_snapshot.refresh(
            reason="连接/目标-重估",
            refresh_bbox=True,
            screenshot=frame_state.screenshot,
            debug=dst_debug2,
            detected_nodes=frame_state.ensure_detected_nodes(),
        ):
            return None
        src_bbox2 = src_snapshot.node_bbox
        dst_bbox2 = dst_snapshot.node_bbox
        src_ok2 = _is_within_position_threshold(self.executor, src_bbox2, src_node.pos)
        dst_ok2 = _is_within_position_threshold(self.executor, dst_bbox2, dst_node.pos)
        if src_ok2 and dst_ok2:
            return src_bbox2, dst_bbox2, src_debug2, dst_debug2
        self.logger.log("定位", "重估后仍未能同时定位到两端，放弃回退")
        return None

    def ensure_valid_bboxes(
        self,
        frame_state: ConnectionFrameState,
        src_node: NodeModel,
        dst_node: NodeModel,
        src_snapshot: NodePortsSnapshotCache,
        dst_snapshot: NodePortsSnapshotCache,
    ) -> Optional[Tuple[BBox, BBox, Dict[str, Any], Dict[str, Any]]]:
        src_bbox = src_snapshot.node_bbox
        dst_bbox = dst_snapshot.node_bbox
        src_debug: Dict[str, Any] = {}
        dst_debug: Dict[str, Any] = {}

        src_ok = _is_within_position_threshold(self.executor, src_bbox, src_node.pos)
        dst_ok = _is_within_position_threshold(self.executor, dst_bbox, dst_node.pos)
        if src_ok and dst_ok:
            self._log_trace(
                "定位",
                "节点位置通过",
                screenshot_token=frame_state.screenshot_token,
                src_bbox=src_bbox,
                dst_bbox=dst_bbox,
            )
            return src_bbox, dst_bbox, src_debug, dst_debug

        self._log_bbox_side("源", src_node, src_bbox, src_debug)
        self._log_bbox_side("目标", dst_node, dst_bbox, dst_debug)

        if self.visual_callback is not None:
            overlays = self._build_position_debug_overlays(frame_state, src_node, dst_node)
            self.visual_callback(frame_state.screenshot, overlays)

        reestimate_result = self._try_scale_reestimate(
            frame_state=frame_state,
            src_node=src_node,
            dst_node=dst_node,
            src_bbox=src_bbox,
            dst_bbox=dst_bbox,
            src_snapshot=src_snapshot,
            dst_snapshot=dst_snapshot,
            src_debug=src_debug,
            dst_debug=dst_debug,
            src_ok=src_ok,
            dst_ok=dst_ok,
        )
        if reestimate_result is not None:
            src_bbox_new, dst_bbox_new, src_debug_new, dst_debug_new = reestimate_result
            self._log_trace(
                "定位",
                "缩放重估后节点位置通过",
                screenshot_token=frame_state.screenshot_token,
                src_bbox=src_bbox_new,
                dst_bbox=dst_bbox_new,
            )
            return src_bbox_new, dst_bbox_new, src_debug_new, dst_debug_new

        return None

    def _dump_ports(
        self,
        tag: str,
        ports_list: List[Any],
        node_def: Any,
    ) -> None:
        for port_obj in ports_list:
            mapped_name = str(getattr(port_obj, "name_cn", "") or "")
            declared_type = ""
            if node_def is not None and mapped_name:
                is_input_for_port = getattr(port_obj, "side", "") == "left"
                declared_type = safe_get_port_type_from_node_def(
                    node_def,
                    mapped_name,
                    is_input=is_input_for_port,
                )
            self.logger.log(
                "端口",
                f"[{tag}] idx={str(getattr(port_obj,'index',None))} side={str(port_obj.side)} name='{mapped_name}'",
                decl=str(declared_type),
                center=(int(port_obj.center[0]), int(port_obj.center[1])),
            )

    def _select_screen_candidates(
        self,
        src_ports_all: List[Any],
        dst_ports_all: List[Any],
        src_selection_kind: Optional[str],
        dst_selection_kind: Optional[str],
    ) -> Tuple[List[Any], List[Any]]:
        src_screen_cands = filter_screen_port_candidates(
            src_ports_all,
            preferred_side="right",
            expected_kind=src_selection_kind,
        )
        dst_screen_cands = filter_screen_port_candidates(
            dst_ports_all,
            preferred_side="left",
            expected_kind=dst_selection_kind,
        )
        self.logger.log(
            "端口",
            "[序号] 屏幕候选(源 从上到下)",
            text=_brief_candidates(src_screen_cands),
        )
        self.logger.log(
            "端口",
            "[序号] 屏幕候选(目标 从上到下)",
            text=_brief_candidates(dst_screen_cands),
        )
        return src_screen_cands, dst_screen_cands

    def build_port_selection(
        self,
        screenshot: Image.Image,
        src_node: NodeModel,
        dst_node: NodeModel,
        src_snapshot: NodePortsSnapshotCache,
        dst_snapshot: NodePortsSnapshotCache,
        src_port_name: Optional[str],
        dst_port_name: Optional[str],
        src_expected_kind: Optional[str],
        dst_expected_kind: Optional[str],
    ) -> Optional[PortSelectionResult]:
        src_ports_all = src_snapshot.ports
        dst_ports_all = dst_snapshot.ports
        src_def = self.executor.get_node_def_for_model(src_node)
        dst_def = self.executor.get_node_def_for_model(dst_node)

        src_selection_kind = _resolve_selection_kind(src_port_name, src_expected_kind)
        dst_selection_kind = _resolve_selection_kind(dst_port_name, dst_expected_kind)

        self._dump_ports("源候选", [p for p in src_ports_all if p.side == "right"], src_def)
        self._dump_ports("源(回退)候选", [p for p in src_ports_all if p.side != "right"], src_def)
        self._dump_ports("目标候选", [p for p in dst_ports_all if p.side == "left"], dst_def)
        self._dump_ports("目标(回退)候选", [p for p in dst_ports_all if p.side != "left"], dst_def)

        src_model_ports = [
            (port_def.name, _model_kind_for(src_node, port_def.name, False))
            for port_def in (src_node.outputs or [])
        ]
        dst_model_ports = [
            (port_def.name, _model_kind_for(dst_node, port_def.name, True))
            for port_def in (dst_node.inputs or [])
        ]
        self.logger.log("端口", "[序号] 模型端口顺序(源 outputs)", values=src_model_ports)
        self.logger.log("端口", "[序号] 模型端口顺序(目标 inputs)", values=dst_model_ports)

        src_screen_cands, dst_screen_cands = self._select_screen_candidates(
            src_ports_all=src_ports_all,
            dst_ports_all=dst_ports_all,
            src_selection_kind=src_selection_kind,
            dst_selection_kind=dst_selection_kind,
        )
        self._log_trace(
            "端口",
            "端口筛选计划",
            screenshot_token=id(screenshot),
            src_candidates=len(src_screen_cands),
            dst_candidates=len(dst_screen_cands),
            src_expected_kind=str(src_selection_kind or "unknown"),
            dst_expected_kind=str(dst_selection_kind or "unknown"),
        )

        src_ordinal_index = _ordinal_in_model(
            src_node,
            str(src_port_name or ""),
            want_input=False,
            kind_expect=src_selection_kind,
        )
        dst_ordinal_index = _ordinal_in_model(
            dst_node,
            str(dst_port_name or ""),
            want_input=True,
            kind_expect=dst_selection_kind,
        )
        self.logger.log(
            "端口",
            "[序号] 计划序号",
            src=src_ordinal_index if src_ordinal_index is not None else "None",
            dst=dst_ordinal_index if dst_ordinal_index is not None else "None",
        )

        src_center = pick_port_center_for_node(
            self.executor,
            screenshot,
            src_snapshot.node_bbox,
            str(src_port_name or ""),
            want_output=True,
            expected_kind=src_selection_kind,
            log_callback=self.log_callback,
            ordinal_fallback_index=src_ordinal_index,
            ports_list=src_ports_all,
            list_ports_for_bbox_func=list_ports_for_bbox,
        )
        dst_center = pick_port_center_for_node(
            self.executor,
            screenshot,
            dst_snapshot.node_bbox,
            str(dst_port_name or ""),
            want_output=False,
            expected_kind=dst_selection_kind,
            log_callback=self.log_callback,
            ordinal_fallback_index=dst_ordinal_index,
            ports_list=dst_ports_all,
            list_ports_for_bbox_func=list_ports_for_bbox,
        )

        if src_center == (0, 0) or dst_center == (0, 0):
            self._log_trace(
                "端口",
                "未能定位端口",
                screenshot_token=id(screenshot),
                src_found=src_center != (0, 0),
                dst_found=dst_center != (0, 0),
                src_candidates_total=len(src_ports_all),
                dst_candidates_total=len(dst_ports_all),
            )
            if self.visual_callback is not None:
                rects_ports = []
                for p in src_ports_all:
                    bx, by, bw, bh = int(p.bbox[0]), int(p.bbox[1]), int(p.bbox[2]), int(p.bbox[3])
                    rects_ports.append({"bbox": (bx, by, bw, bh), "color": (80, 160, 255), "label": f"源:{str(getattr(p,'name_cn','') or '')}"})
                for p in dst_ports_all:
                    bx, by, bw, bh = int(p.bbox[0]), int(p.bbox[1]), int(p.bbox[2]), int(p.bbox[3])
                    rects_ports.append({"bbox": (bx, by, bw, bh), "color": (255, 160, 80), "label": f"目:{str(getattr(p,'name_cn','') or '')}"})
                self.executor.emit_visual(screenshot, {"rects": rects_ports}, self.visual_callback)
            return None

        chosen_src = _find_by_center(src_ports_all, src_center)
        chosen_dst = _find_by_center(dst_ports_all, dst_center)
        if chosen_src is not None:
            self.logger.log(
                "端口",
                "选定源端口",
                idx=str(getattr(chosen_src, "index", None)),
                kind=str(getattr(chosen_src, "kind", "")),
                name=str(chosen_src.name_cn),
                center=(int(src_center[0]), int(src_center[1])),
            )
        if chosen_dst is not None:
            self.logger.log(
                "端口",
                "选定目标端口",
                idx=str(getattr(chosen_dst, "index", None)),
                kind=str(getattr(chosen_dst, "kind", "")),
                name=str(chosen_dst.name_cn),
                center=(int(dst_center[0]), int(dst_center[1])),
            )

        if self.visual_callback is not None:
            src_ord_actual = _ordinal_of_screen_center(src_center, src_screen_cands)
            dst_ord_actual = _ordinal_of_screen_center(dst_center, dst_screen_cands)
            self.logger.log(
                "端口",
                "[序号] 实际命中",
                src=src_ord_actual if src_ord_actual is not None else "None",
                dst=dst_ord_actual if dst_ord_actual is not None else "None",
            )
            self._log_trace(
                "端口",
                "端口命中结果",
                screenshot_token=id(screenshot),
                src_center=(int(src_center[0]), int(src_center[1])),
                dst_center=(int(dst_center[0]), int(dst_center[1])),
                src_ord_plan=src_ordinal_index if src_ordinal_index is not None else "None",
                dst_ord_plan=dst_ordinal_index if dst_ordinal_index is not None else "None",
                src_ord_actual=src_ord_actual if src_ord_actual is not None else "None",
                dst_ord_actual=dst_ord_actual if dst_ord_actual is not None else "None",
            )
            circles = [
                {
                    "center": (int(src_center[0]), int(src_center[1])),
                    "radius": 6,
                    "color": (0, 200, 255),
                    "label": f"选源#{str(src_ord_actual) if src_ord_actual is not None else '?'}",
                },
                {
                    "center": (int(dst_center[0]), int(dst_center[1])),
                    "radius": 6,
                    "color": (0, 220, 120),
                    "label": f"选目标#{str(dst_ord_actual) if dst_ord_actual is not None else '?'}",
                },
            ]
            self.executor.emit_visual(screenshot, {"circles": circles}, self.visual_callback)

        if chosen_src is not None and src_selection_kind in ("flow", "data"):
            actual_src_kind = normalize_kind_text(getattr(chosen_src, "kind", ""))
            if actual_src_kind != src_selection_kind:
                self.logger.log(
                    "端口",
                    "源端口类型与期望不一致",
                    expected=src_selection_kind,
                    actual=str(getattr(chosen_src, "kind", "")),
                )
        if chosen_dst is not None and dst_selection_kind in ("flow", "data"):
            actual_dst_kind = normalize_kind_text(getattr(chosen_dst, "kind", ""))
            if actual_dst_kind != dst_selection_kind:
                self.logger.log(
                    "端口",
                    "目标端口类型与期望不一致",
                    expected=dst_selection_kind,
                    actual=str(getattr(chosen_dst, "kind", "")),
                )

        return PortSelectionResult(
            src_center=src_center,
            dst_center=dst_center,
            src_selection_kind=src_selection_kind,
            dst_selection_kind=dst_selection_kind,
            src_ports_all=src_ports_all,
            dst_ports_all=dst_ports_all,
            src_screen_candidates=src_screen_cands,
            dst_screen_candidates=dst_screen_cands,
        )


__all__ = [
    "ConnectionFrameState",
    "PortSelectionResult",
    "PortMatchingService",
]


