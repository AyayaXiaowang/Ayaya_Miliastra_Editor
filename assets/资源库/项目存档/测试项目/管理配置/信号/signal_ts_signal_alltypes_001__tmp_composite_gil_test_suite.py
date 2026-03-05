from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_ts_signal_alltypes_001__tmp_composite_gil_test_suite"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "TS_Signal_AllTypes_001",
    "parameters": [
        {"name": "数字A", "parameter_type": "整数", "description": "测试参数：整数。"},
        {"name": "数字B", "parameter_type": "浮点数", "description": "测试参数：浮点数。"},
        {"name": "文本", "parameter_type": "字符串", "description": "测试参数：字符串。"},
        {"name": "是否启用", "parameter_type": "布尔值", "description": "测试参数：布尔值。"},
        {"name": "关联GUID", "parameter_type": "GUID", "description": "测试参数：GUID。"},
    ],
    "description": "测试集信号：覆盖整数/浮点数/字符串/布尔值/GUID 五种参数类型（用于复合内发送信号与宿主图监听回归）。",
}

