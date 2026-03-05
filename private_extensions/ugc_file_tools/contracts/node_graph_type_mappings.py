from __future__ import annotations

"""
ugc_file_tools.contracts.node_graph_type_mappings

单一真源：GIA 导出 / GIL 写回共同依赖的 node_data/index.json TypeMappings 解析规则。

背景：
- `.gia` 导出需要根据 TypeMappings 选择 NodeInstance.concrete_id 与 pins 的 indexOfConcrete；
- `.gil` 写回同样需要在“能确定主泛型/字典 K/V”时同步 concrete runtime_id 与 indexOfConcrete；
- 这些规则如果分散在多个模块，极易出现“只改了一半”。

本模块只关心 TypeMappings 的文本约定与字段形态，不依赖具体导出/写回流程。
"""

from typing import Any


def map_type_mapping_token_to_server_var_type_int(type_token: str) -> int | None:
    """
    将 node_data/index.json TypeMappings 的 token（如 Ety / Int / Str / L<Int>）映射为 server VarType(int)。
    """
    token = str(type_token or "").strip()
    if token == "":
        return None
    base_map: dict[str, int] = {
        "Ety": 1,
        "Gid": 2,
        "Int": 3,
        "Bol": 4,
        "Flt": 5,
        "Str": 6,
        "Vec": 12,
        "Fct": 17,
        "Cfg": 20,
        "Pfb": 21,
    }
    if token in base_map:
        return int(base_map[token])
    if token.startswith("L<") and token.endswith(">") and len(token) > 3:
        inner = token[2:-1].strip()
        elem = map_type_mapping_token_to_server_var_type_int(inner)
        if elem is None:
            return None
        list_map: dict[int, int] = {
            1: 13,  # EtyList
            2: 7,  # GidList
            3: 8,  # IntList
            4: 9,  # BoolList
            5: 10,  # FloatList
            6: 11,  # StringList
            12: 15,  # VecList
            17: 24,  # FctList / CampList
            20: 22,  # CfgList
            21: 23,  # PfbList / ComponentIdList
        }
        return int(list_map.get(int(elem))) if int(elem) in list_map else None
    return None


def try_map_list_var_type_to_element_var_type_int(list_var_type_int: int) -> int | None:
    """
    将 server “列表 VarType”反解为其“元素 VarType”。

    背景：
    - 一些泛型节点的主泛型 `T` 体现在 TypeMappings.Type（例如 `S<T:Ety>`），
      但其端口类型表达式可能是 `L<R<T>>`（列表容器包裹反射泛型）。
    - 此时写回/推断侧如果只拿到了端口 VarType（例如 实体列表=13），仍需要能回推到 `T=实体(1)`，
      才能用 TypeMappings 反推出 concrete_id / indexOfConcrete。

    返回 None：表示不是已知的列表 VarType。
    """
    vt = int(list_var_type_int)
    list_elem_type_map: dict[int, int] = {
        7: 2,  # GUID列表 -> GUID
        8: 3,  # 整数列表 -> 整数
        9: 4,  # 布尔值列表 -> 布尔值
        10: 5,  # 浮点数列表 -> 浮点数
        11: 6,  # 字符串列表 -> 字符串
        13: 1,  # 实体列表 -> 实体
        15: 12,  # 三维向量列表 -> 三维向量
        22: 20,  # 配置ID列表 -> 配置ID
        23: 21,  # 元件ID列表 -> 元件ID
        24: 17,  # 阵营列表 -> 阵营
        26: 25,  # 结构体列表 -> 结构体
    }
    out = list_elem_type_map.get(int(vt))
    return int(out) if isinstance(out, int) else None


def _try_parse_generic_two_tokens(inner: str) -> tuple[str, str] | None:
    """
    解析形如 `X<A,B>` 的 inner（已去掉外层前缀/后缀）为两个 token。

    约束：仅用于 TypeMappings 文本；token 内可能嵌套泛型（如 D<Int,Gid>），因此需要按 <> 深度切分。
    """
    s = str(inner or "").strip()
    if s == "":
        return None
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            if depth > 0:
                depth -= 1
        if ch == "," and depth == 0:
            token = "".join(buf).strip()
            if token != "":
                parts.append(token)
            buf = []
            continue
        buf.append(ch)
    last = "".join(buf).strip()
    if last != "":
        parts.append(last)
    if len(parts) != 2:
        return None
    return str(parts[0]).strip(), str(parts[1]).strip()


def try_parse_kv_type_mapping_text(type_text: str) -> tuple[str, str] | None:
    """
    解析字典 K/V 双泛型映射：
    - TypeMappings.Type: `S<K:Int,V:Str>` / `S<K:Ety,V:Int>` 等。
    返回 (K_token, V_token)。
    """
    text = str(type_text or "").strip()
    if not text.startswith("S<") or not text.endswith(">"):
        return None
    inner = text[2:-1].strip()
    if inner == "":
        return None
    # 允许出现多余字段，但必须能抽到 K/V。
    fields = [p.strip() for p in inner.split(",") if p.strip() != ""]
    k_token = None
    v_token = None
    for f in fields:
        if f.startswith("K:"):
            k_token = f[len("K:") :].strip()
        elif f.startswith("V:"):
            v_token = f[len("V:") :].strip()
    if not k_token or not v_token:
        return None
    return str(k_token), str(v_token)


def try_parse_t_dict_type_mapping_text(type_text: str) -> tuple[str, str] | None:
    """
    解析单泛型 T=字典映射：
    - TypeMappings.Type: `S<T:D<Int,Gid>>`
    返回 (K_token, V_token)。
    """
    text = str(type_text or "").strip()
    if not text.startswith("S<T:") or not text.endswith(">"):
        return None
    inner = text[len("S<T:") : -1].strip()
    if not inner.startswith("D<") or not inner.endswith(">"):
        return None
    inner2 = inner[len("D<") : -1].strip()
    return _try_parse_generic_two_tokens(inner2)


def try_resolve_t_dict_concrete_mapping(
    *,
    node_entry_by_id: dict[int, dict[str, Any]],
    node_type_id_int: int,
    dict_key_vt: int,
    dict_value_vt: int,
) -> tuple[int, int | None, int | None] | None:
    """
    针对 TypeMappings.Type 形如 `S<T:D<K,V>>` 的“单泛型 T=字典”节点：
    基于 (K,V) VarType 解析 concrete_id 与该节点的 T 端口 indexOfConcrete。

    返回：
    - concrete_id（NodeInstance.concrete_id.runtime_id）
    - in_index_of_concrete（InputsIndexOfConcrete 中的唯一 int；若不唯一则 None）
    - out_index_of_concrete（OutputsIndexOfConcrete 中的唯一 int；若不唯一则 None）
    """
    entry = node_entry_by_id.get(int(node_type_id_int))
    if not isinstance(entry, dict):
        return None
    mappings = entry.get("TypeMappings")
    if not isinstance(mappings, list):
        return None

    wanted_k = int(dict_key_vt)
    wanted_v = int(dict_value_vt)

    for m in list(mappings):
        if not isinstance(m, dict):
            continue
        concrete_id = m.get("ConcreteId")
        type_text = m.get("Type")
        indices = m.get("InputsIndexOfConcrete")
        output_indices = m.get("OutputsIndexOfConcrete")
        if not isinstance(concrete_id, int) or int(concrete_id) <= 0:
            continue
        if not isinstance(type_text, str) or type_text.strip() == "":
            continue

        parsed = try_parse_t_dict_type_mapping_text(str(type_text))
        if parsed is None:
            continue
        k_token, v_token = parsed
        k_vt = map_type_mapping_token_to_server_var_type_int(str(k_token))
        v_vt = map_type_mapping_token_to_server_var_type_int(str(v_token))
        if not (isinstance(k_vt, int) and isinstance(v_vt, int)):
            continue
        if int(k_vt) != wanted_k or int(v_vt) != wanted_v:
            continue

        in_idx: int | None = None
        out_idx: int | None = None

        if isinstance(indices, list):
            in_candidates = [int(x) for x in indices if isinstance(x, int)]
            if len(in_candidates) == 1:
                in_idx = int(in_candidates[0])

        if isinstance(output_indices, list):
            out_candidates = [int(x) for x in output_indices if isinstance(x, int)]
            if len(out_candidates) == 1:
                out_idx = int(out_candidates[0])

        return int(concrete_id), in_idx, out_idx

    return None


def try_resolve_dict_kv_concrete_mapping(
    *,
    node_entry_by_id: dict[int, dict[str, Any]],
    node_type_id_int: int,
    dict_key_vt: int,
    dict_value_vt: int,
) -> tuple[int, dict[str, int]] | None:
    """
    针对输入包含 `D<R<K>,R<V>>` 的字典泛型节点，基于 (K,V) VarType 解析 concrete_id 与各输入端口的 indexOfConcrete。

    返回：
    - concrete_id（NodeInstance.concrete_id.runtime_id）
    - index_of_concrete_by_port_name（覆盖 {"字典","键","值"} 的已知项；未命中时为 0）

    兼容说明：
    - 不同字典节点的 InputsIndexOfConcrete 长度不一致：
      - 3 项：常见于「字典/键/值」三输入节点；
      - 2 项：常见于「字典/键」节点（例如 Query_Dictionary_Value_by_Key），其「值」索引来自 OutputsIndexOfConcrete。
    """
    entry = node_entry_by_id.get(int(node_type_id_int))
    if not isinstance(entry, dict):
        return None
    mappings = entry.get("TypeMappings")
    if not isinstance(mappings, list):
        return None

    wanted_k = int(dict_key_vt)
    wanted_v = int(dict_value_vt)

    for m in list(mappings):
        if not isinstance(m, dict):
            continue
        concrete_id = m.get("ConcreteId")
        type_text = m.get("Type")
        indices = m.get("InputsIndexOfConcrete")
        output_indices = m.get("OutputsIndexOfConcrete")
        if not isinstance(concrete_id, int) or int(concrete_id) <= 0:
            continue
        if not isinstance(type_text, str) or type_text.strip() == "":
            continue
        parsed = try_parse_kv_type_mapping_text(str(type_text))
        if parsed is None:
            continue
        k_token, v_token = parsed
        k_vt = map_type_mapping_token_to_server_var_type_int(str(k_token))
        v_vt = map_type_mapping_token_to_server_var_type_int(str(v_token))
        if not (isinstance(k_vt, int) and isinstance(v_vt, int)):
            continue
        if int(k_vt) != wanted_k or int(v_vt) != wanted_v:
            continue
        if not isinstance(indices, list) or len(indices) < 2:
            continue
        idx_dict = int(indices[0]) if isinstance(indices[0], int) else 0
        idx_key = int(indices[1]) if isinstance(indices[1], int) else 0
        if len(indices) >= 3 and isinstance(indices[2], int):
            idx_val = int(indices[2])
        elif isinstance(output_indices, list) and output_indices and isinstance(output_indices[0], int):
            idx_val = int(output_indices[0])
        else:
            idx_val = 0
        return int(concrete_id), {"字典": int(idx_dict), "键": int(idx_key), "值": int(idx_val)}

    return None


def resolve_concrete_id_from_node_data_type_mappings(
    *,
    node_entry_by_id: dict[int, dict[str, Any]],
    node_type_id_int: int,
    var_type_int: int,
) -> int | None:
    """
    尝试用 node_data/index.json 的 TypeMappings 反推 Variant/Generic 节点的 concrete_id(runtime_id)。
    - node_type_id_int: generic id
    - var_type_int: 该节点“主泛型 T”对应的 server VarType

    仅覆盖 `S<T:...>` 形态（基础类型与 L<...> 列表）。
    """
    entry = node_entry_by_id.get(int(node_type_id_int))
    if not isinstance(entry, dict):
        return None
    mappings = entry.get("TypeMappings")
    if not isinstance(mappings, list):
        return None

    def _find_concrete_id_for_t_vt(wanted_t_vt: int) -> int | None:
        for m in list(mappings):
            if not isinstance(m, dict):
                continue
            concrete_id = m.get("ConcreteId")
            type_text = m.get("Type")
            if not isinstance(concrete_id, int) or int(concrete_id) <= 0:
                continue
            if not isinstance(type_text, str) or type_text.strip() == "":
                continue

            text = str(type_text).strip()
            if not text.startswith("S<T:") or not text.endswith(">"):
                continue
            inner = text[len("S<T:") : -1].strip()
            vt = map_type_mapping_token_to_server_var_type_int(inner)
            if isinstance(vt, int) and int(vt) == int(wanted_t_vt):
                return int(concrete_id)
        return None

    wanted = int(var_type_int)
    resolved = _find_concrete_id_for_t_vt(int(wanted))
    if isinstance(resolved, int) and int(resolved) > 0:
        return int(resolved)

    # 兼容：当调用方给的是“列表容器 VarType(L<T>)”（例如 实体列表=13），但 TypeMappings 是 `S<T:Ety>` 时，
    # 需要反解出元素类型（例如 Ety=1）再命中 concrete 映射（典型：列表迭代循环、获取列表对应值 等）。
    elem_vt = try_map_list_var_type_to_element_var_type_int(int(wanted))
    if isinstance(elem_vt, int) and int(elem_vt) > 0:
        resolved2 = _find_concrete_id_for_t_vt(int(elem_vt))
        if isinstance(resolved2, int) and int(resolved2) > 0:
            return int(resolved2)

    return None


def try_resolve_t_concrete_mapping(
    *,
    node_entry_by_id: dict[int, dict[str, Any]],
    node_type_id_int: int,
    var_type_int: int,
) -> tuple[int, int | None, int | None] | None:
    """
    针对 TypeMappings.Type 形如 `S<T:...>`（基础类型与 `L<...>` 列表）的单泛型节点：
    基于主泛型 T 的 server VarType 解析 concrete_id 与该节点的 in/out indexOfConcrete。

    返回：
    - concrete_id（NodeInstance.concrete_id.runtime_id / NodeProperty.runtime_id）
    - in_index_of_concrete（InputsIndexOfConcrete 中的唯一 int；若不唯一则 None）
    - out_index_of_concrete（OutputsIndexOfConcrete 中的唯一 int；若不唯一则 None）

    注意：
    - 本解析器不尝试对“多泛型端口/多 indexOfConcrete”做端口级映射；仅在候选唯一时返回。
    - 典型用例：
      - Get_Node_Graph_Variable(337) 的 Vec 输出：OutputsIndexOfConcrete=[11]
      - Set_Node_Graph_Variable(323) 的 Vec 输入：InputsIndexOfConcrete=[null,11,null]
    """
    entry = node_entry_by_id.get(int(node_type_id_int))
    if not isinstance(entry, dict):
        return None
    mappings = entry.get("TypeMappings")
    if not isinstance(mappings, list):
        return None

    wanted = int(var_type_int)
    for m in list(mappings):
        if not isinstance(m, dict):
            continue
        concrete_id = m.get("ConcreteId")
        type_text = m.get("Type")
        indices = m.get("InputsIndexOfConcrete")
        output_indices = m.get("OutputsIndexOfConcrete")
        if not isinstance(concrete_id, int) or int(concrete_id) <= 0:
            continue
        if not isinstance(type_text, str) or type_text.strip() == "":
            continue

        text = str(type_text).strip()
        if not text.startswith("S<T:") or not text.endswith(">"):
            continue
        inner = text[len("S<T:") : -1].strip()
        # 字典映射交由 try_resolve_t_dict_concrete_mapping 处理
        if inner.startswith("D<") and inner.endswith(">"):
            continue
        vt = map_type_mapping_token_to_server_var_type_int(inner)
        if not (isinstance(vt, int) and int(vt) == wanted):
            continue

        in_idx: int | None = None
        out_idx: int | None = None

        if isinstance(indices, list):
            in_candidates = [int(x) for x in indices if isinstance(x, int)]
            if len(in_candidates) == 1:
                in_idx = int(in_candidates[0])

        if isinstance(output_indices, list):
            out_candidates = [int(x) for x in output_indices if isinstance(x, int)]
            if len(out_candidates) == 1:
                out_idx = int(out_candidates[0])

        return int(concrete_id), in_idx, out_idx

    return None


__all__ = [
    "map_type_mapping_token_to_server_var_type_int",
    "try_map_list_var_type_to_element_var_type_int",
    "try_parse_kv_type_mapping_text",
    "try_parse_t_dict_type_mapping_text",
    "try_resolve_t_dict_concrete_mapping",
    "try_resolve_dict_kv_concrete_mapping",
    "resolve_concrete_id_from_node_data_type_mappings",
    "try_resolve_t_concrete_mapping",
]

