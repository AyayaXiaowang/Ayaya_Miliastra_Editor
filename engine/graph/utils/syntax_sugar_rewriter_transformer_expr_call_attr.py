from __future__ import annotations

import ast
from typing import List, Optional

from .syntax_sugar_rewriter_ast_helpers import _build_self_game_expr, _is_dict_var_name
from .syntax_sugar_rewriter_constants import (
    ABS_NODE_CALL_NAME,
    INTEGER_ROUNDING_NODE_CALL_NAME,
    ROUNDING_MODE_CEIL,
    ROUNDING_MODE_FLOOR,
    ROUNDING_MODE_ROUND,
)
from .syntax_sugar_rewriter_issue import SyntaxSugarRewriteIssue


def try_rewrite_attribute_call(
    transformer: object,
    *,
    node: ast.Call,
    func: ast.Attribute,
    positional_args: List[ast.expr],
    keywords: List[ast.keyword],
) -> Optional[ast.AST]:
    """对 Attribute 形式的 Call 做语法糖改写（random/dict/math 等）。"""
    base = getattr(func, "value", None)
    attr_name = str(getattr(func, "attr", "") or "")

    # random.randint/random.uniform/random.random：
    # - randint 仅 server（等价【获取随机整数】）
    # - uniform server/client 均支持（server【获取随机浮点数】，client【获取随机数】）
    # - random() server/client 均支持（等价 random.uniform(0, 1)；注意语义上 random.random() 上限通常为开区间）
    if isinstance(base, ast.Name) and base.id == "random" and attr_name in {"randint", "uniform", "random"}:
        if keywords:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_RANDOM_CALL_KEYWORDS_FORBIDDEN",
                    message="random.xxx(...) 语法糖不支持关键字参数；请使用位置参数（例如 random.randint(a, b) / random.uniform(a, b)）。",
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_RANDOM_CALL_UNPACK_FORBIDDEN",
                    message="random.xxx(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                    node=node,
                )
            )
            return node
        if attr_name == "random":
            if positional_args:
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_RANDOM_RANDOM_ARGS_INVALID",
                        message="random.random() 语法糖不支持入参（请使用 `random.random()`）。",
                        node=node,
                    )
                )
                return node

            node_func_name = "获取随机浮点数" if transformer.scope == "server" else "获取随机数"
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
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_RANDOM_CALL_ARGS_INVALID",
                    message=f"random.{attr_name}(...) 语法糖仅支持 2 个位置参数（下限, 上限）。",
                    node=node,
                )
            )
            return node

        lower_bound_expr, upper_bound_expr = positional_args
        if attr_name == "randint":
            if transformer.scope != "server":
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_RANDOM_RANDINT_NOT_SUPPORTED_IN_CLIENT",
                        message="random.randint(...) 语法糖仅在 server 作用域支持（会改写为【获取随机整数】）。client 侧缺少等价节点。",
                        node=node,
                    )
                )
                return node
            node_func_name = "获取随机整数"
        else:
            node_func_name = "获取随机浮点数" if transformer.scope == "server" else "获取随机数"

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
    if isinstance(base, ast.Name) and _is_dict_var_name(base.id, transformer.dict_var_names) and attr_name == "get":
        if keywords:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_DICT_GET_KEYWORDS_FORBIDDEN",
                    message="字典方法 get(...) 语法糖不支持关键字参数；请使用位置参数写法（例如 `目标字典.get(键)`）。",
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_DICT_GET_UNPACK_FORBIDDEN",
                    message="字典方法 get(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                    node=node,
                )
            )
            return node
        if len(positional_args) != 1:
            transformer.issues.append(
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

    if isinstance(base, ast.Name) and _is_dict_var_name(base.id, transformer.dict_var_names) and attr_name in {"keys", "values"}:
        if transformer.scope != "server":
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_DICT_KEYS_VALUES_NOT_SUPPORTED_IN_CLIENT",
                    message="字典方法 keys()/values() 语法糖仅在 server 作用域支持（会改写为【获取字典中键组成的列表】/【获取字典中值组成的列表】）。",
                    node=node,
                )
            )
            return node

        if keywords or positional_args:
            transformer.issues.append(
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
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                        message="math.fabs(...) 语法糖不支持关键字参数；请使用位置参数写法（math.fabs(x)）。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                        message="math.fabs(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                        node=node,
                    )
                )
                return node
            if len(positional_args) != 1:
                transformer.issues.append(
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
            if transformer.scope != "server":
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_POW_NOT_SUPPORTED_IN_CLIENT",
                        message="math.pow(...) 语法糖仅在 server 作用域支持（会改写为【幂运算】）。client 侧缺少等价节点。",
                        node=node,
                    )
                )
                return node
            if keywords:
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                        message="math.pow(...) 语法糖不支持关键字参数；请使用位置参数写法（math.pow(a, b)）。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                        message="math.pow(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                        node=node,
                    )
                )
                return node
            if len(positional_args) != 2:
                transformer.issues.append(
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
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                        message="math.xxx(...) 语法糖不支持关键字参数；请使用位置参数写法（例如 math.radians(x) / math.degrees(x)）。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                        message="math.xxx(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                        node=node,
                    )
                )
                return node
            if len(positional_args) != 1:
                transformer.issues.append(
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
                input_port_name = "角度值" if transformer.scope == "server" else "角度"
            else:
                node_func_name = "弧度转角度"
                input_port_name = "弧度值" if transformer.scope == "server" else "弧度"

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
            if transformer.scope != "server":
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_DIST_NOT_SUPPORTED_IN_CLIENT",
                        message="math.dist(...) 语法糖仅在 server 作用域支持（会改写为【两坐标点距离】）。",
                        node=node,
                    )
                )
                return node
            if keywords:
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                        message="math.dist(...) 语法糖不支持关键字参数；请使用位置参数写法（math.dist(a, b)）。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_CALL_UNPACK_FORBIDDEN",
                        message="math.dist(...) 语法糖不支持 * 展开入参；请先把值落到变量再调用。",
                        node=node,
                    )
                )
                return node
            if len(positional_args) != 2:
                transformer.issues.append(
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

        # math.floor/math.ceil：保持与旧实现一致，按取整语法糖处理（会改写为【取整数运算】）
        if attr_name in {"floor", "ceil"}:
            if transformer.scope != "server":
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_ROUNDING_NOT_SUPPORTED_IN_CLIENT",
                        message=(
                            f"{attr_name}(...) 取整语法糖仅在 server 作用域支持（会改写为【取整数运算】）。"
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
                        message=f"{attr_name}(...) 取整语法糖仅支持 1 个位置参数，且不支持关键字参数写法。",
                        node=node,
                    )
                )
                return node
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                transformer.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_ROUNDING_CALL_UNPACK_FORBIDDEN",
                        message=f"{attr_name}(...) 取整语法糖不支持 * 展开入参；请先把值落到变量再取整。",
                        node=node,
                    )
                )
                return node

            rounding_mode = ROUNDING_MODE_ROUND
            if attr_name == "floor":
                rounding_mode = ROUNDING_MODE_FLOOR
            elif attr_name == "ceil":
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

        if transformer.scope != "server":
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_MATH_CALL_NOT_SUPPORTED_IN_CLIENT",
                    message="math.xxx(...) 数学函数语法糖仅在 server 作用域支持（会改写为对应运算节点）。",
                    node=node,
                )
            )
            return node

        if keywords:
            transformer.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_MATH_CALL_KEYWORDS_FORBIDDEN",
                    message="math.xxx(...) 语法糖不支持关键字参数；请使用位置参数写法（例如 math.sin(x) / math.log(x, base)）。",
                    node=node,
                )
            )
            return node
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            transformer.issues.append(
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
                transformer.issues.append(
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
                transformer.issues.append(
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
                transformer.issues.append(
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

    return None

