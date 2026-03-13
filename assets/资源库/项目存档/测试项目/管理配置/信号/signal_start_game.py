from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_start_game"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "开始游戏",
    "parameters": [
        {
            "name": "关卡序号",
            "parameter_type": "整数",
            "description": "开局关卡序号（回归夹具）：用于覆盖 event 节点映射与端口类型推断口径。",
        },
    ],
    "description": "开始游戏信号（回归夹具）：带关卡序号参数，用于 `validate-graphs` 与 event 映射回归。",
}

