# -*- coding: utf-8 -*-
"""
一次性动作：检查页面、OCR/节点/端口/模板等测试
回调驱动，不直接持有 UI 状态
"""

from typing import Optional

from PIL import Image
from app.automation import capture as editor_capture
from app.automation import AutomationFacade
from app.automation.vision import list_nodes as _vision_list_nodes
from app.automation.vision import list_ports as _vision_list_ports
from app.automation.vision import invalidate_cache as _vision_invalidate
from app.automation.vision import get_last_node_filter_report as _vision_get_node_filter_report

_SUPPRESSION_REASON_LABELS = {
    "iou": "IoU重叠",
    "containment": "包含关系",
    "center_overlap": "中心接近",
}
from app.automation.input.common import set_visual_sink as _set_visual_sink
from app.automation.input.common import clear_visual_sink as _clear_visual_sink
from app.automation.input.common import set_log_sink as _set_log_sink
from app.automation.input.common import clear_log_sink as _clear_log_sink


class RecognitionActions:
    """识别与测试动作集合，接受回调与上下文访问器"""

    def __init__(
        self,
        log_callback,
        update_visual_callback,
        get_graph_model_callback,
        get_workspace_path_callback,
        get_window_title_callback,
    ):
        self._log = log_callback
        self._update_visual = update_visual_callback
        self._get_graph_model = get_graph_model_callback
        self._get_workspace_path = get_workspace_path_callback
        self._get_window_title = get_window_title_callback

    def check_current_page(self) -> None:
        """一次性执行：截图→识别（节点/端口）→叠加绘制→显示在面板，即使未开始监控也可显示。"""
        # 通过 Facade 截图，避免直接依赖内部实现
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ 截图失败，未找到目标窗口")
            return
        region_x, region_y, region_w, region_h = editor_capture.get_region_rect(screenshot, "节点图布置区域")
        # 统一通过视觉门面识别（标题已映射为库里的完整名）
        _vision_invalidate()
        recognized_nodes = _vision_list_nodes(screenshot)

        # 获取当前打开的图模型用于比对
        graph_model = self._get_graph_model()

        model_titles: set[str] = set()
        if graph_model is not None and hasattr(graph_model, 'nodes'):
            model_titles = {str(n.title) for n in graph_model.nodes.values()}

        # 构建覆盖层：对节点框按"是否在当前图中出现"着色
        rects: list[dict] = []
        circles: list[dict] = []
        matched_count = 0
        unmatched_count = 0
        recognized_titles: list[str] = []
        for rn in recognized_nodes:
            x, y, w, h = rn.bbox
            wx = int(x)
            wy = int(y)
            title_cn = str(getattr(rn, 'name_cn', '') or "")
            recognized_titles.append(title_cn)
            is_matched = bool(title_cn and (title_cn in model_titles)) if model_titles else False
            color = (76, 175, 80) if is_matched else (244, 67, 54)  # 绿=匹配，红=未匹配
            if is_matched:
                matched_count += 1
            else:
                unmatched_count += 1
            rects.append({
                'bbox': (wx, wy, int(w), int(h)),
                'color': color,
                'label': ("✓ " + title_cn) if is_matched else ("✗ " + title_cn)
            })

            # 端口标注：通过视觉门面按窗口坐标获取
            ports = _vision_list_ports(screenshot, (int(x), int(y), int(w), int(h)))
            for rp in ports:
                px, py, pw, ph = rp.bbox
                pcx, pcy = rp.center
                kind_lower = str(getattr(rp, 'kind', '') or "").lower()
                port_color = (255, 200, 0) if 'flow' in kind_lower else ((0, 200, 120) if 'data' in kind_lower else (180, 180, 255))
                rects.append({
                    'bbox': (int(px), int(py), int(pw), int(ph)),
                    'color': port_color,
                    'label': f"{str(getattr(rp,'side',''))}#{'' if getattr(rp,'index',None) is None else int(getattr(rp,'index'))} {str(getattr(rp,'kind',''))}"
                })
                circles.append({
                    'center': (int(pcx), int(pcy)),
                    'radius': 6,
                    'color': port_color,
                    'label': ''
                })

        # 统计当前图中未被识别到的节点（名称存在于模型但未被识别）
        missing_in_view: list[str] = []
        if model_titles:
            rec_set = {t for t in recognized_titles if t}
            missing_in_view = sorted([t for t in model_titles if t not in rec_set])

        overlays = { 'rects': rects, 'circles': circles }
        self._update_visual(screenshot, overlays)

        if model_titles:
            msg = (
                f"✓ 检查完成：识别 {len(recognized_nodes)} 个；与当前图匹配 {matched_count} 个；"
                f"未匹配 {unmatched_count} 个；视图缺失 {len(missing_in_view)} 个。"
            )
            self._log(msg)
            if missing_in_view:
                preview_list = ", ".join(missing_in_view[:8])
                more = " 等" if len(missing_in_view) > 8 else ""
                self._log(f"· 当前图未识别到：{preview_list}{more}")
        else:
            self._log(f"✓ 检查完成：检测到 {len(recognized_nodes)} 个节点；已与模型无关地叠加显示在监控画面。")

    def test_ocr(self) -> None:
        """一次性 OCR 测试：对顶部标签栏执行 OCR 并叠加可视化。"""
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ OCR 测试失败：未找到目标窗口")
            return
        rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "顶部标签栏")
        # 将监控面板注册为全局可视化与日志汇聚器（调用后清理）
        _set_visual_sink(self._update_visual)
        _set_log_sink(self._log)
        text_result = editor_capture.ocr_recognize_region(
            screenshot,
            (int(rx), int(ry), int(rw), int(rh)),
            return_details=False,
        )
        preview_source = text_result[0] if isinstance(text_result, tuple) else text_result
        preview = str(preview_source or "").strip()
        _clear_visual_sink()
        _clear_log_sink()
        if preview:
            self._log(f"✓ OCR 测试完成：'{preview}'")
        else:
            self._log("✓ OCR 测试完成：未识别到文本")

    def test_settings(self) -> None:
        """Settings 按钮行识别测试：优先基于当前图扫描；无模型时回退为全局检测扫描。"""
        graph_model = self._get_graph_model()
        if graph_model is not None and hasattr(graph_model, 'nodes') and int(len(graph_model.nodes)) > 0 and self._get_workspace_path() is not None:
            from app.automation.core.editor_executor import EditorExecutor
            from app.automation.core import editor_connect as _editor_connect
            executor = EditorExecutor(self._get_workspace_path())
            all_ids = list(getattr(graph_model, 'nodes').keys())
            node_ids_for_scan = [str(x) for x in all_ids[: min(len(all_ids), 30)]]
            todo_item = { 'node_ids': node_ids_for_scan }
            execute_scan_settings = getattr(_editor_connect, "execute_scan_settings")
            scanned_map = execute_scan_settings(
                executor,
                todo_item,
                graph_model,
                log_callback=self._log,
                pause_hook=None,
                allow_continue=None,
                visual_callback=self._update_visual,
            )
            total_hits = sum(len(items) for items in scanned_map.values())
            if scanned_map:
                self._log(
                    f"✓ Settings 按钮识别测试完成：扫描 {len(node_ids_for_scan)} 个节点，命中 {total_hits} 条 Settings 记录"
                )
            else:
                self._log("✗ Settings 按钮识别测试未通过（见上方日志）")
            return

        # 回退：基于视觉检测到的节点逐个列举 Settings 行
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ Settings 测试失败：未找到目标窗口")
            return
        detected = _vision_list_nodes(screenshot)
        rects = []
        hit_count = 0
        for dn in detected:
            bx, by, bw, bh = dn.bbox
            rects.append({'bbox': (int(bx), int(by), int(bw), int(bh)), 'color': (100, 160, 255), 'label': str(getattr(dn, 'name_cn', '') or '')})
            ports = _vision_list_ports(screenshot, (int(bx), int(by), int(bw), int(bh)))
            for p in ports:
                if str(getattr(p, 'kind', '') or '').lower() == 'settings':
                    px, py, pw, ph = p.bbox
                    rects.append({'bbox': (int(px), int(py), int(pw), int(ph)), 'color': (255, 120, 0), 'label': f"Settings {str(getattr(p,'side',''))}#{str(getattr(p,'index',''))}"})
                    hit_count += 1
        overlays = { 'rects': rects }
        self._update_visual(screenshot, overlays)
        self._log(f"✓ Settings 回退扫描完成：检测到 {len(detected)} 个节点，命中 Settings 行 {hit_count} 项")

    def test_warning(self) -> None:
        """Warning 模板匹配测试：在节点图区域内搜索 Warning.png 并展示命中。"""
        if self._get_workspace_path() is None:
            self._log("✗ Warning 测试失败：缺少工作区路径")
            return
        from app.automation.core.editor_executor import EditorExecutor
        executor = EditorExecutor(self._get_workspace_path())
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ Warning 测试失败：未找到目标窗口")
            return
        region_x, region_y, region_w, region_h = editor_capture.get_region_rect(screenshot, "节点图布置区域")
        # 使用模板匹配并将可视化与日志汇聚至本面板
        _set_visual_sink(self._update_visual)
        _set_log_sink(self._log)
        _ = editor_capture.match_template(
            screenshot,
            str(executor.node_warning_template_path),
            search_region=(int(region_x), int(region_y), int(region_w), int(region_h)),
        )
        _clear_visual_sink()
        _clear_log_sink()
        self._log("✓ Warning 模板匹配测试完成（详见叠加画面与日志）")

    def test_ocr_zoom(self) -> None:
        """OCR 缩放：识别节点图缩放区域（期望 50% 等百分比文本）"""
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ OCR 缩放测试失败：未找到目标窗口")
            return
        rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "节点图缩放区域")
        _set_visual_sink(self._update_visual)
        _set_log_sink(self._log)
        text_result = editor_capture.ocr_recognize_region(
            screenshot,
            (int(rx), int(ry), int(rw), int(rh)),
            return_details=False,
            exclude_top_pixels=0,
        )
        preview_source = text_result[0] if isinstance(text_result, tuple) else text_result
        preview = str(preview_source or "").strip()
        _clear_visual_sink()
        _clear_log_sink()
        self._log(f"✓ OCR 缩放测试完成：'{preview}'")

    def test_nodes(self) -> None:
        """节点识别：叠加显示检测到的节点矩形与中文标题"""
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ 节点识别测试失败：未找到目标窗口")
            return
        nodes = _vision_list_nodes(screenshot)
        filter_report = _vision_get_node_filter_report()
        raw_count = int(filter_report.get("raw_count", len(nodes)))
        suppressed_entries = list(filter_report.get("suppressed", []))
        rects = []

        def _extract_reason_info(entry_dict) -> tuple[str, str, Optional[float]]:
            reason_key_local = str(entry_dict.get("reason") or "")
            reason_label_local = str(_SUPPRESSION_REASON_LABELS.get(reason_key_local, reason_key_local)).strip()
            metrics_local = entry_dict.get("overlap_metrics") or {}
            metric_value_local: Optional[float] = None
            if reason_key_local == "iou":
                metric_value_local = metrics_local.get("iou")
            elif reason_key_local == "containment":
                metric_value_local = metrics_local.get("containment_ratio")
            elif reason_key_local == "center_overlap":
                metric_value_local = metrics_local.get("center_distance")
                if isinstance(metric_value_local, (int, float)):
                    metric_value_local = float(metric_value_local)
            return reason_key_local, reason_label_local, metric_value_local

        for nd in nodes:
            bx, by, bw, bh = nd.bbox
            cn = str(getattr(nd, 'name_cn', '') or '')
            rects.append({'bbox': (int(bx), int(by), int(bw), int(bh)), 'color': (80, 220, 120), 'label': cn})
        suppressed_overlay_color = (255, 140, 140)
        for entry in suppressed_entries:
            bbox = entry.get("bbox")
            if not bbox:
                continue
            sx, sy, sw, sh = bbox
            suppressed_title = str(entry.get("title_cn") or "未命名")
            overlap_target_title = str(entry.get("overlap_target_title") or "")
            _, reason_label, metric_value = _extract_reason_info(entry)
            reason_suffix = ""
            if isinstance(metric_value, (int, float)):
                reason_suffix = f"{reason_label}={round(float(metric_value), 3)}" if reason_label else f"{round(float(metric_value), 3)}"
            label = "[被抑制]"
            if reason_suffix:
                label += f"({reason_suffix})"
            elif reason_label:
                label += f"({reason_label})"
            label += f" {suppressed_title}"
            if overlap_target_title:
                label += f" ← {overlap_target_title}"
            rects.append({
                'bbox': (int(sx), int(sy), int(sw), int(sh)),
                'color': suppressed_overlay_color,
                'label': label
            })
        self._update_visual(screenshot, { 'rects': rects })
        self._log(f"✓ 节点识别测试：检测 {len(nodes)} 个")
        if suppressed_entries or raw_count != len(nodes):
            preview_snippets: list[str] = []
            for entry in suppressed_entries[:2]:
                suppressed_title = str(entry.get("title_cn") or "未命名")
                overlap_title = str(entry.get("overlap_target_title") or "未知")
                suppressed_bbox = entry.get("bbox")
                overlap_bbox = entry.get("overlap_target_bbox")
                bbox_text = f"{tuple(int(v) for v in suppressed_bbox)}" if suppressed_bbox else ""
                overlap_bbox_text = f"{tuple(int(v) for v in overlap_bbox)}" if overlap_bbox else ""
                _, reason_label, metric_value = _extract_reason_info(entry)
                reason_display = ""
                if isinstance(metric_value, (int, float)):
                    reason_display = f"{reason_label}={round(float(metric_value), 3)}" if reason_label else f"{round(float(metric_value), 3)}"
                elif reason_label:
                    reason_display = reason_label
                reason_segment = f"[{reason_display}] " if reason_display else ""
                preview_snippets.append(
                    f"{reason_segment}{suppressed_title}{(' ' + bbox_text) if bbox_text else ''} ← {overlap_title}{(' ' + overlap_bbox_text) if overlap_bbox_text else ''}"
                )
            extra_suffix = " 等" if len(suppressed_entries) > 2 else ""
            detail = f"· 原始识别 {raw_count} 个，去重抑制 {len(suppressed_entries)} 个"
            if preview_snippets:
                detail += f"（{'; '.join(preview_snippets)}{extra_suffix}）"
            self._log(detail)

    def test_ports(self) -> None:
        """端口识别：为每个检测到的节点标注端口（含 kind/side/index）"""
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ 端口识别测试失败：未找到目标窗口")
            return
        nodes = _vision_list_nodes(screenshot)
        rects: list[dict] = []
        for nd in nodes:
            bx, by, bw, bh = nd.bbox
            rects.append({'bbox': (int(bx), int(by), int(bw), int(bh)), 'color': (140, 160, 255), 'label': str(getattr(nd, 'name_cn','') or '')})
            ports = _vision_list_ports(screenshot, (int(bx), int(by), int(bw), int(bh)))
            for p in ports:
                px, py, pw, ph = p.bbox
                kind = str(getattr(p, 'kind', '') or '')
                side = str(getattr(p, 'side', '') or '')
                index_val = getattr(p, 'index', '')
                confidence_val = getattr(p, 'confidence', None)
                confidence_text = ""
                if isinstance(confidence_val, (int, float)):
                    normalized_confidence = float(confidence_val)
                    if normalized_confidence < 0.0:
                        normalized_confidence = 0.0
                    if normalized_confidence > 1.0:
                        normalized_confidence = 1.0
                    confidence_percent = int(round(normalized_confidence * 100.0))
                    confidence_text = f" {confidence_percent}%"
                color = (255, 160, 80) if side == 'right' else (0, 200, 140)
                rects.append({
                    'bbox': (int(px), int(py), int(pw), int(ph)),
                    'color': color,
                    'label': f"{side}#{index_val}[{kind}]{confidence_text}",
                })
        self._update_visual(screenshot, { 'rects': rects })
        self._log("✓ 端口识别测试完成")

    def test_settings_tpl(self) -> None:
        """模板匹配：Settings.png"""
        if self._get_workspace_path() is None:
            self._log("✗ Settings模板测试失败：缺少工作区路径")
            return
        from app.automation.core.editor_executor import EditorExecutor
        executor = EditorExecutor(self._get_workspace_path())
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ Settings模板测试失败：未找到目标窗口")
            return
        rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "节点图布置区域")
        _set_visual_sink(self._update_visual)
        _set_log_sink(self._log)
        _ = editor_capture.match_template(screenshot, str(executor.node_settings_template_path), search_region=(int(rx), int(ry), int(rw), int(rh)))
        _clear_visual_sink()
        _clear_log_sink()
        self._log("✓ Settings 模板匹配测试完成")

    def test_add_templates(self) -> None:
        """模板匹配：Add.png / Add_Multi.png"""
        if self._get_workspace_path() is None:
            self._log("✗ Add模板测试失败：缺少工作区路径")
            return
        from app.automation.core.editor_executor import EditorExecutor
        executor = EditorExecutor(self._get_workspace_path())
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ Add模板测试失败：未找到目标窗口")
            return
        rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "节点图布置区域")
        _set_visual_sink(self._update_visual)
        _set_log_sink(self._log)
        _ = editor_capture.match_template(screenshot, str(executor.node_add_template_path), search_region=(int(rx), int(ry), int(rw), int(rh)))
        _ = editor_capture.match_template(screenshot, str(executor.node_add_multi_template_path), search_region=(int(rx), int(ry), int(rw), int(rh)))
        _clear_visual_sink()
        _clear_log_sink()
        self._log("✓ Add 模板匹配测试完成")

    def test_searchbar_templates(self) -> None:
        """模板匹配：search.png / search2.png"""
        if self._get_workspace_path() is None:
            self._log("✗ 搜索框模板测试失败：缺少工作区路径")
            return
        from app.automation.core.editor_executor import EditorExecutor
        executor = EditorExecutor(self._get_workspace_path())
        facade = AutomationFacade()
        screenshot = facade.capture_window(self._get_window_title())
        if not screenshot:
            self._log("✗ 搜索框模板测试失败：未找到目标窗口")
            return
        _set_visual_sink(self._update_visual)
        _set_log_sink(self._log)
        _ = editor_capture.match_template(screenshot, str(executor.search_bar_template_path), search_region=None)
        _ = editor_capture.match_template(screenshot, str(executor.search_bar_template_path2), search_region=None)
        _clear_visual_sink()
        _clear_log_sink()
        self._log("✓ 搜索框模板匹配测试完成")

