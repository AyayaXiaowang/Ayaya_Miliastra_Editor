from __future__ import annotations

"""类型占位（仅用于静态分析/类型检查）。

说明：
- 本文件为 **兼容旧导入路径** 保留：`engine.validate.rules.datatypes_typing`；
- 权威定义统一位于 `engine.configs.rules.datatypes_typing`，此处仅做 re-export；
- 运行时无任何行为，仅提供名称以避免“未定义类型”提示。
"""

from engine.configs.rules.datatypes_typing import *  # noqa: F401,F403

# 兼容旧别名：历史上曾使用“通用”表达未绑定类型，现统一以“泛型”为准。
通用 = 泛型  # type: ignore[name-defined]
