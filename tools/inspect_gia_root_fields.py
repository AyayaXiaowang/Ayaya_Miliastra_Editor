from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


JSON_DUMPS_KWARGS = {"ensure_ascii": False, "separators": (",", ":")}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _key_sort_tuple(k: Any) -> Tuple[int, str]:
    try:
        return int(str(k)), str(k)
    except Exception:
        return (2**31 - 1), str(k)


def inspect_root_fields(input_gia: Path, *, decode_depth: int) -> None:
    from ugc_file_tools.gia.container import unwrap_gia_container
    from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map

    proto = unwrap_gia_container(Path(input_gia).resolve(), check_header=True)
    fields, consumed = decode_message_to_field_map(
        data_bytes=proto,
        start_offset=0,
        end_offset=len(proto),
        remaining_depth=int(decode_depth),
    )
    if consumed != len(proto):
        raise ValueError("decode did not consume full proto bytes")
    root = decoded_field_map_to_numeric_message(fields)
    if not isinstance(root, dict):
        raise TypeError("decoded root_message must be dict")

    items: List[Tuple[str, int]] = []
    for k, v in root.items():
        size = len(json.dumps(v, **JSON_DUMPS_KWARGS))
        items.append((str(k), int(size)))
    items.sort(key=lambda kv: _key_sort_tuple(kv[0]))

    print(str(Path(input_gia).resolve()))
    print(f"root fields: {len(items)}")
    for k, size in items:
        print(f"- {k}: approx_json_chars={size}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect top-level root fields of a .gia.")
    parser.add_argument("--input", required=True, help="Input .gia path")
    parser.add_argument("--decode-depth", type=int, default=24, help="protobuf-like decode depth")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root / "private_extensions"))

    inspect_root_fields(Path(args.input), decode_depth=int(args.decode_depth))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

