from __future__ import annotations

"""
section15_exporter.py

薄入口：保持对外 import 路径稳定。
核心实现已拆分至 `ugc_file_tools/gil_package_exporter/section15/`。
"""

from .section15.exporter import _export_section15_resources_from_pyugc_dump

__all__ = ["_export_section15_resources_from_pyugc_dump"]


