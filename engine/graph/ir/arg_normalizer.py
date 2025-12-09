from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.port_name_rules import parse_range_definition


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
    keywords: Dict[str, ast.AST]  # {param_name: expr}
    has_variadic: bool
    variadic_placeholder: Optional[str]  # 例如 "0~99"
    created_variadic_count: int  # 归一化后的“变参位置实参”数量（仅统计位置参数）


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


def _detect_key_value_variadic_pattern(node_def: NodeDef) -> Optional[Tuple[str, str, int]]:
    """检测是否为“键/值成对”的变参节点。

    规则（保持宽松但明确）：
    - 仅考虑非流程输入端口；
    - 其中恰好存在 2 个范围定义（形如“前缀数字~数字”，且前缀非空）；
    - 这 2 个范围定义的起止数字区间一致，前缀不同，例如“键0~49”+“值0~49”；
    - 返回 (键前缀, 值前缀, 起始索引)；否则返回 None。
    """
    inputs = list(getattr(node_def, "inputs", []))
    data_inputs: List[str] = [p for p in inputs if p not in ["流程入", "流程出"]]

    range_defs: List[Tuple[str, Dict[str, int]]] = []
    for name in data_inputs:
        parsed = parse_range_definition(str(name))
        if parsed is None:
            continue
        prefix = str(parsed.get("prefix") or "")
        if prefix == "":
            continue
        range_defs.append((str(name), parsed))

    if len(range_defs) != 2:
        return None

    _, first = range_defs[0]
    _, second = range_defs[1]

    start_a = int(first.get("start", 0))
    end_a = int(first.get("end", 0))
    start_b = int(second.get("start", 0))
    end_b = int(second.get("end", 0))

    prefix_a = str(first.get("prefix") or "")
    prefix_b = str(second.get("prefix") or "")

    if prefix_a == "" or prefix_b == "":
        return None
    if prefix_a == prefix_b:
        return None
    if start_a != start_b or end_a != end_b:
        return None

    # 约定：保持 NodeDef.inputs 中出现的顺序，将第一个视为“键”前缀，第二个视为“值”前缀。
    return prefix_a, prefix_b, start_a


def normalize_call_arguments(call_node: ast.Call, node_def: NodeDef) -> NormalizedArgs:
    """统一归一化调用参数。

    规则概要：
    - 过滤保留参数（self/game/owner_entity/self.game/self.owner_entity）；
    - 非变参节点：
      · 位置参数按“非流程数据端口”的声明顺序映射到端口名；
    - 变参节点：
      · 一般变参（如【拼装列表】）：位置参数依次映射到端口名 `"0"`, `"1"`, ...；
      · 键值对变参（如【拼装字典】）：位置参数按 `(键0, 值0, 键1, 值1, ...)` 映射到端口名；
    - 关键字参数：保留原参数名；忽略以 *_callback 结尾的回调占位。
    """
    has_variadic, normal_data_params, variadic_placeholder = _analyze_node_def_inputs(node_def)

    # 尝试识别“键/值成对”的变参模式（仅在 has_variadic=True 时有意义）
    key_value_meta: Optional[Tuple[str, str, int]] = None
    if has_variadic:
        key_value_meta = _detect_key_value_variadic_pattern(node_def)

    pos_mapped: List[Tuple[str, ast.AST]] = []
    kw_mapped: Dict[str, ast.AST] = {}

    # 位置参数
    pos_index = 0
    if getattr(call_node, "args", None):
        for arg in call_node.args:
            if is_reserved_argument(arg):
                continue

            if has_variadic:
                if key_value_meta is not None:
                    key_prefix, value_prefix, start_index = key_value_meta
                    pair_offset = pos_index // 2
                    is_key_side = (pos_index % 2 == 0)
                    concrete_index = int(start_index + pair_offset)
                    dst_port = f"{key_prefix}{concrete_index}" if is_key_side else f"{value_prefix}{concrete_index}"
                else:
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

