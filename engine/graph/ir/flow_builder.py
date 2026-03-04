"""IR 方法体解析入口（门面）。

为降低单文件体积，`parse_method_body` 的实现已拆分到 `flow_builder_parse.py`，
本文件仅保留稳定导入路径：
`from engine.graph.ir.flow_builder import parse_method_body`
"""

from __future__ import annotations

from .flow_builder_parse import parse_method_body

__all__ = ["parse_method_body"]

