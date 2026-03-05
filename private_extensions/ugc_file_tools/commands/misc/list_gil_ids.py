from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.id_listing import list_component_and_entity_ids_from_gil_file
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "直接读取 .gil，列出其中包含的“元件(template_id)/实体(instance_id)”ID 清单，并导出 JSON 到 ugc_file_tools/out/。\n"
            "默认只导出去重后的 ID 列表 + name->id 映射；如需实例级明细请加 --details。"
        )
    )
    parser.add_argument("--gil", required=True, help="输入 .gil 文件路径")
    parser.add_argument(
        "--output",
        default="gil_ids.json",
        help="输出 JSON 文件路径（会强制落盘到 ugc_file_tools/out/；默认 gil_ids.json）。",
    )
    parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="protobuf-like 解码递归深度上限（默认 16；越大越慢，但可能抽取到更多字段）。",
    )
    parser.add_argument(
        "--details",
        dest="include_instances",
        action="store_true",
        help="输出实例级明细（component_instances/entity_instances）。",
    )
    parser.add_argument(
        "--print",
        dest="print_lists",
        action="store_true",
        help="额外在控制台打印去重后的 ID 列表（默认只打印摘要与输出路径）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    exported = list_component_and_entity_ids_from_gil_file(
        gil_file_path=Path(args.gil),
        max_depth=int(args.max_depth),
        include_instances=bool(args.include_instances),
    )

    output_path = resolve_output_file_path_in_out_dir(Path(args.output), default_file_name="gil_ids.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")

    component_ids = exported.get("component_template_ids") or []
    entity_ids = exported.get("entity_instance_id_ints") or []

    print("=" * 80)
    print("GIL ID 清单导出完成：")
    print(f"- source_gil: {str(Path(args.gil).resolve())}")
    print(f"- output_json: {str(output_path)}")
    print(f"- component_template_ids_count: {int(exported.get('component_template_ids_count') or 0)}")
    print(f"- entity_instance_id_ints_count: {int(exported.get('entity_instance_id_ints_count') or 0)}")
    print("-" * 80)
    if bool(args.print_lists):
        print("component_template_ids:")
        for cid in component_ids:
            print(f"- {cid}")
        print("-" * 40)
        print("entity_instance_id_ints:")
        for eid in entity_ids:
            print(f"- {eid}")
        print("-" * 40)
    print("=" * 80)


if __name__ == "__main__":
    main()



