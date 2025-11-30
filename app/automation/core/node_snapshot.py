from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, List
import math
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core.executor_protocol import EditorExecutorProtocol
from app.automation.vision import list_ports as list_ports_for_bbox, list_nodes
from engine.graph.models.graph_model import NodeModel

NODE_DRAG_UPDATE_MIN_SCREEN_PX: float = 16.0
NODE_DRAG_UPDATE_MIN_PROGRAM_UNITS: float = 8.0


class GraphSceneSnapshot:
    """场景级截图与节点检测缓存，用于跨步骤复用同一帧识别结果。

    特性：
    - 绑定到执行器的视口状态 token（_view_state_token）；视口变化后统一失效；
    - 维护最近一帧 screenshot + list_nodes 结果，避免重复全图识别；
    - 通过 per-node 脏标记控制“哪些节点必须使用新截图”，确保端口/Warning 布局变化时不复用旧帧。
    """

    def __init__(self, executor: EditorExecutorProtocol) -> None:
        self._executor = executor
        self._screenshot: Image.Image | None = None
        self._detected_nodes: List[Any] | None = None
        self._view_state_token: int = -1
        self._dirty_nodes: set[str] = set()

    def invalidate_all(self, reason: str) -> None:
        """整体失效当前场景快照，用于视口变更或显式重置。"""
        self._screenshot = None
        self._detected_nodes = None
        self._view_state_token = -1
        self._dirty_nodes.clear()

    def mark_node_dirty(self, node_id: str) -> None:
        """标记某个节点在当前帧下的检测结果不再可信（例如端口布局发生变化）。"""
        node_id_text = str(node_id or "")
        if node_id_text == "":
            return
        self._dirty_nodes.add(node_id_text)

    def can_reuse_for_current_view(self) -> bool:
        """判断当前缓存是否与执行器的视口 token 一致。"""
        current_token = getattr(self._executor, "_view_state_token", -1)
        if self._screenshot is None or self._detected_nodes is None:
            return True
        return self._view_state_token == int(current_token)

    def can_use_for_node(self, node_id: str) -> bool:
        """判断对于指定节点，是否可以尝试复用当前场景帧。

        规则：
        - 若节点被标记为脏，则必须放弃复用，调用方应重新截图；
        - 若尚未建立场景帧，则允许当前节点触发首帧构建；
        - 若已存在场景帧，则仅当视口 token 一致时才允许复用。
        """
        node_id_text = str(node_id or "")
        if node_id_text in self._dirty_nodes:
            return False
        return self.can_reuse_for_current_view()

    def ensure_frame(self) -> Tuple[Image.Image, List[Any]]:
        """确保存在一帧与当前视口对应的 screenshot + list_nodes 结果。"""
        current_token = int(getattr(self._executor, "_view_state_token", 0))
        if (
            self._screenshot is not None
            and self._detected_nodes is not None
            and self._view_state_token == current_token
        ):
            return self._screenshot, self._detected_nodes

        frame = editor_capture.capture_window(self._executor.window_title)
        if frame is None:
            raise ValueError("截图失败（GraphSceneSnapshot.ensure_frame）")
        detected = list_nodes(frame)

        self._screenshot = frame
        self._detected_nodes = detected
        self._view_state_token = current_token
        self._dirty_nodes.clear()

        return frame, detected

    def update_from_detection(self, screenshot: Image.Image, detected_nodes: List[Any]) -> None:
        """使用外部产生的 screenshot + list_nodes 结果更新场景快照。"""
        if screenshot is None:
            return
        if not isinstance(detected_nodes, list):
            return
        self._screenshot = screenshot
        self._detected_nodes = list(detected_nodes)
        self._view_state_token = int(getattr(self._executor, "_view_state_token", 0))
        self._dirty_nodes.clear()

    @property
    def screenshot(self) -> Image.Image | None:
        return self._screenshot

    @property
    def detected_nodes(self) -> List[Any] | None:
        return self._detected_nodes

    @property
    def dirty_nodes(self) -> set[str]:
        return self._dirty_nodes


def capture_node_ports_snapshot(
    executor: EditorExecutorProtocol,
    node: NodeModel,
    *,
    screenshot: Image.Image | None = None,
    debug: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Any] = None,
    label: str = "",
    detected_nodes: Optional[list] = None,
) -> Tuple[Image.Image | None, Tuple[int, int, int, int], List[Any]]:
    """获取指定节点的截图、bbox 与端口识别结果（可复用现有截图）。"""
    cache = NodePortsSnapshotCache(executor, node, log_callback)
    ok = cache.refresh(
        reason=label or "节点端口快照",
        refresh_bbox=True,
        screenshot=screenshot,
        debug=debug,
        detected_nodes=detected_nodes,
    )
    if not ok:
        frame_fallback = None
        try:
            frame_fallback = cache.screenshot
        except RuntimeError:
            frame_fallback = None
        return frame_fallback, (0, 0, 0, 0), []
    return cache.screenshot, cache.node_bbox, cache.ports


class NodePortsSnapshotCache:
    """缓存节点截图、bbox 与端口识别结果，供多步骤复用。"""

    def __init__(self, executor: EditorExecutorProtocol, node: NodeModel, log_callback=None) -> None:
        self._executor = executor
        self._node = node
        self._log_callback = log_callback
        self._screenshot: Image.Image | None = None
        self._bbox: Tuple[int, int, int, int] | None = None
        self._ports: List[Any] | None = None
        self._frame_token: int | None = None

    def _log(self, message: str) -> None:
        self._executor._log(message, self._log_callback)

    def refresh(
        self,
        *,
        reason: str,
        refresh_bbox: bool,
        screenshot: Image.Image | None = None,
        debug: Optional[Dict[str, Any]] = None,
        detected_nodes: Optional[list] = None,
    ) -> bool:
        frame = screenshot
        detections: Optional[list] = detected_nodes

        # 优先：在未显式提供 screenshot/detections 时尝试复用场景级快照
        if frame is None:
            scene_snapshot = None
            get_scene_snapshot = getattr(self._executor, "get_scene_snapshot", None)
            if callable(get_scene_snapshot) and bool(
                getattr(self._executor, "enable_scene_snapshot_optimization", True)
            ):
                scene_snapshot = get_scene_snapshot()
            if scene_snapshot is not None:
                can_use_for_node = getattr(scene_snapshot, "can_use_for_node", None)
                ensure_frame_method = getattr(scene_snapshot, "ensure_frame", None)
                node_identifier = getattr(self._node, "id", "")
                if (
                    isinstance(node_identifier, str)
                    and node_identifier != ""
                    and callable(can_use_for_node)
                    and callable(ensure_frame_method)
                    and bool(can_use_for_node(node_identifier))
                ):
                    frame, detections = ensure_frame_method()
        if frame is None:
            frame = editor_capture.capture_window(self._executor.window_title)
        if frame is None:
            self._log(f"✗ 截图失败（{reason}）")
            return False
        self._screenshot = frame
        self._frame_token = id(frame)
        if self._bbox is None or refresh_bbox:
            strict_for_connect = isinstance(reason, str) and reason.startswith("连接/")
            debug_dict: Dict[str, Any] = debug if debug is not None else {}
            bbox = self._executor._find_best_node_bbox(
                frame,
                self._node.title,
                self._node.pos,
                debug=debug_dict,
                detected_nodes=detections,
            )
            if int(bbox[2]) <= 0:
                self._bbox = None
                self._ports = None
                self._log(f"✗ 未能定位节点: {self._node.title}（{reason}）")
                return False
            if strict_for_connect:
                if debug_dict.get("strict_connect_mode") is None:
                    debug_dict["strict_connect_mode"] = True
                fallback_used = bool(debug_dict.get("fallback_used"))
                failed_reason = debug_dict.get("failed_reason")
                if fallback_used or failed_reason is not None:
                    self._bbox = None
                    self._ports = None
                    self._log(
                        f"✗ 连接严格模式：未能在预期范围内唯一定位节点 '{self._node.title}'（{reason}）"
                    )
                    return False
            self._bbox = bbox
            self._maybe_update_program_position(bbox, reason)
        self._ports = list_ports_for_bbox(frame, self._bbox)
        return True

    def ensure(
        self,
        *,
        reason: str,
        require_bbox: bool,
        screenshot: Image.Image | None = None,
        debug: Optional[Dict[str, Any]] = None,
        detected_nodes: Optional[list] = None,
    ) -> bool:
        if self._screenshot is None or self._bbox is None or require_bbox:
            return self.refresh(
                reason=reason,
                refresh_bbox=require_bbox or self._bbox is None,
                screenshot=screenshot,
                debug=debug,
                detected_nodes=detected_nodes,
            )
        if self._ports is None:
            self._ports = list_ports_for_bbox(self._screenshot, self._bbox)
        return True

    def mark_dirty(self, *, require_bbox: bool, keep_cached_frame: bool = False) -> None:
        """
        标记当前节点的端口快照为“脏”，并在需要时同步通知场景级快照。

        参数:
            require_bbox: 下次访问时是否强制重新定位节点 bbox。
            keep_cached_frame: 是否保留当前帧的 screenshot/ports 缓存。

        说明:
        - keep_cached_frame=False（默认）：完全失效本地缓存，下一次 ensure() 必须重新截图并识别端口。
        - keep_cached_frame=True：仅在逻辑上标记“节点 UI 已变化”，但保留当前帧截图与端口列表，
          供同一轮配置/类型设置中的后续步骤复用，避免在“已知端口序号”的场景下重复 OCR；
          此时若 require_bbox=True，则仅清空 bbox，允许调用方在需要时单独刷新位置框。
        """
        if not keep_cached_frame:
            self._screenshot = None
            self._ports = None
            self._frame_token = None
            if require_bbox:
                self._bbox = None
        else:
            if require_bbox:
                self._bbox = None

        # 同步更新场景级快照中的脏节点标记（若存在）
        get_scene_snapshot = getattr(self._executor, "get_scene_snapshot", None)
        if callable(get_scene_snapshot) and bool(
            getattr(self._executor, "enable_scene_snapshot_optimization", True)
        ):
            scene_snapshot = get_scene_snapshot()
            mark_node_dirty = getattr(scene_snapshot, "mark_node_dirty", None)
            node_identifier = getattr(self._node, "id", "")
            if callable(mark_node_dirty) and isinstance(node_identifier, str) and node_identifier != "":
                mark_node_dirty(node_identifier)

    @property
    def screenshot(self) -> Image.Image:
        if self._screenshot is None:
            raise RuntimeError("snapshot cache未初始化，请先调用 ensure()")
        return self._screenshot

    @property
    def node_bbox(self) -> Tuple[int, int, int, int]:
        if self._bbox is None:
            raise RuntimeError("snapshot cache未初始化，请先调用 ensure()")
        return self._bbox

    @property
    def ports(self) -> List[Any]:
        if self._ports is None:
            if self._screenshot is None or self._bbox is None:
                raise RuntimeError("snapshot cache未初始化，请先调用 ensure()")
            self._ports = list_ports_for_bbox(self._screenshot, self._bbox)
        return self._ports

    @property
    def frame_token(self) -> int | None:
        return self._frame_token

    def can_reuse_for_frame(self, frame: Image.Image | None) -> bool:
        return (
            frame is not None
            and self._frame_token is not None
            and id(frame) == self._frame_token
            and self._screenshot is not None
            and self._bbox is not None
            and self._ports is not None
        )

    def _maybe_update_program_position(self, bbox: Tuple[int, int, int, int], reason: str) -> None:
        executor = self._executor
        node = self._node
        if isinstance(reason, str) and reason.startswith("连接/"):
            return
        if (
            executor.origin_node_pos is None
            or executor.scale_ratio is None
        ):
            return
        origin_x = float(executor.origin_node_pos[0])
        origin_y = float(executor.origin_node_pos[1])
        scale = float(executor.scale_ratio)
        if abs(scale) <= 1e-9:
            return
        old_prog_x = float(node.pos[0])
        old_prog_y = float(node.pos[1])
        expected_editor_x = origin_x + old_prog_x * scale
        expected_editor_y = origin_y + old_prog_y * scale
        actual_editor_x = float(bbox[0])
        actual_editor_y = float(bbox[1])
        delta_screen_x = actual_editor_x - expected_editor_x
        delta_screen_y = actual_editor_y - expected_editor_y
        delta_screen = math.hypot(delta_screen_x, delta_screen_y)
        if delta_screen < NODE_DRAG_UPDATE_MIN_SCREEN_PX:
            return
        new_prog_x = (actual_editor_x - origin_x) / scale
        new_prog_y = (actual_editor_y - origin_y) / scale
        delta_prog_x = new_prog_x - old_prog_x
        delta_prog_y = new_prog_y - old_prog_y
        delta_prog = math.hypot(delta_prog_x, delta_prog_y)
        if delta_prog < NODE_DRAG_UPDATE_MIN_PROGRAM_UNITS:
            return
        node.pos = (new_prog_x, new_prog_y)
        drag_ratio = delta_prog / max(delta_screen, 1.0)
        executor.drag_distance_per_pixel = float(drag_ratio)
        self._log(
            f"[拖拽测距] '{node.title}' {reason} 检测到偏移≈({delta_prog_x:.1f},{delta_prog_y:.1f}) → "
            f"更新程序坐标=({new_prog_x:.1f},{new_prog_y:.1f}) screenΔ≈{delta_screen:.1f}px ratio≈{drag_ratio:.4f}",
        )
