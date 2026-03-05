from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructImportOptions:
    mode: str  # "merge" | "overwrite"
    include_struct_ids: list[str] | None = None  # 可选：仅导入指定 STRUCT_ID（代码级结构体）

