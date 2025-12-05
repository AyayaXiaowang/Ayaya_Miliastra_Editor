# -*- coding: utf-8 -*-
"""
port_type_common: 端口类型推断通用工具与类型名辅助函数。

职责：
- 提供基础类型与列表类型之间的映射表；
- 收敛“泛型家族/流程类型”这类通用类型名判定逻辑；
- 在声明为列表类型时，将标量推断结果提升为对应的列表类型。

模块定位：
- 作为 `app.automation.ports` 包的内部实现模块，仅供本包内部使用；
- 包外调用方如需使用通用类型工具，应通过
  `app.automation.ports.port_type_inference` 导入由本模块经官方入口
  re-export 的公共符号，而不是直接依赖本模块。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, TypeVar

from engine.nodes.port_type_system import FLOW_PORT_TYPE
from engine.utils.name_utils import dedupe_preserve_order

T = TypeVar("T")



# 基础类型 → 列表类型映射
BASE_TO_LIST_MAP: Dict[str, str] = {
    "实体": "实体列表",
    "GUID": "GUID列表",
    "整数": "整数列表",
    "布尔值": "布尔值列表",
    "浮点数": "浮点数列表",
    "字符串": "字符串列表",
    "三维向量": "三维向量列表",
    "元件ID": "元件ID列表",
    "配置ID": "配置ID列表",
}


def get_non_empty_str(value: object) -> str:
    """将任意对象规范化为去掉首尾空白的非空字符串；否则返回空字符串。

    用途：
    - 统一在类型名/端口类型等场景下做“是字符串且非空白”的判定；
    - 避免在各处重复写 `isinstance(x, str) and x.strip()` 之类的小片段。
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text == "":
        return ""
    return text


def is_non_empty_str(value: object) -> bool:
    """判定 value 是否为“去掉首尾空白后非空”的字符串。"""
    return get_non_empty_str(value) != ""


def is_generic_type_name(type_name: object) -> bool:
    """判定是否为“泛型家族”类型名。

    泛型家族包括：泛型、泛型列表、泛型字典等，以“泛型”开头。
    """
    if not isinstance(type_name, str):
        return False

    text = type_name.strip()
    if text == "":
        # 约定：空字符串视为“泛型家族”的一员，用于表示“未声明/待推断”的占位类型。
        return True
    if text == "泛型" or text.startswith("泛型"):
        return True
    return False


def is_flow_type_name(type_name: object) -> bool:
    """判定是否为“流程”类型名。

    说明：
    - 仅在数据端口类型推断阶段使用，将“流程”视为无效候选；
    - 流程端口本身不会通过类型推断工具参与数据类型推断。
    """
    text = get_non_empty_str(type_name)
    if text == "":
        return False
    return text == FLOW_PORT_TYPE


def is_list_like_type_name(type_name: object) -> bool:
    """判定是否为“列表 / 泛型列表”相关类型名。

    规则：
    - 非字符串直接返回 False；
    - 去除首尾空白后为空字符串返回 False；
    - 其余情况下，只要包含“列表”或等于“泛型列表”即视为列表家族类型。
    """
    text = get_non_empty_str(type_name)
    if text == "":
        return False
    return ("列表" in text) or (text == "泛型列表")


def upgrade_to_list_type(declared_type: str, inferred_scalar: Optional[str]) -> Optional[str]:
    """当端口声明为列表类而候选类型为基础标量时，提升为对应列表类型。

    Args:
        declared_type: 端口声明的类型（可以是列表/泛型列表，也可以是其他类型名）
        inferred_scalar: 从值或上游推断出的“基础标量类型”候选

    Returns:
        提升后的类型或原类型；

    说明：
        - 本函数作为“标量→列表”映射的**唯一入口**，所有需要在“声明为列表类”场景下
          将基础标量升级为对应列表类型的逻辑都应通过此函数完成；
        - 若 `declared_type` 不是列表类，或候选标量为空/无效，则直接返回 `inferred_scalar`，
          调用方可据此判断是否发生了实际的“列表提升”（例如比较前后字符串是否相同）。
    """
    if not isinstance(declared_type, str):
        return inferred_scalar
    if not is_non_empty_str(inferred_scalar):
        return inferred_scalar

    # 仅当“明确为列表类（含 泛型列表）”时，才将基础标量派生为对应“X列表”
    if is_list_like_type_name(declared_type):
        scalar_text = get_non_empty_str(inferred_scalar)
        return BASE_TO_LIST_MAP.get(scalar_text, scalar_text)

    return inferred_scalar


def unique_preserve_order(candidates: Sequence[T]) -> List[T]:
    """按首次出现顺序去重候选序列。

    Args:
        candidates: 候选序列，可以包含重复项。

    Returns:
        去重后的列表，顺序与首次出现顺序一致。
    """
    if not candidates:
        return []

    return dedupe_preserve_order(candidates)


def pick_first_unique(candidates: Sequence[T]) -> Optional[T]:
    """在按顺序去重后选择首个候选。

    空序列返回 None。
    """
    unique_candidates = unique_preserve_order(candidates)
    if not unique_candidates:
        return None
    return unique_candidates[0]


__all__ = [
    "BASE_TO_LIST_MAP",
    "get_non_empty_str",
    "is_non_empty_str",
    "is_generic_type_name",
    "is_flow_type_name",
    "is_list_like_type_name",
    "upgrade_to_list_type",
    "unique_preserve_order",
    "pick_first_unique",
]


