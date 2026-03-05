from __future__ import annotations

import re
from pathlib import Path

from ugc_file_tools.ui.guid_resolution import UiRecordIndex as _UiRecordIndex
from ugc_file_tools.ui.guid_resolution import resolve_ui_key_guid_from_output_gil as _resolve_ui_key_guid_from_output_gil_impl

_UI_HTML_REF_RE = re.compile(
    r"""管理配置/UI源码/(?P<stem>[^`"'\n\r\\]+?)\.html""",
    flags=re.IGNORECASE,
)

_LAYOUT_INDEX_HTML_STEM_IN_DESC_RE = re.compile(
    r"""[（(](?P<stem>[^（）()]+?)\.html[)）]""",
    flags=re.IGNORECASE,
)
_LAYOUT_INDEX_UI_KEY_HINT_IN_DESC_RE = re.compile(
    r"""LAYOUT_INDEX__HTML__(?P<stem>[^\s，。,。)）]+)""",
    flags=re.IGNORECASE,
)


def _infer_layout_index_html_stem_from_graph_variable_description(description: str) -> str | None:
    """
    节点图里“布局索引”类 GraphVariables 的描述通常包含：
    - `（<stem>.html）`
    - 或显式 hint：`LAYOUT_INDEX__HTML__<stem>`
    """
    desc = str(description or "").strip()
    if desc == "":
        return None
    m = _LAYOUT_INDEX_HTML_STEM_IN_DESC_RE.search(desc)
    if m is not None:
        stem = str(m.group("stem") or "").strip()
        return stem if stem != "" else None
    m = _LAYOUT_INDEX_UI_KEY_HINT_IN_DESC_RE.search(desc)
    if m is not None:
        stem = str(m.group("stem") or "").strip()
        return stem if stem != "" else None
    return None


def _infer_primary_ui_layout_name_from_graph_code_file(graph_code_file: Path) -> str | None:
    """
    从节点图 Graph Code 的头部注释/说明中推断其“主 UI 页面名”（通常就是 HTML 文件 stem）。

    约定（示例）：
    - description: 配套 `管理配置/UI源码/第七关-结算.html` 的交互与展示写回…
    """
    head_text = Path(graph_code_file).read_text(encoding="utf-8")[:8192]
    m = _UI_HTML_REF_RE.search(head_text)
    if m is None:
        return None
    stem = str(m.group("stem") or "").strip()
    return stem if stem != "" else None


def _resolve_ui_key_guid_from_output_gil(
    *,
    ui_key: str,
    layout_name_hint: str | None,
    ui_index: _UiRecordIndex,
    root_name_cache: dict[int, str | None],
) -> int | None:
    """兼容别名：实现已收敛到 `ugc_file_tools.ui.guid_resolution`（单一真源）。"""
    return _resolve_ui_key_guid_from_output_gil_impl(
        ui_key=str(ui_key),
        layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
        ui_index=ui_index,
        root_name_cache=root_name_cache,
    )

