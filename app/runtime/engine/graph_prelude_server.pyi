from __future__ import annotations

# 类型桩（stub）：为静态类型检查器与补全提供符号导出
# - 运行时不生效，仅用于编辑器智能提示与静态检查
# - 将 server 侧节点函数与占位类型透出到 `runtime.engine.graph_prelude_server`

from plugins.nodes.server import *
from engine.configs.rules.datatypes_typing import *
from engine.graph.composite.pin_api import (
    流程入,
    流程入引脚,
    流程出,
    流程出引脚,
    数据入,
    数据出,
)
from .game_state import GameRuntime

# 注：上面的 `from plugins.nodes.server import *` 会把所有节点函数的类型桩透出到当前模块，
# 与实际运行时的 `graph_prelude_server.py` 行为保持一致，从而避免“函数名标黄”等提示。


