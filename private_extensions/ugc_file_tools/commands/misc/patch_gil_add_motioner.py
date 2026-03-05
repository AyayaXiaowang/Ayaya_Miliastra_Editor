from __future__ import annotations

"""
patch_gil_add_motioner.py

用途：
- 对指定 `.gil` 的实体实例段（root4/5/1[*]）补齐“运动器(Motioner)”组项：

    entry['7'] group_list 中新增/修补：
      { "1": 4, "2": 1, "14": { "505": 1 } }

说明：
- 输出 `.gil` 强制落盘到 `ugc_file_tools/out/`（不覆盖输入）。
- 为尽量保持 byte-level 稳定，默认使用 lossless 解码：`prefer_raw_hex_for_utf8=True`（避免可读化 sanitize/strip 造成无关字段漂移）。
- 默认不修改 root4/40（时间戳）；如需同步更新可显式加 `--touch-root40`。
- fail-fast：结构异常直接抛错；不使用 try/except。
"""

import argparse
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.motioner_group import patch_payload_root_add_motioner
from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _coerce_optional_int(value: object, *, label: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if text == "":
        return None
    if not text.isdigit():
        raise ValueError(f"{label} must be int, got {value!r}")
    return int(text)


def _iter_values(values: Optional[Iterable[str]]) -> list[str]:
    out: list[str] = []
    for v in list(values or []):
        t = str(v or "").strip()
        if t == "":
            continue
        out.append(t)
    return out


def _default_output_name_for_input(input_gil_path: Path) -> str:
    stem = input_gil_path.name
    if stem.lower().endswith(".gil"):
        stem = stem[:-4]
    return f"{stem}__motioner.gil"


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "为 .gil 的实体实例(root4/5/1[*])补齐“运动器(Motioner)”组项："
            "在 entry['7'] group_list 中新增/修补 {1:4,2:1,14:{505:1}}，并输出新 .gil 到 ugc_file_tools/out/。"
        )
    )
    parser.add_argument("--gil", required=True, help="输入 .gil 文件路径（不会被覆盖）")
    parser.add_argument(
        "--output",
        default="",
        help="输出 .gil 文件名/路径（强制落盘到 ugc_file_tools/out/；默认根据输入文件名生成）。",
    )
    parser.add_argument(
        "--max-decode-depth",
        dest="max_decode_depth",
        type=int,
        default=32,
        help="protobuf-like 解码递归深度上限（默认 32）。",
    )
    parser.add_argument(
        "--touch-root40",
        dest="touch_root40",
        action="store_true",
        help="将 root4/40 更新为当前秒级时间戳（用于模拟“编辑器导出后自动更新时间”）。",
    )

    match_group = parser.add_mutually_exclusive_group(required=True)
    match_group.add_argument("--all", dest="match_all", action="store_true", help="对所有实体实例 entry 补丁。")
    match_group.add_argument("--instance-id", dest="instance_id", help="按 instance_id 精确匹配补丁。")
    match_group.add_argument("--instance-name", dest="instance_name", help="按实例名精确匹配补丁（忽略大小写）。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    input_gil = Path(args.gil).resolve()
    if not input_gil.is_file():
        raise FileNotFoundError(str(input_gil))

    instance_id_int = _coerce_optional_int(getattr(args, "instance_id", None), label="--instance-id")
    instance_name = str(getattr(args, "instance_name", "") or "").strip() or None
    match_all = bool(getattr(args, "match_all", False))

    payload_root = load_gil_payload_as_numeric_message(
        input_gil,
        max_depth=int(args.max_decode_depth),
        prefer_raw_hex_for_utf8=True,
    )

    result = patch_payload_root_add_motioner(
        payload_root,
        instance_id_int=instance_id_int,
        instance_name=instance_name,
        match_all=match_all,
    )

    if int(result.matched_entries) == 0:
        raise ValueError("未匹配到任何实例 entry（请检查 --instance-id/--instance-name 或改用 --all）。")

    if bool(args.touch_root40):
        payload_root["40"] = int(time.time())

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_gil)
    out_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)

    output_arg = str(getattr(args, "output", "") or "").strip()
    output_path = resolve_output_file_path_in_out_dir(
        Path(output_arg) if output_arg else Path(_default_output_name_for_input(input_gil)),
        default_file_name=_default_output_name_for_input(input_gil),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(out_bytes)

    print("=" * 80)
    print("patch_gil_add_motioner 完成：")
    print(f"- source_gil: {str(input_gil)}")
    print(f"- output_gil: {str(output_path)}")
    print(f"- matched_entries: {int(result.matched_entries)}")
    print(f"- changed_entries: {int(result.changed_entries)}")
    print(f"- already_had_motioner_entries: {int(result.already_had_motioner_entries)}")
    print(f"- touch_root40: {bool(args.touch_root40)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

