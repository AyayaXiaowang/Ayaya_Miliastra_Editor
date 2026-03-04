from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union


# -------------------- GIL container (header/payload/footer) --------------------


@dataclass(frozen=True)
class GilContainer:
    header: bytes
    payload: bytes
    footer: bytes


def _u32be(n: int) -> bytes:
    if not (0 <= int(n) <= 0xFFFFFFFF):
        raise ValueError(f"u32 out of range: {n!r}")
    return int(n).to_bytes(4, byteorder="big", signed=False)


def _read_u32be(b: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(b):
        raise ValueError(f"u32 read out of bounds: offset={offset} len={len(b)}")
    return int.from_bytes(b[offset : offset + 4], byteorder="big", signed=False)


def read_gil_container(path: Path) -> GilContainer:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    data = p.read_bytes()
    if len(data) < 20:
        raise ValueError(f"invalid gil file: too small: {str(p)!r}")

    header = data[:20]
    total_size = _read_u32be(header, 0)
    payload_size = _read_u32be(header, 16)
    if int(total_size) != int(payload_size) + 20:
        raise ValueError(
            f"gil header size mismatch: total_size={total_size} payload_size={payload_size} path={str(p)!r}"
        )
    end = 20 + int(payload_size)
    if end > len(data):
        raise ValueError(
            f"gil payload exceeds file length: payload_end={end} file_len={len(data)} path={str(p)!r}"
        )
    payload = data[20:end]
    footer = data[end:]
    return GilContainer(header=header, payload=payload, footer=footer)


def build_gil_bytes_from_container(*, base: GilContainer, new_payload: bytes) -> bytes:
    header = bytearray(base.header)
    payload_size = int(len(new_payload))
    total_size = int(payload_size) + 20
    header[0:4] = _u32be(total_size)
    header[16:20] = _u32be(payload_size)
    return bytes(header) + bytes(new_payload) + base.footer


# -------------------- Protobuf-like codec (numeric-key dump style) --------------------


def _read_varint(data: bytes, offset: int) -> Tuple[int, int]:
    if offset < 0 or offset >= len(data):
        raise ValueError(f"varint offset out of bounds: {offset} len={len(data)}")
    result = 0
    shift = 0
    i = offset
    while i < len(data):
        b = data[i]
        result |= (b & 0x7F) << shift
        i += 1
        if (b & 0x80) == 0:
            return int(result), int(i)
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")
    raise ValueError("unexpected EOF while reading varint")


def _encode_varint(value: int) -> bytes:
    v = int(value)
    if v < 0:
        # 本工具只支持 unsigned varint（GIL 里大量使用无符号/枚举/长度）。
        raise ValueError(f"negative varint not supported: {value!r}")
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
            continue
        out.append(b)
        break
    return bytes(out)


def _is_reasonably_printable_utf8(data: bytes) -> bool:
    if not data:
        return False
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    for ch in text:
        code = ord(ch)
        if ch in ("\t", "\n", "\r"):
            continue
        if code < 0x20:
            return False
    return True


Decoded = Union[int, str, bytes, Dict[str, Any], List[Any]]


def decode_message(data: bytes) -> Dict[str, Any]:
    msg, end = _decode_message_internal(data=data, offset=0, end=len(data), depth=0)
    if end != len(data):
        raise ValueError(f"message did not consume all bytes: consumed={end} total={len(data)}")
    return msg


def _decode_message_internal(*, data: bytes, offset: int, end: int, depth: int) -> Tuple[Dict[str, Any], int]:
    if depth > 32:
        raise ValueError("message nesting too deep")
    out: Dict[str, Any] = {}
    i = int(offset)
    while i < int(end):
        key, i2 = _read_varint(data, i)
        i = i2
        field_no = int(key) >> 3
        wire = int(key) & 0x7
        if field_no <= 0:
            raise ValueError(f"invalid field number: {field_no}")
        k = str(field_no)

        if wire == 0:
            v, i = _read_varint(data, i)
            _append_field_value(out, k, int(v))
            continue

        if wire == 1:
            if i + 8 > end:
                raise ValueError("unexpected EOF in fixed64")
            raw = data[i : i + 8]
            i += 8
            _append_field_value(out, k, raw)  # 保留 bytes（不强转 double）
            continue

        if wire == 5:
            if i + 4 > end:
                raise ValueError("unexpected EOF in fixed32")
            raw = data[i : i + 4]
            i += 4
            _append_field_value(out, k, raw)  # 保留 bytes（不强转 float）
            continue

        if wire == 2:
            length, i = _read_varint(data, i)
            ln = int(length)
            if ln < 0:
                raise ValueError("negative length")
            if i + ln > end:
                raise ValueError("unexpected EOF in length-delimited")
            raw = data[i : i + ln]
            i += ln

            # 优先尝试嵌套 message（需要完整消费）
            nested: Any = None
            if raw:
                try:
                    nested_msg, consumed = _decode_message_internal(data=raw, offset=0, end=len(raw), depth=depth + 1)
                    if consumed == len(raw) and nested_msg:
                        nested = nested_msg
                except Exception:
                    nested = None

            if isinstance(nested, dict):
                _append_field_value(out, k, nested)
                continue

            if _is_reasonably_printable_utf8(raw):
                _append_field_value(out, k, raw.decode("utf-8", errors="strict"))
                continue

            _append_field_value(out, k, raw)
            continue

        raise ValueError(f"unsupported wire type: {wire}")

    return out, int(i)


def _append_field_value(obj: Dict[str, Any], key: str, value: Any) -> None:
    existing = obj.get(key)
    if existing is None:
        obj[key] = value
        return
    if isinstance(existing, list):
        existing.append(value)
        return
    obj[key] = [existing, value]


def encode_message(msg: Dict[str, Any]) -> bytes:
    out = bytearray()
    # field order：按字段号升序；repeated 保持列表顺序
    items: List[Tuple[int, str]] = []
    for k in msg.keys():
        if not str(k).isdigit():
            continue
        items.append((int(k), str(k)))
    items.sort(key=lambda t: t[0])

    for field_no, k in items:
        value = msg.get(k)
        if isinstance(value, list):
            for item in value:
                out.extend(_encode_field(field_no, item))
            continue
        out.extend(_encode_field(field_no, value))
    return bytes(out)


def _encode_field(field_no: int, value: Any) -> bytes:
    fn = int(field_no)
    if fn <= 0:
        raise ValueError(f"invalid field number: {field_no}")

    # int -> varint
    if isinstance(value, bool):
        return _encode_key(fn, 0) + _encode_varint(1 if value else 0)
    if isinstance(value, int):
        return _encode_key(fn, 0) + _encode_varint(int(value))

    # str -> length-delimited utf8
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return _encode_key(fn, 2) + _encode_varint(len(raw)) + raw

    # bytes -> fixed32/fixed64 or length-delimited（默认按 length-delimited）
    if isinstance(value, (bytes, bytearray)):
        rawb = bytes(value)
        return _encode_key(fn, 2) + _encode_varint(len(rawb)) + rawb

    # dict -> nested message (length-delimited)
    if isinstance(value, dict):
        raw = encode_message(dict(value))
        return _encode_key(fn, 2) + _encode_varint(len(raw)) + raw

    raise ValueError(f"unsupported value type for field {field_no}: {type(value).__name__}")


def _encode_key(field_no: int, wire_type: int) -> bytes:
    key = (int(field_no) << 3) | int(wire_type)
    return _encode_varint(int(key))


def decode_packed_varints(data: bytes) -> List[int]:
    """解析 packed repeated varint 列表（用于玩家模板的生效玩家等字段）。"""
    out: List[int] = []
    i = 0
    while i < len(data):
        v, i2 = _read_varint(data, i)
        out.append(int(v))
        i = i2
    return out


def encode_packed_varints(values: List[int]) -> bytes:
    out = bytearray()
    for v in values:
        out.extend(_encode_varint(int(v)))
    return bytes(out)

