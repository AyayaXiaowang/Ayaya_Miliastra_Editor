from __future__ import annotations

"""
VarType 映射单一真源。

说明：
- Graph_Generater 的中文端口类型（如 "整数"/"字符串列表"）在 `.gil/.gia` 侧需要落到 VarType(int)。
- 这里提供“严格/宽松”两套接口，避免各工具脚本复制一份 mapping 后逐渐漂移。
"""

from typing import Dict, Optional


SERVER_PORT_TYPE_TEXT_TO_VAR_TYPE_ID: Dict[str, int] = {
    "实体": 1,
    "GUID": 2,
    "整数": 3,
    "布尔值": 4,
    "浮点数": 5,
    "字符串": 6,
    "GUID列表": 7,
    "整数列表": 8,
    # 经验口径：枚举列表在底层通常以“枚举 item_id 的整数列表”表达（VarType=8）。
    "枚举列表": 8,
    "布尔值列表": 9,
    "浮点数列表": 10,
    "字符串列表": 11,
    "三维向量": 12,
    "实体列表": 13,
    "枚举": 14,
    "三维向量列表": 15,
    "局部变量": 16,
    "阵营": 17,
    "配置ID": 20,
    "元件ID": 21,
    "配置ID列表": 22,
    "元件ID列表": 23,
    "阵营列表": 24,
    "结构体": 25,
    "结构体列表": 26,
    "字典": 27,
    "自定义变量快照": 28,
}

# 反向映射（VarType(int) -> 中文类型名）。
#
# 注意：
# - text->id 存在别名（例如 "枚举列表" 与 "整数列表" 都映射到 8），因此反向映射必须显式指定“canonical 文本”。
# - 该反向映射用于“导入/解析”侧（例如从 .gia 自定义变量条目还原出变量类型文本）。
VAR_TYPE_ID_TO_SERVER_PORT_TYPE_TEXT: Dict[int, str] = {
    1: "实体",
    2: "GUID",
    3: "整数",
    4: "布尔值",
    5: "浮点数",
    6: "字符串",
    7: "GUID列表",
    8: "整数列表",
    9: "布尔值列表",
    10: "浮点数列表",
    11: "字符串列表",
    12: "三维向量",
    13: "实体列表",
    14: "枚举",
    15: "三维向量列表",
    16: "局部变量",
    17: "阵营",
    20: "配置ID",
    21: "元件ID",
    22: "配置ID列表",
    23: "元件ID列表",
    24: "阵营列表",
    25: "结构体",
    26: "结构体列表",
    27: "字典",
    28: "自定义变量快照",
}


def _looks_like_dict_alias_text(port_type_text: str) -> bool:
    t = str(port_type_text or "").strip()
    if t == "":
        return False
    # 兼容复合类型展示名：例如 "字符串-整数字典" / "字符串-GUID字典" / "字典(字符串→整数)"
    if t.endswith("字典"):
        return True
    if t.startswith("字典(") and t.endswith(")"):
        return True
    return False


def try_map_server_port_type_text_to_var_type_id(port_type_text: str) -> Optional[int]:
    """宽松映射：无法映射返回 None。"""
    t = str(port_type_text or "").strip()
    if t == "":
        return None
    if _looks_like_dict_alias_text(t):
        return 27
    vt = SERVER_PORT_TYPE_TEXT_TO_VAR_TYPE_ID.get(t)
    return int(vt) if isinstance(vt, int) else None


def map_server_port_type_text_to_var_type_id_or_raise(port_type_text: str) -> int:
    """严格映射：无法映射直接抛错（fail-fast）。"""
    vt = try_map_server_port_type_text_to_var_type_id(str(port_type_text))
    if not isinstance(vt, int):
        raise ValueError(f"尚无法将端口类型映射为 VarType（请补齐映射或提供样本节点图）：{port_type_text!r}")
    return int(vt)


def try_map_var_type_id_to_server_port_type_text(var_type_id: int) -> Optional[str]:
    """宽松映射：无法映射返回 None。"""
    if not isinstance(var_type_id, int):
        return None
    text = VAR_TYPE_ID_TO_SERVER_PORT_TYPE_TEXT.get(int(var_type_id))
    return str(text) if isinstance(text, str) and str(text).strip() != "" else None


def map_var_type_id_to_server_port_type_text_or_raise(var_type_id: int) -> str:
    """严格映射：无法映射直接抛错（fail-fast）。"""
    text = try_map_var_type_id_to_server_port_type_text(int(var_type_id))
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError(f"尚无法将 VarType(int) 映射为中文类型名：{var_type_id!r}")
    return str(text).strip()

