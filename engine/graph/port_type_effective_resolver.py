from __future__ import annotations

"""port_type_effective_resolver: GraphModel 级别的“有效端口类型”解析（纯逻辑）。

目标
- 统一“在具体节点图里，泛型端口如何实例化为具体类型”的推断规则；
- 同一套规则同时服务：
  - 资源层写入 graph_cache 时的 `NodeModel.effective_input_types/effective_output_types`（可复用的有效类型缓存）
  - UI/工具层展示端口类型（在缺少缓存或需要兜底推断时）

边界
- 纯计算：不做 I/O，不依赖 app/ui，不吞异常；
- 输入仅依赖 GraphModel（nodes/edges/metadata/input_constants）与 NodeDef（声明/动态类型）。
"""

import re
from typing import Any, Callable, Dict, Optional, Set, Tuple

from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.type_registry import (
    BASE_TO_LIST_TYPE_MAP,
    LIST_TYPES,
    TYPE_BOOLEAN,
    TYPE_DICT,
    TYPE_FLOAT,
    TYPE_FLOW,
    TYPE_GENERIC,
    TYPE_INTEGER,
    TYPE_LIST_PLACEHOLDER,
    TYPE_STRING,
    TYPE_STRUCT,
    TYPE_STRUCT_LIST,
    TYPE_VECTOR3,
    is_dict_type_name,
    is_list_type_name,
    normalize_type_text,
    parse_typed_dict_alias,
)
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.graph.common import (
    STRUCT_NODE_TITLES,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_PORT_NAME,
    STRUCT_PORT_LEGACY_BUILD_OUTPUT_NAME,
    STRUCT_PORT_LEGACY_INSTANCE_NAME,
    STRUCT_NAME_PORT_NAME,
)
from engine.graph.semantic.constants import STRUCT_BINDINGS_METADATA_KEY


_VECTOR3_PATTERN = re.compile(
    r"^\(\s*[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?\s*\)$"
)


def is_generic_type_name(type_name: object) -> bool:
    """判定是否为“泛型家族”类型名（仍未落地的占位类型）。

    约定：
    - `""` / `"泛型"` / `"泛型<...>"` 属于泛型家族；
    - `"列表"` / `"字典"` 也属于“未实例化的容器占位”，视为泛型家族（交付边界必须 fail-fast）。
    """
    text = normalize_type_text(type_name)
    if text == "":
        return True
    if text in {TYPE_LIST_PLACEHOLDER, TYPE_DICT}:
        return True
    if text == TYPE_GENERIC or text.startswith(TYPE_GENERIC):
        return True
    return False


def _resolve_struct_bound_type_for_port(
    graph_model: GraphModel,
    node_obj: NodeModel,
    port_name: str,
    *,
    is_input: bool,
) -> str:
    """结构体语义节点的“结构体端口”类型细化：结构体 → 结构体<struct_name>。

    说明：
    - 端口名固定为“结构体”；旧图可能仍为“结构体实例/结果”，这里一并兼容；
    - 具体 struct_name 来自 GraphSemanticPass 生成的 metadata["struct_bindings"][node_id]；
      若该派生字段缺失，则回退读取 node.input_constants["结构体名"]（仅用于展示/推断兜底）。
    """
    title = str(getattr(node_obj, "title", "") or "")
    if title not in STRUCT_NODE_TITLES:
        return ""

    port_text = str(port_name or "").strip()
    if not port_text:
        return ""

    # 仅对“结构体值端口”生效（按节点方向区分）
    if title == STRUCT_BUILD_NODE_TITLE:
        if bool(is_input):
            return ""
        if port_text not in {STRUCT_PORT_NAME, STRUCT_PORT_LEGACY_BUILD_OUTPUT_NAME}:
            return ""
    else:
        # 拆分/修改：结构体值为输入端口
        if not bool(is_input):
            return ""
        if port_text not in {STRUCT_PORT_NAME, STRUCT_PORT_LEGACY_INSTANCE_NAME}:
            return ""

    node_id = str(getattr(node_obj, "id", "") or "")
    meta = getattr(graph_model, "metadata", None) or {}
    bindings = meta.get(STRUCT_BINDINGS_METADATA_KEY)
    binding_payload = bindings.get(node_id) if isinstance(bindings, dict) and node_id else None

    struct_name = ""
    if isinstance(binding_payload, dict):
        raw = binding_payload.get("struct_name")
        if isinstance(raw, str) and raw.strip():
            struct_name = raw.strip()

    # 回退：允许直接使用“结构体名”常量做展示级细化（避免缓存缺少 struct_bindings 时 UI 永远显示“结构体”）
    if not struct_name:
        constants = getattr(node_obj, "input_constants", {}) or {}
        if isinstance(constants, dict):
            raw = constants.get(STRUCT_NAME_PORT_NAME)
            if isinstance(raw, str) and raw.strip():
                struct_name = raw.strip()

    if not struct_name:
        return ""

    # 统一采用“结构体<struct_name>”表示具体类型
    return f"{TYPE_STRUCT}<{struct_name}>"


def normalize_node_id_for_overrides(node_id: object) -> str:
    """将可能带有 copy_block 后缀的节点 ID 归一化为原始节点 ID。"""
    if not isinstance(node_id, str):
        return ""
    raw = node_id.strip()
    if raw == "":
        return ""
    marker = "_copy_block_"
    index = raw.find(marker)
    if index > 0:
        return raw[:index]
    return raw


def build_port_type_overrides(graph_model: GraphModel) -> Dict[str, Dict[str, str]]:
    """标准化 GraphModel.metadata['port_type_overrides'] 结构为 {node_id: {port: type}}。"""
    cached = getattr(graph_model, "_effective_port_type_overrides_cache", None)
    if isinstance(cached, dict):
        return cached

    result: Dict[str, Dict[str, str]] = {}
    meta = getattr(graph_model, "metadata", None) or {}
    overrides_raw = meta.get("port_type_overrides")
    if not isinstance(overrides_raw, dict):
        setattr(graph_model, "_effective_port_type_overrides_cache", result)
        return result

    for node_key, mapping in overrides_raw.items():
        if not isinstance(node_key, str) or not isinstance(mapping, dict):
            continue
        normalized_mapping: Dict[str, str] = {}
        for port_name, type_text in mapping.items():
            if not isinstance(port_name, str):
                continue
            text = str(type_text or "").strip()
            if not text:
                continue
            normalized_mapping[port_name] = text
        if normalized_mapping:
            result[node_key] = normalized_mapping

    setattr(graph_model, "_effective_port_type_overrides_cache", result)
    return result


def get_node_port_type_overrides_for_id(
    overrides_mapping: Dict[str, Dict[str, str]],
    node_identifier: object,
) -> Dict[str, str]:
    if not isinstance(overrides_mapping, dict):
        return {}
    if not isinstance(node_identifier, str):
        return {}
    direct = overrides_mapping.get(node_identifier)
    if isinstance(direct, dict):
        return direct
    normalized = normalize_node_id_for_overrides(node_identifier)
    if normalized and normalized != node_identifier:
        base = overrides_mapping.get(normalized)
        if isinstance(base, dict):
            return base
    return {}


def resolve_override_type_for_node_port(
    overrides_mapping: Dict[str, Dict[str, str]],
    node_identifier: object,
    port_name: object,
) -> str:
    """只返回“非空、非泛型、非流程”的覆盖类型；否则返回空字符串。"""
    if not isinstance(port_name, str):
        return ""
    port_text = port_name.strip()
    if port_text == "":
        return ""
    node_overrides = get_node_port_type_overrides_for_id(overrides_mapping, node_identifier)
    raw = node_overrides.get(port_text)
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    if not text:
        return ""
    if is_generic_type_name(text):
        return ""
    if normalize_type_text(text) == TYPE_FLOW:
        return ""
    return text


def safe_get_port_type_from_node_def(node_def: Any, port_name: str, *, is_input: bool) -> str:
    """不抛异常版端口类型查询：显式类型 → 动态类型 → 流程兜底 → 空字符串。"""
    if node_def is None:
        return ""
    port_text = str(port_name or "").strip()
    if port_text == "":
        return ""
    if is_flow_port_name(port_text):
        return TYPE_FLOW

    type_dict = getattr(node_def, "input_types" if is_input else "output_types", {}) or {}
    # 端口别名兼容：允许使用历史端口名查询类型（不依赖 get_port_type 以避免异常/try-except）
    if isinstance(type_dict, dict) and port_text not in type_dict:
        alias_map = getattr(node_def, "input_port_aliases" if is_input else "output_port_aliases", {}) or {}
        if isinstance(alias_map, dict) and alias_map:
            resolved = ""
            for canonical, aliases in alias_map.items():
                if not isinstance(canonical, str) or not isinstance(aliases, list):
                    continue
                if port_text in aliases:
                    resolved = canonical
                    break
            if resolved:
                port_text = resolved
    if isinstance(type_dict, dict) and port_text in type_dict:
        return str(type_dict.get(port_text) or "")

    from engine.nodes.port_name_rules import get_dynamic_port_type

    inferred = get_dynamic_port_type(
        port_text,
        dict(type_dict) if isinstance(type_dict, dict) else {},
        str(getattr(node_def, "dynamic_port_type", "") or ""),
    )
    return str(inferred or "") if inferred else ""


def _infer_scalar_type_from_constant_value(value: object) -> str:
    """从 NodeModel.input_constants 的 Python 值推断基础类型（偏保守）。"""
    if isinstance(value, bool):
        return TYPE_BOOLEAN
    if isinstance(value, int) and not isinstance(value, bool):
        return TYPE_INTEGER
    if isinstance(value, float):
        return TYPE_FLOAT
    if isinstance(value, str):
        text = value.strip()
        # ui_key: 前缀在节点图中代表“写回阶段回填为整数索引”的占位符（控件/状态组等）。
        # 其语义应按整数处理，否则会把大量 UI 映射常量推断为“字符串”，导致端口类型漂移。
        if text.startswith("ui_key:") and len(text) > len("ui_key:"):
            return TYPE_INTEGER
        lower = text.lower()
        if text in ("是", "否") or lower in ("true", "false"):
            return TYPE_BOOLEAN
        if _VECTOR3_PATTERN.match(text):
            return TYPE_VECTOR3
        # 不尝试把“纯数字字符串”当作整数，避免误判 GUID 等标识
        return TYPE_STRING
    return ""


def _upgrade_to_list_type_if_needed(declared_type: str, inferred_scalar: str) -> str:
    scalar_text = normalize_type_text(inferred_scalar)
    if scalar_text == "" or is_generic_type_name(scalar_text):
        return ""
    declared_text = normalize_type_text(declared_type)
    if declared_text and is_list_type_name(declared_text):
        return str(BASE_TO_LIST_TYPE_MAP.get(scalar_text, scalar_text))
    return scalar_text


def _base_type_from_list_type_text(type_text: str) -> str:
    """从“X列表 / 结构体列表<name>”推导其元素类型“X / 结构体<name>”。

    说明：
    - 该函数用于“列表迭代循环”等节点的泛型实例化：迭代值类型应随迭代列表的元素类型收敛；
    - 仅在列表类型已可确定（非泛型家族）时返回非空结果。
    """
    text = normalize_type_text(type_text)
    if not text or is_generic_type_name(text):
        return ""

    # 结构体列表：允许携带绑定信息，例如：结构体列表<某结构体>
    if text.startswith(f"{TYPE_STRUCT_LIST}<") and text.endswith(">"):
        inner = text[len(f"{TYPE_STRUCT_LIST}<") : -1].strip()
        if inner:
            return f"{TYPE_STRUCT}<{inner}>"
        return ""

    payload = LIST_TYPES.get(text)
    if isinstance(payload, dict):
        base = str(payload.get("base_type") or "").strip()
        if base and (not is_generic_type_name(base)):
            return base
    return ""


def _should_override_with_edge_type(current_type: str, candidate_type: str) -> bool:
    candidate_text = normalize_type_text(candidate_type)
    if candidate_text == "":
        return False
    if is_generic_type_name(candidate_text):
        return False
    current_text = normalize_type_text(current_type)
    if current_text == "":
        return True
    if current_text.startswith(TYPE_STRING) and candidate_text != current_text:
        return True
    return False


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: Set[str] = set()
    result: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result


def _resolve_graph_variable_type_by_name(graph_model: GraphModel, variable_name: str) -> str:
    """从 GraphModel.graph_variables 里按变量名查到变量类型（用于节点图变量 Get/Set 的端口类型收敛）。"""
    name = str(variable_name or "").strip()
    if name == "":
        return ""
    for item in getattr(graph_model, "graph_variables", None) or []:
        if not isinstance(item, dict):
            continue
        n = str(item.get("name") or "").strip()
        if n != name:
            continue
        t = str(item.get("variable_type") or "").strip()
        if t == "":
            return ""
        # 结构体/结构体列表：若变量表里同时提供 struct_name，则可细化为 “结构体<xxx>”
        struct_name = str(item.get("struct_name") or "").strip()
        if struct_name:
            if normalize_type_text(t) == TYPE_STRUCT:
                return f"{TYPE_STRUCT}<{struct_name}>"
            if normalize_type_text(t) == TYPE_STRUCT_LIST:
                return f"{TYPE_STRUCT_LIST}<{struct_name}>"
        return t
    return ""


class EffectivePortTypeResolver:
    """在当前 GraphModel 上解析端口“有效类型”（支持 memo 与循环防御）。"""

    def __init__(
        self,
        graph_model: GraphModel,
        *,
        node_def_resolver: Callable[[NodeModel], Any],
        port_type_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> None:
        self.graph_model = graph_model
        self._node_def_resolver = node_def_resolver
        self._node_def_cache: Dict[str, Any] = {}
        self._overrides = port_type_overrides if port_type_overrides is not None else build_port_type_overrides(graph_model)

        self._incoming_edges: Dict[Tuple[str, str], list[object]] = {}
        self._outgoing_edges: Dict[Tuple[str, str], list[object]] = {}
        self._build_edge_indices()

        self._memo: Dict[Tuple[str, str, bool], str] = {}
        self._visiting: Set[Tuple[str, str, bool]] = set()

    def _build_edge_indices(self) -> None:
        for edge in (getattr(self.graph_model, "edges", None) or {}).values():
            src_node_id = str(getattr(edge, "src_node", "") or "")
            src_port = str(getattr(edge, "src_port", "") or "")
            dst_node_id = str(getattr(edge, "dst_node", "") or "")
            dst_port = str(getattr(edge, "dst_port", "") or "")
            if not src_node_id or not dst_node_id or not src_port or not dst_port:
                continue
            self._incoming_edges.setdefault((dst_node_id, dst_port), []).append(edge)
            self._outgoing_edges.setdefault((src_node_id, src_port), []).append(edge)
        for edges in self._incoming_edges.values():
            edges.sort(key=lambda e: str(getattr(e, "id", "") or ""))
        for edges in self._outgoing_edges.values():
            edges.sort(key=lambda e: str(getattr(e, "id", "") or ""))

    def _get_node_def(self, node: NodeModel) -> Any:
        node_id = str(getattr(node, "id", "") or "")
        if node_id in self._node_def_cache:
            return self._node_def_cache[node_id]
        node_def = self._node_def_resolver(node) if callable(self._node_def_resolver) else None
        self._node_def_cache[node_id] = node_def
        return node_def

    def resolve(self, node_id: str, port_name: str, *, is_input: bool) -> str:
        port_text = str(port_name or "").strip()
        if port_text == "":
            return TYPE_GENERIC
        if is_flow_port_name(port_text):
            return TYPE_FLOW

        key = (str(node_id), port_text, bool(is_input))
        if key in self._memo:
            return self._memo[key]
        if key in self._visiting:
            node_obj = (getattr(self.graph_model, "nodes", None) or {}).get(str(node_id))
            node_def = self._get_node_def(node_obj) if node_obj is not None else None
            declared = safe_get_port_type_from_node_def(node_def, port_text, is_input=bool(is_input))
            declared_text = normalize_type_text(declared)
            return declared_text if declared_text else TYPE_GENERIC

        self._visiting.add(key)

        node_obj = (getattr(self.graph_model, "nodes", None) or {}).get(str(node_id))
        if node_obj is None:
            self._visiting.remove(key)
            self._memo[key] = TYPE_GENERIC
            return TYPE_GENERIC

        node_def = self._get_node_def(node_obj)
        declared = safe_get_port_type_from_node_def(node_def, port_text, is_input=bool(is_input))
        declared_text = normalize_type_text(declared)

        # 0) overrides（最高优先级）
        override_type = resolve_override_type_for_node_port(self._overrides, str(node_id), port_text)
        if override_type:
            self._visiting.remove(key)
            self._memo[key] = override_type
            return override_type

        # 0.5) 结构体语义节点：绑定后细化“结构体端口”类型（结构体<struct_name>）
        struct_bound = _resolve_struct_bound_type_for_port(
            self.graph_model,
            node_obj,
            port_text,
            is_input=bool(is_input),
        )
        if struct_bound:
            self._visiting.remove(key)
            self._memo[key] = struct_bound
            return struct_bound

        # 1) 声明为具体类型：直接采用（节点库单一真源）
        #
        # 注意：对声明为“泛型家族”的端口，`NodeModel.effective_input_types/effective_output_types` 可能只是
        # “展示快照”（例如常量被字符串化后误呈现为“字符串”）。
        # 这类快照不能作为“有效类型”的早返回，否则会阻断后续的 overrides/常量/连线推断。
        if declared_text and (not is_generic_type_name(declared_text)) and declared_text != TYPE_FLOW:
            self._visiting.remove(key)
            self._memo[key] = declared_text
            return declared_text

        # 2) 快照：仅作为兜底候选，不做早返回（避免覆盖有效推断）
        snapshot_map = getattr(node_obj, "input_types" if is_input else "output_types", {}) or {}
        snapshot_existing = ""
        if isinstance(snapshot_map, dict):
            existing = normalize_type_text(snapshot_map.get(port_text, ""))
            if existing and (not is_generic_type_name(existing)) and existing != TYPE_FLOW:
                snapshot_existing = existing

        title = str(getattr(node_obj, "title", "") or "")

        # 3.2.0) 节点特例：拼装字典/建立字典（输出“字典”端口必须实例化为别名字典类型）
        #
        # 背景：
        # - 这两个节点在节点库中都声明输出为“泛型字典”，但在具体图中必须收敛为
        #   `键类型-值类型字典`（或 `_` 分隔）才能让后续字典相关节点的键/值端口正确实例化；
        # - 若不做此特例，通用的“输出从输入常量推断”会误把输出推断为某个标量类型（常见为键口类型），
        #   导致 UI/graph_model_json 中出现“字典端口类型=整数/字符串”等明显错误。
        if (not bool(is_input)) and port_text == "字典" and title in {"拼装字典", "建立字典"}:
            inferred_dict_alias = ""

            def _infer_input_port_type_for_dict_build(input_port: str) -> str:
                # 1) override（允许作者显式标注键/值类型）
                t0 = resolve_override_type_for_node_port(self._overrides, str(node_id), str(input_port))
                if t0:
                    return normalize_type_text(t0)

                # 2) 入边：优先用上游端口的有效类型
                for e in self._incoming_edges.get((str(node_id), str(input_port)), []) or []:
                    src_node_id = str(getattr(e, "src_node", "") or "")
                    src_port = str(getattr(e, "src_port", "") or "")
                    if not src_node_id or not src_port:
                        continue
                    src_type = normalize_type_text(self.resolve(src_node_id, src_port, is_input=False))
                    if src_type and (not is_generic_type_name(src_type)) and src_type != TYPE_FLOW:
                        return src_type

                # 3) 常量：保守按字面量推断（含 ui_key: 整数语义）
                constants_map = getattr(node_obj, "input_constants", {}) or {}
                if isinstance(constants_map, dict) and str(input_port) in constants_map:
                    scalar = _infer_scalar_type_from_constant_value(constants_map.get(str(input_port)))
                    scalar_text = normalize_type_text(scalar)
                    if scalar_text and (not is_generic_type_name(scalar_text)) and scalar_text != TYPE_FLOW:
                        return scalar_text
                return ""

            if title == "拼装字典":
                # 按“键N/值N”成对收敛，优先取第一个能同时解析出 K/V 的槽位。
                key_ports: dict[int, str] = {}
                value_ports: dict[int, str] = {}
                for p in (getattr(node_obj, "inputs", None) or []):
                    name = str(getattr(p, "name", "") or "").strip()
                    if not name:
                        continue
                    if name.startswith("键") and name[1:].isdigit():
                        key_ports[int(name[1:])] = name
                    elif name.startswith("值") and name[1:].isdigit():
                        value_ports[int(name[1:])] = name

                for i in sorted(set(key_ports.keys()) & set(value_ports.keys())):
                    k_type = _infer_input_port_type_for_dict_build(key_ports[int(i)])
                    v_type = _infer_input_port_type_for_dict_build(value_ports[int(i)])
                    if not k_type or not v_type:
                        continue
                    if is_generic_type_name(k_type) or is_generic_type_name(v_type):
                        continue
                    if k_type == TYPE_FLOW or v_type == TYPE_FLOW:
                        continue
                    inferred_dict_alias = f"{k_type}-{v_type}字典"
                    break

            else:
                # 建立字典：键/值来自两条列表的元素类型
                key_list_type = normalize_type_text(self.resolve(str(node_id), "键列表", is_input=True))
                value_list_type = normalize_type_text(self.resolve(str(node_id), "值列表", is_input=True))
                k_type = _base_type_from_list_type_text(key_list_type)
                v_type = _base_type_from_list_type_text(value_list_type)
                if k_type and v_type and (not is_generic_type_name(k_type)) and (not is_generic_type_name(v_type)):
                    if k_type != TYPE_FLOW and v_type != TYPE_FLOW:
                        inferred_dict_alias = f"{k_type}-{v_type}字典"

            inferred_text = normalize_type_text(inferred_dict_alias)
            if inferred_text and is_dict_type_name(inferred_text):
                self._visiting.remove(key)
                self._memo[key] = inferred_text
                return inferred_text

        # 3) 节点特例：列表迭代循环
        # - `迭代列表` 为泛型列表家族；`迭代值` 为泛型；
        # - 在具体图中，`迭代值` 必须跟随 `迭代列表` 的元素类型实例化，否则画布将长期显示“泛型”。
        if (not bool(is_input)) and title == "列表迭代循环" and port_text == "迭代值":
            list_type = self.resolve(str(node_id), "迭代列表", is_input=True)
            element_type = _base_type_from_list_type_text(list_type)
            if element_type and (not is_generic_type_name(element_type)) and element_type != TYPE_FLOW:
                self._visiting.remove(key)
                self._memo[key] = element_type
                return element_type

        # 3.0) 节点特例：获取列表对应值（值类型随列表元素类型收敛）
        # - `列表` 为泛型列表家族；`值` 为泛型；
        # - 在具体图中，`值` 必须跟随 `列表` 的元素类型实例化，否则后续链路会残留“泛型”并在结构校验阶段报错。
        if (not bool(is_input)) and title == "获取列表对应值" and port_text == "值":
            list_type = self.resolve(str(node_id), "列表", is_input=True)
            element_type = _base_type_from_list_type_text(list_type)
            if element_type and (not is_generic_type_name(element_type)) and element_type != TYPE_FLOW:
                self._visiting.remove(key)
                self._memo[key] = element_type
                return element_type

        # 3.1) 节点特例：对列表插入值（插入值类型随列表元素类型收敛）
        # 背景：常量在 GraphModel 中可能以字符串形式存在；当 `插入值` 无入边（常量）时，容易被推断为“字符串”。
        # 规则：当 `列表` 的元素类型已可确定时，强制让 `插入值` 跟随元素类型，以保持“同构列表”约束一致。
        if bool(is_input) and title == "对列表插入值" and port_text == "插入值":
            list_type = self.resolve(str(node_id), "列表", is_input=True)
            element_type = _base_type_from_list_type_text(list_type)
            if element_type and (not is_generic_type_name(element_type)) and element_type != TYPE_FLOW:
                self._visiting.remove(key)
                self._memo[key] = element_type
                return element_type

        # 3.2) 节点特例：字典查/写（键/值类型随“字典”别名字典类型收敛）
        #
        # 背景：字典相关节点多为“泛型字典/泛型键/泛型值”，但在具体图中必须通过别名字典类型实例化：
        # - `键类型_值类型字典` / `键类型-值类型字典`
        # 否则 `键/值` 端口会长期保持为“泛型”，触发 strict 结构校验报错，并导致 UI/Todo 展示不一致。
        wants_dict_kv_binding = (
            (bool(is_input) and port_text == "键" and title in {"以键查询字典值", "查询字典是否包含特定键", "对字典设置或新增键值对"})
            or (bool(is_input) and port_text == "值" and title == "对字典设置或新增键值对")
            or ((not bool(is_input)) and port_text == "值" and title == "以键查询字典值")
        )
        if wants_dict_kv_binding:
            dict_type = self.resolve(str(node_id), "字典", is_input=True)
            ok, key_type, value_type = parse_typed_dict_alias(dict_type)
            if ok:
                if bool(is_input) and port_text == "键":
                    key_text = normalize_type_text(key_type)
                    if key_text and (not is_generic_type_name(key_text)) and key_text != TYPE_FLOW:
                        self._visiting.remove(key)
                        self._memo[key] = key_text
                        return key_text
                if port_text == "值":
                    value_text = normalize_type_text(value_type)
                    if value_text and (not is_generic_type_name(value_text)) and value_text != TYPE_FLOW:
                        self._visiting.remove(key)
                        self._memo[key] = value_text
                        return value_text

        # 3.2.1) 节点特例：以键查询字典值（输入“字典”端口必须收敛为别名字典类型）
        #
        # 背景：
        # - 节点库通常将该节点声明为“泛型字典/泛型键/泛型值”；
        # - 但在具体图中，`字典` 端口必须被实例化为 `键类型-值类型字典`（或 `_`），
        #   否则后续导出（例如 .gia 的 VarType=27）无法写出字典 K/V 类型信息。
        #
        # 策略：
        # - 优先从 `键` 与 `默认值` 两个输入端口收敛键/值类型（override → 入边 → 常量）；
        # - 两者都可确定时，构造 `K-V字典` 写回为该端口的有效类型（供 UI/缓存/导出复用）。
        if bool(is_input) and port_text == "字典" and title == "以键查询字典值":
            inferred_dict_alias = ""

            def _infer_input_port_type_for_dict_query(input_port: str) -> str:
                t0 = resolve_override_type_for_node_port(self._overrides, str(node_id), str(input_port))
                if t0:
                    return normalize_type_text(t0)

                for e in self._incoming_edges.get((str(node_id), str(input_port)), []) or []:
                    src_node_id = str(getattr(e, "src_node", "") or "")
                    src_port = str(getattr(e, "src_port", "") or "")
                    if not src_node_id or not src_port:
                        continue
                    src_type = normalize_type_text(self.resolve(src_node_id, src_port, is_input=False))
                    if src_type and (not is_generic_type_name(src_type)) and src_type != TYPE_FLOW:
                        return src_type

                constants_map = getattr(node_obj, "input_constants", {}) or {}
                if isinstance(constants_map, dict) and str(input_port) in constants_map:
                    scalar = _infer_scalar_type_from_constant_value(constants_map.get(str(input_port)))
                    scalar_text = normalize_type_text(scalar)
                    if scalar_text and (not is_generic_type_name(scalar_text)) and scalar_text != TYPE_FLOW:
                        return scalar_text
                return ""

            k_type = _infer_input_port_type_for_dict_query("键")
            v_type = _infer_input_port_type_for_dict_query("默认值")
            if k_type and v_type and (not is_generic_type_name(k_type)) and (not is_generic_type_name(v_type)):
                if k_type != TYPE_FLOW and v_type != TYPE_FLOW:
                    inferred_dict_alias = f"{k_type}-{v_type}字典"

            inferred_text = normalize_type_text(inferred_dict_alias)
            if inferred_text and is_dict_type_name(inferred_text):
                self._visiting.remove(key)
                self._memo[key] = inferred_text
                return inferred_text

        # 3.0) 节点特例：基础算术节点（加减乘除）
        # - 节点声明为“泛型”但通过泛型约束限制为“整数/浮点数”；
        # - 在具体图中，输出“结果”必须跟随输入类型实例化，避免后续数据链路出现“泛型”残留。
        if (not bool(is_input)) and port_text == "结果" and title in {"加法运算", "减法运算", "乘法运算", "除法运算"}:
            left_type = self.resolve(str(node_id), "左值", is_input=True)
            right_type = self.resolve(str(node_id), "右值", is_input=True)
            for candidate in (left_type, right_type):
                text = normalize_type_text(candidate)
                if text and (not is_generic_type_name(text)) and text != TYPE_FLOW:
                    self._visiting.remove(key)
                    self._memo[key] = text
                    return text

        # 3.0.1) 节点特例：基础算术节点（加减乘除）的输入端口
        #
        # 背景：常量在 GraphModel 中往往以字符串形式存在（例如 "1"），且常量推断会刻意将“纯数字字符串”
        # 视为字符串以避免误判 GUID/配置ID 等标识；这会导致像 `x + 1` 的右值被推断为“字符串”。
        #
        # 规则：当输入端口自身没有入边（通常为常量）时，优先从同节点的其它端口约束反推：
        # - 先看兄弟输入口（左值/右值）是否已通过连线/override 收敛为具体类型；
        # - 再看输出“结果”的出边是否已被下游端口收敛为具体类型；
        # 从而保证“同型约束”的加减乘除在图内保持一致类型，避免 UI/导出出现“左值整数、右值字符串”的伪差异。
        if bool(is_input) and title in {"加法运算", "减法运算", "乘法运算", "除法运算"} and port_text in {"左值", "右值"}:
            incoming = self._incoming_edges.get((str(node_id), port_text), []) or []
            if not incoming:
                sibling_port = "右值" if port_text == "左值" else "左值"
                sibling_type = normalize_type_text(self.resolve(str(node_id), sibling_port, is_input=True))
                if sibling_type and (not is_generic_type_name(sibling_type)) and sibling_type != TYPE_FLOW:
                    self._visiting.remove(key)
                    self._memo[key] = sibling_type
                    return sibling_type

                # 避免输入→输出→输入的递归环：这里不直接 resolve("结果")，
                # 而是直接扫描“结果”的出边，从下游端口推断输出约束。
                downstream_candidates: list[str] = []
                for edge in self._outgoing_edges.get((str(node_id), "结果"), []) or []:
                    dst_node_id = str(getattr(edge, "dst_node", "") or "")
                    dst_port = str(getattr(edge, "dst_port", "") or "")
                    if not dst_node_id or not dst_port:
                        continue
                    dst_type = self.resolve(dst_node_id, dst_port, is_input=True)
                    dst_text = normalize_type_text(dst_type)
                    if not dst_text or is_generic_type_name(dst_text) or dst_text == TYPE_FLOW:
                        continue
                    downstream_candidates.append(dst_text)
                if downstream_candidates:
                    chosen = _dedupe_preserve_order(downstream_candidates)[0]
                    self._visiting.remove(key)
                    self._memo[key] = chosen
                    return chosen

        # 3.0.2) 节点特例：是否相等（输入端口同型约束）
        #
        # 背景：`是否相等` 的两个输入端口声明为“泛型”，但在具体图中需要通过连线/override
        # 实例化为同一具体类型；当一侧为常量（常量常以字符串保存）时，若不做同型约束反推，
        # 会出现“输入1=整数、输入2=字符串”的伪差异，导致 UI/Todo/导出口径不一致。
        if bool(is_input) and title == "是否相等" and port_text in {"输入1", "输入2"}:
            incoming = self._incoming_edges.get((str(node_id), port_text), []) or []
            if not incoming:
                sibling_port = "输入2" if port_text == "输入1" else "输入1"
                sibling_type = normalize_type_text(self.resolve(str(node_id), sibling_port, is_input=True))
                if sibling_type and (not is_generic_type_name(sibling_type)) and sibling_type != TYPE_FLOW:
                    self._visiting.remove(key)
                    self._memo[key] = sibling_type
                    return sibling_type

        # 3.0.3) 节点特例：数值比较（左值/右值输入端口同型约束）
        #
        # 背景：数值比较节点的输入端口声明为“泛型”，但在具体图中必须实例化为同一数值类型；
        # 当一侧为常量且该输入口无入边时，优先跟随兄弟输入口已收敛的具体类型，避免
        # “左值整数、右值字符串”这类由常量字符串化引入的伪差异。
        if bool(is_input) and title in {"数值小于", "数值小于等于", "数值大于", "数值大于等于"} and port_text in {"左值", "右值"}:
            incoming = self._incoming_edges.get((str(node_id), port_text), []) or []
            if not incoming:
                sibling_port = "右值" if port_text == "左值" else "左值"
                sibling_type = normalize_type_text(self.resolve(str(node_id), sibling_port, is_input=True))
                if sibling_type and (not is_generic_type_name(sibling_type)) and sibling_type != TYPE_FLOW:
                    self._visiting.remove(key)
                    self._memo[key] = sibling_type
                    return sibling_type

        # 3) 节点特例：拼装字典（键/值随输出“字典”的别名字典类型收敛）
        if bool(is_input) and title == "拼装字典" and (port_text.startswith("键") or port_text.startswith("值")):
            dict_type = self.resolve(str(node_id), "字典", is_input=False)
            ok, key_type, value_type = parse_typed_dict_alias(dict_type)
            if ok:
                if port_text.startswith("键") and key_type:
                    self._visiting.remove(key)
                    self._memo[key] = key_type
                    return key_type
                if port_text.startswith("值") and value_type:
                    self._visiting.remove(key)
                    self._memo[key] = value_type
                    return value_type

        # 3.0) 节点特例：拼装列表（输出“列表”从元素端口的具体类型反推）
        #
        # 背景：list_literal_rewriter 会把 `x = [a, b, c]` 改写为 `x = 拼装列表(self.game, a, b, c)`，
        # 但节点定义的输出端口类型为“泛型列表”。为避免大量“列表字面量 → 局部变量初始值(泛型)”导致校验失败，
        # 这里在输出侧从元素端口推断出具体列表类型（例如：元素为整数 → 输出为“整数列表”）。
        if (not bool(is_input)) and title == "拼装列表" and port_text == "列表":
            constants_map = getattr(node_obj, "input_constants", {}) or {}
            element_types: list[str] = []
            for p in (getattr(node_obj, "inputs", None) or []) or []:
                p_name = str(getattr(p, "name", "") or "").strip()
                if not p_name or not p_name.isdigit():
                    continue
                incoming = self._incoming_edges.get((str(node_id), str(p_name)), []) or []
                if incoming:
                    for edge_like in list(incoming):
                        src_node_id = ""
                        src_port = ""
                        if isinstance(edge_like, (tuple, list)) and len(edge_like) == 2:
                            src_node_id = str(edge_like[0] or "")
                            src_port = str(edge_like[1] or "")
                        else:
                            # 兼容实现差异：incoming index 可能直接存 EdgeModel
                            src_node_id = str(getattr(edge_like, "src_node", "") or "")
                            src_port = str(getattr(edge_like, "src_port", "") or "")
                        if not src_node_id or not src_port:
                            continue
                        inferred = normalize_type_text(self.resolve(str(src_node_id), str(src_port), is_input=False))
                        if inferred and (not is_generic_type_name(inferred)) and inferred != TYPE_FLOW:
                            element_types.append(inferred)
                elif isinstance(constants_map, dict) and p_name in constants_map:
                    scalar = normalize_type_text(_infer_scalar_type_from_constant_value(constants_map.get(p_name)))
                    if scalar and (not is_generic_type_name(scalar)) and scalar != TYPE_FLOW:
                        element_types.append(scalar)

            if element_types:
                first = element_types[0]
                if first and all(t == first for t in element_types):
                    list_type = str(BASE_TO_LIST_TYPE_MAP.get(first) or "").strip()
                    if list_type and (not is_generic_type_name(list_type)) and list_type != TYPE_FLOW:
                        self._visiting.remove(key)
                        self._memo[key] = list_type
                        return list_type

        # 3.0) 节点特例：拼装列表（元素端口随输出“列表”的元素类型收敛）
        # - `列表` 输出端口通常为“泛型列表家族”，会在具体图中被实例化为如“整数列表/字符串列表”；
        # - `0/1/2/...` 等元素输入端口应跟随该列表的元素类型，以保证画布与任务清单展示一致。
        if bool(is_input) and title == "拼装列表" and port_text.isdigit():
            list_type = self.resolve(str(node_id), "列表", is_input=False)
            element_type = _base_type_from_list_type_text(list_type)
            if element_type and (not is_generic_type_name(element_type)) and element_type != TYPE_FLOW:
                self._visiting.remove(key)
                self._memo[key] = element_type
                return element_type

        # 3.1) 节点特例：获取局部变量（server 形态），“值”输出与“初始值”输入同型透传
        if (not bool(is_input)) and title == "获取局部变量" and port_text == "值":
            has_initial = any(
                str(getattr(p, "name", "") or "") == "初始值" for p in (getattr(node_obj, "inputs", None) or [])
            )
            if has_initial:
                inferred = self.resolve(str(node_id), "初始值", is_input=True)
                if inferred and (not is_generic_type_name(inferred)) and inferred != TYPE_FLOW:
                    self._visiting.remove(key)
                    self._memo[key] = inferred
                    return inferred

        # 3.2) 节点特例：节点图变量 Get/Set
        # - `变量名` 端口本质是“变量名字符串”，不能用它来推断 `变量值` 的类型；
        # - `变量值` 的具体类型必须来自 GraphModel.graph_variables（变量定义表），否则 UI 会显示为泛型/字符串。
        if port_text == "变量值" and title in {"获取节点图变量", "设置节点图变量"}:
            is_value_port_direction = (title == "获取节点图变量" and not bool(is_input)) or (title == "设置节点图变量" and bool(is_input))
            if is_value_port_direction:
                constants_map = getattr(node_obj, "input_constants", {}) or {}
                if isinstance(constants_map, dict):
                    raw_var_name = constants_map.get("变量名")
                    if isinstance(raw_var_name, str) and raw_var_name.strip():
                        resolved = _resolve_graph_variable_type_by_name(self.graph_model, raw_var_name.strip())
                        resolved_text = normalize_type_text(resolved)
                        if resolved_text and (not is_generic_type_name(resolved_text)) and resolved_text != TYPE_FLOW:
                            self._visiting.remove(key)
                            self._memo[key] = resolved_text
                            return resolved_text

        # 3.3) 节点特例：对字典按值/按键排序
        #
        # 背景：该节点声明输出为“泛型列表”，但其输出类型与输入“字典”的别名字典类型存在一一对应关系：
        # - 字典键类型 → 键列表元素类型
        # - 字典值类型（整数/浮点数） → 值列表元素类型
        # 若不做该绑定，键列表/值列表会长期保持为“泛型列表”，从而导致后续【列表迭代循环】无法实例化类型并在校验阶段报错。
        if (not bool(is_input)) and title in {"对字典按值排序", "对字典按键排序"} and port_text in {"键列表", "值列表"}:
            dict_type = self.resolve(str(node_id), "字典", is_input=True)
            ok, key_type, value_type = parse_typed_dict_alias(dict_type)
            if ok:
                if port_text == "键列表" and key_type:
                    resolved = f"{key_type}列表"
                    self._visiting.remove(key)
                    self._memo[key] = resolved
                    return resolved
                if port_text == "值列表" and value_type:
                    resolved = f"{value_type}列表"
                    self._visiting.remove(key)
                    self._memo[key] = resolved
                    return resolved

        # 4) 输入侧：常量推断 + 连线推断
        if bool(is_input):
            inferred_from_constant = ""
            constants_map = getattr(node_obj, "input_constants", {}) or {}
            if isinstance(constants_map, dict) and port_text in constants_map:
                scalar = _infer_scalar_type_from_constant_value(constants_map.get(port_text))
                if scalar:
                    inferred_from_constant = _upgrade_to_list_type_if_needed(declared_text, scalar) or scalar

            candidate_types: list[str] = []
            for edge in self._incoming_edges.get((str(node_id), port_text), []) or []:
                src_node_id = str(getattr(edge, "src_node", "") or "")
                src_port = str(getattr(edge, "src_port", "") or "")
                if not src_node_id or not src_port:
                    continue
                src_type = self.resolve(src_node_id, src_port, is_input=False)
                src_text = normalize_type_text(src_type)
                if not src_text or is_generic_type_name(src_text) or src_text == TYPE_FLOW:
                    continue
                candidate_types.append(src_text)
            inferred_from_edges = ""
            if candidate_types:
                inferred_from_edges = _dedupe_preserve_order(candidate_types)[0]

            effective = normalize_type_text(inferred_from_constant)
            if _should_override_with_edge_type(effective, inferred_from_edges):
                effective = normalize_type_text(inferred_from_edges)
            if effective and (not is_generic_type_name(effective)) and effective != TYPE_FLOW:
                self._visiting.remove(key)
                self._memo[key] = effective
                return effective
            if inferred_from_edges and (not is_generic_type_name(inferred_from_edges)) and inferred_from_edges != TYPE_FLOW:
                self._visiting.remove(key)
                self._memo[key] = inferred_from_edges
                return inferred_from_edges

            fallback = declared_text if declared_text else TYPE_GENERIC
            if snapshot_existing and is_generic_type_name(fallback):
                fallback = snapshot_existing
            self._visiting.remove(key)
            self._memo[key] = fallback
            return fallback

        # 5) 输出侧：基于本节点输入常量派生 + 出边推断
        inferred_output = ""
        if node_def is not None:
            input_constants = dict(getattr(node_obj, "input_constants", {}) or {})
            if input_constants:
                valid_input_names = [
                    str(getattr(p, "name", "") or "") for p in (getattr(node_obj, "inputs", None) or [])
                ]
                valid_input_names = [name for name in valid_input_names if name]
                candidates: list[str] = []
                for input_port_name, value in input_constants.items():
                    if valid_input_names and str(input_port_name) not in valid_input_names:
                        continue
                    input_declared = safe_get_port_type_from_node_def(node_def, str(input_port_name), is_input=True)
                    input_declared_text = normalize_type_text(input_declared)
                    if input_declared_text and (not is_generic_type_name(input_declared_text)):
                        continue
                    scalar = _infer_scalar_type_from_constant_value(value)
                    if not scalar:
                        continue
                    if declared_text and is_list_type_name(declared_text):
                        upgraded = _upgrade_to_list_type_if_needed(declared_text, scalar)
                        upgraded_text = normalize_type_text(upgraded)
                        if upgraded_text and upgraded_text != scalar and (not is_generic_type_name(upgraded_text)):
                            candidates.append(upgraded_text)
                    else:
                        if not is_generic_type_name(scalar):
                            candidates.append(scalar)
                if candidates:
                    inferred_output = _dedupe_preserve_order(candidates)[0]

        inferred_text = normalize_type_text(inferred_output)
        if (
            inferred_text
            and (not is_generic_type_name(inferred_text))
            and inferred_text != TYPE_FLOW
            and (not inferred_text.startswith(TYPE_STRING))
        ):
            self._visiting.remove(key)
            self._memo[key] = inferred_text
            return inferred_text

        out_candidates: list[str] = []
        for edge in self._outgoing_edges.get((str(node_id), port_text), []) or []:
            dst_node_id = str(getattr(edge, "dst_node", "") or "")
            dst_port = str(getattr(edge, "dst_port", "") or "")
            if not dst_node_id or not dst_port:
                continue
            dst_type = self.resolve(dst_node_id, dst_port, is_input=True)
            dst_text = normalize_type_text(dst_type)
            if not dst_text or is_generic_type_name(dst_text) or dst_text == TYPE_FLOW:
                continue
            out_candidates.append(dst_text)
        inferred_from_edges = ""
        if out_candidates:
            inferred_from_edges = _dedupe_preserve_order(out_candidates)[0]

        # 常量推断较保守：数字常量常以字符串形式保存，且“纯数字字符串”会被保守视为字符串；
        # 若下游已通过连线收敛到更具体类型，则允许用边推断覆盖字符串推断，避免类型长期漂移。
        effective = inferred_text
        if _should_override_with_edge_type(effective, inferred_from_edges):
            effective = normalize_type_text(inferred_from_edges)

        if effective and (not is_generic_type_name(effective)) and effective != TYPE_FLOW:
            self._visiting.remove(key)
            self._memo[key] = effective
            return effective
        if inferred_from_edges and (not is_generic_type_name(inferred_from_edges)) and inferred_from_edges != TYPE_FLOW:
            self._visiting.remove(key)
            self._memo[key] = inferred_from_edges
            return inferred_from_edges

        fallback = declared_text if declared_text else TYPE_GENERIC
        if snapshot_existing and is_generic_type_name(fallback):
            fallback = snapshot_existing
        self._visiting.remove(key)
        self._memo[key] = fallback
        return fallback


def apply_effective_port_type_snapshots(
    model: GraphModel,
    *,
    node_def_resolver: Callable[[NodeModel], Any],
    port_type_overrides: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
    """将“有效类型”写回到 NodeModel.effective_input_types/effective_output_types（仅覆盖泛型/缺失项）。

说明：
- 已存在且为“具体非泛型”的快照类型会被保留；
- 仅对图中实际存在的端口名写入（避免把 node_def 的虚拟端口写入快照）。
"""
    overrides = port_type_overrides if port_type_overrides is not None else build_port_type_overrides(model)
    resolver = EffectivePortTypeResolver(
        model,
        node_def_resolver=node_def_resolver,
        port_type_overrides=overrides,
    )

    for node in (getattr(model, "nodes", None) or {}).values():
        node_id = str(getattr(node, "id", "") or "")
        existing_in = dict(getattr(node, "effective_input_types", {}) or {})
        existing_out = dict(getattr(node, "effective_output_types", {}) or {})

        new_in: Dict[str, str] = {}
        for port in getattr(node, "inputs", None) or []:
            port_name = str(getattr(port, "name", "") or "").strip()
            if not port_name:
                continue
            existing = normalize_type_text(existing_in.get(port_name, ""))
            resolved = normalize_type_text(resolver.resolve(node_id, port_name, is_input=True))
            # 升级/纠错策略：
            # - 若 resolver 能给出“具体非泛型”类型，则以 resolver 结果为准（可纠正旧缓存里的错误快照）；
            # - 若 resolver 只能回退为泛型，但旧快照已有具体类型，则保留旧快照避免降级。
            if resolved and (not is_generic_type_name(resolved)) and resolved != TYPE_FLOW:
                new_in[port_name] = resolved
            elif existing and (not is_generic_type_name(existing)) and existing != TYPE_FLOW:
                new_in[port_name] = existing
            else:
                new_in[port_name] = resolved or TYPE_GENERIC

        new_out: Dict[str, str] = {}
        for port in getattr(node, "outputs", None) or []:
            port_name = str(getattr(port, "name", "") or "").strip()
            if not port_name:
                continue
            existing = normalize_type_text(existing_out.get(port_name, ""))
            resolved = normalize_type_text(resolver.resolve(node_id, port_name, is_input=False))
            if resolved and (not is_generic_type_name(resolved)) and resolved != TYPE_FLOW:
                new_out[port_name] = resolved
            elif existing and (not is_generic_type_name(existing)) and existing != TYPE_FLOW:
                new_out[port_name] = existing
            else:
                new_out[port_name] = resolved or TYPE_GENERIC

        node.effective_input_types = new_in
        node.effective_output_types = new_out


__all__ = [
    "is_generic_type_name",
    "normalize_node_id_for_overrides",
    "build_port_type_overrides",
    "get_node_port_type_overrides_for_id",
    "resolve_override_type_for_node_port",
    "safe_get_port_type_from_node_def",
    "EffectivePortTypeResolver",
    "apply_effective_port_type_snapshots",
]


