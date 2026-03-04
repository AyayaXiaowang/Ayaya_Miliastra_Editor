from __future__ import annotations

"""
ugc_file_tools.gia_export.decorations

实体/装饰物/资产包类 `.gia` 导出门面。

说明：
- 本项目中“装饰物/实体/资产包”并非单一 `.gia` 语义，不同类型/真源模板可能要求不同策略；
- 本模块只负责对外稳定 API（薄转发），并明确区分 wire-level 保真补丁与语义重编码两类路径；
- 具体实现仍位于对应模块（保持最小 diff，降低回归风险）。
"""

from ugc_file_tools.gia.asset_bundle_decorations import (  # noqa: F401
    build_asset_bundle_decorations_gia,
)
from ugc_file_tools.gia.decorations_bundle import (  # noqa: F401
    DecorationItem,
    build_decorations_bundle_gia,
    load_decorations_report,
)
from ugc_file_tools.gia.decorations_variants import (  # noqa: F401
    export_gia_decorations_variants,
)
from ugc_file_tools.gia.entity_decorations_writer import (  # noqa: F401
    build_entity_gia_with_decorations_wire,
)
from ugc_file_tools.gia.wire_decorations_bundle import (  # noqa: F401
    build_entity_decorations_bundle_wire,
)
from ugc_file_tools.gia.wire_decorations_transform import (  # noqa: F401
    merge_and_center_decorations_gia_wire,
)

__all__ = [
    # helpers
    "DecorationItem",
    "load_decorations_report",
    # semantic encode / template-based rebuild
    "build_decorations_bundle_gia",
    "build_asset_bundle_decorations_gia",
    # wire-level faithful patch / clone
    "build_entity_decorations_bundle_wire",
    "build_entity_gia_with_decorations_wire",
    "merge_and_center_decorations_gia_wire",
    # experiment variants
    "export_gia_decorations_variants",
]

