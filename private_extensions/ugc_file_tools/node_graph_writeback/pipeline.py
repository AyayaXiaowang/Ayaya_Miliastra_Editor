from __future__ import annotations

"""
node_graph_writeback.pipeline

对外稳定导入路径（薄转发）：
- 真实实现位于 `node_graph_writeback/pipeline_parts/pipeline.py`
- 该文件仅负责 re-export，避免上层工具/测试依赖路径漂移。
"""

from .pipeline_parts.pipeline import (
    _try_load_ui_key_to_guid_registry_for_graph_model,
    run_precheck_and_write_and_postcheck,
    run_write_and_postcheck_pure_json,
    write_graph_model_to_gil,
    write_graph_model_to_gil_pure_json,
)

# Backwards/Tests helpers: keep these internal utilities importable from the stable facade.
from .pipeline_parts.pipeline_signals import _extract_signal_node_def_id_maps_from_payload_root
from .pipeline_parts.pipeline_ui_keys import _classify_missing_ui_keys_with_optional_hidden_semantics
from .pipeline_parts.pipeline_ui_keys import maybe_sync_ui_key_guid_registry_with_base_ui_records

__all__ = [
    "_extract_signal_node_def_id_maps_from_payload_root",
    "_classify_missing_ui_keys_with_optional_hidden_semantics",
    "_try_load_ui_key_to_guid_registry_for_graph_model",
    "maybe_sync_ui_key_guid_registry_with_base_ui_records",
    "write_graph_model_to_gil",
    "write_graph_model_to_gil_pure_json",
    "run_precheck_and_write_and_postcheck",
    "run_write_and_postcheck_pure_json",
]

