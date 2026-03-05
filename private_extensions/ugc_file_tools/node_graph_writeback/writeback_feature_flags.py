from __future__ import annotations

import os
from typing import Iterable, Set


def _split_csv(text: str) -> list[str]:
    raw = str(text or "")
    parts: list[str] = []
    for token in raw.replace(";", ",").replace("|", ",").split(","):
        t = str(token).strip()
        if t != "":
            parts.append(t)
    return parts


def get_disabled_writeback_features() -> Set[str]:
    """
    写回实验开关（用于二分定位“哪一处补丁导致真源可识别”）：

    - 默认：全开（返回空集合）。
    - 通过环境变量禁用：UGC_WB_DISABLE="flag1,flag2"。
    - 特例：UGC_WB_DISABLE="all" 表示禁用所有已接入开关的补丁点（只影响接入了 is_writeback_feature_enabled 的代码）。
    """
    raw = os.environ.get("UGC_WB_DISABLE", "")
    disabled = {str(x) for x in _split_csv(raw)}
    lowered = {str(x).casefold() for x in disabled}
    if "all" in lowered or "*" in lowered:
        return {"all"}
    return disabled


def is_writeback_feature_enabled(name: str) -> bool:
    """
    返回某个写回补丁点是否启用。

    约定：
    - 默认启用（用于保持当前修复版行为不变）。
    - 当 UGC_WB_DISABLE 包含该 name，或包含 all/*，则禁用。
    """
    n = str(name or "").strip()
    if n == "":
        raise ValueError("feature name 不能为空")
    disabled = get_disabled_writeback_features()
    if "all" in {str(x).casefold() for x in disabled}:
        return False
    return n not in disabled


def format_disabled_features(features: Iterable[str]) -> str:
    items = [str(x).strip() for x in (features or []) if str(x).strip() != ""]
    return ",".join(items)

