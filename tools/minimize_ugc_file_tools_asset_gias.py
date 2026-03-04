from __future__ import annotations

"""
minimize_ugc_file_tools_asset_gias.py

将 `private_extensions/ugc_file_tools/builtin_resources/gia_templates/**/*.gia` 裁剪为“最小必需 root 顶层字段集合”：
- 目标：减少对外仓库体积与误入库风险，同时保证导出链路依赖的结构模板仍可使用。
- fail-fast：缺字段 / 解码失败 / 写盘失败均直接抛错。

运行：
  - 预演（不写盘）：python -X utf8 -m tools.minimize_ugc_file_tools_asset_gias
  - 写回（覆盖文件；写前备份到 tmp/）：python -X utf8 -m tools.minimize_ugc_file_tools_asset_gias --apply
"""

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT_FIELD_1 = "1"  # GraphUnit(s)
ROOT_FIELD_2 = "2"  # accessories / entry list (depending on gia type)
ROOT_FIELD_3 = "3"  # filePath / tag string
ROOT_FIELD_5 = "5"  # gameVersion (exists on some templates)


@dataclass(frozen=True, slots=True)
class GiaMinimizeSpec:
    rel_path: str
    required_root_fields: tuple[str, ...]


GIA_SPECS: tuple[GiaMinimizeSpec, ...] = (
    # signal templates（信号导出/示例生成：从模板提取 GraphUnit；依赖 1/2/3）
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/signals/signal_node_defs_full.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3),
    ),
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/signals/signal_node_defs_minimal.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3),
    ),
    # struct templates（结构体导出需要复用 accessories/relatedIds + filePath + gameVersion）
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/struct_defs_6.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3, ROOT_FIELD_5),
    ),
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/struct_defs_2.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3, ROOT_FIELD_5),
    ),
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/struct_defs_3.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3, ROOT_FIELD_5),
    ),
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/struct_defs_1_modern.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3, ROOT_FIELD_5),
    ),
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/struct_defs_1_legacy_adventure_level_config.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3, ROOT_FIELD_5),
    ),
    # layout asset template（布局资产导出/patch 依赖 1/2/3/5）
    GiaMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/gia_templates/layout_asset_template.gia",
        required_root_fields=(ROOT_FIELD_1, ROOT_FIELD_2, ROOT_FIELD_3, ROOT_FIELD_5),
    ),
)


def _ensure_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"{label} must be Mapping, got {type(value).__name__}")


def _utc_stamp_compact() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _minimize_gia_file(*, repo_root: Path, spec: GiaMinimizeSpec, decode_depth: int) -> tuple[int, bytes]:
    gia_path = (repo_root / spec.rel_path).resolve()
    if not gia_path.is_file():
        raise FileNotFoundError(str(gia_path))

    from ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
    from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message

    proto = unwrap_gia_container(gia_path, check_header=True)
    fields, consumed = decode_message_to_field_map(
        data_bytes=proto,
        start_offset=0,
        end_offset=len(proto),
        remaining_depth=int(decode_depth),
    )
    if consumed != len(proto):
        raise ValueError(f"protobuf 解析未消费完整字节流：file={str(gia_path)}")
    root_msg = decoded_field_map_to_numeric_message(fields)
    root_map = _ensure_mapping(root_msg, label="root_message")

    minimized_root: dict[str, Any] = {}
    for field in spec.required_root_fields:
        if field not in root_map:
            raise KeyError(f"gia missing required root field: {field!r}, file={str(gia_path)}")
        minimized_root[str(field)] = root_map[str(field)]

    out_proto = encode_message(dict(minimized_root))
    out_bytes = wrap_gia_container(out_proto)
    return int(gia_path.stat().st_size), bytes(out_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="仓库根目录（默认：tools/ 的上一级）",
    )
    parser.add_argument("--decode-depth", type=int, default=24, help="protobuf-like decode depth")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="写盘覆盖 builtin_resources/gia_templates/**/*.gia（覆盖前会备份到 tmp/artifacts/asset_gia_backups/<utc>/）",
    )
    args = parser.parse_args(argv)

    repo_root = Path(str(args.repo_root)).resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(str(repo_root))

    private_extensions_root = (repo_root / "private_extensions").resolve()
    if not private_extensions_root.is_dir():
        raise FileNotFoundError(str(private_extensions_root))
    sys.path.insert(0, str(private_extensions_root))

    backup_root = (repo_root / "tmp" / "artifacts" / "asset_gia_backups" / _utc_stamp_compact()).resolve()

    total_before = 0
    total_after = 0
    for s in GIA_SPECS:
        before_size, out_bytes = _minimize_gia_file(
            repo_root=repo_root,
            spec=s,
            decode_depth=int(args.decode_depth),
        )
        after_size = int(len(out_bytes))
        total_before += int(before_size)
        total_after += int(after_size)

        gia_path = (repo_root / s.rel_path).resolve()
        print(f"[gia] {gia_path.as_posix()}")
        print(f"  keep={list(s.required_root_fields)}")
        print(f"  size: {before_size} -> {after_size} bytes")

        if bool(args.apply):
            backup_path = (backup_root / Path(s.rel_path)).resolve()
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(gia_path, backup_path)
            gia_path.write_bytes(out_bytes)

    print(f"[total] {total_before} -> {total_after} bytes")
    if bool(args.apply):
        print(f"[backup] {backup_root.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

