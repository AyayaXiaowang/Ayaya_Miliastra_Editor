from __future__ import annotations

import ast
from typing import Optional, Tuple


# ============================================================================
# 语法糖 -> 节点调用：节点名与端口名映射（按 scope）
# ============================================================================

LIST_GET_ITEM_NODE_CALL_NAME = "获取列表对应值"
LIST_LENGTH_NODE_CALL_NAME = "获取列表长度"
LIST_MAX_VALUE_NODE_CALL_NAME = "获取列表最大值"
LIST_MIN_VALUE_NODE_CALL_NAME = "获取列表最小值"
TYPE_CONVERSION_NODE_CALL_NAME = "数据类型转换"
INTEGER_ROUNDING_NODE_CALL_NAME = "取整数运算"
# 注意：必须与节点定义 `plugins/nodes/server/运算节点/取整数运算.py` 的 input_enum_options 保持一致，
# 否则 validate 会报 ENUM_LITERAL_NOT_IN_OPTIONS。
ROUNDING_MODE_FLOOR = "取整逻辑_向下取整"
ROUNDING_MODE_CEIL = "取整逻辑_向上取整"
ROUNDING_MODE_ROUND = "取整逻辑_四舍五入"
DICT_GET_ITEM_NODE_CALL_NAME = "以键查询字典值"
DICT_SET_ITEM_NODE_CALL_NAME = "对字典设置或新增键值对"
DICT_DELETE_ITEM_NODE_CALL_NAME = "以键对字典移除键值对"
DICT_LENGTH_NODE_CALL_NAME = "查询字典长度"
LIST_CONTAINS_NODE_CALL_NAME = "列表是否包含该值"
DICT_CONTAINS_KEY_NODE_CALL_NAME = "查询字典是否包含特定键"

EQUAL_NODE_CALL_NAME = "是否相等"
LOGIC_AND_NODE_CALL_NAME = "逻辑与运算"
LOGIC_OR_NODE_CALL_NAME = "逻辑或运算"
LOGIC_NOT_NODE_CALL_NAME = "逻辑非运算"

ADD_NODE_CALL_NAME = "加法运算"
SUBTRACT_NODE_CALL_NAME = "减法运算"
MULTIPLY_NODE_CALL_NAME = "乘法运算"
DIVIDE_NODE_CALL_NAME = "除法运算"
ABS_NODE_CALL_NAME = "绝对值运算"

_SCOPE_SERVER = "server"
_SCOPE_CLIENT = "client"


def _normalize_scope(scope: str) -> str:
    scope_text = str(scope or "").strip().lower()
    if scope_text in {_SCOPE_SERVER, _SCOPE_CLIENT}:
        return scope_text
    return _SCOPE_SERVER


def _list_get_list_port_name(scope: str) -> str:
    # server: inputs=[("列表", ...), ("序号", ...)]
    # client: inputs=[("序号", ...), ("数据列表", ...)]
    return "数据列表" if scope == _SCOPE_CLIENT else "列表"


def _list_length_list_port_name(scope: str) -> str:
    # server: inputs=[("列表", ...)]
    # client: inputs=[("输入列表", ...)]
    return "输入列表" if scope == _SCOPE_CLIENT else "列表"


def _logic_binary_input_port_names(scope: str) -> Tuple[str, str]:
    # server: inputs=[("输入1", "布尔值"), ("输入2", "布尔值")]
    # client: inputs=[("条件1", "布尔值"), ("条件2", "布尔值")]
    return ("条件1", "条件2") if scope == _SCOPE_CLIENT else ("输入1", "输入2")


def _logic_not_input_port_name(scope: str) -> str:
    # server: inputs=[("输入", "布尔值")]
    # client: inputs=[("条件", "布尔值")]
    return "条件" if scope == _SCOPE_CLIENT else "输入"


def _numeric_compare_node_name(scope: str, op: ast.cmpop) -> Optional[str]:
    if isinstance(op, ast.Gt):
        return "是否大于" if scope == _SCOPE_CLIENT else "数值大于"
    if isinstance(op, ast.Lt):
        return "是否小于" if scope == _SCOPE_CLIENT else "数值小于"
    if isinstance(op, ast.GtE):
        return "是否大于等于" if scope == _SCOPE_CLIENT else "数值大于等于"
    if isinstance(op, ast.LtE):
        return "是否小于等于" if scope == _SCOPE_CLIENT else "数值小于等于"
    return None


def _arith_node_name(op: ast.operator) -> Optional[str]:
    if isinstance(op, ast.Add):
        return ADD_NODE_CALL_NAME
    if isinstance(op, ast.Sub):
        return SUBTRACT_NODE_CALL_NAME
    if isinstance(op, ast.Mult):
        return MULTIPLY_NODE_CALL_NAME
    if isinstance(op, ast.Div):
        return DIVIDE_NODE_CALL_NAME
    return None


