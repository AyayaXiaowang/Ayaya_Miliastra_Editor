from __future__ import annotations

from typing import Any, Dict

from .refs import parse_variable_ref_text

__all__ = [
    "normalize_variable_defaults_map",
]


def normalize_variable_defaults_map(raw: Any) -> Dict[str, Any]:
    """
    把 Workbench 导出的 `variable_defaults` 归一化为：
      {"关卡.xxx": <value>, "玩家自身.yyy": <value>, ...}

    允许 key 写法（导出端不强约束；写回端统一收口为 canonical）：
    - 关卡.xxx / 玩家自身.xxx
    - lv.xxx / ps.xxx / p1.xxx..p8.xxx
    - {1:lv.xxx}

    字典字段路径规范化：
    - 允许 key 使用 "组.字典.键" 表达“单键默认值”
    - 规范化输出：落到 "组.字典" 的 dict 默认值上（key="键"）
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        key_text = str(k or "").strip()
        if key_text == "":
            continue
        _gid, var_name, full_name = parse_variable_ref_text(key_text, allow_constant_number=False)
        if full_name is None or var_name is None:
            raise ValueError(f"variable_defaults key 非法（必须为变量引用 '组名.变量名'）：{key_text!r}")

        full = str(full_name)
        group_name, _, name_path = full.partition(".")
        if not group_name or not name_path:
            raise ValueError(f"variable_defaults key 非法（必须为变量引用 '组名.变量名'）：{key_text!r}")

        # 统一语义：允许用 "组.字典.键" 给字典变量提供“单个键”的默认值。
        # 规范化输出：落到 "组.字典" 的 dict 上（key="键"），避免下游把 "字典.键" 当作标量变量名。
        if "." in name_path:
            base_name, _, key_path = name_path.partition(".")
            if not base_name or not key_path:
                raise ValueError(f"variable_defaults key 非法（字典字段路径不完整）：{key_text!r}")
            base_full = f"{group_name}.{base_name}"
            existing = out.get(base_full)
            if existing is None:
                out[base_full] = {str(key_path): v}
            elif isinstance(existing, dict):
                existing[str(key_path)] = v
            else:
                raise ValueError(
                    "variable_defaults 同一变量名既出现标量默认值又出现字典字段默认值，语义冲突："
                    f"{base_full!r}（已有类型={type(existing).__name__}，新增键={key_path!r}）"
                )
            continue

        # 允许直接提供整张字典默认值：{"组.字典": {"k": 1, ...}}
        if isinstance(v, dict):
            existing = out.get(full)
            if existing is None:
                out[full] = dict(v)
            elif isinstance(existing, dict):
                # merge：后者覆盖前者（稳定）
                existing.update(dict(v))
            else:
                raise ValueError(
                    "variable_defaults 同一变量名既出现标量默认值又出现字典默认值，语义冲突："
                    f"{full!r}（已有类型={type(existing).__name__}）"
                )
            continue

        # 标量默认值：直接落盘
        existing = out.get(full)
        if isinstance(existing, dict):
            raise ValueError(
                "variable_defaults 同一变量名既出现字典默认值又出现标量默认值，语义冲突："
                f"{full!r}（已有类型=dict，新增标量={v!r}）"
            )
        out[full] = v
    return out

