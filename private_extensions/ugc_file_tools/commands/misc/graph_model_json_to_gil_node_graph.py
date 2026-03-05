from __future__ import annotations

"""
graph_model_json_to_gil_node_graph.py

目标：
- 读取 Graph_Generater 导出的 GraphModel(JSON, 含自动布局坐标/edges)；
- 将该 GraphModel 写回到 `.gil` 的节点图段（payload field 10）；支持以“空存档”等 base 容器输出。
- 可选：纯 JSON 模式（不克隆任何现有 `.gil` 的 node/record 模板），仅依据 GraphModel(JSON)+Graph_Generater NodeDef 按 schema 生成并写回。

说明：
- 该文件保持为 **CLI 薄入口 + 兼容 re-export**，核心实现已拆分到 `ugc_file_tools/node_graph_writeback/`。
- 不使用 try/except；失败直接抛错，便于定位。

使用建议（避免口径分叉）：
- **导出中心/交付进游戏测**：优先使用 `python -X utf8 private_extensions\\run_ugc_file_tools.py project import ...`（导出中心同款 pipeline）。
- 本工具（尤其 `--pure-json`）更偏向“内部诊断/二分/最小自举”，不保证覆盖导出中心对“节点图列表/索引”等 UI 依赖字段的完整口径。
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

# 兼容：允许以脚本方式运行 `python ugc_file_tools/graph_model_json_to_gil_node_graph.py ...`
# 此时 sys.path 默认不包含仓库根目录，导致 `import ugc_file_tools.*` 失败。
if __package__ is None:
    # 运行方式兼容：
    # - repo_root: 包含 `engine/`
    # - private_extensions: 包含 `ugc_file_tools/`
    this_file = Path(__file__).resolve()
    repo_root_dir = this_file.parents[3]
    private_extensions_dir = this_file.parents[2]
    for p in (repo_root_dir, private_extensions_dir):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root
from ugc_file_tools.node_graph_writeback.writer import (
    run_precheck_and_write_and_postcheck,
    run_write_and_postcheck_pure_json,
    write_graph_model_to_gil,
)


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "将 GraphModel(JSON) 写回到 .gil 的节点图段（flow + data edges）。\n"
            "注意：导出中心/交付进游戏测请优先使用 `project import`（导出中心同款 pipeline），避免口径分叉。"
        )
    )
    parser.add_argument("--graph-json", required=True, help="输入 GraphModel JSON（export_graph_model_json_from_graph_code.py 的输出）")
    parser.add_argument("--template-gil", required=False, help="模板 .gil（提供节点图段结构模板；也作为默认样本来源之一）")
    parser.add_argument("--base-gil", default=None, help="可选：base .gil（作为输出容器；为空则等同于 template-gil）")
    parser.add_argument("--template-library-dir", default=None, help="可选：额外的样本库目录（递归扫描 *.gil 以补齐节点/record 样本）")
    parser.add_argument("--output-gil", required=True, help="输出 .gil（强制写入 ugc_file_tools/out/；不要覆盖重要样本）")
    parser.add_argument("--template-graph-id", dest="template_graph_id_int", type=int, required=True, help="模板 .gil 中用于取样的 graph_id_int（server graph）")
    parser.add_argument("--new-graph-name", dest="new_graph_name", required=True, help="新图名称")
    parser.add_argument("--new-graph-id", dest="new_graph_id_int", type=int, default=None, help="可选：指定新 graph_id_int（不填则自动分配）")
    parser.add_argument(
        "--pure-json",
        dest="pure_json",
        action="store_true",
        help=(
            "纯 JSON 写回（内部诊断/最小自举）：不克隆任何现有 .gil 的节点/record 模板；"
            "template-gil/template-library-dir 不必提供（仅保留旧模式兼容）。\n"
            "警告：该模式不保证与导出中心对“节点图列表/索引”等 UI 依赖字段口径一致；交付请走 `project import`。"
        ),
    )
    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=str(repo_root()),
        help="Graph_Generater 根目录（默认 workspace/Graph_Generater）",
    )
    parser.add_argument(
        "--node-type-map",
        dest="mapping_path",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名 映射文件（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument(
        "--skip-precheck",
        action="store_true",
        help="跳过写回前/后预检（不推荐；默认会跑节点模板覆盖预检 + 节点图变量写回合约校验）。",
    )
    parser.add_argument(
        "--skip-ui-custom-variable-sync",
        dest="skip_ui_custom_variable_sync",
        action="store_true",
        help=(
            "跳过 UI 自定义变量同步：默认会在写回节点图段后，从 base .gil 所属项目存档的 `管理配置/UI源码/*.html` 扫描"
            "`{1:lv.xxx}` / `{{lv.xxx}}` 占位符与 `data-ui-variable-defaults`，并将缺失的自定义变量（含默认值）补齐到"
            " `关卡实体/玩家实体`。"
        ),
    )
    parser.add_argument(
        "--prefer-signal-specific-type-id",
        dest="prefer_signal_specific_type_id",
        action="store_true",
        help=(
            "兼容参数（保留旧 CLI 口径）：当信号节点满足静态绑定且 base `.gil` 映射可用时，"
            "写回侧会自动将其 runtime type_id 提升为 signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx）。"
            "本参数当前不再影响最终输出，可忽略。"
        ),
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if bool(args.pure_json):
        if args.base_gil is None:
            raise ValueError("--pure-json 模式下必须提供 --base-gil（通常为“空存档.gil”（带基础设施））。")
        report, postcheck_report_path = run_write_and_postcheck_pure_json(
            graph_model_json_path=Path(args.graph_json),
            base_gil_path=Path(args.base_gil),
            output_gil_path=Path(args.output_gil),
            scope_graph_id_int=int(args.template_graph_id_int),
            new_graph_name=str(args.new_graph_name),
            new_graph_id_int=(int(args.new_graph_id_int) if args.new_graph_id_int is not None else None),
            mapping_path=Path(args.mapping_path),
            graph_generater_root=Path(args.graph_generater_root),
            skip_postcheck=bool(args.skip_precheck),
            prefer_signal_specific_type_id=bool(args.prefer_signal_specific_type_id),
            auto_sync_ui_custom_variable_defaults=not bool(args.skip_ui_custom_variable_sync),
        )
        precheck_report_path = None
    else:
        if args.template_gil is None:
            raise ValueError("缺少 --template-gil：旧模式需要模板 .gil 作为样本库与节点图段结构模板。")
        report, precheck_report_path, postcheck_report_path = run_precheck_and_write_and_postcheck(
            graph_model_json_path=Path(args.graph_json),
            template_gil_path=Path(args.template_gil),
            base_gil_path=(Path(args.base_gil) if args.base_gil is not None else None),
            template_library_dir=(Path(args.template_library_dir) if args.template_library_dir is not None else None),
            output_gil_path=Path(args.output_gil),
            template_graph_id_int=int(args.template_graph_id_int),
            new_graph_name=str(args.new_graph_name),
            new_graph_id_int=(int(args.new_graph_id_int) if args.new_graph_id_int is not None else None),
            mapping_path=Path(args.mapping_path),
            graph_generater_root=Path(args.graph_generater_root),
            skip_precheck=bool(args.skip_precheck),
            prefer_signal_specific_type_id=bool(args.prefer_signal_specific_type_id),
            auto_sync_ui_custom_variable_defaults=not bool(args.skip_ui_custom_variable_sync),
        )

    print("=" * 80)
    print("GraphModel(JSON) → GIL 写回完成：")
    for key in sorted(report.keys()):
        print(f"- {key}: {report.get(key)}")
    if precheck_report_path is not None:
        print(f"- precheck_node_template_coverage_report: {str(precheck_report_path)}")
    if postcheck_report_path is not None:
        print(f"- postcheck_graph_variable_contract_report: {str(postcheck_report_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




