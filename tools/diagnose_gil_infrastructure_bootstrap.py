from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_DEFAULT_DECODE_MAX_DEPTH = 64
_SYS_PATH_PREPEND_INDEX = 0
_OFFSET_START = 0


def _parse_args() -> argparse.Namespace:
    """Parse CLI args for the infrastructure bootstrap diagnostic."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-gil", required=True, help="输入 base .gil 路径")
    parser.add_argument("--output-gil", required=True, help="输出 .gil 路径（可与 input 相同）")
    parser.add_argument("--bootstrap-gil", default="", help="bootstrap seed .gil（留空=使用内置 seeds/infrastructure_bootstrap.gil）")
    return parser.parse_args()


def _decode_and_validate_gil_payload(*, gil_path: Path) -> dict[str, object]:
    """Decode gil payload and validate it can be fully consumed as a single message."""
    from ugc_file_tools.gil_dump_codec.gil_container import read_gil_payload_bytes_and_container_meta
    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map

    payload_bytes, meta = read_gil_payload_bytes_and_container_meta(gil_file_path=Path(gil_path))
    field_map, consumed = decode_message_to_field_map(
        data_bytes=payload_bytes,
        start_offset=int(_OFFSET_START),
        end_offset=len(payload_bytes),
        remaining_depth=int(_DEFAULT_DECODE_MAX_DEPTH),
    )
    if int(consumed) != len(payload_bytes):
        raise ValueError(f"payload 未完整解码：consumed={int(consumed)} total={len(payload_bytes)} file={str(gil_path)!r}")

    if not isinstance(field_map, dict):
        raise TypeError("decoded field_map must be dict")

    return {"meta": dict(meta), "payload_bytes_len": int(len(payload_bytes))}


def _repo_root() -> Path:
    """Return the repository root path."""
    return Path(__file__).resolve().parents[1]


def main() -> None:
    """Run infrastructure bootstrap and validate output `.gil` is decodable."""
    repo_root = _repo_root()
    sys.path.insert(int(_SYS_PATH_PREPEND_INDEX), str(repo_root / "private_extensions"))

    from ugc_file_tools.gil.infrastructure_bootstrap import bootstrap_gil_infrastructure_sections
    from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

    args = _parse_args()
    input_gil = Path(str(args.input_gil)).resolve()
    output_gil = Path(str(args.output_gil)).resolve()

    bootstrap_gil_text = str(args.bootstrap_gil or "").strip()
    if bootstrap_gil_text:
        bootstrap_gil = Path(bootstrap_gil_text).resolve()
    else:
        bootstrap_gil = (ugc_file_tools_builtin_resources_root() / "seeds" / "infrastructure_bootstrap.gil").resolve()

    report = bootstrap_gil_infrastructure_sections(
        input_gil_file_path=input_gil,
        output_gil_file_path=output_gil,
        bootstrap_gil_file_path=bootstrap_gil,
    )

    print("[bootstrap] report:")
    from dataclasses import asdict

    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))

    target_for_validation = output_gil if bool(report.changed) else input_gil
    print(f"[validate] target={str(target_for_validation)}")
    summary = _decode_and_validate_gil_payload(gil_path=target_for_validation)
    print("[validate] ok:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

