from __future__ import annotations

import ast
from typing import Dict, List, Optional, Tuple

from .syntax_sugar_rewriter_ast_helpers import _build_self_game_expr, _is_dict_var_name
from .syntax_sugar_rewriter_constants import (
    ABS_NODE_CALL_NAME,
    DICT_LENGTH_NODE_CALL_NAME,
    INTEGER_ROUNDING_NODE_CALL_NAME,
    LIST_LENGTH_NODE_CALL_NAME,
    LIST_MAX_VALUE_NODE_CALL_NAME,
    LIST_MIN_VALUE_NODE_CALL_NAME,
    ROUNDING_MODE_CEIL,
    ROUNDING_MODE_FLOOR,
    ROUNDING_MODE_ROUND,
    TYPE_CONVERSION_NODE_CALL_NAME,
    _list_length_list_port_name,
)
from .syntax_sugar_rewriter_issue import SyntaxSugarRewriteIssue


def try_rewrite_builtin_call(
    transformer: object,
    *,
    node: ast.Call,
    builtin_name: str,
    positional_args: List[ast.expr],
    keywords: List[ast.keyword],
) -> Optional[ast.AST]:
    """对 Name 形式的 Call 做语法糖改写（len/abs/max/min/类型转换/共享复合等）。"""
    # ------------------------------------------------------------------
    # 共享复合节点语法糖（扩展）：允许“直接写复合节点名(...)”
    # ------------------------------------------------------------------
    # 说明：
    # - 仅在普通节点图启用（enable_shared_composite_sugars=True）；复合节点文件内部默认关闭，避免“复合内嵌套复合”。
    # - 仅 server 作用域。
    # - 形如：
    #     结果 = 整数列表_按布尔掩码过滤(输入列表=列表, 保留条件列表=条件列表)
    #   会被改写为：
    #     结果 = self._共享复合_整数列表_按布尔掩码过滤.过滤(...)
    #   并自动向 __init__ 注入实例声明：
    #     self._共享复合_整数列表_按布尔掩码过滤 = 整数列表_按布尔掩码过滤(self.game, self.owner_entity)
    if transformer.enable_shared_composite_sugars and transformer.scope == "server":
        rewritten_shared = try_rewrite_shared_composite_direct_call(
            transformer,
            func_name=builtin_name,
            positional_args=positional_args,
            keywords=keywords,
            source_node=node,
        )
        if rewritten_shared is not None:
            return rewritten_shared

    # dict(zip(keys, values))：仅 server 支持（等价映射【建立字典】）
    if builtin_name == "dict":
        if len(positional_args) == 1 and not keywords:
            zip_call = positional_args[0]
            if isinstance(zip_call, ast.Call):
                zip_func = getattr(zip_call, "func", None)
                if isinstance(zip_func, ast.Name) and zip_func.id == "zip":
                    zip_args = list(getattr(zip_call, "args", []) or [])
                    zip_keywords = list(getattr(zip_call, "keywords", []) or [])
                    if zip_keywords:
                        transformer.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_DICT_ZIP_CALL_KEYWORDS_FORBIDDEN",
                                message="dict(zip(...)) 语法糖不支持 zip(...) 关键字参数写法；请使用位置参数 `zip(键列表, 值列表)`。",
                                node=node,
                            )
                        )
                        return node
                    if any(isinstance(arg, ast.Starred) for arg in zip_args):
                        transformer.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_DICT_ZIP_CALL_UNPACK_FORBIDDEN",
                                message="dict(zip(...)) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                node=node,
                            )
                        )
                        return node
                    if len(zip_args) != 2:
                        transformer.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_DICT_ZIP_CALL_ARGS_INVALID",
                                message="dict(zip(...)) 语法糖仅支持 `dict(zip(键列表, 值列表))`（zip 必须恰好 2 个位置参数）。",
                                node=node,
                            )
                        )
                        return node

                    if transformer.scope != "server":
                        transformer.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_DICT_ZIP_NOT_SUPPORTED_IN_CLIENT",
                                message="dict(zip(...)) 语法糖仅在 server 作用域支持（会改写为【建立字典】）。client 侧缺少等价节点。",
                                node=node,
                            )
                        )
                        return node

                    keys_expr, values_expr = zip_args
                    call_node = ast.Call(
                        func=ast.Name(id="建立字典", ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[
                            ast.keyword(arg="键列表", value=keys_expr),
                            ast.keyword(arg="值列表", value=values_expr),
                        ],
                    )
                    ast.copy_location(call_node, node)
                    call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                    return call_node

    if builtin_name == "pow":
        if transformer.scope != "server":
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_POW_NOT_SUPPORTED_IN_CLIENT",
                    message="pow(a, b) 语法糖仅在 server 作用域支持（会改写为【幂运算】）。client 侧缺少等价节点。",
                    node=node,
                )
            )
            return node
        if keywords:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_POW_CALL_KEYWORDS_FORBIDDEN",
                    message="pow(a, b) 语法糖不支持关键字参数；请使用位置参数写法（pow(a, b)）。",
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_POW_CALL_UNPACK_FORBIDDEN",
                    message="pow(a, b) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                    node=node,
                )
            )
            return node
        if len(positional_args) != 2:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_POW_CALL_ARGS_INVALID",
                    message="pow(a, b) 语法糖仅支持 2 个位置参数（底数, 指数）。",
                    node=node,
                )
            )
            return node
        base_expr, exponent_expr = positional_args
        call_node = ast.Call(
            func=ast.Name(id="幂运算", ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="底数", value=base_expr),
                ast.keyword(arg="指数", value=exponent_expr),
            ],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    if builtin_name == "len":
        if keywords or len(positional_args) != 1:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_LEN_CALL_ARGS_INVALID",
                    message="len(...) 仅支持 1 个位置参数，且不支持关键字参数写法",
                    node=node,
                )
            )
            return node

        container_expr = positional_args[0]
        if transformer.scope == "server" and isinstance(container_expr, ast.Name) and _is_dict_var_name(
            container_expr.id,
            transformer.dict_var_names,
        ):
            call_node = ast.Call(
                func=ast.Name(id=DICT_LENGTH_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="字典", value=ast.Name(id=container_expr.id, ctx=ast.Load()))],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        list_port_name = _list_length_list_port_name(transformer.scope)
        call_node = ast.Call(
            func=ast.Name(id=LIST_LENGTH_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[ast.keyword(arg=list_port_name, value=container_expr)],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    # 共享复合节点语法糖（仅普通节点图启用；复合节点内部禁止嵌套其它复合节点）
    # - any(布尔值列表变量) -> self._shared_comp_bool_any.计算(输入列表=变量)
    # - all(布尔值列表变量) -> self._shared_comp_bool_all.计算(输入列表=变量)
    # - sum(整数列表变量) -> self._shared_comp_int_sum.计算(输入列表=变量)
    if transformer.enable_shared_composite_sugars and transformer.scope == "server" and builtin_name in {"any", "all", "sum"}:
        if keywords or len(positional_args) != 1:
            # 保持原样：后续 UnsupportedPythonSyntaxRule 会给出明确错误
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            return node

        input_expr = positional_args[0]
        if not isinstance(input_expr, ast.Name):
            return node

        list_type = str(transformer.list_var_type_by_name.get(input_expr.id, "") or "").strip()
        if builtin_name in {"any", "all"}:
            if list_type != "布尔值列表":
                return node
            class_name = "布尔值列表_任意为真" if builtin_name == "any" else "布尔值列表_全部为真"
            alias = "_共享复合_布尔值列表_任意为真" if builtin_name == "any" else "_共享复合_布尔值列表_全部为真"
            transformer._require_shared_composite(alias=alias, class_name=class_name)
            return transformer._shared_composite_instance_call(
                alias=alias,
                method_name="计算",
                keywords=[ast.keyword(arg="输入列表", value=ast.Name(id=input_expr.id, ctx=ast.Load()))],
                source_node=node,
            )

        # sum
        if list_type != "整数列表":
            return node
        class_name = "整数列表_求和"
        alias = "_共享复合_整数列表_求和"
        transformer._require_shared_composite(alias=alias, class_name=class_name)
        return transformer._shared_composite_instance_call(
            alias=alias,
            method_name="计算",
            keywords=[ast.keyword(arg="输入列表", value=ast.Name(id=input_expr.id, ctx=ast.Load()))],
            source_node=node,
        )

    if builtin_name in {"int", "float", "str", "bool"}:
        if keywords or len(positional_args) != 1:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_TYPE_CONVERSION_CALL_ARGS_INVALID",
                    message=(
                        f"{builtin_name}(...) 语法糖仅支持 1 个位置参数，且不支持关键字参数写法；"
                        "请改写为【数据类型转换】节点，或拆分为更明确的节点逻辑。"
                    ),
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_TYPE_CONVERSION_CALL_UNPACK_FORBIDDEN",
                    message=f"{builtin_name}(...) 语法糖不支持 * 展开入参；请先把值落到变量再转换。",
                    node=node,
                )
            )
            return node

        value_expr = positional_args[0]
        call_node = ast.Call(
            func=ast.Name(id=TYPE_CONVERSION_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[ast.keyword(arg="输入", value=value_expr)],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    if builtin_name in {"round", "floor", "ceil"}:
        if transformer.scope != "server":
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ROUNDING_NOT_SUPPORTED_IN_CLIENT",
                    message=(
                        f"{builtin_name}(...) 取整语法糖仅在 server 作用域支持（会改写为【取整数运算】）。"
                        "client 作用域缺少对应节点，请将取整放到 server 节点图处理，或改写为其它可用节点逻辑。"
                    ),
                    node=node,
                )
            )
            return node

        if keywords or len(positional_args) != 1:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ROUNDING_CALL_ARGS_INVALID",
                    message=f"{builtin_name}(...) 取整语法糖仅支持 1 个位置参数，且不支持关键字参数写法。",
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ROUNDING_CALL_UNPACK_FORBIDDEN",
                    message=f"{builtin_name}(...) 取整语法糖不支持 * 展开入参；请先把值落到变量再取整。",
                    node=node,
                )
            )
            return node

        rounding_mode = ROUNDING_MODE_ROUND
        if builtin_name == "floor":
            rounding_mode = ROUNDING_MODE_FLOOR
        elif builtin_name == "ceil":
            rounding_mode = ROUNDING_MODE_CEIL

        value_expr = positional_args[0]
        call_node = ast.Call(
            func=ast.Name(id=INTEGER_ROUNDING_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="输入", value=value_expr),
                ast.keyword(arg="取整方式", value=ast.Constant(value=rounding_mode)),
            ],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    if builtin_name == "abs":
        if keywords or len(positional_args) != 1:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ABS_CALL_ARGS_INVALID",
                    message="abs(...) 仅支持 1 个位置参数，且不支持关键字参数写法",
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ABS_CALL_UNPACK_FORBIDDEN",
                    message="abs(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                    node=node,
                )
            )
            return node

        value_expr = positional_args[0]
        if transformer._is_vector_expr(value_expr):
            call_node = ast.Call(
                func=ast.Name(id="三维向量模运算", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="三维向量", value=value_expr)],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node
        call_node = ast.Call(
            func=ast.Name(id=ABS_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[ast.keyword(arg="输入", value=value_expr)],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    if builtin_name in {"max", "min"}:
        if keywords:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_MIN_MAX_CALL_KEYWORDS_FORBIDDEN",
                    message="max/min(...) 语法糖不支持关键字参数（例如 key/default）；请改写为节点逻辑",
                    node=node,
                )
            )
            return node

        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_MIN_MAX_CALL_UNPACK_FORBIDDEN",
                    message="max/min(...) 语法糖不支持 * 展开入参；请先构造列表变量再调用 max/min",
                    node=node,
                )
            )
            return node

        if len(positional_args) == 1:
            container_expr = positional_args[0]
            node_name = LIST_MAX_VALUE_NODE_CALL_NAME if builtin_name == "max" else LIST_MIN_VALUE_NODE_CALL_NAME
            call_node = ast.Call(
                func=ast.Name(id=node_name, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="列表", value=container_expr)],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        if len(positional_args) == 2:
            first_value_expr, second_value_expr = positional_args
            if transformer.scope == "server":
                node_name = "取较大值" if builtin_name == "max" else "取较小值"
                call_node = ast.Call(
                    func=ast.Name(id=node_name, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="输入1", value=first_value_expr),
                        ast.keyword(arg="输入2", value=second_value_expr),
                    ],
                )
                ast.copy_location(call_node, node)
                call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                return call_node

            build_list_call = ast.Call(
                func=ast.Name(id="拼装列表", ctx=ast.Load()),
                args=[_build_self_game_expr(), first_value_expr, second_value_expr],
                keywords=[],
            )
            ast.copy_location(build_list_call, node)
            build_list_call.end_lineno = getattr(node, "end_lineno", getattr(build_list_call, "lineno", None))

            node_name = LIST_MAX_VALUE_NODE_CALL_NAME if builtin_name == "max" else LIST_MIN_VALUE_NODE_CALL_NAME
            call_node = ast.Call(
                func=ast.Name(id=node_name, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="列表", value=build_list_call)],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        transformer.issues.append(
            SyntaxSugarRewriteIssue(
                code="CODE_MIN_MAX_CALL_ARGS_INVALID",
                message="max/min(...) 语法糖仅支持 1 个位置参数（列表）或 2 个位置参数（两值比较），且不支持关键字参数",
                node=node,
            )
        )
        return node

    return None


def try_rewrite_shared_composite_direct_call(
    transformer: object,
    *,
    func_name: str,
    positional_args: List[ast.expr],
    keywords: List[ast.keyword],
    source_node: ast.AST,
) -> Optional[ast.Call]:
    """扩展共享复合节点语法糖：把 `复合节点名(...)` 改写为 `self.<alias>.<入口>(...)`。

    仅在 enable_shared_composite_sugars=True 且 server 作用域生效。
    """

    def _is_self_game_expr(expr: ast.AST) -> bool:
        return (
            isinstance(expr, ast.Attribute)
            and isinstance(getattr(expr, "value", None), ast.Name)
            and expr.value.id == "self"
            and str(getattr(expr, "attr", "") or "") == "game"
        )

    # 避免误伤“普通节点调用”形态：Node Call 约定第一个位置参数为 self.game
    if positional_args and _is_self_game_expr(positional_args[0]):
        return None

    if any(isinstance(arg, ast.Starred) for arg in positional_args):
        return None
    if any(getattr(kw, "arg", None) is None for kw in keywords):
        return None

    func_text = str(func_name or "").strip()
    if not func_text:
        return None

    # func_name -> (alias, composite_class_name, method_name, param_names)
    sugar_map: Dict[str, Tuple[str, str, str, List[str]]] = {
        "整数列表_按布尔掩码过滤": ("_共享复合_整数列表_按布尔掩码过滤", "整数列表_按布尔掩码过滤", "过滤", ["输入列表", "保留条件列表"]),
        "实体列表_按布尔掩码过滤": ("_共享复合_实体列表_按布尔掩码过滤", "实体列表_按布尔掩码过滤", "过滤", ["输入列表", "保留条件列表"]),
        "整数列表_查找首次出现序号": ("_共享复合_整数列表_查找首次出现序号", "整数列表_查找首次出现序号", "查找", ["输入列表", "目标值"]),
        "实体列表_查找首次出现序号": ("_共享复合_实体列表_查找首次出现序号", "实体列表_查找首次出现序号", "查找", ["输入列表", "目标实体"]),
        "权重列表_随机选序号": ("_共享复合_权重列表_随机选序号", "权重列表_随机选序号", "选择", ["权重列表"]),
        "实体列表_按权重随机选实体": ("_共享复合_实体列表_按权重随机选实体", "实体列表_按权重随机选实体", "选择", ["输入实体列表", "权重列表"]),
        "冷却_检查并更新时间戳": ("_共享复合_冷却_检查并更新时间戳", "冷却_检查并更新时间戳", "检查", ["当前时间戳", "上次触发时间戳", "冷却秒数"]),
        "整数列表_统计出现次数": ("_共享复合_整数列表_统计出现次数", "整数列表_统计出现次数", "统计", ["输入列表"]),
        "整数列表_按键分组": ("_共享复合_整数列表_按键分组", "整数列表_按键分组", "分组", ["输入列表", "分组键列表"]),
        "实体列表_按评分取前K": ("_共享复合_实体列表_按评分取前K", "实体列表_按评分取前K", "选择", ["输入实体列表", "评分列表", "TopK数量"]),
    }

    spec = sugar_map.get(func_text)
    if spec is None:
        return None

    alias, class_name, method_name, param_names = spec

    provided: Dict[str, ast.expr] = {}
    for index, arg in enumerate(positional_args):
        if index >= len(param_names):
            return None
        provided[param_names[index]] = arg
    for kw in keywords:
        if not kw.arg:
            return None
        provided[str(kw.arg)] = kw.value

    if set(provided.keys()) != set(param_names):
        return None

    transformer._require_shared_composite(alias=alias, class_name=class_name)
    call_keywords = [ast.keyword(arg=name, value=provided[name]) for name in param_names]
    return transformer._shared_composite_instance_call(
        alias=alias,
        method_name=method_name,
        keywords=call_keywords,
        source_node=source_node,
    )

