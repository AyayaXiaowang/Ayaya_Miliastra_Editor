from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_ui_action_dispatch_01"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "UI_Action",
    "parameters": [
        {
            "name": "action_key",
            "parameter_type": "字符串",
            "description": "HTML 标注的动作 ID（推荐：把关键参数编码进 key，例如 ui.select_level.1）。",
        },
        {
            "name": "action_args",
            "parameter_type": "字符串",
            "description": "动作参数原样透传（可为空；建议仅用于调试/扩展）。",
        },
        {
            "name": "ui_key",
            "parameter_type": "字符串",
            "description": "导出侧生成的 ui_key（调试/追踪用）。",
        },
        {
            "name": "widget_name",
            "parameter_type": "字符串",
            "description": "导出侧生成的控件名（调试/追踪用）。",
        },
    ],
    "description": "UI 交互动作分发信号：用于将“玩家点击某个 UI 道具展示”统一归一为 action_key/action_args，再由业务节点图决定具体行为。",
}

