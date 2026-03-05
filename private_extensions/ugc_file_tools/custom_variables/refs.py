from __future__ import annotations

import re
from typing import Optional, Tuple

from .constants import DEFAULT_VARIABLE_GROUP_NAME, KNOWN_VARIABLE_GROUP_ID_BY_NAME, UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX

__all__ = [
    "is_number_like_text",
    "parse_variable_ref_text",
    "require_scalar_variable_name",
    "TextPlaceholderVarRef",
    "extract_variable_refs_from_text_placeholders",
]


def is_number_like_text(text: str) -> bool:
    raw = str(text or "").strip()
    if raw == "":
        return False
    if raw.startswith("+") or raw.startswith("-"):
        raw = raw[1:]
    if raw.isdigit():
        return True
    if "." in raw:
        left, right = raw.split(".", 1)
        if left.isdigit() and right.isdigit():
            return True
    return False


def parse_variable_ref_text(
    text: str,
    *,
    allow_constant_number: bool,
) -> Tuple[int, Optional[str], Optional[str]]:
    """
    将用户可读的变量引用文本解析为 variable_ref：

    - "关卡.xxx" / "玩家自身.xxx" -> (group_id, "变量名", "组名.变量名")
    - "lv.xxx" / "{1:lv.xxx}" -> 视为关卡变量 -> (关卡组id, "变量名", "关卡.变量名")
    - "." 或 "" -> (unbound_sentinel, None, None)
    - （仅 allow_constant_number=True）纯数字/小数 -> (unbound_sentinel, "100", None) 视为常量数字

    注意：不再把无前缀 "xxx" 自动补成 "关卡.xxx"。
    """
    raw = str(text or "").strip()
    if raw == "" or raw == ".":
        return (int(UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX), None, None)

    default_group_name = str(DEFAULT_VARIABLE_GROUP_NAME or "").strip()
    default_group_id = KNOWN_VARIABLE_GROUP_ID_BY_NAME.get(default_group_name)
    if default_group_id is None:
        raise ValueError(f"未知默认变量组名：{default_group_name!r}（当前已知：{sorted(KNOWN_VARIABLE_GROUP_ID_BY_NAME.keys())}）")

    # 文本框变量占位符：{1:lv.xxx}（仅把 lv.xxx 解析为关卡变量；花括号内的数字目前不参与语义）
    if raw.startswith("{") and raw.endswith("}"):
        inner = raw[1:-1].strip()
        if ":" in inner:
            left, right = inner.split(":", 1)
            if str(left or "").strip().isdigit():
                right_text = str(right or "").strip()
                if right_text.lower().startswith("lv."):
                    var_name = str(right_text[3:] or "").strip()
                    if var_name == "":
                        raise ValueError(f"变量引用不完整：{raw!r}")
                    return (int(default_group_id), var_name, f"{default_group_name}.{var_name}")

    # lv.xxx：视为关卡变量
    if raw.lower().startswith("lv."):
        var_name = str(raw[3:] or "").strip()
        if var_name == "":
            raise ValueError(f"变量引用不完整：{raw!r}")
        return (int(default_group_id), var_name, f"{default_group_name}.{var_name}")

    # 组名.变量名：显式变量引用
    if "." in raw:
        group_name, var_name = raw.split(".", 1)
        group_name = str(group_name or "").strip()
        var_name = str(var_name or "").strip()
        if group_name == "" or var_name == "":
            raise ValueError(f"变量引用必须为 '组名.变量名' 或 '.'：{raw!r}")
        # 兼容 UI源码/Workbench 侧的别名：
        # - ps / p1..p8：玩家自身
        group_name_lower = group_name.lower()
        if group_name_lower == "ps" or (group_name_lower.startswith("p") and group_name_lower[1:].isdigit()):
            group_name = "玩家自身"
        elif group_name_lower == "ls":
            raise ValueError(f"不支持变量引用使用 ls 前缀，请改用 lv：{raw!r}")
        elif group_name_lower == "lv":
            group_name = "关卡"
        if group_name.lower() == "lv":
            return (int(default_group_id), var_name, f"{default_group_name}.{var_name}")
        group_id = KNOWN_VARIABLE_GROUP_ID_BY_NAME.get(group_name)
        if group_id is None:
            raise ValueError(f"未知变量组名：{group_name!r}（当前已知：{sorted(KNOWN_VARIABLE_GROUP_ID_BY_NAME.keys())}）")
        return (int(group_id), var_name, f"{group_name}.{var_name}")

    # 常量数字
    if allow_constant_number and is_number_like_text(raw):
        return (int(UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX), raw, None)

    raise ValueError(
        "变量引用必须为 '组名.变量名' / 'lv.变量名' / '{1:lv.变量名}' / '.'"
        + (" 或 数字常量" if allow_constant_number else "")
        + f"：{raw!r}"
    )


def require_scalar_variable_name(*, full_name: str, var_name: str) -> str:
    """
    单点强约束：标量变量名不允许包含 '.'。

    说明：
    - '.' 在本项目中用于表达“字典字段路径”（dict.key），不应写进“标量变量名”本体；
    - 允许的替代写法：把 '.' 替换为 '__' 形成“镜像标量变量名”，并由节点图负责同步写回。
    """
    n = str(var_name or "").strip()
    if n == "":
        raise ValueError("variable_name 不能为空")
    if "." in n:
        suggestion = n.replace(".", "__")
        raise ValueError(
            f"标量变量名禁止包含 '.'：{full_name!r}（variable_name={n!r}）。"
            f"请改用镜像标量变量名（例如 {suggestion!r}），并在节点图中同步写回该标量变量。"
        )
    return n


_MOUSTACHE_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_BRACED_PLACEHOLDER_PATTERN = re.compile(r"\{(\d+)\s*:\s*([^{}]+?)\}")


TextPlaceholderVarRef = tuple[str, str, tuple[str, ...]]


def extract_variable_refs_from_text_placeholders(text: str) -> set[TextPlaceholderVarRef]:
    """从文本中提取占位符引用到的“实体自定义变量引用”（用于写回 root4/5/1）：

    - moustache：{{lv.xxx}} / {{ps.xxx}} / {{p1.xxx}}
    - moustache（字典字段路径）：{{lv.dict.key}} / {{ps.dict.key}}
    - braced：{1:lv.xxx}（把 lv.xxx 视为关卡变量；同样支持 {1:lv.dict.key}）

    返回：{(group_name, variable_name, field_path_parts), ...}
    - group_name：关卡 / 玩家自身
    - variable_name：根变量名（dict 变量时为 dict 名）
    - field_path_parts：
      - ()：标量变量
      - 非空：字典 key 路径（多段会用 '.' 拼成一个键名；写回端会创建字典变量 type_code=27）
    """
    raw_text = str(text or "")
    results: set[TextPlaceholderVarRef] = set()

    def _accept_expr(expr: str) -> None:
        e = str(expr or "").strip()
        if not e:
            return
        if any(ch.isspace() for ch in e):
            return
        scope, sep, rest = e.partition(".")
        if sep != ".":
            return
        scope_lower = scope.strip().lower()
        tail = rest.strip()
        if not tail:
            return
        segments = [s.strip() for s in tail.split(".") if s.strip()]
        if not segments:
            return
        var_name = segments[0]
        field_path = tuple(segments[1:])

        if scope_lower == "ls":
            raise ValueError(f"不支持 UI 文本占位符使用 ls 前缀，请改用 lv：{e!r}")
        if scope_lower == "lv":
            results.add(("关卡", var_name, field_path))
            return
        if scope_lower == "ps" or (scope_lower.startswith("p") and scope_lower[1:].isdigit()):
            results.add(("玩家自身", var_name, field_path))
            return

    for match in _MOUSTACHE_PLACEHOLDER_PATTERN.finditer(raw_text):
        _accept_expr(match.group(1))
    for match in _BRACED_PLACEHOLDER_PATTERN.finditer(raw_text):
        _accept_expr(match.group(2))

    return results

