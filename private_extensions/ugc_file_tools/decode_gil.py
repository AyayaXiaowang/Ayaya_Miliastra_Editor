import sys
import json
import os
import base64
from typing import Any, Dict, List, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map


MAX_NESTED_DEPTH = 16


def parse_message(
    data_bytes: bytes,
    start_offset: int,
    end_offset: int,
    remaining_depth: int,
) -> Tuple[Dict[str, Any], int]:
    """
    以通用方式解析一段 protobuf-like message 字节（decode_gil 风格输出）。

    该逻辑已统一收口到 `ugc_file_tools.gil_dump_codec.protobuf_like.decode_message_to_field_map`，
    本文件仅保留薄包装与 CLI 入口，避免底层规则分叉。
    """
    return decode_message_to_field_map(
        data_bytes=data_bytes,
        start_offset=start_offset,
        end_offset=end_offset,
        remaining_depth=remaining_depth,
    )


def parse_stream(data_bytes: bytes) -> List[Any]:
    """
    将整个字节流视为一串连续的Protobuf message，逐个解析。
    """
    messages: List[Any] = []
    data_length = len(data_bytes)
    current_offset = 0

    while current_offset < data_length:
        message_fields, next_offset = parse_message(
            data_bytes,
            current_offset,
            data_length,
            MAX_NESTED_DEPTH,
        )

        if next_offset <= current_offset:
            remaining_bytes = data_bytes[current_offset:data_length]
            messages.append(
                {
                    "offset_start": current_offset,
                    "offset_end": data_length,
                    "raw_hex": remaining_bytes.hex(),
                }
            )
            break

        original_fields = message_fields
        original_next_offset = next_offset

        if (
            len(original_fields) <= 1
            and original_next_offset - current_offset <= 4
            and current_offset + 1 < data_length
        ):
            candidate_start_offset = current_offset + 1
            candidate_fields, candidate_next_offset = parse_message(
                data_bytes,
                candidate_start_offset,
                data_length,
                MAX_NESTED_DEPTH,
            )

            original_consumed_length = original_next_offset - current_offset
            candidate_consumed_length = candidate_next_offset - candidate_start_offset

            if (
                len(candidate_fields) > len(original_fields)
                and candidate_next_offset > original_next_offset
                and candidate_consumed_length >= original_consumed_length * 4
            ):
                if candidate_start_offset > current_offset:
                    raw_prefix_bytes = data_bytes[current_offset:candidate_start_offset]
                    messages.append(
                        {
                            "offset_start": current_offset,
                            "offset_end": candidate_start_offset,
                            "raw_hex": raw_prefix_bytes.hex(),
                        }
                    )

                messages.append(
                    {
                        "offset_start": candidate_start_offset,
                        "offset_end": candidate_next_offset,
                        "message": candidate_fields,
                    }
                )

                current_offset = candidate_next_offset
                continue

        if len(message_fields) == 0:
            raw_bytes = data_bytes[current_offset:next_offset]
            messages.append(
                {
                    "offset_start": current_offset,
                    "offset_end": next_offset,
                    "raw_hex": raw_bytes.hex(),
                }
            )
        else:
            messages.append(
                {
                    "offset_start": current_offset,
                    "offset_end": next_offset,
                    "message": message_fields,
                }
            )

        current_offset = next_offset

    return messages


def ensure_output_directory(output_directory: str) -> None:
    if output_directory == "":
        return
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)


def build_output_path(output_directory: str, input_path: str) -> str:
    base_name = os.path.basename(input_path)
    output_file_name = base_name + ".json"
    if output_directory == "":
        return output_file_name
    return os.path.join(output_directory, output_file_name)


def parse_single_file(input_path: str, output_directory: str) -> None:
    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json

    ensure_output_directory(output_directory)
    output_path = build_output_path(output_directory, input_path)
    dump_gil_to_json(input_path, output_path)


def parse_directory(input_directory: str, output_directory: str) -> None:
    ensure_output_directory(output_directory)

    for entry_name in os.listdir(input_directory):
        entry_path = os.path.join(input_directory, entry_name)
        if not os.path.isfile(entry_path):
            continue
        if not entry_name.lower().endswith(".gil"):
            continue
        parse_single_file(entry_path, output_directory)


def decode_bytes_to_python(message_bytes: bytes) -> Any:
    """
    将一段原始字节优先按“单个message”方式完全解析，若无法完整对齐，则退回按流解析。
    """
    data_length = len(message_bytes)
    message_fields, consumed_offset = parse_message(
        message_bytes,
        0,
        data_length,
        MAX_NESTED_DEPTH,
    )

    if consumed_offset == data_length and len(message_fields) > 0:
        return message_fields

    messages_list = parse_stream(message_bytes)
    return messages_list


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--base64":
        base64_text = sys.argv[2]
        message_bytes = base64.b64decode(base64_text)
        decoded_object = decode_bytes_to_python(message_bytes)
        json.dump(decoded_object, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "--hex":
        hex_text = sys.argv[2]
        message_bytes = bytes.fromhex(hex_text)
        decoded_object = decode_bytes_to_python(message_bytes)
        json.dump(decoded_object, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "--raw-file":
        raw_file_path = sys.argv[2]
        with open(raw_file_path, "rb") as raw_file:
            message_bytes = raw_file.read()
        decoded_object = decode_bytes_to_python(message_bytes)
        json.dump(decoded_object, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    if len(sys.argv) < 2:
        default_input_directory = os.path.join("存档测试")
        default_output_directory = os.path.join("out", "gil_json")
        parse_directory(default_input_directory, default_output_directory)
        return

    input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        output_directory = sys.argv[2]
    else:
        output_directory = os.path.join("out", "gil_json")

    if os.path.isdir(input_path):
        parse_directory(input_path, output_directory)
    else:
        parse_single_file(input_path, output_directory)


if __name__ == "__main__":
    main()


