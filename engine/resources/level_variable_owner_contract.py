from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.resources.level_variable_schema_types import LEVEL_VARIABLE_OWNER_VALUES


def _normalize_owner_text(value: object) -> str:
    return str(value or "").strip().lower()


def validate_and_fill_level_variable_payload_owner(payload: dict[str, Any], *, py_path: Path) -> str:
    """
    关卡变量 payload.owner 合约：
    - owner 是强语义一等字段，值域固定为 level/player/data
    - 过渡兼容：若 owner 缺失但 metadata.auto_owner 存在，则显式填充 owner
    - 一致性：owner 与 metadata.auto_owner 同时存在时必须一致，否则 fail-fast
    """
    variable_id = str(payload.get("variable_id") or "").strip()
    variable_name = str(payload.get("variable_name") or "").strip()

    meta = payload.get("metadata")
    if meta is None:
        meta = {}
        payload["metadata"] = meta
    if not isinstance(meta, dict):
        raise TypeError(
            "关卡变量 metadata 必须为 dict："
            f"variable_id={variable_id!r}, variable_name={variable_name!r}（{py_path}）"
        )

    owner = _normalize_owner_text(payload.get("owner"))
    auto_owner = _normalize_owner_text(meta.get("auto_owner"))

    if owner == "":
        if auto_owner != "":
            if auto_owner not in LEVEL_VARIABLE_OWNER_VALUES:
                raise ValueError(
                    "关卡变量 metadata.auto_owner 值域非法（仅支持 level/player/data）："
                    f"variable_id={variable_id!r}, variable_name={variable_name!r}, auto_owner={auto_owner!r}（{py_path}）"
                )
            payload["owner"] = auto_owner
            owner = auto_owner
        else:
            raise ValueError(
                "关卡变量缺少 owner（强语义字段）："
                f"variable_id={variable_id!r}, variable_name={variable_name!r}（{py_path}）。"
                "请在变量条目中补齐 owner='level'|'player'|'data'；"
                "或（仅过渡兼容）补齐 metadata.auto_owner。"
            )

    if owner not in LEVEL_VARIABLE_OWNER_VALUES:
        raise ValueError(
            "关卡变量 owner 值域非法（仅支持 level/player/data）："
            f"variable_id={variable_id!r}, variable_name={variable_name!r}, owner={owner!r}（{py_path}）"
        )

    if auto_owner != "" and auto_owner != owner:
        raise ValueError(
            "关卡变量 owner 与 metadata.auto_owner 冲突："
            f"variable_id={variable_id!r}, variable_name={variable_name!r}, owner={owner!r}, auto_owner={auto_owner!r}（{py_path}）。"
            "请统一两者（推荐以 owner 为准）。"
        )

    return owner


__all__ = ["validate_and_fill_level_variable_payload_owner"]

