from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


JsonDict = Dict[str, Any]


@dataclass(frozen=True, slots=True)
class DecorationItem:
    name: str
    template_id: int
    pos: Tuple[float, float, float]
    scale: Tuple[float, float, float]
    yaw_deg: Optional[float]


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _as_float3(value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field_name} 必须是长度为 3 的 list[float]，got: {value!r}")
    x, y, z = value
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
        raise ValueError(f"{field_name} 必须是 float/int，got: {value!r}")
    return float(x), float(y), float(z)


def load_decorations_report(report_json: Path) -> Tuple[Optional[str], List[DecorationItem]]:
    obj = _read_json(Path(report_json).resolve())
    if not isinstance(obj, dict):
        raise ValueError("decorations report 必须是 JSON object")

    parent_name: Optional[str] = None
    parent_struct = obj.get("parent_struct")
    if isinstance(parent_struct, dict):
        pn = parent_struct.get("name")
        if isinstance(pn, str) and pn.strip() != "":
            parent_name = pn.strip()

    items_raw = obj.get("decorations")
    if not isinstance(items_raw, list):
        raise ValueError("decorations report 缺少 decorations(list)")

    items: List[DecorationItem] = []
    for idx, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"decorations[{idx}] 必须是 object，got: {raw!r}")

        name = str(raw.get("name") or "").strip()
        if name == "":
            raise ValueError(f"decorations[{idx}].name 不能为空")

        template_id = raw.get("template_id")
        if not isinstance(template_id, int):
            raise ValueError(f"decorations[{idx}].template_id 必须是 int，got: {template_id!r}")

        pos = _as_float3(raw.get("pos"), field_name=f"decorations[{idx}].pos")
        scale = _as_float3(raw.get("scale"), field_name=f"decorations[{idx}].scale")

        yaw_raw = raw.get("yaw_deg")
        yaw_deg = float(yaw_raw) if isinstance(yaw_raw, (int, float)) else None

        items.append(
            DecorationItem(
                name=name,
                template_id=int(template_id),
                pos=pos,
                scale=scale,
                yaw_deg=yaw_deg,
            )
        )

    return parent_name, items


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _derive_file_path_from_base(*, base_file_path: str, output_file_name: str) -> str:
    base = str(base_file_path or "").strip()
    out_name = str(output_file_name or "").strip()
    if out_name == "":
        return base
    if base == "":
        return out_name
    marker = "\\"
    last = base.rfind(marker)
    if last < 0:
        return base + marker + out_name
    return base[: last + 1] + out_name


def _find_parent_unit_in_bundle(
    *,
    graph_units: List[JsonDict],
    select_parent_id: Optional[int],
    select_parent_name: str,
    fallback_report_parent_name: Optional[str],
) -> JsonDict:
    name_to_match = str(select_parent_name or "").strip()
    if name_to_match == "" and isinstance(fallback_report_parent_name, str):
        name_to_match = fallback_report_parent_name

    if isinstance(select_parent_id, int):
        for unit in graph_units:
            id_msg = unit.get("1")
            if isinstance(id_msg, dict) and isinstance(id_msg.get("4"), int) and int(id_msg["4"]) == int(select_parent_id):
                return unit
        raise ValueError(f"未在资产包 Root.graph(field_1) 中找到 parent_id={int(select_parent_id)}")

    if name_to_match != "":
        for unit in graph_units:
            if isinstance(unit.get("3"), str) and str(unit["3"]).strip() == name_to_match:
                return unit
        raise ValueError(f"未在资产包 Root.graph(field_1) 中找到 parent_name={name_to_match!r}")

    # fallback: pick the first unit that has relatedIds list
    for unit in graph_units:
        if isinstance(unit.get("2"), list) and unit["2"]:
            return unit
    raise ValueError("无法自动选择 parent GraphUnit：请提供 --select-parent-name 或 --select-parent-id")


def _patch_related_id_message(related_id_template: JsonDict, *, unit_id: int) -> JsonDict:
    msg = copy.deepcopy(related_id_template)
    if not isinstance(msg, dict) or "4" not in msg or not isinstance(msg["4"], int):
        raise ValueError("relatedId template 缺少 field 4(id)")
    msg["4"] = int(unit_id)
    return msg


def _pick_accessory_wrapper_key(unit: JsonDict) -> str:
    # accessory unit keys: 1(id), 3(name), 5(which), plus one wrapper key (often 21)
    excluded = {"1", "2", "3", "5"}
    keys = [str(k) for k in unit.keys() if str(k) not in excluded]
    if not keys:
        raise ValueError(f"accessory unit 未找到 wrapper key: keys={sorted(unit.keys())}")
    keys.sort(key=lambda x: int(x) if x.isdigit() else 10**9)
    return keys[0]


def _patch_accessory_unit(
    *,
    unit_template: JsonDict,
    unit_id: int,
    unit_name: str,
    template_id: int,
    parent_struct_id: int,
    pos: Tuple[float, float, float],
    scale: Tuple[float, float, float],
    yaw_deg: Optional[float],
) -> JsonDict:
    unit = copy.deepcopy(unit_template)

    # GraphUnit.id.id = field 1 -> Id(field 4)
    id_msg = unit.get("1")
    if not isinstance(id_msg, dict) or "4" not in id_msg or not isinstance(id_msg["4"], int):
        raise ValueError("accessory unit 缺少 field 1.id.field_4")
    id_msg["4"] = int(unit_id)

    # GraphUnit.name
    unit["3"] = str(unit_name)

    # wrapper
    wrapper_key = _pick_accessory_wrapper_key(unit)
    wrapper = unit.get(wrapper_key)
    if not isinstance(wrapper, dict) or "1" not in wrapper or not isinstance(wrapper["1"], dict):
        raise ValueError(f"accessory wrapper({wrapper_key}) 缺失或结构错误")
    payload = wrapper["1"]

    payload["1"] = int(unit_id)
    payload["2"] = int(template_id)

    # payload.4: name + parent ref
    for entry in as_list(payload.get("4")):
        if not isinstance(entry, dict):
            continue
        n11 = entry.get("11")
        if isinstance(n11, dict) and isinstance(n11.get("1"), str):
            n11["1"] = str(unit_name)
        f50 = entry.get("50")
        if isinstance(f50, dict) and isinstance(f50.get("502"), int):
            f50["502"] = int(parent_struct_id)

    # payload.5: transform
    transform_entry = None
    for entry in as_list(payload.get("5")):
        if isinstance(entry, dict) and isinstance(entry.get("11"), dict):
            transform_entry = entry
            break
    if transform_entry is None:
        raise ValueError("accessory payload 缺少 Transform（field 5 中未找到 field 11）")
    transform = transform_entry["11"]

    # position
    pos_msg = transform.get("1")
    if not isinstance(pos_msg, dict):
        pos_msg = {}
        transform["1"] = pos_msg
    pos_msg["1"], pos_msg["2"], pos_msg["3"] = float(pos[0]), float(pos[1]), float(pos[2])

    # yaw
    if yaw_deg is None:
        transform["2"] = {}
    else:
        yaw_msg = transform.get("2")
        if not isinstance(yaw_msg, dict):
            yaw_msg = {}
            transform["2"] = yaw_msg
        yaw_msg["2"] = float(yaw_deg)

    # scale
    scale_msg = transform.get("3")
    if not isinstance(scale_msg, dict):
        scale_msg = {}
        transform["3"] = scale_msg
    scale_msg["1"], scale_msg["2"], scale_msg["3"] = float(scale[0]), float(scale[1]), float(scale[2])

    return unit


def build_asset_bundle_decorations_gia(
    *,
    base_gia_path: Path,
    decorations_report_json: Path,
    output_gia_path: Path,
    check_header: bool,
    decode_max_depth: int,
    select_parent_id: Optional[int],
    select_parent_name: str,
    parent_name_override: str,
    use_report_parent_name: bool,
    file_path_override: str,
) -> Dict[str, Any]:
    base_gia_path = Path(base_gia_path).resolve()
    if check_header:
        validate_gia_container_file(base_gia_path)

    proto_bytes = unwrap_gia_container(base_gia_path, check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(decode_max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            "protobuf 解析未消费完整字节流："
            f"consumed={consumed} total={len(proto_bytes)} file={str(base_gia_path)!r}"
        )
    root_message = decoded_field_map_to_numeric_message(root_fields)
    if not isinstance(root_message, dict):
        raise ValueError("decoded root_message 必须是 dict")

    # Asset bundle shape: Root.graph(field 1) is a list
    graph_units_raw = root_message.get("1")
    if not isinstance(graph_units_raw, list):
        raise ValueError("base_gia 不是资产包结构：Root.field_1 不是 list")
    graph_units: List[JsonDict] = []
    for element in graph_units_raw:
        if isinstance(element, dict):
            graph_units.append(element)
    if not graph_units:
        raise ValueError("base_gia: Root.field_1 为空")

    base_accessories = root_message.get("2")
    if not isinstance(base_accessories, list) or not base_accessories:
        raise ValueError("base_gia: Root.accessories(field 2) 为空，无法提取装饰物模板")
    unit_template = base_accessories[0]
    if not isinstance(unit_template, dict):
        raise ValueError("base_gia: accessories[0] 必须是 dict")

    report_parent_name, decorations = load_decorations_report(Path(decorations_report_json))

    parent_unit = _find_parent_unit_in_bundle(
        graph_units=graph_units,
        select_parent_id=int(select_parent_id) if isinstance(select_parent_id, int) else None,
        select_parent_name=str(select_parent_name or ""),
        fallback_report_parent_name=report_parent_name if use_report_parent_name else None,
    )

    parent_id_msg = parent_unit.get("1")
    if not isinstance(parent_id_msg, dict) or "4" not in parent_id_msg or not isinstance(parent_id_msg["4"], int):
        raise ValueError("parent GraphUnit.id.field_4 缺失或不是 int")
    parent_struct_id = int(parent_id_msg["4"])

    related_ids = parent_unit.get("2")
    if not isinstance(related_ids, list) or not related_ids:
        raise ValueError("parent.relatedIds(field 2) 为空，无法提取 relatedId 模板")
    related_template = related_ids[0]
    if not isinstance(related_template, dict) or "4" not in related_template or not isinstance(related_template["4"], int):
        raise ValueError("relatedId 模板缺少 field 4")
    unit_id_start = int(related_template["4"])

    new_accessories: List[JsonDict] = []
    new_related_ids: List[JsonDict] = []
    for i, dec in enumerate(decorations):
        unit_id = int(unit_id_start + i)
        new_accessories.append(
            _patch_accessory_unit(
                unit_template=unit_template,
                unit_id=unit_id,
                unit_name=dec.name,
                template_id=int(dec.template_id),
                parent_struct_id=int(parent_struct_id),
                pos=dec.pos,
                scale=dec.scale,
                yaw_deg=dec.yaw_deg,
            )
        )
        new_related_ids.append(_patch_related_id_message(related_template, unit_id=unit_id))

    root_message["2"] = new_accessories
    parent_unit["2"] = new_related_ids

    # 注意：父 GraphUnit 的名字在 payload 内部可能存在多处冗余字段（例如 field_12 的元信息）。
    # 为避免出现“外层 name 已变，但内部元信息仍是旧值”导致真源导入失败，
    # 这里默认不改名；只有显式传入 --parent-name 才覆盖 unit['3']。
    parent_name_text = str(parent_name_override or "").strip()
    if parent_name_text != "":
        parent_unit["3"] = parent_name_text

    fp_override = str(file_path_override or "").strip()
    if fp_override != "":
        root_message["3"] = fp_override
    else:
        base_fp = root_message.get("3")
        if isinstance(base_fp, str):
            root_message["3"] = _derive_file_path_from_base(
                base_file_path=base_fp,
                output_file_name=Path(str(output_gia_path)).name,
            )

    out_bytes = wrap_gia_container(encode_message(root_message))
    output_gia_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "base_gia_file": str(base_gia_path),
        "output_gia_file": str(output_gia_path),
        "decorations_count": len(decorations),
        "parent_struct_id": int(parent_struct_id),
        "parent_name": str(parent_unit.get("3") or ""),
        "file_path": str(root_message.get("3") or ""),
    }


