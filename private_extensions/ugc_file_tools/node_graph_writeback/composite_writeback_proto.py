from __future__ import annotations

from typing import Any, Dict


def resource_locator(*, origin: int, category: int, kind: int, runtime_id: int) -> Dict[str, Any]:
    # 对齐 dump-json 常见形态：guid=0 时省略 field_4。
    return {"1": int(origin), "2": int(category), "3": int(kind), "5": int(runtime_id)}


def pin_sig(*, kind_int: int, index_int: int) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"1": int(kind_int)}
    if int(index_int) != 0:
        msg["2"] = int(index_int)
    return msg


__all__ = ["resource_locator", "pin_sig"]

