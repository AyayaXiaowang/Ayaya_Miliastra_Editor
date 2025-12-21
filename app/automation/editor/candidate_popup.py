from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.capture.overlay_helpers import build_overlay_for_text_region
from app.automation.capture.reference_panels import build_reference_panel_payload
from app.automation.editor import executor_utils as _exec_utils
from app.automation.editor.structured_logging import StructuredLogger
from app.automation.editor.ui_constants import (
    CONTEXT_MENU_APPEAR_WAIT_SECONDS,
    POST_INPUT_STABILIZE_SECONDS_DEFAULT,
)
from app.automation.input.common import (
    DEFAULT_TYPE_SELECT_WAIT_SECONDS,
    DEFAULT_VERIFY_MAX_ATTEMPTS,
    DEFAULT_WAIT_INTERVAL_SECONDS,
    DEFAULT_WAIT_POLL_INTERVAL_SECONDS,
    sleep_seconds,
)
from app.automation.vision.ui_profile_params import (
    get_candidate_popup_size_px,
    get_ocr_exclude_top_pixels_default,
)
from app.automation.vision.ocr_utils import (
    fingerprint_region,
    get_bbox_center,
    normalize_ocr_bbox,
)

NODE_LIST_CONTEXT_LINGER_SECONDS = 0.5
NODE_LIST_TEMPLATE_X_RIGHT_EXTENSION_WIDTH_MULTIPLIER = 3
RIGHT_CLICK_BEFORE_CAPTURE_WAIT_SECONDS = 0.5


@dataclass(frozen=True)
class CandidatePopupDetection:
    popup_rect: Tuple[int, int, int, int]
    popup_rect_raw: Tuple[int, int, int, int]
    region_rect: Tuple[int, int, int, int]
    match: Optional[Tuple[int, int, int, int, float]] = None


@dataclass
class CandidatePopupFrame:
    screenshot: Image.Image
    frame_digest: str
    detection: Optional[CandidatePopupDetection]
    reused_detection: bool = False
    should_skip_processing: bool = False


@dataclass
class CandidatePopupContext:
    consecutive_no_list: int = 0
    last_list_present: bool = False
    has_clicked_candidate: bool = False
    last_screenshot: Optional[Image.Image] = None
    last_details: Optional[List] = None
    last_popup_rect: Optional[Tuple[int, int, int, int]] = None
    last_region_rect: Optional[Tuple[int, int, int, int]] = None
    last_search_row: Optional[Tuple[int, int]] = None
    last_popup_digest: Optional[str] = None
    last_frame_digest: Optional[str] = None
    last_popup_rect_raw: Optional[Tuple[int, int, int, int]] = None
    last_detection: Optional[CandidatePopupDetection] = None


def _fingerprint_full_frame(image: Image.Image) -> str:
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(image.tobytes())
    hasher.update(str(image.size).encode("ascii"))
    return hasher.hexdigest()


class CandidatePopupToolkit:
    def __init__(
        self,
        executor,
        template_path: Path,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
        logger: StructuredLogger,
        *,
        reference_panel_payload: Optional[dict],
        exclude_top_pixels: Optional[int],
    ) -> None:
        self.executor = executor
        self.template_path = template_path
        self.visual_callback = visual_callback
        self.logger = logger
        self.reference_panel_payload = reference_panel_payload
        self.exclude_top_pixels = exclude_top_pixels

    def capture_frame(self, label: str) -> Image.Image:
        def _builder(_img: Image.Image) -> Dict[str, Any]:
            payload = {}
            if self.reference_panel_payload is not None:
                payload["reference_panel"] = self.reference_panel_payload
            return payload

        return self.executor.capture_and_emit(
            label=label,
            overlays_builder=_builder,
            visual_callback=self.visual_callback,
        )

    def detect_popup(
        self,
        screenshot: Image.Image,
        label: str,
    ) -> Optional[CandidatePopupDetection]:
        # 说明：候选列表/右键弹窗可能出现在节点图布置区域之外（但仍在窗口内）。
        # 执行步骤时通常启用了“强制节点图 ROI”，此处必须临时关闭强制 ROI，
        # 否则会导致模板匹配与 OCR 被裁剪，从而在边缘场景漏检。
        img_width, img_height = screenshot.size
        search_region = (0, 0, int(img_width), int(img_height))
        self.logger.log(
            "模板",
            f"{label}：在全窗口范围搜索候选列表模板",
            search_region=search_region,
        )
        with editor_capture.disable_graph_roi_context():
            match = editor_capture.match_template(
                screenshot,
                str(self.template_path),
                search_region=None,
            )
            if not match:
                self.logger.log("模板", f"{label}：候选列表模板全窗口未命中，跳过该帧 OCR")
                return None
        list_x, list_y, list_w, list_h, match_score = match
        self.logger.log(
            "OCR-模板",
            f"{label}：命中候选列表模板，准备 OCR",
            editor_pos=(int(list_x), int(list_y)),
            size=(int(list_w), int(list_h)),
            score=float(match_score) if isinstance(match_score, (int, float)) else match_score,
        )
        popup_width_px, popup_height_px = get_candidate_popup_size_px()
        popup_rect_raw = (int(list_x), int(list_y), int(popup_width_px), int(popup_height_px))
        popup_rect = editor_capture.clip_to_image_bounds(screenshot, popup_rect_raw)
        return CandidatePopupDetection(
            popup_rect=popup_rect,
            popup_rect_raw=popup_rect_raw,
            region_rect=search_region,
            match=match,
        )

    def recognize_popup(
        self,
        screenshot: Image.Image,
        detection: CandidatePopupDetection,
        label: str,
        *,
        exclude_top_pixels: Optional[int] = None,
    ):
        popup_rect = detection.popup_rect
        popup_rect_raw = detection.popup_rect_raw
        region_rect_full = detection.region_rect
        exclude_pixels = exclude_top_pixels if exclude_top_pixels is not None else self.exclude_top_pixels
        if exclude_pixels is None:
            exclude_pixels = int(get_ocr_exclude_top_pixels_default())
        self.logger.log(
            "OCR",
            f"{label}：在候选列表区域执行 OCR",
            popup_rect=popup_rect,
            clipped_from=popup_rect_raw,
            region=region_rect_full,
            exclude_top=int(exclude_pixels),
        )
        with editor_capture.disable_graph_roi_context():
            return editor_capture.ocr_recognize_region(
                screenshot,
                popup_rect,
                return_details=True,
                exclude_top_pixels=exclude_pixels,
            )

    def extract_position(
        self,
        details: List,
        popup_rect: Tuple[int, int, int, int],
        target_cn_text: str,
        *,
        template_match: Optional[Tuple[int, int, int, int, float]] = None,
    ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
        region_x, region_y, _, _ = popup_rect

        template_left: Optional[int] = None
        template_right: Optional[int] = None
        template_center_x: Optional[float] = None
        if isinstance(template_match, (list, tuple)) and len(template_match) >= 4:
            match_left = int(template_match[0])
            match_width = int(template_match[2])
            template_left = int(match_left)
            base_width = max(0, int(match_width))
            extended_width = int(base_width * (1 + int(NODE_LIST_TEMPLATE_X_RIGHT_EXTENSION_WIDTH_MULTIPLIER)))
            template_right = int(match_left + extended_width)
            template_center_x = float(template_left + float(extended_width) / 2.0)

        best_editor_pos: Optional[Tuple[int, int]] = None
        best_item_text: Optional[str] = None
        best_overlap_width: int = -1
        best_score: float = -1.0
        best_center_dx: float = float("inf")

        for item in details:
            item_text = item[1] if len(item) > 1 else ""
            if not item_text:
                continue
            box = item[0]
            item_cn_text = self.executor.extract_chinese(item_text)
            if not item_cn_text:
                continue
            if item_cn_text != target_cn_text:
                continue

            bbox_left, _bbox_top, bbox_width, _bbox_height = normalize_ocr_bbox(box)
            abs_left = int(region_x + bbox_left)
            abs_right = int(abs_left + max(0, int(bbox_width)))

            # 关键过滤：目标文本框必须与 Node_list 模板命中区域在 X 方向有交集
            overlap_width = 0
            if template_left is not None and template_right is not None:
                overlap_width = int(min(abs_right, template_right) - max(abs_left, template_left))
                if overlap_width <= 0:
                    continue

            center_x, center_y = get_bbox_center(box)
            candidate_center_x = float(region_x + center_x)
            candidate_editor_pos = (int(candidate_center_x), int(region_y + center_y))

            item_score = 0.0
            if len(item) > 2:
                maybe_score = item[2]
                if isinstance(maybe_score, (int, float)):
                    item_score = float(maybe_score)

            # 当存在 template_match 时，优先挑选 X 交集更大的候选；否则保持“首个命中即返回”的行为
            if template_left is None or template_right is None:
                return candidate_editor_pos, item_text

            center_dx = (
                abs(float(candidate_center_x) - float(template_center_x))
                if template_center_x is not None
                else 0.0
            )
            better = False
            if int(overlap_width) > int(best_overlap_width):
                better = True
            elif int(overlap_width) == int(best_overlap_width):
                if float(item_score) > float(best_score):
                    better = True
                elif float(item_score) == float(best_score) and float(center_dx) < float(best_center_dx):
                    better = True
            if better:
                best_overlap_width = int(overlap_width)
                best_score = float(item_score)
                best_center_dx = float(center_dx)
                best_editor_pos = candidate_editor_pos
                best_item_text = str(item_text)

        return best_editor_pos, best_item_text

    @staticmethod
    def build_overlay(
        details: List,
        popup_rect: Tuple[int, int, int, int],
        *,
        highlight: Optional[Tuple[int, int]] = None,
        highlight_label: str = "",
        extra_rects: Optional[List[dict]] = None,
    ) -> dict:
        return build_overlay_for_text_region(
            popup_rect,
            details,
            highlight=highlight,
            highlight_label=highlight_label,
            extra_rects=extra_rects,
            base_label="OCR区域",
            detail_color=(0, 200, 0),
        )

    def emit_overlay(
        self,
        screenshot: Image.Image,
        overlay: dict,
    ) -> None:
        if self.visual_callback is None:
            return
        self.executor.emit_visual(screenshot, overlay, self.visual_callback)


class CandidatePopupFlow:
    def __init__(
        self,
        executor,
        target_text: str,
        wait_seconds: float,
        log_callback: Optional[Callable[[str], None]],
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
        exclude_top_pixels: Optional[int],
    ) -> None:
        self.executor = executor
        self.target_text = target_text
        self.target_cn_text = executor.extract_chinese(target_text)
        self.wait_seconds = wait_seconds
        self.log_callback = log_callback
        self.pause_hook = pause_hook
        self.allow_continue = allow_continue
        self.visual_callback = visual_callback
        self.exclude_top_pixels = exclude_top_pixels
        self.interval = DEFAULT_WAIT_POLL_INTERVAL_SECONDS
        self.attempts_per_round = max(1, int(wait_seconds / self.interval))
        self.micro_retries = 0
        self.context = CandidatePopupContext()
        self.node_list_template_path = _resolve_node_list_template_path(executor)
        self.logger = StructuredLogger(executor, log_callback, prefix="[候选] ")
        reference_payload = build_reference_panel_payload(
            title=f"模板: {self.node_list_template_path.name}",
            text=f"目标：{target_text}",
            image_path=str(self.node_list_template_path),
        )
        self.toolkit = CandidatePopupToolkit(
            executor,
            self.node_list_template_path,
            visual_callback,
            self.logger,
            reference_panel_payload=reference_payload,
            exclude_top_pixels=exclude_top_pixels,
        )
        self.aborted = False

    def _wait_with_executor_hooks(self, seconds: float) -> bool:
        """统一封装基于执行器的带钩子等待，便于在不同场景下复用。"""
        return self.executor.wait_with_hooks(
            float(seconds),
            self.pause_hook,
            self.allow_continue,
            0.1,
            self.log_callback,
        )

    def _recognize_popup_details(
        self,
        screenshot: Image.Image,
        detection: CandidatePopupDetection,
        label: str,
        *,
        exclude_top_pixels_override: Optional[int],
    ) -> Optional[List]:
        """在给定候选区域上执行 OCR，并返回结构化明细列表。"""
        exclude_pixels = exclude_top_pixels_override
        _text_full, raw_details = self.toolkit.recognize_popup(
            screenshot,
            detection,
            label,
            exclude_top_pixels=exclude_pixels,
        )
        return raw_details if isinstance(raw_details, list) else None

    def run(self) -> bool:
        for round_idx in range(self.micro_retries + 1):
            if self._run_round(round_idx):
                return True
            if round_idx < self.micro_retries:
                if not self._run_micro_retry():
                    return False
        return False

    def emit_failure_visual(self) -> None:
        if (
            self.visual_callback is None
            or self.context.last_screenshot is None
            or self.context.last_details is None
            or self.context.last_popup_rect is None
        ):
            return
        extra_rects: list[dict] = []
        if self.context.last_search_row is not None:
            region_x, _, region_w, _ = self.context.last_popup_rect
            row_top, row_bottom = self.context.last_search_row
            extra_rects.append(
                {
                    "bbox": (int(region_x), int(row_top), int(region_w), int(row_bottom - row_top)),
                    "color": (255, 0, 0),
                    "label": "搜索框行",
                }
            )
        overlay = self.toolkit.build_overlay(
            self.context.last_details,
            self.context.last_popup_rect,
            extra_rects=extra_rects,
        )
        self.toolkit.emit_overlay(self.context.last_screenshot, overlay)

    def log_failure_summary(self) -> None:
        if self.context.last_list_present:
            self.logger.log("结果", f"未能在超时内选择: {self.target_text}（列表存在但未定位目标）")
        else:
            self.logger.log("结果", f"未能在超时内选择: {self.target_text}（列表未出现）")

    def _run_round(self, round_idx: int) -> bool:
        for attempt_idx in range(self.attempts_per_round):
            if not self._check_hooks():
                return False
            self._log_wait_state(round_idx, attempt_idx)
            frame = self._capture_frame(f"候选列表轮询#{attempt_idx+1}")
            if frame is None:
                return False
            if frame.should_skip_processing:
                continue
            if frame.detection is None:
                self.context.last_frame_digest = frame.frame_digest
                if not self._handle_popup_absence():
                    return False
                continue
            if self._process_detection(frame, attempt_idx, round_idx):
                return True
            if not self._wait_interval():
                return False
        return False

    def _capture_frame(self, label: str) -> Optional[CandidatePopupFrame]:
        screenshot = self.toolkit.capture_frame(label)
        if screenshot is None:
            self.logger.log("通用", f"{label}：窗口截图失败")
            return None
        width_px, height_px = screenshot.size
        self.logger.log("截图", f"{label}", size=(int(width_px), int(height_px)))
        frame_digest = _fingerprint_full_frame(screenshot)
        detection: Optional[CandidatePopupDetection] = None
        reused_detection = False
        should_skip = False
        if frame_digest == self.context.last_frame_digest:
            if self.context.last_list_present and self.context.last_detection is not None:
                self.logger.log("缓存", "画面未变化，复用上一帧候选区域")
                detection = self.context.last_detection
                reused_detection = True
            else:
                self.logger.log("缓存", "画面未变化且无候选列表，继续等待")
                if not self._wait_interval():
                    return None
                should_skip = True
        if detection is None and not should_skip:
            detection = self.toolkit.detect_popup(screenshot, "搜索候选列表模板")
        return CandidatePopupFrame(
            screenshot=screenshot,
            frame_digest=frame_digest,
            detection=detection,
            reused_detection=reused_detection,
            should_skip_processing=should_skip,
        )

    def _process_detection(
        self,
        frame: CandidatePopupFrame,
        attempt_idx: int,
        round_idx: int,
    ) -> bool:
        detection = frame.detection
        if detection is None:
            return False
        self.logger.log("候选", "候选列表已出现，开始 OCR 定位")
        popup_digest = fingerprint_region(frame.screenshot, detection.popup_rect)
        if self.context.last_popup_digest == popup_digest and self.context.last_details is not None:
            details = self.context.last_details
            self.logger.log("候选", "候选列表画面未变化，复用缓存 OCR 结果")
        else:
            _text_full, raw_details = self.toolkit.recognize_popup(
                frame.screenshot,
                detection,
                f"轮询#{attempt_idx+1}（第{round_idx+1}轮）",
                exclude_top_pixels=self.exclude_top_pixels,
            )
            details = raw_details if isinstance(raw_details, list) else None
        self._record_detection_result(frame, detection, details, popup_digest)
        if self.context.has_clicked_candidate and (not details or len(details) == 0):
            self.logger.log(
                "候选",
                f"OCR 无文本（点击后），视为列表已关闭 → 已选择 '{self.target_text}'",
            )
            return True
        if not details:
            self.logger.log("候选", "候选列表 OCR 无结果，继续轮询")
            return False
        best_editor_pos, best_item_text = self.toolkit.extract_position(
            details,
            detection.popup_rect,
            self.target_cn_text,
            template_match=detection.match,
        )
        if best_editor_pos is None:
            self.logger.log("候选", f"OCR 未定位到 '{self.target_text}'，继续轮询")
            return False
        return self._click_candidate(
            frame.screenshot,
            detection,
            details,
            best_editor_pos,
            best_item_text or self.target_text,
        )

    def _click_candidate(
        self,
        screenshot: Image.Image,
        detection: CandidatePopupDetection,
        details: List,
        editor_pos: Tuple[int, int],
        label_text: str,
    ) -> bool:
        screen_x, screen_y = self.executor.convert_editor_to_screen_coords(editor_pos[0], editor_pos[1])
        self.logger.log(
            "候选",
            f"OCR 匹配到 '{self.target_text}'，点击候选项",
            screen=(screen_x, screen_y),
        )
        overlay = self.toolkit.build_overlay(
            details,
            detection.popup_rect,
            highlight=editor_pos,
            highlight_label=label_text,
        )
        self.toolkit.emit_overlay(screenshot, overlay)
        clicked = editor_capture.click_left_button(screen_x, screen_y)
        if not clicked:
            self.logger.log("候选", "点击失败，继续等待")
            return False
        self.context.has_clicked_candidate = True
        return self._verify_candidate_dismissed()

    def _verify_candidate_dismissed(self) -> bool:
        for verify_idx in range(DEFAULT_VERIFY_MAX_ATTEMPTS):
            if not self._wait_with_executor_hooks(0.15):
                return False
            verify_screenshot = self.toolkit.capture_frame(f"候选验证#{verify_idx+1}")
            detection = self.toolkit.detect_popup(
                verify_screenshot,
                f"验证#{verify_idx+1} 搜索候选列表模板",
            )
            if not detection:
                self.logger.log(
                    "候选",
                    f"验证#{verify_idx+1}：候选列表已消失，选择 '{self.target_text}' 成功",
                )
                return True
            verify_details = self._recognize_popup_details(
                verify_screenshot,
                detection,
                f"验证#{verify_idx+1}",
                exclude_top_pixels_override=None,
            )
            if not verify_details or len(verify_details) == 0:
                self.logger.log(
                    "候选",
                    f"验证#{verify_idx+1}：OCR 无文本，视为候选列表已关闭 → '{self.target_text}'",
                )
                return True
            verify_best_editor_pos, _ = self.toolkit.extract_position(
                verify_details,
                detection.popup_rect,
                self.target_cn_text,
                template_match=detection.match,
            )
            if verify_best_editor_pos is not None:
                screen_x2, screen_y2 = self.executor.convert_editor_to_screen_coords(
                    verify_best_editor_pos[0],
                    verify_best_editor_pos[1],
                )
                self.logger.log(
                    "候选",
                    f"验证#{verify_idx+1}：列表仍在，再次点击 '{self.target_text}'",
                    screen=(screen_x2, screen_y2),
                )
                editor_capture.click_left_button(screen_x2, screen_y2)
                overlay = self.toolkit.build_overlay(
                    verify_details,
                    detection.popup_rect,
                    highlight=verify_best_editor_pos,
                    highlight_label=self.target_text,
                )
                self.toolkit.emit_overlay(verify_screenshot, overlay)
            else:
                self.logger.log(
                    "候选",
                    f"验证#{verify_idx+1}：列表仍在但未找到 '{self.target_text}'，继续检测",
                )
        self.logger.log("候选", "验证结束：候选列表仍在，进入下一轮等待/定位")
        return False

    def _handle_popup_absence(self) -> bool:
        self.context.consecutive_no_list += 1
        self.context.last_list_present = False
        self.context.last_popup_digest = None
        self.logger.log("候选", "候选列表不存在（未命中模板），继续等待")
        # 连续未见候选列表达到统一的重试上限后，尝试重新右键触发一次弹窗。
        if self.context.consecutive_no_list >= DEFAULT_VERIFY_MAX_ATTEMPTS:
            self.context.consecutive_no_list = 0
            return self._retry_trigger_popup()
        return self._wait_with_executor_hooks(self.interval)

    def _retry_trigger_popup(self) -> bool:
        last_click_pos = self.executor.get_last_context_click_editor_pos()
        if last_click_pos is not None:
            ax, ay = (int(last_click_pos[0]), int(last_click_pos[1]))
        else:
            snap = self.toolkit.capture_frame("重试右键前")
            rx, ry, rw, rh = editor_capture.get_region_rect(snap, "节点图布置区域")
            ax = int(rx + rw // 2)
            ay = int(ry + rh // 2)
        sx, sy = self.executor.convert_editor_to_screen_coords(ax, ay)
        self.logger.log(
            "候选",
            "连续3次未见候选列表，重试右键触发搜索弹窗",
            editor=(ax, ay),
            screen=(sx, sy),
        )
        if not self.executor.right_click_with_hooks(
            sx,
            sy,
            self.pause_hook,
            self.allow_continue,
            self.log_callback,
            self.visual_callback,
            linger_seconds=NODE_LIST_CONTEXT_LINGER_SECONDS,
        ):
            return False
        return self._wait_with_executor_hooks(RIGHT_CLICK_BEFORE_CAPTURE_WAIT_SECONDS)

    def _record_detection_result(
        self,
        frame: CandidatePopupFrame,
        detection: Optional[CandidatePopupDetection],
        details: Optional[List],
        popup_digest: Optional[str],
    ) -> None:
        self.context.last_screenshot = frame.screenshot
        self.context.last_detection = detection
        if detection is not None:
            self.context.last_popup_rect = detection.popup_rect
            self.context.last_popup_rect_raw = detection.popup_rect_raw
            self.context.last_region_rect = detection.region_rect
        else:
            self.context.last_popup_rect = None
            self.context.last_popup_rect_raw = None
            self.context.last_region_rect = None
        self.context.last_details = details
        self.context.last_search_row = None
        self.context.last_list_present = detection is not None
        self.context.consecutive_no_list = 0
        self.context.last_popup_digest = popup_digest
        self.context.last_frame_digest = frame.frame_digest

    def _wait_interval(self) -> bool:
        waited = self._wait_with_executor_hooks(self.interval)
        if (not waited) and self.allow_continue is not None and not self.allow_continue():
            self.aborted = True
        return waited

    def _check_hooks(self) -> bool:
        if self.pause_hook is not None:
            self.pause_hook()
        if self.allow_continue is not None and not self.allow_continue():
            self.logger.log("候选", "执行被用户终止/暂停，放弃选择候选项")
            self.aborted = True
            return False
        return True

    def _log_wait_state(self, round_idx: int, attempt_idx: int) -> None:
        if self.context.last_list_present:
            self.logger.log(
                "候选",
                f"候选列表已存在，进行 OCR 定位（{attempt_idx+1}/{self.attempts_per_round}，第{round_idx+1}轮）",
            )
        else:
            self.logger.log(
                "候选",
                f"等待候选列表出现（{attempt_idx+1}/{self.attempts_per_round}，第{round_idx+1}轮）",
            )

    def _run_micro_retry(self) -> bool:
        self.logger.log("候选", "微恢复：重开右键并重新输入搜索文本")
        last_click_pos = self.executor.get_last_context_click_editor_pos()
        if last_click_pos is not None:
            editor_x, editor_y = int(last_click_pos[0]), int(last_click_pos[1])
        else:
            snap = editor_capture.capture_window(self.executor.window_title)
            if not snap:
                return True
            graph_region = editor_capture.get_region_rect(snap, "节点图布置区域")
            editor_x = graph_region[0] + graph_region[2] // 2
            editor_y = graph_region[1] + graph_region[3] // 2
        screen_x, screen_y = self.executor.convert_editor_to_screen_coords(editor_x, editor_y)
        self.executor.right_click_with_hooks(
            screen_x,
            screen_y,
            self.pause_hook,
            self.allow_continue,
            self.log_callback,
            self.visual_callback,
            linger_seconds=NODE_LIST_CONTEXT_LINGER_SECONDS,
        )
        waited = self.executor.wait_with_hooks(
            RIGHT_CLICK_BEFORE_CAPTURE_WAIT_SECONDS,
            self.pause_hook,
            self.allow_continue,
            0.1,
            self.log_callback,
        )
        if not waited:
            if self.allow_continue is not None and not self.allow_continue():
                self.aborted = True
            return False
        return self.executor.input_text_with_hooks(
            self.target_text,
            self.pause_hook,
            self.allow_continue,
            self.log_callback,
        )


def _resolve_node_list_template_path(executor) -> Path:
    workspace_root = getattr(executor, "workspace_path", None)
    if workspace_root is None:
        workspace_root = Path(".")
    template_profile = getattr(executor, "ocr_template_profile", "4K-CN")
    return Path(workspace_root) / "assets" / "ocr_templates" / template_profile / "Node_list.png"


def _wait_for_type_search_bar(
    executor,
    log_callback: Optional[Callable[[str], None]],
    *,
    timeout_seconds: float = DEFAULT_TYPE_SELECT_WAIT_SECONDS,
    poll_interval: float = DEFAULT_WAIT_INTERVAL_SECONDS,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> Tuple[Optional[Image.Image], Optional[Tuple[int, int, int, int, float]]]:
    logger = StructuredLogger(executor, log_callback, prefix="[类型选择] ")
    logger.log(
        "输入",
        "等待类型搜索框出现",
        timeout=f"{timeout_seconds:.2f}s",
        templates=[
            executor.search_bar_template_path2.name,
            executor.search_bar_template_path.name,
        ],
    )
    start = time.monotonic()
    attempt = 0
    screenshot: Optional[Image.Image] = None
    while time.monotonic() - start <= float(timeout_seconds):
        screenshot = editor_capture.capture_window(executor.window_title)
        if not screenshot:
            logger.log("输入", "窗口截图失败")
            return None, None
        match = editor_capture.match_template(screenshot, str(executor.search_bar_template_path2))
        template_name = executor.search_bar_template_path2.name
        if not match:
            match = editor_capture.match_template(screenshot, str(executor.search_bar_template_path))
            template_name = executor.search_bar_template_path.name
        if match:
            elapsed = time.monotonic() - start
            logger.log("输入", "类型搜索框已就绪", template=template_name, elapsed=f"{elapsed:.2f}s")
            return screenshot, match
        if attempt == 0:
            logger.log("输入", "类型搜索框尚未出现，继续轮询")
        attempt += 1
        if not executor.wait_with_hooks(
            float(poll_interval),
            pause_hook,
            allow_continue,
            0.1,
            log_callback,
        ):
            logger.log("输入", "执行被用户终止/暂停，放弃等待类型搜索框")
            return None, None
    logger.log("输入", "超时：类型搜索框模板始终未命中")
    return None, None


def click_type_search_and_choose(
    executor,
    target_type_text: str,
    log_callback: Optional[Callable[[str], None]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    screenshot, match = _wait_for_type_search_bar(
        executor,
        log_callback,
        timeout_seconds=DEFAULT_TYPE_SELECT_WAIT_SECONDS,
        poll_interval=DEFAULT_WAIT_INTERVAL_SECONDS,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    if not screenshot or not match:
        return False
    logger = StructuredLogger(executor, log_callback, prefix="[类型选择] ")
    match_left, match_top, match_width, match_height, _ = match
    search_center_editor_x = int(match_left + match_width // 2)
    search_center_editor_y = int(match_top + match_height // 2)
    search_center_screen_x, search_center_screen_y = executor.convert_editor_to_screen_coords(
        search_center_editor_x,
        search_center_editor_y,
    )
    logger.log(
        "输入",
        "点击搜索框",
        editor=(search_center_editor_x, search_center_editor_y),
        screen=(search_center_screen_x, search_center_screen_y),
    )
    rects = [
        {
            "bbox": (int(match_left), int(match_top), int(match_width), int(match_height)),
            "color": (120, 200, 255),
            "label": "类型搜索框",
        }
    ]
    circles = [
        {
            "center": (int(search_center_editor_x), int(search_center_editor_y)),
            "radius": 6,
            "color": (0, 220, 0),
            "label": "点击",
        }
    ]
    executor.emit_visual(screenshot, {"rects": rects, "circles": circles}, visual_callback)
    _exec_utils.click_and_verify(
        executor,
        search_center_screen_x,
        search_center_screen_y,
        "[类型选择] 点击搜索框",
        log_callback,
    )
    logger.log("输入", f"等待 {CONTEXT_MENU_APPEAR_WAIT_SECONDS:.2f} 秒")
    if not executor.wait_with_hooks(CONTEXT_MENU_APPEAR_WAIT_SECONDS, pause_hook, allow_continue, 0.05, log_callback):
        logger.log("输入", "执行被用户终止/暂停，放弃类型选择")
        return False
    logger.log("输入", f"输入类型关键字: '{target_type_text}'")
    editor_capture.input_text(target_type_text)
    logger.log("输入", f"等待 {POST_INPUT_STABILIZE_SECONDS_DEFAULT:.2f} 秒")
    if not executor.wait_with_hooks(POST_INPUT_STABILIZE_SECONDS_DEFAULT, pause_hook, allow_continue, 0.1, log_callback):
        logger.log("输入", "执行被用户终止/暂停，放弃类型选择")
        return False
    # 输入完成后重新识别一次类型搜索框位置，再基于最新位置推导下方候选坐标
    logger.log("输入", "重新识别类型搜索框位置以定位候选")
    refreshed_screenshot = editor_capture.capture_window(executor.window_title)
    if not refreshed_screenshot:
        logger.log("输入", "重新截图失败，放弃类型选择")
        return False
    refreshed_match = editor_capture.match_template(
        refreshed_screenshot,
        str(executor.search_bar_template_path2),
    )
    if not refreshed_match:
        refreshed_match = editor_capture.match_template(
            refreshed_screenshot,
            str(executor.search_bar_template_path),
        )
    if not refreshed_match:
        logger.log("输入", "当前画面未找到类型搜索框，放弃点击候选")
        return False
    refreshed_left, refreshed_top, refreshed_width, refreshed_height, _ = refreshed_match
    candidate_editor_x = int(refreshed_left + refreshed_width // 2)
    candidate_editor_y = int(refreshed_top + refreshed_height + 25)
    candidate_screen_x, candidate_screen_y = executor.convert_editor_to_screen_coords(
        candidate_editor_x,
        candidate_editor_y,
    )
    logger.log(
        "输入",
        "点击下方候选",
        editor=(candidate_editor_x, candidate_editor_y),
        screen=(candidate_screen_x, candidate_screen_y),
    )
    circles2 = [
        {
            "center": (int(candidate_editor_x), int(candidate_editor_y)),
            "radius": 6,
            "color": (255, 200, 0),
            "label": "候选",
        }
    ]
    candidate_rects = [
        {
            "bbox": (
                int(refreshed_left),
                int(refreshed_top),
                int(refreshed_width),
                int(refreshed_height),
            ),
            "color": (120, 200, 255),
            "label": "类型搜索框",
        }
    ]
    executor.emit_visual(
        refreshed_screenshot,
        {"rects": candidate_rects, "circles": circles2},
        visual_callback,
    )
    _exec_utils.click_and_verify(
        executor,
        candidate_screen_x,
        candidate_screen_y,
        "[类型选择] 点击下方候选",
        log_callback,
    )
    return True


def select_from_search_popup(
    executor,
    target_text: str,
    wait_seconds: float = 2.5,
    log_callback: Optional[Callable[[str], None]] = None,
    exclude_top_pixels: Optional[int] = None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    if not target_text:
        StructuredLogger(executor, log_callback, prefix="[候选] ").log("输入", "目标文本为空，无法选择")
        return False
    window_rect = editor_capture.get_window_rect(executor.window_title)
    if not window_rect:
        StructuredLogger(executor, log_callback, prefix="[候选] ").log("输入", "未找到编辑器窗口，无法 OCR 选择")
        return False
    flow = CandidatePopupFlow(
        executor=executor,
        target_text=target_text,
        wait_seconds=wait_seconds,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        exclude_top_pixels=exclude_top_pixels,
    )
    success = flow.run()
    if success:
        return True
    if flow.aborted:
        return False
    flow.emit_failure_visual()
    flow.log_failure_summary()
    return False


__all__ = [
    "CandidatePopupFlow",
    "CandidatePopupContext",
    "CandidatePopupToolkit",
    "select_from_search_popup",
    "click_type_search_and_choose",
    "NODE_LIST_CONTEXT_LINGER_SECONDS",
]

