"""兼容层：ugc_file_tools.graph_codegen.executable_code_generator

历史上 `ugc_file_tools` 曾维护过一份 `ExecutableCodeGenerator` 的增强分叉版，
导致 GraphModel → Graph Code 的生成口径在多处漂移。

当前唯一真源为 `app.codegen.executable_code_generator`；本模块仅保留薄转发以兼容旧导入路径。
"""

from __future__ import annotations

from app.codegen.executable_code_generator import ExecutableCodeGenerator, ExecutableCodegenOptions

__all__ = [
    "ExecutableCodeGenerator",
    "ExecutableCodegenOptions",
]

