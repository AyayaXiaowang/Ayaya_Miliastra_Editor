from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_test_signal_no_params_01__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "测试信号_无参覆盖",
    "parameters": [],
    "description": "测试信号：无参数信号（仅含信号名与标准入参），用于覆盖“多信号组合/无参信号写回与校验”的回归场景。",
}

