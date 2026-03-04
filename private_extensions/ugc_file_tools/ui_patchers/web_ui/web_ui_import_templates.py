from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.ui_schema_library import compute_ui_record_schema_id, record_ui_schema_library_from_dll_dump
from ugc_file_tools.ui_schema_library.library import set_schema_label
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
)
from .web_ui_import_constants import UI_SCHEMA_LABEL_ITEM_DISPLAY, UI_SCHEMA_LABEL_PROGRESSBAR, UI_SCHEMA_LABEL_TEXTBOX
from .web_ui_import_item_display import (
    choose_item_display_record_template,
    try_load_item_display_record_template_from_ui_schema_library,
)
from .web_ui_import_progressbar import choose_progressbar_record_template, try_load_progressbar_record_template_from_ui_schema_library
from .web_ui_import_textbox import choose_textbox_record_template, try_load_textbox_record_template_from_ui_schema_library


@dataclass(frozen=True, slots=True)
class WebUiImportTemplates:
    progressbar_record: Optional[Dict[str, Any]]
    textbox_record: Optional[Dict[str, Any]]
    item_display_record: Optional[Dict[str, Any]]


def prepare_template_records(
    *,
    ui_record_list: List[Any],
    widgets: List[Any],
    enable_progressbars: bool,
    enable_textboxes: bool,
    progressbar_template_gil_file_path: Optional[Path],
    textbox_template_gil_file_path: Optional[Path],
    item_display_template_gil_file_path: Optional[Path],
) -> WebUiImportTemplates:
    has_any_progressbars = any(isinstance(w, dict) and str(w.get("widget_type") or "").strip() == "进度条" for w in widgets)
    has_any_textboxes = any(isinstance(w, dict) and str(w.get("widget_type") or "").strip() == "文本框" for w in widgets)
    has_any_item_displays = any(isinstance(w, dict) and str(w.get("widget_type") or "").strip() == "道具展示" for w in widgets)

    template_progressbar_record: Optional[Dict[str, Any]] = None
    if enable_progressbars and has_any_progressbars:
        template_progressbar_record = choose_progressbar_record_template(ui_record_list)
        if template_progressbar_record is None and progressbar_template_gil_file_path is not None:
            progressbar_template_path = Path(progressbar_template_gil_file_path).resolve()
            if not progressbar_template_path.is_file():
                raise FileNotFoundError(str(progressbar_template_path))
            progressbar_template_dump = _dump_gil_to_raw_json_object(progressbar_template_path)
            progressbar_template_records = _extract_ui_record_list(progressbar_template_dump)
            template_progressbar_record = choose_progressbar_record_template(progressbar_template_records)
            if template_progressbar_record is None:
                raise RuntimeError("progressbar_template_gil_file_path 未找到任何可克隆的 ProgressBar record。")

            # 一次性沉淀到 schema library：后续无需再提供模板存档
            record_ui_schema_library_from_dll_dump(
                dll_dump_object=progressbar_template_dump,
                source_gil_file_path=progressbar_template_path,
            )
            progressbar_schema_id = compute_ui_record_schema_id(template_progressbar_record)
            set_schema_label(schema_id=progressbar_schema_id, label=UI_SCHEMA_LABEL_PROGRESSBAR)

        if template_progressbar_record is None:
            template_progressbar_record = try_load_progressbar_record_template_from_ui_schema_library()
            if template_progressbar_record is None:
                raise RuntimeError(
                    "enable_progressbars=True 但输入 .gil 未包含任何可克隆的 ProgressBar；"
                    "且 ui_schema_library 未命中已标注的 ProgressBar 模板。"
                    "请先提供一次 progressbar_template_gil（或使用内置样本 seed）运行一次以沉淀模板，之后即可省略。"
                )

    template_textbox_record: Optional[Dict[str, Any]] = None
    if enable_textboxes and has_any_textboxes:
        template_textbox_record = choose_textbox_record_template(ui_record_list)
        if template_textbox_record is None and textbox_template_gil_file_path is not None:
            textbox_template_path = Path(textbox_template_gil_file_path).resolve()
            if not textbox_template_path.is_file():
                raise FileNotFoundError(str(textbox_template_path))
            textbox_template_dump = _dump_gil_to_raw_json_object(textbox_template_path)
            textbox_template_records = _extract_ui_record_list(textbox_template_dump)
            template_textbox_record = choose_textbox_record_template(textbox_template_records)
            if template_textbox_record is None:
                raise RuntimeError("textbox_template_gil_file_path 未找到任何可克隆的 TextBox record。")

            # 一次性沉淀到 schema library：后续无需再提供模板存档
            record_ui_schema_library_from_dll_dump(
                dll_dump_object=textbox_template_dump,
                source_gil_file_path=textbox_template_path,
            )
            textbox_schema_id = compute_ui_record_schema_id(template_textbox_record)
            set_schema_label(schema_id=textbox_schema_id, label=UI_SCHEMA_LABEL_TEXTBOX)

        if template_textbox_record is None:
            template_textbox_record = try_load_textbox_record_template_from_ui_schema_library()
            if template_textbox_record is None:
                raise RuntimeError(
                    "enable_textboxes=True 但输入 .gil 未包含任何可克隆的 TextBox；"
                    "且 ui_schema_library 未命中已标注的 TextBox 模板。"
                    "请先提供 --textbox-template-gil 运行一次以沉淀模板，之后即可省略该参数。"
                )

        # 保证后续 clone 时不污染 schema library 的实例（保险起见做一次深拷贝）
        template_textbox_record = copy.deepcopy(template_textbox_record)

    template_item_display_record: Optional[Dict[str, Any]] = None
    if has_any_item_displays:
        template_item_display_record = choose_item_display_record_template(ui_record_list)
        if template_item_display_record is None and item_display_template_gil_file_path is not None:
            item_display_template_path = Path(item_display_template_gil_file_path).resolve()
            if not item_display_template_path.is_file():
                raise FileNotFoundError(str(item_display_template_path))
            item_display_template_dump = _dump_gil_to_raw_json_object(item_display_template_path)
            item_display_template_records = _extract_ui_record_list(item_display_template_dump)
            template_item_display_record = choose_item_display_record_template(item_display_template_records)
            if template_item_display_record is None:
                raise RuntimeError("item_display_template_gil_file_path 未找到任何可克隆的 道具展示 record。")

            # 一次性沉淀到 schema library：后续无需再提供模板存档
            record_ui_schema_library_from_dll_dump(
                dll_dump_object=item_display_template_dump,
                source_gil_file_path=item_display_template_path,
            )
            item_display_schema_id = compute_ui_record_schema_id(template_item_display_record)
            set_schema_label(schema_id=item_display_schema_id, label=UI_SCHEMA_LABEL_ITEM_DISPLAY)

        if template_item_display_record is None:
            template_item_display_record = try_load_item_display_record_template_from_ui_schema_library()

        if template_item_display_record is not None:
            template_item_display_record = copy.deepcopy(template_item_display_record)

    if template_progressbar_record is not None:
        template_progressbar_record = copy.deepcopy(template_progressbar_record)

    return WebUiImportTemplates(
        progressbar_record=template_progressbar_record,
        textbox_record=template_textbox_record,
        item_display_record=template_item_display_record,
    )

