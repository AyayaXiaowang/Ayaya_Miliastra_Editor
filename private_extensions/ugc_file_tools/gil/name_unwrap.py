from __future__ import annotations

"""
name_unwrap.py

用途：
- 将 dump-json / numeric-message 树里出现的“名字字段”归一化为可读文本，用于：
  - `component_key:` / `entity_key:` 回填识别
  - base `.gil` 冲突扫描（模板/实例同名检查）
  - 导出中心候选列表展示

背景（典型 bug 现象）：
- 某些 `.gil` 样本里，名称并不是直接存成 utf8 string，而是存成“嵌套 message 的 bytes”：
  - wire: 0x0A + <len(varint)> + <utf8_bytes>
- protobuf-like lossless 解码为了避免 strip/sanitize 导致 payload 漂移，会把它保持为 raw bytes，
  在 dump-json 侧表现为：`"<binary_data> 0A .."`。
- 若上层直接拿这个字符串当作名字，会导致：
  - `飞机头` 等元件存在于 `.gil`，但识别表里匹配不到
  - 候选列表出现大量 `<binary_data> ...` 噪音项

约束：
- 不使用 try/except；本模块实现均为“无异常路径优先”的纯函数。
"""

from typing import Final, Optional

from ugc_file_tools.gil_dump_codec.protobuf_like import decode_varint

_BINARY_DATA_PREFIX: Final[str] = "<binary_data>"
_HEX_DIGITS: Final[set[str]] = set("0123456789abcdefABCDEF")


def _parse_binary_data_hex_text_no_throw(text: str) -> Optional[bytes]:
    """
    解析 dump-json 的 `<binary_data> ..` 文本为原始 bytes。

    - 返回 None：表示不是合法的 `<binary_data>` 形态（调用方应回退为原文）。
    - 返回 b""：表示 empty bytes（`"<binary_data> "`）。
    """
    s = str(text or "")
    if not s.startswith(_BINARY_DATA_PREFIX):
        return None

    hex_text = s[len(_BINARY_DATA_PREFIX) :].strip()
    compact = "".join(ch for ch in hex_text if ch not in " \n\r\t")
    if compact == "":
        return b""
    if len(compact) % 2 != 0:
        return None
    for ch in compact:
        if ch not in _HEX_DIGITS:
            return None

    out = bytearray()
    for i in range(0, len(compact), 2):
        # safe: already validated two hex digits
        out.append(int(compact[i : i + 2], 16))
    return bytes(out)


def _strip_c_string_terminator(text: str) -> str:
    s = str(text or "")
    if "\x00" in s:
        s = s.split("\x00", 1)[0]
    return str(s)


def _try_unwrap_single_field1_string_message_bytes(raw: bytes) -> Optional[str]:
    """
    若 raw bytes 恰好是 “field_1 的 length-delimited string” 的完整 wire 编码，则解出字符串：
      raw == 0x0A + <len(varint)> + <utf8_bytes>

    注意：
    - 这里刻意要求 end == len(raw)，避免把复杂 message 误当作“名字”解包。
    """
    if not raw:
        return None
    if raw[0] != 0x0A:
        return None

    length, next_offset, ok = decode_varint(raw, 1, len(raw))
    if not ok:
        return None

    end = int(next_offset) + int(length)
    if end != len(raw):
        return None

    inner = bytes(raw[next_offset:end])
    decoded = inner.decode("utf-8", errors="replace")
    if "\ufffd" in decoded:
        return None
    decoded = _strip_c_string_terminator(decoded)
    out = str(decoded).strip()
    return out if out != "" else None


def normalize_dump_json_name_text(text: str) -> str:
    """
    将“名字字段”的 dump-json 表示归一化为可读字符串。

    输入可能是：
    - 普通字符串：`"飞机头"`
    - `<binary_data>`：`"<binary_data> 0A 09 E9 A3 9E E6 9C BA E5 A4 B4"`
    - 少见：嵌套 message bytes 被误判为 utf8，表现为 `"\n\t飞机头"` 或类似控制前缀
    """
    s0 = _strip_c_string_terminator(str(text or ""))
    if s0 == "":
        return ""

    # --- `<binary_data> ..` ---
    if s0.startswith(_BINARY_DATA_PREFIX):
        raw = _parse_binary_data_hex_text_no_throw(s0)
        if raw is None:
            return str(s0).strip()
        if raw == b"":
            return ""

        unwrapped = _try_unwrap_single_field1_string_message_bytes(raw)
        if unwrapped is not None:
            return str(unwrapped)

        # fallback：按 utf8 best-effort 解码（名字字段通常可读）
        decoded = raw.decode("utf-8", errors="replace")
        decoded = _strip_c_string_terminator(decoded)
        return str(decoded).strip()

    # --- 普通字符串（可能包含“嵌套 message bytes 的控制前缀”） ---
    s = str(s0).strip()
    if s == "":
        return ""

    raw2 = s.encode("utf-8")
    unwrapped2 = _try_unwrap_single_field1_string_message_bytes(raw2)
    if unwrapped2 is not None:
        return str(unwrapped2)

    return str(s)


__all__ = ["normalize_dump_json_name_text"]

