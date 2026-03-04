from __future__ import annotations
"""
内置 UI Workbench（Web 工作台）后端工具函数。

注意：实现已下沉到 `app.runtime.services.ui_workbench.utils`，
本模块仅作为稳定导入路径的薄封装。
"""

from app.runtime.services.ui_workbench.utils import (
    crc32_hex,
    decode_utf8_b64,
    encode_utf8_b64,
    list_html_files,
    read_json,
    write_json,
)


__all__ = [
    "crc32_hex",
    "decode_utf8_b64",
    "encode_utf8_b64",
    "list_html_files",
    "read_json",
    "write_json",
]

