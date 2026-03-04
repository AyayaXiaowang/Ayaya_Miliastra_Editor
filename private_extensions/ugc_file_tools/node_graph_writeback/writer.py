from __future__ import annotations

"""
writer.py

对外稳定入口（薄 wrapper）：
- 保持 `write_graph_model_to_gil` 与 `run_precheck_and_write_and_postcheck` 的导入路径不变；
- 核心实现拆分至 `pipeline.py` 与各职责模块（见本目录 claude.md）。
"""

from .pipeline import (
    run_precheck_and_write_and_postcheck,
    run_write_and_postcheck_pure_json,
    write_graph_model_to_gil,
    write_graph_model_to_gil_pure_json,
)

__all__ = [
    "write_graph_model_to_gil",
    "write_graph_model_to_gil_pure_json",
    "run_precheck_and_write_and_postcheck",
    "run_write_and_postcheck_pure_json",
]


