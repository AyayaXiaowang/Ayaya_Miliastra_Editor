from __future__ import annotations

"""
文本相似度与中文近似匹配工具。

提供通用的 Levenshtein 距离计算与基于中文提取的近似匹配判断，
用于 OCR 标题与端口名近似匹配、运行时节点/端口容错选择等场景。

注意：不使用第三方库，保证在无额外依赖下可用。
"""

from typing import Optional
import re


def levenshtein_distance(text_a: str, text_b: str) -> int:
    """计算 Levenshtein 编辑距离。

    Args:
        text_a: 文本A
        text_b: 文本B

    Returns:
        最小编辑步数（插入/删除/替换均计 1）
    """
    len_a = len(text_a)
    len_b = len(text_b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a
    dp = [[0] * (len_b + 1) for _ in range(len_a + 1)]
    for i in range(len_a + 1):
        dp[i][0] = i
    for j in range(len_b + 1):
        dp[0][j] = j
    for i in range(1, len_a + 1):
        char_a = text_a[i - 1]
        for j in range(1, len_b + 1):
            char_b = text_b[j - 1]
            replace_cost = 0 if char_a == char_b else 1
            delete_cost = dp[i - 1][j] + 1
            insert_cost = dp[i][j - 1] + 1
            substitute_cost = dp[i - 1][j - 1] + replace_cost
            best_cost = delete_cost if delete_cost < insert_cost else insert_cost
            if substitute_cost < best_cost:
                best_cost = substitute_cost
            dp[i][j] = best_cost
    return dp[len_a][len_b]


def chinese_similar(text_a: str, text_b: str, max_distance: int = 2) -> bool:
    """基于中文内容的近似匹配。

    - 仅取字符串中的中文部分进行比对；
    - 若相等或包含直接判真；
    - 否则比较编辑距离，允许不超过阈值（默认2）。
    """
    chinese_a = "".join(re.findall(r"[\u4e00-\u9fff]+", text_a)) if isinstance(text_a, str) else ""
    chinese_b = "".join(re.findall(r"[\u4e00-\u9fff]+", text_b)) if isinstance(text_b, str) else ""
    if chinese_a == "" or chinese_b == "":
        return False
    if chinese_a == chinese_b or chinese_a in chinese_b or chinese_b in chinese_a:
        return True
    return int(levenshtein_distance(chinese_a, chinese_b)) <= int(max_distance)


__all__ = [
    "levenshtein_distance",
    "chinese_similar",
]



