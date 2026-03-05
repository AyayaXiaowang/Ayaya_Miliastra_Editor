from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ugc_file_tools.ui_schema_library import compute_ui_record_schema_id, record_ui_schema_library_from_dll_dump
from ugc_file_tools.ui_schema_library.library import set_schema_label
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list
from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

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


BUILTIN_UI_TEMPLATE_DIR_NAME = "空的界面控件组"
BUILTIN_PROGRESSBAR_TEMPLATE_FILE_NAME = "进度条样式.gil"
BUILTIN_TEXTBOX_TEMPLATE_FILE_NAME = "文本框样式.gil"
BUILTIN_ITEM_DISPLAY_TEMPLATE_FILE_NAME = "道具展示.gil"


@dataclass(frozen=True, slots=True)
class WebUiImportTemplates:
    progressbar_record: Optional[Dict[str, Any]]
    textbox_record: Optional[Dict[str, Any]]
    item_display_record: Optional[Dict[str, Any]]


def _resolve_builtin_ui_template_gil_or_raise(*, template_file_name: str) -> Path:
    template_path = (ugc_file_tools_builtin_resources_root() / BUILTIN_UI_TEMPLATE_DIR_NAME / str(template_file_name)).resolve()
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))
    return template_path


def _load_template_record_from_gil_and_record_schema(
    *,
    template_gil_file_path: Path,
    choose_template_record: Callable[[List[Any]], Optional[Dict[str, Any]]],
    schema_label: str,
    template_missing_error_message: str,
) -> Dict[str, Any]:
    template_path = Path(template_gil_file_path).resolve()
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))
    template_dump = _dump_gil_to_raw_json_object(template_path)
    template_records = _extract_ui_record_list(template_dump)
    template_record = choose_template_record(template_records)
    if template_record is None:
        raise RuntimeError(str(template_missing_error_message))

    # 一次性沉淀到 schema library：后续无需再提供模板存档
    record_ui_schema_library_from_dll_dump(
        dll_dump_object=template_dump,
        source_gil_file_path=template_path,
    )
    template_schema_id = compute_ui_record_schema_id(template_record)
    set_schema_label(schema_id=template_schema_id, label=str(schema_label))
    return template_record


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
            template_progressbar_record = _load_template_record_from_gil_and_record_schema(
                template_gil_file_path=Path(progressbar_template_gil_file_path).resolve(),
                choose_template_record=choose_progressbar_record_template,
                schema_label=UI_SCHEMA_LABEL_PROGRESSBAR,
                template_missing_error_message="progressbar_template_gil_file_path 未找到任何可克隆的 ProgressBar record。",
            )

        if template_progressbar_record is None:
            template_progressbar_record = try_load_progressbar_record_template_from_ui_schema_library()

        if template_progressbar_record is None:
            builtin_progressbar_template_gil_file_path = _resolve_builtin_ui_template_gil_or_raise(
                template_file_name=BUILTIN_PROGRESSBAR_TEMPLATE_FILE_NAME
            )
            template_progressbar_record = _load_template_record_from_gil_and_record_schema(
                template_gil_file_path=builtin_progressbar_template_gil_file_path,
                choose_template_record=choose_progressbar_record_template,
                schema_label=UI_SCHEMA_LABEL_PROGRESSBAR,
                template_missing_error_message="内置进度条样本 seed 未找到任何可克隆的 ProgressBar record。",
            )

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
            template_textbox_record = _load_template_record_from_gil_and_record_schema(
                template_gil_file_path=Path(textbox_template_gil_file_path).resolve(),
                choose_template_record=choose_textbox_record_template,
                schema_label=UI_SCHEMA_LABEL_TEXTBOX,
                template_missing_error_message="textbox_template_gil_file_path 未找到任何可克隆的 TextBox record。",
            )

        if template_textbox_record is None:
            template_textbox_record = try_load_textbox_record_template_from_ui_schema_library()

        if template_textbox_record is None:
            builtin_textbox_template_gil_file_path = _resolve_builtin_ui_template_gil_or_raise(
                template_file_name=BUILTIN_TEXTBOX_TEMPLATE_FILE_NAME
            )
            template_textbox_record = _load_template_record_from_gil_and_record_schema(
                template_gil_file_path=builtin_textbox_template_gil_file_path,
                choose_template_record=choose_textbox_record_template,
                schema_label=UI_SCHEMA_LABEL_TEXTBOX,
                template_missing_error_message="内置文本框样本 seed 未找到任何可克隆的 TextBox record。",
            )

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
            template_item_display_record = _load_template_record_from_gil_and_record_schema(
                template_gil_file_path=Path(item_display_template_gil_file_path).resolve(),
                choose_template_record=choose_item_display_record_template,
                schema_label=UI_SCHEMA_LABEL_ITEM_DISPLAY,
                template_missing_error_message="item_display_template_gil_file_path 未找到任何可克隆的 道具展示 record。",
            )

        if template_item_display_record is None:
            template_item_display_record = try_load_item_display_record_template_from_ui_schema_library()

        if template_item_display_record is None:
            builtin_item_display_template_gil_file_path = _resolve_builtin_ui_template_gil_or_raise(
                template_file_name=BUILTIN_ITEM_DISPLAY_TEMPLATE_FILE_NAME
            )
            template_item_display_record = _load_template_record_from_gil_and_record_schema(
                template_gil_file_path=builtin_item_display_template_gil_file_path,
                choose_template_record=choose_item_display_record_template,
                schema_label=UI_SCHEMA_LABEL_ITEM_DISPLAY,
                template_missing_error_message="内置道具展示样本 seed 未找到任何可克隆的 道具展示 record。",
            )

        if template_item_display_record is not None:
            template_item_display_record = copy.deepcopy(template_item_display_record)

    if template_progressbar_record is not None:
        template_progressbar_record = copy.deepcopy(template_progressbar_record)

    return WebUiImportTemplates(
        progressbar_record=template_progressbar_record,
        textbox_record=template_textbox_record,
        item_display_record=template_item_display_record,
    )

