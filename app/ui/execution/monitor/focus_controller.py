# -*- coding: utf-8 -*-
"""
"定位镜头"识别与视口对齐
回调驱动，提供识别成功后的节点可见性列表通知。

额外调试能力：
- 在每次成功执行“定位镜头”后，将当前视口下可见节点的识别结果
  （节点ID、标题、程序坐标、编辑器 bbox 等）落盘为 JSON，便于后续
  离线复现与问题排查。
"""

from pathlib import Path

from PyQt6 import QtCore

from app.automation.editor.executor_protocol import ViewportController
from app.runtime.services import get_shared_json_cache_service
from app.automation.vision import get_last_raw_title_rects as _get_last_raw_title_rects


class FocusController:
    """匹配并定位镜头：识别当前画面、几何拟合、视口对齐"""

    def __init__(
        self,
        log_callback,
        update_visual_callback,
        get_graph_model_callback,
        get_workspace_path_callback,
        get_graph_view_callback,
        on_focus_succeeded_callback,
        get_shared_executor_callback=None,
        set_shared_executor_callback=None,
    ):
        self._log = log_callback
        self._update_visual = update_visual_callback
        self._get_graph_model = get_graph_model_callback
        self._get_workspace_path = get_workspace_path_callback
        self._get_graph_view = get_graph_view_callback
        self._on_focus_succeeded = on_focus_succeeded_callback
        self._get_shared_executor = get_shared_executor_callback
        self._set_shared_executor = set_shared_executor_callback
        self._last_program_viewport_rect: tuple[float, float, float, float] | None = None
        # 既作为执行器被执行线程使用，又作为 ViewportController 被本控制器使用
        self._executor: ViewportController | None = None

    def get_last_program_viewport_rect(self):
        """返回最近一次定位镜头时的程序视口矩形 (left, top, width, height)。"""
        return self._last_program_viewport_rect

    def get_last_program_viewport_center(self):
        """返回最近一次定位镜头时的程序视口中心点程序坐标 (x, y)。"""
        rect = self._last_program_viewport_rect
        if rect is None:
            return None
        left, top, width, height = rect
        center_x = float(left) + float(width) * 0.5
        center_y = float(top) + float(height) * 0.5
        return (center_x, center_y)

    def _get_effective_executor_for_drag(self) -> ViewportController | None:
        """获取可用于拖拽测试的视口控制器实例。

        优先使用本地缓存，其次尝试从外部共享入口获取；
        返回对象在语义上同时也是执行器实例。
        """
        executor = self._executor
        if executor is None and self._get_shared_executor is not None:
            shared = self._get_shared_executor()
            if shared is not None:
                executor = shared
                self._executor = shared
        return executor

    def _dump_last_focus_recognition_snapshot(
        self,
        workspace_path,
        graph_model,
        visible_map: dict[str, dict],
    ) -> None:
        """将最近一次“定位镜头”下的可见节点识别结果落盘为 JSON。

        保存内容仅用于调试与离线分析，不参与运行时逻辑：
        - 路径：{runtime_cache_root}/debug/last_focus_recognition.json（默认 runtime_cache_root 为 app/runtime/cache）
        - 字段：graph_id、节点ID、标题、程序坐标、可见标记、编辑器 bbox / center / screen_center。
        """
        workspace_root = Path(workspace_path)

        graph_id_value = getattr(graph_model, "graph_id", None)
        if graph_id_value is None:
            graph_id_text = ""
        else:
            graph_id_text = str(graph_id_value)

        nodes_payload: list[dict] = []
        for node_id, info in visible_map.items():
            node_model = graph_model.nodes.get(node_id)
            node_title_text = ""
            program_pos_x = 0.0
            program_pos_y = 0.0
            if node_model is not None:
                if getattr(node_model, "title", None) is not None:
                    node_title_text = str(node_model.title).strip()
                if getattr(node_model, "pos", None) is not None:
                    program_pos_x = float(node_model.pos[0])
                    program_pos_y = float(node_model.pos[1])

            bbox_value = info.get("bbox")
            if isinstance(bbox_value, (list, tuple)) and len(bbox_value) == 4:
                bbox_list = [
                    int(bbox_value[0]),
                    int(bbox_value[1]),
                    int(bbox_value[2]),
                    int(bbox_value[3]),
                ]
            else:
                bbox_list = None

            center_value = info.get("center")
            if isinstance(center_value, (list, tuple)) and len(center_value) == 2:
                center_list = [int(center_value[0]), int(center_value[1])]
            else:
                center_list = None

            screen_center_value = info.get("screen_center")
            if isinstance(screen_center_value, (list, tuple)) and len(screen_center_value) == 2:
                screen_center_list = [
                    int(screen_center_value[0]),
                    int(screen_center_value[1]),
                ]
            else:
                screen_center_list = None

            nodes_payload.append(
                {
                    "node_id": str(node_id),
                    "title": node_title_text,
                    "program_pos": [float(program_pos_x), float(program_pos_y)],
                    "visible": bool(info.get("visible")),
                    "bbox": bbox_list,
                    "center": center_list,
                    "screen_center": screen_center_list,
                }
            )

        payload = {
            "graph_id": graph_id_text,
            "node_count": int(len(nodes_payload)),
            "nodes": nodes_payload,
        }

        cache_service = get_shared_json_cache_service(workspace_root)
        cache_service.save_json(
            "debug/last_focus_recognition.json",
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    def ensure_point_visible(self, program_x: float, program_y: float) -> None:
        """使用与执行步骤相同的画布拖拽逻辑，确保指定程序坐标点出现在安全视口区域内。

        依赖前置：
        - 至少成功执行过一次 `match_and_focus()`，以建立坐标映射与缩放状态；
        - 当前必须可获取 GraphModel 作为可见性与距离判定的依据。
        """
        graph_model = self._get_graph_model()
        if graph_model is None or not hasattr(graph_model, "nodes") or int(len(graph_model.nodes)) == 0:
            self._log("✗ 拖拽测试：当前未注入任何节点图模型，无法执行拖拽")
            return

        viewport_controller = self._get_effective_executor_for_drag()
        if viewport_controller is None:
            self._log("✗ 拖拽测试：尚未建立坐标映射，请先点击一次“定位镜头”按钮")
            return
        if getattr(viewport_controller, "scale_ratio", None) is None or getattr(viewport_controller, "origin_node_pos", None) is None:
            self._log("✗ 拖拽测试：当前坐标映射尚未完成，请先成功执行一次“定位镜头”")
            return

        # 记录拖拽前的视口矩形，便于对比视口是否发生了实际平移
        vp_before_left, vp_before_top, vp_before_w, vp_before_h = viewport_controller.get_program_viewport_rect()
        self._log(
            f"· 拖拽测试前编辑器视口(程序坐标)：({vp_before_left:.1f}, {vp_before_top:.1f}, {vp_before_w:.1f}, {vp_before_h:.1f})"
        )
        self._log(
            f"拖拽测试：尝试将视口平移到程序坐标 ({float(program_x):.1f}, {float(program_y):.1f}) 附近…"
        )
        viewport_controller.ensure_program_point_visible(
            float(program_x),
            float(program_y),
            margin_ratio=0.10,
            max_steps=8,
            pan_step_pixels=420,
            log_callback=self._log,
            pause_hook=None,
            allow_continue=None,
            visual_callback=self._update_visual,
            graph_model=graph_model,
            force_pan_if_inside_margin=True,
        )
        # 拖拽后重新获取一次视口矩形，便于在监控面板中展示最新的中心坐标
        vp_left, vp_top, vp_w, vp_h = viewport_controller.get_program_viewport_rect()
        self._last_program_viewport_rect = (
            float(vp_left),
            float(vp_top),
            float(vp_w),
            float(vp_h),
        )
        self._log(
            f"· 拖拽测试后编辑器视口(程序坐标)：({vp_left:.1f}, {vp_top:.1f}, {vp_w:.1f}, {vp_h:.1f})"
        )

    def match_and_focus(self) -> None:
        # 以"用户当前正在查看的节点图"为准：优先使用注入的当前图（任务清单预览/执行上下文），再回退到编辑器回调
        graph_model = self._get_graph_model()
        # 无当前图或无节点：直接日志提示，不进行截图与匹配
        if graph_model is None or not hasattr(graph_model, 'nodes') or int(len(graph_model.nodes)) == 0:
            self._log("✗ 当前未打开任何节点图或图中无节点：跳过匹配与定位（不截图）")
            return
        workspace_path = self._get_workspace_path()
        if workspace_path is None:
            self._log("✗ 缺少工作区路径，无法创建执行器进行识别")
            return

        from app.automation.editor.editor_executor import EditorExecutor

        # 优先复用外部共享的执行器实例（与执行线程共享），保持视口状态一致
        executor = None
        if self._get_shared_executor is not None:
            shared = self._get_shared_executor()
            if shared is not None and getattr(shared, "workspace_path", None) == workspace_path:
                executor = shared
        if executor is None:
            executor = EditorExecutor(workspace_path)

        # 先确保画布缩放为 50%，避免比例失配导致后续识别/拟合错误
        self._log("检查缩放(50%)…")
        ok_zoom = executor.ensure_zoom_ratio_50(
            log_callback=self._log,
            pause_hook=None,
            allow_continue=None,
            visual_callback=self._update_visual,
        )
        if not ok_zoom:
            self._log("✗ 无法将缩放调整为 50%，已取消定位镜头")
            return

        self._log("匹配并定位：开始识别与几何拟合（三阶段：唯一锚点→普通锚点→普通节点兜底）…")
        ok_fit = executor.verify_and_update_view_mapping_by_recognition(
            graph_model,
            log_callback=self._log,
            visual_callback=self._update_visual,
        )
        if not ok_fit:
            self._log("✗ 识别/几何拟合未通过（锚点与普通节点匹配均失败），无法定位镜头")
            return

        # 至此，坐标映射已建立，可以安全地将执行器标记为“可用于拖拽/定位”
        self._executor = executor
        if self._set_shared_executor is not None:
            self._set_shared_executor(executor)

        self._log("✓ 识别/几何拟合通过，准备按编辑器视口对齐程序视图…")

        # 在视口对齐前，先将当前可见节点的识别结果回填到程序坐标，避免坐标陈旧导致后续可见性判断失真
        updated_count = executor.sync_visible_nodes_positions(
            graph_model,
            threshold_px=40.0,
            log_callback=self._log,
        )
        if int(updated_count) > 0:
            self._log(f"· 根据识别结果更新了 {int(updated_count)} 个节点的程序坐标")

        # 直接按外部编辑器"当前视口矩形"在程序坐标中的投影进行聚焦，使两边视图看起来一致
        vp_left, vp_top, vp_w, vp_h = executor.get_program_viewport_rect()
        self._last_program_viewport_rect = (
            float(vp_left),
            float(vp_top),
            float(vp_w),
            float(vp_h),
        )
        self._log(f"· 当前编辑器视口(程序坐标)：({vp_left:.1f}, {vp_top:.1f}, {vp_w:.1f}, {vp_h:.1f})")
        target_rect = QtCore.QRectF(float(vp_left), float(vp_top), float(vp_w), float(vp_h))

        view = self._get_graph_view()
        if view is None:
            self._log("✗ 无法访问图视图(GraphView)，定位步骤已取消")
            return

        # 使用视口矩形精确定位（不增加额外边距），以保证两边视图"看起来一致"
        if hasattr(view, '_execute_focus_on_rect') and callable(getattr(view, '_execute_focus_on_rect')):
            view._execute_focus_on_rect(target_rect, padding_ratio=1.0)
        else:
            view.centerOn(target_rect.center())
        self._log("✓ 已按当前编辑器视口在程序坐标中完成镜头定位")

        # —— 定位完成：统计当前画面中可见的模型节点，并向任务清单页面发出联动信号 ——
        visible_map_after = executor.recognize_visible_nodes(graph_model)
        # 将本次“定位镜头”下的可见节点识别结果落盘，便于后续离线分析与复现。
        self._dump_last_focus_recognition_snapshot(
            workspace_path=workspace_path,
            graph_model=graph_model,
            visible_map=visible_map_after,
        )
        visible_ids_after = [node_id for node_id, info in visible_map_after.items() if bool(info.get("visible"))]
        if len(visible_ids_after) > 0:
            self._on_focus_succeeded(visible_ids_after)

            # 为当前可见节点构建覆盖层：在监控截图上为每个识别到的节点绘制矩形并标注节点ID
            def _build_visible_nodes_overlay(image) -> dict:
                raw_title_by_bbox: dict[tuple[int, int, int, int], str] = {}
                raw_title_rects = _get_last_raw_title_rects()
                for raw_title, rect in raw_title_rects:
                    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
                        continue
                    rect_left, rect_top, rect_w, rect_h = rect
                    key = (int(rect_left), int(rect_top), int(rect_w), int(rect_h))
                    raw_title_by_bbox[key] = str(raw_title or "").strip()

                rect_items: list[dict] = []
                for node_id, info in visible_map_after.items():
                    if not bool(info.get("visible")):
                        continue
                    bbox = info.get("bbox")
                    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                        continue
                    bbox_left, bbox_top, bbox_width, bbox_height = bbox
                    bbox_key = (
                        int(bbox_left),
                        int(bbox_top),
                        int(bbox_width),
                        int(bbox_height),
                    )
                    node_model = graph_model.nodes.get(node_id)
                    node_title_text = ""
                    if node_model is not None and getattr(node_model, "title", None) is not None:
                        node_title_text = str(node_model.title).strip()

                    # 识别标题（纠错后）：来自可见性识别结果（list_nodes 的 name_cn）
                    recognized_title_text = str(info.get("recognized_title", "") or "").strip()
                    # OCR 原始标题（不映射）：由 vision_backend 缓存提供，按 bbox 对齐
                    raw_title_text = str(raw_title_by_bbox.get(bbox_key, "") or "").strip()

                    # label 文案策略（保持单行，避免监控画面过度拥挤）：
                    # - 优先展示模型标题；
                    # - 若存在 raw!=recognized，则附加 "OCR:raw→recognized"；
                    # - 若识别标题缺失但 raw 存在，则附加 "OCR:raw"；
                    # - 无模型标题时至少显示 node_id，避免 label 为空导致完全不显示。
                    base = node_title_text or recognized_title_text or raw_title_text or str(node_id)
                    extras = ""
                    if raw_title_text and recognized_title_text and raw_title_text != recognized_title_text:
                        extras = f" OCR:{raw_title_text}→{recognized_title_text}"
                    elif raw_title_text and not recognized_title_text:
                        extras = f" OCR:{raw_title_text}"
                    elif recognized_title_text and not raw_title_text and node_title_text and node_title_text != recognized_title_text:
                        extras = f" 识别:{recognized_title_text}"

                    label_text = f"{base}{extras} ({node_id})" if str(node_id) else f"{base}{extras}"
                    rect_items.append(
                        {
                            "bbox": (
                                int(bbox_left),
                                int(bbox_top),
                                int(bbox_width),
                                int(bbox_height),
                            ),
                            "color": (80, 220, 120),
                            "label": label_text,
                        }
                    )
                return {"rects": rect_items}

            # 推送一帧带有“可见节点ID标签”的截图到执行监控面板（使用严格窗口截图，尽量避免遮挡）
            executor.capture_and_emit(
                label="定位镜头-可见节点ID",
                overlays_builder=_build_visible_nodes_overlay,
                visual_callback=self._update_visual,
                use_strict_window_capture=True,
            )

            # 调试：输出当前视口可见节点的名称与X范围，辅助判断定位到哪一支分支
            titles_after: list[str] = []
            x_min_list: list[int] = []
            x_max_list: list[int] = []
            for node_id in visible_ids_after:
                node_model = graph_model.nodes.get(node_id)
                if node_model is not None:
                    titles_after.append(str(node_model.title))
            for info in visible_map_after.values():
                if bool(info.get("visible")) and isinstance(info.get("bbox"), (list, tuple)):
                    bbox_left, bbox_top, bbox_width, bbox_height = info["bbox"]
                    x_min_list.append(int(bbox_left))
                    x_max_list.append(int(bbox_left) + int(bbox_width))
            if len(titles_after) > 0:
                preview = ", ".join(titles_after[:8]) + (" 等" if len(titles_after) > 8 else "")
                self._log(f"· 可见节点(调试)：{len(titles_after)} 个：{preview}")
            if len(x_min_list) > 0 and len(x_max_list) > 0:
                self._log(f"· 可见区域X范围(调试)：[{min(x_min_list)}, {max(x_max_list)}]")

