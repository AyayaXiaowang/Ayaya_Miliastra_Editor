from __future__ import annotations

"""
report_gil_payload_root_wire_sections_diff.py

用途：
- 更“硬”的 wire-level 对照：读取两份 `.gil` 的 payload_root(raw bytes)，
  在 protobuf-like wire chunks 层面对比指定 field_number 的 length-delimited section payload 是否完全一致。

设计目标：
- 纯 bytes 对比（不走 dump-json / message 解码），用于证明“是否发生 payload drift”；
- 特别适用于排查：导出/写回链路是否意外重编码了 templates/instances/ui 等段。
"""

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil_dump_codec.gil_container import read_gil_payload_bytes
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir
from ugc_file_tools.wire import decode_message_to_wire_chunks, parse_tag_raw, split_length_delimited_value_raw


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex_head(data: bytes, *, max_bytes: int) -> str:
    b = bytes(data[: max(0, int(max_bytes))])
    return b.hex(" ").upper()


@dataclass(frozen=True, slots=True)
class _FieldOccurrence:
    wire_type: int
    value_raw: bytes
    payload_bytes: bytes | None  # only for wire_type=2


def _collect_field_occurrences(*, payload_bytes: bytes, field_number: int) -> list[_FieldOccurrence]:
    chunks, consumed = decode_message_to_wire_chunks(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
    )
    if int(consumed) != len(payload_bytes):
        raise ValueError(
            "payload_bytes did not decode to a single complete message: "
            f"consumed={int(consumed)}, total={len(payload_bytes)}"
        )

    out: list[_FieldOccurrence] = []
    for tag_raw, value_raw in list(chunks):
        tag = parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(field_number):
            continue
        if int(tag.wire_type) == 2:
            _length_raw, inner_payload = split_length_delimited_value_raw(value_raw)
            out.append(
                _FieldOccurrence(
                    wire_type=int(tag.wire_type),
                    value_raw=bytes(value_raw),
                    payload_bytes=bytes(inner_payload),
                )
            )
            continue
        out.append(
            _FieldOccurrence(
                wire_type=int(tag.wire_type),
                value_raw=bytes(value_raw),
                payload_bytes=None,
            )
        )
    return out


def _summarize_occurrences(
    *,
    occs: Sequence[_FieldOccurrence],
    preview_bytes: int,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"occurrences": []}
    for i, occ in enumerate(list(occs)):
        item: Dict[str, Any] = {
            "index": int(i),
            "wire_type": int(occ.wire_type),
            "value_raw_len": int(len(occ.value_raw)),
            "value_raw_sha256": _sha256_hex(bytes(occ.value_raw)),
            "value_raw_hex_head": _hex_head(bytes(occ.value_raw), max_bytes=int(preview_bytes)),
        }
        if occ.payload_bytes is not None:
            item["payload_len"] = int(len(occ.payload_bytes))
            item["payload_sha256"] = _sha256_hex(bytes(occ.payload_bytes))
            item["payload_hex_head"] = _hex_head(bytes(occ.payload_bytes), max_bytes=int(preview_bytes))
        out["occurrences"].append(item)
    out["occurrences_count"] = int(len(out["occurrences"]))
    return out


def report_gil_payload_root_wire_sections_diff(
    *,
    a_gil_path: Path,
    b_gil_path: Path,
    field_numbers: Sequence[int],
    output_dir: Path,
    preview_bytes: int,
    label_a: str = "a",
    label_b: str = "b",
) -> Dict[str, Any]:
    a_path = Path(a_gil_path).resolve()
    b_path = Path(b_gil_path).resolve()
    if not a_path.is_file():
        raise FileNotFoundError(str(a_path))
    if not b_path.is_file():
        raise FileNotFoundError(str(b_path))

    fields = [int(x) for x in list(field_numbers or [])]
    fields = [x for x in fields if int(x) > 0]
    fields = sorted(list(dict.fromkeys(fields)))
    if not fields:
        raise ValueError("field_numbers 不能为空")

    out_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gil_payload_root_wire_sections_diff")
    out_dir.mkdir(parents=True, exist_ok=True)

    a_payload = read_gil_payload_bytes(a_path)
    b_payload = read_gil_payload_bytes(b_path)

    fields_report: List[Dict[str, Any]] = []
    for field_number in fields:
        a_occs = _collect_field_occurrences(payload_bytes=a_payload, field_number=int(field_number))
        b_occs = _collect_field_occurrences(payload_bytes=b_payload, field_number=int(field_number))

        # 当前场景：payload_root 的 section 一般为非 repeated；若 repeated，也按“逐项 bytes 对齐”比对（保守）。
        equal_payload = False
        equal_value_raw = False
        if len(a_occs) == len(b_occs):
            equal_value_raw = all(bytes(a.value_raw) == bytes(b.value_raw) for a, b in zip(a_occs, b_occs))
            equal_payload = all(
                (a.payload_bytes is not None and b.payload_bytes is not None and bytes(a.payload_bytes) == bytes(b.payload_bytes))
                or (a.payload_bytes is None and b.payload_bytes is None and bytes(a.value_raw) == bytes(b.value_raw))
                for a, b in zip(a_occs, b_occs)
            )

        fields_report.append(
            {
                "field_number": int(field_number),
                "present_in_a": bool(a_occs),
                "present_in_b": bool(b_occs),
                "occurrences_count_a": int(len(a_occs)),
                "occurrences_count_b": int(len(b_occs)),
                "equal_value_raw": bool(equal_value_raw),
                "equal_payload": bool(equal_payload),
                f"{label_a}": _summarize_occurrences(occs=a_occs, preview_bytes=int(preview_bytes)),
                f"{label_b}": _summarize_occurrences(occs=b_occs, preview_bytes=int(preview_bytes)),
            }
        )

    report_obj: Dict[str, Any] = {
        "a_gil": str(a_path),
        "b_gil": str(b_path),
        "output_dir": str(out_dir),
        "fields": fields_report,
    }

    report_path = (out_dir / "report.json").resolve()
    report_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    # 简短 markdown 总结：方便快速翻阅
    lines: list[str] = []
    lines.append("# gil payload_root wire sections diff")
    lines.append("")
    lines.append(f"- {label_a}: `{str(a_path)}`")
    lines.append(f"- {label_b}: `{str(b_path)}`")
    lines.append("")
    lines.append("| field | present(a) | present(b) | occ(a) | occ(b) | equal_payload |")
    lines.append("|---:|:---:|:---:|---:|---:|:---:|")
    for item in fields_report:
        lines.append(
            f"| {int(item['field_number'])} | {bool(item['present_in_a'])} | {bool(item['present_in_b'])} | "
            f"{int(item['occurrences_count_a'])} | {int(item['occurrences_count_b'])} | {bool(item['equal_payload'])} |"
        )
    summary_md_path = (out_dir / "summary.md").resolve()
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "output_dir": str(out_dir),
        "report_json": str(report_path),
        "summary_md": str(summary_md_path),
        "fields": fields_report,
    }


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="Wire-level compare `.gil` payload_root sections (field_number) by raw bytes.")
    parser.add_argument("a_gil", help="对照文件 A（.gil）")
    parser.add_argument("b_gil", help="对照文件 B（.gil）")
    parser.add_argument(
        "--fields",
        nargs="*",
        type=int,
        default=[4, 5, 9, 10],
        help="要对比的 payload_root field_number 列表（默认 4/5/9/10）",
    )
    parser.add_argument(
        "--preview-bytes",
        dest="preview_bytes",
        type=int,
        default=32,
        help="report 中每个 occurrence 输出的 hex head 预览字节数（默认 32）",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="_tmp_gil_payload_root_wire_sections_diff",
        help="输出目录名（实际会被收口到 ugc_file_tools/out/ 下）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = report_gil_payload_root_wire_sections_diff(
        a_gil_path=Path(args.a_gil),
        b_gil_path=Path(args.b_gil),
        field_numbers=list(args.fields or []),
        output_dir=Path(args.output_dir),
        preview_bytes=int(args.preview_bytes),
    )

    print("=== gil payload_root wire sections diff ===")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- report_json: {result.get('report_json')}")
    print(f"- summary_md: {result.get('summary_md')}")
    print("")
    for item in list(result.get("fields") or []):
        if not isinstance(item, dict):
            continue
        print(
            f"- field={item.get('field_number')}: "
            f"present(a)={item.get('present_in_a')}, present(b)={item.get('present_in_b')}, "
            f"occ(a)={item.get('occurrences_count_a')}, occ(b)={item.get('occurrences_count_b')}, "
            f"equal_payload={item.get('equal_payload')}"
        )


if __name__ == "__main__":
    main()

