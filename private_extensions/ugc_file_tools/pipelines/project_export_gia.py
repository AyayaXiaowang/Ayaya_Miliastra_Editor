from __future__ import annotations

"""
Compatibility shim.

Historically the full export-to-GIA implementation lived in this single module.
It has been split into focused modules under `ugc_file_tools.pipelines.project_export_gia_parts`
to reduce complexity while keeping the public import path stable.
"""

from ugc_file_tools.pipelines.project_export_gia_parts.pipeline import run_project_export_to_gia
from ugc_file_tools.pipelines.project_export_gia_parts.signals_collect import collect_used_signal_specs_from_graph_payload
from ugc_file_tools.pipelines.project_export_gia_parts.types import ProgressCallback, ProjectExportGiaPlan

# Backwards compat: keep the old underscored symbol name importable from this stable shim,
# but do not import underscored names across modules.
_collect_used_signal_specs_from_graph_payload = collect_used_signal_specs_from_graph_payload

__all__ = [
    "ProgressCallback",
    "ProjectExportGiaPlan",
    "run_project_export_to_gia",
    "collect_used_signal_specs_from_graph_payload",
    "_collect_used_signal_specs_from_graph_payload",
]

