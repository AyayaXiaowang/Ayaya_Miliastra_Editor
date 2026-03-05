from __future__ import annotations

"""
ugc_file_tools.gia_export.wire_patch

`.gia` 的 wire-level 保真补丁门面（尽量不改变未知字段与字节结构，仅对少量字段做补丁）。

说明：
- 具体实现位于 `ugc_file_tools.gia.wire_patch`；
- 本模块只负责对外稳定 API（便于入口收敛与后续迁移而不影响调用方）。
"""

from ugc_file_tools.gia.wire_patch import (  # noqa: F401
    WireChunk,
    patch_gia_file_path_wire,
)

__all__ = [
    "WireChunk",
    "patch_gia_file_path_wire",
]

