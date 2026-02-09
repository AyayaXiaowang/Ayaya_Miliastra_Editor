from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple

from .syntax_sugar_rewriter_ast_helpers import (
    _build_self_game_expr,
    _extract_subscript_index_expr,
    _is_dict_var_name,
)
from .syntax_sugar_rewriter_constants import (
    ABS_NODE_CALL_NAME,
    ADD_NODE_CALL_NAME,
    DICT_CONTAINS_KEY_NODE_CALL_NAME,
    DICT_DELETE_ITEM_NODE_CALL_NAME,
    DICT_GET_ITEM_NODE_CALL_NAME,
    DICT_LENGTH_NODE_CALL_NAME,
    DICT_SET_ITEM_NODE_CALL_NAME,
    DIVIDE_NODE_CALL_NAME,
    EQUAL_NODE_CALL_NAME,
    INTEGER_ROUNDING_NODE_CALL_NAME,
    LOGIC_NOT_NODE_CALL_NAME,
    LIST_CONTAINS_NODE_CALL_NAME,
    LIST_GET_ITEM_NODE_CALL_NAME,
    LIST_LENGTH_NODE_CALL_NAME,
    LIST_MAX_VALUE_NODE_CALL_NAME,
    LIST_MIN_VALUE_NODE_CALL_NAME,
    LOGIC_AND_NODE_CALL_NAME,
    LOGIC_OR_NODE_CALL_NAME,
    MULTIPLY_NODE_CALL_NAME,
    ROUNDING_MODE_CEIL,
    ROUNDING_MODE_FLOOR,
    ROUNDING_MODE_ROUND,
    SUBTRACT_NODE_CALL_NAME,
    TYPE_CONVERSION_NODE_CALL_NAME,
    _arith_node_name,
    _list_get_list_port_name,
    _list_length_list_port_name,
    _logic_binary_input_port_names,
    _logic_not_input_port_name,
    _normalize_scope,
    _numeric_compare_node_name,
)
from .syntax_sugar_rewriter_issue import SyntaxSugarRewriteIssue


class _GraphCodeSyntaxSugarTransformerExprCallMixin:
    def visit_Call(self, node: ast.Call):  # noqa: N802
        # 先重写参数，再处理内置函数语法糖：
        # - len/abs/max/min
        # - int/float/str/bool（数据类型转换）
        # - round/floor/ceil（取整数运算，仅 server）
        clamp_rewritten = self._try_rewrite_server_clamp_min_max(node)
        if clamp_rewritten is not None:
            return clamp_rewritten

        time_call_rewritten = self._try_rewrite_time_time_call(node)
        if time_call_rewritten is not None:
            return time_call_rewritten

        datetime_call_rewritten = self._try_rewrite_datetime_calls(node)
        if datetime_call_rewritten is not None:
            return datetime_call_rewritten

        visited = self.generic_visit(node)
        if not isinstance(visited, ast.Call):
            return visited
        node = visited

        positional_args = list(getattr(node, "args", []) or [])
        keywords = list(getattr(node, "keywords", []) or [])

        func = getattr(node, "func", None)
        if isinstance(func, ast.Attribute):
            base = getattr(func, "value", None)
            attr_name = str(getattr(func, "attr", "") or "")

            # random.randint/random.uniform/random.random：
            # - randint 仅 server（等价【获取随机整数】）
            # - uniform server/client 均支持（server【获取随机浮点数】，client【获取随机数】）
            # - random() server/client 均支持（等价 random.uniform(0, 1)；注意语义上 random.random() 上限通常为开区间）
            if isinstance(base, ast.Name) and base.id == "random" and attr_name in {"randint", "uniform", "random"}:
                if keywords:
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_RANDOM_CALL_KEYWORDS_FORBIDDEN",
                            message="random.xxx(...) 语法糖不支持关键字参数；请使用位置参数（例如 random.randint(a, b) / random.uniform(a, b)）。",
                            node=node,
                        )
                    )
                    return node
                if any(isinstance(arg, ast.Starred) for arg in positional_args):
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_RANDOM_CALL_UNPACK_FORBIDDEN",
                            message="random.xxx(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                            node=node,
                        )
                    )
                    return node
                if attr_name == "random":
                    if positional_args:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_RANDOM_RANDOM_ARGS_INVALID",
                                message="random.random() 语法糖不支持入参（请使用 `random.random()`）。",
                                node=node,
                            )
                        )
                        return node

                    node_func_name = "获取随机浮点数" if self.scope == "server" else "获取随机数"
                    call_node = ast.Call(
                        func=ast.Name(id=node_func_name, ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[
                            ast.keyword(arg="下限", value=ast.Constant(value=0.0)),
                            ast.keyword(arg="上限", value=ast.Constant(value=1.0)),
                        ],
                    )
                    ast.copy_location(call_node, node)
                    call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                    return call_node

                if len(positional_args) != 2:
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_RANDOM_CALL_ARGS_INVALID",
                            message=f"random.{attr_name}(...) 语法糖仅支持 2 个位置参数（下限, 上限）。",
                            node=node,
                        )
                    )
                    return node

                lower_bound_expr, upper_bound_expr = positional_args
                if attr_name == "randint":
                    if self.scope != "server":
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_RANDOM_RANDINT_NOT_SUPPORTED_IN_CLIENT",
                                message="random.randint(...) 语法糖仅在 server 作用域支持（会改写为【获取随机整数】）。client 侧缺少等价节点。",
                                node=node,
                            )
                        )
                        return node
                    node_func_name = "获取随机整数"
                else:
                    node_func_name = "获取随机浮点数" if self.scope == "server" else "获取随机数"

                call_node = ast.Call(
                    func=ast.Name(id=node_func_name, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="下限", value=lower_bound_expr),
                        ast.keyword(arg="上限", value=upper_bound_expr),
                    ],
                )
                ast.copy_location(call_node, node)
                call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                return call_node

            # dict.keys()/dict.values()：仅 server 支持（client 缺少对应节点）
            if isinstance(base, ast.Name) and _is_dict_var_name(base.id, self.dict_var_names) and attr_name == "get":
                if keywords:
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_DICT_GET_KEYWORDS_FORBIDDEN",
                            message="字典方法 get(...) 语法糖不支持关键字参数；请使用位置参数写法（例如 `目标字典.get(键)`）。",
                            node=node,
                        )
                    )
                    return node
                if any(isinstance(arg, ast.Starred) for arg in positional_args):
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_DICT_GET_UNPACK_FORBIDDEN",
                            message="字典方法 get(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                            node=node,
                        )
                    )
                    return node
                if len(positional_args) != 1:
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_DICT_GET_ARGS_INVALID",
                            message="字典方法 get(...) 语法糖仅支持 1 个位置参数（键）。若需要默认值，请改用 if 分支或拆解为多步节点逻辑。",
                            node=node,
                        )
                    )
                    return node

                key_expr = positional_args[0]
                call_node = ast.Call(
                    func=ast.Name(id="以键查询字典值", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="字典", value=ast.Name(id=base.id, ctx=ast.Load())),
                        ast.keyword(arg="键", value=key_expr),
                    ],
                )
                ast.copy_location(call_node, node)
                call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                return call_node

            if isinstance(base, ast.Name) and _is_dict_var_name(base.id, self.dict_var_names) and attr_name in {"keys", "values"}:
                if self.scope != "server":
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_DICT_KEYS_VALUES_NOT_SUPPORTED_IN_CLIENT",
                            message="字典方法 keys()/values() 语法糖仅在 server 作用域支持（会改写为【获取字典中键组成的列表】/【获取字典中值组成的列表】）。",
                            node=node,
                        )
                    )
                    return node

                if keywords or positional_args:
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_DICT_KEYS_VALUES_ARGS_FORBIDDEN",
                            message="仅支持 `目标字典.keys()` / `目标字典.values()`（不支持任何入参）。",
                            node=node,
                        )
                    )
                    return node

                node_name = "获取字典中键组成的列表" if attr_name == "keys" else "获取字典中值组成的列表"
                call_node = ast.Call(
                    func=ast.Name(id=node_name, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[ast.keyword(arg="字典", value=ast.Name(id=base.id, ctx=ast.Load()))],
                )
                ast.copy_location(call_node, node)
                call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                return call_node

            # math.xxx(...)：仅 server 支持（用于绕开方法调用禁用规则）
            if isinstance(base, ast.Name) and base.id == "math":
                # math.fabs：server/client 均支持（等价映射【绝对值运算】）
                if attr_name == "fabs":
                    if keywords:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                                message="math.fabs(...) 语法糖不支持关键字参数；请使用位置参数写法（math.fabs(x)）。",
                                node=node,
                            )
                        )
                        return node
                    if any(isinstance(arg, ast.Starred) for arg in positional_args):
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                                message="math.fabs(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                node=node,
                            )
                        )
                        return node
                    if len(positional_args) != 1:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_ARGS_INVALID",
                                message="math.fabs(...) 语法糖仅支持 1 个位置参数。",
                                node=node,
                            )
                        )
                        return node
                    value_expr = positional_args[0]
                    call_node = ast.Call(
                        func=ast.Name(id=ABS_NODE_CALL_NAME, ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[ast.keyword(arg="输入", value=value_expr)],
                    )
                    ast.copy_location(call_node, node)
                    call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                    return call_node

                # math.pow：仅 server 支持（等价映射【幂运算】）
                if attr_name == "pow":
                    if self.scope != "server":
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_POW_NOT_SUPPORTED_IN_CLIENT",
                                message="math.pow(...) 语法糖仅在 server 作用域支持（会改写为【幂运算】）。client 侧缺少等价节点。",
                                node=node,
                            )
                        )
                        return node
                    if keywords:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                                message="math.pow(...) 语法糖不支持关键字参数；请使用位置参数写法（math.pow(a, b)）。",
                                node=node,
                            )
                        )
                        return node
                    if any(isinstance(arg, ast.Starred) for arg in positional_args):
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                                message="math.pow(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                node=node,
                            )
                        )
                        return node
                    if len(positional_args) != 2:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_ARGS_INVALID",
                                message="math.pow(...) 语法糖仅支持 2 个位置参数（底数, 指数）。",
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

                # math.radians/math.degrees：server/client 均支持（节点端口名有差异，需要按 scope 映射）
                if attr_name in {"radians", "degrees"}:
                    if keywords:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                                message="math.xxx(...) 语法糖不支持关键字参数；请使用位置参数写法（例如 math.radians(x) / math.degrees(x)）。",
                                node=node,
                            )
                        )
                        return node
                    if any(isinstance(arg, ast.Starred) for arg in positional_args):
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                                message="math.xxx(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                node=node,
                            )
                        )
                        return node
                    if len(positional_args) != 1:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_RAD_DEG_CALL_ARGS_INVALID",
                                message=f"math.{attr_name}(...) 语法糖仅支持 1 个位置参数。",
                                node=node,
                            )
                        )
                        return node

                    value_expr = positional_args[0]
                    if attr_name == "radians":
                        node_func_name = "角度转弧度"
                        input_port_name = "角度值" if self.scope == "server" else "角度"
                    else:
                        node_func_name = "弧度转角度"
                        input_port_name = "弧度值" if self.scope == "server" else "弧度"

                    call_node = ast.Call(
                        func=ast.Name(id=node_func_name, ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[ast.keyword(arg=input_port_name, value=value_expr)],
                    )
                    ast.copy_location(call_node, node)
                    call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                    return call_node

                # math.dist：仅 server 支持（等价映射【两坐标点距离】）
                if attr_name == "dist":
                    if self.scope != "server":
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_DIST_NOT_SUPPORTED_IN_CLIENT",
                                message="math.dist(...) 语法糖仅在 server 作用域支持（会改写为【两坐标点距离】）。",
                                node=node,
                            )
                        )
                        return node
                    if keywords:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                                message="math.dist(...) 语法糖不支持关键字参数；请使用位置参数写法（math.dist(a, b)）。",
                                node=node,
                            )
                        )
                        return node
                    if any(isinstance(arg, ast.Starred) for arg in positional_args):
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                                message="math.dist(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                node=node,
                            )
                        )
                        return node
                    if len(positional_args) != 2:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_DIST_CALL_ARGS_INVALID",
                                message="math.dist(...) 语法糖仅支持 2 个位置参数（坐标点1, 坐标点2）。",
                                node=node,
                            )
                        )
                        return node
                    point1_expr, point2_expr = positional_args
                    call_node = ast.Call(
                        func=ast.Name(id="两坐标点距离", ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[
                            ast.keyword(arg="坐标点1", value=point1_expr),
                            ast.keyword(arg="坐标点2", value=point2_expr),
                        ],
                    )
                    ast.copy_location(call_node, node)
                    call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                    return call_node

                if attr_name in {"floor", "ceil"}:
                    builtin_name = attr_name
                else:
                    if self.scope != "server":
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_NOT_SUPPORTED_IN_CLIENT",
                                message="math.xxx(...) 数学函数语法糖仅在 server 作用域支持（会改写为对应运算节点）。",
                                node=node,
                            )
                        )
                        return node

                    if keywords:
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                                message="math.xxx(...) 语法糖不支持关键字参数；请使用位置参数写法（例如 math.sin(x) / math.log(x, base)）。",
                                node=node,
                            )
                        )
                        return node
                    if any(isinstance(arg, ast.Starred) for arg in positional_args):
                        self.issues.append(
                            SyntaxSugarRewriteIssue(
                                code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                                message="math.xxx(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                node=node,
                            )
                        )
                        return node

                    trig_node_by_name = {
                        "sin": ("正弦函数", "弧度"),
                        "cos": ("余弦函数", "弧度"),
                        "tan": ("正切函数", "弧度"),
                        "asin": ("反正弦函数", "输入"),
                        "acos": ("反余弦函数", "输入"),
                        "atan": ("反正切函数", "输入"),
                    }
                    if attr_name in trig_node_by_name:
                        if len(positional_args) != 1:
                            self.issues.append(
                                SyntaxSugarRewriteIssue(
                                    code="CODE_MATH_TRIG_CALL_ARGS_INVALID",
                                    message=f"math.{attr_name}(...) 语法糖仅支持 1 个位置参数。",
                                    node=node,
                                )
                            )
                            return node
                        node_func_name, input_port_name = trig_node_by_name[attr_name]
                        call_node = ast.Call(
                            func=ast.Name(id=node_func_name, ctx=ast.Load()),
                            args=[_build_self_game_expr()],
                            keywords=[ast.keyword(arg=input_port_name, value=positional_args[0])],
                        )
                        ast.copy_location(call_node, node)
                        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                        return call_node

                    if attr_name == "sqrt":
                        if len(positional_args) != 1:
                            self.issues.append(
                                SyntaxSugarRewriteIssue(
                                    code="CODE_MATH_SQRT_CALL_ARGS_INVALID",
                                    message="math.sqrt(...) 语法糖仅支持 1 个位置参数。",
                                    node=node,
                                )
                            )
                            return node
                        call_node = ast.Call(
                            func=ast.Name(id="算术平方根运算", ctx=ast.Load()),
                            args=[_build_self_game_expr()],
                            keywords=[ast.keyword(arg="输入", value=positional_args[0])],
                        )
                        ast.copy_location(call_node, node)
                        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                        return call_node

                    if attr_name == "log":
                        if len(positional_args) != 2:
                            self.issues.append(
                                SyntaxSugarRewriteIssue(
                                    code="CODE_MATH_LOG_CALL_ARGS_INVALID",
                                    message="math.log(...) 语法糖仅支持 2 个位置参数（math.log(真数, 底数)）。",
                                    node=node,
                                )
                            )
                            return node
                        true_number_expr, base_number_expr = positional_args
                        call_node = ast.Call(
                            func=ast.Name(id="对数运算", ctx=ast.Load()),
                            args=[_build_self_game_expr()],
                            keywords=[
                                ast.keyword(arg="真数", value=true_number_expr),
                                ast.keyword(arg="底数", value=base_number_expr),
                            ],
                        )
                        ast.copy_location(call_node, node)
                        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                        return call_node

                    return node

            return node
        elif isinstance(func, ast.Name):
            builtin_name = str(getattr(func, "id", "") or "")
        else:
            return node

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
        if self.enable_shared_composite_sugars and self.scope == "server":
            rewritten_shared = self._try_rewrite_shared_composite_direct_call(
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
                            self.issues.append(
                                SyntaxSugarRewriteIssue(
                                    code="CODE_DICT_ZIP_CALL_KEYWORDS_FORBIDDEN",
                                    message="dict(zip(...)) 语法糖不支持 zip(...) 关键字参数写法；请使用位置参数 `zip(键列表, 值列表)`。",
                                    node=node,
                                )
                            )
                            return node
                        if any(isinstance(arg, ast.Starred) for arg in zip_args):
                            self.issues.append(
                                SyntaxSugarRewriteIssue(
                                    code="CODE_DICT_ZIP_CALL_UNPACK_FORBIDDEN",
                                    message="dict(zip(...)) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                                    node=node,
                                )
                            )
                            return node
                        if len(zip_args) != 2:
                            self.issues.append(
                                SyntaxSugarRewriteIssue(
                                    code="CODE_DICT_ZIP_CALL_ARGS_INVALID",
                                    message="dict(zip(...)) 语法糖仅支持 `dict(zip(键列表, 值列表))`（zip 必须恰好 2 个位置参数）。",
                                    node=node,
                                )
                            )
                            return node

                        if self.scope != "server":
                            self.issues.append(
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
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_POW_NOT_SUPPORTED_IN_CLIENT",
                        message="pow(a, b) 语法糖仅在 server 作用域支持（会改写为【幂运算】）。client 侧缺少等价节点。",
                        node=node,
                    )
                )
                return node
            if keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_POW_CALL_KEYWORDS_FORBIDDEN",
                        message="pow(a, b) 语法糖不支持关键字参数；请使用位置参数写法（pow(a, b)）。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_POW_CALL_UNPACK_FORBIDDEN",
                        message="pow(a, b) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                        node=node,
                    )
                )
                return node
            if len(positional_args) != 2:
                self.issues.append(
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
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LEN_CALL_ARGS_INVALID",
                        message="len(...) 仅支持 1 个位置参数，且不支持关键字参数写法",
                        node=node,
                    )
                )
                return node

            container_expr = positional_args[0]
            if self.scope == "server" and isinstance(container_expr, ast.Name) and _is_dict_var_name(
                container_expr.id,
                self.dict_var_names,
            ):
                call_node = ast.Call(
                    func=ast.Name(id=DICT_LENGTH_NODE_CALL_NAME, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[ast.keyword(arg="字典", value=ast.Name(id=container_expr.id, ctx=ast.Load()))],
                )
                ast.copy_location(call_node, node)
                call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
                return call_node

            list_port_name = _list_length_list_port_name(self.scope)
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
        if self.enable_shared_composite_sugars and self.scope == "server" and builtin_name in {"any", "all", "sum"}:
            if keywords or len(positional_args) != 1:
                # 保持原样：后续 UnsupportedPythonSyntaxRule 会给出明确错误
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                return node

            input_expr = positional_args[0]
            if not isinstance(input_expr, ast.Name):
                return node

            list_type = str(self.list_var_type_by_name.get(input_expr.id, "") or "").strip()
            if builtin_name in {"any", "all"}:
                if list_type != "布尔值列表":
                    return node
                class_name = "布尔值列表_任意为真" if builtin_name == "any" else "布尔值列表_全部为真"
                alias = "_共享复合_布尔值列表_任意为真" if builtin_name == "any" else "_共享复合_布尔值列表_全部为真"
                self._require_shared_composite(alias=alias, class_name=class_name)
                return self._shared_composite_instance_call(
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
            self._require_shared_composite(alias=alias, class_name=class_name)
            return self._shared_composite_instance_call(
                alias=alias,
                method_name="计算",
                keywords=[ast.keyword(arg="输入列表", value=ast.Name(id=input_expr.id, ctx=ast.Load()))],
                source_node=node,
            )

        if builtin_name in {"int", "float", "str", "bool"}:
            if keywords or len(positional_args) != 1:
                self.issues.append(
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
                self.issues.append(
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
            if self.scope != "server":
                self.issues.append(
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
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_ROUNDING_CALL_ARGS_INVALID",
                        message=f"{builtin_name}(...) 取整语法糖仅支持 1 个位置参数，且不支持关键字参数写法。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                self.issues.append(
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
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_ABS_CALL_ARGS_INVALID",
                        message="abs(...) 仅支持 1 个位置参数，且不支持关键字参数写法",
                        node=node,
                    )
                )
                return node

            value_expr = positional_args[0]
            if self._is_vector_expr(value_expr):
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
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MIN_MAX_CALL_KEYWORDS_FORBIDDEN",
                        message="max/min(...) 语法糖不支持关键字参数（例如 key/default）；请改写为节点逻辑",
                        node=node,
                    )
                )
                return node

            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                self.issues.append(
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
                if self.scope == "server":
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

            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_MIN_MAX_CALL_ARGS_INVALID",
                    message="max/min(...) 语法糖仅支持 1 个位置参数（列表）或 2 个位置参数（两值比较），且不支持关键字参数",
                    node=node,
                )
            )
            return node

        return node

    def _try_rewrite_shared_composite_direct_call(
        self,
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

        self._require_shared_composite(alias=alias, class_name=class_name)
        call_keywords = [ast.keyword(arg=name, value=provided[name]) for name in param_names]
        return self._shared_composite_instance_call(
            alias=alias,
            method_name=method_name,
            keywords=call_keywords,
            source_node=source_node,
        )

