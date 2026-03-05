from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir, resolve_output_file_path_in_out_dir


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


def _to_list_of_dicts(value: Any) -> List[JsonDict]:
    out: List[JsonDict] = []
    if isinstance(value, list):
        for element in value:
            if isinstance(element, dict):
                out.append(element)
        return out
    if isinstance(value, dict):
        return [value]
    return []


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


def _decode_gia_root_message(base_gia_path: Path, *, check_header: bool, decode_max_depth: int) -> JsonDict:
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
    return root_message


def _pick_accessory_wrapper_key(unit: JsonDict) -> str:
    excluded = {"1", "2", "3", "5"}
    keys = [str(k) for k in unit.keys() if str(k) not in excluded]
    if not keys:
        raise ValueError(f"accessory unit 未找到 wrapper key: keys={sorted(unit.keys())}")
    keys.sort(key=lambda x: int(x) if x.isdigit() else 10**9)
    return keys[0]


def _extract_accessory_template_id(unit: JsonDict) -> Optional[int]:
    wrapper_key = _pick_accessory_wrapper_key(unit)
    wrapper = unit.get(wrapper_key)
    if not isinstance(wrapper, dict):
        return None
    payload = wrapper.get("1")
    if not isinstance(payload, dict):
        return None
    value = payload.get("2")
    if isinstance(value, int):
        return int(value)
    return None


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

    id_msg = unit.get("1")
    if not isinstance(id_msg, dict) or "4" not in id_msg or not isinstance(id_msg["4"], int):
        raise ValueError("accessory unit 缺少 field 1.id.field_4")
    id_msg["4"] = int(unit_id)

    unit["3"] = str(unit_name)

    wrapper_key = _pick_accessory_wrapper_key(unit)
    wrapper = unit.get(wrapper_key)
    if not isinstance(wrapper, dict) or "1" not in wrapper or not isinstance(wrapper["1"], dict):
        raise ValueError(f"accessory wrapper({wrapper_key}) 缺失或结构错误")
    payload = wrapper["1"]

    payload["1"] = int(unit_id)
    payload["2"] = int(template_id)

    for entry in as_list(payload.get("4")):
        if not isinstance(entry, dict):
            continue
        n11 = entry.get("11")
        if isinstance(n11, dict) and isinstance(n11.get("1"), str):
            n11["1"] = str(unit_name)
        f50 = entry.get("50")
        if isinstance(f50, dict) and isinstance(f50.get("502"), int):
            f50["502"] = int(parent_struct_id)

    transform_entry = None
    for entry in as_list(payload.get("5")):
        if isinstance(entry, dict) and isinstance(entry.get("11"), dict):
            transform_entry = entry
            break
    if transform_entry is None:
        raise ValueError("accessory payload 缺少 Transform（field 5 中未找到 field 11）")
    transform = transform_entry["11"]

    pos_msg = transform.get("1")
    if not isinstance(pos_msg, dict):
        pos_msg = {}
        transform["1"] = pos_msg
    pos_msg["1"], pos_msg["2"], pos_msg["3"] = float(pos[0]), float(pos[1]), float(pos[2])

    if yaw_deg is None:
        transform["2"] = {}
    else:
        yaw_msg = transform.get("2")
        if not isinstance(yaw_msg, dict):
            yaw_msg = {}
            transform["2"] = yaw_msg
        yaw_msg["2"] = float(yaw_deg)

    scale_msg = transform.get("3")
    if not isinstance(scale_msg, dict):
        scale_msg = {}
        transform["3"] = scale_msg
    scale_msg["1"], scale_msg["2"], scale_msg["3"] = float(scale[0]), float(scale[1]), float(scale[2])

    return unit


def _patch_related_id_template(related_template: JsonDict, *, unit_id: int) -> JsonDict:
    msg = copy.deepcopy(related_template)
    if not isinstance(msg, dict) or "4" not in msg or not isinstance(msg["4"], int):
        raise ValueError("relatedId template 缺少 field 4(id)")
    msg["4"] = int(unit_id)
    return msg


def _select_parent_unit_for_asset_bundle(
    *, graph_units: List[JsonDict], select_parent_name: str, select_parent_id: Optional[int]
) -> JsonDict:
    if isinstance(select_parent_id, int):
        for unit in graph_units:
            id_msg = unit.get("1")
            if isinstance(id_msg, dict) and isinstance(id_msg.get("4"), int) and int(id_msg["4"]) == int(select_parent_id):
                return unit
        raise ValueError(f"未找到 parent_id={int(select_parent_id)}")

    name = str(select_parent_name or "").strip()
    if name == "":
        raise ValueError("资产包模式必须提供 --select-parent-name 或 --select-parent-id")
    for unit in graph_units:
        if isinstance(unit.get("3"), str) and str(unit["3"]).strip() == name:
            return unit
    raise ValueError(f"未找到 parent_name={name!r}")


def _write_root_message_as_gia(*, root_message: JsonDict, output_gia_path: Path) -> Path:
    out_bytes = wrap_gia_container(encode_message(root_message))
    output_gia_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)
    return output_gia_path


def export_gia_decorations_variants(
    *,
    entity_base_gia: Optional[Path],
    asset_bundle_base_gia: Optional[Path],
    decorations_report_json: Path,
    output_dir: Path,
    output_prefix: str,
    check_header: bool,
    decode_max_depth: int,
    select_parent_name: str,
    select_parent_id: Optional[int],
    limit_count: int,
) -> Dict[str, Any]:
    """
    导出一组变体 `.gia`，用于通过“真源能否显示/能否打开”来二分定位导入约束。
    产物都会落盘到 ugc_file_tools/out/<output_dir>/ 下，并生成 manifest.json。
    """
    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gia_variants")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_parent_name, decorations_all = load_decorations_report(Path(decorations_report_json))
    decorations = decorations_all[: int(limit_count)] if int(limit_count) > 0 else decorations_all

    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "decorations_report": str(Path(decorations_report_json).resolve()),
        "decorations_count": len(decorations),
        "variants": [],
    }

    def _add_variant(kind: str, label: str, out_path: Path, notes: str) -> None:
        manifest["variants"].append(
            {
                "kind": kind,
                "label": label,
                "output_gia": str(out_path),
                "notes": notes,
            }
        )

    # ---------- Entity variants ----------
    if entity_base_gia is not None:
        base_path = Path(entity_base_gia).resolve()
        base_root = _decode_gia_root_message(base_path, check_header=check_header, decode_max_depth=decode_max_depth)

        parent_unit = base_root.get("1")
        if not isinstance(parent_unit, dict):
            raise ValueError("entity base: Root.field_1 不是 dict（不是实体结构）")
        parent_id_msg = parent_unit.get("1")
        if not isinstance(parent_id_msg, dict) or not isinstance(parent_id_msg.get("4"), int):
            raise ValueError("entity base: parent GraphUnit 缺少 id")
        parent_struct_id = int(parent_id_msg["4"])

        base_accessories = _to_list_of_dicts(base_root.get("2"))
        if not base_accessories:
            raise ValueError("entity base: Root.field_2(accessories) 为空")
        accessory_template = base_accessories[0]
        base_template_id = _extract_accessory_template_id(accessory_template)

        related_raw = parent_unit.get("2")
        related_list = _to_list_of_dicts(related_raw)
        if not related_list:
            raise ValueError("entity base: parent.relatedIds(field 2) 为空")
        related_template = related_list[0]
        if not isinstance(related_template.get("4"), int):
            raise ValueError("entity base: relatedId 模板缺少 field 4")
        unit_id_start = int(related_template["4"])

        # E0: only filePath renamed (no structural change)
        e0 = copy.deepcopy(base_root)
        if isinstance(e0.get("3"), str):
            e0["3"] = _derive_file_path_from_base(
                base_file_path=str(e0["3"]),
                output_file_name=f"{output_prefix}__entity_only_filePath.gia",
            )
        out0 = _write_root_message_as_gia(root_message=e0, output_gia_path=output_dir / f"{output_prefix}__entity_only_filePath.gia")
        _add_variant("entity", "E0_only_filePath", out0, "仅替换 Root.filePath 的文件名，其他保持 base 不变。")

        # E1: accessories=1 (use base template id), keep relatedIds untouched
        e1 = copy.deepcopy(base_root)
        unit_id_1 = unit_id_start
        tid = int(base_template_id) if isinstance(base_template_id, int) else int(decorations[0].template_id)
        e1["2"] = _patch_accessory_unit(
            unit_template=accessory_template,
            unit_id=unit_id_1,
            unit_name=decorations[0].name,
            template_id=tid,
            parent_struct_id=parent_struct_id,
            pos=decorations[0].pos,
            scale=decorations[0].scale,
            yaw_deg=decorations[0].yaw_deg,
        )
        out1 = _write_root_message_as_gia(
            root_message=e1, output_gia_path=output_dir / f"{output_prefix}__entity_acc1_keep_related_use_base_tid.gia"
        )
        _add_variant(
            "entity",
            "E1_acc1_keep_related_use_base_tid",
            out1,
            "只替换 accessories(1条)，relatedIds 保持 base 原样；template_id 强制沿用 base 的 accessory template_id。",
        )

        # E2: accessories=1 (use report template id), update relatedIds=1 (dict)
        e2 = copy.deepcopy(base_root)
        e2["2"] = _patch_accessory_unit(
            unit_template=accessory_template,
            unit_id=unit_id_1,
            unit_name=decorations[0].name,
            template_id=int(decorations[0].template_id),
            parent_struct_id=parent_struct_id,
            pos=decorations[0].pos,
            scale=decorations[0].scale,
            yaw_deg=decorations[0].yaw_deg,
        )
        parent2 = e2.get("1")
        if not isinstance(parent2, dict):
            raise ValueError("entity base: Root.field_1 结构错误")
        parent2["2"] = _patch_related_id_template(related_template, unit_id=unit_id_1)
        out2 = _write_root_message_as_gia(
            root_message=e2, output_gia_path=output_dir / f"{output_prefix}__entity_acc1_update_related_use_report_tid.gia"
        )
        _add_variant(
            "entity",
            "E2_acc1_update_related_use_report_tid",
            out2,
            "accessories=1 + relatedIds=1（单条 message）；template_id 使用 report。",
        )

        # E3: accessories=N (use report), update relatedIds=N (list)
        e3 = copy.deepcopy(base_root)
        new_acc: List[JsonDict] = []
        new_rel: List[JsonDict] = []
        for i, dec in enumerate(decorations):
            uid = unit_id_start + i
            new_acc.append(
                _patch_accessory_unit(
                    unit_template=accessory_template,
                    unit_id=uid,
                    unit_name=dec.name,
                    template_id=int(dec.template_id),
                    parent_struct_id=parent_struct_id,
                    pos=dec.pos,
                    scale=dec.scale,
                    yaw_deg=dec.yaw_deg,
                )
            )
            new_rel.append(_patch_related_id_template(related_template, unit_id=uid))
        e3["2"] = new_acc
        parent3 = e3.get("1")
        if not isinstance(parent3, dict):
            raise ValueError("entity base: Root.field_1 结构错误")
        parent3["2"] = new_rel
        out3 = _write_root_message_as_gia(
            root_message=e3, output_gia_path=output_dir / f"{output_prefix}__entity_accN_update_related_list.gia"
        )
        _add_variant("entity", "E3_accN_update_related_list", out3, "accessories=N(list) + relatedIds=N(list)。")

    # ---------- Asset bundle variants ----------
    if asset_bundle_base_gia is not None:
        base_path = Path(asset_bundle_base_gia).resolve()
        base_root = _decode_gia_root_message(base_path, check_header=check_header, decode_max_depth=decode_max_depth)

        graph_units = _to_list_of_dicts(base_root.get("1"))
        if not graph_units:
            raise ValueError("asset bundle base: Root.field_1(graph units) 为空或不是 list")
        parent_unit = _select_parent_unit_for_asset_bundle(
            graph_units=graph_units,
            select_parent_name=str(select_parent_name or ""),
            select_parent_id=int(select_parent_id) if isinstance(select_parent_id, int) else None,
        )
        parent_id_msg = parent_unit.get("1")
        if not isinstance(parent_id_msg, dict) or not isinstance(parent_id_msg.get("4"), int):
            raise ValueError("asset bundle base: parent GraphUnit 缺少 id")
        parent_struct_id = int(parent_id_msg["4"])

        base_accessories = _to_list_of_dicts(base_root.get("2"))
        if not base_accessories:
            raise ValueError("asset bundle base: Root.field_2(accessories) 为空")
        accessory_template = base_accessories[0]
        base_template_id = _extract_accessory_template_id(accessory_template)

        related_list = _to_list_of_dicts(parent_unit.get("2"))
        if not related_list:
            raise ValueError("asset bundle base: parent.relatedIds(field 2) 为空")
        related_template = related_list[0]
        if not isinstance(related_template.get("4"), int):
            raise ValueError("asset bundle base: relatedId 模板缺少 field 4")
        unit_id_start = int(related_template["4"])

        # B0: only filePath renamed
        b0 = copy.deepcopy(base_root)
        if isinstance(b0.get("3"), str):
            b0["3"] = _derive_file_path_from_base(
                base_file_path=str(b0["3"]),
                output_file_name=f"{output_prefix}__asset_only_filePath.gia",
            )
        outb0 = _write_root_message_as_gia(root_message=b0, output_gia_path=output_dir / f"{output_prefix}__asset_only_filePath.gia")
        _add_variant("asset_bundle", "B0_only_filePath", outb0, "仅替换 Root.filePath 的文件名，其他保持 base 不变。")

        # B1: accessories=1 (use base template id), keep relatedIds untouched
        b1 = copy.deepcopy(base_root)
        uid1 = unit_id_start
        tid = int(base_template_id) if isinstance(base_template_id, int) else int(decorations[0].template_id)
        b1["2"] = _patch_accessory_unit(
            unit_template=accessory_template,
            unit_id=uid1,
            unit_name=decorations[0].name,
            template_id=tid,
            parent_struct_id=parent_struct_id,
            pos=decorations[0].pos,
            scale=decorations[0].scale,
            yaw_deg=decorations[0].yaw_deg,
        )
        outb1 = _write_root_message_as_gia(
            root_message=b1, output_gia_path=output_dir / f"{output_prefix}__asset_acc1_keep_related_use_base_tid.gia"
        )
        _add_variant(
            "asset_bundle",
            "B1_acc1_keep_related_use_base_tid",
            outb1,
            "只替换 accessories(1条)，relatedIds 保持 base 原样；template_id 强制沿用 base。",
        )

        # B2: accessories=1 (use report template id), update relatedIds=1 (list with 1 item)
        b2 = copy.deepcopy(base_root)
        b2["2"] = _patch_accessory_unit(
            unit_template=accessory_template,
            unit_id=uid1,
            unit_name=decorations[0].name,
            template_id=int(decorations[0].template_id),
            parent_struct_id=parent_struct_id,
            pos=decorations[0].pos,
            scale=decorations[0].scale,
            yaw_deg=decorations[0].yaw_deg,
        )
        parent2 = _select_parent_unit_for_asset_bundle(
            graph_units=_to_list_of_dicts(b2.get("1")),
            select_parent_name=str(select_parent_name or ""),
            select_parent_id=select_parent_id,
        )
        parent2["2"] = [_patch_related_id_template(related_template, unit_id=uid1)]
        outb2 = _write_root_message_as_gia(
            root_message=b2, output_gia_path=output_dir / f"{output_prefix}__asset_acc1_update_related_list_use_report_tid.gia"
        )
        _add_variant(
            "asset_bundle",
            "B2_acc1_update_related_list_use_report_tid",
            outb2,
            "accessories=1 + relatedIds=[1条]；template_id 使用 report。",
        )

        # B3: accessories=N + relatedIds=N (list)
        b3 = copy.deepcopy(base_root)
        new_acc2: List[JsonDict] = []
        new_rel2: List[JsonDict] = []
        for i, dec in enumerate(decorations):
            uid = unit_id_start + i
            new_acc2.append(
                _patch_accessory_unit(
                    unit_template=accessory_template,
                    unit_id=uid,
                    unit_name=dec.name,
                    template_id=int(dec.template_id),
                    parent_struct_id=parent_struct_id,
                    pos=dec.pos,
                    scale=dec.scale,
                    yaw_deg=dec.yaw_deg,
                )
            )
            new_rel2.append(_patch_related_id_template(related_template, unit_id=uid))
        b3["2"] = new_acc2
        parent3 = _select_parent_unit_for_asset_bundle(
            graph_units=_to_list_of_dicts(b3.get("1")),
            select_parent_name=str(select_parent_name or ""),
            select_parent_id=select_parent_id,
        )
        parent3["2"] = new_rel2
        outb3 = _write_root_message_as_gia(
            root_message=b3, output_gia_path=output_dir / f"{output_prefix}__asset_accN_update_related_list.gia"
        )
        _add_variant("asset_bundle", "B3_accN_update_related_list", outb3, "accessories=N(list) + relatedIds=N(list)。")

    manifest_path = output_dir / f"{output_prefix}__manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output_dir": str(output_dir),
        "manifest": str(manifest_path),
        "variants_count": len(manifest.get("variants") or []),
    }


