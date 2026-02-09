from __future__ import annotations

# 类型桩（stub）：为静态类型检查器与补全提供符号导出
# - 运行时不生效，仅用于编辑器智能提示与静态检查
# - 将 server 侧节点函数与占位类型透出到 `runtime.engine.graph_prelude_server`

from plugins.nodes.server import *
from engine.configs.rules.datatypes_typing import *
from engine.graph.models.package_model import GraphVariableConfig
from engine.graph.composite.pin_api import (
    流程入,
    流程入引脚,
    流程出,
    流程出引脚,
    数据入,
    数据出,
)
from .game_state import GameRuntime
from .node_graph_validator import validate_node_graph

# 注：
# - 上面的 `from plugins.nodes.server import *` 仅用于“类型层”的全量符号导出（来自 .pyi 类型桩）；
# - 实际运行时的节点函数导出由 `graph_prelude_server.py` 通过 V2 AST 清单加载实现并注入 globals() 完成。


