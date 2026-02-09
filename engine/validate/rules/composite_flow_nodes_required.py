from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional

from engine.graph.common import node_name_index_from_library
from engine.graph.composite.pin_marker_collector import collect_pin_markers
from engine.graph.composite.source_format import find_composite_classes
from engine.graph.utils.metadata_extractor import extract_metadata_from_docstring
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.nodes.port_type_system import FLOW_PORT_TYPE
from engine.utils.graph.graph_utils import is_flow_port_name

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text


_PIN_MARKER_FUNCTION_NAMES: set[str] = {
    "流程入",
    "流程入引脚",
    "流程出",
    "流程出引脚",
    "数据入",
    "数据出",
}

_FLOW_CONTROL_STATEMENT_TYPES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.Match,
    ast.For,
    ast.While,
)


class CompositeFlowNodesRequiredRule(ValidationRule):
    """复合节点：当入口方法声明了流程引脚时，必须存在可建模的流程节点。

    背景：
    - 类格式复合节点的 `流程入/流程出` 只是“虚拟引脚声明”，本身不产生流程节点；
    - 若方法体内没有任何流程节点（执行节点/流程控制节点），将无法把虚拟流程引脚映射到子图流程连线，
      最终表现为“有流程口但内部无流程链路”，属于结构性错误。
    """

    rule_id = "engine_composite_flow_nodes_required"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if not ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)

        # scope-aware：确保 server/client 变体节点的“无后缀名称”映射正确
        docstring = ast.get_docstring(tree) or ""
        metadata = extract_metadata_from_docstring(docstring)
        scope = str((metadata.scope or metadata.graph_type or "server") or "server").strip().lower()

        # 只需要基础节点库即可判断“调用的节点是否为流程节点”
        registry = get_node_registry(ctx.workspace_path, include_composite=False)
        node_library: Dict[str, NodeDef] = registry.get_library()
        node_name_index = node_name_index_from_library(node_library, scope=scope)

        issues: List[EngineIssue] = []
        for composite_class in find_composite_classes(tree):
            for class_item in (composite_class.body or []):
                if not isinstance(class_item, ast.FunctionDef):
                    continue

                if not _has_decorator_named(class_item, "flow_entry"):
                    continue

                markers = collect_pin_markers(class_item)
                declares_flow_pins = bool((markers.flow_inputs or []) or (markers.flow_outputs or []))
                if not declares_flow_pins:
                    continue

                if _method_body_has_any_flow_nodes(class_item, node_library=node_library, node_name_index=node_name_index):
                    continue

                issues.append(
                    EngineIssue(
                        level=self.default_level,
                        category=self.category,
                        code="COMPOSITE_FLOW_PINS_WITHOUT_FLOW_NODES",
                        message=(
                            f"{line_span_text(class_item)}: 类格式复合节点 {composite_class.name}.{class_item.name} "
                            "声明了流程引脚（流程入/流程出），但方法体内未产生任何可建模的流程节点。"
                            "这会导致虚拟流程引脚无法映射到子图流程连线。\n"
                            "修复建议：如果这是纯数据计算，请移除流程入/流程出；"
                            "如果需要流程节点，请至少调用一个带流程端口的节点（执行/流程控制节点），"
                            "或使用 if/match/for/while 等会生成流程控制节点的结构。"
                        ),
                        file=str(file_path),
                        line_span=line_span_text(class_item),
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


def _has_decorator_named(func_def: ast.FunctionDef, decorator_name: str) -> bool:
    expected = str(decorator_name or "")
    if not expected:
        return False
    for decorator in (func_def.decorator_list or []):
        if _decorator_name(decorator) == expected:
            return True
    return False


def _extract_call_name(call_node: ast.Call) -> str:
    func_expr = getattr(call_node, "func", None)
    if isinstance(func_expr, ast.Name):
        return str(func_expr.id or "")
    if isinstance(func_expr, ast.Attribute):
        return str(func_expr.attr or "")
    return ""


def _node_def_has_flow_ports(node_def: Optional[NodeDef]) -> bool:
    if node_def is None:
        return False
    # 优先：显式端口类型（最可靠，支持“成功/失败”等非标准流程端口名）
    for port_type in list(getattr(node_def, "input_types", {}).values()) + list(getattr(node_def, "output_types", {}).values()):
        if str(port_type or "") == FLOW_PORT_TYPE:
            return True
    # 回退：端口名启发式（兼容缺少显式类型定义的流程端口）
    for port_name in list(getattr(node_def, "inputs", []) or []) + list(getattr(node_def, "outputs", []) or []):
        port_text = str(port_name or "")
        if not port_text:
            continue
        if is_flow_port_name(port_text):
            return True
    return False


def _method_body_has_any_flow_nodes(
    func_def: ast.FunctionDef,
    *,
    node_library: Dict[str, NodeDef],
    node_name_index: Dict[str, str],
) -> bool:
    # 控制流语句本身会在 IR 中建模为流程控制节点（双分支/多分支/循环等）
    for node in ast.walk(func_def):
        if isinstance(node, _FLOW_CONTROL_STATEMENT_TYPES):
            return True

    # 识别“带流程端口的节点调用”（执行节点/流程控制节点/事件节点等）
    for node in ast.walk(func_def):
        if not isinstance(node, ast.Call):
            continue
        call_name = _extract_call_name(node)
        if not call_name:
            continue
        if call_name in _PIN_MARKER_FUNCTION_NAMES:
            continue

        full_key = node_name_index.get(call_name)
        if not full_key:
            continue
        node_def = node_library.get(full_key)
        if _node_def_has_flow_ports(node_def):
            return True

    return False


__all__ = ["CompositeFlowNodesRequiredRule"]


