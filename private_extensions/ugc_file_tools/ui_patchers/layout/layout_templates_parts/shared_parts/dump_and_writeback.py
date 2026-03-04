from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
    read_gil_payload_bytes,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_field_map,
    encode_tag,
    encode_message,
    parse_binary_data_hex_text,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import (
    build_length_delimited_value_raw,
    parse_tag_raw,
    split_length_delimited_value_raw,
    upsert_varint_field,
)


def dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    """
    Public API (no leading underscores).

    Import policy: cross-module imports must not import underscored private names.
    """
    return _dump_gil_to_raw_json_object(Path(input_gil_file_path).resolve())


def _write_back_modified_gil_by_reencoding_payload(
    *,
    raw_dump_object: Dict[str, Any],
    input_gil_path: Path,
    output_gil_path: Path,
) -> None:
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")

    # === 写回策略（关键）===
    # 目标：尽量保留输入 `.gil` 的 wire-level 原始字节，仅对“确实发生语义变化”的区域做最小替换，
    # 避免某些真源存档包含的“非规范 varint 编码/特殊写法”在全量重编码时被规范化，从而导致游戏拒识。
    #
    # 做法：
    # - 以 wire-level chunk 拆分 payload_root（tag_raw + value_raw），默认原样保留；
    # - 仅 patch：
    #   - root field_40（修改时间，varint）
    #   - root field_9（UI 段：优先在 field_9 内按 record 列表做最小替换）
    #   - root field_5（实例/实体段：只替换 root4/5/1 中“发生语义变化”的 entry message）
    #
    # “是否变化”的判定依据：
    # - 对比 baseline（对输入 payload 做同口径 lossless dump 得到的 numeric_message）与本次修改后的 payload_root，
    #   仅当某个 entry/record 的 dict 真正发生变化时才替换；避免因为“原始 bytes 非规范”导致 encode 与原 bytes 不同而误替换。
    input_path = Path(input_gil_path).resolve()
    original_payload_bytes = read_gil_payload_bytes(input_path)
    baseline_field_map, baseline_consumed = decode_message_to_field_map(
        data_bytes=original_payload_bytes,
        start_offset=0,
        end_offset=len(original_payload_bytes),
        remaining_depth=32,
    )
    if baseline_consumed != len(original_payload_bytes):
        raise ValueError(
            "gil payload 未能完整解码为单个 message（存在 trailing bytes）："
            f"consumed={baseline_consumed}, total={len(original_payload_bytes)}"
        )
    baseline_payload_root = decoded_field_map_to_numeric_message(baseline_field_map, prefer_raw_hex_for_utf8=True)
    if not isinstance(baseline_payload_root, dict):
        raise TypeError("decoded baseline payload_root is not dict")

    root_chunks, consumed_offset = decode_message_to_wire_chunks(
        data_bytes=original_payload_bytes,
        start_offset=0,
        end_offset=len(original_payload_bytes),
    )
    if consumed_offset != len(original_payload_bytes):
        raise ValueError(
            "wire decode 未能完整消费 payload：" f"consumed={consumed_offset}, total={len(original_payload_bytes)}"
        )

    # 1) 更新修改时间（field_40）
    payload_root["40"] = int(time.time())
    root_chunks = upsert_varint_field(root_chunks, field_number=40, new_value=int(payload_root["40"]))

    # 2) patch UI 段（root field_9）
    baseline_node9 = baseline_payload_root.get("9")
    node9 = payload_root.get("9")
    # 兼容：极简/空存档可能缺失 UI 段（baseline_node9=None），但本次写回需要追加 node9(dict)。
    # 此处只对“存在但类型不对”的情况 fail-fast，避免阻断“缺段则追加”的合法场景。
    if node9 is not None and not isinstance(node9, dict):
        raise ValueError("root field_9(UI) 结构异常：期望为 dict")
    if baseline_node9 is not None and not isinstance(baseline_node9, dict):
        raise ValueError("root field_9(UI) baseline 结构异常：期望为 dict")

    # 允许：baseline 缺失 UI 段（baseline_node9=None），但写回端通过 prepare_* 注入了 node9(dict)。
    # 该场景必须把 field_9 追加进输出 payload，否则 verify/后续流程读回仍为 None。
    if isinstance(node9, dict):
        if isinstance(baseline_node9, dict):
            patched_root_chunks: List[Tuple[bytes, bytes]] = []
            replaced_9 = False
            for tag_raw, value_raw in list(root_chunks):
                parsed = parse_tag_raw(tag_raw)
                if (not replaced_9) and parsed.field_number == 9 and parsed.wire_type == 2:
                    _len_raw, old_node9_bytes = split_length_delimited_value_raw(value_raw)
                    node9_chunks, node9_consumed = decode_message_to_wire_chunks(
                        data_bytes=old_node9_bytes,
                        start_offset=0,
                        end_offset=len(old_node9_bytes),
                    )
                    if node9_consumed != len(old_node9_bytes):
                        raise ValueError("root field_9 wire decode 未完整消费")

                    # field_501：布局注册表（bytes list）
                    baseline_501 = baseline_node9.get("501")
                    target_501 = node9.get("501")
                    if isinstance(baseline_501, str):
                        baseline_501 = [baseline_501]
                    if isinstance(target_501, str):
                        target_501 = [target_501]
                    if baseline_501 is None:
                        baseline_501 = []
                    if target_501 is None:
                        target_501 = []
                    if not isinstance(baseline_501, list) or not isinstance(target_501, list):
                        raise ValueError("field_9/501 结构异常：期望为 list/str/None")

                    # field_502：UI record list（message list）
                    baseline_502 = baseline_node9.get("502")
                    target_502 = node9.get("502")
                    if isinstance(baseline_502, dict):
                        baseline_502 = [baseline_502]
                    if isinstance(target_502, dict):
                        target_502 = [target_502]
                    if baseline_502 is None:
                        baseline_502 = []
                    if target_502 is None:
                        target_502 = []
                    if not isinstance(baseline_502, list) or not isinstance(target_502, list):
                        raise ValueError("field_9/502 结构异常：期望为 list/dict/None")

                    out_node9_chunks: List[Tuple[bytes, bytes]] = []
                    idx_501 = 0
                    idx_502 = 0

                    for inner_tag_raw, inner_value_raw in list(node9_chunks):
                        inner_parsed = parse_tag_raw(inner_tag_raw)
                        if inner_parsed.field_number == 501 and inner_parsed.wire_type == 2:
                            # 对齐 list 索引
                            if idx_501 >= len(target_501):
                                raise ValueError("field_9/501 数量减少（不支持删除 registry 条目）")
                            new_text = target_501[idx_501]
                            old_text = baseline_501[idx_501] if idx_501 < len(baseline_501) else None
                            idx_501 += 1

                            if new_text == old_text:
                                out_node9_chunks.append((bytes(inner_tag_raw), bytes(inner_value_raw)))
                                continue
                            # 允许空字符串表示空 bytes
                            if isinstance(new_text, str) and new_text == "":
                                out_node9_chunks.append((bytes(inner_tag_raw), build_length_delimited_value_raw(b"")))
                                continue
                            if not isinstance(new_text, str) or not new_text.startswith("<binary_data>"):
                                raise ValueError("field_9/501 期望为 '<binary_data>' 或空字符串")
                            out_node9_chunks.append(
                                (
                                    bytes(inner_tag_raw),
                                    build_length_delimited_value_raw(parse_binary_data_hex_text(new_text)),
                                )
                            )
                            continue

                        if inner_parsed.field_number == 502 and inner_parsed.wire_type == 2:
                            if idx_502 >= len(target_502):
                                raise ValueError("field_9/502 数量减少（不支持删除 UI record）")
                            new_record = target_502[idx_502]
                            old_record = baseline_502[idx_502] if idx_502 < len(baseline_502) else None
                            idx_502 += 1
                            if old_record is not None and new_record == old_record:
                                out_node9_chunks.append((bytes(inner_tag_raw), bytes(inner_value_raw)))
                                continue
                            if not isinstance(new_record, dict):
                                raise ValueError("field_9/502 record 期望为 dict")
                            encoded = encode_message(dict(new_record))
                            out_node9_chunks.append((bytes(inner_tag_raw), build_length_delimited_value_raw(encoded)))
                            continue

                        out_node9_chunks.append((bytes(inner_tag_raw), bytes(inner_value_raw)))

                    # 追加新增的 registry entries（501）
                    if len(target_501) > idx_501:
                        for extra in target_501[idx_501:]:
                            if isinstance(extra, str) and extra == "":
                                out_node9_chunks.append((encode_tag(501, 2), build_length_delimited_value_raw(b"")))
                                continue
                            if not isinstance(extra, str) or not extra.startswith("<binary_data>"):
                                raise ValueError("field_9/501 追加条目期望为 '<binary_data>' 或空字符串")
                            out_node9_chunks.append(
                                (encode_tag(501, 2), build_length_delimited_value_raw(parse_binary_data_hex_text(extra)))
                            )

                    # 追加新增的 UI records（502）
                    if len(target_502) > idx_502:
                        for extra in target_502[idx_502:]:
                            if not isinstance(extra, dict):
                                raise ValueError("field_9/502 追加 record 期望为 dict")
                            out_node9_chunks.append(
                                (encode_tag(502, 2), build_length_delimited_value_raw(encode_message(dict(extra))))
                            )

                    new_node9_bytes = encode_wire_chunks(out_node9_chunks)
                    patched_root_chunks.append((bytes(tag_raw), build_length_delimited_value_raw(new_node9_bytes)))
                    replaced_9 = True
                    continue

                patched_root_chunks.append((bytes(tag_raw), bytes(value_raw)))

            if not replaced_9:
                # 允许少数极端存档缺失 UI 段：此时直接追加（保持其它 payload 完全不动）
                encoded_node9 = encode_message(dict(node9))
                patched_root_chunks.append((encode_tag(9, 2), build_length_delimited_value_raw(encoded_node9)))

            root_chunks = patched_root_chunks
        else:
            # baseline 没有 field_9：直接追加新的 UI 段（不做全量重编码）
            encoded_node9 = encode_message(dict(node9))
            root_chunks = list(root_chunks)
            root_chunks.append((encode_tag(9, 2), build_length_delimited_value_raw(encoded_node9)))

    # 3) patch 实例/实体段（root field_5 -> field_1 entries）
    baseline_node5 = baseline_payload_root.get("5")
    node5 = payload_root.get("5")
    # 兼容：少数极简存档可能缺失实例/实体段（baseline_node5=None），但本次写回需要追加 node5(dict)。
    if node5 is not None and not isinstance(node5, dict):
        raise ValueError("root field_5 结构异常：期望为 dict")
    if baseline_node5 is not None and not isinstance(baseline_node5, dict):
        raise ValueError("root field_5 baseline 结构异常：期望为 dict")

    if isinstance(node5, dict):
        if isinstance(baseline_node5, dict):
            baseline_entries = baseline_node5.get("1")
            entries = node5.get("1")
            if isinstance(baseline_entries, dict):
                baseline_entries = [baseline_entries]
            if isinstance(entries, dict):
                entries = [entries]
            if baseline_entries is None:
                baseline_entries = []
            if entries is None:
                entries = []
            if not isinstance(baseline_entries, list) or not isinstance(entries, list):
                raise ValueError("root field_5/1(entry_list) 结构异常：期望为 list/dict/None")

            patched_root_chunks2: List[Tuple[bytes, bytes]] = []
            replaced_5 = False
            for tag_raw, value_raw in list(root_chunks):
                parsed = parse_tag_raw(tag_raw)
                if (not replaced_5) and parsed.field_number == 5 and parsed.wire_type == 2:
                    _len_raw, old_node5_bytes = split_length_delimited_value_raw(value_raw)
                    node5_chunks, node5_consumed = decode_message_to_wire_chunks(
                        data_bytes=old_node5_bytes,
                        start_offset=0,
                        end_offset=len(old_node5_bytes),
                    )
                    if node5_consumed != len(old_node5_bytes):
                        raise ValueError("root field_5 wire decode 未完整消费")

                    out_node5_chunks: List[Tuple[bytes, bytes]] = []
                    idx_entry = 0
                    for inner_tag_raw, inner_value_raw in list(node5_chunks):
                        inner_parsed = parse_tag_raw(inner_tag_raw)
                        if inner_parsed.field_number == 1 and inner_parsed.wire_type == 2:
                            if idx_entry >= len(entries):
                                raise ValueError("root field_5/1 数量减少（不支持删除 entry）")
                            new_entry = entries[idx_entry]
                            old_entry = baseline_entries[idx_entry] if idx_entry < len(baseline_entries) else None
                            idx_entry += 1
                            if old_entry is not None and new_entry == old_entry:
                                out_node5_chunks.append((bytes(inner_tag_raw), bytes(inner_value_raw)))
                                continue
                            if not isinstance(new_entry, dict):
                                raise ValueError("root field_5/1 entry 期望为 dict")
                            out_node5_chunks.append(
                                (
                                    bytes(inner_tag_raw),
                                    build_length_delimited_value_raw(encode_message(dict(new_entry))),
                                )
                            )
                            continue
                        out_node5_chunks.append((bytes(inner_tag_raw), bytes(inner_value_raw)))

                    if len(entries) > idx_entry:
                        for extra in entries[idx_entry:]:
                            if not isinstance(extra, dict):
                                raise ValueError("root field_5/1 追加 entry 期望为 dict")
                            out_node5_chunks.append(
                                (encode_tag(1, 2), build_length_delimited_value_raw(encode_message(dict(extra))))
                            )

                    new_node5_bytes = encode_wire_chunks(out_node5_chunks)
                    patched_root_chunks2.append((bytes(tag_raw), build_length_delimited_value_raw(new_node5_bytes)))
                    replaced_5 = True
                    continue

                patched_root_chunks2.append((bytes(tag_raw), bytes(value_raw)))

            if not replaced_5:
                # root 没有 field_5：允许极少数极简存档；此时直接追加新的 section5
                encoded_node5 = encode_message(dict(node5))
                patched_root_chunks2.append((encode_tag(5, 2), build_length_delimited_value_raw(encoded_node5)))

            root_chunks = patched_root_chunks2
        else:
            # baseline 没有 field_5：直接追加新的 section5（不做全量重编码）
            encoded_node5 = encode_message(dict(node5))
            root_chunks = list(root_chunks)
            root_chunks.append((encode_tag(5, 2), build_length_delimited_value_raw(encoded_node5)))

    # 4) 追加“baseline 缺失但 payload_root 新增”的 root 字段（极空存档 bootstrap 场景）
    #
    # 说明：
    # - 当前写回策略为了最大限度保留 wire-level 原始 bytes，默认只 patch field_40/field_9/field_5；
    # - 但对“极空 base .gil”（payload 仅有少量字段）来说，UI 写回阶段可能会从 seed `.gil`
    #   补齐大量 root4 段（例如 10/11/12/...），这些字段在 baseline 中不存在，若不追加则输出仍缺段，
    #   容易在编辑器侧表现为“布局切换异常/页面叠加/看起来像串页”。（表现常被误认为每页都有上一页的文字）
    # - 因此这里仅做“追加缺失字段”（不替换已有字段），保证常规场景仍保持最小改动策略。
    baseline_field_numbers = {parse_tag_raw(tag_raw).field_number for tag_raw, _ in list(root_chunks)}
    missing_fields: Dict[str, Any] = {}
    for k, v in dict(payload_root).items():
        key_text = str(k)
        if key_text in {"40", "9", "5"}:
            continue
        # 只处理数值键（字段号）
        if not key_text.isdigit():
            continue
        field_number = int(key_text)
        if field_number in baseline_field_numbers:
            continue
        missing_fields[key_text] = v

    if missing_fields:
        missing_sorted: Dict[str, Any] = {}
        for k2 in sorted(missing_fields.keys(), key=lambda t: int(t)):
            missing_sorted[str(k2)] = missing_fields[str(k2)]

        encoded_missing = encode_message(dict(missing_sorted))
        missing_chunks, missing_consumed = decode_message_to_wire_chunks(
            data_bytes=encoded_missing,
            start_offset=0,
            end_offset=len(encoded_missing),
        )
        if missing_consumed != len(encoded_missing):
            raise ValueError("missing root fields wire decode 未完整消费")
        root_chunks = list(root_chunks) + list(missing_chunks)

    new_payload_bytes = encode_wire_chunks(list(root_chunks))
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=new_payload_bytes, container_spec=container_spec)
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    output_gil_path.write_bytes(output_bytes)


def _dump_gil_to_raw_json_object(gil_file_path: Path) -> Dict[str, Any]:
    """
    写回用：以“尽量 lossless”的方式加载 `.gil` payload 为数值键 dict。

    注意：这里不能复用 dump-json 的“可读输出”逻辑，否则会因为 utf8 sanitize/strip
    导致 payload bytes 变化（即使用户没有改任何字段），从而出现“编辑器导入失败”。
    """
    payload_bytes = read_gil_payload_bytes(Path(gil_file_path).resolve())
    decoded_field_map, consumed_offset = decode_message_to_field_map(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
        remaining_depth=32,
    )
    if consumed_offset != len(payload_bytes):
        raise ValueError(
            "gil payload 未能完整解码为单个 message（存在 trailing bytes）："
            f"consumed={consumed_offset}, total={len(payload_bytes)}"
        )
    payload_root = decoded_field_map_to_numeric_message(decoded_field_map, prefer_raw_hex_for_utf8=True)
    if not isinstance(payload_root, dict):
        raise TypeError("decoded payload_root is not dict")
    return {"4": payload_root}


__all__ = [
    "dump_gil_to_raw_json_object",
    "_write_back_modified_gil_by_reencoding_payload",
    "_dump_gil_to_raw_json_object",
]

