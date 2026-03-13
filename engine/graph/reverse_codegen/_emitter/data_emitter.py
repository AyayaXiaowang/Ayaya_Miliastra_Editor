from __future__ import annotations

import keyword
from typing import Dict, List, Mapping, Sequence, Tuple

from engine.graph.common import format_constant
from engine.graph.models import NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.name_utils import make_valid_identifier

from engine.graph.reverse_codegen._common import (
    ReverseGraphCodeError,
    _resolve_node_def,
)
from engine.graph.reverse_codegen._emitter.call_args import _render_node_call_args
from engine.graph.reverse_codegen._emitter.constants import (
    _ARITHMETIC_OPERATOR_BY_TITLE,
    _NUMERIC_TYPES,
)
from engine.graph.reverse_codegen._emitter.naming import (
    _finalize_output_var_names,
    _pick_call_name_for_node,
)


class _StructuredEventEmitterDataEmitter:
    """提供数据节点发射、表达式解析与赋值语句渲染能力。"""

    def _collect_direct_data_sources_into_nodes(self, nodes: set[str]) -> set[str]:
        """返回直接连到这些节点任一数据输入端口的来源节点集合。"""
        result: set[str] = set()
        for dst_id in nodes:
            dst_node = self.model.nodes.get(dst_id)  # type: ignore[attr-defined]
            if dst_node is None:
                continue
            for port in (dst_node.inputs or []):
                pname = str(getattr(port, "name", "") or "")
                if not pname:
                    continue
                if self._is_flow_port(dst_node, pname, False):  # type: ignore[attr-defined]
                    continue
                source = self.data_in_edge.get((dst_id, pname))  # type: ignore[attr-defined]
                if source is None:
                    continue
                result.add(source[0])
        return result

    def _can_emit_data_node_without_unbound_flow_sources(
        self,
        *,
        node_id: str,
        var_mapping: Mapping[Tuple[str, str], str],
        visiting: set[str],
    ) -> bool:
        """判断纯数据节点能否在当前作用域被提前发出而不依赖流程节点输出。"""
        nid = str(node_id or "")
        if not nid:
            return False
        if nid in visiting:
            return True
        visiting.add(nid)

        node = self.model.nodes.get(nid)  # type: ignore[attr-defined]
        if node is None:
            return False
        if self._node_has_any_flow_port(node):  # type: ignore[attr-defined]
            return False

        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname:
                continue
            if self._is_flow_port(node, pname, False):  # type: ignore[attr-defined]
                continue
            source = self.data_in_edge.get((nid, pname))  # type: ignore[attr-defined]
            if source is None:
                continue
            src_node_id, src_port = source
            src_key = (str(src_node_id), str(src_port))
            if src_key in var_mapping:
                continue
            src_node = self.model.nodes.get(src_key[0])  # type: ignore[attr-defined]
            if src_node is None:
                return False
            if self._node_has_any_flow_port(src_node):  # type: ignore[attr-defined]
                return False
            if not self._can_emit_data_node_without_unbound_flow_sources(
                node_id=src_key[0],
                var_mapping=var_mapping,
                visiting=visiting,
            ):
                return False

        return True

    def _ensure_data_node_emitted(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        """确保纯数据节点已被发出并在不合法时 fail-fast。"""
        if node_id in self.emitted_nodes:  # type: ignore[attr-defined]
            return
        node = self.model.nodes.get(node_id)  # type: ignore[attr-defined]
        if node is None:
            return

        if self._node_has_any_flow_port(node):  # type: ignore[attr-defined]
            raise ReverseGraphCodeError(
                f"数据依赖要求提前生成流程节点：{node.category}/{node.title}；该图在当前策略下无法稳定反向"
            )

        self._emit_node_statement(
            out_lines=out_lines,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )

    def _expr_for_required_data_input_or_constant(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
    ) -> str:
        """返回必需数据输入的变量表达式或常量表达式。"""
        node = self.model.nodes.get(node_id)  # type: ignore[attr-defined]
        if node is None:
            raise ReverseGraphCodeError("节点不存在")

        source = self.data_in_edge.get((node_id, port_name))  # type: ignore[attr-defined]
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            if expr is None:
                raise ReverseGraphCodeError(f"无法解析数据来源变量：{node.title}.{port_name}")
            return expr

        if port_name in (node.input_constants or {}):
            return format_constant((node.input_constants or {}).get(port_name))

        raise ReverseGraphCodeError(f"节点缺少输入：{node.title}.{port_name}")

    def _resolve_arithmetic_operator_numeric_result_type(self, *, node_id: str) -> str:
        """解析算术运算符表达式应标注的结果数值类型。"""
        left_type = str(self._port_type_resolver.resolve(str(node_id), "左值", is_input=True) or "").strip()  # type: ignore[attr-defined]
        right_type = str(self._port_type_resolver.resolve(str(node_id), "右值", is_input=True) or "").strip()  # type: ignore[attr-defined]
        out_type = str(self._port_type_resolver.resolve(str(node_id), "结果", is_input=False) or "").strip()  # type: ignore[attr-defined]
        if left_type in _NUMERIC_TYPES and right_type in _NUMERIC_TYPES and out_type in _NUMERIC_TYPES:
            return out_type
        node = self.model.nodes.get(str(node_id))  # type: ignore[attr-defined]
        title = str(getattr(node, "title", "") or "") if node is not None else str(node_id)
        raise ReverseGraphCodeError(
            f"启用了 prefer_arithmetic_operators，但节点 {title} 的左右值类型不是数值："
            f"左值={left_type or '（未知）'} 右值={right_type or '（未知）'} 结果={out_type or '（未知）'}；"
            "请修正端口类型推断/覆盖，或关闭该选项以输出 canonical 节点调用。"
        )

    def _try_emit_arithmetic_operator_statement(
        self,
        *,
        out_lines: List[str],
        node: NodeModel,
        node_id: str,
        output_var_names: List[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> bool:
        """尝试将基础算术节点发射为带括号的运算符表达式。"""
        if not bool(getattr(self.options, "prefer_arithmetic_operators", False)):  # type: ignore[attr-defined]
            return False

        title = str(getattr(node, "title", "") or "").strip()
        op = _ARITHMETIC_OPERATOR_BY_TITLE.get(title)
        if not op:
            return False

        if not output_var_names:
            raise ReverseGraphCodeError(f"算术节点 {title} 缺少数据输出端口，无法生成运算符表达式")
        if len(output_var_names) != 1:
            raise ReverseGraphCodeError(f"算术节点 {title} 存在多数据输出，无法生成运算符表达式")

        result_type = self._resolve_arithmetic_operator_numeric_result_type(node_id=str(node_id))
        left_expr = self._expr_for_required_data_input_or_constant(
            node_id=str(node_id),
            port_name="左值",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
        )
        right_expr = self._expr_for_required_data_input_or_constant(
            node_id=str(node_id),
            port_name="右值",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
        )
        expr = f"({left_expr} {op} {right_expr})"
        out_lines.append(f'{indent}{output_var_names[0]}: "{result_type}" = {expr}')
        self.emitted_nodes.add(str(node_id))  # type: ignore[attr-defined]
        return True

    def _expr_for_required_data_input(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        """返回控制流节点必需数据输入端口的变量表达式。"""
        node = self.model.nodes.get(node_id)  # type: ignore[attr-defined]
        if node is None:
            raise ReverseGraphCodeError("节点不存在")
        source = self.data_in_edge.get((node_id, port_name))  # type: ignore[attr-defined]
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            if expr is None:
                raise ReverseGraphCodeError(f"无法解析数据来源变量：{node.title}.{port_name}")
            return expr
        raise ReverseGraphCodeError(f"控制流节点缺少数据来源：{node.title}.{port_name}")

    def _expr_for_optional_data_input(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        """返回可选数据输入端口的变量表达式或常量表达式。"""
        node = self.model.nodes.get(node_id)  # type: ignore[attr-defined]
        if node is None:
            return ""
        source = self.data_in_edge.get((node_id, port_name))  # type: ignore[attr-defined]
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            return expr or ""
        if port_name in (node.input_constants or {}):
            return format_constant((node.input_constants or {}).get(port_name))
        return ""

    def _expr_for_required_match_subject(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        """返回 match subject 的变量名表达式并在不满足 Name 约束时 fail-fast。"""
        expr = self._expr_for_required_data_input(
            node_id=node_id,
            port_name=port_name,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=loop_stack,
        )
        if not expr.isidentifier() or keyword.iskeyword(expr):
            raise ReverseGraphCodeError(f"match subject 必须是变量名（Name），但当前为：{expr!r}")
        return expr

    def _render_match_case_pattern(self, port_name: str) -> str:
        """将多分支输出端口名渲染为 match/case 的 pattern 表达式。"""
        name = str(port_name or "").strip()
        if name == "默认":
            return "_"
        if name and (name.isdigit() or (name.startswith("-") and name[1:].isdigit())):
            return name
        return repr(name)

    def _unique_var_name(self, base: str, used: set[str]) -> str:
        """生成一个不与已有集合冲突的合法变量名。"""
        candidate = make_valid_identifier(base or "") or "var"
        if keyword.iskeyword(candidate):
            candidate = f"{candidate}_var"
        while candidate in used:
            candidate = f"{candidate}_1"
        used.add(candidate)
        return candidate

    def _emit_node_statement(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        """将普通节点渲染为赋值语句或调用语句并绑定数据输出变量。"""
        if node_id in self.emitted_nodes:  # type: ignore[attr-defined]
            return
        node = self.model.nodes.get(node_id)  # type: ignore[attr-defined]
        if node is None:
            return

        node_def = _resolve_node_def(node=node, node_library=self.node_library)  # type: ignore[attr-defined]
        call_name = _pick_call_name_for_node(
            node=node,
            node_def=node_def,
            node_library=self.node_library,  # type: ignore[attr-defined]
            node_name_index=self.node_name_index,  # type: ignore[attr-defined]
            call_name_candidates_by_identity=self.call_name_candidates_by_identity,  # type: ignore[attr-defined]
        )

        self._ensure_data_inputs_emitted(
            node=node,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
        )

        output_var_names = self._bind_data_output_vars(
            node=node,
            node_def=node_def,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
        )

        extra_args = _render_node_call_args(
            node=node,
            node_def=node_def,
            node_library=self.node_library,  # type: ignore[attr-defined]
            data_in_edge=self.data_in_edge,  # type: ignore[attr-defined]
            var_mapping=var_mapping,
        )
        call_expr = self._render_call_expr_for_node(
            node=node,
            node_def=node_def,
            call_name=call_name,
            extra_args=extra_args,
        )

        if self._try_emit_arithmetic_operator_statement(
            out_lines=out_lines,
            node=node,
            node_id=node_id,
            output_var_names=output_var_names,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        ):
            return

        self._emit_assignment_or_call(
            out_lines=out_lines,
            indent=indent,
            output_var_names=output_var_names,
            call_expr=call_expr,
        )
        self.emitted_nodes.add(node_id)  # type: ignore[attr-defined]

    def _ensure_data_inputs_emitted(
        self,
        *,
        node: NodeModel,
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
    ) -> None:
        """确保节点所有数据输入端口的来源节点已在当前作用域发出。"""
        for port in (node.inputs or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname:
                continue
            if self._is_flow_port(node, pname, False):  # type: ignore[attr-defined]
                continue
            source = self.data_in_edge.get((node_id, pname))  # type: ignore[attr-defined]
            if source is None:
                continue
            src_node_id, src_port = source
            src_key = (str(src_node_id), str(src_port))
            if src_key in var_mapping:
                continue
            if str(src_node_id) not in self.emitted_nodes:  # type: ignore[attr-defined]
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=str(src_node_id),
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )

    def _bind_data_output_vars(
        self,
        *,
        node: NodeModel,
        node_def: NodeDef,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
    ) -> List[str]:
        """为节点的数据输出端口绑定变量名并更新 var_mapping。"""
        data_outputs = [
            p
            for p in (node.outputs or [])
            if (str(getattr(p, "name", "") or ""))
            and (not self._is_flow_port(node, str(getattr(p, "name", "") or ""), True))  # type: ignore[attr-defined]
        ]
        if not data_outputs:
            return []

        raw_names = [str(getattr(p, "name", "") or "") for p in data_outputs]
        is_dynamic_outputs = bool(node_def is not None and (not getattr(node_def, "output_types", None)))
        output_var_names = raw_names if is_dynamic_outputs else _finalize_output_var_names(raw_names, used=used_var_names)
        for port, var_name in zip(data_outputs, output_var_names):
            port_name = str(getattr(port, "name", "") or "")
            var_mapping[(node.id, port_name)] = var_name
        return output_var_names

    def _render_call_expr_for_node(
        self,
        *,
        node: NodeModel,
        node_def: NodeDef,
        call_name: str,
        extra_args: Sequence[str],
    ) -> str:
        """渲染节点的调用表达式字符串。"""
        if bool(getattr(node_def, "is_composite", False)):
            return self._render_composite_call_expr(node=node, node_def=node_def, extra_args=extra_args)
        return f"{call_name}({', '.join(['self.game'] + list(extra_args))})"

    def _render_composite_call_expr(
        self,
        *,
        node: NodeModel,
        node_def: NodeDef,
        extra_args: Sequence[str],
    ) -> str:
        """渲染复合节点的 self.<实例>.<入口>(...) 调用表达式。"""
        composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(
            getattr(node, "composite_id", "") or ""
        ).strip()
        if not composite_id:
            composite_id = str(getattr(node_def, "name", "") or getattr(node, "title", "") or "").strip()
        alias = self.composite_alias_by_id.get(composite_id) or (  # type: ignore[attr-defined]
            make_valid_identifier(str(getattr(node_def, "name", "") or getattr(node, "title", "") or "")) or "复合实例"
        )
        if not alias.isidentifier() or keyword.iskeyword(alias):
            raise ReverseGraphCodeError(f"复合节点实例名不可作为 self 属性：{alias!r}")
        if extra_args:
            return f"self.{alias}.{self._composite_entry_method_name}({', '.join(extra_args)})"  # type: ignore[attr-defined]
        return f"self.{alias}.{self._composite_entry_method_name}()"  # type: ignore[attr-defined]

    def _emit_assignment_or_call(
        self,
        *,
        out_lines: List[str],
        indent: str,
        output_var_names: Sequence[str],
        call_expr: str,
    ) -> None:
        """根据输出变量个数发射赋值语句或直接调用语句。"""
        if output_var_names:
            if len(output_var_names) == 1:
                out_lines.append(f"{indent}{output_var_names[0]} = {call_expr}")
            else:
                lhs = ", ".join(output_var_names)
                out_lines.append(f"{indent}{lhs} = {call_expr}")
        else:
            out_lines.append(f"{indent}{call_expr}")

