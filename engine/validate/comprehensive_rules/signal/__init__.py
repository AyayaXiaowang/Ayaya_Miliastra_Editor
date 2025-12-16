"""信号系统综合校验规则子包。

对外稳定入口仍为 `engine.validate.comprehensive_rules.signal_rule.SignalUsageRule`。
该子包按功能域拆分实现，便于维护、复用与缓存优化。
"""

from .usage import SignalUsageRule

__all__ = ["SignalUsageRule"]


