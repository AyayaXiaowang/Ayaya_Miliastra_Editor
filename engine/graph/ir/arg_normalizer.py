from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from engine.nodes.node_definition_loader import NodeDef


RESERVED_PARAM_NAMES = {"self", "game", "owner_entity"}
RESERVED_SELF_ATTRS = {"game", "owner_entity"}


def is_reserved_argument(expr: ast.AST) -> bool:
    """判断参数表达式是否为保留参数：self / game / owner_entity / self.game / self.owner_entity。"""
    if isinstance(expr, ast.Name) and expr.id in RESERVED_PARAM_NAMES:
        return True
    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name) and expr.value.id == "self" and expr.attr in RESERVED_SELF_ATTRS:
            return True
    return False


@dataclass
class NormalizedArgs:
    """归一化后的调用实参信息。"""
    positional: List[Tuple[str, ast.AST]]  # [(dst_port_name, expr)]
    keywords: Dict[str, ast.AST]           # {param_name: expr}
    has_variadic: bool
    variadic_placeholder: Optional[str]    # 例如 "0~99"
    created_variadic_count: int            # 归一化后的数字端口数量（仅统计位置参数）


def _analyze_node_def_inputs(node_def: NodeDef) -> Tuple[bool, List[str], Optional[str]]:
    """分析节点定义的输入端口，返回 (是否变参, 普通数据端口列表, 变参占位端口名或None)。"""
    inputs = list(getattr(node_def, "inputs", []))
    data_inputs: List[str] = [p for p in inputs if p not in ["流程入", "流程出"]]
    variadic_placeholder: Optional[str] = next((p for p in data_inputs if "~" in p), None)
    has_variadic = variadic_placeholder is not None
    if has_variadic:
        # 非占位的普通数据端口
        normal_data = [p for p in data_inputs if p != variadic_placeholder]
        return True, normal_data, variadic_placeholder
    return False, data_inputs, None


def normalize_call_arguments(call_node: ast.Call, node_def: NodeDef) -> NormalizedArgs:
    """统一归一化调用参数：
    - 过滤保留参数（self/game/owner_entity/self.game/self.owner_entity）
    - 位置参数：若为变参节点，则映射到数字端口"0","1"...；否则按定义中的数据端口顺序映射
    - 关键字参数：保留原名；忽略 *_callback 形式的回调占位
    返回归一化的端口与表达式映射，供节点工厂/连线路由/解析器复用。
    """
    has_variadic, normal_data_params, variadic_placeholder = _analyze_node_def_inputs(node_def)

    pos_mapped: List[Tuple[str, ast.AST]] = []
    kw_mapped: Dict[str, ast.AST] = {}

    # 位置参数
    pos_index = 0
    if getattr(call_node, "args", None):
        for arg in call_node.args:
            if is_reserved_argument(arg):
                continue
            if has_variadic:
                dst_port = str(pos_index)
            else:
                if pos_index >= len(normal_data_params):
                    # 超出定义的参数数量，忽略
                    pos_index += 1
                    continue
                dst_port = normal_data_params[pos_index]
            pos_mapped.append((dst_port, arg))
            pos_index += 1

    # 关键字参数
    for keyword in getattr(call_node, "keywords", []):
        name = keyword.arg
        if not name:
            continue
        if name.endswith("_callback"):
            continue
        kw_mapped[name] = keyword.value

    return NormalizedArgs(
        positional=pos_mapped,
        keywords=kw_mapped,
        has_variadic=has_variadic,
        variadic_placeholder=variadic_placeholder,
        created_variadic_count=len(pos_mapped) if has_variadic else 0,
    )



