from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_test_signal_multi_sender_01__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "测试信号_多点发送",
    "parameters": [
        {"name": "来源", "parameter_type": "字符串", "description": "发送来源标记（例如 实体创建/定时器/收到其它信号后）。"},
        {"name": "序号", "parameter_type": "整数", "description": "本次发送序号（用于区分同一图内多次发送）。"},
        {"name": "权重", "parameter_type": "浮点数", "description": "测试用权重（覆盖浮点数参数）。"},
        {"name": "开关", "parameter_type": "布尔值", "description": "测试用开关（覆盖布尔参数）。"},
        {"name": "标签列表", "parameter_type": "字符串列表", "description": "测试用标签列表（覆盖字符串列表参数）。"},
        {"name": "数值列表", "parameter_type": "整数列表", "description": "测试用数值列表（覆盖整数列表参数）。"},
    ],
    "description": "测试信号：同一个信号会在同一节点图内从多个位置发送，参数值各不相同，用于回归“多点发送 + 多类型参数”的严格校验与端口补全。",
}

