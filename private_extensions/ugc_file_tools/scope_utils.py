from __future__ import annotations

"""
Scope 归一化工具（server/client）。

设计目的：
- 把“scope 文本解析”的语义收敛为单一真源，避免不同脚本/链路对非法值的处理不一致：
  - 有的默认回退 server
  - 有的直接抛错

约定：
- normalize_scope_or_raise：非空且不合法 -> 直接抛错（fail-fast）
- normalize_scope_or_default：空值 -> 回退 default；非空但不合法 -> 直接抛错（避免静默吞错）
"""

from typing import Optional


def normalize_scope_or_raise(text: str) -> str:
    t = str(text or "").strip().lower()
    if t in ("server", "s"):
        return "server"
    if t in ("client", "c"):
        return "client"
    raise ValueError(f"scope 不支持：{text!r}（可选：server/client）")


def normalize_scope_or_default(text: str, *, default_scope: str = "server") -> str:
    raw = str(text or "").strip()
    if raw == "":
        return normalize_scope_or_raise(str(default_scope))
    return normalize_scope_or_raise(raw)


def try_normalize_scope(text: str) -> Optional[str]:
    """可选：用于“探测/报告”场景的温和接口。非法值返回 None（不抛错）。"""
    t = str(text or "").strip().lower()
    if t in ("server", "s"):
        return "server"
    if t in ("client", "c"):
        return "client"
    return None

