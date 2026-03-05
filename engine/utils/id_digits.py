from __future__ import annotations

import re
from typing import Final

_DIGITS_1_TO_10_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{1,10}$")


def is_digits_1_to_10(value: object) -> bool:
    """是否为“1~10 位纯数字”。

    支持：
    - int：范围 [0, 9_999_999_999]
    - str：1~10 位 ASCII 数字（允许前导 0）

    注意：
    - bool 是 int 的子类，这里显式排除，避免 True/False 被当作数字 ID。
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 9_999_999_999
    if isinstance(value, str):
        return _DIGITS_1_TO_10_PATTERN.fullmatch(value) is not None
    return False


__all__ = ["is_digits_1_to_10"]


