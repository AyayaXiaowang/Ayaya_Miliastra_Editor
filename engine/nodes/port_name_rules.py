from __future__ import annotations

import re
from typing import Dict, Optional

# 兼容范围端口名映射：
# - 定义名形如 <可选前缀><起始数字>~<结束数字>，例："0~99"、"键0~49"、"值0~49"
# - 实例名形如 <相同前缀><数字>，且数字位于区间（含边界），例："0"、"键12"、"值7"
_RANGE_DEF_PATTERN = re.compile(r"^(?P<prefix>\D*?)(?P<start>\d+)\~(?P<end>\d+)$")
_INSTANCE_PATTERN = re.compile(r"^(?P<prefix>\D*?)(?P<index>\d+)$")


def parse_range_definition(defined_name: str) -> Optional[Dict[str, int]]:
    """
    解析范围端口定义名，返回包含 prefix/start/end 的字典；不是范围定义时返回 None。
    """
    m = _RANGE_DEF_PATTERN.match(str(defined_name))
    if not m:
        return None
    return {
        "prefix": m.group("prefix") or "",
        "start": int(m.group("start")),
        "end": int(m.group("end")),
    }


def map_index_to_range_instance(defined_name: str, index: int) -> Optional[str]:
    """
    将范围定义名与"从0开始的序号"映射为具体实例名。
    仅当 defined_name 为范围定义时生效；否则返回 None。
    """
    parsed = parse_range_definition(defined_name)
    if parsed is None:
        return None
    value = int(parsed["start"] + int(index))
    if value > parsed["end"]:
        return None
    return f"{parsed['prefix']}{value}"


def match_range_port_type(port_name: str, declared_types: Dict[str, str]) -> Optional[str]:
    """
    在 declared_types 的键中查找范围端口定义，若 port_name 落在任一范围内则返回对应类型。
    未命中返回 None。
    """
    name_str = str(port_name)
    instance_match = _INSTANCE_PATTERN.match(name_str)
    if not instance_match:
        return None

    prefix_in = str(instance_match.group("prefix") or "")
    idx_in = int(instance_match.group("index"))

    for defined_name, port_type in declared_types.items():
        parsed = parse_range_definition(defined_name)
        if parsed is None:
            continue
        prefix_def = parsed["prefix"]
        if prefix_in != prefix_def:
            continue
        if int(parsed["start"]) <= idx_in <= int(parsed["end"]):
            return port_type
    return None


def get_dynamic_port_type(
    port_name: str,
    declared_types: Dict[str, str],
    default_type: Optional[str] = None,
) -> Optional[str]:
    """
    动态推断端口类型（优先精确匹配，回退范围匹配，最终用 default_type）。
    """
    exact = declared_types.get(port_name)
    if exact:
        return exact

    range_type = match_range_port_type(port_name, declared_types)
    if range_type:
        return range_type

    return default_type
