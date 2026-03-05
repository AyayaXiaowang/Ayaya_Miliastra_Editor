from __future__ import annotations

import ast
import json
from pathlib import Path
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text
from engine.graph.composite.pin_marker_collector import (
    collect_pin_markers,
    infer_data_inputs_from_signature,
)
from engine.graph.composite.source_format import (
    find_composite_classes,
    try_extract_composite_payload_json,
)


class CompositePinDirectionRule(ValidationRule):
    """复合节点：引脚方向一致性校验

    约束：
    - payload 复合节点：virtual_pins[].is_input / is_flow 必须与 mapped_ports[].is_input / is_flow 一致。
      - 数据入（is_input=True）只能映射到内部输入端口（mapped_ports[].is_input=True）
      - 数据出（is_input=False）只能映射到内部输出端口（mapped_ports[].is_input=False）
      - 流程口/数据口同理（is_flow 必须一致）
    - 类格式复合节点：同一入口方法内，同名引脚不能同时声明为 数据入 与 数据出。
      - 数据入不能设置为出引脚（禁止“同名 in/out”）
    - 类格式复合节点：禁止“数据出变量直接（或经纯别名链）透传自数据入/入口形参”。
      - 典型错误：`数据出("描述回声")` + `描述回声 = 说明文本`（说明文本为数据入/入口形参）
    """

    rule_id = "engine_composite_pin_direction"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if not ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        payload_json = try_extract_composite_payload_json(tree)
        if payload_json is not None:
            payload_obj = json.loads(payload_json)
            if isinstance(payload_obj, dict):
                issues.extend(
                    _check_payload_virtual_pin_mappings(
                        payload_obj,
                        file_path,
                        default_level=self.default_level,
                    )
                )
            return issues

        composite_classes = find_composite_classes(tree)
        if composite_classes:
            issues.extend(
                _check_class_format_pin_direction_conflicts(
                    composite_classes,
                    file_path,
                    default_level=self.default_level,
                )
            )
            issues.extend(
                _check_class_format_data_output_passthrough_forbidden(
                    composite_classes,
                    file_path,
                    default_level=self.default_level,
                )
            )
            return issues

        return issues


def _check_payload_virtual_pin_mappings(
    payload_obj: object,
    file_path: Path,
    *,
    default_level: str,
) -> List[EngineIssue]:
    issues: List[EngineIssue] = []
    if not isinstance(payload_obj, dict):
        return issues

    virtual_pins = payload_obj.get("virtual_pins", [])
    if not isinstance(virtual_pins, list):
        return issues

    for pin in virtual_pins:
        if not isinstance(pin, dict):
            continue

        pin_name = str(pin.get("pin_name", "") or "")
        is_input = bool(pin.get("is_input", False))
        is_flow = bool(pin.get("is_flow", False))

        mapped_ports = pin.get("mapped_ports", [])
        if not isinstance(mapped_ports, list) or not mapped_ports:
            continue

        for mapped in mapped_ports:
            if not isinstance(mapped, dict):
                continue
            port_name = str(mapped.get("port_name", "") or "")
            mapped_is_input = bool(mapped.get("is_input", False))
            mapped_is_flow = bool(mapped.get("is_flow", False))

            if mapped_is_input != is_input:
                issues.append(
                    EngineIssue(
                        level=default_level,
                        category="复合节点",
                        code="COMPOSITE_VIRTUAL_PIN_MAPPING_DIRECTION_MISMATCH",
                        message=(
                            f"payload 复合节点引脚 '{pin_name}' 的方向为"
                            f"{'输入' if is_input else '输出'}，但其映射端口 '{port_name}' 标记为"
                            f"{'输入' if mapped_is_input else '输出'}。"
                            "数据入只能映射到内部输入端口，数据出只能映射到内部输出端口。"
                        ),
                        file=str(file_path),
                    )
                )

            if mapped_is_flow != is_flow:
                issues.append(
                    EngineIssue(
                        level=default_level,
                        category="复合节点",
                        code="COMPOSITE_VIRTUAL_PIN_MAPPING_FLOW_DATA_MISMATCH",
                        message=(
                            f"payload 复合节点引脚 '{pin_name}' 的端口类型为"
                            f"{'流程口' if is_flow else '数据口'}，但其映射端口 '{port_name}' 标记为"
                            f"{'流程口' if mapped_is_flow else '数据口'}。"
                            "流程口只能映射到流程端口，数据口只能映射到数据端口。"
                        ),
                        file=str(file_path),
                    )
                )

    return issues


def _decorator_name(decorator: ast.AST) -> str:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    return ""


def _check_class_format_pin_direction_conflicts(
    class_defs: List[ast.ClassDef],
    file_path: Path,
    *,
    default_level: str,
) -> List[EngineIssue]:
    issues: List[EngineIssue] = []

    for cls in class_defs:
        for item in cls.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            decorator_names = [_decorator_name(d) for d in (item.decorator_list or [])]
            if "flow_entry" not in decorator_names:
                continue

            markers = collect_pin_markers(item)
            signature_inputs = infer_data_inputs_from_signature(item)

            data_input_names = {m.name for m in (signature_inputs or [])}
            data_input_names.update(m.name for m in (markers.data_inputs or []))
            data_output_names = {m.name for m in (markers.data_outputs or [])}

            conflicts = sorted(data_input_names & data_output_names)
            if not conflicts:
                continue

            for pin_name in conflicts:
                issues.append(
                    EngineIssue(
                        level=default_level,
                        category="复合节点",
                        code="COMPOSITE_PIN_DIRECTION_CONFLICT",
                        message=(
                            f"类格式复合节点 {cls.name}.{item.name} 的引脚 '{pin_name}' 同时被声明为"
                            " 数据入(输入) 与 数据出(输出)。数据入不能设置为出引脚，请修改引脚名或拆分为不同引脚。"
                        ),
                        file=str(file_path),
                        line_span=line_span_text(item),
                    )
                )

    return issues


def _collect_assignment_facts(
    func_def: ast.FunctionDef,
) -> Tuple[Dict[str, Set[str]], Dict[str, bool]]:
    """收集函数内的“纯别名赋值”与“非别名赋值”事实。

    返回：
    - alias_sources: {目标变量名: {来源变量名...}}
      仅收集形如 `目标 = 来源` / `目标: "类型" = 来源`（来源为 Name）的赋值。
    - has_non_alias_assignment: {目标变量名: True/False}
      只要出现过对该目标变量的非别名赋值（例如 Call/常量/表达式），即记为 True。
    """
    alias_sources: Dict[str, Set[str]] = {}
    has_non_alias_assignment: Dict[str, bool] = {}

    for node in ast.walk(func_def):
        targets: List[ast.expr] = []
        value: Optional[ast.expr] = None
        if isinstance(node, ast.Assign):
            targets = list(getattr(node, "targets", []) or [])
            value = getattr(node, "value", None)
        elif isinstance(node, ast.AnnAssign):
            tgt = getattr(node, "target", None)
            if tgt is not None:
                targets = [tgt]
            value = getattr(node, "value", None)
        else:
            continue

        value_is_name = isinstance(value, ast.Name)
        source_name = value.id if value_is_name else ""

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            target_name = target.id
            if value_is_name:
                alias_sources.setdefault(target_name, set()).add(source_name)
            else:
                has_non_alias_assignment[target_name] = True

    return alias_sources, has_non_alias_assignment


def _find_passthrough_chain(
    start_name: str,
    input_names: Set[str],
    alias_sources: Dict[str, Set[str]],
    has_non_alias_assignment: Dict[str, bool],
) -> Optional[List[str]]:
    """寻找一条“纯别名链”从 start_name 走到某个 input_names 的链路。

    约束：
    - 一旦遇到 `has_non_alias_assignment[var]=True`，该变量视为“已被节点/表达式赋值参与”，不再沿别名继续扩展。
    """
    start = str(start_name or "")
    if not start:
        return None

    queue: Deque[str] = deque([start])
    parent: Dict[str, Optional[str]] = {start: None}

    while queue:
        current = queue.popleft()
        if current in input_names:
            # reconstruct: start -> ... -> current
            chain_rev: List[str] = []
            cursor: Optional[str] = current
            while cursor is not None:
                chain_rev.append(cursor)
                cursor = parent.get(cursor)
            return list(reversed(chain_rev))

        if has_non_alias_assignment.get(current, False):
            continue

        for src in sorted(alias_sources.get(current, set())):
            if src not in parent:
                parent[src] = current
                queue.append(src)

    return None


def _check_class_format_data_output_passthrough_forbidden(
    class_defs: List[ast.ClassDef],
    file_path: Path,
    *,
    default_level: str,
) -> List[EngineIssue]:
    """类格式复合节点：禁止数据出变量透传自数据入/入口形参。

    说明：
    - 这里的“透传”仅指“纯别名链”（`a = b` / `a: "类型" = b`）最终指向入口形参/数据入；
    - 若通过节点调用产生输出（例如 `a = 某节点(self.game, ...)`），则不视为透传（属于正常的内部数据流）。
    """
    issues: List[EngineIssue] = []

    for cls in class_defs:
        for item in cls.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            decorator_names = [_decorator_name(d) for d in (item.decorator_list or [])]
            if "flow_entry" not in decorator_names:
                continue

            markers = collect_pin_markers(item)
            signature_inputs = infer_data_inputs_from_signature(item)
            input_names: Set[str] = {m.name for m in (signature_inputs or [])}
            input_names.update(m.name for m in (markers.data_inputs or []))
            if not input_names:
                continue

            data_outputs = list(markers.data_outputs or [])
            if not data_outputs:
                continue

            alias_sources, has_non_alias_assignment = _collect_assignment_facts(item)

            for out_marker in data_outputs:
                out_pin_name = str(getattr(out_marker, "name", "") or "")
                out_var_name = str(getattr(out_marker, "variable", "") or "") or out_pin_name
                if not out_var_name:
                    continue

                # 若输出变量在方法内参与过“非别名赋值”，则视为已进入内部数据流（不认为是纯透传）
                if has_non_alias_assignment.get(out_var_name, False):
                    continue

                chain = _find_passthrough_chain(
                    out_var_name,
                    input_names,
                    alias_sources,
                    has_non_alias_assignment,
                )
                if not chain:
                    continue

                root = chain[-1]
                chain_text = " -> ".join(chain)
                issues.append(
                    EngineIssue(
                        level=default_level,
                        category="复合节点",
                        code="COMPOSITE_DATA_OUTPUT_PASSTHROUGH_FORBIDDEN",
                        message=(
                            f"类格式复合节点 {cls.name}.{item.name} 的数据出引脚 '{out_pin_name}' "
                            f"对应变量 '{out_var_name}' 透传自数据入/入口形参 '{root}'（{chain_text}）。"
                            "数据出不允许直接透传数据入，请通过节点调用产生输出，或显式落地到局部变量节点后再输出。"
                        ),
                        file=str(file_path),
                        line_span=line_span_text(item),
                    )
                )

    return issues


