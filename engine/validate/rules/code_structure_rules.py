"""
代码结构规范规则：if布尔条件、可变参数节点最小入参、节点图变量声明、类型名合法性等
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from engine.configs.specialized.node_graph_configs import StructDefinition
from engine.nodes.node_registry import get_node_registry
from engine.nodes.port_type_system import FLOW_PORT_TYPE, ANY_PORT_TYPE, GENERIC_PORT_TYPE
from engine.graph.utils.metadata_extractor import extract_graph_variables_from_ast
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
    SIGNAL_NAME_PORT_NAME,
)
from engine.signal import get_default_signal_repository

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import (
    get_cached_module,
    read_source,
    extract_declared_graph_vars,
    line_span_text,
    iter_class_methods,
    create_rule_issue,
)
from .datatype_rules import BASE_TYPES, LIST_TYPES
from .node_index import boolean_node_names, variadic_min_args, event_node_names


_ALLOWED_TYPE_NAMES_CACHE: Dict[str, Set[str]] = {}


def _get_allowed_type_names(workspace_path: Path) -> Set[str]:
    """返回当前工作区下节点图支持的所有数据类型名称集合（含结构体/列表/端口类型）。"""
    cache_key = str(workspace_path.resolve())
    cached = _ALLOWED_TYPE_NAMES_CACHE.get(cache_key)
    if cached is not None:
        return cached

    allowed: Set[str] = set()

    # 1) 基础数据类型与列表类型（数据类型规则里的权威定义）
    for type_name in BASE_TYPES.keys():
        if isinstance(type_name, str) and type_name:
            allowed.add(type_name)
    for type_name in LIST_TYPES.keys():
        if isinstance(type_name, str) and type_name:
            allowed.add(type_name)

    # 2) 结构体定义中声明的支持类型（包含“结构体”等早期命名形式）
    struct_definition = StructDefinition()
    for type_name in struct_definition.supported_types:
        if isinstance(type_name, str) and type_name:
            allowed.add(type_name)

    # 3) 节点端口类型（节点库中所有输入/输出/动态端口类型）
    registry = get_node_registry(workspace_path, include_composite=True)
    node_library = registry.get_library()
    for _, node_def in node_library.items():
        for port_type in getattr(node_def, "input_types", {}).values():
            if isinstance(port_type, str) and port_type:
                allowed.add(port_type)
        for port_type in getattr(node_def, "output_types", {}).values():
            if isinstance(port_type, str) and port_type:
                allowed.add(port_type)
        dynamic_type = getattr(node_def, "dynamic_port_type", "")
        if isinstance(dynamic_type, str) and dynamic_type:
            allowed.add(dynamic_type)

    # 4) 特殊端口类型与流程类型
    allowed.add(FLOW_PORT_TYPE)
    allowed.add(ANY_PORT_TYPE)
    allowed.add(GENERIC_PORT_TYPE)
    # 节点库中广泛使用的“枚举”端口类型
    allowed.add("枚举")

    _ALLOWED_TYPE_NAMES_CACHE[cache_key] = allowed
    return allowed


def _parse_typed_dict_alias(type_name: str) -> tuple[bool, str, str]:
    """解析类似“字符串-GUID列表字典”的别名字典类型。

    约定格式：
    - 统一以“字典”结尾，例如：`字符串-GUID列表字典`
    - 以第一个“-”划分键/值类型名：左侧为键类型，右侧为值类型
    - 键/值类型名本身必须是已有的合法类型名（例如：整数、字符串、GUID列表等）

    返回三元组：
    - is_alias: 是否匹配该别名格式
    - key_type: 键类型名（仅在 is_alias 为 True 时有意义）
    - value_type: 值类型名（仅在 is_alias 为 True 时有意义）
    """
    text = type_name.strip()
    if not text:
        return False, "", ""
    if not text.endswith("字典"):
        return False, "", ""

    body = text[: -len("字典")].strip()
    if not body:
        return False, "", ""

    dash_index = body.find("-")
    underscore_index = body.find("_")

    separator_index = -1
    if dash_index >= 0 and underscore_index >= 0:
        separator_index = min(dash_index, underscore_index)
    elif dash_index >= 0:
        separator_index = dash_index
    else:
        separator_index = underscore_index

    if separator_index <= 0 or separator_index >= len(body) - 1:
        return False, "", ""

    key_raw = body[:separator_index]
    value_raw = body[separator_index + 1 :]
    key_type = key_raw.strip()
    value_type = value_raw.strip()
    if not key_type or not value_type:
        return False, "", ""

    return True, key_type, value_type


class IfBooleanRule(ValidationRule):
    """if 条件必须为布尔表达式；禁止使用 if not ..."""

    rule_id = "engine_code_if_boolean"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        boolean_funcs = boolean_node_names(ctx.workspace_path)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            bool_vars_assigned: Set[str] = set()
            # 收集布尔变量赋值
            for node in ast.walk(method):
                targets = []
                value = None

                # 普通赋值：flag = True / flag = 是否相等(...)
                if isinstance(node, ast.Assign):
                    targets = list(getattr(node, "targets", []) or [])
                    value = getattr(node, "value", None)

                # 带类型注解的赋值：flag: "布尔值" = 是否相等(...)
                elif isinstance(node, ast.AnnAssign):
                    target = getattr(node, "target", None)
                    if isinstance(target, ast.Name):
                        targets = [target]
                    elif isinstance(target, ast.Tuple):
                        targets = list(getattr(target, "elts", []) or [])
                    value = getattr(node, "value", None)

                if not targets or value is None:
                    continue

                # 常量布尔赋值
                if isinstance(value, ast.Constant) and isinstance(
                    getattr(value, "value", None), bool
                ):
                    for tgt in targets:
                        if isinstance(tgt, ast.Name):
                            bool_vars_assigned.add(tgt.id)
                # 布尔节点调用赋值
                if isinstance(value, ast.Call) and isinstance(
                    getattr(value, "func", None), ast.Name
                ):
                    fname = value.func.id
                    if fname in boolean_funcs:
                        for tgt in targets:
                            if isinstance(tgt, ast.Name):
                                bool_vars_assigned.add(tgt.id)

            # 检查 if 条件
            for node in ast.walk(method):
                if not isinstance(node, ast.If):
                    continue
                # 禁止 if not ...
                if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                    issues.append(create_rule_issue(self, file_path, node, "CODE_IF_NOT_FORBIDDEN",
                                              f"{line_span_text(node)}: 禁止使用 'if not ...'，请使用【逻辑非】节点构造取反后的布尔条件"))
                # 必须是布尔表达式
                is_boolean_expr = _is_boolean_expr(node.test, boolean_funcs, bool_vars_assigned)
                if not is_boolean_expr:
                    issues.append(create_rule_issue(self, file_path, node, "CODE_IF_NON_BOOL_CONDITION",
                                              f"{line_span_text(node)}: if 条件必须为布尔类型；请使用布尔节点或其输出赋值后的变量，禁止将非布尔数据直接作为条件"))
                    continue
                if _contains_inline_compare(node.test):
                    issues.append(create_rule_issue(
                        self,
                        file_path,
                        node.test,
                        "CODE_IF_INLINE_COMPARISON",
                        f"{line_span_text(node.test)}: 禁止在 if 条件中直接书写 Python 比较（如 'A == B' 或 'X is None'）；请改用比较类节点输出，或先将布尔结果赋值给变量后再分支",
                    ))

        return issues


class VariadicMinArgsRule(ValidationRule):
    """可变参数节点：至少提供指定数量的数据入参。"""

    rule_id = "engine_code_variadic_min_args"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        rules = variadic_min_args(ctx.workspace_path)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                fname = func.id
                if fname not in rules:
                    continue
                required = int(rules[fname])
                total_pos_args = len(getattr(node, "args", []) or [])
                provided_data_args = max(0, total_pos_args - 1)  # 跳过 self.game
                if provided_data_args < required:
                    if required == 1:
                        msg = f"{line_span_text(node)}: 【{fname}】不允许空参数，至少提供 1 个输入"
                    else:
                        msg = f"{line_span_text(node)}: 【{fname}】不允许空参数，至少提供 {required} 个输入（例如一对键值）"
                    issues.append(create_rule_issue(self, file_path, node, "CODE_VARIADIC_MIN_ARGS", msg))

        return issues


class GraphVarsDeclarationRule(ValidationRule):
    """【设置/获取节点图变量】的『变量名』必须在 GRAPH_VARIABLES 中声明。"""

    rule_id = "engine_code_graph_vars_decl"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        declared: Set[str] = extract_declared_graph_vars(tree, read_source(file_path))
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not (isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name)):
                    continue
                fname = node.func.id
                if fname not in ("设置节点图变量", "获取节点图变量"):
                    continue
                var_kw = None
                for kw in (node.keywords or []):
                    if kw.arg == "变量名":
                        var_kw = kw
                        break
                if var_kw is None:
                    issues.append(create_rule_issue(self, file_path, node, "CODE_GRAPH_VAR_DECLARATION",
                                              f"{line_span_text(node)}: 【{fname}】必须提供参数『变量名』，且为字符串常量并在文件顶部的 GRAPH_VARIABLES 清单中声明"))
                    continue
                value_node = var_kw.value
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    var_name = value_node.value.strip()
                    if (not declared) or (var_name not in declared):
                        extra = ""
                        if declared:
                            preview = "、".join(sorted(list(declared))[:8])
                            more = "" if len(declared) <= 8 else "..."
                            extra = f"；已声明: {preview}{more}"
                        else:
                            extra = "；未在文件顶部声明任何 GRAPH_VARIABLES 图变量"
                        issues.append(create_rule_issue(self, file_path, value_node, "CODE_GRAPH_VAR_DECLARATION",
                                                  f"{line_span_text(value_node)}: 【{fname}】参数『变量名』='{var_name}' 未在 GRAPH_VARIABLES 清单中声明{extra}"))
                else:
                    target = value_node if hasattr(value_node, "lineno") else node
                    issues.append(create_rule_issue(self, file_path, target, "CODE_GRAPH_VAR_DECLARATION",
                                              f"{line_span_text(target)}: 【{fname}】的参数『变量名』必须为字符串常量，并在 GRAPH_VARIABLES 清单中声明"))

        return issues


class SignalParamNamesRule(ValidationRule):
    """发送信号：调用中使用的参数名必须出现在信号定义的参数列表中。

    场景：
    - 程序员在 Graph Code 中直接写 `发送信号(self.game, 信号名=\"xxx\", 不存在的参数=1)`。
    - 若 `不存在的参数` 不在信号 `xxx` 的参数定义里，则视为错误，防止“写错参数名但静默被忽略”。
    """

    rule_id = "engine_code_signal_param_names"
    category = "信号系统"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)

        # 加载全局信号定义视图（来自代码级 Schema 视图或内置常量）。
        repo = get_default_signal_repository()
        allowed_params_by_id: Dict[str, Set[str]] = repo.get_allowed_param_names_by_id()
        if not allowed_params_by_id:
            return []

        all_signals: Dict[str, Dict] = repo.get_all_payloads()

        issues: List[EngineIssue] = []
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                # 仅关心【发送信号】节点调用
                if func.id != SIGNAL_SEND_NODE_TITLE:
                    continue

                # 提取“信号名”参数的字面量值，用于定位信号定义。
                signal_key = ""
                for kw in getattr(node, "keywords", []) or []:
                    name = kw.arg
                    if name != SIGNAL_NAME_PORT_NAME:
                        continue
                    value = getattr(kw, "value", None)
                    if isinstance(value, ast.Constant) and isinstance(getattr(value, "value", None), str):
                        signal_key = value.value.strip()  # type: ignore[attr-defined]
                    break

                if not signal_key:
                    # 未显式指定“信号名”，交由其他规则/运行时处理。
                    continue

                # 根据 signal_name 反查信号定义。
                # 约定：Graph Code 中“信号名”参数必须使用『信号名称』，禁止直接填写信号 ID；
                # 若发现填写的是某个 signal_id，则单独报错提示改为使用名称。
                signal_id = ""
                resolved_id = repo.resolve_id_by_name(signal_key)
                if resolved_id:
                    signal_id = resolved_id
                else:
                    # 未匹配到任何名称，进一步判断是否误用 ID。
                    payload = repo.get_payload(signal_key)
                    if payload is not None:
                        signal_display_name = str(payload.get("signal_name") or signal_key)
                        msg = (
                            f"{line_span_text(node)}: 【发送信号】的“信号名”参数值 '{signal_key}' "
                            f"是信号 ID，请改为使用该信号的名称 '{signal_display_name}' "
                            f"作为“信号名”参数；信号 ID 仅用于事件名或内部绑定，不应用于 Graph Code。"
                        )
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_SIGNAL_ID_NOT_ALLOWED",
                                msg,
                            )
                        )
                        continue

                    msg = (
                        f"{line_span_text(node)}: 【发送信号】的“信号名”参数值 '{signal_key}' "
                        f"在当前信号定义中不存在，请先在信号管理的代码资源中定义该信号，"
                        f"或改用已有信号的名称。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_SIGNAL_UNKNOWN_ID",
                            msg,
                        )
                    )
                    continue

                allowed_params = allowed_params_by_id.get(signal_id, set())
                if not allowed_params:
                    continue

                # 收集调用中实际使用的“数据参数名”：排除静态输入端口（流程入/目标实体/信号名）。
                used_params: Set[str] = set()
                for kw in getattr(node, "keywords", []) or []:
                    name = kw.arg
                    if not isinstance(name, str) or not name:
                        continue
                    if name in static_inputs:
                        continue
                    used_params.add(name)

                extra = used_params - allowed_params
                if not extra:
                    continue

                extra_text = ", ".join(sorted(extra))
                msg = (
                    f"{line_span_text(node)}: 【发送信号】调用中使用了信号定义中不存在的参数: {extra_text}；"
                    f"这些参数在运行时不会收到任何值，请参照信号 '{signal_id}' 的参数列表修正参数名，"
                    f"或在信号管理中补充对应的参数定义。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_SIGNAL_EXTRA_PARAMS",
                        msg,
                    )
                )

        return issues


class NoLiteralAssignmentRule(ValidationRule):
    """禁止使用 Python 常量直接赋值（应依附节点输出或事件参数）。"""

    rule_id = "engine_code_no_literal_assignment"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if isinstance(node, ast.Assign):
                    value = getattr(node, "value", None)
                    if _is_literal_expression(value):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                value or node,
                                "CODE_NO_LITERAL_ASSIGNMENT",
                                f"{line_span_text(value or node)}: 禁止直接将常量赋值给变量，请改用节点输出（如【获取局部变量】或常量节点）",
                            )
                        )
                elif isinstance(node, ast.AnnAssign):
                    value = getattr(node, "value", None)
                    if _is_literal_expression(value):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                value or node,
                                "CODE_NO_LITERAL_ASSIGNMENT",
                                f"{line_span_text(value or node)}: 禁止直接将常量赋值给变量，请改用节点输出（如【获取局部变量】或常量节点）",
                            )
                        )

        return issues


class EventNameRule(ValidationRule):
    """事件名合法性校验：register_event_handler 注册的事件名必须来源于事件节点或信号。"""

    rule_id = "engine_code_event_name"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        valid_event_names = event_node_names(ctx.workspace_path)
        signal_repo = get_default_signal_repository()
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue

                func = getattr(node, "func", None)
                is_attr_call = isinstance(func, ast.Attribute) and getattr(func, "attr", "") == "register_event_handler"
                is_name_call = isinstance(func, ast.Name) and func.id == "register_event_handler"
                if not (is_attr_call or is_name_call):
                    continue

                event_arg_node = None
                positional_args = getattr(node, "args", []) or []
                if positional_args:
                    event_arg_node = positional_args[0]
                else:
                    for keyword in getattr(node, "keywords", []) or []:
                        if keyword.arg in {"event", "event_name"}:
                            event_arg_node = keyword.value
                            break

                if not isinstance(event_arg_node, ast.Constant):
                    continue
                event_value = getattr(event_arg_node, "value", None)
                if not isinstance(event_value, str):
                    continue

                event_name = event_value.strip()
                if not event_name:
                    continue

                # 信号 ID（signal_xxx）作为事件名时放行，由信号系统规则单独校验
                if event_name.startswith("signal_"):
                    continue

                # 显示名称为已知信号名时同样视为合法，解析为 ID 的职责交给信号系统与图解析器。
                if signal_repo.resolve_id_by_name(event_name):
                    continue

                if event_name in valid_event_names:
                    continue

                message = (
                    f"{line_span_text(event_arg_node)}: 事件名 '{event_name}' 不在当前引擎事件节点列表中；"
                    f"请检查是否拼写错误，或改为使用已有事件/信号（例如通过【监听信号】节点绑定信号后使用信号ID）。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        event_arg_node,
                        "CODE_UNKNOWN_EVENT_NAME",
                        message,
                    )
                )

        return issues


class TypeNameRule(ValidationRule):
    """类型名合法性校验：节点图代码中的中文类型注解/节点图变量声明必须使用已支持的数据类型。

    能力：
    - 检查函数体内 AnnAssign 形式的中文字符串类型注解（例如：x: "整数" = ...）
    - 检查文件头 docstring 中“节点图变量：”段落里声明的类型名
    - 类型集合统一来源于：数据类型规则、结构体支持类型、节点库端口类型
    """

    rule_id = "engine_code_type_name"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        allowed_types = _get_allowed_type_names(ctx.workspace_path)
        issues: List[EngineIssue] = []

        # 1) 代码级 GRAPH_VARIABLES 中的图变量类型检查
        issues.extend(
            self._check_code_graph_var_types(
                tree,
                file_path,
                allowed_types,
            )
        )

        # 2) 函数体内 AnnAssign 的中文字符串类型注解检查
        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.AnnAssign):
                    continue
                annotation = getattr(node, "annotation", None)
                if not (
                    isinstance(annotation, ast.Constant)
                    and isinstance(getattr(annotation, "value", None), str)
                ):
                    continue
                type_name = str(annotation.value).strip()
                if not type_name:
                    continue

                is_typed_dict, key_type_name, value_type_name = _parse_typed_dict_alias(
                    type_name
                )
                if is_typed_dict:
                    if key_type_name in allowed_types and value_type_name in allowed_types:
                        continue

                if type_name in allowed_types:
                    continue

                target = getattr(node, "target", None)
                var_name = getattr(target, "id", "") if isinstance(target, ast.Name) else ""
                var_label = f"变量『{var_name}』" if var_name else "该变量"
                message = (
                    f"{line_span_text(node)}: {var_label}使用了未知类型名『{type_name}』；"
                    "请使用节点图支持的数据类型（例如：整数、字符串、布尔值、实体、结构体等），"
                    "或在类型配置与节点定义中新增该类型后再使用。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_UNKNOWN_TYPE_NAME",
                        message,
                    )
                )

        return issues

    def _check_docstring_graph_var_types(
        self,
        doc: str,
        file_path: Path,
        allowed_types: Set[str],
        at_node: ast.AST,
    ) -> List[EngineIssue]:
        """解析文件头注释中的“节点图变量：”段落并校验每个变量声明的类型名。"""
        lines = [ln.strip() for ln in doc.splitlines()]
        in_vars_block = False
        issues: List[EngineIssue] = []

        for line in lines:
            if not in_vars_block:
                if line.startswith("节点图变量") or line.startswith("graph_variables"):
                    in_vars_block = True
                continue

            if not line:
                continue

            if not line.startswith("-"):
                # 一旦离开以 "-" 开头的列表段落，就停止解析节点图变量部分
                break

            entry = line[1:].strip()
            entry = entry.replace("[对外暴露]", "").strip()
            if ":" not in entry:
                continue

            name_part, tail = entry.split(":", 1)
            var_name = name_part.strip().split()[0]
            type_and_default = tail.strip()
            if not type_and_default:
                continue

            type_text = type_and_default
            if "=" in type_text:
                type_text = type_text.split("=", 1)[0].strip()
            # 去掉可能跟随在类型名后的说明，例如 "[仅作为结构体字段的镜像]" 等
            if "[" in type_text:
                type_text = type_text.split("[", 1)[0].strip()

            if not type_text:
                continue
            if type_text in allowed_types:
                continue

            message = (
                f"节点图变量『{var_name}』在文件头声明中使用了未知类型名『{type_text}』；"
                "请使用节点图支持的数据类型（例如：整数、字符串、布尔值、实体、结构体等），"
                "或在类型配置与节点定义中新增该类型后再使用。"
            )
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    at_node,
                    "DOC_UNKNOWN_TYPE_NAME",
                    message,
                )
            )

        return issues

    def _check_code_graph_var_types(
        self,
        tree: ast.Module,
        file_path: Path,
        allowed_types: Set[str],
    ) -> List[EngineIssue]:
        """检查代码级 GRAPH_VARIABLES 声明中的图变量类型名。"""
        issues: List[EngineIssue] = []
        variables = extract_graph_variables_from_ast(tree)
        if not variables:
            return issues

        anchor_node: ast.AST = tree
        if tree.body:
            anchor_node = tree.body[0]

        for entry in variables:
            name_value = entry.get("name")
            type_value = entry.get("variable_type")
            if not isinstance(name_value, str) or not isinstance(type_value, str):
                continue

            var_name = name_value.strip()
            type_name = type_value.strip()
            if not var_name or not type_name:
                continue

            is_typed_dict, key_type_name, value_type_name = _parse_typed_dict_alias(
                type_name
            )
            if is_typed_dict:
                if key_type_name in allowed_types and value_type_name in allowed_types:
                    continue

            if type_name in allowed_types:
                continue

            message = (
                f"节点图变量『{var_name}』在 GRAPH_VARIABLES 声明中使用了未知类型名『{type_name}』；"
                "请使用节点图支持的数据类型（例如：整数、字符串、布尔值、实体、结构体等），"
                "或在类型配置与节点定义中新增该类型后再使用。"
            )
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    anchor_node,
                    "CODE_UNKNOWN_TYPE_NAME",
                    message,
                )
            )

        return issues


# ========== 共享辅助函数 ==========

def _is_boolean_expr(expr: ast.expr, boolean_funcs: Set[str], bool_vars_assigned: Set[str]) -> bool:
    """判断表达式是否为布尔类型"""
    # True/False
    if isinstance(expr, ast.Constant):
        return isinstance(getattr(expr, "value", None), bool)
    # 变量：要求来自布尔来源
    if isinstance(expr, ast.Name):
        return expr.id in bool_vars_assigned
    # 调用：要求布尔函数
    if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
        return expr.func.id in boolean_funcs
    # not X
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _is_boolean_expr(expr.operand, boolean_funcs, bool_vars_assigned)
    # X and Y / X or Y
    if isinstance(expr, ast.BoolOp):
        values = getattr(expr, "values", [])
        if not values:
            return False
        return all(_is_boolean_expr(v, boolean_funcs, bool_vars_assigned) for v in values)
    # 比较表达式
    if isinstance(expr, ast.Compare):
        return True
    return False


def _contains_inline_compare(expr: ast.expr) -> bool:
    """判断表达式内是否存在 Python 比较（==, !=, is, in 等）。"""
    for inner in ast.walk(expr):
        if isinstance(inner, ast.Compare):
            return True
    return False


def _is_literal_expression(expr: ast.AST | None) -> bool:
    """判断表达式是否是纯字面量（含正负号包裹）。"""
    if expr is None:
        return False
    if isinstance(expr, ast.Constant):
        if getattr(expr, "value", None) is None:
            return False
        return True
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.USub, ast.UAdd)) and isinstance(expr.operand, ast.Constant):
        return True
    return False

