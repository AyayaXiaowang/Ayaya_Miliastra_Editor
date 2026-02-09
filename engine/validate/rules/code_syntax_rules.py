"""
代码语法规范规则：限制 Graph Code 中可使用的 Python 原生语法（容器字面量、f-string、lambda、方法调用等）。

说明：
- 列表相关语法糖（`[...]`、列表下标修改、insert/clear/extend）在类方法体内允许使用，但会在校验阶段被统一改写为等价的节点调用；
- 字典字面量 `{k: v}` **必须显式声明键/值类型**：仅允许以“带别名字典中文类型注解的变量声明”形式出现（例如 `映射: "键类型-值类型字典" = {k: v}` / `映射: "键类型_值类型字典" = {k: v}`）；禁止直接在节点调用入参或其它表达式里内联 `{...}`（会报错 `CODE_DICT_LITERAL_TYPED_ANNOTATION_REQUIRED`）。合法字面量会在校验阶段被统一改写为等价的【拼装字典】节点调用；
- 空列表 `[]`、空字典 `{}` 与超过上限的容器字面量会被视为错误；
- `for x in [...]` 禁止：必须先声明带中文类型注解的列表变量（例如 `列表: "整数列表" = [1,2,3]`），再写为 `for x in 列表:`；
- `for x in {...}` 禁止：节点图 for 循环仅支持遍历“列表变量”，字典遍历需先转为键/值列表再迭代。

新增支持（语法糖归一化）：
- `for 序号, 元素 in enumerate(列表变量):` 允许：会被改写为 `len + range + 下标读取` 的等价节点逻辑；
- `a + b / a - b / a * b / a / b` 允许：会被改写为【加/减/乘/除法运算】节点调用。

额外约定（非允许即禁止）：
- Graph Code/复合节点方法体中，任何会被 IR 静默跳过的语句形态必须在校验阶段直接报错（例如 assert、非调用表达式语句、未被改写的 AugAssign/Delete 等）。
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
from engine.graph.utils.list_literal_rewriter import (
    ListLiteralRewriteIssue,
    rewrite_graph_code_list_literals,
)
from engine.graph.utils.dict_literal_rewriter import (
    DictLiteralRewriteIssue,
    rewrite_graph_code_dict_literals,
)
from engine.graph.utils.syntax_sugar_rewriter import (
    SyntaxSugarRewriteIssue,
    rewrite_graph_code_syntax_sugars,
)
from engine.graph.utils.graph_code_rewrite_config import build_graph_code_rewrite_config
from engine.graph.composite.pin_marker_collector import (
    DATA_IN_FUNCTIONS,
    DATA_OUT_FUNCTIONS,
    FLOW_IN_FUNCTIONS,
    FLOW_OUT_FUNCTIONS,
)
from .node_index import node_function_names, flow_node_names


def _rewrite_config_for_ctx(ctx: ValidationContext):
    return build_graph_code_rewrite_config(is_composite=ctx.is_composite)


class ListLiteralRewriteRule(ValidationRule):
    """列表相关语法糖：在类方法体内允许使用，并在校验入口统一转换为等价的节点调用。

    约定：
    - 禁止空列表 `[]`；
    - 禁止元素数超过 100；
    - `for x in [...]` 禁止：for 的迭代器位置必须是“显式声明带中文类型注解”的列表变量。

    说明：
    - 该规则会**就地更新 ctx.ast_cache**，使后续规则在同一校验流程中看到“已改写”的 AST；
    - 不支持模块/类体顶层列表字面量（无法转换为节点），这类写法会直接报错。
    """

    rule_id = "engine_code_list_literal_rewrite"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        rewrite_config = _rewrite_config_for_ctx(ctx)
        rewritten_tree, rewrite_issues = rewrite_graph_code_list_literals(
            tree,
            max_elements=rewrite_config.max_list_literal_elements,
        )
        ctx.ast_cache[ctx.file_path] = rewritten_tree

        issues: List[EngineIssue] = []
        for rewrite_issue in list(rewrite_issues or []):
            if not isinstance(rewrite_issue, ListLiteralRewriteIssue):
                continue
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    rewrite_issue.node,
                    str(rewrite_issue.code),
                    f"{line_span_text(rewrite_issue.node)}: {rewrite_issue.message}",
                )
            )
        return issues


class SyntaxSugarRewriteRule(ValidationRule):
    """常见 Python 语法糖归一化：在类方法体内允许并自动转换为等价的节点调用。

    目的：
    - 让 Graph Code 可以书写更自然的“读写/比较/逻辑/增量赋值”等表达；
    - 统一转换为节点调用形态，复用后续端口必填、同型输入、布尔条件等规则；
    - 避免 IR 对 Subscript/Compare/BoolOp/AugAssign 等语法不完备导致“缺线/缺数据来源”。

    说明：
    - 该规则会**就地更新 ctx.ast_cache**，使后续规则看到“已改写”的 AST；
    - scope（server/client）会影响部分节点名/端口名映射。
    """

    rule_id = "engine_code_syntax_sugar_rewrite"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        from .ast_utils import infer_graph_scope  # 避免在模块顶层形成循环 import

        scope = infer_graph_scope(ctx)
        rewrite_config = _rewrite_config_for_ctx(ctx)
        rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(
            tree,
            scope=scope,
            enable_shared_composite_sugars=rewrite_config.enable_shared_composite_sugars,
        )
        ctx.ast_cache[ctx.file_path] = rewritten_tree

        issues: List[EngineIssue] = []
        for rewrite_issue in list(rewrite_issues or []):
            if not isinstance(rewrite_issue, SyntaxSugarRewriteIssue):
                continue
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    rewrite_issue.node,
                    str(rewrite_issue.code),
                    f"{line_span_text(rewrite_issue.node)}: {rewrite_issue.message}",
                )
            )
        return issues


def _is_self_game_expr(expr: ast.AST) -> bool:
    if not isinstance(expr, ast.Attribute):
        return False
    value = getattr(expr, "value", None)
    return isinstance(value, ast.Name) and value.id == "self" and expr.attr == "game"


def _looks_like_node_invocation(call_node: ast.Call) -> bool:
    args = list(getattr(call_node, "args", []) or [])
    if not args:
        return False
    return _is_self_game_expr(args[0])


def _is_range_call(call_node: ast.AST) -> bool:
    if not isinstance(call_node, ast.Call):
        return False
    func = getattr(call_node, "func", None)
    return isinstance(func, ast.Name) and func.id == "range"


_COMPOSITE_PIN_MARKER_FUNCTIONS: set[str] = set().union(
    FLOW_IN_FUNCTIONS,
    FLOW_OUT_FUNCTIONS,
    DATA_IN_FUNCTIONS,
    DATA_OUT_FUNCTIONS,
)


class UnsupportedPythonSyntaxRule(ValidationRule):
    """禁止使用解析器/IR 不支持且会导致“静默跳过/缺线”的 Python 语法。

    目标：
    - 对“不支持的语句/表达式”直接报错（而不是让 IR 跳过，导致运行时图不完整）。
    - 对“非节点函数调用”直接报错：Graph Code 方法体只能调用节点函数（含语法糖改写后的节点调用）。

    适用范围：
    - 普通节点图：仅检查 `on_...` 事件方法体；
    - 复合节点类格式：检查所有带装饰器的方法体（排除 __xx__ 魔术方法）。
    """

    rule_id = "engine_code_unsupported_python_syntax"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        parent_map = build_parent_map(tree)

        # scope 会影响可调用节点集合（server/client 同名节点可能不同）
        from .ast_utils import infer_graph_scope  # 避免在模块顶层形成循环 import

        scope = infer_graph_scope(ctx)
        known_node_names = node_function_names(ctx.workspace_path, scope)
        flow_node_func_names = flow_node_names(ctx.workspace_path, scope)

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            method_name = getattr(method, "name", "")
            if ctx.is_composite:
                if method_name.startswith("__"):
                    continue
                decorator_list = list(getattr(method, "decorator_list", []) or [])
                if not decorator_list:
                    continue
            else:
                if not method_name.startswith("on_"):
                    continue

            for statement in list(getattr(method, "body", []) or []):
                for node in ast.walk(statement):
                    # ===== 0) 非允许即禁止：阻断 IR 静默跳过 =====
                    #
                    # 说明：IR 的 parse_method_body 只会建模少量 statement；其余语句若不在此处硬禁止，
                    # 会造成“源码写了但图里没有”的隐性问题。

                    # 0.1) 明确禁止：assert / del / global / nonlocal
                    if isinstance(node, ast.Assert):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_ASSERT_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 assert；节点图不会执行 Python 断言语义。",
                            )
                        )
                        continue

                    if isinstance(node, ast.Delete):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_DELETE_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 del 语句；节点图不支持删除变量/属性等语义。"
                                "若要删除列表/字典的下标，请使用对应节点或语法糖（del 目标列表[序号] / del 目标字典[键]）。",
                            )
                        )
                        continue

                    if isinstance(node, (ast.Global, ast.Nonlocal)):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_SCOPE_STATEMENT_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 global/nonlocal；节点图不支持 Python 作用域声明语义。",
                            )
                        )
                        continue

                    # 0.2) 明确禁止：残留 AugAssign（允许的形态必须已被 SyntaxSugarRewriteRule 改写为 Assign）
                    if isinstance(node, ast.AugAssign):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_AUG_ASSIGN_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 该增量赋值写法不受支持；"
                                "仅允许对变量名使用 +=, -=, *=, /=（且会自动改写为节点调用）。",
                            )
                        )
                        continue

                    # 0.3) 明确禁止：海象运算符 / 三目表达式（会被 IR 静默跳过）
                    if isinstance(node, ast.NamedExpr):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_NAMED_EXPR_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用海象运算符 (:=)；请拆分为单独赋值语句与后续使用。",
                            )
                        )
                        continue

                    if isinstance(node, ast.IfExp):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_IF_EXP_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用三目表达式（X if 条件 else Y）；"
                                "请改写为 if 语句并用变量承接结果（或拆成两条节点逻辑）。",
                            )
                        )
                        continue

                    # 0.5) 禁止“非调用表达式语句”（同样会被 IR 静默跳过）
                    if isinstance(node, ast.Expr):
                        expr_value = getattr(node, "value", None)
                        if isinstance(expr_value, ast.Call):
                            func = getattr(expr_value, "func", None)
                            if isinstance(func, ast.Name):
                                call_name = func.id
                                # 纯数据节点以“裸表达式语句”出现会被 IR 静默跳过（无赋值、无消费）：
                                # 强制要求：只有“流程/执行类节点”允许以语句形式出现；纯数据节点必须赋值给变量。
                                if (call_name in known_node_names) and (call_name not in flow_node_func_names):
                                    issues.append(
                                        create_rule_issue(
                                            self,
                                            file_path,
                                            node,
                                            "CODE_DATA_NODE_CALL_STATEMENT_FORBIDDEN",
                                            f"{line_span_text(node)}: 禁止将纯数据节点『{call_name}(...)』作为独立语句调用；"
                                            "该写法在节点图中没有流程语义且会被解析器静默跳过。"
                                            "请将其结果赋值给变量后再使用，或改用对应的执行/流程节点。",
                                        )
                                    )
                        else:
                            # 允许方法 docstring：作为注释用途，不参与节点图语义（等价于注释，不应报错）
                            if isinstance(expr_value, ast.Constant) and isinstance(getattr(expr_value, "value", None), str):
                                parent_stmt = parent_map.get(node)
                                if isinstance(parent_stmt, ast.FunctionDef):
                                    method_body = list(getattr(parent_stmt, "body", []) or [])
                                    if method_body and method_body[0] is node:
                                        continue
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    node,
                                    "CODE_EXPR_STATEMENT_NOT_SUPPORTED",
                                    f"{line_span_text(node)}: 禁止使用非调用的表达式语句（例如孤立的变量/常量/表达式）；"
                                    "节点图只支持以『节点调用』作为有效语句。",
                                )
                            )
                        # 仍然允许继续扫描子节点（例如其中包含的非法调用），避免漏报
                        continue

                    # ===== 1) 明确不支持的语句 =====
                    if isinstance(node, ast.While):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_WHILE_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 while 语句；当前解析器不支持将 while 转换为节点图。"
                                "请改用 `for i in range(...)` 或 `for x in 列表变量:` + `break` 的方式表达循环。",
                            )
                        )
                        continue

                    if isinstance(node, ast.Continue):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_CONTINUE_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 continue；节点图循环暂不支持 continue 的跳转语义。"
                                "请改写为“if 条件: pass else: <本轮后续逻辑>”的结构，或拆分为多个循环。",
                            )
                        )
                        continue

                    if isinstance(node, ast.For):
                        orelse = list(getattr(node, "orelse", []) or [])
                        if orelse:
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    node,
                                    "CODE_FOR_ELSE_NOT_SUPPORTED",
                                    f"{line_span_text(node)}: 禁止使用 for...else；当前解析器不支持 for 的 else 分支。"
                                    "请改写为：循环内设置显式标记变量，循环后再用 if 判断是否需要执行“else 逻辑”。",
                                )
                            )

                        iter_expr = getattr(node, "iter", None)
                        if isinstance(iter_expr, (ast.List, ast.Dict)):
                            # 列表/字典字面量在 for iter 的限制由专用 rewriter 负责给出更明确提示。
                            continue
                        if isinstance(iter_expr, ast.Name) or _is_range_call(iter_expr):
                            continue
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_FOR_ITER_UNSUPPORTED",
                                f"{line_span_text(node)}: for 循环的迭代器仅支持 `range(...)` 或“列表变量名”。"
                                "禁止使用表达式/调用/属性/下标等作为迭代器；请先赋值到带中文类型注解的列表变量，再进行迭代。",
                            )
                        )
                        continue

                    if isinstance(node, ast.Try):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_TRY_EXCEPT_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 try/except/finally；节点图不支持异常捕获语义。"
                                "请改用显式分支/节点逻辑处理错误路径。",
                            )
                        )
                        continue

                    if isinstance(node, ast.With):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_WITH_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 with；节点图不支持上下文管理器语义。",
                            )
                        )
                        continue

                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_IMPORT_IN_METHOD_FORBIDDEN",
                                f"{line_span_text(node)}: 禁止在节点图方法体内使用 import；"
                                "请将 import 放到模块顶层（通常由 `_prelude` 负责注入）。",
                            )
                        )
                        continue

                    if isinstance(node, ast.Raise):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_RAISE_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 raise；节点图不会执行 Python 异常抛出语义。"
                                "如需提前结束流程，请使用 return 或改写为分支控制流。",
                            )
                        )
                        continue

                    # ===== 1.1) 兜底：禁止 IR 会静默跳过的“未知语句类型” =====
                    #
                    # 放在“显式禁用语句”之后，避免吞掉 while/try/with 等更具体的错误码。
                    if isinstance(node, ast.stmt) and not isinstance(
                        node,
                        (
                            ast.Assign,
                            ast.AnnAssign,
                            ast.Expr,
                            ast.If,
                            ast.Match,
                            ast.For,
                            ast.Break,
                            ast.Return,
                            ast.Pass,
                        ),
                    ):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_STATEMENT_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 该 Python 语句在节点图中不受支持（非允许即禁止）；"
                                "请改写为节点调用/if/match/for 等受支持结构，或拆分为多步节点逻辑。",
                            )
                        )
                        continue

                    # ===== 2) 不支持的表达式形态（会导致 IR 无法建模）=====
                    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_COMPREHENSION_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用推导式（list/dict/set/generator comprehension）；"
                                "请改写为显式 for 循环，并使用【拼装列表/拼装字典】等节点逐步构造容器。",
                            )
                        )
                        continue

                    if isinstance(node, (ast.Yield, ast.YieldFrom)):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_YIELD_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 yield；节点图不支持生成器语义。",
                            )
                        )
                        continue

                    if isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith, ast.AsyncFunctionDef)):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_ASYNC_NOT_SUPPORTED",
                                f"{line_span_text(node)}: 禁止使用 async/await；节点图不支持异步语义。",
                            )
                        )
                        continue

                    # ===== 3) 禁止非节点函数调用（避免 IR 静默跳过）=====
                    if isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name):
                        call_name = node.func.id

                        # range(...)：仅允许用于 for 的 iter 位置
                        if call_name == "range":
                            parent = parent_map.get(node)
                            if isinstance(parent, ast.For) and getattr(parent, "iter", None) is node:
                                continue
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    node,
                                    "CODE_RANGE_CALL_CONTEXT_FORBIDDEN",
                                    f"{line_span_text(node)}: range(...) 仅允许出现在 for 循环的迭代器位置（`for i in range(...):`）。"
                                    "请不要在其他位置调用 range(...)。",
                                )
                            )
                            continue

                        # 复合节点：允许引脚声明辅助函数（pure no-op），这些不是“节点函数调用”
                        if ctx.is_composite and (call_name in _COMPOSITE_PIN_MARKER_FUNCTIONS):
                            continue

                        # 已知节点函数名：允许（是否漏传 self.game 由 NodeCallGameRequiredRule 负责）
                        if call_name in known_node_names:
                            continue

                        # 形如 `未知函数(self.game, ...)`：更像“节点名拼写错误/不存在”
                        if _looks_like_node_invocation(node):
                            # 普通节点图会由 UnknownNodeCallRule 统一上报，避免重复报错；
                            # 复合节点规则集默认不包含 UnknownNodeCallRule，因此在此补齐。
                            if ctx.is_composite:
                                issues.append(
                                    create_rule_issue(
                                        self,
                                        file_path,
                                        node,
                                        "CODE_UNKNOWN_NODE_CALL",
                                        f"{line_span_text(node)}: 发现疑似节点调用『{call_name}(self.game, ...)』，但『{call_name}』不在当前作用域节点库中；"
                                        "请检查节点名是否拼写错误或选择一个已有节点替代。",
                                    )
                                )
                            continue

                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_PYTHON_FUNCTION_CALL_FORBIDDEN",
                                f"{line_span_text(node)}: 禁止在节点图方法体内调用 Python 函数『{call_name}(...)』；"
                                "节点图方法体只能调用节点函数（或由语法糖改写得到的节点调用）。",
                            )
                        )

        return issues


class DictLiteralRewriteRule(ValidationRule):
    """字典字面量语法糖：将“显式注解的字典字面量”改写为【拼装字典】节点调用。

    约定：
    - 禁止空字典 `{}`；
    - 禁止键值对数量超过 50；
    - 禁止 `{**d}` 这类字典展开语法；
    - `for x in {...}` 禁止：节点图 for 循环仅支持遍历“列表变量”，字典遍历应先转为键/值列表再迭代。
    - 禁止在节点调用入参或其它表达式里直接内联 `{...}`：字典必须先落到变量并显式声明别名字典类型（键类型-值类型字典 / 键类型_值类型字典）。

    说明：
    - 该规则会**就地更新 ctx.ast_cache**，使后续规则在同一校验流程中看到“已改写”的 AST；
    - 不支持模块/类体顶层字典字面量（无法转换为节点），这类写法会直接报错。
    """

    rule_id = "engine_code_dict_literal_rewrite"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        rewrite_config = _rewrite_config_for_ctx(ctx)
        rewritten_tree, rewrite_issues = rewrite_graph_code_dict_literals(
            tree,
            max_pairs=rewrite_config.max_dict_literal_pairs,
        )
        ctx.ast_cache[ctx.file_path] = rewritten_tree

        issues: List[EngineIssue] = []
        for rewrite_issue in list(rewrite_issues or []):
            if not isinstance(rewrite_issue, DictLiteralRewriteIssue):
                continue
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    rewrite_issue.node,
                    str(rewrite_issue.code),
                    f"{line_span_text(rewrite_issue.node)}: {rewrite_issue.message}",
                )
            )
        return issues


class NoFStringLambdaEnumerateRule(ValidationRule):
    """禁止 f-string 与 lambda。

    说明：
    - enumerate(...) 不再由本规则直接禁止：`for 序号, 元素 in enumerate(列表变量):` 会在语法糖归一化阶段被改写；
    - enumerate(...) 的其余用法会被 `UnsupportedPythonSyntaxRule` 作为“Python 函数调用”直接报错。
    """

    rule_id = "engine_code_no_fstring_lambda_enumerate"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
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
        if ctx.file_path is None:
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
        if ctx.file_path is None:
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
    """限制 range() 的参数形态，避免 IR 静默降级。

    约定：
    - range() 仅允许出现在 for 循环的 iter 位置（其余上下文由 UnsupportedPythonSyntaxRule 报错）；
    - range() 仅支持 1 或 2 个位置参数（不支持 step 参数）；
    - 每个参数必须是“简单变量名或数值常量”（含一元 +/- 数值常量），禁止 Call/BinOp/Attribute/Subscript 等表达式。

    目的：
    - IR 的 range 参数提取是静态的：仅能识别常量或变量名；
    - 若放行复杂表达式，会在解析阶段被静默当作 0，造成“源码写了但图语义变了”的隐性坑。
    """

    rule_id = "engine_code_no_inline_arithmetic_in_range"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        parent_map = build_parent_map(tree)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                # 查找所有的 range() 调用
                if not isinstance(node, ast.Call):
                    continue
                
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name) or func.id != "range":
                    continue

                # 仅检查 for iter 中的 range(...)；其余上下文由 UnsupportedPythonSyntaxRule 报错
                parent = parent_map.get(node)
                if not (isinstance(parent, ast.For) and getattr(parent, "iter", None) is node):
                    continue

                keywords = list(getattr(node, "keywords", []) or [])
                if keywords:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_RANGE_CALL_KEYWORDS_FORBIDDEN",
                            f"{line_span_text(node)}: range(...) 禁止使用关键字参数；请使用位置参数 range(终止值) 或 range(起始值, 终止值)。",
                        )
                    )
                    continue

                args = list(getattr(node, "args", []) or [])
                if len(args) not in {1, 2}:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_RANGE_CALL_ARGS_COUNT_INVALID",
                            f"{line_span_text(node)}: range(...) 仅支持 1 或 2 个位置参数（不支持 step 参数）；"
                            "请改写为 `for i in range(终止值):` 或 `for i in range(起始值, 终止值):`。",
                        )
                    )
                    continue

                for arg in args:
                    if self._is_allowed_range_arg(arg):
                        continue
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            arg,
                            "CODE_RANGE_ARG_NOT_SIMPLE",
                            f"{line_span_text(arg)}: range(...) 参数必须是简单变量名或数值常量；"
                            "禁止在 range 参数中写调用/下标/属性/算术表达式。"
                            "如需计算上下界，请先用节点计算并存入变量，再传给 range()。",
                        )
                    )
                    # 一个 range() 调用只报告一次（避免刷屏）
                    break

        return issues

    def _is_allowed_range_arg(self, node: ast.AST) -> bool:
        # 变量名
        if isinstance(node, ast.Name) and isinstance(getattr(node, "id", None), str) and node.id:
            return True
        # 数值常量
        if isinstance(node, ast.Constant) and isinstance(getattr(node, "value", None), (int, float)):
            return True
        # 一元 +/- 数值常量（例如 -1 / +1.0）
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(getattr(node, "op", None), (ast.USub, ast.UAdd))
            and isinstance(getattr(node, "operand", None), ast.Constant)
            and isinstance(getattr(node.operand, "value", None), (int, float))
        ):
            return True
        return False