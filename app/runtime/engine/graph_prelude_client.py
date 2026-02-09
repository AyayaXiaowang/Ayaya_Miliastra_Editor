from __future__ import annotations

# Client 侧节点图最小导入预设：
# - 暴露 GameRuntime（如需在类型注解中使用）
# - 通过 V2 AST 清单加载并导出所有 client 侧节点实现（执行/查询/运算/流程/事件）
# - 导入“占位类型”以消除类型检查器对中文类型名的未定义提示

from .game_state import GameRuntime
from .node_impl_loader import load_node_exports_for_scope
from .resource_definition_validator import validate_runtime_definitions_or_raise
from engine.graph.models.package_model import GraphVariableConfig  # noqa: F401
from engine.configs.rules.datatypes_typing import *  # noqa: F401,F403
from engine.graph.composite.pin_api import (  # noqa: F401,F403
    流程入,
    流程入引脚,
    流程出,
    流程出引脚,
    数据入,
    数据出,
)
from .node_graph_validator import validate_node_graph  # noqa: F401

# 运行期定义资源（结构体/信号/关卡变量）强校验：一旦有错误直接抛出，避免运行期潜伏。
validate_runtime_definitions_or_raise()

# 注入所有 client 节点实现（保持 Graph Code 直接调用“节点函数名(...)”的写法）
globals().update(load_node_exports_for_scope("client"))

