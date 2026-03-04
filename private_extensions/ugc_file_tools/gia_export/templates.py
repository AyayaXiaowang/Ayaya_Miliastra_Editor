from __future__ import annotations

import copy
import json
import re
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.repo_paths import ugc_file_tools_root
from ugc_file_tools.var_type_map import (
    map_server_port_type_text_to_var_type_id_or_raise,
    map_var_type_id_to_server_port_type_text_or_raise,
)
from ugc_file_tools.custom_variables.value_message import (  # noqa: PLC2701
    build_custom_variable_type_descriptor as _build_custom_variable_type_descriptor,
    build_custom_variable_value_message as _build_custom_variable_value_message,
    build_dict_custom_variable_item as _build_dict_custom_variable_item,
)


@dataclass(frozen=True, slots=True)
class CustomVariableDef:
    name: str
    var_type_text: str
    var_type_int: int
    default_value: Any


@dataclass(frozen=True, slots=True)
class ComponentTemplateConfig:
    template_id: str
    template_name: str
    custom_variables: list[CustomVariableDef]


_EXPORT_TAG_RE = re.compile(r"^(?P<uid>\d+)-(?P<ts>\d+)-(?P<id>\d+)-\\(?P<file>.+)$")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _require_dict(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} must be dict, got {type(value).__name__}")
    return value


def _coerce_non_empty_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if text == "":
        raise ValueError(f"{field_name} 不能为空")
    return text


def load_component_template_config_from_json_file(template_json_path: Path) -> ComponentTemplateConfig:
    """
    解析 Graph_Generater 项目存档中的“元件库模板 JSON”，抽取：
    - 元件名称（name）
    - 自定义变量（default_components[].component_type == '自定义变量'）
    """
    template_json_path = Path(template_json_path).resolve()
    if not template_json_path.is_file():
        raise FileNotFoundError(str(template_json_path))
    obj = json.loads(template_json_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"template json root must be dict: {str(template_json_path)}")

    template_id = str(obj.get("template_id") or "").strip()
    template_name = str(obj.get("name") or "").strip()
    if template_name == "":
        template_name = str(template_id).strip()
    template_name = _coerce_non_empty_text(template_name, field_name="template.name")

    custom_variables: list[CustomVariableDef] = []
    seen: set[str] = set()

    default_components = obj.get("default_components") or []
    if not isinstance(default_components, list):
        raise TypeError("template.default_components must be list")

    for comp in default_components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("component_type") or "").strip() != "自定义变量":
            continue
        settings = comp.get("settings") or {}
        if not isinstance(settings, dict):
            raise TypeError("自定义变量.component.settings must be dict")
        defined = settings.get("已定义自定义变量") or []
        if not isinstance(defined, list):
            raise TypeError("自定义变量.settings.已定义自定义变量 must be list")
        for item in defined:
            if not isinstance(item, dict):
                continue
            name = str(item.get("变量名") or "").strip()
            if name == "":
                raise ValueError(f"自定义变量条目缺少变量名：{str(template_json_path)}")
            if name in seen:
                raise ValueError(f"自定义变量变量名重复：{name!r}（file={str(template_json_path)}）")
            seen.add(name)

            var_type_text = str(item.get("数据类型") or "").strip()
            var_type_text = _coerce_non_empty_text(var_type_text, field_name=f"{name}.数据类型")
            var_type_int = map_server_port_type_text_to_var_type_id_or_raise(var_type_text)
            default_value = item.get("默认值")
            custom_variables.append(
                CustomVariableDef(
                    name=name,
                    var_type_text=var_type_text,
                    var_type_int=int(var_type_int),
                    default_value=default_value,
                )
            )

    return ComponentTemplateConfig(
        template_id=str(template_id),
        template_name=template_name,
        custom_variables=custom_variables,
    )


def build_component_template_root_id_int(*, template_key: str) -> int:
    """
    为“元件模板 .gia”分配一个稳定的 template_root_id（1077936xxx / 0x4040xxxx）。

    约束与设计：
    - 真源样本的 low16 常为很小的顺序值（0x0001/0x0002...）；但在部分真源/周边工具链中，low16
      可能会被当作 int16（有符号 16 位）处理，若 low16>=0x8000 则会变成负数，导致“不可见/不识别”；
    - 因此这里将 low16 固定在 **0x4000~0x7FFF（<0x8000）**：既避开真源常见的顺序槽位，也避免负数风险；
    - 使用 crc32 保证同一 template_key 导出时 id 稳定，便于 diff/协作。
    """
    key_text = _coerce_non_empty_text(template_key, field_name="template_key")
    h = int(zlib.crc32(key_text.encode("utf-8")) & 0xFFFFFFFF)
    low16 = int(0x4000 | (h & 0x3FFF))  # 0x4000~0x7FFF
    return int(0x40400000 | low16)


def load_component_base_bundle_from_gia(
    base_gia_file: Path,
    *,
    max_depth: int = 24,
    prefer_raw_hex_for_utf8: bool = True,
) -> dict[str, Any]:
    """
    读取一个“元件模板 base .gia”，并解码为可写回的 numeric_message（数值键 dict）。

    说明：
    - 这里的 base `.gia` 由真源导出（例如“空模型元件”），本工具仅做“结构克隆 + 小范围字段补丁”；
    - `prefer_raw_hex_for_utf8=True` 用于最大程度保留未知 bytes 字段，避免 roundtrip 时被误当 utf8 改写。
    """
    base_gia_file = Path(base_gia_file).resolve()
    if not base_gia_file.is_file():
        raise FileNotFoundError(str(base_gia_file))
    proto_bytes = unwrap_gia_container(base_gia_file, check_header=True)
    field_map, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(f"base .gia protobuf 解析未消费完整字节流：consumed={consumed} total={len(proto_bytes)} file={str(base_gia_file)}")
    return decoded_field_map_to_numeric_message(field_map, prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8))


def load_builtin_component_base_bundle(*, prefer_raw_hex_for_utf8: bool = True) -> dict[str, Any]:
    """
    读取内置的“空模型元件 base bundle”（field_map JSON），并转换为 numeric_message。

    用途：
    - 让元件模板导出在 UI/CLI 中“默认无需用户手动提供 base .gia”；
    - 仍保留 `--base-gia` 覆盖能力（用于对齐不同版本/不同真源模板差异）。
    """
    base_field_map_file = (ugc_file_tools_root() / "gia_export" / "builtin_component_template_base_field_map.json").resolve()
    if not base_field_map_file.is_file():
        raise FileNotFoundError(str(base_field_map_file))
    obj = json.loads(base_field_map_file.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError("builtin base field_map json root must be dict")
    return decoded_field_map_to_numeric_message(obj, prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8))


def _extract_export_tag_text(bundle: Mapping[str, Any]) -> str:
    raw = bundle.get("3")
    if isinstance(raw, str) and raw.startswith("<binary_data>"):
        b = parse_binary_data_hex_text(raw)
        text = b.decode("utf-8")
        if text.strip() == "":
            raise ValueError("bundle[3] export_tag decoded empty")
        return text
    if isinstance(raw, str):
        text = raw.strip()
        if text == "":
            raise ValueError("bundle[3] export_tag empty")
        return text
    raise TypeError(f"bundle[3] export_tag must be str, got {type(raw).__name__}")


def _build_export_tag_from_base(*, base_export_tag: str, file_stem: str) -> str:
    """
    对齐真源常见 filePath 形态：<uid>-<timestamp>-<id>-\\<file>.gia
    - uid/id 继承 base 模板
    - timestamp 取当前时间
    - file 使用导出文件名
    """
    m = _EXPORT_TAG_RE.match(str(base_export_tag or "").strip())
    if m is None:
        raise ValueError(f"base export_tag 不符合预期：{base_export_tag!r}")
    uid = int(m.group("uid"))
    export_id_int = int(m.group("id"))
    ts = int(time.time())
    safe_stem = sanitize_file_stem(str(file_stem or "").strip() or "untitled")
    # 注意：export_tag 内部通常只有 1 个反斜杠分隔符；JSON dump 会显示为 "\\"
    return f"{uid}-{ts}-{export_id_int}-\\{safe_stem}.gia"


def build_custom_variable_item(defn: CustomVariableDef) -> dict[str, Any]:
    name = _coerce_non_empty_text(defn.name, field_name="variable.name")
    vt = int(defn.var_type_int)
    if vt == 27:
        if defn.default_value is None:
            default_map: dict[str, Any] = {}
        elif isinstance(defn.default_value, dict):
            default_map = dict(defn.default_value)
        else:
            raise TypeError(f"字典默认值必须为 dict 或 None，实际：{defn.default_value!r}")
        return _build_dict_custom_variable_item(variable_name=str(name), default_value_by_key=default_map)

    return {
        "2": name,
        "3": vt,
        "4": _build_custom_variable_value_message(var_type_int=vt, default_value=defn.default_value),
        "5": 1,
        "6": _build_custom_variable_type_descriptor(var_type_int=vt),
    }


def patch_component_bundle_with_custom_variables(
    base_bundle: Mapping[str, Any],
    *,
    template_name: str,
    custom_variables: Sequence[CustomVariableDef],
    template_root_id_int: int | None = None,
    output_file_stem: str | None = None,
) -> dict[str, Any]:
    """
    基于 base 元件模板 `.gia` 的 bundle message，补丁：
    - 资源名（bundle.1.3）
    - 内部 name record（bundle.1.11.1.6[...].11 内的 message.1）
    - 自定义变量列表容器（bundle.1.11.1.8[group_id=1].11.1）
    - Root.filePath（bundle.3）按 base 的 uid/id 重建，file 名与 output_file_stem 对齐
    """
    bundle = copy.deepcopy(dict(base_bundle))

    resource_entry = _require_dict(bundle.get("1"), path="bundle['1']")

    # 对用户可见的资源名
    name_text = _coerce_non_empty_text(template_name, field_name="template_name")
    resource_entry["3"] = name_text

    payload11 = _require_dict(resource_entry.get("11"), path="bundle['1']['11']")
    payload = _require_dict(payload11.get("1"), path="bundle['1']['11']['1']")

    # ===== 0) 补丁 template_root_id（避免复用 base 的内置 id） =====
    if template_root_id_int is not None:
        rid = int(template_root_id_int)
        id_message = _require_dict(resource_entry.get("1"), path="bundle['1']['1']")
        id_message["4"] = int(rid)
        resource_entry["1"] = id_message
        payload["1"] = int(rid)

    # ===== 1) 补丁内部 name record（带 $ 前缀） =====
    records = payload.get("6")
    record_list = [x for x in _as_list(records) if isinstance(x, dict)]
    if not record_list:
        raise ValueError("base bundle 缺少 payload['6'] name records（无法补丁元件名称）")
    # 经验：record['1']==1 且含 '11' 的 entry 是 name record
    name_record: dict[str, Any] | None = None
    for r in record_list:
        if r.get("1") == 1 and "11" in r:
            name_record = r
            break
    if name_record is None:
        raise ValueError("base bundle 未找到 record['1']==1 的 name record（payload['6']）")
    # 对齐真源样本：record.field_11 内部存放的是一个“带 tag/len 的嵌套 message”，其 field_1 文本通常为 name 本身；
    # readable dump 中偶发出现的前缀字符（例如 '$'）多为长度 varint 被误当成可见字符的副作用，并非业务前缀。
    name_record["11"] = {"1": name_text}
    payload["6"] = record_list if isinstance(records, list) else record_list  # normalize to list

    # ===== 2) 补丁自定义变量容器（group 1/1） =====
    groups_raw = payload.get("8")
    groups_list = [x for x in _as_list(groups_raw) if isinstance(x, dict)]
    if not groups_list:
        raise ValueError("base bundle 缺少 payload['8'] groups（无法写入自定义变量）")

    group_1: dict[str, Any] | None = None
    for g in groups_list:
        if g.get("1") == 1 and g.get("2") == 1:
            group_1 = g
            break
    if group_1 is None:
        group_1 = {"1": 1, "2": 1, "11": format_binary_data_hex_text(b"")}
        groups_list.insert(0, group_1)

    variable_items = [build_custom_variable_item(v) for v in list(custom_variables)]
    if variable_items:
        group_1["11"] = {"1": variable_items}
    else:
        group_1["11"] = format_binary_data_hex_text(b"")
    payload["8"] = groups_list

    # ===== 3) 补丁 Root.filePath/export_tag（bundle['3']） =====
    base_export_tag = _extract_export_tag_text(bundle)
    stem = str(output_file_stem or "").strip() or str(name_text)
    bundle["3"] = _build_export_tag_from_base(base_export_tag=base_export_tag, file_stem=stem)

    return bundle


def build_component_gia_bytes_from_base_bundle(
    base_bundle: Mapping[str, Any],
    *,
    template_name: str,
    custom_variables: Sequence[CustomVariableDef],
    template_root_id_int: int | None = None,
    output_file_stem: str | None = None,
) -> bytes:
    bundle = patch_component_bundle_with_custom_variables(
        base_bundle,
        template_name=str(template_name),
        custom_variables=custom_variables,
        template_root_id_int=template_root_id_int,
        output_file_stem=output_file_stem,
    )
    proto_bytes = encode_message(dict(bundle))
    return wrap_gia_container(proto_bytes)


def patch_bundle_with_custom_variables(
    base_bundle: Mapping[str, Any],
    *,
    template_name: str,
    custom_variables: Sequence[CustomVariableDef],
    template_root_id_int: int | None = None,
    output_file_stem: str | None = None,
) -> dict[str, Any]:
    """
    通用补丁：基于“template-like bundle（含 payload.groups field_8）”写入自定义变量。

    说明：
    - 当前已验证可用于：
      - 元件模板 `.gia`（Component Template）
      - 玩家模板 `.gia`（Player Template）主资源条目（field_1）
    - 实现复用现有元件模板补丁逻辑（字段结构一致）。
    """
    return patch_component_bundle_with_custom_variables(
        base_bundle,
        template_name=str(template_name),
        custom_variables=custom_variables,
        template_root_id_int=template_root_id_int,
        output_file_stem=output_file_stem,
    )


def _coerce_utf8_text_from_numeric_message(value: Any, *, field_name: str) -> str:
    if isinstance(value, str):
        if value.startswith("<binary_data>"):
            raw = parse_binary_data_hex_text(value)
            return raw.decode("utf-8", errors="replace").strip()
        return str(value).strip()
    return str(value if value is not None else "").strip()


def _coerce_int_from_numeric_message(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        return int(1 if value else 0)
    if isinstance(value, int):
        return int(value)
    raise TypeError(f"{field_name} must be int, got {type(value).__name__}")


def extract_custom_variable_items_from_bundle(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """
    从 bundle 中提取 group1(1/1) 的自定义变量条目列表（numeric_message 风格）。

    结构（已在元件模板与玩家模板样本中验证）：
      bundle['1']['11']['1']['8'] = groups
      groups[*]['1']==1 && groups[*]['2']==1 -> group_1
      group_1['11']['1'] = [variable_item, ...]
    """
    resource_entry = _require_dict(bundle.get("1"), path="bundle['1']")
    payload11 = _require_dict(resource_entry.get("11"), path="bundle['1']['11']")
    payload = _require_dict(payload11.get("1"), path="bundle['1']['11']['1']")

    groups_raw = payload.get("8")
    groups_list = [x for x in _as_list(groups_raw) if isinstance(x, dict)]
    if not groups_list:
        return []

    group_1: dict[str, Any] | None = None
    for g in groups_list:
        if g.get("1") == 1 and g.get("2") == 1:
            group_1 = g
            break
    if group_1 is None:
        return []

    container = group_1.get("11")
    if isinstance(container, str) and container.startswith("<binary_data>"):
        # empty bytes -> no variables
        return []
    if not isinstance(container, dict):
        raise TypeError(f"bundle['1']['11']['1']['8'][group1]['11'] must be dict or <binary_data>, got {type(container).__name__}")

    items_raw = container.get("1")
    return [x for x in _as_list(items_raw) if isinstance(x, dict)]


def _value_field_key_for_custom_variable_int(*, var_type_int: int) -> str:
    # 与写入侧口径保持一致：值字段号 = var_type_int + 10
    return str(int(var_type_int) + 10)


def _extract_default_value_from_custom_variable_value_message(
    *,
    var_type_int: int,
    value_message: Mapping[str, Any],
    variable_name: str,
) -> Any:
    vt = int(var_type_int)
    key = _value_field_key_for_custom_variable_int(var_type_int=vt)
    node = value_message.get(key)

    # Dict（value_key=37）
    if vt == 27:
        if not isinstance(node, dict):
            return {}
        keys_nodes = node.get("501") or []
        vals_nodes = node.get("502") or []
        if not isinstance(keys_nodes, list) or not isinstance(vals_nodes, list):
            raise TypeError(f"dict 默认值结构不合法：{variable_name!r}（501/502 必须为 list）")
        val_vt = node.get("504")
        val_vt_int = int(val_vt) if isinstance(val_vt, int) else 6
        out: dict[str, Any] = {}
        for k_node, v_node in zip(keys_nodes, vals_nodes):
            if not isinstance(k_node, dict) or not isinstance(v_node, dict):
                continue
            k_value_node = k_node.get("16")
            if not isinstance(k_value_node, dict):
                continue
            key_text = _coerce_utf8_text_from_numeric_message(k_value_node.get("1"), field_name=f"{variable_name}.dict_key")
            if key_text == "":
                continue
            out[key_text] = _extract_default_value_from_custom_variable_value_message(
                var_type_int=int(val_vt_int),
                value_message=v_node,
                variable_name=f"{variable_name}.{key_text}",
            )
        return out

    # Int / GUID / Entity / Enum / Faction / ComponentId
    if vt in (1, 2, 3, 14, 17, 21):
        if not isinstance(node, dict):
            return 0
        v = node.get("1")
        if v is None:
            return 0
        if isinstance(v, bool):
            return int(1 if v else 0)
        if isinstance(v, int):
            return int(v)
        raise TypeError(f"{variable_name!r} 默认值应为 int：vt={vt} got={type(v).__name__}")

    # Float
    if vt == 5:
        if not isinstance(node, dict):
            return 0.0
        v = node.get("1")
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            fv = float(v)
            if not (fv == fv):
                raise ValueError(f"{variable_name!r} 默认值为 NaN（不支持）")
            return float(fv)
        raise TypeError(f"{variable_name!r} 默认值应为 float：got={type(v).__name__}")

    # String
    if vt == 6:
        if not isinstance(node, dict):
            return ""
        return _coerce_utf8_text_from_numeric_message(node.get("1"), field_name=f"{variable_name}.string_default")

    # Bool
    if vt == 4:
        if not isinstance(node, dict):
            return False
        v = node.get("1")
        if v is None:
            return False
        if isinstance(v, bool):
            return bool(v)
        if isinstance(v, int):
            return bool(int(v) != 0)
        raise TypeError(f"{variable_name!r} 默认值应为 bool/int：got={type(v).__name__}")

    # ConfigId（value_key=30）
    if vt == 20:
        if not isinstance(node, dict):
            return 0
        inner = node.get("1")
        if isinstance(inner, str) and inner.startswith("<binary_data>"):
            return 0
        if not isinstance(inner, dict):
            return 0
        raw_v = inner.get("2")
        return int(raw_v) if isinstance(raw_v, int) else 0

    # StringList
    if vt == 11:
        if not isinstance(node, dict):
            return []
        raw = node.get("1")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"{variable_name!r} 默认值应为 list[str]：got={type(raw).__name__}")
        return [str(x) for x in raw]

    # IntList / GuidList / EntityList / ConfigIdList / ComponentIdList / FactionList（按 repeated varint 读取）
    if vt in (7, 8, 13, 22, 23, 24, 26):
        if not isinstance(node, dict):
            return []
        raw = node.get("1")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"{variable_name!r} 默认值应为 list[int]：got={type(raw).__name__}")
        out: list[int] = []
        for x in raw:
            if isinstance(x, bool):
                out.append(int(1 if x else 0))
            elif isinstance(x, int):
                out.append(int(x))
            elif isinstance(x, float):
                if not (x == x):
                    raise ValueError(f"{variable_name!r} 默认值列表包含 NaN（不支持）")
                out.append(int(x))
            else:
                raise TypeError(f"{variable_name!r} 默认值列表元素不支持：{x!r}")
        return out

    # FloatList
    if vt == 10:
        if not isinstance(node, dict):
            return []
        raw = node.get("1")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"{variable_name!r} 默认值应为 list[float]：got={type(raw).__name__}")
        out_f: list[float] = []
        for x in raw:
            if isinstance(x, bool):
                out_f.append(float(1.0 if x else 0.0))
            elif isinstance(x, (int, float)):
                fv = float(x)
                if not (fv == fv):
                    raise ValueError(f"{variable_name!r} 默认值列表包含 NaN（不支持）")
                out_f.append(float(fv))
            else:
                raise TypeError(f"{variable_name!r} 默认值列表元素不支持：{x!r}")
        return out_f

    # BoolList（按 repeated varint 0/1 读取）
    if vt == 9:
        if not isinstance(node, dict):
            return []
        raw = node.get("1")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"{variable_name!r} 默认值应为 list[bool]：got={type(raw).__name__}")
        out_b: list[bool] = []
        for x in raw:
            if isinstance(x, bool):
                out_b.append(bool(x))
            elif isinstance(x, int):
                out_b.append(bool(int(x) != 0))
            else:
                raise TypeError(f"{variable_name!r} 默认值列表元素不支持：{x!r}")
        return out_b

    raise ValueError(f"暂不支持从 .gia 解析该自定义变量类型：{variable_name!r} var_type_int={vt}")


def extract_custom_variable_defs_from_bundle(bundle: Mapping[str, Any]) -> list[CustomVariableDef]:
    """
    从 bundle 中解析自定义变量定义列表（name/type/default）。

    注意：该解析面向“元件模板/玩家模板”的 group1(1/1) override variables 结构，
    并非 NodeGraph 的 VarBase。
    """
    items = extract_custom_variable_items_from_bundle(bundle)
    out: list[CustomVariableDef] = []
    for item in items:
        name_text = _coerce_utf8_text_from_numeric_message(item.get("2"), field_name="variable.name")
        if name_text == "":
            continue
        vt = _coerce_int_from_numeric_message(item.get("3"), field_name=f"{name_text}.var_type_int")
        vt_text = map_var_type_id_to_server_port_type_text_or_raise(int(vt))
        value_msg = item.get("4")
        if not isinstance(value_msg, dict):
            raise TypeError(f"{name_text!r} 的 value_message(item['4']) 必须为 dict，got {type(value_msg).__name__}")
        default_value = _extract_default_value_from_custom_variable_value_message(
            var_type_int=int(vt),
            value_message=value_msg,
            variable_name=name_text,
        )
        out.append(
            CustomVariableDef(
                name=str(name_text),
                var_type_text=str(vt_text),
                var_type_int=int(vt),
                default_value=default_value,
            )
        )
    return out

