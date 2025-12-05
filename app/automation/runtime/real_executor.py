from __future__ import annotations
"""
RealExecutor：真实编辑器窗口执行器（应用层）

说明：
- 本模块承担“真实编辑器窗口”上的执行动作。
- 在分层与插件化架构下，UI/外设交互属于应用层；因此 RealExecutor 位于 `app.automation`，不在 `engine` 内部。
- 依赖 `app.automation.*` 提供的截图/识别/输入能力，以及 `app.runtime.engine.view_state.ViewState` 维护视口状态。
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable, Dict
from pathlib import Path

from PIL import Image
import os
import time

from engine.configs.settings import settings
from engine.utils.text.text_similarity import (
    levenshtein_distance,
    chinese_similar,
)

from app.automation.vision.ocr_utils import extract_chinese
from app.automation.input.common import sleep_seconds
from app.runtime.engine.view_state import ViewState
from app.automation.vision import (
    capture_client_image,
    list_nodes,
    list_ports,
)
from app.automation.ports.port_picker import pick_port_center_for_node
from app.automation.core.view_alignment import run_pan_loop, PanEvaluation
from app.automation.core.view_mapping import (
    compute_segmented_pan_unit,
    generate_spiral_deltas,
    perform_drag_with_motion_estimation,
)
from app.automation.core.connection_drag import perform_connection_drag, mean_abs_diff_in_region
from app.automation.input.win_input import (
    get_client_rect,
    client_to_screen,
    move_mouse_client,
    drag_client,
    send_text,
    press_enter,
)


@dataclass
class NodeRef:
    name_cn: str
    bbox: Tuple[int, int, int, int]
    center: Tuple[int, int]


class _RuntimePortPickerExecutor:
    def __init__(self, logger: Callable[[str], None]) -> None:
        self._logger = logger

    def _log(self, message: str, _log_callback=None) -> None:
        if self._logger is not None:
            self._logger(message)


class RealExecutor:
    """
    真实执行器：将步骤在真实编辑器窗口中执行。
    - 通过 ViewState 维护画布→视口映射；
    - 使用 app.automation.vision 完成截图/识别；
    - 使用 win_input 注入鼠标键盘操作（客户区像素）。
    """

    def __init__(self, hwnd: int, view_state: ViewState) -> None:
        if hwnd == 0:
            raise ValueError("invalid hwnd")
        self._hwnd = int(hwnd)
        self._view_state = view_state
        client_rect = get_client_rect(self._hwnd)
        self._view_state.set_client_origin(client_rect.left, client_rect.top)
        self._view_state.set_viewport_size(client_rect.width, client_rect.height)
        if settings.REAL_EXEC_VERBOSE:
            print(
                f"[RealExec] init hwnd={self._hwnd} "
                f"client=({client_rect.left},{client_rect.top},{client_rect.width}x{client_rect.height})"
            )

        # 模板路径（基于工程根目录推导）：供需要使用固定 OCR 模板的功能复用
        root_dir = Path(__file__).resolve().parents[3]
        templates_root = root_dir / "assets" / "ocr_templates" / "4K-CN"
        self.dict_key_template_path = templates_root / "jian.png"
        self.dict_value_template_path = templates_root / "zhi.png"

    def _log(self, message: str) -> None:
        if settings.REAL_EXEC_VERBOSE:
            print(f"[RealExec] {message}")

    # ---------- 截图与识别 ----------
    def capture(self) -> Image.Image:
        client_rect = get_client_rect(self._hwnd)
        self._view_state.set_client_origin(client_rect.left, client_rect.top)
        self._view_state.set_viewport_size(client_rect.width, client_rect.height)
        image = capture_client_image(self._hwnd)
        if settings.REAL_EXEC_VERBOSE:
            print(
                f"[RealExec] capture: client=({client_rect.left},{client_rect.top},"
                f"{client_rect.width}x{client_rect.height})"
            )
        return image

    def find_node_by_name(self, image: Image.Image, name_cn: str) -> Optional[NodeRef]:
        candidates = list_nodes(image)
        if settings.REAL_EXEC_VERBOSE:
            titles = [c.name_cn for c in candidates]
            print(
                f"[RealExec] list_nodes: {len(candidates)} -> "
                f"{titles[:8]}{' ...' if len(titles) > 8 else ''}"
            )
        for node in candidates:
            if chinese_similar(node.name_cn, name_cn):
                if settings.REAL_EXEC_VERBOSE:
                    print(
                        f"[RealExec] find_node_by_name: "
                        f"matched='{node.name_cn}' target='{name_cn}' center={node.center}"
                    )
                return NodeRef(
                    name_cn=node.name_cn,
                    bbox=node.bbox,
                    center=node.center,
                )
        return None

    # ---------- 可见性保障（按预测/分段拖拽/相位相关纠偏） ----------
    def ensure_visible_node(
        self,
        name_cn: str,
        predicted_sim_xy: Optional[Tuple[float, float]] = None,
        max_steps: int = 8,
        pan_step_pixels: int = 400,
    ) -> NodeRef:
        found_node: Optional[NodeRef] = None

        def _capture_frame() -> Image.Image:
            return self.capture()

        def _evaluate(current_image: Image.Image, step_index: int) -> PanEvaluation:
            nonlocal found_node
            candidate = self.find_node_by_name(current_image, name_cn)
            if candidate is not None:
                found_node = candidate
                if settings.REAL_EXEC_VERBOSE:
                    print(
                        f"[RealExec] ensure_visible_node: "
                        f"matched '{name_cn}' at {candidate.center}"
                    )
                return PanEvaluation(satisfied=True)

            viewport_center_x, viewport_center_y = self._view_state.viewport_center()
            if predicted_sim_xy is not None:
                pred_client_x, pred_client_y = self._view_state.to_client(predicted_sim_xy)
                vector_x = int(pred_client_x - viewport_center_x)
                vector_y = int(pred_client_y - viewport_center_y)
            else:
                vector_x = pan_step_pixels
                vector_y = 0

            drag_plan = {
                'viewport_center': (int(viewport_center_x), int(viewport_center_y)),
                'vector': (int(vector_x), int(vector_y)),
            }
            return PanEvaluation(satisfied=False, drag_args=drag_plan)

        def _execute_drag(current_image: Image.Image, plan: Dict[str, Any]) -> Image.Image:
            viewport_center_x, viewport_center_y = plan['viewport_center']
            vector_x, vector_y = plan['vector']
            unit_x, unit_y, _ = compute_segmented_pan_unit(
                vector_x,
                vector_y,
                pan_step_pixels,
            )
            start_x = viewport_center_x
            start_y = viewport_center_y
            end_x = viewport_center_x - unit_x
            end_y = viewport_center_y - unit_y
            if settings.REAL_EXEC_VERBOSE:
                print(
                    f"[RealExec] pan step: vector=({vector_x},{vector_y}) "
                    f"unit=({unit_x},{unit_y}) start=({start_x},{start_y}) "
                    f"end=({end_x},{end_y})"
                )
            return self._drag_with_phase_correction(
                current_image,
                start_x,
                start_y,
                end_x,
                end_y,
            )

        outcome = run_pan_loop(
            _capture_frame,
            _evaluate,
            _execute_drag,
            max_steps=max_steps,
        )

        if not outcome.success:
            raise RuntimeError("ensure_visible_node failed")
        if found_node is None:
            final_image = outcome.last_image if outcome.last_image is not None else self.capture()
            found_node = self.find_node_by_name(final_image, name_cn)
        if found_node is None:
            raise RuntimeError("ensure_visible_node failed")
        return found_node

    # ---------- 端口解析 ----------
    def _find_port_center(
        self,
        image: Image.Image,
        node: NodeRef,
        port_name_cn: str,
        want_output: bool,
    ) -> Tuple[int, int]:
        ports = list_ports(image, node.bbox)
        if len(ports) == 0:
            raise RuntimeError("no ports detected in node")
        picker = _RuntimePortPickerExecutor(self._log)
        center = pick_port_center_for_node(
            executor=picker,
            screenshot=image,
            node_bbox=node.bbox,
            desired_port=port_name_cn,
            want_output=want_output,
            expected_kind=None,
            log_callback=None,
            ordinal_fallback_index=None,
            ports_list=ports,
            list_ports_for_bbox_func=list_ports,
        )
        if int(center[0]) == 0 and int(center[1]) == 0:
            raise RuntimeError("target port not found")
        return center

    def _drag_with_phase_correction(
        self,
        base_image: Image.Image,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        log_context: str = "",
        steps: int = 15,
        step_sleep_ms: int = 4,
    ) -> Image.Image:
        def _drag_action() -> None:
            drag_client(
                self._hwnd,
                start_x,
                start_y,
                end_x,
                end_y,
                steps=steps,
                step_sleep_ms=step_sleep_ms,
            )

        next_image, delta_x, delta_y = perform_drag_with_motion_estimation(
            base_image,
            drag_action=_drag_action,
            capture_after=self.capture,
        )
        self._view_state.apply_content_motion(delta_x, delta_y)
        if settings.REAL_EXEC_VERBOSE:
            prefix = f"{log_context}" if log_context else ""
            print(
                f"[RealExec] {prefix}phaseCorr delta=({delta_x:.2f},{delta_y:.2f}) "
                f"-> offset={self._view_state.canvas_offset()}"
            )
        return next_image

    # ---------- 画布拖拽辅助 ----------
    def pan_by_vector_pixels(
        self,
        vector_x: int,
        vector_y: int,
        segments: int = 1,
    ) -> None:
        if segments <= 0:
            segments = 1
        viewport_center_x, viewport_center_y = self._view_state.viewport_center()
        step_x = int(vector_x / segments)
        step_y = int(vector_y / segments)
        for _ in range(segments):
            before = self.capture()
            start_x = viewport_center_x
            start_y = viewport_center_y
            end_x = viewport_center_x - step_x
            end_y = viewport_center_y - step_y
            if settings.REAL_EXEC_VERBOSE:
                print(
                    f"[RealExec] pan_by_vector: step=({step_x},{step_y}) "
                    f"start=({start_x},{start_y}) end=({end_x},{end_y})"
                )
            self._drag_with_phase_correction(
                before,
                start_x,
                start_y,
                end_x,
                end_y,
                log_context="pan_by_vector: ",
            )

    def spiral_search_for_node(
        self,
        name_cn: str,
        step: int = 360,
        rings: int = 6,
    ) -> Optional[NodeRef]:
        image = self.capture()
        found = self.find_node_by_name(image, name_cn)
        if found is not None:
            return found
        for dx_unit, dy_unit in generate_spiral_deltas(step=step, rings=rings):
            if settings.REAL_EXEC_VERBOSE:
                print(f"[RealExec] spiral move=({dx_unit},{dy_unit})")
            self.pan_by_vector_pixels(dx_unit, dy_unit, segments=1)
            image = self.capture()
            found = self.find_node_by_name(image, name_cn)
            if found is not None:
                if settings.REAL_EXEC_VERBOSE:
                    print(
                        f"[RealExec] spiral found '{name_cn}' at {found.center}"
                    )
                return found
        return None

    # ---------- 原子动作 ----------
    def connect(
        self,
        src_node_cn: str,
        src_port_cn: str,
        dst_node_cn: str,
        dst_port_cn: str,
    ) -> None:
        image_before = self.capture()
        src_node = self.ensure_visible_node(src_node_cn)
        dst_node = self.ensure_visible_node(dst_node_cn)

        image_ports = self.capture()
        src_center = self._find_port_center(image_ports, src_node, src_port_cn, True)
        dst_center = self._find_port_center(image_ports, dst_node, dst_port_cn, False)

        src_client_x = src_center[0] - self._view_state.client_origin()[0]
        src_client_y = src_center[1] - self._view_state.client_origin()[1]
        dst_client_x = dst_center[0] - self._view_state.client_origin()[0]
        dst_client_y = dst_center[1] - self._view_state.client_origin()[1]
        if settings.REAL_EXEC_VERBOSE:
            print(
                f"[RealExec] connect: src='{src_node_cn}:{src_port_cn}' "
                f"center={src_center} -> dst='{dst_node_cn}:{dst_port_cn}' "
                f"center={dst_center}"
            )
        if settings.REAL_EXEC_VERBOSE:
            print(
                f"[RealExec] connect drag: client ({src_client_x},{src_client_y}) "
                f"-> ({dst_client_x},{dst_client_y})"
            )

        def _drag_callable(x1: int, y1: int, x2: int, y2: int) -> None:
            drag_client(
                self._hwnd,
                x1,
                y1,
                x2,
                y2,
                steps=25,
                step_sleep_ms=5,
            )

        def _verify_connection() -> bool:
            image_after = self.capture()
            change = mean_abs_diff_in_region(image_before, image_after, dst_center)
            if settings.REAL_EXEC_VERBOSE:
                print(f"[RealExec] connect verify: meanDiff={change:.2f}")
            if change >= 2.0:
                return True
            drag_client(
                self._hwnd,
                dst_client_x,
                dst_client_y,
                dst_client_x + 8,
                dst_client_y,
                steps=10,
                step_sleep_ms=4,
            )
            image_after2 = self.capture()
            change2 = mean_abs_diff_in_region(image_after, image_after2, dst_center)
            if settings.REAL_EXEC_VERBOSE:
                print(f"[RealExec] connect verify(retry): meanDiff={change2:.2f}")
            if change2 >= 2.0:
                return True
            folder = os.path.join(
                os.path.dirname(__file__),
                "..",
                "runtime",
                "fails",
            )
            os.makedirs(folder, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.abspath(
                os.path.join(folder, f"connect_fail_{timestamp}.png")
            )
            image_after2.save(path)
            if settings.REAL_EXEC_VERBOSE:
                print(f"[RealExec] connect failed, saved: {path}")
            raise RuntimeError("connect verification failed")

        perform_connection_drag(
            drag_callable=_drag_callable,
            src_screen=(src_client_x, src_client_y),
            dst_screen=(dst_client_x, dst_client_y),
            log_fn=self._log,
            description=f"{src_node_cn}.{src_port_cn} → {dst_node_cn}.{dst_port_cn}",
            verify_callable=_verify_connection,
        )

    def connect_and_create(
        self,
        src_node_cn: str,
        src_port_cn: str,
        new_node_name_cn: str,
        drop_sim_xy: Optional[Tuple[float, float]] = None,
    ) -> None:
        image = self.capture()
        src_node = self.ensure_visible_node(src_node_cn)
        image = self.capture()
        src_center = self._find_port_center(image, src_node, src_port_cn, True)

        if drop_sim_xy is not None:
            drop_client_x, drop_client_y = self._view_state.to_client(drop_sim_xy)
        else:
            # 基于源节点右侧固定偏移
            offset_x = int((src_node.bbox[2]) * 0.9) + 240
            offset_y = int((src_node.bbox[3]) * -0.2)
            src_client_x = src_center[0] - self._view_state.client_origin()[0]
            src_client_y = src_center[1] - self._view_state.client_origin()[1]
            drop_client_x = src_client_x + offset_x
            drop_client_y = src_client_y + offset_y

        src_client_x = src_center[0] - self._view_state.client_origin()[0]
        src_client_y = src_center[1] - self._view_state.client_origin()[1]

        if settings.REAL_EXEC_VERBOSE:
            print(
                f"[RealExec] connect_and_create: drag from {src_center} "
                f"-> clientDrop=({drop_client_x},{drop_client_y})"
            )
        drag_client(
            self._hwnd,
            src_client_x,
            src_client_y,
            drop_client_x,
            drop_client_y,
            steps=25,
            step_sleep_ms=5,
        )

        send_text(extract_chinese(new_node_name_cn))
        press_enter()
        if settings.REAL_EXEC_VERBOSE:
            print(
                f"[RealExec] connect_and_create: "
                f"input='{extract_chinese(new_node_name_cn)}' and pressed Enter"
            )

        # 验证：等待新节点出现在投放点附近
        max_checks = 8
        drop_abs_x = drop_client_x + self._view_state.client_origin()[0]
        drop_abs_y = drop_client_y + self._view_state.client_origin()[1]
        for attempt in range(max_checks):
            sleep_seconds(0.15)
            img = self.capture()
            nodes = list_nodes(img)
            for nd in nodes:
                if chinese_similar(nd.name_cn, new_node_name_cn):
                    dist = (
                        (nd.center[0] - drop_abs_x) ** 2
                        + (nd.center[1] - drop_abs_y) ** 2
                    ) ** 0.5
                    if dist <= 320:
                        if settings.REAL_EXEC_VERBOSE:
                            print(
                                f"[RealExec] connect_and_create: "
                                f"new node='{nd.name_cn}' found at {nd.center}, "
                                f"dist={dist:.1f}"
                            )
                        return
            if settings.REAL_EXEC_VERBOSE:
                print(
                    f"[RealExec] connect_and_create: "
                    f"attempt {attempt + 1}/{max_checks} not found"
                )
        # 失败截图
        folder = os.path.join(
            os.path.dirname(__file__),
            "..",
            "runtime",
            "fails",
        )
        os.makedirs(folder, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        final_image = self.capture()
        path = os.path.abspath(
            os.path.join(folder, f"connect_create_fail_{timestamp}.png")
        )
        final_image.save(path)
        if settings.REAL_EXEC_VERBOSE:
            print(f"[RealExec] connect_and_create failed, saved: {path}")
        raise RuntimeError("connect_and_create verification failed")



