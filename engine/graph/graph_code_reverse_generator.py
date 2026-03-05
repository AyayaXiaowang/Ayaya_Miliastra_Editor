from __future__ import annotations

"""
兼容入口：历史上 Reverse Graph Code Generator 的实现位于本文件。

当前实现已迁移到 `engine.graph.reverse_codegen` 子包；本文件仅做 re-export，
以避免外部工具链/脚本依赖 `engine.graph.graph_code_reverse_generator` 导入路径而破坏。
"""

from engine.graph.reverse_codegen import (  # noqa: F401
    ReverseGraphCodeError,
    ReverseGraphCodeOptions,
    build_semantic_signature,
    diff_semantic_signature,
    generate_graph_code_from_model,
)

__all__ = [
    "ReverseGraphCodeError",
    "ReverseGraphCodeOptions",
    "generate_graph_code_from_model",
    "build_semantic_signature",
    "diff_semantic_signature",
]

