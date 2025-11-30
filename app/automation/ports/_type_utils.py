# -*- coding: utf-8 -*-
"""
类型推断等通用工具（仅供 core.automation 内部使用）。
"""

from __future__ import annotations

import re


def infer_type_from_value(value_text: str) -> str:
    """基于内容推断数据类型：优先布尔/向量，再数值，最后字符串。

    返回："布尔值" | "三维向量" | "整数" | "浮点数" | "字符串"
    """
    if not isinstance(value_text, str):
        return "字符串"
    text = value_text.strip()
    lower = text.lower()
    # 布尔：中文/英文常见写法
    if text in ("是", "否") or lower in ("true", "false"):
        return "布尔值"
    # 三维向量：(x,y,z) 允许空格，小数与负号
    if re.match(r"^\(\s*[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?\s*\)$", text):
        return "三维向量"
    # 整数
    if re.match(r"^[+-]?\d+$", text):
        return "整数"
    # 浮点数（包含科学计数法/小数）
    if re.match(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$", text) and ("." in text or "e" in lower):
        return "浮点数"
    # 字符串：去掉引号也视为字符串
    return "字符串"


