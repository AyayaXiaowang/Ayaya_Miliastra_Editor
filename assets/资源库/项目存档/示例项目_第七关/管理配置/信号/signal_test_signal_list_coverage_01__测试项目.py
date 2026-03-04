from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_test_signal_list_coverage_01__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "测试信号_列表覆盖",
    "parameters": [
        {"name": "标签列表", "parameter_type": "字符串列表", "description": "测试用标签列表（覆盖字符串列表类型）。"},
        {"name": "数值列表", "parameter_type": "整数列表", "description": "测试用数值列表（覆盖整数列表类型）。"},
        {"name": "开关", "parameter_type": "布尔值", "description": "示例开关（用于与列表参数混用覆盖）。"},
    ],
    "description": "测试信号：覆盖列表型参数（字符串列表/整数列表）与布尔值混合，用于端口类型推断与写回回归。",
}

