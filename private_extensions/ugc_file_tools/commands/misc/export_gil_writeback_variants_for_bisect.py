from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


def _parse_variants_json(path: Path) -> List[Dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        raise ValueError("variants_json 必须是 list")
    out: List[Dict[str, Any]] = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        disable = item.get("disable") or []
        if label == "":
            raise ValueError(f"variant.label 不能为空：{item!r}")
        if not isinstance(disable, list):
            raise ValueError(f"variant.disable 必须是 list：label={label!r}")
        disable2 = [str(x).strip() for x in disable if str(x).strip() != ""]
        out.append({"label": label, "disable": disable2})
    if not out:
        raise ValueError("variants_json 为空")
    return out


def main(argv: List[str] | None = None) -> None:
    """
    批量导出多份 GIL（同一份 GraphModel），用于在游戏侧做二分定位：
    - 每份产物通过环境变量 UGC_WB_DISABLE 禁用不同的写回补丁点；
    - 产物默认写入 ugc_file_tools/out/，可选额外复制到指定目录（便于进游戏测试）。
    """
    from ugc_file_tools.node_graph_writeback.writer import run_precheck_and_write_and_postcheck

    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-json", required=True, help="输入 GraphModel JSON（export_graph_model_json_from_graph_code 的输出）")
    parser.add_argument("--template-gil", required=True, help="模板 .gil（提供节点样本/结构模板）")
    parser.add_argument("--base-gil", required=True, help="base .gil（作为输出容器）")
    parser.add_argument("--template-graph-id", required=True, type=int, help="模板图 graph_id_int")
    parser.add_argument("--new-graph-name", required=True, help="新图名称")
    parser.add_argument("--new-graph-id", required=True, type=int, help="新图 graph_id_int（建议与模板一致）")
    parser.add_argument("--skip-precheck", action="store_true", help="跳过写回预检（不推荐）")
    parser.add_argument("--prefer-signal-specific-type-id", action="store_true", help="同写回工具：优先 signal-specific runtime")

    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=str(repo_root()),
        help="Graph_Generater 根目录（默认当前仓库根目录）",
    )
    parser.add_argument(
        "--node-type-map",
        dest="mapping_path",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名 映射文件（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument("--template-library-dir", default=None, help="可选：额外的样本库目录（递归扫描 *.gil 以补齐节点/record 样本）")

    parser.add_argument("--output-prefix", required=True, help="输出文件名前缀（basename，不含目录）")
    parser.add_argument("--variants-json", help="variants 配置 JSON（list[{label, disable:[...]}]）")
    parser.add_argument("--copy-to", help="可选：将生成的 .gil 额外复制到该目录（绝对路径）")

    args = parser.parse_args(argv)

    graph_json_path = Path(str(args.graph_json)).resolve()
    template_gil_path = Path(str(args.template_gil)).resolve()
    base_gil_path = Path(str(args.base_gil)).resolve()
    if not graph_json_path.is_file():
        raise FileNotFoundError(str(graph_json_path))
    if not template_gil_path.is_file():
        raise FileNotFoundError(str(template_gil_path))
    if not base_gil_path.is_file():
        raise FileNotFoundError(str(base_gil_path))

    if args.variants_json:
        variants = _parse_variants_json(Path(str(args.variants_json)).resolve())
    else:
        variants = [
            {"label": "A_all_enabled", "disable": []},
            {"label": "B_disable_all_patches", "disable": ["all"]},
        ]

    copy_to_dir: Path | None = None
    if args.copy_to:
        copy_to_dir = Path(str(args.copy_to)).resolve()
        copy_to_dir.mkdir(parents=True, exist_ok=True)

    # 按 variant 逐个写回
    reports: List[Dict[str, Any]] = []
    original_disable = os.environ.get("UGC_WB_DISABLE")
    for i, v in enumerate(list(variants), start=1):
        label = str(v.get("label") or "").strip()
        disable = [str(x).strip() for x in (v.get("disable") or []) if str(x).strip() != ""]
        os.environ["UGC_WB_DISABLE"] = ",".join(disable)

        out_name = f"{str(args.output_prefix).strip()}__{i:02d}__{label}.gil"
        report, precheck_report_path, postcheck_report_path = run_precheck_and_write_and_postcheck(
            graph_model_json_path=graph_json_path,
            template_gil_path=template_gil_path,
            base_gil_path=base_gil_path,
            template_library_dir=(Path(args.template_library_dir).resolve() if args.template_library_dir else None),
            output_gil_path=Path(out_name),
            template_graph_id_int=int(args.template_graph_id),
            new_graph_name=str(args.new_graph_name),
            new_graph_id_int=int(args.new_graph_id),
            mapping_path=Path(str(args.mapping_path)).resolve(),
            graph_generater_root=Path(str(args.graph_generater_root)).resolve(),
            skip_precheck=bool(args.skip_precheck),
            prefer_signal_specific_type_id=bool(args.prefer_signal_specific_type_id),
            auto_sync_ui_custom_variable_defaults=False,
            auto_fill_graph_variable_defaults_from_ui_registry=True,
            ui_registry_autofill_excluded_graph_variable_names=None,
        )
        output_gil = Path(str(report.get("output_gil") or "")).resolve()

        copied_to = None
        if copy_to_dir is not None:
            dst = copy_to_dir / output_gil.name
            shutil.copyfile(str(output_gil), str(dst))
            copied_to = str(dst)

        reports.append(
            {
                "variant": {"label": label, "disable": disable},
                "output_gil": str(output_gil),
                "copied_to": copied_to,
                "precheck_report": (str(precheck_report_path) if precheck_report_path is not None else None),
                "postcheck_report": (str(postcheck_report_path) if postcheck_report_path is not None else None),
            }
        )

    # 恢复环境变量
    if original_disable is None:
        os.environ.pop("UGC_WB_DISABLE", None)
    else:
        os.environ["UGC_WB_DISABLE"] = str(original_disable)

    report_path = resolve_output_file_path_in_out_dir(Path(f"{str(args.output_prefix).strip()}__bisect_variants.report.json"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"variants": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 80)
    print("写回 variants 导出完成：")
    print(f"- report: {str(report_path)}")
    for item in reports:
        v = item["variant"]
        print(f"- {v['label']}: disable={v['disable']} -> {item['output_gil']}")
        if item["copied_to"]:
            print(f"  copied_to: {item['copied_to']}")
    print("=" * 80)

