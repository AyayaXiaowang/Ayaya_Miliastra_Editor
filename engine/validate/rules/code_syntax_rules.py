"""
代码语法规范规则：禁止使用Python原生语法（列表/字典字面量、f-string、lambda、方法调用等）
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.utils.composite_instance_utils import collect_composite_instance_aliases
from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import (
    get_cached_module,
    build_parent_map,
    line_span_text,
    iter_class_methods,
    create_rule_issue,
)


class NoListDictLiteralRule(ValidationRule):
    """禁止在节点图中直接使用列表/字典字面量（应使用对应节点）。"""

    rule_id = "engine_code_no_list_dict_literal"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []
        parent_map = build_parent_map(tree)

        # 1) 类方法内部：禁止列表/字典字面量（包括出现在函数调用参数等任意表达式位置）
        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if isinstance(node, ast.List):
                    parent = parent_map.get(node)
                    if isinstance(parent, (ast.List, ast.Dict)):
                        continue
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_NO_LIST_LITERAL",
                            f"{line_span_text(node)}: 禁止使用列表字面量 []，请使用【拼装列表】节点",
                        )
                    )
                    continue

                if isinstance(node, ast.Dict):
                    parent = parent_map.get(node)
                    if isinstance(parent, (ast.List, ast.Dict)):
                        continue
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_NO_DICT_LITERAL",
                            f"{line_span_text(node)}: 禁止使用字典字面量 {{}}, 请使用【建立字典】节点",
                        )
                    )

        # 2) 模块顶层：同样禁止使用列表/字典字面量声明常量（包括出现在赋值右侧表达式内部的情况）
        for top_level_statement in tree.body:
            # 特例放行：GRAPH_VARIABLES 顶层声明允许使用列表字面量承载 GraphVariableConfig 清单
            if isinstance(top_level_statement, ast.AnnAssign):
                target = getattr(top_level_statement, "target", None)
                if isinstance(target, ast.Name) and target.id == "GRAPH_VARIABLES":
                    continue

            for node in ast.walk(top_level_statement):
                if isinstance(node, ast.List):
                    parent = parent_map.get(node)
                    if isinstance(parent, (ast.List, ast.Dict)):
                        continue
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_NO_LIST_LITERAL",
                            f"{line_span_text(node)}: 禁止使用列表字面量 []，请使用【拼装列表】节点",
                        )
                    )
                    continue

                if isinstance(node, ast.Dict):
                    parent = parent_map.get(node)
                    if isinstance(parent, (ast.List, ast.Dict)):
                        continue
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_NO_DICT_LITERAL",
                            f"{line_span_text(node)}: 禁止使用字典字面量 {{}}, 请使用【建立字典】节点",
                        )
                    )

        return issues


class NoFStringLambdaEnumerateRule(ValidationRule):
    """禁止 f-string、lambda 与 enumerate(...)。"""

    rule_id = "engine_code_no_fstring_lambda_enumerate"
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
                if isinstance(node, ast.JoinedStr):
                    issues.append(create_rule_issue(self, file_path, node, "CODE_NO_FSTRING",
                                              f"{line_span_text(node)}: 禁止使用 f-string，节点图不支持字符串拼接"))
                if isinstance(node, ast.Lambda):
                    issues.append(create_rule_issue(self, file_path, node, "CODE_NO_LAMBDA",
                                              f"{line_span_text(node)}: 禁止使用 lambda；请将比较/排序键等逻辑改为节点表达"))
                if isinstance(node, ast.Call):
                    func = getattr(node, "func", None)
                    if isinstance(func, ast.Name) and func.id == "enumerate":
                        issues.append(create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_NO_ENUMERATE",
                            f"{line_span_text(node)}: 禁止使用 enumerate(...)；"
                            f"建议：使用 for 循环与独立的『整数』计数变量，"
                            f"或先用【拼装列表】构造列表再直接迭代（迭代变量类型即为元素基础类型）"
                        ))

        return issues


class MatchCaseLiteralPatternRule(ValidationRule):
    """限制 match/case 的 case 模式必须为字面量（或由字面量组成的 `|` 组合），避免解析器无法静态解析。

    允许：
    - case "xxx" / case 0 / case True / case None
    - case "a" | "b"（所有分支均为字面量）
    - case _（通配）

    禁止：
    - case 变量名
    - case self.xxx
    - case 任意表达式（Call/BinOp/Attribute/...）
    - case [a, b] / case {"k": v} 等结构模式
    """

    rule_id = "engine_code_match_case_pattern_must_be_literal"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Match):
                continue
            for one_case in getattr(node, "cases", []) or []:
                pattern = getattr(one_case, "pattern", None)
                if pattern is None:
                    continue
                if _is_allowed_match_case_pattern(pattern):
                    continue
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        pattern,
                        "CODE_MATCH_CASE_PATTERN_NOT_LITERAL",
                        f"{line_span_text(pattern)}: match/case 的 case 模式必须使用字面量（例如 case \"xxx\"/case 0/case _，或字面量 `|` 组合）；"
                        f"禁止使用运行期变量/属性/表达式（例如 case self.xxx 或 case 变量名），否则节点图解析器无法解析",
                    )
                )

        return issues


class NoMethodNestedCallsRule(ValidationRule):
    """禁止方法调用与嵌套方法调用（例如 obj.append()/dct.get()/x.items() 等）。"""

    rule_id = "engine_code_no_method_nested_calls"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []
        parent_map = build_parent_map(tree)
        allowed_full_names = set((ctx.config or {}).get("ALLOW_METHOD_CALLS", []) or [])
        allowed_method_names = set((ctx.config or {}).get("ALLOW_METHOD_CALL_NAMES", []) or [])
        
        # 提取复合节点实例属性（从 __init__ 中）
        composite_instances = collect_composite_instance_aliases(tree)

        for _, method in iter_class_methods(tree):
            current_method_name = getattr(method, "name", "")
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Attribute):
                    continue
                full_name = _format_attr_chain(func)
                simple_name = getattr(func, "attr", "")

                # 配置型白名单放行（例如事件注册 register_event_handler）
                # 1) 完整链路名匹配（如 self.game.register_event_handler）
                # 2) 方法名匹配（只按末级名，如 register_event_handler）
                # 3) 方法级特殊放行：在 register_handlers 中的事件注册调用
                if (full_name in allowed_full_names) or (simple_name in allowed_method_names):
                    continue
                if (current_method_name == "register_handlers") and (simple_name in {"register_event_handler"}):
                    continue
                
                # 4) 复合节点实例方法调用放行：self.xxx.yyy() 其中 xxx 是复合节点实例
                if _is_composite_instance_method_call(func, composite_instances):
                    continue
                
                # 顶层调用：Expr(value=Call) 或 Assign(value=Call)
                parent = parent_map.get(node)
                is_top_expr = isinstance(parent, ast.Expr) and getattr(parent, "value", None) is node
                is_top_assign = isinstance(parent, ast.Assign) and getattr(parent, "value", None) is node
                if is_top_expr or is_top_assign:
                    issues.append(create_rule_issue(self, file_path, node, "CODE_NO_METHOD_CALL",
                                              f"{line_span_text(node)}: 禁止使用方法调用 {_format_attr_chain(func)}()，请使用节点替代"))
                else:
                    issues.append(create_rule_issue(self, file_path, node, "CODE_NO_NESTED_METHOD_CALL",
                                              f"{line_span_text(node)}: 禁止在表达式中嵌套方法调用 {_format_attr_chain(func)}()，请使用节点拆解为多步"))

        return issues


# ========== 共享辅助函数 ==========

def _is_composite_instance_method_call(func: ast.Attribute, composite_instances: set) -> bool:
    """检查是否是复合节点实例的方法调用
    
    检查形式：self.xxx.yyy() 其中 xxx 在 composite_instances 中
    
    Args:
        func: 方法调用的 func 节点
        composite_instances: 复合节点实例属性名集合
        
    Returns:
        如果是复合节点实例的方法调用，返回 True
    """
    if not isinstance(func.value, ast.Attribute):
        return False
    
    obj = func.value
    if not isinstance(obj.value, ast.Name) or obj.value.id != 'self':
        return False
    
    instance_attr = obj.attr
    return instance_attr in composite_instances


def _is_allowed_match_case_pattern(pattern: ast.AST) -> bool:
    """判断 case pattern 是否为解析器可静态处理的“字面量模式”。

    说明：Python 的 match/case 模式语法非常丰富，但节点图解析器只支持最常见的“常量匹配”与 `_` 通配。
    """
    # case _ : MatchAs(name=None, pattern=None)
    if isinstance(pattern, ast.MatchAs) and getattr(pattern, "name", None) is None and getattr(pattern, "pattern", None) is None:
        return True

    # case None / case True / case False : MatchSingleton
    if isinstance(pattern, ast.MatchSingleton):
        return True

    # case "xxx" / case 0 : MatchValue(value=Constant(...))
    if isinstance(pattern, ast.MatchValue):
        value_node = getattr(pattern, "value", None)
        return isinstance(value_node, ast.Constant)

    # case "a" | "b" : MatchOr(patterns=[...])
    if isinstance(pattern, ast.MatchOr):
        inner_patterns = getattr(pattern, "patterns", None) or []
        if not inner_patterns:
            return False
        return all(_is_allowed_match_case_pattern(p) for p in inner_patterns)

    return False
def _format_attr_chain(attr: ast.Attribute) -> str:
    """生成 a.b.c 形式的可读字符串"""
    parts: List[str] = []
    cur = attr
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value  # type: ignore
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    parts.reverse()
    return ".".join(parts)


class NoInlineIfInCallRule(ValidationRule):
    """禁止在函数调用参数中使用内联 if（三目）表达式。"""

    rule_id = "engine_code_no_inline_if_in_call"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext):
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                # 位置参数与关键字参数
                arg_exprs = list(getattr(node, "args", []) or [])
                for kw in (getattr(node, "keywords", []) or []):
                    arg_exprs.append(getattr(kw, "value", None))
                # 检测任一参数内是否包含 IfExp（三目）
                for arg_expr in arg_exprs:
                    if arg_expr is None:
                        continue
                    for inner in ast.walk(arg_expr):
                        if isinstance(inner, ast.IfExp):
                            issues.append(EngineIssue(
                                level=self.default_level,
                                category=self.category,
                                code="CODE_NO_INLINE_IF_IN_CALL",
                                message=f"{line_span_text(inner)}: 禁止在函数调用参数中使用内联 if 表达式（X if 条件 else Y）；请将分支逻辑拆解为前置变量/节点，或使用流程分支节点",
                                file=str(file_path),
                                line_span=line_span_text(inner),
                            ))
                            # 同一个参数内多个 IfExp 也只需逐一报告，无需去重
        return issues


class NoInlineArithmeticInRangeRule(ValidationRule):
    """禁止在 range() 参数中使用内联算术运算表达式（如 range(1, x + 1)）。
    
    range() 仅允许在 for 循环的迭代器位置出现，并且其参数必须是简单的变量或常量，
    不能包含内联的加减乘除等算术运算。如需计算上下界，应先使用节点（如【加法运算】）
    计算结果并存入变量，再将该变量传递给 range()。
    """

    rule_id = "engine_code_no_inline_arithmetic_in_range"
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
                # 查找所有的 range() 调用
                if not isinstance(node, ast.Call):
                    continue
                
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name) or func.id != "range":
                    continue
                
                # 检查 range() 的每个参数
                args = list(getattr(node, "args", []) or [])
                for arg in args:
                    if arg is None:
                        continue
                    
                    # 检查参数是否包含算术运算（BinOp）
                    if self._contains_arithmetic(arg):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_NO_INLINE_ARITHMETIC_IN_RANGE",
                                (
                                    f"{line_span_text(node)}: 禁止在 range() 参数中使用内联算术运算（如 x + 1）；"
                                    "请先使用节点（如【加法运算】）计算结果并存入变量，再将该变量传递给 range()"
                                ),
                            )
                        )
                        # 一个 range() 调用只报告一次
                        break

        return issues
    
    def _contains_arithmetic(self, node: ast.AST) -> bool:
        """检查节点树中是否包含算术运算表达式（BinOp）"""
        for child in ast.walk(node):
            if isinstance(child, ast.BinOp):
                return True
        return False