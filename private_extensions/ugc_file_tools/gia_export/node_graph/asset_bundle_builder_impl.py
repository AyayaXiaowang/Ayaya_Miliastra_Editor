from __future__ import annotations

"""
ugc_file_tools.gia_export.node_graph.asset_bundle_builder_impl

实现聚合入口（内部工程化拆分后保留该文件名，避免外部 import 路径断裂）。

对外稳定 API：
- `GiaAssetBundleGraphExportHints`
- `build_asset_bundle_message_from_graph_model_json`
- `create_gia_file_from_graph_model_json`
"""

from .asset_bundle_builder_graph_builder import (  # noqa: F401
    build_asset_bundle_message_from_graph_model_json,
    create_gia_file_from_graph_model_json,
)
from .asset_bundle_builder_types import GiaAssetBundleGraphExportHints  # noqa: F401

__all__ = [
    "GiaAssetBundleGraphExportHints",
    "build_asset_bundle_message_from_graph_model_json",
    "create_gia_file_from_graph_model_json",
]
