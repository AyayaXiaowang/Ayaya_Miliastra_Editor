from __future__ import annotations

"""
路径文本工具（统一真源）。

说明：
- 该模块只做“字符串级”的路径展示归一化，不做 IO、不做 Path 解析；
- 主要用于 UI/CLI/工具脚本中展示路径、生成稳定 key，避免在各处手写 replace("\\", "/")。
"""


def normalize_slash(text: str) -> str:
    """将路径字符串中的 Windows 分隔符 '\\\\' 归一化为 '/'。

    注意：
    - 该函数不保证路径存在，也不做 resolve；
    - 仅用于展示与稳定化处理（例如 JSON 报告、UI 列表、缓存键等）。
    """

    return str(text).replace("\\", "/")


