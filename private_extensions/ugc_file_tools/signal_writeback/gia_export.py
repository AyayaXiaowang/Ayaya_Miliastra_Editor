from __future__ import annotations

import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message, format_binary_data_hex_text
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root

from . import helpers as signal_helpers


@dataclass(frozen=True, slots=True)
class BasicSignalPyRecord:
    """代码级基础信号（*.py）记录（用于 UI 列表与导出）。"""

    signal_id_str: str  # 来自 SIGNAL_ID（字符串）
    signal_name: str  # 来自 SIGNAL_PAYLOAD.signal_name
    py_path: Path
    scope: str  # "shared" | "project"
    payload: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExportBasicSignalsGiaPlan:
    """
    将项目存档（共享根 + 项目根）的“基础信号（*.py）”导出为 `.gia`。

    说明：
    - 输出为一组 GraphUnit（信号相关的 node_def：发送/监听/向服务器发送），复用真源样本结构。
    - 由于信号 node_def 结构复杂，导出采用“模板 .gia → 深拷贝 → 定点 patch”的策略，避免手工拼装全字段。
    """

    project_archive_path: Path | None = None
    output_gia_file_name_in_out: str = "基础信号.gia"
    game_version: str = "6.3.0"

    selected_signal_ids: Sequence[str] | None = None
    output_user_dir: Path | None = None

    template_gia: Path | None = None


def parse_signal_payload_to_params(signal_payload: Mapping[str, Any]) -> tuple[str, list[dict[str, object]]]:
    """
    Public API (no leading underscores).

    将代码级 `SIGNAL_PAYLOAD`（dict）解析为：
    - signal_name: str
    - params: list[{param_name, type_id}]

    说明：
    - `parameters` 的 schema 对齐 Graph_Generater 侧信号定义（name/parameter_type/...）。
    - 参数类型文本映射统一复用 `node_graph_semantics.var_base.map_server_port_type_to_var_type_id`。
    """
    if not isinstance(signal_payload, Mapping):
        raise TypeError("signal_payload must be a mapping")

    name = str(signal_payload.get("signal_name") or "").strip()
    if name == "":
        raise ValueError("signal_payload.signal_name is required")

    parameters = signal_payload.get("parameters")
    if parameters is None:
        parameters = signal_payload.get("params")
    if parameters is None:
        parameters = signal_payload.get("signal_params")

    if parameters is None:
        params_list: list[dict[str, object]] = []
        return name, params_list

    if not isinstance(parameters, list):
        raise TypeError("signal_payload.parameters must be a list")

    from ugc_file_tools.node_graph_semantics.var_base import map_server_port_type_to_var_type_id

    out: list[dict[str, object]] = []
    for item in list(parameters):
        if not isinstance(item, Mapping):
            raise TypeError("signal_payload.parameters item must be a mapping")
        param_name = str(item.get("name") or "").strip()
        if param_name == "":
            raise ValueError("signal_payload.parameters item missing name")
        type_text = str(item.get("parameter_type") or item.get("type") or "").strip()
        if type_text == "":
            raise ValueError(f"signal_payload.parameters item missing parameter_type: {param_name!r}")
        type_id = int(map_server_port_type_to_var_type_id(str(type_text)))
        out.append({"param_name": str(param_name), "type_id": int(type_id)})

    return name, out


def _iter_basic_signal_py_files_in_project(project_archive_path: Path) -> List[Path]:
    directory = Path(project_archive_path) / "管理配置" / "信号"
    if not directory.is_dir():
        return []
    files = sorted(
        [
            p
            for p in directory.rglob("*.py")
            if p.is_file()
            and p.suffix.lower() == ".py"
            and p.name != "__init__.py"
            and (not p.name.startswith("_"))
            and p.parent.name != "__pycache__"
        ],
        key=lambda p: p.as_posix().casefold(),
    )
    return files


def _iter_basic_signal_py_files_in_shared_root() -> List[Path]:
    directory = repo_root() / "assets" / "资源库" / "共享" / "管理配置" / "信号"
    if not directory.is_dir():
        return []
    files = sorted(
        [
            p
            for p in directory.rglob("*.py")
            if p.is_file()
            and p.suffix.lower() == ".py"
            and p.name != "__init__.py"
            and (not p.name.startswith("_"))
            and p.parent.name != "__pycache__"
        ],
        key=lambda p: p.as_posix().casefold(),
    )
    return files


def collect_basic_signal_py_records(*, project_archive_path: Path | None) -> List[BasicSignalPyRecord]:
    """收集基础信号定义（共享根 + 项目根；同 SIGNAL_ID 项目覆盖共享）。"""
    shared_files = _iter_basic_signal_py_files_in_shared_root()
    project_files = _iter_basic_signal_py_files_in_project(project_archive_path) if project_archive_path else []

    by_id: Dict[str, BasicSignalPyRecord] = {}

    def _load_record(py_path: Path, *, scope: str) -> BasicSignalPyRecord | None:
        env = runpy.run_path(str(py_path))
        sid_raw = env.get("SIGNAL_ID")
        if sid_raw is None:
            # 允许目录下存在辅助脚本，但必须显式不定义 SIGNAL_ID
            return None
        sid = str(sid_raw or "").strip()
        if sid == "":
            raise ValueError(f"SIGNAL_ID 为空：{str(py_path)}")

        payload = env.get("SIGNAL_PAYLOAD")
        if not isinstance(payload, dict):
            raise ValueError(f"SIGNAL_PAYLOAD 缺失或不是 dict：{str(py_path)}")
        name = str(payload.get("signal_name") or "").strip()
        if name == "":
            raise ValueError(f"SIGNAL_PAYLOAD.signal_name 为空：{str(py_path)}")

        return BasicSignalPyRecord(
            signal_id_str=str(sid),
            signal_name=str(name),
            py_path=Path(py_path),
            scope=str(scope),
            payload=dict(payload),
        )

    for p in shared_files:
        record = _load_record(Path(p), scope="shared")
        if record is not None:
            by_id[str(record.signal_id_str)] = record

    for p in project_files:
        record = _load_record(Path(p), scope="project")
        if record is not None:
            by_id[str(record.signal_id_str)] = record

    # 稳定排序：先按 name，再按 id
    return sorted(by_id.values(), key=lambda r: (str(r.signal_name).casefold(), str(r.signal_id_str).casefold()))


def _default_template_gia_path() -> Path:
    # 内置模板：包含多个信号定义，便于抽取三类 node_def 的结构模板
    return (
        Path(__file__).resolve().parents[1]
        / "builtin_resources"
        / "gia_templates"
        / "signals"
        / "signal_node_defs_full.gia"
    ).resolve()


def _ensure_dict(value: Any, *, hint: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"expected dict: {hint}, got {type(value).__name__}")
    return value


def _ensure_list(value: Any, *, hint: str) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(f"expected list: {hint}, got {type(value).__name__}")
    return value


def _ensure_list_field(parent: Dict[str, Any], key: str) -> List[Any]:
    """
    兼容样本差异：repeated message 在“只有 1 个元素”时可能表现为 dict（标量）或 list。
    返回可写的 list 视图，并在必要时就地把 parent[key] 归一化为 list。
    """
    value = parent.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        parent[key] = [value]
        return parent[key]
    if value is None:
        parent[key] = []
        return parent[key]
    raise ValueError(f"expected list/dict/None at key={key!r}, got {type(value).__name__}")


def _iter_graph_units_in_root(root_msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    main = root_msg.get("1")
    if isinstance(main, dict):
        units.append(main)
    elif isinstance(main, list):
        for u in main:
            if isinstance(u, dict):
                units.append(u)
    accessories = root_msg.get("2")
    if isinstance(accessories, list):
        for u in accessories:
            if isinstance(u, dict):
                units.append(u)
    return units


def _get_graph_unit_name(unit: Mapping[str, Any]) -> str:
    name = unit.get("3")
    return str(name or "").strip() if isinstance(name, str) else ""


def _find_node_def_object_in_graph_unit(unit: Dict[str, Any], *, expected_node_def_name: str) -> Dict[str, Any]:
    """
    在 GraphUnit 中定位 node_def 业务对象（dict，且包含 key '200' 为中文 node_def 名称）。
    由于 GraphUnit 内部 wrapper 层级可能变化，这里使用“递归扫描 + 结构特征”定位，避免硬编码路径。
    """
    expected = str(expected_node_def_name).strip()
    if expected == "":
        raise ValueError("expected_node_def_name 不能为空")

    found: List[Dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            v200 = value.get("200")
            if isinstance(v200, str) and v200.strip() == expected:
                # 结构特征：信号 node_def 至少包含 meta(4) 与 signal_info(107)
                if isinstance(value.get("4"), dict) and isinstance(value.get("107"), dict):
                    found.append(value)
            for child in value.values():
                walk(child)
            return
        if isinstance(value, list):
            for child in value:
                walk(child)
            return

    walk(unit)

    if len(found) != 1:
        raise ValueError(f"未能唯一定位 node_def（expected={expected!r}，found={len(found)}）")
    return dict(found[0])


def _set_node_def_id_inplace(node_def: Dict[str, Any], *, node_def_id_int: int) -> None:
    meta = _ensure_dict(node_def.get("4"), hint="node_def.4(meta)")
    meta1 = _ensure_dict(meta.get("1"), hint="node_def.4.1(meta1)")
    meta1["5"] = int(node_def_id_int)
    meta2 = meta.get("2")
    if isinstance(meta2, dict):
        meta2["5"] = int(node_def_id_int)


def _set_signal_index_inplace(node_def: Dict[str, Any], *, signal_index_int: int) -> None:
    meta = _ensure_dict(node_def.get("4"), hint="node_def.4(meta)")
    meta["5"] = int(signal_index_int)


def _set_port_index_inplace(port_obj: Dict[str, Any], *, port_index_int: int) -> None:
    port_obj["8"] = int(port_index_int)


def _ensure_single_dict_container(node_def: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    兼容少量样本：同一字段在不同导出中可能表现为 dict 或单元素 list[dict]。
    对于信号 node_def 的 100/101（流程端口容器），语义上应只有 1 个元素。
    """
    value = node_def.get(key)
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        if len(value) != 1 or not isinstance(value[0], dict):
            raise ValueError(f"expected {key} list[dict] len=1")
        return value[0]
    raise ValueError(f"expected dict/list at key={key!r}, got {type(value).__name__}")


def _build_node_def_meta_dict(*, node_def_id_int: int, scope_code_int: int) -> Dict[str, Any]:
    # 与 signal_writeback.helpers._build_node_def_meta_dict 对齐（复用其口径）
    return signal_helpers._build_node_def_meta_dict(node_def_id_int=int(node_def_id_int), scope_code_int=int(scope_code_int))


_SERVER_SIGNAL_DESCRIPTOR_TYPE_ID_BY_VAR_TYPE: Dict[int, int] = {
    # 与“可运行样本”对齐的 server-send 参数描述类型号（field_4.field_3/field_4.field_4）
    1: 1,   # 实体
    2: 14,  # GUID（样本：发送者GUID）
    3: 3,   # 整数
    4: 5,   # 布尔值
    5: 7,   # 浮点数
    6: 9,   # 字符串
    8: 4,   # 整数列表
    9: 6,   # 布尔值列表
    10: 8,  # 浮点数列表
    11: 10, # 字符串列表
}


def _map_server_signal_descriptor_type_id(*, var_type_id: int) -> int:
    vt = int(var_type_id)
    mapped = _SERVER_SIGNAL_DESCRIPTOR_TYPE_ID_BY_VAR_TYPE.get(int(vt))
    if isinstance(mapped, int):
        return int(mapped)

    # 列表类型：优先尝试“元素类型映射后 +1”规则（对齐样本：Str(9) -> L<Str>(10)）。
    if signal_helpers._is_list_type_id(int(vt)):
        element_vt = signal_helpers._resolve_element_type_id_for_list_type(int(vt))
        mapped_element_vt = _map_server_signal_descriptor_type_id(var_type_id=int(element_vt))
        return int(mapped_element_vt + 1)

    # 未覆盖类型保持原值，避免无样本类型被强行错误映射。
    return int(vt)


def _build_server_scalar_type_descriptor(*, scalar_type_id_int: int, struct_id_int: int | None) -> Dict[str, Any]:
    descriptor = signal_helpers._build_scalar_type_descriptor(
        type_id_int=int(scalar_type_id_int),
        struct_id_int=(int(struct_id_int) if isinstance(struct_id_int, int) else None),
        dict_key_type_id_int=None,
        dict_value_type_id_int=None,
    )
    mapped_type_id = _map_server_signal_descriptor_type_id(var_type_id=int(scalar_type_id_int))
    descriptor["3"] = int(mapped_type_id)
    descriptor["4"] = int(mapped_type_id)

    # server-send 的 bool 描述字段与 send/listen 不同：field_101 需要写 200001。
    if int(scalar_type_id_int) == 4:
        descriptor["101"] = format_binary_data_hex_text(encode_message({"1": 200001}))

    return descriptor


def _build_server_type_descriptor_from_param_spec(*, param_spec: Mapping[str, Any]) -> Dict[str, Any]:
    type_id_value = param_spec.get("type_id")
    if not isinstance(type_id_value, int):
        raise ValueError("param_spec missing type_id int")
    type_id_int = int(type_id_value)

    if int(type_id_int) == 27:
        raise ValueError("信号参数类型不支持『字典』(type_id=27)")

    struct_id_int: int | None = None
    if int(type_id_int) in (25, 26):
        struct_id_int = signal_helpers._parse_optional_int_like(param_spec.get("struct_id"), field_name="struct_id")
        if not isinstance(struct_id_int, int):
            raise ValueError("struct/struct_list param requires struct_id")

    if signal_helpers._is_list_type_id(int(type_id_int)):
        element_type_id_int = signal_helpers._resolve_element_type_id_for_list_type(int(type_id_int))
        element_descriptor = _build_server_scalar_type_descriptor(
            scalar_type_id_int=int(element_type_id_int),
            struct_id_int=struct_id_int,
        )
        wrapper_bytes_text = format_binary_data_hex_text(encode_message({"1": dict(element_descriptor)}))
        mapped_list_type_id = _map_server_signal_descriptor_type_id(var_type_id=int(type_id_int))
        return {
            "1": 10002,
            "102": str(wrapper_bytes_text),
            "3": int(mapped_list_type_id),
            "4": int(mapped_list_type_id),
        }

    return _build_server_scalar_type_descriptor(
        scalar_type_id_int=int(type_id_int),
        struct_id_int=struct_id_int,
    )


def _build_param_item_message_from_param_spec(
    *,
    param_spec: Mapping[str, Any],
    port_index_int: int,
    param_ordinal_int: int = 0,
    for_server_node: bool = False,
) -> Dict[str, Any]:
    """
    构造 send/server node_def['102'] 内的 param item message（非 binary 文本）。
    对齐可运行样本：
    - field_3.field_2：写“参数序号”（首个参数省略）；
    - server-send 的 field_4 类型描述使用 server 口径（与 send/listen 不同）。
    """
    param_name = str(param_spec.get("param_name") or "").strip()
    if param_name == "":
        raise ValueError("param_spec missing param_name")
    type_id_value = param_spec.get("type_id")
    if not isinstance(type_id_value, int):
        raise ValueError("param_spec missing type_id int")
    type_id_int = int(type_id_value)

    ordinal = int(param_ordinal_int)
    if int(ordinal) < 0:
        raise ValueError(f"param_ordinal_int must be >= 0, got {ordinal}")

    field_3_msg: Dict[str, Any] = {"1": 3}
    if int(ordinal) > 0:
        field_3_msg["2"] = int(ordinal)

    type_descriptor = (
        _build_server_type_descriptor_from_param_spec(param_spec=param_spec)
        if bool(for_server_node)
        else signal_helpers._build_type_descriptor_from_param_spec(param_spec=param_spec)
    )

    return {
        "1": str(param_name),
        "2": 1,
        "3": dict(field_3_msg),
        "4": dict(type_descriptor),
        "8": int(port_index_int),
    }


def _reset_send_node_def_for_new_signal(
    *,
    node_def: Dict[str, Any],
    signal_index_int: int,
    node_def_id_int: int,
    signal_name: str,
    listen_meta_dict: Dict[str, Any],
    server_meta_dict: Dict[str, Any],
    flow_in_port_index: int,
    flow_out_port_index: int,
    signal_name_port_index: int,
    send_param_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    signal_helpers._ensure_node_def_name(node_def, "发送信号")
    _set_node_def_id_inplace(node_def, node_def_id_int=int(node_def_id_int))
    _set_signal_index_inplace(node_def, signal_index_int=int(signal_index_int))

    _set_port_index_inplace(_ensure_single_dict_container(node_def, "100"), port_index_int=int(flow_in_port_index))
    _set_port_index_inplace(_ensure_single_dict_container(node_def, "101"), port_index_int=int(flow_out_port_index))

    ports_106 = _ensure_list_field(node_def, "106")
    if not (ports_106 and isinstance(ports_106[0], dict)):
        raise ValueError("send node_def missing 106 list[0]")
    ports_106[0]["8"] = int(signal_name_port_index)

    sig = _ensure_dict(node_def.get("107"), hint="send.107(signal)")
    sig101 = _ensure_dict(sig.get("101"), hint="send.107.101")
    sig101["1"] = str(signal_name)
    sig101["2"] = dict(listen_meta_dict)
    sig101["3"] = dict(server_meta_dict)

    if send_param_items:
        node_def["102"] = list(send_param_items)
    else:
        node_def.pop("102", None)
    return node_def


def _reset_listen_node_def_for_new_signal(
    *,
    node_def: Dict[str, Any],
    signal_index_int: int,
    node_def_id_int: int,
    signal_name: str,
    send_meta_dict: Dict[str, Any],
    server_meta_dict: Dict[str, Any],
    flow_port_index: int,
    signal_name_port_index: int,
    fixed_output_port_indices: Tuple[int, int, int],
    params: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    signal_helpers._ensure_node_def_name(node_def, "监听信号")
    _set_node_def_id_inplace(node_def, node_def_id_int=int(node_def_id_int))
    _set_signal_index_inplace(node_def, signal_index_int=int(signal_index_int))

    _set_port_index_inplace(_ensure_single_dict_container(node_def, "101"), port_index_int=int(flow_port_index))

    ports_106 = _ensure_list_field(node_def, "106")
    if not (ports_106 and isinstance(ports_106[0], dict)):
        raise ValueError("listen node_def missing 106 list[0]")
    ports_106[0]["8"] = int(signal_name_port_index)

    fixed_names = ["事件源实体", "事件源GUID", "信号来源实体"]
    ports_103 = _ensure_list_field(node_def, "103")
    fixed_ports: List[Dict[str, Any]] = []
    for item in ports_103:
        if not isinstance(item, dict):
            continue
        name = str(item.get("1") or "").strip()
        if name in fixed_names:
            fixed_ports.append(item)
    if len(fixed_ports) != 3:
        raise ValueError(f"listen node_def fixed outputs not found or not unique: found={len(fixed_ports)}")

    name_to_port = {str(p.get("1") or "").strip(): dict(p) for p in fixed_ports}
    name_to_port["事件源实体"]["8"] = int(fixed_output_port_indices[0])
    name_to_port["事件源GUID"]["8"] = int(fixed_output_port_indices[1])
    name_to_port["信号来源实体"]["8"] = int(fixed_output_port_indices[2])

    new_ports_103: List[Dict[str, Any]] = [name_to_port[n] for n in fixed_names]
    for param_index, param in enumerate(params):
        param_name = str(param.get("param_name") or "").strip()
        type_id = param.get("type_id")
        port_index = param.get("port_index")
        if param_name == "" or not isinstance(type_id, int) or not isinstance(port_index, int):
            raise ValueError("listen params requires param_name/type_id/port_index")

        port_obj = signal_helpers._build_listen_param_port_object_from_param_spec(
            param_spec=param,
            param_index=int(param_index),
        )
        port_obj["8"] = int(port_index)
        new_ports_103.append(dict(port_obj))

    node_def["103"] = new_ports_103

    sig = _ensure_dict(node_def.get("107"), hint="listen.107(signal)")
    sig102 = _ensure_dict(sig.get("102"), hint="listen.107.102")
    sig102["1"] = str(signal_name)
    sig102["2"] = dict(send_meta_dict)
    sig102["3"] = dict(server_meta_dict)

    return node_def


def _reset_send_to_server_node_def_for_new_signal(
    *,
    node_def: Dict[str, Any],
    signal_index_int: int,
    node_def_id_int: int,
    signal_name: str,
    listen_meta_dict: Dict[str, Any],
    send_meta_dict: Dict[str, Any],
    flow_in_port_index: int,
    flow_out_port_index: int,
    extra_port_index: int,
    signal_name_port_index: int,
    server_param_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    signal_helpers._ensure_node_def_name(node_def, "向服务器节点图发送信号")
    _set_node_def_id_inplace(node_def, node_def_id_int=int(node_def_id_int))
    _set_signal_index_inplace(node_def, signal_index_int=int(signal_index_int))

    _set_port_index_inplace(_ensure_single_dict_container(node_def, "100"), port_index_int=int(flow_in_port_index))
    _set_port_index_inplace(_ensure_single_dict_container(node_def, "101"), port_index_int=int(flow_out_port_index))

    ports_106 = _ensure_list_field(node_def, "106")
    if len(ports_106) < 2 or (not isinstance(ports_106[0], dict)) or (not isinstance(ports_106[1], dict)):
        raise ValueError("send_to_server node_def missing 106 list[0..1]")
    ports_106[0]["8"] = int(extra_port_index)
    ports_106[1]["8"] = int(signal_name_port_index)

    sig = _ensure_dict(node_def.get("107"), hint="server.107(signal)")
    sig101 = _ensure_dict(sig.get("101"), hint="server.107.101")
    sig101["1"] = str(signal_name)
    sig101["2"] = dict(listen_meta_dict)
    sig101["3"] = dict(send_meta_dict)

    if server_param_items:
        node_def["102"] = list(server_param_items)
    else:
        node_def.pop("102", None)

    return node_def


def _build_graph_unit_id_for_node_def(*, node_def_id_int: int) -> Dict[str, Any]:
    # 对齐真源样本（class=23，type 多数省略/为 0；id=0x6000_0001...）
    return {"2": 23, "4": int(node_def_id_int)}


def _set_graph_unit_id_inplace(unit: Dict[str, Any], *, node_def_id_int: int) -> None:
    unit_id = unit.get("1")
    if isinstance(unit_id, dict):
        unit_id["4"] = int(node_def_id_int)
    else:
        unit["1"] = _build_graph_unit_id_for_node_def(node_def_id_int=int(node_def_id_int))


def _set_graph_unit_related_ids_inplace(unit: Dict[str, Any], *, related_node_def_ids: Sequence[int]) -> None:
    unit["2"] = [{"2": 23, "4": int(v)} for v in list(related_node_def_ids)]


def _parse_signal_payload_to_params(payload: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    signal_name = str(payload.get("signal_name") or "").strip()
    if signal_name == "":
        raise ValueError("SIGNAL_PAYLOAD.signal_name 不能为空")

    raw_params = payload.get("parameters") or []
    if not isinstance(raw_params, list):
        raise ValueError("SIGNAL_PAYLOAD.parameters 必须是 list")

    params: List[Dict[str, Any]] = []
    for item in raw_params:
        if not isinstance(item, Mapping):
            continue
        param_name = str(item.get("name") or "").strip()
        param_type = item.get("parameter_type")
        if param_name == "":
            raise ValueError(f"signal param missing name: signal={signal_name!r}")

        # 对齐 signal_writeback 的类型约束（不支持字典/别名字典）
        type_id_int = int(signal_helpers._parse_type_id(param_type))

        param_spec: Dict[str, Any] = {"param_name": str(param_name), "type_id": int(type_id_int)}
        if "struct_id" in item:
            param_spec["struct_id"] = item.get("struct_id")

        params.append(param_spec)

    return str(signal_name), params


def _load_signal_node_def_templates_from_gia(template_gia_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    从模板 `.gia` 中提取三个 GraphUnit（发送/监听/向服务器发送）作为模板（深拷贝返回）。
    """
    proto_bytes = unwrap_gia_container(Path(template_gia_path).resolve(), check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=16,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（信号模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)
    if not isinstance(root_msg, dict):
        raise ValueError("信号模板 .gia root 不是 dict")

    by_name: Dict[str, Dict[str, Any]] = {}
    for unit in _iter_graph_units_in_root(dict(root_msg)):
        name = _get_graph_unit_name(unit)
        if name and name not in by_name:
            by_name[name] = dict(unit)

    def _pick(name: str) -> Dict[str, Any]:
        unit = by_name.get(name)
        if not isinstance(unit, dict):
            raise ValueError(f"信号模板 .gia 缺少 GraphUnit：{name!r}")
        return dict(unit)

    return _pick("发送信号"), _pick("监听信号"), _pick("向服务器节点图发送信号")


def export_basic_signals_to_gia(*, plan: ExportBasicSignalsGiaPlan) -> Dict[str, Any]:
    import copy
    import shutil

    project_archive_path = Path(plan.project_archive_path).resolve() if plan.project_archive_path is not None else None
    if project_archive_path is not None and (not project_archive_path.is_dir()):
        raise FileNotFoundError(str(project_archive_path))

    records = collect_basic_signal_py_records(project_archive_path=project_archive_path)
    if not records:
        raise ValueError("未找到任何基础信号定义（*.py）")

    selected_ids = plan.selected_signal_ids
    if selected_ids is not None:
        selected_set = {str(s).strip() for s in list(selected_ids) if str(s).strip() != ""}
        if not selected_set:
            raise ValueError("selected_signal_ids 为空（至少需要选择 1 个信号）")
        records = [r for r in records if str(r.signal_id_str) in selected_set]
        if not records:
            raise ValueError("未匹配到任何选中的信号（selected_signal_ids）")

    template_gia = Path(plan.template_gia).resolve() if plan.template_gia is not None else _default_template_gia_path()
    if not template_gia.is_file():
        raise FileNotFoundError(str(template_gia))
    tpl_send_unit, tpl_listen_unit, tpl_server_unit = _load_signal_node_def_templates_from_gia(template_gia)

    # 预先定位 node_def（并把定位结果写回到 unit 中，后续只做拷贝+patch）
    tpl_send_node_def = _find_node_def_object_in_graph_unit(dict(tpl_send_unit), expected_node_def_name="发送信号")
    tpl_listen_node_def = _find_node_def_object_in_graph_unit(dict(tpl_listen_unit), expected_node_def_name="监听信号")
    tpl_server_node_def = _find_node_def_object_in_graph_unit(dict(tpl_server_unit), expected_node_def_name="向服务器节点图发送信号")

    # 分配策略：对齐写回脚本默认值（node_def_id 从 0x60000001 起；signal_index 从 1 起；port_index 从 1 起）
    next_node_def_id = 0x60000001
    next_signal_index = 1
    next_port_index = 1

    send_units: List[Dict[str, Any]] = []
    accessory_units: List[Dict[str, Any]] = []
    exported_signal_ids: List[str] = []
    exported_signal_names: List[str] = []

    for record in list(records):
        payload = record.payload
        signal_name, params = _parse_signal_payload_to_params(payload)

        # allocate ids
        send_node_def_id = int(next_node_def_id)
        listen_node_def_id = int(next_node_def_id + 1)
        server_node_def_id = int(next_node_def_id + 2)
        next_node_def_id += 3

        signal_index_int = int(next_signal_index)
        next_signal_index += 1

        send_meta = _build_node_def_meta_dict(node_def_id_int=send_node_def_id, scope_code_int=20000)
        listen_meta = _build_node_def_meta_dict(node_def_id_int=listen_node_def_id, scope_code_int=20000)
        server_meta = _build_node_def_meta_dict(node_def_id_int=server_node_def_id, scope_code_int=20002)

        # allocate fixed port indices
        send_flow_in = int(next_port_index)
        send_flow_out = int(next_port_index + 1)
        send_signal_name_port = int(next_port_index + 2)
        next_port_index += 3

        listen_flow = int(next_port_index)
        listen_signal_name_port = int(next_port_index + 1)
        listen_event_source_entity = int(next_port_index + 2)
        listen_event_source_guid = int(next_port_index + 3)
        listen_signal_source_entity = int(next_port_index + 4)
        next_port_index += 5

        server_flow_in = int(next_port_index)
        server_flow_out = int(next_port_index + 1)
        server_extra_port = int(next_port_index + 2)
        server_signal_name_port = int(next_port_index + 3)
        next_port_index += 4

        send_param_items: List[Dict[str, Any]] = []
        server_param_items: List[Dict[str, Any]] = []
        listen_param_ports: List[Dict[str, Any]] = []

        for param_ordinal, p in enumerate(list(params)):
            param_name = str(p.get("param_name") or "").strip()
            type_id = p.get("type_id")
            if param_name == "" or not isinstance(type_id, int):
                raise ValueError("signal param requires param_name/type_id")

            send_port = int(next_port_index)
            listen_port = int(next_port_index + 1)
            server_port = int(next_port_index + 2)
            next_port_index += 3

            send_param_items.append(
                _build_param_item_message_from_param_spec(
                    param_spec=p,
                    port_index_int=send_port,
                    param_ordinal_int=int(param_ordinal),
                    for_server_node=False,
                )
            )
            server_param_items.append(
                _build_param_item_message_from_param_spec(
                    param_spec=p,
                    port_index_int=server_port,
                    param_ordinal_int=int(param_ordinal),
                    for_server_node=True,
                )
            )
            listen_param_ports.append(
                {
                    **dict(p),
                    "param_name": str(param_name),
                    "type_id": int(type_id),
                    "port_index": int(listen_port),
                }
            )

        # build units by cloning templates
        send_unit = copy.deepcopy(dict(tpl_send_unit))
        listen_unit = copy.deepcopy(dict(tpl_listen_unit))
        server_unit = copy.deepcopy(dict(tpl_server_unit))

        # patch graph unit ids + related ids
        _set_graph_unit_id_inplace(send_unit, node_def_id_int=send_node_def_id)
        _set_graph_unit_id_inplace(listen_unit, node_def_id_int=listen_node_def_id)
        _set_graph_unit_id_inplace(server_unit, node_def_id_int=server_node_def_id)

        _set_graph_unit_related_ids_inplace(send_unit, related_node_def_ids=[listen_node_def_id, server_node_def_id])
        _set_graph_unit_related_ids_inplace(listen_unit, related_node_def_ids=[send_node_def_id, server_node_def_id])
        _set_graph_unit_related_ids_inplace(server_unit, related_node_def_ids=[send_node_def_id, listen_node_def_id])

        # patch node defs (定位到 unit 内部对象并原地改）
        send_node_def = _find_node_def_object_in_graph_unit(send_unit, expected_node_def_name="发送信号")
        listen_node_def = _find_node_def_object_in_graph_unit(listen_unit, expected_node_def_name="监听信号")
        server_node_def = _find_node_def_object_in_graph_unit(server_unit, expected_node_def_name="向服务器节点图发送信号")

        send_node_def = _reset_send_node_def_for_new_signal(
            node_def=send_node_def,
            signal_index_int=signal_index_int,
            node_def_id_int=send_node_def_id,
            signal_name=signal_name,
            listen_meta_dict=listen_meta,
            server_meta_dict=server_meta,
            flow_in_port_index=send_flow_in,
            flow_out_port_index=send_flow_out,
            signal_name_port_index=send_signal_name_port,
            send_param_items=send_param_items,
        )
        listen_node_def = _reset_listen_node_def_for_new_signal(
            node_def=listen_node_def,
            signal_index_int=signal_index_int,
            node_def_id_int=listen_node_def_id,
            signal_name=signal_name,
            send_meta_dict=send_meta,
            server_meta_dict=server_meta,
            flow_port_index=listen_flow,
            signal_name_port_index=listen_signal_name_port,
            fixed_output_port_indices=(listen_event_source_entity, listen_event_source_guid, listen_signal_source_entity),
            params=listen_param_ports,
        )
        server_node_def = _reset_send_to_server_node_def_for_new_signal(
            node_def=server_node_def,
            signal_index_int=signal_index_int,
            node_def_id_int=server_node_def_id,
            signal_name=signal_name,
            listen_meta_dict=listen_meta,
            send_meta_dict=send_meta,
            flow_in_port_index=server_flow_in,
            flow_out_port_index=server_flow_out,
            extra_port_index=server_extra_port,
            signal_name_port_index=server_signal_name_port,
            server_param_items=server_param_items,
        )

        # 将 patched node_def 写回 unit：用“就地递归替换”的方式把找到的对象替换回原树
        def _replace_node_def_inplace(unit: Dict[str, Any], *, expected: str, new_obj: Dict[str, Any]) -> None:
            expected_name = str(expected).strip()
            replaced = {"done": False}

            def walk(value: Any) -> Any:
                if isinstance(value, dict):
                    v200 = value.get("200")
                    if isinstance(v200, str) and v200.strip() == expected_name:
                        if isinstance(value.get("4"), dict) and isinstance(value.get("107"), dict):
                            replaced["done"] = True
                            return dict(new_obj)
                    for k, child in list(value.items()):
                        value[k] = walk(child)
                    return value
                if isinstance(value, list):
                    for i, child in enumerate(list(value)):
                        value[i] = walk(child)
                    return value
                return value

            walk(unit)
            if not replaced["done"]:
                raise ValueError(f"未能替换 node_def：{expected_name!r}")

        _replace_node_def_inplace(send_unit, expected="发送信号", new_obj=send_node_def)
        _replace_node_def_inplace(listen_unit, expected="监听信号", new_obj=listen_node_def)
        _replace_node_def_inplace(server_unit, expected="向服务器节点图发送信号", new_obj=server_node_def)

        send_units.append(send_unit)
        accessory_units.extend([listen_unit, server_unit])

        exported_signal_ids.append(str(record.signal_id_str))
        exported_signal_names.append(str(signal_name))

    file_name = str(plan.output_gia_file_name_in_out).strip()
    if file_name == "":
        file_name = "基础信号.gia"
    stem = sanitize_file_stem(Path(file_name).stem)
    output_path = resolve_output_file_path_in_out_dir(Path(f"{stem}.gia"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 与结构体导出一致：单条时用 message 形态，多条时用 repeated
    root_message: Dict[str, Any] = {
        "1": send_units[0] if len(send_units) == 1 else list(send_units),
        "2": list(accessory_units),
        "3": f"0-0-0-\\\\{stem}.gia",
        "5": str(plan.game_version or "6.3.0"),
    }
    out_bytes = wrap_gia_container(encode_message(root_message))
    output_path.write_bytes(out_bytes)

    copied_to_user_dir = ""
    copied_file = ""
    if plan.output_user_dir is not None:
        user_dir = Path(plan.output_user_dir).resolve()
        if not user_dir.is_absolute():
            raise ValueError(f"output_user_dir 必须是绝对路径：{str(user_dir)}")
        user_dir.mkdir(parents=True, exist_ok=True)
        copied_path = (user_dir / output_path.name).resolve()
        shutil.copy2(str(output_path), str(copied_path))
        copied_to_user_dir = str(user_dir)
        copied_file = str(copied_path)

    return {
        "output_gia_file": str(output_path),
        "signals_total": int(len(send_units)),
        "signal_ids": list(exported_signal_ids),
        "signal_names": list(exported_signal_names),
        "accessories_total": int(len(accessory_units)),
        "project_archive_path": str(project_archive_path) if project_archive_path is not None else "",
        "template_gia": str(template_gia),
        "copied_to_user_dir": copied_to_user_dir,
        "copied_file": copied_file,
    }

