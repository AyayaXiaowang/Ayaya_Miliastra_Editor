from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file
from ugc_file_tools.gia.varbase_semantics import as_list, get_field, get_message_field, get_message_node
from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
    read_gil_payload_bytes,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, decode_varint, encode_varint


@dataclass(frozen=True, slots=True)
class LenField:
    """
    protobuf-like length-delimited 字段定位信息（用于 bytes 级 patch）。

    字段含义对齐 genshin-ts injector 的 `LenField`：
    - depth/p0..p5：长度分隔树路径（例如 10.1.1）
    - len_offset/len_size：length varint 在原 payload 中的位置与字节数
    - data_start/data_end：payload bytes 段的范围（不含 length varint）
    """

    field: int
    depth: int
    p0: int
    p1: int
    p2: int
    p3: int
    p4: int
    p5: int
    len_offset: int
    len_size: int
    data_start: int
    data_end: int


@dataclass(frozen=True, slots=True)
class GilNodeGraphInjectReport:
    """
    注入结果报告（用于 UI/CLI 展示）。
    """

    source_gia_file: str
    target_gil_file: str
    output_gil_file: str
    graph_id_int: int
    mode: str  # "replace"
    backup_file: str
    old_payload_size: int
    new_payload_size: int


def _read_varint_or_raise(buf: bytes, offset: int, end: int) -> Tuple[int, int]:
    value, next_offset, ok = decode_varint(buf, offset, end)
    if not ok:
        raise ValueError("invalid varint")
    return int(value), int(next_offset)


def _parse_len_fields(
    buf: bytes,
    start: int,
    end: int,
    depth: int,
    p0: int,
    p1: int,
    p2: int,
    p3: int,
    p4: int,
    p5: int,
    out: List[LenField],
    *,
    node_graph_blob_fields: Optional[List[LenField]] = None,
) -> None:
    """
    扫描一段 message，收集所有 wire_type=2 的 LenField，并递归进入其 payload。

    - 与 genshin-ts 的 `parseMessage(...)` 对齐：最多维护 6 层路径 p0..p5
    - 为避免扫描 node graph 内部海量字段，调用方可只使用 `node_graph_blob_fields` 来筛选 10.1.1。
    """

    offset = int(start)
    while offset < int(end):
        # 兼容 genshin-ts：当遇到非 protobuf-like 的片段时，不抛错，直接终止该分支解析。
        key_value, next_offset, ok = decode_varint(buf, offset, end)
        if not ok:
            return
        key = int(key_value)
        offset = int(next_offset)
        field = int(key) >> 3
        wire = int(key) & 0x07

        if wire == 0:
            _v, next_offset2, ok2 = decode_varint(buf, offset, end)
            if not ok2:
                return
            offset = int(next_offset2)
            continue
        if wire == 1:
            offset += 8
            continue
        if wire == 5:
            offset += 4
            continue
        if wire != 2:
            # group 等历史 wire_type 不支持
            return

        # wire == 2
        len_offset = int(offset)
        length_value, next_offset3, ok3 = decode_varint(buf, offset, end)
        if not ok3:
            return
        length = int(length_value)
        data_start = int(next_offset3)
        data_end = int(data_start + int(length))
        if int(length) < 0 or data_end > int(end):
            return

        next_depth = int(depth + 1)
        np0, np1, np2, np3, np4, np5 = int(p0), int(p1), int(p2), int(p3), int(p4), int(p5)
        if depth == 0:
            np0 = int(field)
        elif depth == 1:
            np1 = int(field)
        elif depth == 2:
            np2 = int(field)
        elif depth == 3:
            np3 = int(field)
        elif depth == 4:
            np4 = int(field)
        elif depth == 5:
            np5 = int(field)

        entry = LenField(
            field=int(field),
            depth=int(next_depth),
            p0=int(np0),
            p1=int(np1),
            p2=int(np2),
            p3=int(np3),
            p4=int(np4),
            p5=int(np5),
            len_offset=int(len_offset),
            len_size=int(data_start - len_offset),
            data_start=int(data_start),
            data_end=int(data_end),
        )
        out.append(entry)

        # NodeGraph blob 字段：10.1.1（对齐 genshin-ts injector 的筛选）
        if (
            node_graph_blob_fields is not None
            and next_depth == 3
            and np0 == 10
            and np1 == 1
            and np2 == 1
        ):
            node_graph_blob_fields.append(entry)

        # 递归进入下一层（最多 6 层路径即可）
        if int(length) > 0 and int(depth) < 6:
            _parse_len_fields(
                buf,
                data_start,
                data_end,
                next_depth,
                np0,
                np1,
                np2,
                np3,
                np4,
                np5,
                out,
                node_graph_blob_fields=node_graph_blob_fields,
            )

        offset = int(data_end)


def parse_len_fields(
    buf: bytes,
    start: int,
    end: int,
    depth: int,
    p0: int,
    p1: int,
    p2: int,
    p3: int,
    p4: int,
    p5: int,
    out: List[LenField],
    *,
    node_graph_blob_fields: Optional[List[LenField]] = None,
) -> None:
    """Public API: wrapper for `_parse_len_fields` (used by read-only scanners)."""
    _parse_len_fields(
        buf,
        start,
        end,
        depth,
        p0,
        p1,
        p2,
        p3,
        p4,
        p5,
        out,
        node_graph_blob_fields=node_graph_blob_fields,
    )


def _try_read_node_graph_id_and_type(node_graph_bytes: bytes) -> Optional[Tuple[int, Optional[int]]]:
    """
    ultra-fast signature（移植自 genshin-ts）：
    - NodeGraph 以 field 1（id message，wire=2）开头：key varint == 10
    - id message 内：field 2 为 type，field 5 为 id
    """

    b = bytes(node_graph_bytes or b"")
    if not b:
        return None

    key, next_offset, ok = decode_varint(b, 0, len(b))
    if not ok or int(key) != 10:
        return None
    length, next_offset2, ok2 = decode_varint(b, int(next_offset), len(b))
    if not ok2:
        return None
    ln = int(length)
    start = int(next_offset2)
    end = int(start + ln)
    if ln <= 0 or end > len(b):
        return None

    graph_id: Optional[int] = None
    graph_type: Optional[int] = None

    off = int(start)
    while off < end:
        k, off2, ok3 = decode_varint(b, off, end)
        if not ok3:
            break
        off = int(off2)
        field = int(k) >> 3
        wire = int(k) & 0x07

        if wire == 0:
            v, off3, ok4 = decode_varint(b, off, end)
            if not ok4:
                break
            off = int(off3)
            if field == 2:
                graph_type = int(v)
            if field == 5:
                graph_id = int(v)
                break
            continue

        if wire == 1:
            off += 8
            continue
        if wire == 5:
            off += 4
            continue
        if wire == 2:
            lv, off3, ok4 = decode_varint(b, off, end)
            if not ok4:
                break
            off = int(off3 + int(lv))
            continue
        break

    if isinstance(graph_id, int):
        gid = int(graph_id)
        # 经验：真源 NodeGraph id 基本都在 0x40000000 段（>= 1e9）。
        # 用阈值过滤掉“碰巧符合字节形状但并非 NodeGraph”的误匹配。
        if gid < 1_000_000_000:
            return None
        # NodeGraph.Id.type 常见取值：20000(entity) / 20003(status) / 20004(class) / 20005(item)
        if isinstance(graph_type, int) and int(graph_type) not in {20000, 20003, 20004, 20005}:
            return None
        return gid, int(graph_type) if isinstance(graph_type, int) else None
    return None


def _read_node_graph_summary(node_graph_bytes: bytes) -> Tuple[str, int]:
    """
    用最小递归深度读取 NodeGraph 的：
    - name（field 2）
    - node_count（field 3 的 repeated 长度）
    """

    fields, consumed = decode_message_to_field_map(
        data_bytes=bytes(node_graph_bytes),
        start_offset=0,
        end_offset=len(node_graph_bytes),
        remaining_depth=1,
    )
    if consumed != len(node_graph_bytes):
        raise ValueError("node graph protobuf did not consume all bytes")

    name_node = fields.get("field_2")
    name = ""
    if isinstance(name_node, dict):
        utf8 = name_node.get("utf8")
        if isinstance(utf8, str):
            name = str(utf8)

    nodes = fields.get("field_3")
    node_count = len(as_list(nodes))
    return str(name), int(node_count)


def extract_node_graph_bytes_from_gia(
    gia_file_path: Path,
    *,
    expected_graph_id_int: int | None,
    check_gia_header: bool,
) -> bytes:
    """
    从 `.gia`（AssetBundle）中提取 NodeGraph 的原始 protobuf bytes（不含 `.gia` 容器头尾）。

    说明：
    - 仅解码到 GraphUnitWrapper/NodeGraphContainer 所需的层级：remaining_depth=3
    - 优先返回 NodeGraph 字段的 raw_hex（保持 bytes 层面与导出产物一致）
    - 若当前层级被 decode 成 message（没有 raw_hex），则将 message 重编码为 bytes（语义等价）
    """

    gia_file_path = Path(gia_file_path).resolve()
    if check_gia_header:
        validate_gia_container_file(gia_file_path)

    proto_bytes = unwrap_gia_container(gia_file_path, check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        # 需要至少覆盖到：Root -> GraphUnit -> wrapper(13) -> inner(1) -> node_graph(1)
        # 这里给到 4，并仍允许后续按 raw_hex/message 两种形态兜底，避免因深度不足漏掉 NodeGraph。
        remaining_depth=4,
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            f"gia protobuf did not consume all bytes: consumed={consumed} total={len(proto_bytes)} file={str(gia_file_path)!r}"
        )

    graph_units: List[object] = list(as_list(root_fields.get("field_1"))) + list(as_list(root_fields.get("field_2")))
    matched: List[Tuple[int, bytes]] = []
    for graph_unit in graph_units:
        unit_msg = get_message_node(graph_unit)
        if unit_msg is None:
            # depth 不足时可能只拿到 raw_hex：此处尝试解开一层 GraphUnit message
            if isinstance(graph_unit, dict) and isinstance(graph_unit.get("raw_hex"), str):
                raw_hex = str(graph_unit.get("raw_hex") or "")
                raw_bytes = bytes.fromhex(raw_hex) if raw_hex else b""
                unit_msg, consumed2 = decode_message_to_field_map(
                    data_bytes=raw_bytes,
                    start_offset=0,
                    end_offset=len(raw_bytes),
                    remaining_depth=4,
                )
                if consumed2 != len(raw_bytes):
                    continue
            else:
                continue

        wrapper = get_message_field(unit_msg, 13)
        if wrapper is None:
            continue

        inner = get_message_field(wrapper, 1)
        if inner is None:
            # depth 较浅时 inner 可能只保留 raw_hex：这里解开一层 container(inner)
            inner_node = get_field(wrapper, 1)
            if not isinstance(inner_node, dict):
                continue
            inner_raw_hex = inner_node.get("raw_hex")
            if not isinstance(inner_raw_hex, str):
                continue
            inner_raw_bytes = bytes.fromhex(inner_raw_hex) if inner_raw_hex else b""
            inner, consumed3 = decode_message_to_field_map(
                data_bytes=inner_raw_bytes,
                start_offset=0,
                end_offset=len(inner_raw_bytes),
                remaining_depth=2,
            )
            if consumed3 != len(inner_raw_bytes):
                continue

        node_graph_node = get_field(inner, 1)
        if not isinstance(node_graph_node, dict):
            continue
        node_graph_bytes: bytes | None = None

        raw_hex = node_graph_node.get("raw_hex")
        if isinstance(raw_hex, str):
            node_graph_bytes = bytes.fromhex(raw_hex) if raw_hex else b""

        # 有些情况下 decode 会把该字段识别为嵌套 message（不提供 raw_hex）
        if node_graph_bytes is None:
            nested = node_graph_node.get("message")
            if isinstance(nested, dict):
                from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
                from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message

                numeric_message = decoded_field_map_to_numeric_message(nested, prefer_raw_hex_for_utf8=True)
                node_graph_bytes = encode_message(dict(numeric_message))

        if node_graph_bytes is None:
            continue

        fast = _try_read_node_graph_id_and_type(node_graph_bytes)
        if fast is None:
            continue
        gid, _gtype = fast
        if expected_graph_id_int is not None:
            if int(gid) != int(expected_graph_id_int):
                continue
            return bytes(node_graph_bytes)
        matched.append((int(gid), bytes(node_graph_bytes)))

    if expected_graph_id_int is None:
        if not matched:
            raise ValueError(f"NodeGraph not found in gia: file={str(gia_file_path)!r}")
        # 导出产物通常是“单图 .gia”，此处要求唯一，避免误注入到错误图
        ids = sorted({int(gid) for gid, _ in matched})
        if len(ids) != 1:
            preview = ", ".join(str(x) for x in ids[:12])
            suffix = "..." if len(ids) > 12 else ""
            raise ValueError(
                f"multiple NodeGraphs found in gia; expected a single graph: file={str(gia_file_path)!r} ids=[{preview}{suffix}]"
            )
        return bytes(matched[0][1])

    raise ValueError(
        f"NodeGraph not found in gia: file={str(gia_file_path)!r} expected_graph_id_int={expected_graph_id_int!r}"
    )


def _rewrite_node_graph_id_and_type(
    node_graph_bytes: bytes,
    *,
    graph_id_int: int,
    graph_type_int: int | None,
) -> bytes:
    """
    将 NodeGraph bytes 中的 `id.id` / `id.type` 改写为目标值（对齐 genshin-ts injector 的行为）。

    说明：
    - field 1：NodeGraph.Id message（wire=2）
      - field 2：type
      - field 5：id
    - 使用本仓库统一的 protobuf-like codec 进行“语义级重编码”（不追求字节级完全一致）。
    """
    from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
    from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message

    b = bytes(node_graph_bytes or b"")
    if not b:
        raise ValueError("node graph bytes empty")

    fields_map, consumed = decode_message_to_field_map(
        data_bytes=b,
        start_offset=0,
        end_offset=len(b),
        remaining_depth=2,
    )
    if consumed != len(b):
        raise ValueError("node graph protobuf did not consume all bytes")

    numeric = decoded_field_map_to_numeric_message(fields_map, prefer_raw_hex_for_utf8=True)
    id_msg = numeric.get("1")
    if not isinstance(id_msg, dict):
        raise ValueError("node graph missing id message (field 1)")

    id_msg["5"] = int(graph_id_int)
    if graph_type_int is not None:
        id_msg["2"] = int(graph_type_int)
    numeric["1"] = id_msg

    return bytes(encode_message(dict(numeric)))


def _find_node_graph_field_by_id(
    *,
    payload: bytes,
    node_graph_blob_fields: Sequence[LenField],
    all_len_fields: Sequence[LenField],
    target_graph_id_int: int,
) -> Tuple[LenField | None, List[int]]:
    """
    在 `.gil` payload 中查找指定 graph_id 的 NodeGraph bytes 字段。

    策略：
    - 先扫 10.1.1（node_graph_blob_fields）：性能更好、误判更少
    - 若没找到，再回退扫 all_len_fields（兼容部分真源路径差异）

    返回：
    - (target_field or None, found_ids_in_blob_fields)
    """
    target_id = int(target_graph_id_int)
    found_ids_blob: List[int] = []

    for f in node_graph_blob_fields:
        blob = payload[int(f.data_start) : int(f.data_end)]
        fast = _try_read_node_graph_id_and_type(blob)
        if fast is None:
            continue
        gid, _gtype = fast
        found_ids_blob.append(int(gid))
        if int(gid) == target_id:
            return f, found_ids_blob

    # fallback: scan all length-delimited fields
    for f in all_len_fields:
        blob = payload[int(f.data_start) : int(f.data_end)]
        fast = _try_read_node_graph_id_and_type(blob)
        if fast is None:
            continue
        gid, _gtype = fast
        if int(gid) == target_id:
            return f, found_ids_blob

    return None, found_ids_blob


def find_node_graph_field_by_id(
    *,
    payload: bytes,
    node_graph_blob_fields: Sequence[LenField],
    all_len_fields: Sequence[LenField],
    target_graph_id_int: int,
) -> Tuple[LenField | None, List[int]]:
    """Public API: locate the NodeGraph blob field for a target graph_id_int."""
    return _find_node_graph_field_by_id(
        payload=payload,
        node_graph_blob_fields=node_graph_blob_fields,
        all_len_fields=all_len_fields,
        target_graph_id_int=int(target_graph_id_int),
    )


@dataclass(frozen=True, slots=True)
class _Patch:
    start: int
    end: int
    replacement: bytes


def _apply_patches(payload: bytes, patches: Sequence[_Patch]) -> bytes:
    src = bytes(payload)
    sorted_patches = sorted(list(patches), key=lambda p: int(p.start), reverse=True)
    parts: List[bytes] = []
    last_end = len(src)
    for p in sorted_patches:
        if int(p.end) < int(last_end):
            parts.append(src[int(p.end) : int(last_end)])
        parts.append(bytes(p.replacement))
        last_end = int(p.start)
    if last_end > 0:
        parts.append(src[:last_end])
    parts.reverse()
    return b"".join(parts)


def _find_ancestor_fields(fields: Sequence[LenField], target: LenField) -> List[LenField]:
    ancestors = [
        f
        for f in fields
        if f is not target and int(f.data_start) <= int(target.len_offset) and int(f.data_end) >= int(target.data_end)
    ]
    ancestors.sort(key=lambda f: int(f.data_end - f.data_start))
    return ancestors


def _apply_replacement(payload: bytes, fields: Sequence[LenField], *, target: LenField, new_data: bytes) -> bytes:
    old_len = int(target.data_end - target.data_start)
    new_len = int(len(new_data))
    new_len_bytes = bytes(encode_varint(int(new_len)))
    delta = int(new_len - old_len + (len(new_len_bytes) - int(target.len_size)))

    patches: List[_Patch] = [
        _Patch(
            start=int(target.len_offset),
            end=int(target.data_end),
            replacement=new_len_bytes + bytes(new_data),
        )
    ]

    for ancestor in _find_ancestor_fields(fields, target):
        old_ancestor_len = int(ancestor.data_end - ancestor.data_start)
        new_ancestor_len = int(old_ancestor_len + delta)
        if new_ancestor_len < 0:
            raise ValueError("ancestor length underflow")
        new_ancestor_len_bytes = bytes(encode_varint(int(new_ancestor_len)))
        ancestor_len_size_delta = int(len(new_ancestor_len_bytes) - int(ancestor.len_size))
        patches.append(
            _Patch(
                start=int(ancestor.len_offset),
                end=int(ancestor.data_start),
                replacement=new_ancestor_len_bytes,
            )
        )
        delta += ancestor_len_size_delta

    return _apply_patches(payload, patches)


def inject_gia_into_gil_node_graph(
    *,
    source_gia_file: Path,
    target_gil_file: Path,
    output_gil_file: Path | None,
    target_graph_id_int: int,
    check_gia_header: bool = False,
    skip_non_empty_check: bool = False,
    create_backup: bool = True,
    rewrite_graph_id_and_type: bool = True,
) -> GilNodeGraphInjectReport:
    """
    将 `.gia` 中的 NodeGraph 注入到目标 `.gil`（替换对应 graph_id 的 10.1.1 blob）。

    重要约束：
    - 这是“文件级注入”（patch `.gil` bytes），不是进程注入。
    - 默认启用安全检查：目标图若非空且 name 不以 `_GSTS` 开头，则拒绝覆盖。
    """

    source_gia_file = Path(source_gia_file).resolve()
    target_gil_file = Path(target_gil_file).resolve()
    out_file = Path(output_gil_file).resolve() if output_gil_file is not None else Path(target_gil_file).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    target_graph_id_int2 = int(target_graph_id_int)
    # 对齐 genshin-ts：允许 `.gia` 内的图 ID 与目标 `.gil` 占位图不同，必要时可改号后注入。
    node_graph_bytes = extract_node_graph_bytes_from_gia(
        source_gia_file,
        expected_graph_id_int=None,
        check_gia_header=bool(check_gia_header),
    )
    fast = _try_read_node_graph_id_and_type(node_graph_bytes)
    if fast is None:
        raise ValueError("source NodeGraph bytes invalid")
    source_graph_id_int = int(fast[0])
    source_graph_type_int = int(fast[1]) if isinstance(fast[1], int) else None

    container_spec = read_gil_container_spec(target_gil_file)
    payload = read_gil_payload_bytes(target_gil_file)

    all_len_fields: List[LenField] = []
    node_graph_blob_fields: List[LenField] = []
    _parse_len_fields(
        payload,
        0,
        len(payload),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        all_len_fields,
        node_graph_blob_fields=node_graph_blob_fields,
    )

    # 兼容：部分真源 `.gil` 的 NodeGraph bytes 不在固定的 10.1.1 路径上。
    # 这里优先扫 10.1.1，没找到目标 id 再回退全量扫，避免出现“判定包含但注入找不到”的不一致。
    target_field, found_ids_blob = _find_node_graph_field_by_id(
        payload=payload,
        node_graph_blob_fields=node_graph_blob_fields,
        all_len_fields=all_len_fields,
        target_graph_id_int=target_graph_id_int2,
    )
    existing_type: Optional[int] = None
    if target_field is not None:
        old_blob = payload[int(target_field.data_start) : int(target_field.data_end)]
        fast_old = _try_read_node_graph_id_and_type(old_blob)
        existing_type = int(fast_old[1]) if (fast_old is not None and isinstance(fast_old[1], int)) else None

    if target_field is None:
        # 提供更可读的诊断信息（不吞错，直接抛）
        found_ids = sorted(set(int(x) for x in found_ids_blob))
        preview = ", ".join(str(x) for x in found_ids[:12])
        suffix = "..." if len(found_ids) > 12 else ""
        raise ValueError(
            "target NodeGraph not found in gil: "
            f"graph_id_int={target_graph_id_int2} "
            f"target_gil_file={str(target_gil_file)!r} "
            f"found_in_10_1_1={len(found_ids)} [{preview}{suffix}]"
        )

    if not bool(skip_non_empty_check):
        old_blob = payload[int(target_field.data_start) : int(target_field.data_end)]
        name, node_count = _read_node_graph_summary(old_blob)
        if int(node_count) > 0 and not str(name).startswith("_GSTS"):
            raise ValueError(
                f"refuse to replace non-empty NodeGraph whose name not _GSTS*: graph_id={target_graph_id_int2} name={name!r} node_count={node_count}"
            )

    # 对齐 genshin-ts：注入前将 incoming NodeGraph 的 id/type 对齐到目标图（避免“没有人家的号”的问题）。
    new_node_graph_bytes = bytes(node_graph_bytes)
    if bool(rewrite_graph_id_and_type):
        desired_type: int | None = int(existing_type) if existing_type is not None else source_graph_type_int
        if source_graph_id_int != target_graph_id_int2 or (
            desired_type is not None and source_graph_type_int is not None and int(desired_type) != int(source_graph_type_int)
        ):
            new_node_graph_bytes = _rewrite_node_graph_id_and_type(
                new_node_graph_bytes,
                graph_id_int=int(target_graph_id_int2),
                graph_type_int=int(desired_type) if desired_type is not None else None,
            )

    new_payload = _apply_replacement(payload, all_len_fields, target=target_field, new_data=new_node_graph_bytes)
    out_bytes = build_gil_file_bytes_from_payload(payload_bytes=new_payload, container_spec=container_spec)

    backup_path = ""
    if bool(create_backup) and out_file.resolve() == target_gil_file.resolve():
        stamp = int(time.time() * 1000)
        backup = (target_gil_file.parent / f"{target_gil_file.stem}.before_inject_{stamp}.gil").resolve()
        backup.write_bytes(target_gil_file.read_bytes())
        backup_path = str(backup)

    out_file.write_bytes(out_bytes)

    return GilNodeGraphInjectReport(
        source_gia_file=str(source_gia_file),
        target_gil_file=str(target_gil_file),
        output_gil_file=str(out_file),
        graph_id_int=int(target_graph_id_int2),
        mode="replace",
        backup_file=str(backup_path),
        old_payload_size=int(len(payload)),
        new_payload_size=int(len(new_payload)),
    )

