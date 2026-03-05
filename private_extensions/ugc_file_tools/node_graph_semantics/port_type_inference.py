from __future__ import annotations

"""
ugc_file_tools.node_graph_semantics.port_type_inference

节点图共享语义层：端口类型/VarType 推断（写回 `.gil` 与导出 `.gia` 共用）。

动机：
- `node_graph_writeback` 与 `gia_export/node_graph` 都需要把 GraphModel(JSON) 中的
  “端口类型文本/泛型/常量/连线”收敛为稳定的 server VarType(int)，并在必要时参考 NodeEditorPack pin 画像；
- 若该逻辑放在 `.gia` 导出子域（例如 `gia_export/node_graph/*`），写回侧复用时会形成“依赖倒挂”；
- 因此该模块作为 single source of truth 上移到 `node_graph_semantics/`，两侧只依赖语义层与 `contracts/`。

注意：
- 本模块提供对外公开 API（无下划线），供跨域复用；
- 内部实现允许保留私有 helper（下划线），但跨模块禁止 `from ... import _private_name`。
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from ugc_file_tools.node_data_index import load_type_entry_by_id_map, resolve_default_node_data_index_path

from .dict_kv_types import try_infer_dict_kv_var_types_from_default_value, try_resolve_dict_kv_var_types_from_type_text
from .var_base import infer_var_type_int_from_raw_value as _infer_var_type_int_from_raw_value
from .var_base import map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id


@dataclass(frozen=True, slots=True)
class _NepPinDef:
    direction: str  # "In" | "Out"
    shell_index: int
    kernel_index: int
    type_expr: str
    identifier: str
    label_zh: str


def _iter_nep_pins(node_record: Mapping[str, Any], *, is_flow: bool) -> list[_NepPinDef]:
    key = "FlowPins" if bool(is_flow) else "DataPins"
    raw = node_record.get(key)
    if not isinstance(raw, list):
        return []

    out: list[_NepPinDef] = []
    for p in raw:
        if not isinstance(p, Mapping):
            continue
        direction = str(p.get("Direction") or "").strip()
        if direction not in {"In", "Out"}:
            continue
        type_expr = str(p.get("Type") or "").strip()
        label_zh = ""
        label_obj = p.get("Label")
        if isinstance(label_obj, Mapping):
            label_zh = str(label_obj.get("zh-Hans") or "").strip()
        identifier = str(p.get("Identifier") or "").strip()
        shell_index = int(p.get("ShellIndex") or 0)
        raw_kernel_index = p.get("KernelIndex")
        kernel_index = int(raw_kernel_index) if isinstance(raw_kernel_index, int) else int(shell_index)
        out.append(
            _NepPinDef(
                direction=str(direction),
                shell_index=int(shell_index),
                kernel_index=int(kernel_index),
                type_expr=str(type_expr),
                identifier=str(identifier),
                label_zh=str(label_zh),
            )
        )
    return out


def _find_nep_pin_def(
    node_record: Mapping[str, Any] | None,
    *,
    is_flow: bool,
    direction: str,
    port_name: str,
    ordinal: int,
) -> _NepPinDef | None:
    """
    在 NodeEditorPack node record 中定位 pin 定义。

    优先匹配：
    - zh-Hans label（GraphModel 端口名通常为中文）
    - identifier
    兜底：按 shell_index 升序取 ordinal。
    """
    if node_record is None:
        return None
    direction_norm = str(direction or "").strip()
    if direction_norm not in {"In", "Out"}:
        raise ValueError(f"invalid direction: {direction!r}")

    name = str(port_name or "").strip()
    pins = [p for p in _iter_nep_pins(node_record, is_flow=bool(is_flow)) if p.direction == direction_norm]

    if name != "":
        for p in pins:
            if p.label_zh != "" and p.label_zh == name:
                return p
        for p in pins:
            if p.identifier != "" and p.identifier == name:
                return p

    pins_sorted = sorted(pins, key=lambda x: int(x.shell_index))
    if 0 <= int(ordinal) < len(pins_sorted):
        return pins_sorted[int(ordinal)]
    return None


def _map_nep_type_expr_to_server_var_type_int(type_expr: str) -> int:
    """
    NodeEditorPack pin TypeExpr → server VarType(int)。

    说明：
    - 覆盖常见基础类型/列表/枚举；未知类型返回 0（交由 node_data TypeIndex 兜底）。
    """
    t = str(type_expr or "").strip()
    if t == "":
        return 0
    # enum item：E<?>（注意：E<1016> 等并非枚举，而是特殊句柄/实体类型）
    if t == "E<?>":
        return 14
    # local variable handle：E<1016>（node_data TypeId=16）
    if t == "E<1016>":
        return 16
    # list：L<T>
    if t.startswith("L<") and t.endswith(">"):
        inner = t[len("L<") : -1].strip()
        inner_map: Dict[str, int] = {
            "GUID": 7,
            "Gid": 7,
            "Int": 8,
            "Bol": 9,
            "Flt": 10,
            "Str": 11,
            "Ety": 13,
            "Vec": 15,
        }
        hit = inner_map.get(inner)
        return int(hit or 0)
    mapping: Dict[str, int] = {
        "Ety": 1,  # Entity
        "GUID": 2,
        "Gid": 2,
        "Int": 3,
        "Bol": 4,
        "Flt": 5,
        "Str": 6,
        "Loc": 16,  # LocalVariable（node_data: E<1016>）
        "GUIDArr": 7,
        "IntArr": 8,
        "BolArr": 9,
        "FltArr": 10,
        "StrArr": 11,
        "Vec": 12,
        "EtyArr": 13,
        "VecArr": 15,
        "Faction": 17,
        "Config": 20,
        "Prefab": 21,
        "ConfigArr": 22,
        "PrefabArr": 23,
    }
    return int(mapping.get(t, 0))


_TYPE_ID_BY_EXPR_CACHE: Dict[str, int] | None = None


def _get_server_type_id_by_expr() -> Dict[str, int]:
    """
    NodeEditorPack 的 pin `TypeExpr` 有时不是基础 VarType（例如：`E<1016>` 这类特殊实体/句柄类型）。
    此时需要回查 node_data 的 type index，把 Expression → TypeId（写入 NodePin.field_4）。
    """
    global _TYPE_ID_BY_EXPR_CACHE
    if isinstance(_TYPE_ID_BY_EXPR_CACHE, dict):
        return _TYPE_ID_BY_EXPR_CACHE

    type_entry_by_id = load_type_entry_by_id_map(resolve_default_node_data_index_path())
    expr_to_id: Dict[str, int] = {}
    for type_id, entry in (type_entry_by_id or {}).items():
        if not isinstance(type_id, int) or not isinstance(entry, dict):
            continue
        expr = str(entry.get("Expression") or "").strip()
        if not expr:
            continue
        # 以首次出现为准（避免同 expr 多 id 时的不稳定）
        expr_to_id.setdefault(expr, int(type_id))

    _TYPE_ID_BY_EXPR_CACHE = expr_to_id
    return expr_to_id


def _map_nep_type_expr_to_server_type_id_int(type_expr: str) -> int:
    """
    将 NodeEditorPack 的 TypeExpr 映射为“server pin type_id”（NodePin.field_4）。
    - 基础类型/列表：走 VarType 映射（1..26 等）
    - 特殊类型（如 E<1016>）：回查 node_data type index
    """
    text = str(type_expr or "").strip()
    if text == "":
        return 0

    vt = int(_map_nep_type_expr_to_server_var_type_int(text))
    if vt > 0:
        return int(vt)

    # 兜底：按 Expression 精确回查 TypeId
    return int(_get_server_type_id_by_expr().get(text, 0))


def _is_nep_fixed_special_type_expr(type_expr: str) -> bool:
    """
    NodeEditorPack TypeExpr 中存在少量“固定特殊类型”，其 TypeId 不应被 GraphModel 的泛型推断覆盖。
    当前明确需要保真的是：`E<1016>`（LocalVariable handle）。
    """
    text = str(type_expr or "").strip()
    if text == "Loc":
        return True
    return False


def _iter_list(value: Any) -> Iterable[Any]:
    return value if isinstance(value, list) else []


def iter_list(value: Any) -> Iterable[Any]:
    """Public API (no leading underscores)."""
    return _iter_list(value)


def _is_ui_key_placeholder_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = str(value).strip().lower()
    return lowered.startswith("ui_key:") or lowered.startswith("ui:")


def _contains_ui_key_placeholder(value: Any) -> bool:
    if _is_ui_key_placeholder_text(value):
        return True
    if isinstance(value, dict):
        for k, v in value.items():
            if _contains_ui_key_placeholder(k) or _contains_ui_key_placeholder(v):
                return True
        return False
    if isinstance(value, (list, tuple)):
        for item in value:
            if _contains_ui_key_placeholder(item):
                return True
        return False
    return False


def _get_port_type_text(node_payload: Mapping[str, Any], port_name: str, *, is_input: bool) -> str:
    # 优先读取工具链 enrich 后的具体类型（可包含泛型端口的实例化结果）
    # 其次读取 graph_cache 快照（effective_input_types/effective_output_types）
    # 再次读取 NodeDef 声明类型（input_port_declared_types/output_port_declared_types）
    for key in (
        ("input_port_types" if bool(is_input) else "output_port_types"),
        ("effective_input_types" if bool(is_input) else "effective_output_types"),
        ("input_port_declared_types" if bool(is_input) else "output_port_declared_types"),
    ):
        t0 = node_payload.get(key)
        if not isinstance(t0, Mapping):
            continue
        v0 = t0.get(str(port_name))
        if isinstance(v0, str) and v0.strip():
            return v0.strip()
    return ""


def get_port_type_text(node_payload: Mapping[str, Any], port_name: str, *, is_input: bool) -> str:
    """Public API (no leading underscores)."""
    return _get_port_type_text(node_payload, port_name, is_input=bool(is_input))


def _infer_input_type_text_by_dst_node_and_port(
    *,
    edges: Sequence[Dict[str, Any]],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
    graph_variable_type_text_by_name: Mapping[str, str] | None = None,
) -> Dict[Tuple[str, str], str]:
    """
    输入端口类型兜底推断：
    - 若 dst 输入端口为“泛型/缺失”，且该 pin 有 data edge，则用 src 输出端口的 output_port_types 反推；
    - 仅当候选类型唯一时才采纳。
    """
    candidates: Dict[Tuple[str, str], set[str]] = {}

    def _get_concrete_src_output_type_text_for_inference(src_payload: Mapping[str, Any], src_port: str) -> str:
        """
        从 src 节点 payload 中提取“可用于推断的输出端口具体类型文本”。

        背景：
        - GraphModel(JSON) 在不同链路中可能只携带 `effective_output_types`（graph_cache 快照）而缺失 `output_port_types`；
        - 若只读取 `output_port_types`，会导致 inferred_in_type_text 缺失，从而让字典 KV / 泛型端口推断退化。

        策略：
        - 优先 `output_port_types`（工具链 enrich 后的具体类型）
        - 其次 `effective_output_types`（GraphModel 快照）
        - 最后 `output_port_declared_types`（固定类型端口仍可提供证据；泛型会被过滤掉）
        """
        port = str(src_port or "").strip()
        if port == "":
            return ""

        # 特例：节点图变量 Get/Set 的 “变量值” 端口类型以 graph_variables 表为真源。
        # 说明：GraphModel(JSON) 的 typed 字段经常保持为“泛型”，仅靠字段读取会让 inferred_in_type_text 缺失，
        # 进而影响下游字典 KV / Variant concrete / OUT_PARAM 等推断。
        node_title = str(src_payload.get("title") or "").strip()
        if node_title in {"获取节点图变量", "设置节点图变量"} and port == "变量值":
            input_constants = src_payload.get("input_constants")
            if isinstance(input_constants, Mapping):
                var_name = input_constants.get("变量名")
                if isinstance(var_name, str) and var_name.strip():
                    gv_type_map = dict(graph_variable_type_text_by_name or {})
                    gv_type_text = str(gv_type_map.get(var_name.strip()) or "").strip()
                    if gv_type_text and gv_type_text != "流程" and ("泛型" not in gv_type_text):
                        return gv_type_text

        # 特例：获取局部变量 的“值”输出端口与“初始值”输入端口同型（R<T>）。
        # 当 output_* 字段仍为“泛型”时，允许从 input_* 快照字段反推输出端口类型用于下游推断。
        if node_title == "获取局部变量" and port == "值":
            init_t = str(_get_port_type_text(src_payload, "初始值", is_input=True) or "").strip()
            if init_t and init_t != "流程" and ("泛型" not in init_t):
                return init_t
        for key in ("output_port_types", "effective_output_types", "output_port_declared_types"):
            type_map = src_payload.get(key)
            if not isinstance(type_map, Mapping):
                continue
            raw = type_map.get(port)
            if not isinstance(raw, str):
                continue
            text = str(raw).strip()
            if (not text) or text == "流程" or ("泛型" in text):
                continue
            return text
        return ""

    for edge in list(edges):
        if not isinstance(edge, dict):
            continue
        src_node = str(edge.get("src_node") or "")
        dst_node = str(edge.get("dst_node") or "")
        src_port = str(edge.get("src_port") or "")
        dst_port = str(edge.get("dst_port") or "")
        if src_node == "" or dst_node == "" or src_port == "" or dst_port == "":
            continue
        src_payload = graph_node_by_graph_node_id.get(src_node)
        if not isinstance(src_payload, dict):
            continue
        src_type_text = _get_concrete_src_output_type_text_for_inference(src_payload, src_port)
        if src_type_text == "":
            continue
        candidates.setdefault((dst_node, dst_port), set()).add(str(src_type_text))
    inferred: Dict[Tuple[str, str], str] = {}
    for key, cs in candidates.items():
        if len(cs) == 1:
            inferred[key] = next(iter(cs))
    return inferred


def infer_input_type_text_by_dst_node_and_port(
    *,
    edges: Sequence[Dict[str, Any]],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
    graph_variable_type_text_by_name: Mapping[str, str] | None = None,
) -> Dict[Tuple[str, str], str]:
    """
    Public API (no leading underscores).

    Import policy: cross-module imports must not import underscored private names.
    """
    return _infer_input_type_text_by_dst_node_and_port(
        edges=edges,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        graph_variable_type_text_by_name=graph_variable_type_text_by_name,
    )


def _resolve_server_var_type_int_for_port(
    *,
    graph_scope: str,
    node_id: str,
    port_name: str,
    is_input: bool,
    node_payload: Mapping[str, Any],
    graph_variable_type_text_by_name: Mapping[str, str],
    inferred_out_type_text: Dict[Tuple[str, str], str],
    inferred_in_type_text: Dict[Tuple[str, str], str],
    raw_constant_value: Any,
    nep_node_record: Mapping[str, Any] | None,
    nep_port_name: str,
    nep_ordinal: int,
) -> int:
    """
    统一把“端口类型文本/泛型/常量”收敛为 server VarTypeId（即 ServerTypeId）。
    """
    _ = graph_scope

    # NodeEditorPack 固定特殊类型优先（避免被 GraphModel 的“同名数据口类型”误覆盖）
    nep_dir = "In" if bool(is_input) else "Out"
    hit = _find_nep_pin_def(
        nep_node_record,
        is_flow=False,
        direction=str(nep_dir),
        port_name=str(nep_port_name),
        ordinal=int(nep_ordinal),
    )
    if hit is not None:
        nep_expr = str(getattr(hit, "type_expr", "") or "").strip()
        if _is_nep_fixed_special_type_expr(nep_expr):
            nep_type_id = int(_map_nep_type_expr_to_server_type_id_int(nep_expr))
            if nep_type_id > 0:
                return int(nep_type_id)

    t = _get_port_type_text(node_payload, port_name, is_input=bool(is_input))
    raw_contains_ui_key = _contains_ui_key_placeholder(raw_constant_value)
    if (not t) or t == "流程" or ("泛型" in t):
        # NodeEditorPack 兜底：
        # - GraphModel（尤其是复合子图）里，部分端口类型可能缺失/泛型；
        # - 但 NodeEditorPack 的 pin 画像里有稳定的 TypeExpr，可用来推断 server VarType。
        if hit is not None:
            vt_by_nep = int(_map_nep_type_expr_to_server_type_id_int(str(getattr(hit, "type_expr", "") or "")))
            if int(vt_by_nep) > 0:
                return int(vt_by_nep)

        # 特例：节点图变量 Get/Set 的 “变量值” 端口类型应该由 graph_variables 表决定。
        # GraphModel(JSON) 里这些端口经常保持为“泛型”，若直接走兜底会落到字符串(6)，
        # 导致导入编辑器后出现“整数变量显示成字符串”的错配。
        node_title = str(node_payload.get("title") or "").strip()
        if node_title in {"获取节点图变量", "设置节点图变量"} and str(port_name).strip() == "变量值":
            input_constants = node_payload.get("input_constants")
            if isinstance(input_constants, Mapping):
                var_name = input_constants.get("变量名")
                if isinstance(var_name, str) and var_name.strip():
                    gv_type_text = str(graph_variable_type_text_by_name.get(var_name.strip()) or "").strip()
                    if gv_type_text and gv_type_text != "流程" and ("泛型" not in gv_type_text):
                        t = gv_type_text

        inferred_text = None
        if bool(is_input):
            inferred_text = inferred_in_type_text.get((str(node_id), str(port_name)))
        else:
            inferred_text = inferred_out_type_text.get((str(node_id), str(port_name)))
        if isinstance(inferred_text, str) and inferred_text.strip() and ("泛型" not in inferred_text) and inferred_text != "流程":
            t = inferred_text.strip()
        elif raw_constant_value is not None:
            # 统一口径：任何位置出现 ui_key:/ui: 占位符，都按“数值语义”推断，
            # 避免占位符因端口画像缺失而退化成字符串并原样落库。
            if bool(raw_contains_ui_key):
                if isinstance(raw_constant_value, dict):
                    return 27
                if isinstance(raw_constant_value, (list, tuple)):
                    return 8
                return 3
            return int(_infer_var_type_int_from_raw_value(raw_constant_value))
        else:
            # 保守兜底：字符串
            return 6

    # 结构体类型展示名可能形如 "结构体<xxx>" / "结构体列表<xxx>"：统一映射为 25/26
    if t.startswith("结构体列表"):
        return 26
    if t.startswith("结构体"):
        return 25

    mapped_vt = int(_map_server_port_type_to_var_type_id(str(t)))
    if bool(raw_contains_ui_key):
        # 显式数值/容器数值口径保持原类型；其它类型统一收敛为可回填的数值语义。
        if isinstance(raw_constant_value, dict):
            return 27
        if isinstance(raw_constant_value, (list, tuple)):
            if int(mapped_vt) in {7, 8}:
                return int(mapped_vt)
            return 8
        if int(mapped_vt) in {2, 3}:
            return int(mapped_vt)
        return 3

    return int(mapped_vt)


def resolve_server_var_type_int_for_port(
    *,
    graph_scope: str,
    node_id: str,
    port_name: str,
    is_input: bool,
    node_payload: Mapping[str, Any],
    graph_variable_type_text_by_name: Mapping[str, str],
    inferred_out_type_text: Dict[Tuple[str, str], str],
    inferred_in_type_text: Dict[Tuple[str, str], str],
    raw_constant_value: Any,
    nep_node_record: Mapping[str, Any] | None,
    nep_port_name: str,
    nep_ordinal: int,
) -> int:
    """Public API (no leading underscores)."""
    return _resolve_server_var_type_int_for_port(
        graph_scope=graph_scope,
        node_id=node_id,
        port_name=port_name,
        is_input=is_input,
        node_payload=node_payload,
        graph_variable_type_text_by_name=graph_variable_type_text_by_name,
        inferred_out_type_text=inferred_out_type_text,
        inferred_in_type_text=inferred_in_type_text,
        raw_constant_value=raw_constant_value,
        nep_node_record=nep_node_record,
        nep_port_name=nep_port_name,
        nep_ordinal=nep_ordinal,
    )


def _parse_dict_key_value_var_types_from_port_type_text(type_text: str) -> Tuple[int, int] | None:
    """
    从 GraphModel(JSON) 的端口类型文本中提取“字典的键/值 VarType”。

    约定：
    - 形如：`字符串_整数字典` / `配置ID-整数字典` / `GUID_实体列表字典`
    - 或：`字典(字符串→整数)` / `字典(字符串->整数)`
    """
    return try_resolve_dict_kv_var_types_from_type_text(
        str(type_text or ""),
        map_port_type_text_to_var_type_id=_map_server_port_type_to_var_type_id,
        reject_generic=True,
    )


def parse_dict_key_value_var_types_from_port_type_text(type_text: str) -> Tuple[int, int] | None:
    """Public API (no leading underscores)."""
    return _parse_dict_key_value_var_types_from_port_type_text(str(type_text or ""))


def try_parse_dict_key_value_var_types_from_nep_type_expr(type_expr: str) -> Tuple[int, int] | None:
    """
    从 NodeEditorPack 的 TypeExpr 中提取“字典 K/V VarType”。

    支持形态（固定类型字典）：
    - "D<Str,Int>" / "D<GUID,Ety>" / "D<Config,Int>" 等

    不支持（返回 None）：
    - 反射/泛型字典："D<R<K>,R<V>>"（缺少具体 K/V）
    - 其它复杂嵌套/未知 token
    """
    t = str(type_expr or "").strip()
    if not (t.startswith("D<") and t.endswith(">")):
        return None
    inner = t[len("D<") : -1].strip()
    if inner == "":
        return None

    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in inner:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    if len(parts) != 2:
        return None

    key_expr, val_expr = str(parts[0]).strip(), str(parts[1]).strip()
    if key_expr == "" or val_expr == "":
        return None
    key_vt = int(_map_nep_type_expr_to_server_var_type_int(key_expr))
    val_vt = int(_map_nep_type_expr_to_server_var_type_int(val_expr))
    if int(key_vt) <= 0 or int(val_vt) <= 0:
        return None
    return int(key_vt), int(val_vt)


def _infer_dict_kv_var_types_from_default_value(default_value: Any) -> Tuple[int, int] | None:
    return try_infer_dict_kv_var_types_from_default_value(
        default_value,
        infer_var_type_int_from_raw_value=_infer_var_type_int_from_raw_value,
    )


def infer_dict_kv_var_types_from_default_value(default_value: Any) -> Tuple[int, int] | None:
    """Public API (no leading underscores)."""
    return _infer_dict_kv_var_types_from_default_value(default_value)


def _get_port_declared_type_text(node_payload: Mapping[str, Any], port_name: str, *, is_input: bool) -> str:
    key = "input_port_declared_types" if bool(is_input) else "output_port_declared_types"
    t0 = node_payload.get(key)
    if isinstance(t0, Mapping):
        v0 = t0.get(str(port_name))
        if isinstance(v0, str) and v0.strip():
            return v0.strip()
    return ""


def get_port_declared_type_text(node_payload: Mapping[str, Any], port_name: str, *, is_input: bool) -> str:
    """Public API (no leading underscores)."""
    return _get_port_declared_type_text(node_payload, port_name, is_input=bool(is_input))


__all__ = [
    "infer_input_type_text_by_dst_node_and_port",
    "resolve_server_var_type_int_for_port",
    "iter_list",
    "get_port_type_text",
    "get_port_declared_type_text",
    "parse_dict_key_value_var_types_from_port_type_text",
    "try_parse_dict_key_value_var_types_from_nep_type_expr",
    "infer_dict_kv_var_types_from_default_value",
]

