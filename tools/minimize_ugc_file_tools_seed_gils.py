from __future__ import annotations

"""
minimize_ugc_file_tools_seed_gils.py

将 `private_extensions/ugc_file_tools/builtin_resources/seeds/*.gil` 裁剪为“最小必需 payload_root 顶层字段”：
- 不改变写回逻辑，仅减少 seed `.gil` 内与默认链路无关的段，降低仓库体积与隐私/未授权内容误入风险。
- fail-fast：缺字段 / 解码失败 / 写盘失败均直接抛错。

运行：
  - 预演（不写盘）：python -X utf8 -m tools.minimize_ugc_file_tools_seed_gils
  - 写回（会覆盖 seeds/*.gil；覆盖前会备份到 tmp/）：python -X utf8 -m tools.minimize_ugc_file_tools_seed_gils --apply
"""

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SECTION_2 = "2"
SECTION_4 = "4"
SECTION_5 = "5"
SECTION_6 = "6"
SECTION_8 = "8"
SECTION_10 = "10"
SECTION_11 = "11"
SECTION_35 = "35"


@dataclass(frozen=True, slots=True)
class SeedMinimizeSpec:
    rel_path: str
    required_top_level_fields: tuple[str, ...]


SEED_SPECS: tuple[SeedMinimizeSpec, ...] = (
    # `gil/infrastructure_bootstrap.py` 只从 bootstrap seed 读取：11/35/2
    SeedMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/seeds/infrastructure_bootstrap.gil",
        required_top_level_fields=(SECTION_11, SECTION_35, SECTION_2),
    ),
    # templates_importer / instances_importer 仅依赖：templates(4) / instances(5) / tabs(6) / root8(8)
    SeedMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/seeds/template_instance_exemplars.gil",
        required_top_level_fields=(SECTION_4, SECTION_5, SECTION_6, SECTION_8),
    ),
    # struct_definitions_importer_parts 仅依赖：node graph root(10)（其中含 struct blobs）
    SeedMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/seeds/struct_def_exemplars.gil",
        required_top_level_fields=(SECTION_10,),
    ),
    # ingame_save_structs_importer 依赖：node graph root(10)（含 struct blobs + node defs）
    SeedMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/seeds/ingame_save_structs_bootstrap.gil",
        required_top_level_fields=(SECTION_10,),
    ),
    # signal_writeback 从模板 payload 中选择无参信号 node_defs / signal entries：都在 10
    SeedMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/seeds/signal_node_def_templates.gil",
        required_top_level_fields=(SECTION_10,),
    ),
)


def _ensure_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"{label} must be Mapping, got {type(value).__name__}")


def _utc_stamp_compact() -> str:
    # 仅用于备份路径命名：可读且可排序
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _minimize_seed_file(*, repo_root: Path, spec: SeedMinimizeSpec) -> tuple[int, bytes]:
    seed_path = (repo_root / spec.rel_path).resolve()
    if not seed_path.is_file():
        raise FileNotFoundError(str(seed_path))

    from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message
    from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
    from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message

    container_spec = read_gil_container_spec(seed_path)
    payload_root = load_gil_payload_as_numeric_message(seed_path, max_depth=64, prefer_raw_hex_for_utf8=True)
    root_map = _ensure_mapping(payload_root, label="payload_root")

    # 仅裁剪“顶层字段集合”，不在字段内部做二次裁剪（避免改变 exemplar 覆盖范围）
    minimized_root: dict[str, Any] = {}
    for field in spec.required_top_level_fields:
        if field not in root_map:
            raise KeyError(f"seed missing required payload_root field: {field!r}, file={str(seed_path)}")
        minimized_root[str(field)] = root_map[str(field)]

    payload_bytes = encode_message(dict(minimized_root))
    out_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    return int(seed_path.stat().st_size), bytes(out_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="仓库根目录（默认：tools/ 的上一级）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="写盘覆盖 seeds/*.gil（覆盖前会备份到 tmp/artifacts/seed_gil_backups/<utc>/）",
    )
    args = parser.parse_args(argv)

    repo_root = Path(str(args.repo_root)).resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(str(repo_root))

    # 约定：`ugc_file_tools` 是 private extension；工具脚本运行时显式注入 import 根，避免依赖外部环境变量。
    private_extensions_root = (repo_root / "private_extensions").resolve()
    if not private_extensions_root.is_dir():
        raise FileNotFoundError(str(private_extensions_root))
    sys.path.insert(0, str(private_extensions_root))

    backup_root = (repo_root / "tmp" / "artifacts" / "seed_gil_backups" / _utc_stamp_compact()).resolve()

    total_before = 0
    total_after = 0
    for s in SEED_SPECS:
        before_size, out_bytes = _minimize_seed_file(repo_root=repo_root, spec=s)
        after_size = int(len(out_bytes))
        total_before += int(before_size)
        total_after += int(after_size)

        seed_path = (repo_root / s.rel_path).resolve()
        print(f"[seed] {seed_path.as_posix()}")
        print(f"  keep={list(s.required_top_level_fields)}")
        print(f"  size: {before_size} -> {after_size} bytes")

        if bool(args.apply):
            backup_path = (backup_root / Path(s.rel_path)).resolve()
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seed_path, backup_path)
            seed_path.write_bytes(out_bytes)

    print(f"[total] {total_before} -> {total_after} bytes")
    if bool(args.apply):
        print(f"[backup] {backup_root.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

