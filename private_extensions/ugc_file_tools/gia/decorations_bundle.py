from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
    # 部分工具链/PowerShell 产物可能携带 UTF-8 BOM，这里统一兼容。
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _as_float3(value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field_name} 必须是长度为 3 的 list[float]，got: {value!r}")
    x, y, z = value
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
        raise ValueError(f"{field_name} 必须是 float/int，got: {value!r}")
    return float(x), float(y), float(z)


def load_decorations_report(report_json: Path) -> Tuple[Optional[str], List[DecorationItem]]:
    """
    读取 decorations_*.report.json（由外部抽取脚本生成）：
    - parent_struct.name（可选）
    - decorations[*].name/template_id/pos/yaw_deg/scale
    """
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


def _find_first_dict_in_list(value: Any) -> Optional[JsonDict]:
    if not isinstance(value, list):
        return None
    for element in value:
        if isinstance(element, dict):
            return element
    return None


def _pick_first_key_excluding(d: JsonDict, excluded: Iterable[str]) -> str:
    excluded_set = set(excluded)
    candidates = [k for k in d.keys() if str(k) not in excluded_set]
    if not candidates:
        raise ValueError(f"未找到 wrapper key：available={sorted(d.keys())} excluded={sorted(excluded_set)}")
    candidates.sort(key=lambda x: int(x) if str(x).isdigit() else 10**9)
    return str(candidates[0])


def _patch_related_id_message(related_id_template: JsonDict, *, unit_id: int) -> JsonDict:
    msg = copy.deepcopy(related_id_template)
    if not isinstance(msg, dict):
        raise ValueError("relatedId template 必须是 dict")
    if "4" not in msg:
        raise ValueError(f"relatedId template 缺少 field 4(id)：{msg!r}")
    msg["4"] = int(unit_id)
    return msg


def _iter_list_field_messages(container: JsonDict, field_number: str) -> Iterable[JsonDict]:
    value = container.get(field_number)
    if not isinstance(value, list):
        return
    for element in value:
        if isinstance(element, dict):
            yield element


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
    if not isinstance(unit, dict):
        raise ValueError("accessory unit template must be dict")

    # 1) GraphUnit.id.id = field 1 -> Id(field 4)
    id_msg = unit.get("1")
    if not isinstance(id_msg, dict):
        raise ValueError("accessory unit 缺少 field 1(id message)")
    id_msg["4"] = int(unit_id)

    # 2) GraphUnit.name
    unit["3"] = str(unit_name)

    # 3) 找到 payload wrapper（样本中为 21），并更新其内部 payload
    wrapper_key = _pick_first_key_excluding(unit, excluded=("1", "2", "3", "5"))
    wrapper = unit.get(wrapper_key)
    if not isinstance(wrapper, dict):
        raise ValueError(f"accessory wrapper({wrapper_key}) 必须是 dict")
    payload = wrapper.get("1")
    if not isinstance(payload, dict):
        raise ValueError(f"accessory wrapper({wrapper_key}).1 必须是 dict")

    # payload:
    # - 1: unit_id
    # - 2: template_id
    payload["1"] = int(unit_id)
    payload["2"] = int(template_id)

    # payload.4: name + parent ref
    for entry in as_list(payload.get("4")):
        if not isinstance(entry, dict):
            continue
        # name: entry.11.1
        n11 = entry.get("11")
        if isinstance(n11, dict) and "1" in n11 and isinstance(n11["1"], str):
            n11["1"] = str(unit_name)
        # parent_struct_id: entry.50.502
        f50 = entry.get("50")
        if isinstance(f50, dict) and isinstance(f50.get("502"), int):
            f50["502"] = int(parent_struct_id)

    # payload.5: transform
    # 取第一个包含 11 的条目作为 Transform 载体（样本一致）
    transform_entry = None
    for entry in as_list(payload.get("5")):
        if isinstance(entry, dict) and isinstance(entry.get("11"), dict):
            transform_entry = entry
            break
    if transform_entry is None:
        raise ValueError("accessory payload 缺少 Transform（field 5 中未找到包含 field 11 的条目）")
    transform = transform_entry.get("11")
    if not isinstance(transform, dict):
        raise ValueError("Transform 必须是 dict")

    # position: field 1 -> message(1=x,2=y,3=z)
    pos_msg = transform.get("1")
    if not isinstance(pos_msg, dict):
        pos_msg = {}
        transform["1"] = pos_msg
    pos_msg["1"], pos_msg["2"], pos_msg["3"] = float(pos[0]), float(pos[1]), float(pos[2])

    # yaw: field 2 -> message(field 2 = yaw_deg) 或空 message（不覆盖）
    if yaw_deg is None:
        transform["2"] = {}
    else:
        yaw_msg = transform.get("2")
        if not isinstance(yaw_msg, dict):
            yaw_msg = {}
            transform["2"] = yaw_msg
        yaw_msg["2"] = float(yaw_deg)

    # scale: field 3 -> message(1=sx,2=sy,3=sz)
    scale_msg = transform.get("3")
    if not isinstance(scale_msg, dict):
        scale_msg = {}
        transform["3"] = scale_msg
    scale_msg["1"], scale_msg["2"], scale_msg["3"] = float(scale[0]), float(scale[1]), float(scale[2])

    return unit


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _derive_file_path_from_base(
    *,
    base_file_path: str,
    output_file_name: str,
) -> str:
    """
    真源 `.gia` 的 Root.filePath 常见形态：
    `<uid>-<time>-<level_id>-\\<file_name>.gia`
    这里尽量保留前缀，只替换 `\\` 之后的文件名，确保导入器能识别。
    """
    base = str(base_file_path or "").strip()
    out_name = str(output_file_name or "").strip()
    if out_name == "":
        return base
    if base == "":
        return out_name

    # normalize separators inside string (it's a payload string, not a filesystem path)
    marker = "\\"
    last = base.rfind(marker)
    if last < 0:
        # 有些样本可能没有 `\\`，保守处理：直接用原串 + `\\` + 文件名
        return base + marker + out_name
    prefix = base[: last + 1]
    return prefix + out_name


def build_decorations_bundle_gia(
    *,
    base_gia_path: Path,
    decorations_report_json: Path,
    output_gia_path: Path,
    check_header: bool,
    decode_max_depth: int,
    parent_name_override: str,
    file_path_override: str,
    game_version_override: str,
    use_report_parent_name: bool,
) -> Dict[str, Any]:
    """
    基于一个“结构模板 base .gia”（例如控模型带内容.gia）重建 Root.graph/Root.accessories：
    - 保留 base 的 parent(GraphUnit) payload 细节（模型/内容等）
    - 按 decorations_report_json 生成 N 个装饰物 unit（克隆 base 的第一个装饰物 unit 作为模板）
    - 输出为全新 .gia（不 patch 原文件；重新 encode + wrap）
    """
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

    parent_unit = root_message.get("1")
    if not isinstance(parent_unit, dict):
        raise ValueError("base_gia: Root.graph(field 1) 缺失或类型错误")

    base_accessories_raw = root_message.get("2")
    base_accessories: List[JsonDict] = []
    if isinstance(base_accessories_raw, list):
        for element in base_accessories_raw:
            if isinstance(element, dict):
                base_accessories.append(element)
    elif isinstance(base_accessories_raw, dict):
        base_accessories.append(base_accessories_raw)
    if not base_accessories:
        raise ValueError("base_gia: Root.accessories(field 2) 为空，无法提取装饰物模板")
    unit_template = base_accessories[0]
    if not isinstance(unit_template, dict):
        raise ValueError("base_gia: accessories[0] 必须是 dict")

    report_parent_name, decorations = load_decorations_report(Path(decorations_report_json))

    # parent id from base (do NOT mutate ids inside base payload)
    parent_id_msg = parent_unit.get("1")
    if not isinstance(parent_id_msg, dict) or "4" not in parent_id_msg or not isinstance(parent_id_msg["4"], int):
        raise ValueError("base_gia: parent GraphUnit.id.field_4 缺失或不是 int")
    parent_struct_id = int(parent_id_msg["4"])

    # relatedIds template
    related_raw = parent_unit.get("2")
    if isinstance(related_raw, dict):
        related_template = related_raw
    else:
        related_template = _find_first_dict_in_list(related_raw)
    if related_template is None:
        raise ValueError("base_gia: parent.relatedIds(field 2) 为空，无法提取 relatedId 模板")

    # unit_id assignment: keep report order, generate sequential ids starting from base first relatedId id
    unit_id_start: Optional[int] = None
    first_related = related_template.get("4")
    if isinstance(first_related, int):
        unit_id_start = int(first_related)
    if unit_id_start is None:
        raise ValueError("base_gia: relatedId 模板缺少 field 4(id)")

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

    # Patch root + parent unit
    root_message["2"] = new_accessories
    parent_unit["2"] = new_related_ids

    # Set parent name
    # 注意：父 GraphUnit 的名字在 payload 内部可能存在多处冗余字段（例如 field_12 的元信息）。
    # 为避免出现“外层 name 已变，但内部元信息仍是旧值”导致真源导入失败，
    # 这里默认不改名；只有显式传入 --parent-name 才覆盖 unit['3']。
    parent_name = str(parent_name_override or "").strip()
    if parent_name != "":
        parent_unit["3"] = parent_name

    # Set filePath
    file_path_text = str(file_path_override or "").strip()
    if file_path_text != "":
        root_message["3"] = file_path_text
    else:
        base_fp = root_message.get("3")
        if isinstance(base_fp, str):
            root_message["3"] = _derive_file_path_from_base(
                base_file_path=base_fp,
                output_file_name=Path(str(output_gia_path)).name,
            )

    # Set gameVersion
    game_version_text = str(game_version_override or "").strip()
    if game_version_text != "":
        root_message["5"] = game_version_text

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
        "game_version": str(root_message.get("5") or ""),
    }


