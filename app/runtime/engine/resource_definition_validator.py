from __future__ import annotations

from typing import Dict

from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
from engine.signal import get_default_signal_repository
from engine.struct import get_default_struct_repository

_VALIDATED: bool = False


def _format_errors(title: str, errors: Dict[str, str]) -> str:
    if not errors:
        return ""
    lines = [title]
    for key in sorted(errors.keys()):
        msg = str(errors.get(key) or "").strip() or "unknown error"
        lines.append(f"- {key}: {msg}")
    return "\n".join(lines)


def validate_runtime_definitions_or_raise() -> None:
    """运行期“代码级资源定义”校验入口（抛错即失败）。

    覆盖：
    - 结构体定义（STRUCT_PAYLOAD）
    - 信号定义（SIGNAL_PAYLOAD）
    - 关卡变量/自定义变量（LEVEL_VARIABLES）

    说明：
    - 该函数设计为“进程内只执行一次”；用于让运行时在执行节点图/加载资源前就能发现定义错误；
    - 不使用 try/except 吞错：发现问题直接抛出，保证错误不会被静默忽略。
    """
    global _VALIDATED
    if _VALIDATED:
        return

    struct_repo = get_default_struct_repository()
    signal_repo = get_default_signal_repository()

    struct_errors = struct_repo.get_errors()
    signal_errors = signal_repo.get_errors()

    # 触发关卡变量 schema 加载：加载过程中会对变量类型与 ID 默认值做强校验，失败将直接抛错。
    _ = get_default_level_variable_schema_view().get_all_variables()

    summary_parts: list[str] = []
    struct_text = _format_errors("结构体定义错误：", struct_errors)
    if struct_text:
        summary_parts.append(struct_text)
    signal_text = _format_errors("信号定义错误：", signal_errors)
    if signal_text:
        summary_parts.append(signal_text)

    if summary_parts:
        raise ValueError("运行期定义校验失败：\n" + "\n\n".join(summary_parts))

    _VALIDATED = True


__all__ = ["validate_runtime_definitions_or_raise"]


