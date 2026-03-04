from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.decorations import export_gia_decorations_variants
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "批量导出多种 `.gia` 变体（实体/资产包），用于在真源中通过“能否出现/能否打开”来二分定位导入约束。\n"
            "输出：会在 out/<dir>/ 下生成多份 .gia + manifest.json，并可选复制到 Beyond_Local_Export。"
        )
    )
    argument_parser.add_argument(
        "--decorations-report",
        dest="decorations_report_json",
        required=True,
        help="装饰物报告 JSON（decorations[*].name/template_id/pos/yaw_deg/scale）。",
    )
    argument_parser.add_argument("--entity-base-gia", dest="entity_base_gia", default="", help="可选：实体类 base .gia（例如空模型加一个装饰物.gia）。")
    argument_parser.add_argument("--asset-base-gia", dest="asset_base_gia", default="", help="可选：资产包类 base .gia（例如花间的钢琴.gia）。")
    argument_parser.add_argument(
        "--select-parent-name",
        dest="select_parent_name",
        default="",
        help="资产包模式：在 Root.field_1(GraphUnit list) 中选择 parent GraphUnit 的 name。",
    )
    argument_parser.add_argument(
        "--select-parent-id",
        dest="select_parent_id",
        type=int,
        default=None,
        help="资产包模式：在 Root.field_1(GraphUnit list) 中选择 parent GraphUnit 的 id（优先）。",
    )
    argument_parser.add_argument(
        "--limit",
        dest="limit_count",
        type=int,
        default=10,
        help="限制装饰物数量（默认 10；<=0 表示不限制）。",
    )
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="gia_variants",
        help="输出目录（默认：gia_variants；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    argument_parser.add_argument(
        "--output-prefix",
        dest="output_prefix",
        default="variants",
        help="输出文件名前缀（默认 variants）。",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 base .gia 容器头/尾（失败会直接抛错）。",
    )
    argument_parser.add_argument(
        "--decode-max-depth",
        dest="decode_max_depth",
        type=int,
        default=16,
        help="protobuf 递归解码深度上限（默认 16）。",
    )
    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    entity_base = str(args.entity_base_gia or "").strip()
    asset_base = str(args.asset_base_gia or "").strip()
    if entity_base == "" and asset_base == "":
        raise ValueError("至少提供一个 base：--entity-base-gia 或 --asset-base-gia")

    result = export_gia_decorations_variants(
        entity_base_gia=Path(entity_base) if entity_base != "" else None,
        asset_bundle_base_gia=Path(asset_base) if asset_base != "" else None,
        decorations_report_json=Path(args.decorations_report_json),
        output_dir=Path(args.output_dir),
        output_prefix=str(args.output_prefix or "").strip() or "variants",
        check_header=bool(args.check_header),
        decode_max_depth=int(args.decode_max_depth),
        select_parent_name=str(args.select_parent_name or ""),
        select_parent_id=int(args.select_parent_id) if isinstance(args.select_parent_id, int) else None,
        limit_count=int(args.limit_count),
    )

    copied_count = 0
    copied_dir = get_beyond_local_export_dir()
    copied_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(result.get("output_dir") or "").resolve()
    for p in out_dir.glob("*.gia"):
        shutil.copy2(p, copied_dir / p.name)
        copied_count += 1

    print("=" * 80)
    print("变体导出完成：")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- manifest: {result.get('manifest')}")
    print(f"- variants_count: {result.get('variants_count')}")
    print(f"- exported_to: {str(copied_dir)}")
    print(f"- exported_files: {copied_count}")
    print("=" * 80)


if __name__ == "__main__":
    main()



