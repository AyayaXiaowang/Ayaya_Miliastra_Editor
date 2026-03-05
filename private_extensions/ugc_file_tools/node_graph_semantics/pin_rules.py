from __future__ import annotations

from typing import Any, Optional

from ugc_file_tools.contracts.node_graph_type_mappings import (
    map_type_mapping_token_to_server_var_type_int as _map_type_mapping_token_to_server_vt,
    try_map_list_var_type_to_element_var_type_int as _try_map_list_vt_to_elem_vt,
)
from ugc_file_tools.node_data_index import load_node_entry_by_id_map, resolve_default_node_data_index_path

from .genshin_ts_node_schema import try_resolve_index_of_concrete_from_genshin_ts


_NODE_ENTRY_BY_ID_CACHE: dict[int, dict[str, Any]] | None = None
_NODE_ENTRY_BY_ID_LOADED: bool = False


# ---------------------------- Pin index mapping constants ----------------------------
# 说明：
# - Graph_Generater 的 GraphModel 里，某些节点会“隐藏/不暴露”底层 NodeDef 的部分输入端口；
# - 但 `.gil` NodePin 记录使用的是底层 NodeDef 的 InParam.index（shell index）；
# - 因此写回侧需要对这类节点做 slot_index→pin_index 的显式映射，避免端口整体错位。
#
# 创建元件（Create_Prefab, node_type_id=252）：
# - NodeEditorPack/真源端口布局包含两个连续的实体输入（Ety, Ety），但 GraphModel 只暴露“拥有者实体”一个端口；
# - 导致从“是否覆写等级/等级/单位标签索引列表”开始，GraphModel 的 slot_index 相对底层 NodeDef 需要整体 +1。
CREATE_PREFAB_WRAPPER_NODE_TITLE = "创建元件"
CREATE_PREFAB_HIDDEN_INPARAM_OFFSET_AFTER_OWNER_ENTITY = 1
CREATE_PREFAB_PORT_NAMES_NEED_OFFSET: frozenset[str] = frozenset(
    {
        "是否覆写等级",
        "等级",
        "单位标签索引列表",
    }
)


def _get_node_entry_by_id_map() -> dict[int, dict[str, Any]]:
    global _NODE_ENTRY_BY_ID_CACHE, _NODE_ENTRY_BY_ID_LOADED
    if _NODE_ENTRY_BY_ID_LOADED:
        return dict(_NODE_ENTRY_BY_ID_CACHE or {})

    _NODE_ENTRY_BY_ID_LOADED = True
    _NODE_ENTRY_BY_ID_CACHE = load_node_entry_by_id_map(resolve_default_node_data_index_path())
    if not isinstance(_NODE_ENTRY_BY_ID_CACHE, dict):
        _NODE_ENTRY_BY_ID_CACHE = {}
    return dict(_NODE_ENTRY_BY_ID_CACHE)


def _try_resolve_index_of_concrete_from_node_data_type_mappings(
    *,
    node_type_id_int: int,
    is_input: bool,
    pin_index: int,
    var_type_int: int,
) -> Optional[int]:
    """
    node_data/index.json TypeMappings 兜底：当 genshin-ts ConcreteMap 缺失/未命中时，
    尝试从 `S<T:...>`（非字典）映射中解析当前 pin 的 indexOfConcrete。

    约定：
    - 仅处理单泛型 `T`（`S<T:...>`）且 inner 不是 `D<...>` 的映射；
    - `pin_index` 以 data pin 的 index（IN_PARAM/OUT_PARAM 的 index）为准；
    - 返回 0 视为有效（但上游写 ConcreteBase 时通常会省略写入 0）。
    """
    node_entry = _get_node_entry_by_id_map().get(int(node_type_id_int))
    if not isinstance(node_entry, dict):
        return None

    mappings = node_entry.get("TypeMappings")
    if not isinstance(mappings, list):
        return None

    wanted_vt = int(var_type_int)
    key = "InputsIndexOfConcrete" if bool(is_input) else "OutputsIndexOfConcrete"

    def _try_find_kv(*, wanted_param_vt: int, match_param: str) -> Optional[int]:
        """
        解析 `S<K:...,V:...>` 的双泛型映射。

        重要约定（经 node_data 校准样本验证）：
        - 多数字典泛型节点（如 Query_Dictionary_Value_by_Key）的 `indexOfConcrete` 选择分属 K/V 两个泛型组；
        - 当我们要为某个 pin 写 `indexOfConcrete` 时，需要明确是按 K 还是按 V 去匹配：
          - output pins 通常对应 `V`（例如输出 `R<V>`）
          - input pins 通常对应 `K`（例如输入 `R<K>`）
        - 本函数只做“最小稳定兜底”：仅按 `match_param` 指定的 K 或 V 进行匹配，避免输出 pin 被 K 命中后误选到错误 mapping。
        """
        for m in list(mappings):
            if not isinstance(m, dict):
                continue
            type_text = m.get("Type")
            if not isinstance(type_text, str) or type_text.strip() == "":
                continue
            text = str(type_text).strip()
            if not (text.startswith("S<K:") and text.endswith(">") and ",V:" in text):
                continue
            inner = text[len("S<") : -1].strip()
            # inner: "K:xxx,V:yyy"
            if not inner.startswith("K:") or ",V:" not in inner:
                continue
            k_part, v_part = inner.split(",V:", 1)
            if not k_part.startswith("K:"):
                continue
            k_token = k_part[len("K:") :].strip()
            v_token = str(v_part).strip()
            if k_token == "" or v_token == "":
                continue

            token = k_token if str(match_param) == "K" else v_token
            mapped = _map_type_mapping_token_to_server_vt(str(token))
            if not (isinstance(mapped, int) and int(mapped) == int(wanted_param_vt)):
                continue

            indices = m.get(key)
            if not isinstance(indices, list):
                continue
            if int(pin_index) < 0 or int(pin_index) >= len(indices):
                continue
            raw = indices[int(pin_index)]
            if isinstance(raw, int):
                return int(raw)
        return None

    def _try_find(*, wanted_t_vt: int) -> Optional[int]:
        for m in list(mappings):
            if not isinstance(m, dict):
                continue
            type_text = m.get("Type")
            if not isinstance(type_text, str) or type_text.strip() == "":
                continue
            text = str(type_text).strip()
            if not text.startswith("S<T:") or not text.endswith(">"):
                continue
            inner = text[len("S<T:") : -1].strip()
            # 字典映射不在此函数处理
            if inner.startswith("D<") and inner.endswith(">"):
                continue
            mapped = _map_type_mapping_token_to_server_vt(inner)
            if not (isinstance(mapped, int) and int(mapped) == int(wanted_t_vt)):
                continue

            indices = m.get(key)
            if not isinstance(indices, list):
                continue
            if int(pin_index) < 0 or int(pin_index) >= len(indices):
                continue
            raw = indices[int(pin_index)]
            if isinstance(raw, int):
                return int(raw)
        return None

    # 先按“端口 VarType”直匹配（兼容 TypeMappings 中存在 `S<T:L<...>>` 的节点）。
    direct = _try_find(wanted_t_vt=int(wanted_vt))
    if isinstance(direct, int):
        return int(direct)

    # 双泛型 K/V 字典节点兜底：输出 pin 优先匹配 V；输入 pin 优先匹配 K。
    kv = _try_find_kv(
        wanted_param_vt=int(wanted_vt),
        match_param=("K" if bool(is_input) else "V"),
    )
    if isinstance(kv, int):
        return int(kv)

    # 再按“列表容器 VarType(L<T>) → 元素 VarType(T)”回退匹配（典型：输入端口为 `L<R<T>>` 的列表泛型节点）。
    elem_vt = _try_map_list_vt_to_elem_vt(int(wanted_vt))
    if isinstance(elem_vt, int):
        resolved2 = _try_find(wanted_t_vt=int(elem_vt))
        if isinstance(resolved2, int):
            return int(resolved2)

    return None


def _infer_index_of_concrete_for_generic_pin(
    *,
    node_title: str,
    port_name: str,
    is_input: bool,
    var_type_int: Optional[int] = None,
    node_type_id_int: Optional[int] = None,
    pin_index: Optional[int] = None,
) -> Optional[int]:
    """推断 ConcreteBaseValue.indexOfConcrete。

    说明：
    - indexOfConcrete 在部分“泛型/反射端口”中用于区分同一节点内不同泛型组（例如拼装字典的键/值）。
    - 该字段目前缺少完备的 schema/表驱动来源，因此仅对少数已验证节点做小范围推断。
    - 某些节点的 indexOfConcrete 与具体 VarType 强相关，因此允许调用方传入 `var_type_int` 协助推断。
    """
    title = str(node_title or "").strip()
    port = str(port_name or "").strip()
    vt = int(var_type_int) if isinstance(var_type_int, int) else None

    # 优先使用 genshin-ts 的 ConcreteMap（真源口径）推断 indexOfConcrete。
    # 该映射表比人工经验更稳定，可覆盖更多泛型/反射端口节点。
    if isinstance(node_type_id_int, int) and isinstance(pin_index, int) and isinstance(vt, int):
        resolved = try_resolve_index_of_concrete_from_genshin_ts(
            node_type_id_int=int(node_type_id_int),
            is_input=bool(is_input),
            pin_index=int(pin_index),
            var_type_int=int(vt),
        )
        if isinstance(resolved, int):
            return int(resolved)

    if title == "拼装字典":
        # 校准样本观察：
        # - 配置ID-整数：键侧 index=5，值侧 index=2
        # - 字符串-字符串：键侧 index=3，值侧 index=5
        # - GUID-布尔：键侧 index=1，值侧 index=3
        # - 字符串-浮点数：键侧 index=3，值侧 index=4
        # - 实体-实体：通常不写 indexOfConcrete（None）
        #
        # 结论：该节点的 indexOfConcrete 与“键/值位置 + 具体 VarType”共同决定。
        if not bool(is_input):
            return None
        if port.startswith("键"):
            if vt == 2:  # GUID
                return 1
            if vt == 3:  # 整数
                return 2
            if vt == 6:  # 字符串
                return 3
            if vt == 17:  # 阵营（经验：键侧排在字符串之后）
                return 4
            if vt == 20:  # 配置ID
                return 5
            if vt == 1:  # 实体
                return None
            # 兜底：保持为空（避免写错导致编辑器推断异常）
            return None
        if port.startswith("值"):
            if vt == 2:  # GUID
                return 1
            if vt == 3:  # 整数
                return 2
            if vt == 4:  # 布尔
                return 3
            if vt == 5:  # 浮点数
                return 4
            if vt == 6:  # 字符串
                return 5
            if vt == 13:  # 实体列表
                # 真源样本：整数-实体列表字典 的值侧使用 indexOfConcrete=11
                return 11
            if vt == 1:  # 实体
                return None
            return None
        return None

    if title == "获取局部变量":
        # 校准样本观察：indexOfConcrete 与“值类型(VarType)”强相关。
        #
        # 注：
        # - 该节点在真源/NodeEditorPack 中的泛型收敛集合可由 genshin-ts concrete_map 推导：
        #   - concrete_pins: "18:3:0" / "18:4:1"
        #   - maps[4] = [Bol, Int, Str, Ety, Gid, Flt, Vec, IntList, StrList, EtyList, GidList, FltList, VecList, BolList, Cfg, Pfb, CfgList, PfbList, Fct, FctList]
        # - 这里保留一份“无外部表依赖”的显式映射，作为 concrete_map 缺失/未命中时的稳定兜底。
        if port in {"初始值", "值"}:
            mapping: dict[int, int] = {
                4: 0,   # 布尔值
                3: 1,   # 整数
                6: 2,   # 字符串
                1: 3,   # 实体
                2: 4,   # GUID
                5: 5,   # 浮点数
                12: 6,  # 三维向量
                8: 7,   # 整数列表
                11: 8,  # 字符串列表
                13: 9,  # 实体列表
                7: 10,  # GUID列表
                10: 11, # 浮点数列表
                15: 12, # 三维向量列表
                9: 13,  # 布尔值列表
                20: 14, # 配置ID
                21: 15, # 元件ID
                22: 16, # 配置ID列表
                23: 17, # 元件ID列表
                17: 18, # 阵营
                24: 19, # 阵营列表
            }
            if isinstance(vt, int) and vt in mapping:
                return int(mapping[int(vt)])
            # 兼容旧口径：未提供 var_type 时按历史样本回退为 4
            if vt is None:
                return 4
        return None

    if title == "拼装列表":
        # 校准样本（列表正确.gil）：
        # - 实体列表：元素 pins 使用 indexOfConcrete=2；OutParam(实体列表) 也使用 2
        # - 浮点数列表：元素 pins(vt=5) 与 OutParam(浮点数列表 vt=10) 均使用 indexOfConcrete=4
        #
        # 注意：这里只覆盖“已验证且需要强制写入”的少数类型；其余类型应继续走下方
        # `node_data TypeMappings` 兜底（例如 字符串/字符串列表 的 indexOfConcrete=1）。
        if bool(is_input):
            if vt == 1:
                return 2
            if vt == 5:
                return 4
        else:
            # outparam
            if vt == 13:
                return 2
            if vt == 10:
                return 4

    if title == "以键对字典移除键值对":
        # 校准样本：键为字符串时使用 indexOfConcrete=3
        if bool(is_input) and port == "键" and vt == 6:
            return 3
        return None

    if title == "对字典设置或新增键值对":
        # 真源样本：字符串字典场景下 键=3，值=5
        if not bool(is_input):
            return None
        if vt == 6 and port == "键":
            return 3
        if vt == 6 and port == "值":
            return 5
        return None

    # node_data TypeMappings 兜底：覆盖像【是否相等(Equal, 14)】这类 `S<T:...>` 单泛型节点。
    # 目的：当 genshin-ts ConcreteMap 不可用时，仍能写出非零 indexOfConcrete（例如 Ety=2），
    # 避免导入编辑器后回退到默认 concrete（常见表现：端口类型显示为字符串）。
    if isinstance(node_type_id_int, int) and isinstance(pin_index, int) and isinstance(vt, int):
        resolved2 = _try_resolve_index_of_concrete_from_node_data_type_mappings(
            node_type_id_int=int(node_type_id_int),
            is_input=bool(is_input),
            pin_index=int(pin_index),
            var_type_int=int(vt),
        )
        if isinstance(resolved2, int):
            return int(resolved2)

    return None


def _map_inparam_pin_index_for_node(*, node_title: str, port_name: str, slot_index: int) -> int:
    """将 GraphModel 的 data_inputs slot_index 映射为 GIL NodePin.InParam.index。

    背景：部分变参/动态端口节点在存档内部有 index 偏移或成对布局：
    - 拼装字典：OutParam.index=0，InParam 从 1 开始（键0=1, 值0=2, 键1=3, 值1=4...）
    - 拼装列表：InParam.index=0 为“元素数量”，元素端口从 1 开始（元素0=1, 元素1=2, ...）。
    """
    title = str(node_title or "").strip()
    port = str(port_name or "").strip()
    slot = int(slot_index)

    if title == "拼装字典":
        # GraphModel 的 data_inputs 顺序是 键0,值0,键1,值1,... → 与 record index=slot+1 对齐
        return int(slot + 1)

    if title == "拼装列表":
        # 对齐样本（test4 校准图）：pin0 为“元素数量”，元素输入端口从 pin1 开始。
        # GraphModel 的输入端口名通常为 "0"/"1"/"2"...（元素序号）。
        if port.isdigit():
            return int(port) + 1
        return int(slot) + 1

    if title == "修改结构体":
        # 真源样本（学习结构体的节点图怎么用.gil）观察：
        # - InParam.index=0：结构体实例（Struct）
        # - InParam.index=1：结构体名（选择端口，通常不以 InParam record 写入）
        # - 字段赋值端口按『字段值 + 是否修改』成对出现：
        #   - 字段0值=pin2, 是否修改_字段0=pin3
        #   - 字段1值=pin4, 是否修改_字段1=pin5
        #   ...
        if port == "结构体实例":
            return 0
        if port == "结构体名":
            return 1
        # GraphModel.data_inputs 的 slot_index 以 inputs（去掉流程端口）顺序为准：
        # [结构体名(slot0), 结构体实例(slot1), 字段0(slot2), 字段1(slot3), ...]
        # 因此字段N(slot=2+N) -> pin=2+2*N
        if int(slot) < 2:
            return int(slot)
        return int(2 + (int(slot) - 2) * 2)

    if title == CREATE_PREFAB_WRAPPER_NODE_TITLE and port in CREATE_PREFAB_PORT_NAMES_NEED_OFFSET:
        return int(slot + CREATE_PREFAB_HIDDEN_INPARAM_OFFSET_AFTER_OWNER_ENTITY)

    return int(slot)


def infer_index_of_concrete_for_generic_pin(
    *,
    node_title: str,
    port_name: str,
    is_input: bool,
    var_type_int: Optional[int] = None,
    node_type_id_int: Optional[int] = None,
    pin_index: Optional[int] = None,
) -> Optional[int]:
    """Public API: infer ConcreteBaseValue.indexOfConcrete for generic/reflective pins."""
    return _infer_index_of_concrete_for_generic_pin(
        node_title=str(node_title),
        port_name=str(port_name),
        is_input=bool(is_input),
        var_type_int=var_type_int,
        node_type_id_int=node_type_id_int,
        pin_index=pin_index,
    )


def map_inparam_pin_index_for_node(*, node_title: str, port_name: str, slot_index: int) -> int:
    """Public API: map GraphModel data_inputs slot_index to GIL NodePin.InParam.index."""
    return _map_inparam_pin_index_for_node(
        node_title=str(node_title),
        port_name=str(port_name),
        slot_index=int(slot_index),
    )

