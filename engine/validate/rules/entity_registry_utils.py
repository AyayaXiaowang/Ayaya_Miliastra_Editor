from __future__ import annotations

"""
entity_registry_utils.py

目标：
- 为校验规则提供 `entity_key/entity:` 占位符解析工具函数。

说明：
- 校验阶段无法可靠判断“实体名是否存在于某个 .gil”（参考 GIL 由导出/写回时选择），
  因此这里只做语法解析与非空校验，不做存在性校验。
"""

from typing import Optional


def parse_entity_key_placeholder(text: str) -> Optional[str]:
    """
    解析 entity_key/entity: 占位符，返回其中的“实体名”。

    允许：
    - entity_key:某实体
    - entity:某实体
    """
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("entity_key:"):
        key = raw[len("entity_key:") :].strip()
        return key if key else None
    if lowered.startswith("entity:"):
        key = raw[len("entity:") :].strip()
        return key if key else None
    return None


__all__ = ["parse_entity_key_placeholder"]

