from __future__ import annotations

import re

SERVER_SCOPE_MASK = 0x40000000
CLIENT_SCOPE_MASK = 0x40800000
SCOPE_MASK = 0xFF800000

# GraphEntry.graph_id_int（server/client）通常为 10 位十进制（包含 scope mask: 0x40000000/0x40800000）。
GRAPH_ID_INT_RE = re.compile(r"_(\d{10})(?:__|$)")

# 扫描 Graph Code 文件头部（docstring metadata）用：避免把 `_prelude.py` 等辅助脚本当作节点图。
SCAN_HEAD_CHARS = 8192
GRAPH_ID_LINE_RE = re.compile(r"(?m)^\s*graph_id\s*:\s*(\S+)\s*$")
GRAPH_NAME_LINE_RE = re.compile(r"(?m)^\s*graph_name\s*:\s*(.+?)\s*$")
GRAPH_TYPE_LINE_RE = re.compile(r"(?m)^\s*graph_type\s*:\s*(\S+)\s*$")

UI_SOURCE_HTML_HINT_RE = re.compile(r"管理配置[\\/]+UI源码[\\/]+([^\\/`\"']+?)\.html")
UI_KEY_PLACEHOLDER_RE = re.compile(r"(?:ui_key:|ui:)(?P<key>[^\s\"']+)")

