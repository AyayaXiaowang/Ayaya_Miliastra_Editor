from __future__ import annotations

from pathlib import Path
from typing import Mapping

STRUCT_TYPE_BASIC: str = "basic"
STRUCT_TYPE_INGAME_SAVE: str = "ingame_save"


def infer_expected_struct_type_from_source_path(source_path: Path) -> str:
    """根据结构体定义文件的物理目录推断其期望 struct_type。

    约定（目录即分类）：
    - `.../管理配置/结构体定义/基础结构体/**.py` -> basic
    - `.../管理配置/结构体定义/局内存档结构体/**.py` -> ingame_save

    说明：
    - 仅对上述两个“规范目录”做强约束，其它目录返回空字符串表示“不强制”。
    """
    text = str(source_path.as_posix())
    if "/管理配置/结构体定义/局内存档结构体/" in text:
        return STRUCT_TYPE_INGAME_SAVE
    if "/管理配置/结构体定义/基础结构体/" in text:
        return STRUCT_TYPE_BASIC
    return ""


def infer_struct_type_from_payload(payload: Mapping[str, object]) -> str:
    """从结构体 payload 中读取 struct_type（兼容 struct_ype/struct_type 两种字段）。"""
    raw_value = payload.get("struct_ype")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    raw_struct_type = payload.get("struct_type")
    if isinstance(raw_struct_type, str) and raw_struct_type.strip():
        return raw_struct_type.strip()
    return ""

