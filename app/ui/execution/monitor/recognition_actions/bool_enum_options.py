# -*- coding: utf-8 -*-
from __future__ import annotations

from app.automation import AutomationFacade
from app.automation import capture as editor_capture
from app.automation.vision import invalidate_cache as _vision_invalidate
from app.automation.vision import list_nodes as _vision_list_nodes
from app.automation.vision import list_ports as _vision_list_ports

from .shared import _temporary_global_sinks


def test_bool_enum_options(self) -> None:
    """布尔/枚举选项识别：识别可见布尔/枚举端口→点击展开→扫描 D7D7D7 下拉矩形→OCR。"""
    workspace_path = self._get_workspace_path()
    if workspace_path is None:
        self._log("✗ 布尔/枚举选项测试失败：缺少工作区路径")
        return

    window_title = self._get_window_title()
    window_title_text = str(window_title or "").strip()
    if not window_title_text:
        self._log("✗ 布尔/枚举选项测试失败：缺少窗口标题")
        return

    from app.automation.editor.editor_executor import EditorExecutor
    from app.automation.editor import executor_utils as _exec_utils
    from app.automation.input.common import sleep_seconds
    from app.automation.config.config_params_helpers import (
        filter_screen_input_candidates,
        format_candidates_brief,
    )
    from app.automation.ports._ports import normalize_kind_text
    from app.automation.editor.node_library_provider import get_node_library

    executor = EditorExecutor(workspace_path)
    facade = AutomationFacade()
    facade.focus_editor(window_title_text)

    _vision_invalidate()
    screenshot_before = facade.capture_window(window_title_text)
    if not screenshot_before:
        self._log("✗ 布尔/枚举选项测试失败：未找到目标窗口")
        return

    visible_nodes = _vision_list_nodes(screenshot_before)
    if not visible_nodes:
        self._update_visual(
            screenshot_before,
            {
                "rects": [],
                "circles": [],
                "header": "布尔/枚举选项：未识别到任何节点",
            },
        )
        self._log("✗ 布尔/枚举选项测试失败：画面中未识别到任何节点")
        return

    node_library = get_node_library(workspace_path, include_composite=True)
    node_defs_by_name: dict[str, list] = {}
    for node_def in node_library.values():
        node_name = str(getattr(node_def, "name", "") or "").strip()
        if node_name:
            node_defs_by_name.setdefault(node_name, []).append(node_def)

    selected_node_title: str | None = None
    selected_node_bbox: tuple[int, int, int, int] | None = None
    selected_port_name: str | None = None
    selected_declared_type: str | None = None
    selected_port_center: tuple[int, int] | None = None
    selected_port_bbox: tuple[int, int, int, int] | None = None

    # 记录部分调试信息：便于确认是否“做了端口识别”以及识别到了什么。
    debug_node_entries: list[dict] = []
    debug_log_lines: list[str] = []

    for visible_node in visible_nodes:
        node_title = str(getattr(visible_node, "name_cn", "") or "").strip()
        if not node_title:
            continue

        candidate_defs = node_defs_by_name.get(node_title, [])
        if not candidate_defs:
            if len(debug_log_lines) < 8:
                debug_log_lines.append(f"· 节点未映射到 NodeLibrary：'{node_title}'")
            continue

        raw_bbox = getattr(visible_node, "bbox", None)
        if not raw_bbox:
            continue
        node_bbox = tuple(int(v) for v in raw_bbox)
        if int(node_bbox[2]) <= 0 or int(node_bbox[3]) <= 0:
            continue

        ports_snapshot = _vision_list_ports(screenshot_before, node_bbox)
        debug_entry = None
        if len(debug_node_entries) < 5:
            debug_entry = {
                "title": node_title,
                "bbox": node_bbox,
                "ports": ports_snapshot[:8],
                "index_map": None,  # {index: (port_name, type_text, is_bool_or_enum)}
            }
            debug_node_entries.append(debug_entry)
        if len(debug_log_lines) < 20:
            ports_brief = format_candidates_brief(filter_screen_input_candidates(ports_snapshot, expected_kind=None))
            debug_log_lines.append(f"· 节点 '{node_title}'：端口识别={len(ports_snapshot)}；候选(左侧/不限kind)={ports_brief}")

        # 对同名节点定义逐个尝试，选择能在当前端口识别结果中“对齐到布尔/枚举端口 index”的那一个。
        for node_def in candidate_defs:

            input_types = dict(getattr(node_def, "input_types", {}) or {})
            input_enum_options = dict(getattr(node_def, "input_enum_options", {}) or {})
            input_names_in_order = list(getattr(node_def, "inputs", []) or [])

            bool_enum_ports_by_index: list[tuple[int, str, str, bool]] = []
            index_map: dict[int, tuple[str, str, bool]] = {}
            for input_index, port_name in enumerate(input_names_in_order):
                port_name_text = str(port_name or "").strip()
                if not port_name_text:
                    continue
                declared_type_text = str(input_types.get(port_name_text, "") or "").strip()
                declared_type_lower = declared_type_text.lower()
                options_for_port = input_enum_options.get(port_name_text)
                has_enum_options = isinstance(options_for_port, list) and int(len(options_for_port)) > 0
                is_boolean = ("布尔" in declared_type_text) or (declared_type_lower in ("bool", "boolean"))
                is_enum = ("枚举" in declared_type_text) or ("enum" in declared_type_lower) or has_enum_options
                is_bool_or_enum = bool(is_boolean or is_enum)
                index_map[int(input_index)] = (port_name_text, declared_type_text, is_bool_or_enum)
                if is_bool_or_enum:
                    bool_enum_ports_by_index.append((int(input_index), port_name_text, declared_type_text, bool(is_boolean)))

            # 把 index→端口名/类型 映射注入到 debug 入口，便于失败时叠加展示
            if debug_entry is not None and debug_entry.get("index_map") is None and index_map:
                debug_entry["index_map"] = index_map

            if not bool_enum_ports_by_index:
                if len(debug_log_lines) < 30:
                    debug_log_lines.append(f"· NodeDef '{node_title}' 未声明任何布尔/枚举输入端口")
                continue

            # 优先找布尔端口；其次枚举端口
            bool_enum_ports_by_index.sort(key=lambda item: (0 if item[3] else 1, item[1]))

            # 识别到的左侧端口：按 index 去重（优先更高置信度）
            left_ports_by_index: dict[int, object] = {}
            for port_obj in ports_snapshot:
                side_text = str(getattr(port_obj, "side", "") or "").lower()
                if side_text != "left":
                    continue
                idx_value = getattr(port_obj, "index", None)
                if idx_value is None:
                    continue
                port_index = int(idx_value)
                previous = left_ports_by_index.get(port_index)
                if previous is None:
                    left_ports_by_index[port_index] = port_obj
                    continue
                prev_conf = getattr(previous, "confidence", None)
                cur_conf = getattr(port_obj, "confidence", None)
                if isinstance(cur_conf, (int, float)) and isinstance(prev_conf, (int, float)):
                    if float(cur_conf) > float(prev_conf):
                        left_ports_by_index[port_index] = port_obj

            if len(debug_log_lines) < 30:
                bool_enum_preview = ", ".join([f"{idx}:{name}[{tp}]" for idx, name, tp, _is_bool in bool_enum_ports_by_index[:8]])
                if bool_enum_preview:
                    debug_log_lines.append(f"· NodeDef 布尔/枚举输入索引：{bool_enum_preview}")
                recognized_left_indices = sorted(left_ports_by_index.keys())
                debug_log_lines.append(f"· 识别到的左侧端口索引：{recognized_left_indices[:20]}")

            # 基于“端口识别 index”与 NodeDef.inputs 的 index 对齐来选中端口
            for input_index, port_name_text, declared_type_text, _is_boolean in bool_enum_ports_by_index:
                chosen_port_obj = left_ports_by_index.get(int(input_index))
                kind_hint = "index"
                if chosen_port_obj is None:
                    # 回退：若端口识别缺失 index 或 index 不可靠，则用“从上到下顺序”按 index 取
                    ordered_left_ports = filter_screen_input_candidates(ports_snapshot, expected_kind=None)
                    if int(input_index) < int(len(ordered_left_ports)):
                        chosen_port_obj = ordered_left_ports[int(input_index)]
                        kind_hint = "y-order"

                if chosen_port_obj is None:
                    continue

                port_center = tuple(int(v) for v in getattr(chosen_port_obj, "center", (0, 0)))
                port_bbox = tuple(int(v) for v in getattr(chosen_port_obj, "bbox", (0, 0, 0, 0)))
                if port_center == (0, 0) or int(port_bbox[2]) <= 0 or int(port_bbox[3]) <= 0:
                    continue

                # 再做一次 kind 保护：避免误挑到流程端口
                kind_text = str(getattr(chosen_port_obj, "kind", "") or "")
                if normalize_kind_text(kind_text) == "flow":
                    continue

                selected_node_title = node_title
                selected_node_bbox = node_bbox
                selected_port_name = port_name_text
                selected_declared_type = declared_type_text
                selected_port_center = (int(port_center[0]), int(port_center[1]))
                selected_port_bbox = port_bbox
                if len(debug_log_lines) < 30:
                    debug_log_lines.append(
                        f"  ✓ 选中端口 index={int(input_index)} '{port_name_text}'({declared_type_text}) via={kind_hint} center={selected_port_center}"
                    )
                break

            if selected_port_center is not None:
                break

        if selected_port_center is not None:
            break

    if (
        selected_node_title is None
        or selected_node_bbox is None
        or selected_port_name is None
        or selected_declared_type is None
        or selected_port_center is None
        or selected_port_bbox is None
    ):
        # 失败时也将端口识别结果叠加出来，避免“看起来只识别了节点”的误解。
        rects: list[dict] = []
        circles: list[dict] = []
        for entry in debug_node_entries:
            node_bbox = entry["bbox"]
            node_title = entry["title"]
            index_map = entry.get("index_map")
            rects.append(
                {
                    "bbox": node_bbox,
                    "color": (140, 160, 255),
                    "label": str(node_title),
                }
            )
            ports_preview = entry.get("ports", [])
            for port_obj in ports_preview:
                port_bbox = tuple(int(v) for v in getattr(port_obj, "bbox", (0, 0, 0, 0)))
                port_center = tuple(int(v) for v in getattr(port_obj, "center", (0, 0)))
                port_kind = str(getattr(port_obj, "kind", "") or "")
                port_side = str(getattr(port_obj, "side", "") or "")
                port_index = getattr(port_obj, "index", None)
                port_name = str(getattr(port_obj, "name_cn", "") or "")
                mapped_suffix = ""
                highlight_bool_enum = False
                if isinstance(index_map, dict) and port_index is not None:
                    mapped = index_map.get(int(port_index))
                    if isinstance(mapped, tuple) and len(mapped) == 3:
                        mapped_name, mapped_type, is_bool_enum = mapped
                        mapped_name_text = str(mapped_name or "").strip()
                        mapped_type_text = str(mapped_type or "").strip()
                        highlight_bool_enum = bool(is_bool_enum)
                        if mapped_name_text or mapped_type_text:
                            mapped_suffix = f" → {mapped_name_text}({mapped_type_text})"
                rects.append(
                    {
                        "bbox": port_bbox,
                        "color": (0, 220, 0)
                        if highlight_bool_enum
                        else ((255, 160, 80) if port_side == "right" else (0, 200, 140)),
                        "label": f"{port_side}#{'' if port_index is None else int(port_index)}[{port_kind}] {port_name or '?'}{mapped_suffix}",
                    }
                )
                circles.append(
                    {
                        "center": port_center,
                        "radius": 4,
                        "color": (255, 200, 0),
                        "label": "",
                    }
                )
        self._update_visual(
            screenshot_before,
            {
                "rects": rects,
                "circles": circles,
                "header": "布尔/枚举选项：未找到可定位的布尔/枚举端口",
            },
        )
        if debug_log_lines:
            for line in debug_log_lines[:30]:
                self._log(line)
        self._log("✗ 布尔/枚举选项测试失败：未能在当前画面定位到任何布尔/枚举端口（请先让带布尔/枚举端口的节点出现在视口中）")
        return

    port_center_x, port_center_y = selected_port_center
    click_editor_x = int(port_center_x + 50)
    click_editor_y = int(port_center_y + 25)
    click_screen_x, click_screen_y = executor.convert_editor_to_screen_coords(click_editor_x, click_editor_y)

    # 步骤1：展示端口定位结果
    self._update_visual(
        screenshot_before,
        {
            "rects": [{"bbox": selected_node_bbox, "color": (120, 200, 255), "label": str(selected_node_title)}]
            + [{"bbox": selected_port_bbox, "color": (0, 200, 140), "label": f"端口bbox {selected_port_name}"}],
            "circles": [
                {
                    "center": (int(port_center_x), int(port_center_y)),
                    "radius": 6,
                    "color": (255, 200, 0),
                    "label": f"{selected_port_name}（{selected_declared_type}）",
                },
                {
                    "center": (int(click_editor_x), int(click_editor_y)),
                    "radius": 6,
                    "color": (0, 220, 0),
                    "label": "点击点(+50,+25)",
                },
            ],
            "header": f"步骤1/识别端口：{selected_node_title}.{selected_port_name}",
        },
    )
    if debug_log_lines:
        for line in debug_log_lines[:20]:
            self._log(line)
    self._log(
        f"✓ 识别到布尔/枚举端口：{selected_node_title}.{selected_port_name} "
        f"type='{selected_declared_type}' 点击 editor=({int(click_editor_x)},{int(click_editor_y)}) "
        f"screen=({int(click_screen_x)},{int(click_screen_y)})"
    )

    # 步骤2：执行第一次点击（展开下拉）
    facade.focus_editor(window_title_text)
    _exec_utils.click_and_verify(
        executor,
        int(click_screen_x),
        int(click_screen_y),
        "[测试/布尔枚举] 点击展开下拉",
        self._log,
    )
    sleep_seconds(0.35)

    screenshot_after = facade.capture_window(window_title_text)
    if not screenshot_after:
        self._log("✗ 布尔/枚举选项测试失败：点击后截图失败")
        return

    self._update_visual(
        screenshot_after,
        {
            "rects": [{"bbox": selected_node_bbox, "color": (120, 200, 255), "label": str(selected_node_title)}],
            "circles": [{"center": (int(click_editor_x), int(click_editor_y)), "radius": 6, "color": (0, 220, 0), "label": "已点击"}],
            "header": "步骤2/已点击展开：准备扫描 D7D7D7 下拉区域",
        },
    )

    # 步骤3：颜色扫描下拉矩形（D7D7D7）
    prepared_bgr = editor_capture.prepare_color_scan_image(screenshot_after)
    found_rectangles = editor_capture.find_color_rectangles(
        screenshot_after,
        target_color_hex="D7D7D7",
        color_tolerance=18,
        near_point=(int(click_editor_x), int(click_editor_y) + 6),
        max_distance=900,
        prepared_bgr=prepared_bgr,
    )

    filtered_rectangles: list[tuple[int, int, int, int, float]] = []
    for rect_x, rect_y, rect_w, rect_h, distance in found_rectangles:
        # 下拉矩形应出现在点击点下方
        if int(rect_y) < int(click_editor_y) + 6:
            continue
        # 允许横向偏移一点（下拉可能略向左/右弹出）
        if int(click_editor_x) < int(rect_x) - 60 or int(click_editor_x) > int(rect_x + rect_w) + 60:
            continue
        filtered_rectangles.append((int(rect_x), int(rect_y), int(rect_w), int(rect_h), float(distance)))

    chosen_rectangle: tuple[int, int, int, int, float] | None = None
    if filtered_rectangles:
        chosen_rectangle = filtered_rectangles[0]
    elif found_rectangles:
        chosen_rectangle = tuple(int(v) if i < 4 else float(v) for i, v in enumerate(found_rectangles[0]))  # type: ignore[assignment]

    if chosen_rectangle is None:
        self._update_visual(
            screenshot_after,
            {
                "rects": [],
                "circles": [{"center": (int(click_editor_x), int(click_editor_y)), "radius": 6, "color": (255, 200, 0), "label": "点击点"}],
                "header": "步骤3/颜色扫描失败：未找到 D7D7D7 下拉矩形",
            },
        )
        self._log("✗ 布尔/枚举选项测试失败：未扫描到颜色为 D7D7D7 的下拉矩形")
        return

    dropdown_x, dropdown_y, dropdown_w, dropdown_h, dropdown_distance = chosen_rectangle
    overlay_rects: list[dict] = [
        {
            "bbox": (int(dropdown_x), int(dropdown_y), int(dropdown_w), int(dropdown_h)),
            "color": (0, 220, 0),
            "label": f"D7D7D7 下拉矩形 dist={round(float(dropdown_distance), 1)}",
        }
    ]
    candidate_list = filtered_rectangles[1:5] if filtered_rectangles else found_rectangles[1:5]
    for candidate in candidate_list:
        cand_x, cand_y, cand_w, cand_h, cand_dist = candidate
        overlay_rects.append(
            {
                "bbox": (int(cand_x), int(cand_y), int(cand_w), int(cand_h)),
                "color": (255, 160, 80),
                "label": f"候选 dist={round(float(cand_dist), 1)}",
            }
        )

    self._update_visual(
        screenshot_after,
        {
            "rects": overlay_rects,
            "circles": [{"center": (int(click_editor_x), int(click_editor_y)), "radius": 6, "color": (0, 220, 0), "label": "点击点"}],
            "header": "步骤3/颜色扫描：命中 D7D7D7 下拉矩形",
        },
    )
    self._log(
        f"✓ 颜色扫描命中下拉矩形：bbox=({int(dropdown_x)},{int(dropdown_y)},{int(dropdown_w)},{int(dropdown_h)}) "
        f"dist={round(float(dropdown_distance), 1)}"
    )

    # 步骤4：OCR 下拉内容（会通过全局 sink 自动在画面叠加文本框）
    with _temporary_global_sinks(self._update_visual, self._log):
        ocr_result = editor_capture.ocr_recognize_region(
            screenshot_after,
            (int(dropdown_x), int(dropdown_y), int(dropdown_w), int(dropdown_h)),
            return_details=True,
            exclude_top_pixels=0,
        )

    if isinstance(ocr_result, tuple):
        ocr_text, ocr_details = ocr_result
    else:
        ocr_text = str(ocr_result or "")
        ocr_details = []

    ocr_text_clean = str(ocr_text or "").strip()
    if ocr_text_clean:
        self._log(f"✓ 下拉选项 OCR：{ocr_text_clean}")
    else:
        self._log("✓ 下拉选项 OCR：未识别到文本（详见叠加画面）")

    if isinstance(ocr_details, list) and ocr_details:
        raw_lines = [
            str(item[1] or "").strip()
            for item in ocr_details
            if isinstance(item, (list, tuple)) and len(item) >= 2 and str(item[1] or "").strip()
        ]
        seen_lines: set[str] = set()
        unique_lines: list[str] = []
        for line in raw_lines:
            if line in seen_lines:
                continue
            seen_lines.add(line)
            unique_lines.append(line)

        if unique_lines:
            preview_lines = unique_lines[:8]
            suffix = " 等" if len(unique_lines) > len(preview_lines) else ""
            self._log(f"· OCR 行={len(unique_lines)}：{'；'.join(preview_lines)}{suffix}")


__all__ = ["test_bool_enum_options"]



