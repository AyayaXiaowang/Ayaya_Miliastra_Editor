from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_survivor_wave_start_01"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "幸存者波次_开始",
    "parameters": [],
    "description": "幸存者波次控制：用于触发新一波开始的自定义信号。通常由关卡流程/控制逻辑通过【发送信号】广播，波次控制节点图通过【监听信号】接收后启动倒计时与波次流程。",
}


