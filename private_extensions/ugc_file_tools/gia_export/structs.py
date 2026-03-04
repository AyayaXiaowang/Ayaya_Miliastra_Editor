from __future__ import annotations

"""
ugc_file_tools.gia_export.structs

结构体定义 `.gia`（StructureDefinition GraphUnit）导出门面。

说明：
- 实现本体位于 `ugc_file_tools.struct_def_writeback.gia_export`；
- 本模块只负责对外稳定 API（便于入口收敛与后续迁移而不影响调用方）。
"""

from ugc_file_tools.struct_def_writeback.gia_export import (  # noqa: F401
    BasicStructPyRecord,
    ExportBasicStructsGiaPlan,
    collect_basic_struct_py_records,
    export_basic_structs_to_gia,
)

__all__ = [
    "BasicStructPyRecord",
    "ExportBasicStructsGiaPlan",
    "collect_basic_struct_py_records",
    "export_basic_structs_to_gia",
]

