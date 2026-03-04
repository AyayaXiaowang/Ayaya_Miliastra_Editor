from __future__ import annotations

"""
minimize_ugc_file_tools_ui_fixture_gils.py

将 `private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/*.gil` 裁剪为“最小必需 payload_root 顶层字段”：
- 目标：减少对外仓库体积与误入库风险，同时保证被硬引用的写回/导入逻辑仍可运行。
- fail-fast：缺字段 / 解码失败 / 写盘失败均直接抛错。

运行：
  - 预演（不写盘）：python -X utf8 -m tools.minimize_ugc_file_tools_ui_fixture_gils
  - 写回（覆盖文件；写前备份到 tmp/）：python -X utf8 -m tools.minimize_ugc_file_tools_ui_fixture_gils --apply
"""

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SECTION_5 = "5"
SECTION_9 = "9"


@dataclass(frozen=True, slots=True)
class FixtureMinimizeSpec:
    rel_path: str
    required_top_level_fields: tuple[str, ...]


UI_FIXTURE_SPECS: tuple[FixtureMinimizeSpec, ...] = (
    # web_ui_import_prepare: 需要 5(实体段) + 9(UI 段模板/兜底)
    FixtureMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/进度条样式.gil",
        required_top_level_fields=(SECTION_5, SECTION_9),
    ),
    # web_ui_import_templates: 仅用于从 UI record_list 中选择“道具展示”可克隆 record
    FixtureMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/道具展示.gil",
        required_top_level_fields=(SECTION_9,),
    ),
    # web_ui_import_templates: TextBox 需要可克隆样本 record（仅需 UI 段）
    FixtureMinimizeSpec(
        rel_path="private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/文本框样式.gil",
        required_top_level_fields=(SECTION_9,),
    ),
)


def _ensure_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"{label} must be Mapping, got {type(value).__name__}")


def _utc_stamp_compact() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _minimize_fixture_file(*, repo_root: Path, spec: FixtureMinimizeSpec) -> tuple[int, bytes]:
    fixture_path = (repo_root / spec.rel_path).resolve()
    if not fixture_path.is_file():
        raise FileNotFoundError(str(fixture_path))

    from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message
    from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
    from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message

    container_spec = read_gil_container_spec(fixture_path)
    payload_root = load_gil_payload_as_numeric_message(fixture_path, max_depth=64, prefer_raw_hex_for_utf8=True)
    root_map = _ensure_mapping(payload_root, label="payload_root")

    minimized_root: dict[str, Any] = {}
    for field in spec.required_top_level_fields:
        if field not in root_map:
            raise KeyError(f"fixture missing required payload_root field: {field!r}, file={str(fixture_path)}")
        minimized_root[str(field)] = root_map[str(field)]

    payload_bytes = encode_message(dict(minimized_root))
    out_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    return int(fixture_path.stat().st_size), bytes(out_bytes)


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
        help="写盘覆盖 builtin_resources/空的界面控件组/*.gil（覆盖前会备份到 tmp/artifacts/ui_fixture_gil_backups/<utc>/）",
    )
    args = parser.parse_args(argv)

    repo_root = Path(str(args.repo_root)).resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(str(repo_root))

    private_extensions_root = (repo_root / "private_extensions").resolve()
    if not private_extensions_root.is_dir():
        raise FileNotFoundError(str(private_extensions_root))
    sys.path.insert(0, str(private_extensions_root))

    backup_root = (repo_root / "tmp" / "artifacts" / "ui_fixture_gil_backups" / _utc_stamp_compact()).resolve()

    total_before = 0
    total_after = 0
    for s in UI_FIXTURE_SPECS:
        before_size, out_bytes = _minimize_fixture_file(repo_root=repo_root, spec=s)
        after_size = int(len(out_bytes))
        total_before += int(before_size)
        total_after += int(after_size)

        fixture_path = (repo_root / s.rel_path).resolve()
        print(f"[ui_fixture] {fixture_path.as_posix()}")
        print(f"  keep={list(s.required_top_level_fields)}")
        print(f"  size: {before_size} -> {after_size} bytes")

        if bool(args.apply):
            backup_path = (backup_root / Path(s.rel_path)).resolve()
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture_path, backup_path)
            fixture_path.write_bytes(out_bytes)

    print(f"[total] {total_before} -> {total_after} bytes")
    if bool(args.apply):
        print(f"[backup] {backup_root.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

