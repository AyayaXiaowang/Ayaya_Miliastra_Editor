from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_test_signal_scalar_coverage_01__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "测试信号_标量覆盖",
    "parameters": [
        {"name": "发送者GUID", "parameter_type": "GUID", "description": "触发该信号的发送者 GUID（用于覆盖 GUID 类型参数）。"},
        {"name": "整数参数", "parameter_type": "整数", "description": "测试用整数参数。"},
        {"name": "浮点参数", "parameter_type": "浮点数", "description": "测试用浮点参数。"},
        {"name": "字符串参数", "parameter_type": "字符串", "description": "测试用字符串参数。"},
        {"name": "布尔参数", "parameter_type": "布尔值", "description": "测试用布尔参数。"},
    ],
    "description": "测试信号：覆盖 GUID/整数/浮点数/字符串/布尔值 五种标量参数类型，用于节点图严格校验与端口类型补全回归。",
}

