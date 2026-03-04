from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    ProtobufLikeParseOptions,
    decode_varint_with_raw,
    encode_tag,
    encode_varint,
    parse_message,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, parse_tag_raw, split_length_delimited_value_raw


@dataclass(frozen=True, slots=True)
class WireChunk:
    field_number: int
    wire_type: int
    tag_raw: bytes
    value_raw: bytes


_PROBE_OPTIONS = ProtobufLikeParseOptions(
    max_depth=3,
    bytes_preview_length=32,
    max_length_delimited_string_bytes=128,
    max_packed_items=256,
    max_message_bytes_for_probe=4096,
)


def _parse_chunks(chunks: List[Tuple[bytes, bytes]]) -> List[WireChunk]:
    out: List[WireChunk] = []
    for tag_raw, value_raw in list(chunks):
        tag = parse_tag_raw(tag_raw)
        out.append(
            WireChunk(
                field_number=int(tag.field_number),
                wire_type=int(tag.wire_type),
                tag_raw=bytes(tag_raw),
                value_raw=bytes(value_raw),
            )
        )
    return out


def _is_valid_message_payload(payload: bytes) -> bool:
    if not payload:
        return False
    message_json, next_offset, ok, _error = parse_message(
        byte_data=payload,
        start_offset=0,
        end_offset=len(payload),
        depth=0,
        options=_PROBE_OPTIONS,
    )
    if not ok:
        return False
    if next_offset != len(payload):
        return False
    entry_count = int(message_json.get("_meta", {}).get("entry_count", 0))
    return entry_count > 0


def _decode_varint_value(value_raw: bytes) -> int:
    value, next_offset, _raw, ok = decode_varint_with_raw(value_raw, 0, len(value_raw))
    if not ok or next_offset != len(value_raw):
        raise ValueError("invalid varint value_raw")
    return int(value)


def _derive_file_path_from_base(*, base_file_path: str, output_file_name: str) -> str:
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
    marker = "\\"
    last = base.rfind(marker)
    if last < 0:
        return base + marker + out_name
    return base[: last + 1] + out_name


def _encode_fixed32_float(value: float) -> bytes:
    return struct.pack("<f", float(value))


def _build_vector3_message(x: float, y: float, z: float) -> bytes:
    chunks = [
        (encode_tag(1, 5), _encode_fixed32_float(float(x))),
        (encode_tag(2, 5), _encode_fixed32_float(float(y))),
        (encode_tag(3, 5), _encode_fixed32_float(float(z))),
    ]
    return encode_wire_chunks(chunks)


def _decode_vector3_message(payload: bytes) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not payload:
        return None, None, None
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    if consumed != len(payload):
        raise ValueError("vector3 payload wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    for c in parsed:
        if c.wire_type != 5:
            continue
        if len(c.value_raw) < 4:
            raise ValueError("vector3 fixed32 value_raw truncated")
        if c.field_number == 1:
            x = struct.unpack("<f", c.value_raw[:4])[0]
        elif c.field_number == 2:
            y = struct.unpack("<f", c.value_raw[:4])[0]
        elif c.field_number == 3:
            z = struct.unpack("<f", c.value_raw[:4])[0]
    return x, y, z


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return float(lo)
    if value > hi:
        return float(hi)
    return float(value)


def _deg_to_rad(deg: float) -> float:
    return float(deg) * math.pi / 180.0


def _rad_to_deg(rad: float) -> float:
    return float(rad) * 180.0 / math.pi


def _normalize_deg(deg: float) -> float:
    # Normalize to [-180, 180)
    v = (float(deg) + 180.0) % 360.0 - 180.0
    if abs(v) < 1e-12:
        return 0.0
    return float(v)


def _decode_vector3_message_with_default(
    payload: bytes, *, default: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    x, y, z = _decode_vector3_message(payload)
    dx, dy, dz = tuple(default)
    return (
        float(dx if x is None else x),
        float(dy if y is None else y),
        float(dz if z is None else z),
    )


Mat3 = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
Mat4 = Tuple[
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
]


def _mat3_transpose(m: Mat3) -> Mat3:
    return (
        (float(m[0][0]), float(m[1][0]), float(m[2][0])),
        (float(m[0][1]), float(m[1][1]), float(m[2][1])),
        (float(m[0][2]), float(m[1][2]), float(m[2][2])),
    )


def _mat3_mul_vec3(m: Mat3, v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return (
        float(m[0][0] * x + m[0][1] * y + m[0][2] * z),
        float(m[1][0] * x + m[1][1] * y + m[1][2] * z),
        float(m[2][0] * x + m[2][1] * y + m[2][2] * z),
    )


def _mat3_from_euler_deg_unity_zxy(rot_deg: Tuple[float, float, float]) -> Mat3:
    """
    Euler(deg) → rotation matrix（经验：z, x, y 顺序）：
    R = Ry(y) * Rx(x) * Rz(z)

    说明：该实现用于 keep_world / reparent 的几何保持，要求内部自洽。
    """
    x_rad = _deg_to_rad(float(rot_deg[0]))
    y_rad = _deg_to_rad(float(rot_deg[1]))
    z_rad = _deg_to_rad(float(rot_deg[2]))

    cx, sx = math.cos(x_rad), math.sin(x_rad)
    cy, sy = math.cos(y_rad), math.sin(y_rad)
    cz, sz = math.cos(z_rad), math.sin(z_rad)

    r00 = cy * cz + sy * sx * sz
    r01 = -cy * sz + sy * sx * cz
    r02 = sy * cx

    r10 = cx * sz
    r11 = cx * cz
    r12 = -sx

    r20 = -sy * cz + cy * sx * sz
    r21 = sy * sz + cy * sx * cz
    r22 = cy * cx

    return (
        (float(r00), float(r01), float(r02)),
        (float(r10), float(r11), float(r12)),
        (float(r20), float(r21), float(r22)),
    )


def _euler_deg_unity_zxy_from_mat3(r: Mat3) -> Tuple[float, float, float]:
    """
    rotation matrix → Euler(deg)，匹配 `_mat3_from_euler_deg_unity_zxy` 的约定。
    """
    sin_x = _clamp(-float(r[1][2]), -1.0, 1.0)
    x = math.asin(sin_x)
    cx = math.cos(x)

    if abs(cx) > 1e-8:
        z = math.atan2(float(r[1][0]), float(r[1][1]))
        y = math.atan2(float(r[0][2]), float(r[2][2]))
    else:
        z = 0.0
        if x > 0.0:
            y = math.atan2(float(r[0][1]), float(r[0][0]))
        else:
            y = math.atan2(-float(r[0][1]), float(r[0][0]))

    return (_normalize_deg(_rad_to_deg(x)), _normalize_deg(_rad_to_deg(y)), _normalize_deg(_rad_to_deg(z)))


def _mat4_from_trs(
    *,
    pos: Tuple[float, float, float],
    rot_deg: Tuple[float, float, float],
    scale: Tuple[float, float, float],
) -> Mat4:
    r = _mat3_from_euler_deg_unity_zxy(tuple(rot_deg))
    sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
    # A = R * diag(scale)  (column-wise scale)
    a00, a01, a02 = float(r[0][0] * sx), float(r[0][1] * sy), float(r[0][2] * sz)
    a10, a11, a12 = float(r[1][0] * sx), float(r[1][1] * sy), float(r[1][2] * sz)
    a20, a21, a22 = float(r[2][0] * sx), float(r[2][1] * sy), float(r[2][2] * sz)
    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
    return (
        (a00, a01, a02, px),
        (a10, a11, a12, py),
        (a20, a21, a22, pz),
        (0.0, 0.0, 0.0, 1.0),
    )


def _mat4_mul(a: Mat4, b: Mat4) -> Mat4:
    out: List[List[float]] = [[0.0, 0.0, 0.0, 0.0] for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = float(
                a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
            )
    return (tuple(out[0]), tuple(out[1]), tuple(out[2]), tuple(out[3]))  # type: ignore[return-value]


def _mat4_inv_trs(
    *,
    pos: Tuple[float, float, float],
    rot_deg: Tuple[float, float, float],
    scale: Tuple[float, float, float],
) -> Mat4:
    sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
    if abs(sx) < 1e-12 or abs(sy) < 1e-12 or abs(sz) < 1e-12:
        raise ValueError(f"invalid scale for TRS inverse: scale={scale!r}")
    inv_sx, inv_sy, inv_sz = 1.0 / sx, 1.0 / sy, 1.0 / sz

    r = _mat3_from_euler_deg_unity_zxy(tuple(rot_deg))
    rt = _mat3_transpose(r)
    # invA = S^-1 * R^T  (left-multiply diag => scale rows)
    inv_a: Mat3 = (
        (float(rt[0][0] * inv_sx), float(rt[0][1] * inv_sx), float(rt[0][2] * inv_sx)),
        (float(rt[1][0] * inv_sy), float(rt[1][1] * inv_sy), float(rt[1][2] * inv_sy)),
        (float(rt[2][0] * inv_sz), float(rt[2][1] * inv_sz), float(rt[2][2] * inv_sz)),
    )

    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
    inv_tx = -float(inv_a[0][0] * px + inv_a[0][1] * py + inv_a[0][2] * pz)
    inv_ty = -float(inv_a[1][0] * px + inv_a[1][1] * py + inv_a[1][2] * pz)
    inv_tz = -float(inv_a[2][0] * px + inv_a[2][1] * py + inv_a[2][2] * pz)

    return (
        (float(inv_a[0][0]), float(inv_a[0][1]), float(inv_a[0][2]), float(inv_tx)),
        (float(inv_a[1][0]), float(inv_a[1][1]), float(inv_a[1][2]), float(inv_ty)),
        (float(inv_a[2][0]), float(inv_a[2][1]), float(inv_a[2][2]), float(inv_tz)),
        (0.0, 0.0, 0.0, 1.0),
    )


def _decompose_mat4_to_trs(m: Mat4) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    px, py, pz = float(m[0][3]), float(m[1][3]), float(m[2][3])

    # columns of upper 3x3
    c0 = (float(m[0][0]), float(m[1][0]), float(m[2][0]))
    c1 = (float(m[0][1]), float(m[1][1]), float(m[2][1]))
    c2 = (float(m[0][2]), float(m[1][2]), float(m[2][2]))

    def length(v: Tuple[float, float, float]) -> float:
        return float(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))

    sx, sy, sz = length(c0), length(c1), length(c2)
    if sx < 1e-12 or sy < 1e-12 or sz < 1e-12:
        raise ValueError(f"cannot decompose TRS: singular scale from matrix (sx,sy,sz)=({sx},{sy},{sz})")

    r: Mat3 = (
        (float(m[0][0] / sx), float(m[0][1] / sy), float(m[0][2] / sz)),
        (float(m[1][0] / sx), float(m[1][1] / sy), float(m[1][2] / sz)),
        (float(m[2][0] / sx), float(m[2][1] / sy), float(m[2][2] / sz)),
    )

    det = (
        r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1])
        - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
        + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0])
    )
    if float(det) < 0.0:
        sx = -float(sx)
        r = (
            (-float(r[0][0]), float(r[0][1]), float(r[0][2])),
            (-float(r[1][0]), float(r[1][1]), float(r[1][2])),
            (-float(r[2][0]), float(r[2][1]), float(r[2][2])),
        )

    rot_deg = _euler_deg_unity_zxy_from_mat3(r)
    return (float(px), float(py), float(pz)), tuple(rot_deg), (float(sx), float(sy), float(sz))


def _extract_trs_from_transform_message(
    transform_bytes: bytes,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("transform: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    pos: Optional[Tuple[float, float, float]] = None
    rot_deg = (0.0, 0.0, 0.0)
    scale = (1.0, 1.0, 1.0)

    for c in parsed:
        if c.wire_type != 2:
            continue
        if c.field_number == 1:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            x, y, z = _decode_vector3_message(payload)
            if x is None or y is None or z is None:
                raise ValueError("transform.pos(Vector3) 缺字段")
            pos = (float(x), float(y), float(z))
        elif c.field_number == 2:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            rot_deg = _decode_vector3_message_with_default(payload, default=rot_deg)
        elif c.field_number == 3:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            scale = _decode_vector3_message_with_default(payload, default=scale)

    if pos is None:
        raise ValueError("transform: 缺少 position(field_1)")
    return tuple(pos), tuple(rot_deg), tuple(scale)


def _patch_transform_trs_optional(
    transform_bytes: bytes,
    *,
    pos: Optional[Tuple[float, float, float]],
    rot_deg: Optional[Tuple[float, float, float]],
    scale: Optional[Tuple[float, float, float]],
) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("wire decode not fully consumed (transform)")
    parsed = _parse_chunks(chunks_raw)

    want_pos = pos is not None
    want_rot = rot_deg is not None
    want_scale = scale is not None

    wrote_pos = False
    wrote_rot = False
    wrote_scale = False

    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.wire_type == 2 and c.field_number in (1, 2, 3):
            if c.field_number == 1 and want_pos and (not wrote_pos):
                out.append(
                    (
                        c.tag_raw,
                        build_length_delimited_value_raw(_build_vector3_message(float(pos[0]), float(pos[1]), float(pos[2]))),  # type: ignore[index]
                    )
                )
                wrote_pos = True
                continue
            if c.field_number == 2 and want_rot and (not wrote_rot):
                out.append(
                    (
                        c.tag_raw,
                        build_length_delimited_value_raw(
                            _build_vector3_message(float(rot_deg[0]), float(rot_deg[1]), float(rot_deg[2]))  # type: ignore[index]
                        ),
                    )
                )
                wrote_rot = True
                continue
            if c.field_number == 3 and want_scale and (not wrote_scale):
                out.append(
                    (
                        c.tag_raw,
                        build_length_delimited_value_raw(
                            _build_vector3_message(float(scale[0]), float(scale[1]), float(scale[2]))  # type: ignore[index]
                        ),
                    )
                )
                wrote_scale = True
                continue
        out.append((c.tag_raw, c.value_raw))

    if want_pos and (not wrote_pos):
        out.append(
            (
                encode_tag(1, 2),
                build_length_delimited_value_raw(_build_vector3_message(float(pos[0]), float(pos[1]), float(pos[2]))),  # type: ignore[index]
            )
        )
    if want_rot and (not wrote_rot):
        out.append(
            (
                encode_tag(2, 2),
                build_length_delimited_value_raw(_build_vector3_message(float(rot_deg[0]), float(rot_deg[1]), float(rot_deg[2]))),  # type: ignore[index]
            )
        )
    if want_scale and (not wrote_scale):
        out.append(
            (
                encode_tag(3, 2),
                build_length_delimited_value_raw(_build_vector3_message(float(scale[0]), float(scale[1]), float(scale[2]))),  # type: ignore[index]
            )
        )

    return encode_wire_chunks(out)


def _pack_varints(values: Sequence[int]) -> bytes:
    out: List[bytes] = []
    for v in list(values):
        out.append(encode_varint(int(v)))
    return b"".join(out)


def _patch_first_varint_field(message_bytes: bytes, *, field_number: int, new_value: int) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (varint patch)")
    parsed = _parse_chunks(chunks_raw)

    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == int(field_number) and c.wire_type == 0 and not replaced:
            out.append((c.tag_raw, encode_varint(int(new_value))))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))
    if not replaced:
        out.append((encode_tag(int(field_number), 0), encode_varint(int(new_value))))
    return encode_wire_chunks(out)


def _patch_transform_pos_only(transform_bytes: bytes, *, pos: Tuple[float, float, float]) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("wire decode not fully consumed (transform)")
    parsed = _parse_chunks(chunks_raw)

    pos_payload = _build_vector3_message(pos[0], pos[1], pos[2])
    pos_value_raw = build_length_delimited_value_raw(pos_payload)

    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == 1 and c.wire_type == 2 and not replaced:
            out.append((c.tag_raw, pos_value_raw))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))
    if not replaced:
        out.append((encode_tag(1, 2), pos_value_raw))
    return encode_wire_chunks(out)


def _extract_graph_unit_id(graph_unit_bytes: bytes) -> int:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number != 1 or c.wire_type != 2:
            continue
        _lr, id_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(id_payload):
            continue
        id_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=id_payload, start_offset=0, end_offset=len(id_payload))
        if consumed2 != len(id_payload):
            raise ValueError("GraphUnit.id wire decode not fully consumed")
        id_parsed = _parse_chunks(id_chunks_raw)
        for ic in id_parsed:
            if ic.field_number == 4 and ic.wire_type == 0:
                return _decode_varint_value(ic.value_raw)
    raise ValueError("GraphUnit: 无法提取 id(field_1.field_4)")


def _extract_graph_unit_name(graph_unit_bytes: bytes) -> str:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number == 3 and c.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            return payload.decode("utf-8", errors="replace")
    return ""


def _try_extract_transform_pos_from_component_tree(graph_unit_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    """
    优先尝试按 `list_gia_entities` 的经验路径从 GraphUnit 中提取 Transform.position：
    - unit.field_12(field_12) -> message
      - .field_1 -> message
        - .field_6[*] -> entry message
          - entry.field_1 == 1 优先（否则回退第一个包含 field_11 的 entry）
          - entry.field_11 -> transform message
            - transform.field_1 -> Vector3 message (fixed32 floats)
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes)
    )
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    c12_payload: Optional[bytes] = None
    for c in parsed:
        if c.field_number == 12 and c.wire_type == 2:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            c12_payload = bytes(p)
            break
    if c12_payload is None or (not _is_valid_message_payload(c12_payload)):
        return None

    c12_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=c12_payload, start_offset=0, end_offset=len(c12_payload))
    if consumed2 != len(c12_payload):
        raise ValueError("GraphUnit.field_12 wire decode not fully consumed")
    c12_parsed = _parse_chunks(c12_chunks_raw)

    c1_payload: Optional[bytes] = None
    for c in c12_parsed:
        if c.field_number == 1 and c.wire_type == 2:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            c1_payload = bytes(p)
            break
    if c1_payload is None or (not _is_valid_message_payload(c1_payload)):
        return None

    c1_chunks_raw, consumed3 = decode_message_to_wire_chunks(data_bytes=c1_payload, start_offset=0, end_offset=len(c1_payload))
    if consumed3 != len(c1_payload):
        raise ValueError("GraphUnit.field_12.field_1 wire decode not fully consumed")
    c1_parsed = _parse_chunks(c1_chunks_raw)

    # pick entry: prefer key==1, else first entry containing field_11
    chosen_transform_payload: Optional[bytes] = None
    fallback_transform_payload: Optional[bytes] = None
    for c in c1_parsed:
        if c.field_number != 6 or c.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed4 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed4 != len(entry_payload):
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)

        entry_key: Optional[int] = None
        transform_payload: Optional[bytes] = None
        for ec in entry_parsed:
            if ec.field_number == 1 and ec.wire_type == 0 and entry_key is None:
                entry_key = _decode_varint_value(ec.value_raw)
            if ec.field_number == 11 and ec.wire_type == 2 and transform_payload is None:
                _lr2, p2 = split_length_delimited_value_raw(ec.value_raw)
                transform_payload = bytes(p2)
        if transform_payload is None or (not _is_valid_message_payload(transform_payload)):
            continue
        if fallback_transform_payload is None:
            fallback_transform_payload = bytes(transform_payload)
        if entry_key == 1:
            chosen_transform_payload = bytes(transform_payload)
            break

    transform_bytes = chosen_transform_payload or fallback_transform_payload
    if transform_bytes is None:
        return None

    # read transform.field_1 position vector3
    t_chunks_raw, consumed5 = decode_message_to_wire_chunks(
        data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes)
    )
    if consumed5 != len(transform_bytes):
        raise ValueError("transform wire decode not fully consumed")
    t_parsed = _parse_chunks(t_chunks_raw)
    for tc in t_parsed:
        if tc.field_number == 1 and tc.wire_type == 2:
            _lr, pos_payload = split_length_delimited_value_raw(tc.value_raw)
            x, y, z = _decode_vector3_message(pos_payload)
            if x is None or y is None or z is None:
                raise ValueError("GraphUnit.transform.pos(Vector3) 缺字段")
            return float(x), float(y), float(z)
    return None


def _try_extract_transform_trs_from_component_tree(
    graph_unit_bytes: bytes,
) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]]:
    """
    同 `_try_extract_transform_pos_from_component_tree`，但提取 Transform 的 TRS（pos/rot/scale）。
    - pos: transform.field_1(Vector3, required)
    - rot_deg: transform.field_2(Vector3, default (0,0,0))
    - scale: transform.field_3(Vector3, default (1,1,1))
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes)
    )
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    c12_payload: Optional[bytes] = None
    for c in parsed:
        if c.field_number == 12 and c.wire_type == 2:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            c12_payload = bytes(p)
            break
    if c12_payload is None or (not _is_valid_message_payload(c12_payload)):
        return None

    c12_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=c12_payload, start_offset=0, end_offset=len(c12_payload))
    if consumed2 != len(c12_payload):
        raise ValueError("GraphUnit.field_12 wire decode not fully consumed")
    c12_parsed = _parse_chunks(c12_chunks_raw)

    c1_payload: Optional[bytes] = None
    for c in c12_parsed:
        if c.field_number == 1 and c.wire_type == 2:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            c1_payload = bytes(p)
            break
    if c1_payload is None or (not _is_valid_message_payload(c1_payload)):
        return None

    c1_chunks_raw, consumed3 = decode_message_to_wire_chunks(data_bytes=c1_payload, start_offset=0, end_offset=len(c1_payload))
    if consumed3 != len(c1_payload):
        raise ValueError("GraphUnit.field_12.field_1 wire decode not fully consumed")
    c1_parsed = _parse_chunks(c1_chunks_raw)

    chosen_transform_payload: Optional[bytes] = None
    fallback_transform_payload: Optional[bytes] = None
    for c in c1_parsed:
        if c.field_number != 6 or c.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed4 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed4 != len(entry_payload):
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)

        entry_key: Optional[int] = None
        transform_payload: Optional[bytes] = None
        for ec in entry_parsed:
            if ec.field_number == 1 and ec.wire_type == 0 and entry_key is None:
                entry_key = _decode_varint_value(ec.value_raw)
            if ec.field_number == 11 and ec.wire_type == 2 and transform_payload is None:
                _lr2, p2 = split_length_delimited_value_raw(ec.value_raw)
                transform_payload = bytes(p2)
        if transform_payload is None or (not _is_valid_message_payload(transform_payload)):
            continue
        if fallback_transform_payload is None:
            fallback_transform_payload = bytes(transform_payload)
        if entry_key == 1:
            chosen_transform_payload = bytes(transform_payload)
            break

    transform_bytes = chosen_transform_payload or fallback_transform_payload
    if transform_bytes is None:
        return None
    return _extract_trs_from_transform_message(bytes(transform_bytes))


def _patch_first_transform_pos_in_message(message_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> Tuple[bytes, bool]:
    """
    在任意 message 里递归寻找“transform-like message”（包含 field_1(Vector3)）并补丁其 position。
    返回：(patched_message_bytes, patched_bool)。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes)
    )
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (recursive transform patch)")
    parsed = _parse_chunks(chunks_raw)

    # 1) current message itself is a transform?
    # A transform-like message contains field_1 (wire_type=2) which payload is a Vector3 message (fixed32 floats).
    for c in parsed:
        if c.field_number != 1 or c.wire_type != 2:
            continue
        _lr, pos_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(pos_payload):
            continue
        vx, vy, vz = _decode_vector3_message(pos_payload)
        if vx is None or vy is None or vz is None:
            continue
        return _patch_transform_pos_only(message_bytes, pos=tuple(new_pos)), True

    # 2) otherwise search nested messages (DFS)
    out: List[Tuple[bytes, bytes]] = []
    patched_any = False
    for c in parsed:
        if (not patched_any) and c.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            if _is_valid_message_payload(payload):
                new_payload, patched = _patch_first_transform_pos_in_message(payload, new_pos=tuple(new_pos))
                if patched:
                    out.append((c.tag_raw, build_length_delimited_value_raw(new_payload)))
                    patched_any = True
                    continue
        out.append((c.tag_raw, c.value_raw))

    if not patched_any:
        return message_bytes, False
    return encode_wire_chunks(out), True


def _try_patch_transform_pos_in_component_tree(
    graph_unit_bytes: bytes, *, new_pos: Tuple[float, float, float]
) -> Tuple[Optional[bytes], bool]:
    """
    尝试按 component tree 固定形态补丁 Transform.position。
    返回：(patched_bytes_or_none, patched_bool)。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes)
    )
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    # locate field_12
    index_12: Optional[int] = None
    c12_payload: Optional[bytes] = None
    for i, c in enumerate(parsed):
        if c.field_number == 12 and c.wire_type == 2:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            c12_payload = bytes(p)
            index_12 = int(i)
            break
    if index_12 is None or c12_payload is None or (not _is_valid_message_payload(c12_payload)):
        return None, False

    c12_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=c12_payload, start_offset=0, end_offset=len(c12_payload))
    if consumed2 != len(c12_payload):
        raise ValueError("GraphUnit.field_12 wire decode not fully consumed")
    c12_parsed = _parse_chunks(c12_chunks_raw)

    # locate c12.field_1
    index_c1: Optional[int] = None
    c1_payload: Optional[bytes] = None
    for i, c in enumerate(c12_parsed):
        if c.field_number == 1 and c.wire_type == 2:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            c1_payload = bytes(p)
            index_c1 = int(i)
            break
    if index_c1 is None or c1_payload is None or (not _is_valid_message_payload(c1_payload)):
        return None, False

    c1_chunks_raw, consumed3 = decode_message_to_wire_chunks(data_bytes=c1_payload, start_offset=0, end_offset=len(c1_payload))
    if consumed3 != len(c1_payload):
        raise ValueError("GraphUnit.field_12.field_1 wire decode not fully consumed")
    c1_parsed = _parse_chunks(c1_chunks_raw)

    # choose entry index
    chosen_entry_index: Optional[int] = None
    for i, c in enumerate(c1_parsed):
        if c.field_number != 6 or c.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed4 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed4 != len(entry_payload):
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)
        entry_key: Optional[int] = None
        has_transform = False
        for ec in entry_parsed:
            if ec.field_number == 1 and ec.wire_type == 0 and entry_key is None:
                entry_key = _decode_varint_value(ec.value_raw)
            if ec.field_number == 11 and ec.wire_type == 2:
                _lr2, tp = split_length_delimited_value_raw(ec.value_raw)
                if _is_valid_message_payload(tp):
                    has_transform = True
        if not has_transform:
            continue
        if chosen_entry_index is None:
            chosen_entry_index = int(i)
        if entry_key == 1:
            chosen_entry_index = int(i)
            break
    if chosen_entry_index is None:
        return None, False

    # patch chosen entry.field_11 transform.field_1 position
    new_c1_chunks: List[Tuple[bytes, bytes]] = []
    patched = False
    for i, c in enumerate(c1_parsed):
        if i != int(chosen_entry_index):
            new_c1_chunks.append((c.tag_raw, c.value_raw))
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        entry_chunks_raw, consumed4 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed4 != len(entry_payload):
            new_c1_chunks.append((c.tag_raw, c.value_raw))
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)
        new_entry_chunks: List[Tuple[bytes, bytes]] = []
        patched_entry = False
        for ec in entry_parsed:
            if ec.field_number == 11 and ec.wire_type == 2 and not patched_entry:
                _lr2, transform_payload = split_length_delimited_value_raw(ec.value_raw)
                if not _is_valid_message_payload(transform_payload):
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                    continue
                new_transform = _patch_transform_pos_only(transform_payload, pos=tuple(new_pos))
                new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(new_transform)))
                patched_entry = True
            else:
                new_entry_chunks.append((ec.tag_raw, ec.value_raw))
        if patched_entry:
            new_entry_payload = encode_wire_chunks(new_entry_chunks)
            new_c1_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_entry_payload)))
            patched = True
        else:
            new_c1_chunks.append((c.tag_raw, c.value_raw))

    if not patched:
        return None, False

    new_c1_payload = encode_wire_chunks(new_c1_chunks)
    new_c12_chunks: List[Tuple[bytes, bytes]] = []
    for i, c in enumerate(c12_parsed):
        if i == int(index_c1):
            new_c12_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_c1_payload)))
        else:
            new_c12_chunks.append((c.tag_raw, c.value_raw))
    new_c12_payload = encode_wire_chunks(new_c12_chunks)

    new_unit_chunks: List[Tuple[bytes, bytes]] = []
    for i, c in enumerate(parsed):
        if i == int(index_12):
            new_unit_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_c12_payload)))
        else:
            new_unit_chunks.append((c.tag_raw, c.value_raw))
    return encode_wire_chunks(new_unit_chunks), True


def _extract_graph_unit_pos(graph_unit_bytes: bytes) -> Tuple[float, float, float]:
    pos = _try_extract_transform_pos_from_component_tree(graph_unit_bytes)
    if pos is not None:
        return pos

    # fallback: generic DFS search for first transform-like message
    found = _find_first_transform_pos_in_message(graph_unit_bytes)
    if found is None:
        raise ValueError("GraphUnit: 找不到可识别的 Transform.position")
    return found


def _extract_graph_unit_trs(
    graph_unit_bytes: bytes,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    trs = _try_extract_transform_trs_from_component_tree(graph_unit_bytes)
    if trs is not None:
        return trs

    found = _find_first_transform_trs_in_message(graph_unit_bytes)
    if found is None:
        raise ValueError("GraphUnit: 找不到可识别的 Transform(TRS)")
    return found


def _find_first_transform_trs_in_message(
    message_bytes: bytes,
) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]]:
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes)
    )
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (recursive transform search)")
    parsed = _parse_chunks(chunks_raw)

    pos_payload: Optional[bytes] = None
    rot_payload: Optional[bytes] = None
    scale_payload: Optional[bytes] = None
    for c in parsed:
        if c.wire_type != 2 or c.field_number not in (1, 2, 3):
            continue
        _lr, payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(payload):
            continue
        if c.field_number == 1 and pos_payload is None:
            pos_payload = bytes(payload)
        elif c.field_number == 2 and rot_payload is None:
            rot_payload = bytes(payload)
        elif c.field_number == 3 and scale_payload is None:
            scale_payload = bytes(payload)

    if pos_payload is not None:
        x, y, z = _decode_vector3_message(pos_payload)
        if x is not None and y is not None and z is not None:
            rot = _decode_vector3_message_with_default(rot_payload or b"", default=(0.0, 0.0, 0.0))
            scale = _decode_vector3_message_with_default(scale_payload or b"", default=(1.0, 1.0, 1.0))
            return (float(x), float(y), float(z)), tuple(rot), tuple(scale)

    for c in parsed:
        if c.wire_type != 2:
            continue
        _lr, payload = split_length_delimited_value_raw(c.value_raw)
        if _is_valid_message_payload(payload):
            found = _find_first_transform_trs_in_message(payload)
            if found is not None:
                return found
    return None


def _find_first_transform_pos_in_message(message_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes)
    )
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (recursive transform search)")
    parsed = _parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number == 1 and c.wire_type == 2:
            _lr, pos_payload = split_length_delimited_value_raw(c.value_raw)
            if _is_valid_message_payload(pos_payload):
                x, y, z = _decode_vector3_message(pos_payload)
                if x is not None and y is not None and z is not None:
                    return float(x), float(y), float(z)

    for c in parsed:
        if c.wire_type != 2:
            continue
        _lr, payload = split_length_delimited_value_raw(c.value_raw)
        if _is_valid_message_payload(payload):
            found = _find_first_transform_pos_in_message(payload)
            if found is not None:
                return found
    return None


def _patch_graph_unit_pos(graph_unit_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> bytes:
    patched_bytes, ok = _try_patch_transform_pos_in_component_tree(graph_unit_bytes, new_pos=tuple(new_pos))
    if ok and patched_bytes is not None:
        return bytes(patched_bytes)

    patched2, ok2 = _patch_first_transform_pos_in_message(graph_unit_bytes, new_pos=tuple(new_pos))
    if not ok2:
        raise ValueError("GraphUnit: 找不到可补丁的 Transform.position")
    return bytes(patched2)


def _extract_accessory_parent_unit_id(payload_bytes: bytes) -> int:
    """
    从 accessory payload 中提取 parent bind：
    - payload.field_4 entry.key==40 的 entry.field_50.message.field_502
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number != 4 or c.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)
        entry_key: Optional[int] = None
        nested_payload: Optional[bytes] = None
        for ec in entry_parsed:
            if ec.field_number == 1 and ec.wire_type == 0 and entry_key is None:
                entry_key = _decode_varint_value(ec.value_raw)
            if ec.field_number == 50 and ec.wire_type == 2 and nested_payload is None:
                _lr2, np = split_length_delimited_value_raw(ec.value_raw)
                nested_payload = bytes(np)
        if entry_key != 40 or nested_payload is None or (not _is_valid_message_payload(nested_payload)):
            continue
        nested_chunks_raw, consumed3 = decode_message_to_wire_chunks(
            data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
        )
        if consumed3 != len(nested_payload):
            continue
        nested_parsed = _parse_chunks(nested_chunks_raw)
        for nc in nested_parsed:
            if nc.field_number == 502 and nc.wire_type == 0:
                return _decode_varint_value(nc.value_raw)
    raise ValueError("accessory payload: 找不到 parent bind（field_4 entry.key==40 / field_50.field_502）")


def _graph_unit_has_related_ids(graph_unit_bytes: bytes) -> bool:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)
    return any(c.field_number == 2 and c.wire_type == 2 for c in parsed)


def _clear_graph_unit_related_ids(graph_unit_bytes: bytes) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)
    kept = [(c.tag_raw, c.value_raw) for c in parsed if not (c.field_number == 2 and c.wire_type == 2)]
    return encode_wire_chunks(kept)


def _patch_graph_unit_related_ids(graph_unit_bytes: bytes, *, unit_ids: Sequence[int]) -> bytes:
    """
    将 GraphUnit 的 relatedIds(field_2) 重建为给定 unit_ids 列表（wire-level）。
    - 复用 GraphUnit 内现有 relatedId 模板（field_2 的第一条）以保留其它字段。
    - 会删除原有所有 relatedIds，再按 unit_ids 顺序插入新列表。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    related_template: Optional[WireChunk] = None
    first_related_idx: Optional[int] = None
    for idx, c in enumerate(parsed):
        if c.field_number == 2 and c.wire_type == 2:
            related_template = c
            first_related_idx = int(idx)
            break
    if related_template is None:
        raise ValueError("GraphUnit: 缺少 relatedIds(field_2) 模板，无法重建")

    # insertion position: keep the original relatedIds location, else insert right after Id(field_1)
    if first_related_idx is not None:
        insert_at = int(first_related_idx)
    else:
        insert_at = 0
        for idx, c in enumerate(parsed):
            if c.field_number == 1 and c.wire_type == 2:
                insert_at = idx + 1
                break

    # compute insert position in kept list after removing field_2
    insert_pos = 0
    for idx, c in enumerate(parsed):
        if idx >= int(insert_at):
            break
        if c.field_number == 2 and c.wire_type == 2:
            continue
        insert_pos += 1

    kept_chunks: List[Tuple[bytes, bytes]] = [(c.tag_raw, c.value_raw) for c in parsed if not (c.field_number == 2 and c.wire_type == 2)]

    _lr, template_payload = split_length_delimited_value_raw(related_template.value_raw)
    if not _is_valid_message_payload(template_payload):
        raise ValueError("relatedIds template payload 不是 message")

    new_related_chunks: List[Tuple[bytes, bytes]] = []
    for uid in list(unit_ids):
        new_payload = _patch_first_varint_field(template_payload, field_number=4, new_value=int(uid))
        new_related_chunks.append((related_template.tag_raw, build_length_delimited_value_raw(new_payload)))

    spliced = kept_chunks[:insert_pos] + new_related_chunks + kept_chunks[insert_pos:]
    return encode_wire_chunks(spliced)


def _patch_packed_ids_inside_parent_graph(parent_unit_bytes: bytes, *, packed_ids: bytes) -> bytes:
    """
    best-effort：在 parent Graph 内部寻找“packed accessories id 列表”并更新。

    经验（真源样本）：
    - 某个嵌套 message 的 repeated entry 中：
      - entry.field_1(varint) == 40
      - entry.field_50 为 bytes，或为 message 且包含 field_501(bytes)。
    - 承载该 repeated entry 的外层字段号不稳定（常见 5/6），因此只能递归结构匹配。
    """

    def try_patch_entry(entry_payload: bytes) -> Tuple[bytes, bool]:
        entry_chunks_raw, consumed0 = decode_message_to_wire_chunks(data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload))
        if consumed0 != len(entry_payload):
            return entry_payload, False
        entry_parsed = _parse_chunks(entry_chunks_raw)

        entry_key: Optional[int] = None
        for ec in entry_parsed:
            if ec.field_number == 1 and ec.wire_type == 0:
                entry_key = _decode_varint_value(ec.value_raw)
                break
        if entry_key != 40:
            return entry_payload, False

        new_entry_chunks: List[Tuple[bytes, bytes]] = []
        entry_patched = False
        for ec in entry_parsed:
            if ec.field_number == 50 and ec.wire_type == 2 and not entry_patched:
                _lrr, nested_payload = split_length_delimited_value_raw(ec.value_raw)
                if not _is_valid_message_payload(nested_payload):
                    # older shape: field_50 is bytes
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(bytes(packed_ids))))
                    entry_patched = True
                    continue

                nested_chunks_raw, consumed1 = decode_message_to_wire_chunks(
                    data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
                )
                if consumed1 != len(nested_payload):
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                    continue
                nested_parsed = _parse_chunks(nested_chunks_raw)

                new_nested_chunks: List[Tuple[bytes, bytes]] = []
                bytes_patched = False
                for nc in nested_parsed:
                    if nc.field_number == 501 and nc.wire_type == 2 and not bytes_patched:
                        new_nested_chunks.append((nc.tag_raw, build_length_delimited_value_raw(bytes(packed_ids))))
                        bytes_patched = True
                    else:
                        new_nested_chunks.append((nc.tag_raw, nc.value_raw))

                if bytes_patched:
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_nested_chunks))))
                    entry_patched = True
                    continue

                # nested is a message but doesn't contain field_501 in this sample; fall back to raw bytes.
                new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(bytes(packed_ids))))
                entry_patched = True
                continue

            new_entry_chunks.append((ec.tag_raw, ec.value_raw))

        if not entry_patched:
            return entry_payload, False
        return encode_wire_chunks(new_entry_chunks), True

    def patch_message(message_bytes: bytes) -> Tuple[bytes, bool]:
        chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
        if consumed != len(message_bytes):
            return message_bytes, False
        parsed = _parse_chunks(chunks_raw)

        out: List[Tuple[bytes, bytes]] = []
        patched_any = False

        for c in parsed:
            if c.wire_type == 2:
                _lr, payload = split_length_delimited_value_raw(c.value_raw)
                if _is_valid_message_payload(payload):
                    # 1) current payload itself is an entry?
                    new_payload, patched_entry = try_patch_entry(payload)
                    if patched_entry:
                        out.append((c.tag_raw, build_length_delimited_value_raw(new_payload)))
                        patched_any = True
                        continue

                    # 2) otherwise, search deeper
                    new_payload2, patched_nested = patch_message(payload)
                    if patched_nested:
                        out.append((c.tag_raw, build_length_delimited_value_raw(new_payload2)))
                        patched_any = True
                        continue

            out.append((c.tag_raw, c.value_raw))

        return encode_wire_chunks(out), patched_any

    new_parent_bytes, patched = patch_message(parent_unit_bytes)
    if not patched:
        return parent_unit_bytes
    return new_parent_bytes


def _extract_accessory_payload_bytes(accessory_unit_bytes: bytes) -> bytes:
    """
    Accessory GraphUnit 的 wrapper 内部包含 payload(field_1) message。
    wrapper 的字段号不稳定（常见 21），因此这里按“包含 field_1 的 message”做结构探测。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=accessory_unit_bytes, start_offset=0, end_offset=len(accessory_unit_bytes)
    )
    if consumed != len(accessory_unit_bytes):
        raise ValueError("accessory unit: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    for c in parsed:
        if c.wire_type != 2:
            continue
        _lr, wrapper_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(wrapper_payload):
            continue

        wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=wrapper_payload, start_offset=0, end_offset=len(wrapper_payload)
        )
        if consumed2 != len(wrapper_payload):
            continue
        wrapper_parsed = _parse_chunks(wrapper_chunks_raw)

        for wc in wrapper_parsed:
            if wc.field_number != 1 or wc.wire_type != 2:
                continue
            _lr2, payload_bytes = split_length_delimited_value_raw(wc.value_raw)
            if not _is_valid_message_payload(payload_bytes):
                continue
            if _payload_has_transform(payload_bytes):
                return payload_bytes

    raise ValueError("accessory unit: 找不到 wrapper(payload.field_1)")


def _extract_accessory_transform_bytes(payload_bytes: bytes) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number != 5 or c.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue

        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)

        for ec in entry_parsed:
            if ec.field_number == 11 and ec.wire_type == 2:
                _lr2, transform_payload = split_length_delimited_value_raw(ec.value_raw)
                if not _is_valid_message_payload(transform_payload):
                    raise ValueError("accessory payload: transform(field_11) 不是 message")
                return transform_payload

    raise ValueError("accessory payload: 找不到 transform（field_5[*].field_11）")


def _payload_has_transform(payload_bytes: bytes) -> bool:
    if not _is_valid_message_payload(payload_bytes):
        return False
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        return False
    parsed = _parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number != 5 or c.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        entry_parsed = _parse_chunks(entry_chunks_raw)
        if any(ec.field_number == 11 and ec.wire_type == 2 for ec in entry_parsed):
            return True

    return False


def _extract_accessory_pos(accessory_unit_bytes: bytes) -> Tuple[float, float, float]:
    payload_bytes = _extract_accessory_payload_bytes(accessory_unit_bytes)
    transform_bytes = _extract_accessory_transform_bytes(payload_bytes)

    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("transform: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number == 1 and c.wire_type == 2:
            _lr, pos_payload = split_length_delimited_value_raw(c.value_raw)
            x, y, z = _decode_vector3_message(pos_payload)
            if x is None or y is None or z is None:
                raise ValueError("transform.pos(Vector3) 缺字段")
            return float(x), float(y), float(z)

    raise ValueError("transform: 缺少 position(field_1)")


def _extract_accessory_trs(
    accessory_unit_bytes: bytes,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    payload_bytes = _extract_accessory_payload_bytes(accessory_unit_bytes)
    transform_bytes = _extract_accessory_transform_bytes(payload_bytes)
    return _extract_trs_from_transform_message(transform_bytes)


def _patch_accessory_payload(
    payload_bytes: bytes,
    *,
    new_pos: Optional[Tuple[float, float, float]],
    new_rot_deg: Optional[Tuple[float, float, float]],
    new_scale: Optional[Tuple[float, float, float]],
    new_parent_unit_id: Optional[int],
) -> bytes:
    """
    对 accessory payload 做最小补丁：
    - 可选：更新 transform.position/rotation/scale(field_5[*].field_11.field_{1,2,3})
    - 可选：更新 parent bind（field_4 entry.key==40 的 entry.field_50.field_502）
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    want_transform = (new_pos is not None) or (new_rot_deg is not None) or (new_scale is not None)

    out: List[Tuple[bytes, bytes]] = []
    transform_patched = False
    parent_bind_patched = False

    for c in parsed:
        # patch transform (first match)
        if want_transform and (c.field_number == 5 and c.wire_type == 2) and (not transform_patched):
            _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
            if not _is_valid_message_payload(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue

            entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
            )
            if consumed2 != len(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = _parse_chunks(entry_chunks_raw)

            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            patched_entry = False
            for ec in entry_parsed:
                if ec.field_number == 11 and ec.wire_type == 2 and not patched_entry:
                    _lr2, transform_payload = split_length_delimited_value_raw(ec.value_raw)
                    if not _is_valid_message_payload(transform_payload):
                        new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                        continue
                    new_transform = _patch_transform_trs_optional(
                        transform_payload,
                        pos=tuple(new_pos) if new_pos is not None else None,
                        rot_deg=tuple(new_rot_deg) if new_rot_deg is not None else None,
                        scale=tuple(new_scale) if new_scale is not None else None,
                    )
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(new_transform)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))

            if patched_entry:
                out.append((c.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
                transform_patched = True
            else:
                out.append((c.tag_raw, c.value_raw))
            continue

        # patch parent bind (first match entry.key==40)
        if (new_parent_unit_id is not None) and (c.field_number == 4 and c.wire_type == 2) and (not parent_bind_patched):
            _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
            if not _is_valid_message_payload(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue

            entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
            )
            if consumed2 != len(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = _parse_chunks(entry_chunks_raw)

            entry_key: Optional[int] = None
            for ec in entry_parsed:
                if ec.field_number == 1 and ec.wire_type == 0:
                    entry_key = _decode_varint_value(ec.value_raw)
                    break
            if entry_key != 40:
                out.append((c.tag_raw, c.value_raw))
                continue

            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            patched_entry = False
            for ec in entry_parsed:
                if ec.field_number == 50 and ec.wire_type == 2 and not patched_entry:
                    _lr2, nested_payload = split_length_delimited_value_raw(ec.value_raw)
                    if not _is_valid_message_payload(nested_payload):
                        raise ValueError("accessory payload: parent bind nested(field_50) 不是 message")
                    patched_nested = _patch_first_varint_field(
                        nested_payload, field_number=502, new_value=int(new_parent_unit_id)
                    )
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(patched_nested)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))

            if not patched_entry:
                raise ValueError("accessory payload: 找不到 parent bind entry.field_50.field_502")
            out.append((c.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
            parent_bind_patched = True
            continue

        out.append((c.tag_raw, c.value_raw))

    if want_transform and not transform_patched:
        raise ValueError("accessory payload: 找不到可补丁的 transform（field_5[*].field_11）")
    if new_parent_unit_id is not None and not parent_bind_patched:
        raise ValueError("accessory payload: 找不到可补丁的 parent bind（field_4 entry.key==40 / field_50.field_502）")
    return encode_wire_chunks(out)


def _patch_accessory_unit(
    accessory_unit_bytes: bytes,
    *,
    new_pos: Optional[Tuple[float, float, float]],
    new_rot_deg: Optional[Tuple[float, float, float]],
    new_scale: Optional[Tuple[float, float, float]],
    new_parent_unit_id: Optional[int],
) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=accessory_unit_bytes, start_offset=0, end_offset=len(accessory_unit_bytes)
    )
    if consumed != len(accessory_unit_bytes):
        raise ValueError("accessory unit: wire decode not fully consumed")
    parsed = _parse_chunks(chunks_raw)

    out: List[Tuple[bytes, bytes]] = []
    wrapper_patched = False

    for c in parsed:
        if c.wire_type == 2 and not wrapper_patched:
            _lr, wrapper_payload = split_length_delimited_value_raw(c.value_raw)
            if not _is_valid_message_payload(wrapper_payload):
                out.append((c.tag_raw, c.value_raw))
                continue

            wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=wrapper_payload, start_offset=0, end_offset=len(wrapper_payload)
            )
            if consumed2 != len(wrapper_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            wrapper_parsed = _parse_chunks(wrapper_chunks_raw)

            # patch the first field_1 payload that looks like accessory payload (contains transform)
            new_wrapper_chunks: List[Tuple[bytes, bytes]] = []
            inner_patched = False
            for wc in wrapper_parsed:
                if wc.field_number == 1 and wc.wire_type == 2 and not inner_patched:
                    _lr2, payload_bytes = split_length_delimited_value_raw(wc.value_raw)
                    if _is_valid_message_payload(payload_bytes) and _payload_has_transform(payload_bytes):
                        new_payload = _patch_accessory_payload(
                            payload_bytes,
                            new_pos=new_pos,
                            new_rot_deg=new_rot_deg,
                            new_scale=new_scale,
                            new_parent_unit_id=new_parent_unit_id,
                        )
                        new_wrapper_chunks.append((wc.tag_raw, build_length_delimited_value_raw(new_payload)))
                        inner_patched = True
                        continue
                new_wrapper_chunks.append((wc.tag_raw, wc.value_raw))

            if inner_patched:
                out.append((c.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_wrapper_chunks))))
                wrapper_patched = True
                continue

        out.append((c.tag_raw, c.value_raw))

    if not wrapper_patched:
        raise ValueError("accessory unit: 找不到可补丁的 wrapper（含 field_1 payload 的 message）")
    return encode_wire_chunks(out)


def _normalize_axes(axes_text: str) -> Tuple[bool, bool, bool]:
    t = str(axes_text or "").strip().lower().replace(",", "").replace(" ", "")
    if t == "":
        raise ValueError("axes 不能为空")
    if any(ch not in {"x", "y", "z"} for ch in t):
        raise ValueError(f"invalid axes: {axes_text!r}")
    want_x = "x" in t
    want_y = "y" in t
    want_z = "z" in t
    if not (want_x or want_y or want_z):
        raise ValueError(f"invalid axes: {axes_text!r}")
    return want_x, want_y, want_z


def _compute_center(points: Sequence[Tuple[float, float, float]], *, mode: str) -> Tuple[float, float, float]:
    if not points:
        raise ValueError("points 为空")
    m = str(mode or "").strip().lower()
    if m not in {"bbox", "mean"}:
        raise ValueError(f"invalid center mode: {mode!r}")

    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]

    if m == "mean":
        n = float(len(points))
        return (sum(xs) / n, sum(ys) / n, sum(zs) / n)

    # bbox
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)


def merge_and_center_decorations_gia_wire(
    *,
    input_gia_path: Path,
    output_gia_path: Path,
    check_header: bool,
    center_mode: str,
    center_axes: str,
    center_policy: str,
    do_center: bool,
    do_merge: bool,
    target_parent_id: Optional[int],
    target_parent_name: str,
    drop_other_parents: bool,
    keep_file_path: bool,
    file_path_override: str,
) -> Dict[str, Any]:
    """
    对一个“空物体 + 多装饰物”的 `.gia` 做 wire-level 变换：
    - center：
      - move_decorations：计算装饰物坐标中心，并整体平移装饰物，使空物体位于几何中心（通过把中心点平移到原点实现；会改变世界坐标）。
      - keep_world：计算装饰物“世界坐标”中心，并补丁 parent.Transform.position，同时反向补偿每个装饰物的 local position，确保装饰物世界坐标不变。
    - merge：当 Root.field_1 含多个“带 relatedIds 的 parent GraphUnit”时，将所有装饰物挂到同一个 parent 上（更新：
      - parent.relatedIds
      - parent 内部 packed accessories id 列表（best-effort）
      - 每个装饰物的 parent bind 字段）

    说明：
    - 只做最小必要补丁，不做语义重编码，尽量保持真源可见性。
    - 默认会将 Root.filePath 的文件名部分对齐 output 文件名（可用 keep_file_path 或 file_path_override 控制）。
    """
    input_gia_path = Path(input_gia_path).resolve()
    if not input_gia_path.is_file():
        raise FileNotFoundError(f"input gia file not found: {str(input_gia_path)!r}")

    if check_header:
        validate_gia_container_file(input_gia_path)

    proto_bytes = unwrap_gia_container(input_gia_path, check_header=False)
    root_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=proto_bytes, start_offset=0, end_offset=len(proto_bytes))
    if consumed != len(proto_bytes):
        raise ValueError("root wire decode not fully consumed")
    root_parsed = _parse_chunks(root_chunks_raw)

    policy = str(center_policy or "").strip().lower()
    if policy not in {"move_decorations", "keep_world"}:
        raise ValueError(f"invalid center_policy: {center_policy!r} (expected 'move_decorations'|'keep_world')")

    base_file_path_text = ""
    for c in root_parsed:
        if c.field_number == 3 and c.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            base_file_path_text = payload.decode("utf-8", errors="replace")
            break

    # collect root.field_1 (GraphUnit list) and root.field_2 (accessories list)
    parent_units: List[bytes] = []
    for c in root_parsed:
        if c.field_number == 1 and c.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            parent_units.append(bytes(payload))

    accessory_units: List[bytes] = []
    for c in root_parsed:
        if c.field_number == 2 and c.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            accessory_units.append(bytes(payload))

    if not accessory_units:
        raise ValueError("root 缺少 accessories(field_2)")

    want_x, want_y, want_z = _normalize_axes(center_axes)

    # merge: determine candidate parents (units that have relatedIds(field_2))
    candidate_parent_indices = [i for i, u in enumerate(parent_units) if _graph_unit_has_related_ids(u)]

    merge_applicable = bool(do_merge) and len(candidate_parent_indices) >= 2

    target_parent_unit_id: Optional[int] = None
    target_parent_index: Optional[int] = None
    if merge_applicable:
        # pick target parent
        if isinstance(target_parent_id, int):
            want_id = int(target_parent_id)
            matched = [i for i in candidate_parent_indices if _extract_graph_unit_id(parent_units[i]) == want_id]
            if not matched:
                raise ValueError(f"未找到 target_parent_id={want_id}（candidate parents: {candidate_parent_indices}）")
            if len(matched) >= 2:
                raise ValueError(f"target_parent_id={want_id} 匹配到多个 parent（不允许歧义）")
            target_parent_index = int(matched[0])
        else:
            name_text = str(target_parent_name or "").strip()
            if name_text != "":
                matched = [i for i in candidate_parent_indices if _extract_graph_unit_name(parent_units[i]).strip() == name_text]
                if not matched:
                    raise ValueError(f"未找到 target_parent_name={name_text!r}")
                if len(matched) >= 2:
                    raise ValueError(f"target_parent_name={name_text!r} 匹配到多个 parent（请改用 --target-parent-id）")
                target_parent_index = int(matched[0])
            else:
                target_parent_index = int(candidate_parent_indices[0])
        target_parent_unit_id = _extract_graph_unit_id(parent_units[int(target_parent_index)])
    else:
        # for reporting / single-parent cases
        if candidate_parent_indices:
            target_parent_index = int(candidate_parent_indices[0])
            target_parent_unit_id = _extract_graph_unit_id(parent_units[int(target_parent_index)])

    # ---- Parse accessories (id/local/parent bind) ----
    accessory_items: List[Dict[str, Any]] = []
    for unit in accessory_units:
        unit_bytes = bytes(unit)
        unit_id_int = _extract_graph_unit_id(unit_bytes)
        local_pos, local_rot_deg, local_scale = _extract_accessory_trs(unit_bytes)
        payload_bytes = _extract_accessory_payload_bytes(unit_bytes)
        parent_id_int = _extract_accessory_parent_unit_id(payload_bytes)
        accessory_items.append(
            {
                "unit_bytes": unit_bytes,
                "unit_id_int": int(unit_id_int),
                "parent_id_int": int(parent_id_int),
                "local_pos": (float(local_pos[0]), float(local_pos[1]), float(local_pos[2])),
                "local_rot_deg": (float(local_rot_deg[0]), float(local_rot_deg[1]), float(local_rot_deg[2])),
                "local_scale": (float(local_scale[0]), float(local_scale[1]), float(local_scale[2])),
            }
        )

    # ---- Strategy: move decorations (local space) ----
    if policy == "move_decorations":
        local_positions = [tuple(it["local_pos"]) for it in accessory_items]
        center_x, center_y, center_z = _compute_center(local_positions, mode=str(center_mode))
        shift_x = center_x if want_x else 0.0
        shift_y = center_y if want_y else 0.0
        shift_z = center_z if want_z else 0.0

        merged = False
        parent_units_by_original_index: List[Optional[bytes]] = [bytes(u) for u in parent_units]

        if merge_applicable and target_parent_index is not None and target_parent_unit_id is not None:
            accessory_unit_ids = [int(it["unit_id_int"]) for it in accessory_items]
            packed_ids = _pack_varints(accessory_unit_ids)

            new_target_parent = _patch_graph_unit_related_ids(parent_units[int(target_parent_index)], unit_ids=accessory_unit_ids)
            new_target_parent = _patch_packed_ids_inside_parent_graph(new_target_parent, packed_ids=packed_ids)

            new_parent_units: List[Optional[bytes]] = []
            for idx, u in enumerate(parent_units):
                if idx == int(target_parent_index):
                    new_parent_units.append(bytes(new_target_parent))
                    continue
                if idx in candidate_parent_indices:
                    if bool(drop_other_parents):
                        new_parent_units.append(None)
                    else:
                        new_parent_units.append(bytes(_clear_graph_unit_related_ids(u)))
                    continue
                new_parent_units.append(bytes(u))
            parent_units_by_original_index = new_parent_units
            merged = True

        new_accessory_units: List[bytes] = []
        for it in accessory_items:
            out_unit = bytes(it["unit_bytes"])
            if merged and target_parent_unit_id is not None:
                out_unit = _patch_accessory_unit(
                    out_unit,
                    new_pos=None,
                    new_rot_deg=None,
                    new_scale=None,
                    new_parent_unit_id=int(target_parent_unit_id),
                )
            if bool(do_center):
                x, y, z = it["local_pos"]
                new_pos = (float(x - shift_x), float(y - shift_y), float(z - shift_z))
                out_unit = _patch_accessory_unit(out_unit, new_pos=new_pos, new_rot_deg=None, new_scale=None, new_parent_unit_id=None)
            new_accessory_units.append(bytes(out_unit))

        shift_space = "decorations_local"
        shift_applied = {"x": float(shift_x), "y": float(shift_y), "z": float(shift_z)}
        center_space = "local"
        center_obj = {"x": float(center_x), "y": float(center_y), "z": float(center_z)}
        target_parent_pos_before = None
        target_parent_pos_after = None

    # ---- Strategy: keep world positions (move parent + compensate locals) ----
    else:
        # Resolve parent GraphUnits by id (need their world transforms).
        parent_unit_by_id: Dict[int, bytes] = {}
        parent_index_by_id: Dict[int, int] = {}
        for idx, u in enumerate(parent_units):
            uid = _extract_graph_unit_id(u)
            if int(uid) in parent_unit_by_id:
                raise ValueError(f"duplicated parent GraphUnit id in Root.field_1: {int(uid)}")
            parent_unit_by_id[int(uid)] = bytes(u)
            parent_index_by_id[int(uid)] = int(idx)

        involved_parent_ids = sorted({int(it["parent_id_int"]) for it in accessory_items})
        if merge_applicable and isinstance(target_parent_unit_id, int):
            if int(target_parent_unit_id) not in involved_parent_ids:
                involved_parent_ids.append(int(target_parent_unit_id))
                involved_parent_ids.sort()

        parent_trs_by_id: Dict[
            int, Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
        ] = {}
        parent_mat_by_id: Dict[int, Mat4] = {}
        for pid in involved_parent_ids:
            if pid not in parent_unit_by_id:
                raise ValueError(f"accessory 绑定的 parent_id={pid} 不存在于 Root.field_1（无法保持世界坐标不动）")
            trs = _extract_graph_unit_trs(parent_unit_by_id[int(pid)])
            parent_trs_by_id[int(pid)] = trs
            parent_mat_by_id[int(pid)] = _mat4_from_trs(pos=trs[0], rot_deg=trs[1], scale=trs[2])

        # Compute per-accessory world matrices + positions.
        world_positions_all: List[Tuple[float, float, float]] = []
        for it in accessory_items:
            pid = int(it["parent_id_int"])
            parent_mat = parent_mat_by_id[pid]
            local_mat = _mat4_from_trs(
                pos=tuple(it["local_pos"]),
                rot_deg=tuple(it["local_rot_deg"]),
                scale=tuple(it["local_scale"]),
            )
            world_mat = _mat4_mul(parent_mat, local_mat)
            wx, wy, wz = float(world_mat[0][3]), float(world_mat[1][3]), float(world_mat[2][3])
            it["world_mat"] = world_mat
            it["world_pos"] = (wx, wy, wz)
            world_positions_all.append((wx, wy, wz))

        center_x, center_y, center_z = _compute_center(world_positions_all, mode=str(center_mode))
        center_space = "world"
        center_obj = {"x": float(center_x), "y": float(center_y), "z": float(center_z)}

        # Patch parents + accessories
        parent_units_by_original_index = [bytes(u) for u in parent_units]
        new_accessory_units: List[bytes] = []
        merged = False

        target_parent_pos_before = None
        target_parent_pos_after = None

        if merge_applicable and target_parent_unit_id is not None and target_parent_index is not None:
            merged = True
            p0, r0, s0 = parent_trs_by_id[int(target_parent_unit_id)]
            target_parent_pos_before = {"x": float(p0[0]), "y": float(p0[1]), "z": float(p0[2])}

            if bool(do_center):
                p1 = (
                    float(center_x) if want_x else float(p0[0]),
                    float(center_y) if want_y else float(p0[1]),
                    float(center_z) if want_z else float(p0[2]),
                )
            else:
                p1 = (float(p0[0]), float(p0[1]), float(p0[2]))
            target_parent_pos_after = {"x": float(p1[0]), "y": float(p1[1]), "z": float(p1[2])}

            shift_space = "parent_world"
            shift_applied = {"x": float(p1[0] - p0[0]), "y": float(p1[1] - p0[1]), "z": float(p1[2] - p0[2])}

            # patch target parent: relatedIds + packed list + position
            accessory_unit_ids = [int(it["unit_id_int"]) for it in accessory_items]
            packed_ids = _pack_varints(accessory_unit_ids)

            new_target_parent = _patch_graph_unit_related_ids(parent_units[int(target_parent_index)], unit_ids=accessory_unit_ids)
            new_target_parent = _patch_packed_ids_inside_parent_graph(new_target_parent, packed_ids=packed_ids)
            new_target_parent = _patch_graph_unit_pos(new_target_parent, new_pos=tuple(p1))

            new_parent_units: List[Optional[bytes]] = []
            for idx, u in enumerate(parent_units):
                if idx == int(target_parent_index):
                    new_parent_units.append(bytes(new_target_parent))
                    continue
                if idx in candidate_parent_indices:
                    if bool(drop_other_parents):
                        new_parent_units.append(None)
                    else:
                        new_parent_units.append(bytes(_clear_graph_unit_related_ids(u)))
                    continue
                new_parent_units.append(bytes(u))
            parent_units_by_original_index = new_parent_units

            # patch all accessories: rebind parent + compensate local TRS to keep world unchanged
            inv_target_after = _mat4_inv_trs(pos=tuple(p1), rot_deg=tuple(r0), scale=tuple(s0))
            for it in accessory_items:
                local_new_mat = _mat4_mul(inv_target_after, it["world_mat"])
                new_pos, new_rot_deg, new_scale = _decompose_mat4_to_trs(local_new_mat)
                out_unit = _patch_accessory_unit(
                    bytes(it["unit_bytes"]),
                    new_pos=tuple(new_pos),
                    new_rot_deg=tuple(new_rot_deg),
                    new_scale=tuple(new_scale),
                    new_parent_unit_id=int(target_parent_unit_id),
                )
                new_accessory_units.append(bytes(out_unit))

        else:
            # no merge: center per parent (when do_center), keep each accessory bound parent unchanged
            shift_space = "parent_world"
            shift_applied = {"x": 0.0, "y": 0.0, "z": 0.0}

            if not bool(do_center):
                # no centering: keep bytes as-is to avoid float noise
                new_accessory_units = [bytes(it["unit_bytes"]) for it in accessory_items]
            else:
                parent_new_pos_by_id: Dict[int, Tuple[float, float, float]] = {}
                group_world: Dict[int, List[Tuple[float, float, float]]] = {}
                for it in accessory_items:
                    group_world.setdefault(int(it["parent_id_int"]), []).append(tuple(it["world_pos"]))
                for pid, pts in group_world.items():
                    cpx, cpy, cpz = _compute_center(pts, mode=str(center_mode))
                    p0, _r0, _s0 = parent_trs_by_id[int(pid)]
                    p1 = (
                        float(cpx) if want_x else float(p0[0]),
                        float(cpy) if want_y else float(p0[1]),
                        float(cpz) if want_z else float(p0[2]),
                    )
                    parent_new_pos_by_id[int(pid)] = tuple(p1)

                # patch parent units in root.field_1
                for pid, p1 in parent_new_pos_by_id.items():
                    idx = parent_index_by_id.get(int(pid))
                    if idx is None:
                        raise ValueError(f"internal error: parent_index missing for pid={pid}")
                    parent_units_by_original_index[int(idx)] = _patch_graph_unit_pos(
                        parent_units_by_original_index[int(idx)], new_pos=tuple(p1)
                    )

                # patch accessories local pos to keep world constant under moved parent (rot/scale unchanged)
                for it in accessory_items:
                    pid = int(it["parent_id_int"])
                    p1 = parent_new_pos_by_id.get(pid, parent_trs_by_id[pid][0])
                    _p0, r0, s0 = parent_trs_by_id[pid]
                    wx, wy, wz = it["world_pos"]
                    delta = (float(wx - p1[0]), float(wy - p1[1]), float(wz - p1[2]))
                    inv_rs = _mat4_inv_trs(pos=(0.0, 0.0, 0.0), rot_deg=tuple(r0), scale=tuple(s0))
                    new_local = (
                        float(inv_rs[0][0] * delta[0] + inv_rs[0][1] * delta[1] + inv_rs[0][2] * delta[2]),
                        float(inv_rs[1][0] * delta[0] + inv_rs[1][1] * delta[1] + inv_rs[1][2] * delta[2]),
                        float(inv_rs[2][0] * delta[0] + inv_rs[2][1] * delta[1] + inv_rs[2][2] * delta[2]),
                    )
                    out_unit = _patch_accessory_unit(
                        bytes(it["unit_bytes"]),
                        new_pos=new_local,
                        new_rot_deg=None,
                        new_scale=None,
                        new_parent_unit_id=None,
                    )
                    new_accessory_units.append(bytes(out_unit))

    # determine new filePath
    output_gia_path = resolve_output_file_path_in_out_dir(Path(output_gia_path), default_file_name="decorations_centered.gia")
    output_name = Path(str(output_gia_path)).name

    file_path_text = str(file_path_override or "").strip()
    if bool(keep_file_path):
        new_file_path = base_file_path_text
    elif file_path_text != "":
        new_file_path = file_path_text
    else:
        new_file_path = _derive_file_path_from_base(base_file_path=base_file_path_text, output_file_name=output_name)

    new_file_path_value_raw = build_length_delimited_value_raw(new_file_path.encode("utf-8"))

    # rebuild root bytes (preserve unknown fields)
    out_root_chunks: List[Tuple[bytes, bytes]] = []
    file_path_written = False
    parent_idx = 0
    accessory_idx = 0

    for c in root_parsed:
        if c.field_number == 1 and c.wire_type == 2:
            if parent_idx >= len(parent_units_by_original_index):
                raise ValueError("internal error: parent index out of range")
            replacement = parent_units_by_original_index[parent_idx]
            parent_idx += 1
            if replacement is None:
                continue
            out_root_chunks.append((c.tag_raw, build_length_delimited_value_raw(replacement)))
            continue

        if c.field_number == 2 and c.wire_type == 2:
            if accessory_idx >= len(new_accessory_units):
                raise ValueError("internal error: accessory index out of range")
            out_root_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_accessory_units[accessory_idx])))
            accessory_idx += 1
            continue

        if c.field_number == 3 and c.wire_type == 2 and not file_path_written:
            out_root_chunks.append((c.tag_raw, new_file_path_value_raw))
            file_path_written = True
            continue

        out_root_chunks.append((c.tag_raw, c.value_raw))

    if parent_idx != len(parent_units_by_original_index):
        raise ValueError("internal error: not all parent chunks consumed")
    if accessory_idx != len(new_accessory_units):
        raise ValueError("internal error: not all accessory chunks consumed")
    if not file_path_written:
        out_root_chunks.append((encode_tag(3, 2), new_file_path_value_raw))

    out_proto = encode_wire_chunks(out_root_chunks)
    out_bytes = wrap_gia_container(out_proto)
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "input_gia_file": str(input_gia_path),
        "output_gia_file": str(output_gia_path),
        "accessories_count": len(accessory_units),
        "center_policy": str(policy),
        "center_space": str(center_space),
        "shift_space": str(shift_space),
        "center_mode": str(center_mode),
        "center_axes": str(center_axes),
        "center": dict(center_obj),
        "shift_applied": dict(shift_applied),
        "merged": bool(merged),
        "target_parent_unit_id": int(target_parent_unit_id) if target_parent_unit_id is not None else None,
        "target_parent_pos_before": target_parent_pos_before,
        "target_parent_pos_after": target_parent_pos_after,
        "file_path": str(new_file_path),
        "proto_size": len(out_proto),
    }

