from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from engine.graph.common import validate_pin_type_annotation


@dataclass
class PinMarker:
    name: str
    pin_type: str


@dataclass
class DataOutputMarker(PinMarker):
    variable: str


@dataclass
class PinMarkerSummary:
    flow_inputs: List[PinMarker] = field(default_factory=list)
    flow_outputs: List[PinMarker] = field(default_factory=list)
    data_inputs: List[PinMarker] = field(default_factory=list)
    data_outputs: List[DataOutputMarker] = field(default_factory=list)


FLOW_IN_FUNCTIONS = {"流程入", "流程入引脚"}
FLOW_OUT_FUNCTIONS = {"流程出", "流程出引脚"}
DATA_IN_FUNCTIONS = {"数据入"}
DATA_OUT_FUNCTIONS = {"数据出"}


def collect_pin_markers(func_def: ast.FunctionDef) -> PinMarkerSummary:
    """扫描函数体，收集流程/数据引脚声明"""
    visitor = _PinMarkerVisitor()
    visitor.visit(func_def)
    return visitor.summary


def infer_data_inputs_from_signature(func_def: ast.FunctionDef) -> List[PinMarker]:
    """根据方法签名（除 self 外）推断数据输入列表"""
    markers: List[PinMarker] = []
    for arg in func_def.args.args[1:]:
        pin_name = arg.arg
        pin_type = _resolve_annotation(arg.annotation)
        markers.append(PinMarker(pin_name, pin_type))
    return markers


def _resolve_annotation(annotation: Optional[ast.expr]) -> str:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return validate_pin_type_annotation(annotation.value.strip(), allow_python_builtin=False)
    if isinstance(annotation, ast.Name):
        return validate_pin_type_annotation(annotation.id, allow_python_builtin=False)
    return "泛型"


class _PinMarkerVisitor(ast.NodeVisitor):
    def __init__(self):
        self.summary = PinMarkerSummary()
        self._flow_in_seen: Dict[str, PinMarker] = {}
        self._flow_out_seen: Dict[str, PinMarker] = {}
        self._data_in_seen: Dict[str, PinMarker] = {}
        self._data_out_seen: Dict[str, DataOutputMarker] = {}

    def visit_Call(self, node: ast.Call) -> None:
        func_name = _extract_call_name(node)
        if not func_name:
            return super().visit_Call(node)

        if func_name in FLOW_IN_FUNCTIONS:
            marker = self._build_pin_marker(node, default_name="流程入", default_type="流程")
            if marker and marker.name not in self._flow_in_seen:
                self._flow_in_seen[marker.name] = marker
                self.summary.flow_inputs.append(marker)
        elif func_name in FLOW_OUT_FUNCTIONS:
            marker = self._build_pin_marker(node, default_name="流程出", default_type="流程")
            if marker and marker.name not in self._flow_out_seen:
                self._flow_out_seen[marker.name] = marker
                self.summary.flow_outputs.append(marker)
        elif func_name in DATA_IN_FUNCTIONS:
            marker = self._build_pin_marker(node, default_name="", default_type="泛型")
            if marker and marker.name not in self._data_in_seen:
                self._data_in_seen[marker.name] = marker
                self.summary.data_inputs.append(marker)
        elif func_name in DATA_OUT_FUNCTIONS:
            marker = self._build_data_output_marker(node)
            if marker and marker.name not in self._data_out_seen:
                self._data_out_seen[marker.name] = marker
                self.summary.data_outputs.append(marker)

        self.generic_visit(node)

    def _build_pin_marker(self, node: ast.Call, *, default_name: str, default_type: str) -> Optional[PinMarker]:
        pin_name = _extract_str_arg(node, ("名称", "名字", "name", "pin_name"), positional_index=0)
        if not pin_name:
            pin_name = default_name or ""
        if not pin_name:
            return None

        pin_type_raw = _extract_str_arg(node, ("类型", "type", "pin_type"), positional_index=1)
        pin_type = pin_type_raw or default_type
        pin_type = validate_pin_type_annotation(pin_type, allow_python_builtin=False)
        return PinMarker(pin_name, pin_type)

    def _build_data_output_marker(self, node: ast.Call) -> Optional[DataOutputMarker]:
        marker = self._build_pin_marker(node, default_name="", default_type="泛型")
        if not marker:
            return None
        variable = _extract_str_arg(node, ("变量", "变量名", "variable", "var_name"), positional_index=None)
        return DataOutputMarker(marker.name, marker.pin_type, variable or marker.name)


def _extract_call_name(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_str_arg(node: ast.Call, keyword_names: Sequence[str], positional_index: Optional[int]) -> Optional[str]:
    for keyword in node.keywords:
        if keyword.arg in keyword_names:
            return _constant_to_str(keyword.value)
    if positional_index is not None and len(node.args) > positional_index:
        return _constant_to_str(node.args[positional_index])
    return None


def _constant_to_str(expr: ast.expr) -> Optional[str]:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    return None


