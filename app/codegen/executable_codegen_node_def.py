from __future__ import annotations

import keyword
from typing import Dict, List, Optional, Tuple

from engine.graph.models import NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.port_name_rules import parse_range_definition
from engine.utils.graph.graph_utils import is_flow_port_name


class _ExecutableCodegenNodeDefMixin:
    def _get_node_def(self, node: NodeModel) -> Optional[NodeDef]:
        """按 NodeModel 尝试在节点库中解析对应 NodeDef。

        兼容带作用域后缀的键（如 `...#server/#client`）。
        """
        base_key = f"{node.category}/{node.title}"
        direct = self.node_library.get(base_key)
        if direct is not None:
            return direct
        for suffix in ("#server", "#client"):
            scoped = self.node_library.get(f"{base_key}{suffix}")
            if scoped is not None:
                return scoped
        return None

    @staticmethod
    def _is_safe_kwarg_name(name: str) -> bool:
        """判断字符串能否作为 Python 关键字参数名（不引入 dict 字面量绕路）。"""
        text = str(name or "").strip()
        return bool(text) and text.isidentifier() and (not keyword.iskeyword(text))

    @staticmethod
    def _is_flow_port_name(port_name: str) -> bool:
        return bool(is_flow_port_name(str(port_name or "")))

    @staticmethod
    def _try_parse_int_literal(value: object) -> Optional[int]:
        """尽力把 int/纯数字字符串归一化为 int；其它类型返回 None。"""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                return int(text)
        return None

    @staticmethod
    def _detect_key_value_variadic_pattern(node_def: NodeDef) -> Optional[Tuple[str, str, int]]:
        """检测是否为“键/值成对”的动态端口节点（例如：键0~49 + 值0~49）。"""
        inputs = list(getattr(node_def, "inputs", []) or [])
        data_inputs: List[str] = [str(p) for p in inputs if str(p) not in ("流程入", "流程出")]

        range_defs: List[Dict[str, int | str]] = []
        for name in data_inputs:
            parsed = parse_range_definition(str(name))
            if parsed is None:
                continue
            prefix = str(parsed.get("prefix") or "")
            if prefix == "":
                continue
            range_defs.append(dict(parsed))

        if len(range_defs) != 2:
            return None

        first = range_defs[0]
        second = range_defs[1]
        start_a = int(first.get("start", 0) or 0)
        end_a = int(first.get("end", 0) or 0)
        start_b = int(second.get("start", 0) or 0)
        end_b = int(second.get("end", 0) or 0)
        prefix_a = str(first.get("prefix") or "")
        prefix_b = str(second.get("prefix") or "")

        if prefix_a == "" or prefix_b == "" or prefix_a == prefix_b:
            return None
        if start_a != start_b or end_a != end_b:
            return None
        return prefix_a, prefix_b, start_a


__all__ = ["_ExecutableCodegenNodeDefMixin"]

