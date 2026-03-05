from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_deliver_mom_notes__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_下发本局纸条",
    "parameters": [
        {"name": "线索标题", "parameter_type": "字符串"},
        {"name": "线索标签列表", "parameter_type": "字符串列表"},
        {"name": "线索文本列表", "parameter_type": "字符串列表"},
    ],
    "description": "第七关亲戚数据服务：在开局选定本局 round 后，下发『妈妈的纸条』线索面板所需的标题、标签与文本列表。",
}

