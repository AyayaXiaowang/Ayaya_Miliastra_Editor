from __future__ import annotations

from typing import Tuple


def _parse_int_pair(text: str) -> Tuple[int, int]:
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError(f"期望格式为 'a,b'，但收到: {text!r}")
    return int(parts[0].strip()), int(parts[1].strip())


def _parse_float_pair(text: str) -> Tuple[float, float]:
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError(f"期望格式为 'a,b'，但收到: {text!r}")
    return float(parts[0].strip()), float(parts[1].strip())


