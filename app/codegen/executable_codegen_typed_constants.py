from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine.graph.common import format_constant
from engine.graph.models import GraphModel


class _ExecutableCodegenTypedConstantsMixin:
    def _reset_typed_constant_state_for_event(self) -> None:
        self._typed_const_cache = {}
        self._typed_const_counter = 0
        self._typed_const_type_by_int_value = {}

    def _infer_typed_constant_int_types_for_event(
        self,
        flow_nodes: List[str],
        graph_model: GraphModel,
        *,
        special_types: Optional[set[str]] = None,
    ) -> Dict[int, str]:
        """
        轻量预扫描：收集“某个 int 常量在至少一个明确类型端口上被使用”的信息，
        以便后续在泛型端口（如 拼装字典）也能复用同一份“类型化常量变量”。

        规则：
        - 只对 int/数字字符串 常量生效；
        - 当同一个 int 值对应多个类型（冲突）时，不做推断，避免误判。
        """
        target_types = special_types if special_types is not None else {"GUID", "配置ID", "元件ID"}

        types_by_value: Dict[int, set[str]] = {}
        for node_id in flow_nodes:
            node = graph_model.nodes.get(node_id)
            if node is None:
                continue
            node_def = self._get_node_def(node)
            if node_def is None:
                continue
            input_constants = getattr(node, "input_constants", {}) or {}
            for port in (node.inputs or []):
                port_name = str(getattr(port, "name", "") or "")
                if self._is_flow_port_name(port_name):
                    continue
                if port_name not in input_constants:
                    continue
                raw_value = input_constants.get(port_name)
                int_value = self._try_parse_int_literal(raw_value)
                if not isinstance(int_value, int):
                    continue
                expected_type = str(node_def.get_port_type(port_name, is_input=True) or "").strip()
                if expected_type not in target_types:
                    continue
                types_by_value.setdefault(int(int_value), set()).add(expected_type)

        resolved: Dict[int, str] = {}
        for int_value, type_set in types_by_value.items():
            if len(type_set) != 1:
                continue
            resolved[int(int_value)] = next(iter(type_set))
        return resolved

    def _ensure_typed_const_var(
        self,
        *,
        type_name: str,
        raw_value: object,
        var_types: Dict[str, str],
    ) -> Tuple[str, Optional[str]]:
        """
        生成并复用“类型化常量变量”：
        - const_1: "配置ID" = 1000000001
        - const_2: "GUID" = "1073742153"
        """
        normalized_type = str(type_name or "").strip()
        if normalized_type == "":
            raise ValueError("type_name is empty")

        # GUID：推荐落为“数字字符串”（便于兼容 ID 字面量校验规则与运行时常见约定）。
        literal_value: object
        if normalized_type == "GUID":
            parsed_int = self._try_parse_int_literal(raw_value)
            literal_value = str(parsed_int) if isinstance(parsed_int, int) else str(raw_value or "")
        else:
            literal_value = raw_value

        literal_expr = format_constant(literal_value)
        cache_key = (normalized_type, literal_expr)
        existing = self._typed_const_cache.get(cache_key)
        if existing is not None:
            return existing, None

        self._typed_const_counter += 1
        var_name = f"const_{self._typed_const_counter}"
        self._typed_const_cache[cache_key] = var_name
        var_types[var_name] = normalized_type
        return var_name, f'{var_name}: "{normalized_type}" = {literal_expr}'


__all__ = ["_ExecutableCodegenTypedConstantsMixin"]

