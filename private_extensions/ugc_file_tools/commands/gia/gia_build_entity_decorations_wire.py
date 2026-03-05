from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia_export.decorations import build_entity_gia_with_decorations_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "生成“带装饰物的实体类” .gia（wire-level：基于模板克隆 + 精确补丁）。\n"
            "关键点：会同步写入 parent.relatedIds + parent 内部 packed accessories id 列表，并修正每个装饰物对 parent id 的绑定。"
        )
    )
    argument_parser.add_argument("--entity-base-gia", dest="entity_base_gia", required=True, help="实体 base .gia（可为纯空模型，无装饰物）")
    argument_parser.add_argument(
        "--accessory-template-gia",
        dest="accessory_template_gia",
        default="",
        help="可选：提供装饰物模板来源 .gia（当 entity-base-gia 内缺少 accessories/relatedIds 模板时必须提供；例如空模型加一个装饰物.gia）。",
    )
    argument_parser.add_argument(
        "--decorations-report",
        dest="decorations_report_json",
        required=True,
        help="装饰物报告 JSON（decorations[*].name/template_id/pos/yaw_deg/scale）。",
    )
    argument_parser.add_argument(
        "--entity-name",
        dest="entity_name",
        default="",
        help="可选：设置实体名称（写入 parent GraphUnit.name，并尽量同步父图内部 name record）。",
    )
    argument_parser.add_argument("--output", dest="output_gia_file", required=True, help="输出 .gia（会强制落盘到 ugc_file_tools/out/）")
    argument_parser.add_argument(
        "--limit",
        dest="limit_count",
        type=int,
        default=10,
        help="装饰物数量（默认 10；<=0 表示不限制）。",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 base/template .gia 容器头/尾（失败会直接抛错）。",
    )
    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    out_path = resolve_output_file_path_in_out_dir(Path(args.output_gia_file))
    template_gia = str(args.accessory_template_gia or "").strip()

    result = build_entity_gia_with_decorations_wire(
        entity_base_gia=Path(args.entity_base_gia),
        accessory_template_gia=Path(template_gia) if template_gia != "" else None,
        decorations_report_json=Path(args.decorations_report_json),
        output_gia_path=out_path,
        check_header=bool(args.check_header),
        limit_count=int(args.limit_count),
        entity_name=str(args.entity_name or ""),
    )

    output_gia_file = Path(str(result["output_gia_file"])).resolve()
    if not output_gia_file.is_file():
        raise FileNotFoundError(f"生成失败：未找到输出文件：{str(output_gia_file)!r}")

    dst_dir = get_beyond_local_export_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied_path = dst_dir / output_gia_file.name
    shutil.copy2(output_gia_file, copied_path)
    copied_to: Optional[str] = str(copied_path)

    print("=" * 80)
    print("entity decorations (wire) 生成完成：")
    print(f"- entity_base_gia: {result.get('entity_base_gia')}")
    print(f"- accessory_template_gia: {result.get('accessory_template_gia')}")
    print(f"- output_gia_file: {result.get('output_gia_file')}")
    print(f"- decorations_count: {result.get('decorations_count')}")
    print(f"- unit_id_start: {result.get('unit_id_start')}")
    print(f"- parent_unit_id: {result.get('parent_unit_id')}")
    print(f"- file_path: {result.get('file_path')}")
    print(f"- proto_size: {result.get('proto_size')}")
    print(f"- exported_to: {copied_to}")
    print("=" * 80)


if __name__ == "__main__":
    main()


