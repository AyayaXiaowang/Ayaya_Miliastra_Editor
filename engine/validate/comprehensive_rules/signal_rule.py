from __future__ import annotations

"""信号系统综合校验规则（稳定入口）。

历史原因：外部代码可能直接 import `engine.validate.comprehensive_rules.signal_rule`。
为降低单文件体积与耦合，具体实现已拆分到 `engine.validate.comprehensive_rules.signal` 子包中，
该文件仅做 re-export，保证外部导入路径与符号名稳定。
"""

from .signal.definition_bounds import (
    MAX_SIGNAL_PARAMS,
    MAX_SIGNAL_PARAM_NAME_LENGTH,
    validate_signal_definition_bounds,
)
from .signal.usage import SignalUsageRule, validate_package_signal_usage

__all__ = [
    "SignalUsageRule",
    "validate_package_signal_usage",
    "MAX_SIGNAL_PARAMS",
    "MAX_SIGNAL_PARAM_NAME_LENGTH",
    "validate_signal_definition_bounds",
]


