from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file
from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


JsonDict = Dict[str, Any]

_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


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


def _pick_accessory_wrapper_key(unit: JsonDict) -> str:
    # 对齐 `gia_decorations_bundle.py`：排除 GraphUnit 常见字段，选择最小的“wrapper”键
    excluded = {"1", "2", "3", "5"}
    keys = [str(k) for k in unit.keys() if str(k) not in excluded]
    if not keys:
        raise ValueError(f"accessory unit 未找到 wrapper key: keys={sorted(unit.keys())}")
    keys.sort(key=lambda x: int(x) if x.isdigit() else 10**9)
    return keys[0]


def _find_hex_colors(value: Any) -> List[str]:
    found: List[str] = []

    def walk(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            for m in _HEX_COLOR_RE.findall(v):
                found.append(m.upper())
            return
        if isinstance(v, dict):
            for vv in v.values():
                walk(vv)
            return
        if isinstance(v, list):
            for vv in v:
                walk(vv)
            return

    walk(value)
    # 稳定去重（保持出现顺序）
    dedup: List[str] = []
    seen: set[str] = set()
    for c in found:
        if c in seen:
            continue
        seen.add(c)
        dedup.append(c)
    return dedup


def _extract_transform_from_accessory_payload(payload: JsonDict) -> Tuple[Tuple[float, float, float], Optional[float], Tuple[float, float, float]]:
    # 对齐 `gia_decorations_bundle.py`：payload.5 中第一个包含 11 的 entry 视为 transform 载体
    payload_5 = payload.get("5")
    transform_entry: Optional[JsonDict] = None
    for entry in (payload_5 if isinstance(payload_5, list) else [payload_5]):
        if isinstance(entry, dict) and isinstance(entry.get("11"), dict):
            transform_entry = entry
            break
    if transform_entry is None:
        raise ValueError("accessory payload 缺少 Transform（field 5 中未找到 field 11）")
    transform = transform_entry["11"]

    pos_msg = transform.get("1") if isinstance(transform, dict) else None
    pos_x = _as_float(pos_msg.get("1")) if isinstance(pos_msg, dict) else None
    pos_y = _as_float(pos_msg.get("2")) if isinstance(pos_msg, dict) else None
    pos_z = _as_float(pos_msg.get("3")) if isinstance(pos_msg, dict) else None
    pos = (float(pos_x or 0.0), float(pos_y or 0.0), float(pos_z or 0.0))

    yaw_deg: Optional[float] = None
    yaw_msg = transform.get("2") if isinstance(transform, dict) else None
    if isinstance(yaw_msg, dict):
        yaw_deg = _as_float(yaw_msg.get("2"))

    scale_msg = transform.get("3") if isinstance(transform, dict) else None
    sx = _as_float(scale_msg.get("1")) if isinstance(scale_msg, dict) else None
    sy = _as_float(scale_msg.get("2")) if isinstance(scale_msg, dict) else None
    sz = _as_float(scale_msg.get("3")) if isinstance(scale_msg, dict) else None
    scale = (float(sx or 1.0), float(sy or 1.0), float(sz or 1.0))

    return pos, yaw_deg, scale


def _extract_vector3_from_message(msg: Any, *, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if not isinstance(msg, dict):
        return default
    x = _as_float(msg.get("1"))
    y = _as_float(msg.get("2"))
    z = _as_float(msg.get("3"))
    return (float(default[0] if x is None else x), float(default[1] if y is None else y), float(default[2] if z is None else z))


def _extract_rotation3_from_message(msg: Any) -> Dict[str, Optional[float]]:
    """
    旋转字段在不同 `.gia` 结构中可能并非严格的 (x,y,z)。
    这里不强行做语义映射，只尽量提取 1/2/3 三个 float，以便后续人工核对。
    """
    if not isinstance(msg, dict):
        return {"x": None, "y": None, "z": None}
    return {
        "x": _as_float(msg.get("1")),
        "y": _as_float(msg.get("2")),
        "z": _as_float(msg.get("3")),
    }


def _extract_entities_from_graph_units(root_message: JsonDict) -> Dict[str, Any]:
    """
    某些 `.gia`（例如“画布/控件组”类）会将多个 GraphUnit 直接放在 Root.field_1(list) 中，
    而不是使用 Root.accessories(field_2)。

    这里把每个 GraphUnit 当作一个“实体”，并尝试从其 `field_12`（组件树）中抽取 Transform：
    - unit["12"]["1"]["6"][?] 的 entry 中，通常 key==1 的 entry["11"] 即 transform message
    - transform["1"] -> position(Vector3)
    - transform["2"] -> rotation-like message（尽量提取 1/2/3）
    - transform["3"] -> scale(Vector3)
    """
    root_file_path = str(root_message.get("3") or "")
    root_game_version = str(root_message.get("5") or "")

    graph_units = _to_list_of_dicts(root_message.get("1"))
    entities: List[Dict[str, Any]] = []

    for unit in graph_units:
        unit_id_int: Optional[int] = None
        id_msg = unit.get("1")
        if isinstance(id_msg, dict) and isinstance(id_msg.get("4"), int):
            unit_id_int = int(id_msg["4"])

        name = str(unit.get("3") or "").strip()
        colors = _find_hex_colors(name) or _find_hex_colors(unit)

        template_id_int: Optional[int] = None
        # 经验：部分样本在 unit.field_12.field_1.field_2.field_1 存模板/类型 id（int）
        c12 = unit.get("12")
        if isinstance(c12, dict):
            c1 = c12.get("1")
            if isinstance(c1, dict):
                c2 = c1.get("2")
                if isinstance(c2, dict) and isinstance(c2.get("1"), int):
                    template_id_int = int(c2["1"])

        pos = (0.0, 0.0, 0.0)
        scale = (1.0, 1.0, 1.0)
        rotation = {"x": None, "y": None, "z": None}

        transform_msg: Optional[JsonDict] = None
        if isinstance(c12, dict):
            c1 = c12.get("1")
            if isinstance(c1, dict):
                entries = _to_list_of_dicts(c1.get("6"))
                # 优先挑 key==1 且包含 11 的 entry；否则挑第一个包含 11 的 entry
                for entry in entries:
                    if entry.get("1") == 1 and isinstance(entry.get("11"), dict):
                        transform_msg = entry["11"]
                        break
                if transform_msg is None:
                    for entry in entries:
                        if isinstance(entry.get("11"), dict):
                            transform_msg = entry["11"]
                            break

        if isinstance(transform_msg, dict):
            pos = _extract_vector3_from_message(transform_msg.get("1"), default=pos)
            rotation = _extract_rotation3_from_message(transform_msg.get("2"))
            scale = _extract_vector3_from_message(transform_msg.get("3"), default=scale)

        entities.append(
            {
                "unit_id_int": unit_id_int,
                "name": name,
                "template_id_int": template_id_int,
                "pos": {"x": pos[0], "y": pos[1], "z": pos[2]},
                "rotation_deg": rotation,
                "yaw_deg": rotation.get("y"),
                "scale": {"x": scale[0], "y": scale[1], "z": scale[2]},
                "colors": colors,
            }
        )

    return {
        "schema_version": 1,
        "root_file_path": root_file_path,
        "root_game_version": root_game_version,
        "parent": None,
        "entities": entities,
        "entities_count": len(entities),
        "source_shape": "root.field_1(graph_units)",
    }


def _extract_accessory_entities(root_message: JsonDict) -> Dict[str, Any]:
    """
    目标：从“实体类/装饰物挂件类”的 `.gia` 中抽取 Root.accessories（field 2）的实体列表。
    输出结构尽量稳定，便于后续脚本化处理。
    """
    root_file_path = str(root_message.get("3") or "")
    root_game_version = str(root_message.get("5") or "")

    parent_unit_raw = root_message.get("1")
    parent_units = _to_list_of_dicts(parent_unit_raw)
    parent_unit = parent_units[0] if parent_units else None

    parent_struct_id: Optional[int] = None
    parent_name: str = ""
    if isinstance(parent_unit, dict):
        parent_name = str(parent_unit.get("3") or "")
        id_msg = parent_unit.get("1")
        if isinstance(id_msg, dict) and isinstance(id_msg.get("4"), int):
            parent_struct_id = int(id_msg["4"])

    accessories = _to_list_of_dicts(root_message.get("2"))
    entities: List[Dict[str, Any]] = []
    for unit in accessories:
        unit_id: Optional[int] = None
        unit_id_msg = unit.get("1")
        if isinstance(unit_id_msg, dict) and isinstance(unit_id_msg.get("4"), int):
            unit_id = int(unit_id_msg["4"])

        name = str(unit.get("3") or "").strip()
        wrapper_key = _pick_accessory_wrapper_key(unit)
        wrapper = unit.get(wrapper_key)
        if not isinstance(wrapper, dict):
            raise ValueError(f"accessory wrapper({wrapper_key}) 必须是 dict")
        payload = wrapper.get("1")
        if not isinstance(payload, dict):
            raise ValueError(f"accessory wrapper({wrapper_key}).1 必须是 dict")

        template_id: Optional[int] = None
        if isinstance(payload.get("2"), int):
            template_id = int(payload["2"])

        pos, yaw_deg, scale = _extract_transform_from_accessory_payload(payload)
        colors = _find_hex_colors(unit)

        entities.append(
            {
                "unit_id_int": unit_id,
                "name": name,
                "template_id_int": template_id,
                "pos": {"x": pos[0], "y": pos[1], "z": pos[2]},
                "yaw_deg": yaw_deg,
                "scale": {"x": scale[0], "y": scale[1], "z": scale[2]},
                "colors": colors,
                "wrapper_key": wrapper_key,
            }
        )

    return {
        "schema_version": 1,
        "root_file_path": root_file_path,
        "root_game_version": root_game_version,
        "parent": {
            "struct_id_int": parent_struct_id,
            "name": parent_name,
        },
        "entities": entities,
        "entities_count": len(entities),
        "source_shape": "root.field_2(accessories)",
    }


def _classify_shapes(
    exported: Dict[str, Any],
    *,
    circle_colors: Iterable[str],
) -> Dict[str, Any]:
    circle_color_set = {str(c).strip().upper() for c in circle_colors if str(c).strip() != ""}

    circles: List[Dict[str, Any]] = []
    rects: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []

    for entity in list(exported.get("entities") or []):
        if not isinstance(entity, dict):
            continue
        colors = entity.get("colors") or []
        if not isinstance(colors, list):
            colors = []
        colors_norm = [str(c).strip().upper() for c in colors if str(c).strip() != ""]

        kind = "rect"
        if any(c in circle_color_set for c in colors_norm):
            kind = "circle"
        elif len(colors_norm) == 0:
            kind = "unknown"

        entity2 = {**entity, "shape_kind": kind}
        if kind == "circle":
            circles.append(entity2)
        elif kind == "rect":
            rects.append(entity2)
        else:
            unknown.append(entity2)

    return {
        **exported,
        "shape_rules": {
            "circle_colors": sorted(circle_color_set),
            "rect_rule": "除 circle_colors 外均视为矩形（若未找到任何颜色，则标记为 unknown）",
        },
        "shapes": {
            "circles": circles,
            "rectangles": rects,
            "unknown": unknown,
            "circles_count": len(circles),
            "rectangles_count": len(rects),
            "unknown_count": len(unknown),
        },
    }


def export_gia_entities(
    gia_file_path: Path,
    *,
    output_json_path: Path,
    circle_colors: Iterable[str],
    check_header: bool,
    decode_max_depth: int,
) -> Path:
    gia_file_path = Path(gia_file_path).resolve()
    if not gia_file_path.is_file():
        raise FileNotFoundError(f"input gia file not found: {str(gia_file_path)!r}")

    if check_header:
        validate_gia_container_file(gia_file_path)

    proto_bytes = unwrap_gia_container(gia_file_path, check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(decode_max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            "protobuf 解析未消费完整字节流："
            f"consumed={consumed} total={len(proto_bytes)} file={str(gia_file_path)!r}"
        )

    root_message = decoded_field_map_to_numeric_message(root_fields)
    if not isinstance(root_message, dict):
        raise ValueError("decoded root_message 必须是 dict")

    exported = _extract_accessory_entities(root_message)
    # fallback：有些 `.gia` 将 GraphUnit 列表直接放在 Root.field_1，而不是 accessories(field_2)
    if int(exported.get("entities_count") or 0) == 0:
        exported = _extract_entities_from_graph_units(root_message)
    exported = _classify_shapes(exported, circle_colors=circle_colors)
    exported["source_gia_file"] = str(gia_file_path)

    output_json_path = resolve_output_file_path_in_out_dir(Path(output_json_path))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_json_path


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "解析实体类/装饰物挂件类 .gia，抽取 Root.accessories(2) 的实体清单并导出 JSON。\n"
            "额外支持：基于颜色 hex 列表将实体归类为 circle/rect。"
        )
    )
    argument_parser.add_argument("--input-gia", dest="input_gia_file", required=True, help="输入 .gia 文件路径")
    argument_parser.add_argument(
        "--output",
        dest="output_json_file",
        default="gia_entities.json",
        help="输出 JSON 文件路径（会强制落盘到 ugc_file_tools/out/；默认 gia_entities.json）。",
    )
    argument_parser.add_argument(
        "--circle-color",
        dest="circle_colors",
        action="append",
        default=[],
        help="指定一个“圆形颜色”的 hex（可多次传入）。例如 --circle-color #F3D199",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 .gia 容器头/尾（失败会直接抛错）。",
    )
    argument_parser.add_argument(
        "--decode-max-depth",
        dest="decode_max_depth",
        type=int,
        default=24,
        help="protobuf 递归解码深度上限（默认 24；实体/装饰物通常嵌套更深）。",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    output_path = export_gia_entities(
        Path(args.input_gia_file),
        output_json_path=Path(args.output_json_file),
        circle_colors=list(args.circle_colors or []),
        check_header=bool(args.check_header),
        decode_max_depth=int(args.decode_max_depth),
    )

    print("=" * 80)
    print("GIA 实体清单导出完成：")
    print(f"- source_gia_file: {str(Path(args.input_gia_file).resolve())}")
    print(f"- output_json: {str(output_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



