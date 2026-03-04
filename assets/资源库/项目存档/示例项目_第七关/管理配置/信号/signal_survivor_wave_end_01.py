from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_survivor_wave_end_01"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "幸存者波次_结束",
    "parameters": [
        {
            "name": "当前波次",
            "parameter_type": "整数",
            "description": "已结束的波次编号（从 1 开始递增）。",
        },
    ],
    "description": "幸存者波次控制：当一波倒计时结束时广播该信号，供关卡内其他节点图（刷怪、结算、提示等）按需监听并处理波次结束逻辑。",
}


