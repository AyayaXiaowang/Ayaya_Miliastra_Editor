from __future__ import annotations

import ast
import copy
from typing import List, Tuple

from .syntax_sugar_rewriter_ast_helpers import (
    _collect_all_name_ids,
    _collect_container_var_names,
    _collect_list_var_type_by_name,
    _collect_var_type_by_name,
    _iter_class_defs,
    _iter_method_defs,
)
from .syntax_sugar_rewriter_constants import _normalize_scope
from .syntax_sugar_rewriter_issue import SyntaxSugarRewriteIssue
from .syntax_sugar_rewriter_transformer import _GraphCodeSyntaxSugarTransformer


def rewrite_graph_code_syntax_sugars(
    tree: ast.Module,
    *,
    scope: str,
    enable_shared_composite_sugars: bool = False,
) -> Tuple[ast.Module, List[SyntaxSugarRewriteIssue]]:
    """将 Graph Code / 复合节点类方法体内的“常见 Python 语法糖”改写为等价的节点调用。

    当前支持（按需求逐步扩展）：
    - 列表下标读取：`值 = 列表[序号]` → `值 = 获取列表对应值(self.game, <列表入参>=列表, 序号=序号)`
    - len(...):
      - len(列表)：`len(列表)` → `获取列表长度(self.game, <列表入参>=列表)`
      - len(字典变量)（仅 server）：`len(字典变量)` → `查询字典长度(self.game, 字典=字典变量)`
    - abs(数值)：`abs(x)` → `绝对值运算(self.game, 输入=x)`
    - pow（仅 server）：`pow(a, b)` → `幂运算(self.game, 底数=a, 指数=b)`
    - print（仅 server，且仅语句形态）：`print(x)` → `打印字符串(self.game, 字符串=...)`
    - max/min：
      - `max(列表)` / `min(列表)` → `获取列表最大值/获取列表最小值(self.game, 列表=列表)`
      - `max(a, b)` / `min(a, b)`：
        - server：`取较大值/取较小值(self.game, 输入1=a, 输入2=b)`（单节点）
        - client：`获取列表最大值/获取列表最小值(self.game, 列表=拼装列表(self.game, a, b))`
      - 常见 clamp 写法（仅 server，且需能可靠识别上下限/输入）：`max(下限, min(上限, 输入))` / `min(上限, max(下限, 输入))`
        → `范围限制运算(self.game, 输入=输入, 下限=下限, 上限=上限)`（单节点；无法判定时会保持为 max/min 嵌套写法）
    - 类型转换：`int/float/str/bool(x)` → `数据类型转换(self.game, 输入=x)`（输出类型由承接端口/变量注解决定）
    - 取整（仅 server）：`round/floor/ceil(x)` → `取整数运算(self.game, 输入=x, 取整方式=...)`
    - 字典下标读取：`值 = 字典[键]` → `值 = 以键查询字典值(self.game, 字典=字典, 键=键)`
    - 字典 get：`值 = 字典.get(键)` → `值 = 以键查询字典值(self.game, 字典=字典, 键=键)`
    - 字典下标赋值：`字典[键] = 值` → `对字典设置或新增键值对(self.game, 字典=字典, 键=键, 值=值)`
    - del 字典下标：`del 字典[键]` → `以键对字典移除键值对(self.game, 字典=字典, 键=键)`
    - Compare（用于绕开 if 内联比较禁用）：`X in 列表` / `键 in 字典` / `A == B` / `A > B` 等
    - BoolOp：`A and B` / `A or B` → `逻辑与运算(...)` / `逻辑或运算(...)`
    - AugAssign：`x += y` / `x -= y` / `x *= y` / `x /= y` → `x = 加/减/乘/除法运算(...)`
    - 运算符（仅 server）：
      - `%`：`a % b` → `模运算(self.game, 被模数=a, 模数=b)`
      - `**`：`a ** b` → `幂运算(self.game, 底数=a, 指数=b)`
      - 位运算：`a & b` / `a | b` / `a ^ b` / `a << n` / `a >> n` / `~a` → `按位与/按位或/按位异或/左移运算/右移运算/按位取补运算(...)`
    - 布尔异或（server/client，需类型确定）：`A ^ B` → `逻辑异或运算(self.game, <端口映射>=A/B)`
    - 按位读出折叠（仅 server，严格模板）：`((值 >> 起始位) & ((1 << (结束位 - 起始位 + 1)) - 1))` → `按位读出(self.game, 值=值, 读出起始位=起始位, 读出结束位=结束位)`
    - 按位写入折叠（仅 server，严格模板）：`(被写入值 & ~mask) | (写入值 << 起始位)`（mask 为固定形态）→ `按位写入(self.game, 被写入值=被写入值, 写入值=写入值, 写入起始位=起始位, 写入结束位=结束位)`
    - 三维向量外积（server/client，需类型确定）：`向量A ^ 向量B` → `三维向量外积(self.game, 三维向量1=向量A, 三维向量2=向量B)`
    - math.xxx(...)（仅 server）：
      - `math.sin/cos/tan(x)` → `正弦函数/余弦函数/正切函数(self.game, 弧度=x)`
      - `math.asin/acos/atan(x)` → `反正弦函数/反余弦函数/反正切函数(self.game, 输入=x)`
      - `math.sqrt(x)` → `算术平方根运算(self.game, 输入=x)`
      - `math.pow(a, b)` → `幂运算(self.game, 底数=a, 指数=b)`
      - `math.log(x, base)` → `对数运算(self.game, 真数=x, 底数=base)`（仅两参形式）
      - `math.fabs(x)` → `绝对值运算(self.game, 输入=x)`
    - random.xxx(...)：
      - `random.randint(a, b)`（仅 server）→ `获取随机整数(self.game, 下限=a, 上限=b)`（包含上下限）
      - `random.uniform(a, b)` → server `获取随机浮点数(self.game, 下限=a, 上限=b)` / client `获取随机数(self.game, 下限=a, 上限=b)`（包含上下限）
      - `random.random()` → server `获取随机浮点数(self.game, 下限=0.0, 上限=1.0)` / client `获取随机数(self.game, 下限=0.0, 上限=1.0)`
    - time（仅 server）：
      - `time.time()` → `查询时间戳_UTC_0时区(self.game)`（输出为整数时间戳）
    - datetime（仅 server）：
      - `datetime.fromtimestamp(ts)` → `根据时间戳计算格式化时间(self.game, 时间戳=ts)`（输出：年/月/日/时/分/秒）
      - `datetime.fromtimestamp(ts).isoweekday()` → `根据时间戳计算星期几(self.game, 时间戳=ts)`（输出：1~7）
      - `datetime.fromtimestamp(ts).weekday() + 1` → `根据时间戳计算星期几(self.game, 时间戳=ts)`（单节点）
      - `datetime(...).timestamp()` → `根据格式化时间计算时间戳(self.game, 年=..., 月=..., 日=..., 时=..., 分=..., 秒=...)`
    - 容器方法（仅 server）：
      - `列表变量.sort()` / `列表变量.sort(reverse=True/False)` → `列表排序(self.game, 列表=列表变量, 排序方式="排序规则_顺序/排序规则_逆序")`
      - `字典变量.keys()` / `字典变量.values()` → `获取字典中键组成的列表/获取字典中值组成的列表(self.game, 字典=字典变量)`
      - `字典变量.clear()` → `清空字典(self.game, 字典=字典变量)`
      - `目标列表.append(x)` → `对列表插入值(self.game, 列表=目标列表, 插入序号=<大常量>, 插入值=x)`（利用 insert 越界等价 append）
      - `目标列表.pop(序号)` → `对列表移除值(self.game, 列表=目标列表, 移除序号=序号)`（仅语句形态，不支持承接返回值）
      - `目标字典.pop(键)` → `以键对字典移除键值对(self.game, 字典=目标字典, 键=键)`（仅语句形态，不支持承接返回值）

    说明：
    - 该函数为“纯函数”：会 deepcopy 输入 AST，并返回新 AST；
    - 仅处理类方法体；模块顶层/类体顶层不做重写（语义不明确，且无法转换为节点图执行流）。
    - scope 用于处理 server/client 的节点名/端口名差异。
    """
    if not isinstance(tree, ast.Module):
        raise TypeError("rewrite_graph_code_syntax_sugars 仅支持 ast.Module 输入")

    normalized_scope = _normalize_scope(scope)
    cloned_tree: ast.Module = copy.deepcopy(tree)
    issues: List[SyntaxSugarRewriteIssue] = []

    for class_def in _iter_class_defs(cloned_tree):
        # 在“普通节点图（非复合节点定义）”中，允许把部分 Python 语法改写为“共享复合节点调用”：
        # - 通过注入 `self.<自动实例> = <复合类>(...)` 到 __init__，让 IR 能识别 `self.<实例>.<入口>(...)`
        # - 复合节点定义文件中禁止嵌套其它复合节点（由 CompositeTypesAndNestingRule 阻断），因此默认关闭
        required_shared_composites: dict[str, str] = {}
        for method_def in _iter_method_defs(class_def):
            list_var_names, dict_var_names = _collect_container_var_names(method_def)
            used_names = _collect_all_name_ids(method_def)
            list_var_type_by_name = _collect_list_var_type_by_name(method_def)
            var_type_by_name = _collect_var_type_by_name(method_def)
            transformer = _GraphCodeSyntaxSugarTransformer(
                scope=normalized_scope,
                list_var_names=list_var_names,
                dict_var_names=dict_var_names,
                used_names=used_names,
                list_var_type_by_name=list_var_type_by_name,
                var_type_by_name=var_type_by_name,
                enable_shared_composite_sugars=enable_shared_composite_sugars,
            )
            transformer.visit(method_def)
            issues.extend(transformer.issues)
            # 汇总本类需要的共享复合节点实例：{alias: class_name}
            for alias, class_name in (getattr(transformer, "required_shared_composites", {}) or {}).items():
                if alias and class_name:
                    required_shared_composites.setdefault(alias, class_name)

        if enable_shared_composite_sugars and required_shared_composites:
            _ensure_shared_composites_in_init(class_def, required_shared_composites)

    ast.fix_missing_locations(cloned_tree)
    return cloned_tree, issues


def _ensure_shared_composites_in_init(class_def: ast.ClassDef, required: dict[str, str]) -> None:
    """确保类 __init__ 中包含 `self.<alias> = <class_name>(...)` 声明，用于复合节点实例识别。"""
    init_method: ast.FunctionDef | None = None
    for item in list(getattr(class_def, "body", []) or []):
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            init_method = item
            break

    if init_method is None:
        # 兜底：创建最小 __init__，保证复合节点实例可被扫描识别。
        init_method = ast.FunctionDef(
            name="__init__",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="self"),
                    ast.arg(arg="game"),
                    ast.arg(arg="owner_entity"),
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=[
                ast.Assign(
                    targets=[ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="game", ctx=ast.Store())],
                    value=ast.Name(id="game", ctx=ast.Load()),
                ),
                ast.Assign(
                    targets=[
                        ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="owner_entity", ctx=ast.Store())
                    ],
                    value=ast.Name(id="owner_entity", ctx=ast.Load()),
                ),
            ],
            decorator_list=[],
            returns=None,
            type_comment=None,
        )
        class_def.body.insert(0, init_method)

    # 解析 __init__ 已存在的实例声明：self.xxx = ClassName(...)
    existing_pairs: set[tuple[str, str]] = set()
    for stmt in list(getattr(init_method, "body", []) or []):
        if not isinstance(stmt, ast.Assign):
            continue
        if len(getattr(stmt, "targets", []) or []) != 1:
            continue
        target = stmt.targets[0]
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"):
            continue
        if not isinstance(getattr(stmt, "value", None), ast.Call):
            continue
        rhs_func = getattr(stmt.value, "func", None)
        if not isinstance(rhs_func, ast.Name):
            continue
        existing_pairs.add((target.attr, rhs_func.id))

    # 取 __init__ 的前两个形参名作为构造入参（兼容自定义命名）
    init_arg_names = [a.arg for a in list(getattr(init_method.args, "args", []) or [])]
    game_name = init_arg_names[1] if len(init_arg_names) >= 2 else "game"
    owner_name = init_arg_names[2] if len(init_arg_names) >= 3 else "owner_entity"

    # 选择插入位置：优先放在 self.game / self.owner_entity 之后，否则追加到末尾
    insert_at = len(init_method.body)
    for index, stmt in enumerate(list(getattr(init_method, "body", []) or [])):
        if not isinstance(stmt, ast.Assign):
            continue
        targets = list(getattr(stmt, "targets", []) or [])
        if len(targets) != 1:
            continue
        t0 = targets[0]
        if not (isinstance(t0, ast.Attribute) and isinstance(t0.value, ast.Name) and t0.value.id == "self"):
            continue
        if t0.attr in {"game", "owner_entity"}:
            insert_at = index + 1

    for alias, class_name in required.items():
        if (alias, class_name) in existing_pairs:
            continue
        assign_stmt = ast.Assign(
            targets=[ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr=alias, ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id=class_name, ctx=ast.Load()),
                args=[ast.Name(id=game_name, ctx=ast.Load()), ast.Name(id=owner_name, ctx=ast.Load())],
                keywords=[],
            ),
        )
        init_method.body.insert(insert_at, assign_stmt)
        insert_at += 1


__all__ = [
    "SyntaxSugarRewriteIssue",
    "rewrite_graph_code_syntax_sugars",
]


