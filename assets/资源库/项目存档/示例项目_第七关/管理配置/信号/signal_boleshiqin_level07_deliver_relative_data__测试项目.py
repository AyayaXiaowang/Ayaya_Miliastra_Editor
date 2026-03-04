from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_deliver_relative_data__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_下发亲戚数据",
    "parameters": [
        {"name": "亲戚ID", "parameter_type": "字符串"},
        {"name": "称谓", "parameter_type": "字符串"},
        {"name": "真相为允许", "parameter_type": "布尔值"},
        {"name": "外观_身体", "parameter_type": "字符串"},
        {"name": "外观_头发", "parameter_type": "字符串"},
        {"name": "外观_胡子", "parameter_type": "字符串"},
        {"name": "外观_眼镜", "parameter_type": "字符串"},
        {"name": "外观_衣服", "parameter_type": "字符串"},
        {"name": "外观_领饰", "parameter_type": "字符串"},
        {"name": "对白列表", "parameter_type": "字符串列表"},
    ],
    "description": "第七关亲戚数据服务：收到『请求下一位亲戚』后，将本回合来访者的关键数据下发给 UI 游戏中流程（真相/外观/对白）。",
}

