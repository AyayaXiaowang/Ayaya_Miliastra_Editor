from __future__ import annotations

import ast
import keyword
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

from engine.nodes.node_registry import get_node_registry
from engine.utils.graph.graph_utils import is_flow_port_name

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    line_span_text,
)


@lru_cache(maxsize=8)
def _required_input_ports_by_func(workspace_path: Path, scope: str) -> Dict[str, List[str]]:
    """构造 {节点函数名: 必填输入端口名列表(按声明顺序)} 映射。

    约定：
    - 仅检查“静态输入端口”（来自 NodeDef.inputs）；
    - 流程端口（如“流程入/流程出”）不参与 Graph Code 的参数传递，因此不视为缺参；
    - 变参占位端口（名称中含“~”）不视为真实端口名，不参与缺参判断。
    """
    scope_text = str(scope or "").strip().lower()
    if scope_text not in {"server", "client"}:
        scope_text = "server"

    # 仅针对“基础节点函数调用”做缺参校验：
    # 复合节点在 Graph Code 中以“类实例 + 方法调用”形式出现，不以节点函数调用形式传入端口。
    registry = get_node_registry(workspace_path, include_composite=False)
    library = registry.get_library()
    mapping: Dict[str, List[str]] = {}
    for full_key, node_def in (library.items() if isinstance(library, dict) else []):
        if bool(getattr(node_def, "is_composite", False)):
            continue
        if not bool(getattr(node_def, "is_available_in_scope", lambda _scope: True)(scope_text)):
            continue

        # 节点在 Graph Code 中的“可调用名”以节点库 key 的名称部分为准：`类别/名称` → `名称`。
        # 这样可以覆盖 V2 管线注入的别名（例如 make_valid_identifier 派生的可调用别名）。
        if not isinstance(full_key, str) or "/" not in full_key:
            continue
        _, func_name = full_key.split("/", 1)
        func_name = str(func_name or "").strip()
        if (not func_name) or ("#" in func_name) or (not func_name.isidentifier()) or keyword.iskeyword(func_name):
            continue

        inputs = list(getattr(node_def, "inputs", []) or [])
        required_ports: List[str] = []
        for port_name in inputs:
            if not isinstance(port_name, str) or port_name == "":
                continue
            if "~" in port_name:
                continue
            if is_flow_port_name(port_name):
                continue
            required_ports.append(port_name)
        if required_ports:
            mapping[func_name] = required_ports
    return mapping


class RequiredInputsRule(ValidationRule):
    """通用必填入参校验：节点调用必须提供所有必填输入端口。

    背景：
    - Graph Code 中，节点调用以 `节点名(self.game, 端口名=值, ...)` 的形式显式传入输入端口；
    - 节点的“必填输入端口集合”以节点库（NodeDef.inputs）为唯一权威；
    - 若漏传某个必填端口，运行时代码生成/执行往往会产生静默错误（字段不写回/绑定信息丢失等）。
    """

    rule_id = "engine_code_required_inputs"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        required_ports_by_func = _required_input_ports_by_func(ctx.workspace_path, scope)
        if not required_ports_by_func:
            return []

        issues: List[EngineIssue] = []

        from engine.graph.ir.arg_normalizer import is_reserved_argument

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue

                func_name = func.id
                required_ports = required_ports_by_func.get(func_name)
                if not required_ports:
                    continue

                provided_ports: Set[str] = set()

                # 1) 关键字参数直接映射端口名
                for kw in getattr(node, "keywords", []) or []:
                    arg = getattr(kw, "arg", None)
                    if isinstance(arg, str) and arg:
                        provided_ports.add(arg)

                # 2) 位置参数：过滤 self/game/owner_entity 等保留参数，将其余按“必填端口声明顺序”映射
                pos_args = list(getattr(node, "args", []) or [])
                data_args = [arg for arg in pos_args if not is_reserved_argument(arg)]
                if data_args:
                    for i in range(min(len(data_args), len(required_ports))):
                        provided_ports.add(required_ports[i])

                missing = [p for p in required_ports if p not in provided_ports]
                if not missing:
                    continue

                missing_text = "，".join(missing)
                msg = (
                    f"{line_span_text(node)}: 【{func_name}】调用缺少必填输入端口参数: {missing_text}。"
                    f"请按节点定义补全这些端口的输入值（流程端口不在本规则检查范围）。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_NODE_MISSING_REQUIRED_INPUTS",
                        msg,
                    )
                )

        return issues


__all__ = ["RequiredInputsRule"]


