from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ugc_file_tools.node_graph_semantics.genshin_ts_node_schema import check_graph_model_against_genshin_ts_node_schema


def _run_precheck_node_template_coverage_or_raise(
    *,
    graph_model_json_path: Path,
    template_gil_path: Path,
    base_gil_path: Optional[Path],
    template_graph_id_int: int,
    template_library_dir: Optional[Path],
    mapping_path: Path,
    default_scope: str,
    output_gil_path: Path,
    graph_generater_root: Path,
) -> Path:
    """
    写回前预检：确保 GraphModel 所需节点在 node_type_semantic_map.json 可映射到唯一 type_id，
    且该 type_id 在模板库中存在样本覆盖。

    产物：会在 ugc_file_tools/out/ 生成一份 JSON 报告；若存在缺口则直接抛错阻断写回。
    """
    report_name = f"{Path(output_gil_path).name}.precheck.node_template_coverage_diff.report.json"

    from ugc_file_tools.node_graph_writeback.template_coverage_diff import write_node_template_coverage_diff_report

    report_path = write_node_template_coverage_diff_report(
        graph_models=[Path(graph_model_json_path).resolve()],
        template_gil_path=Path(template_gil_path),
        base_gil_path=Path(base_gil_path).resolve() if base_gil_path is not None else Path(template_gil_path).resolve(),
        template_graph_id_int=int(template_graph_id_int),
        template_library_dir=Path(template_library_dir).resolve() if template_library_dir is not None else None,
        mapping_path=Path(mapping_path),
        default_scope=str(default_scope),
        output_json_name=str(report_name),
    )

    doc = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise TypeError(f"预检报告 JSON 顶层必须是 dict：{str(report_path)!r}")
    summary = doc.get("summary")
    if not isinstance(summary, dict):
        raise TypeError(f"预检报告 summary 必须是 dict：{str(report_path)!r}")

    missing_template_type_ids_count = int(summary.get("missing_template_type_ids_count") or 0)
    missing_type_id_mapping_titles_count = int(summary.get("missing_type_id_mapping_titles_count") or 0)
    ambiguous_title_mappings_count = int(summary.get("ambiguous_title_mappings_count") or 0)

    if missing_template_type_ids_count != 0 or missing_type_id_mapping_titles_count != 0 or ambiguous_title_mappings_count != 0:
        raise ValueError(
            "写回前预检失败（节点模板覆盖/映射存在缺口），请先修复后再写回：\n"
            f"- report: {str(report_path)}\n"
            f"- missing_template_type_ids_count: {missing_template_type_ids_count}\n"
            f"- missing_type_id_mapping_titles_count: {missing_type_id_mapping_titles_count}\n"
            f"- ambiguous_title_mappings_count: {ambiguous_title_mappings_count}\n"
            "修复方向：补齐 graph_ir/node_type_semantic_map.json 的 title→type_id 映射，或补充模板样本库 template_library_dir。"
        )

    # ===== 真源画像校验（genshin-ts / NodeEditorPack）=====
    # 目的：用真源节点画像（node_id + pins record）对 GraphModel 的端口数量/类型做交叉验证，
    #       提前发现“节点 type_id/端口索引错位/typed JSON 漂移”等会导致导入失败的问题。
    #
    # 策略（保守）：
    # - schema 缺失默认不阻断（只输出报告），避免因第三方覆盖不足影响主链路；
    # - 若 schema 命中且 port_count/可判定 port_type 不一致，则直接抛错阻断写回。
    graph_json_object = json.loads(Path(graph_model_json_path).read_text(encoding="utf-8"))
    if not isinstance(graph_json_object, dict):
        raise TypeError("graph_model_json must be dict")

    from ugc_file_tools.node_graph_semantics.graph_generater import load_node_defs_by_scope as _load_node_defs_by_scope
    from ugc_file_tools.node_graph_semantics.graph_model import (
        normalize_graph_model_payload as _normalize_graph_model_payload,
        normalize_nodes_list as _normalize_nodes_list,
    )
    from ugc_file_tools.node_graph_semantics.layout import sort_graph_nodes_for_stable_ids as _sort_graph_nodes_for_stable_ids
    from .node_index import _build_graph_node_id_maps
    from .type_id_map import (
        build_node_def_key_to_type_id as _build_node_def_key_to_type_id,
        build_node_name_to_type_id as _build_node_name_to_type_id,
    )

    name_to_type_id = _build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(default_scope))
    node_def_key_to_type_id = _build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(default_scope),
        graph_generater_root=Path(graph_generater_root),
    )
    node_defs_by_name = _load_node_defs_by_scope(graph_generater_root=Path(graph_generater_root), scope=str(default_scope))

    # 预检只需要 node_type_id_by_graph_node_id：
    # 这里不做 struct_id→type_id 的可选覆盖（避免引入 base_gil 依赖），结构体节点的 type_id 差异
    # 不应作为“真源画像校验”的硬错误来源。
    graph_model = _normalize_graph_model_payload(graph_json_object)
    nodes = _normalize_nodes_list(graph_model)
    sorted_nodes = _sort_graph_nodes_for_stable_ids(nodes)
    node_id_int_by_graph_node_id, node_type_id_by_graph_node_id, _title_by_id, _node_by_id = _build_graph_node_id_maps(
        sorted_nodes=sorted_nodes,
        name_to_type_id=name_to_type_id,
        node_def_key_to_type_id=node_def_key_to_type_id,
    )
    _ = node_id_int_by_graph_node_id
    _ = _title_by_id
    _ = _node_by_id

    genshin_report_path, genshin_issues = check_graph_model_against_genshin_ts_node_schema(
        graph_model_json_object=graph_json_object,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        scope=str(default_scope),
        strict_missing_schema=False,
        output_report_name=f"{Path(output_gil_path).name}.precheck.genshin_ts_node_schema.report.json",
    )

    # 阻断策略（保守但避免误报）：
    # - port_type_mismatch：始终阻断（表示 typed JSON 与真源画像可判定类型不一致）
    # - port_count_mismatch：仅当 GraphModel 的 data ports **多于** schema 记录时才阻断。
    #   说明：GraphModel 可能缺失/隐藏部分 pins（例如 unknown pin / 内部 pin0(len)），
    #   写回时会保留模板节点的完整 pins 结构，因此 “少于 schema” 仅记录报告不阻断。
    blocking: list = []
    for i in list(genshin_issues):
        if i.kind == "port_type_mismatch":
            blocking.append(i)
            continue
        if i.kind != "port_count_mismatch":
            continue
        d = i.details if isinstance(i.details, dict) else {}
        data_in = int(d.get("data_inputs_count") or 0)
        data_out = int(d.get("data_outputs_count") or 0)
        exp_in = int(d.get("expected_inputs_count") or 0)
        exp_out = int(d.get("expected_outputs_count") or 0)
        if data_in > exp_in or data_out > exp_out:
            blocking.append(i)
    if blocking:
        raise ValueError(
            "写回前预检失败（genshin-ts 节点画像校验发现端口数量/类型不一致），请先修复后再写回：\n"
            f"- mapping: {str(Path(mapping_path).resolve())}\n"
            f"- graph_model: {str(Path(graph_model_json_path).resolve())}\n"
            f"- report: {str(genshin_report_path) if genshin_report_path is not None else '(schema report missing)'}\n"
            f"- blocking_issues: {len(blocking)}\n"
            "修复方向：检查 node_type_semantic_map 的 title→type_id 是否正确、GraphModel 是否为 typed JSON、以及端口规则/动态端口处理是否遗漏。"
        )

    # 将 genshin-ts 校验结果“挂”到模板覆盖预检报告里，保持单一 report 路径可追溯。
    if genshin_report_path is not None:
        doc["genshin_ts_node_schema_precheck"] = {
            "report": str(genshin_report_path),
            "issues_count": int(len(genshin_issues)),
            "blocking_issues_count": int(len(blocking)),
        }
        report_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    return report_path


def _run_postcheck_graph_variable_writeback_contract_or_raise(
    *,
    output_gil_path: Path,
    focus_graph_id_int: int,
) -> Path:
    """
    写回后校验：对写回产物的 GraphEntry['6'] 进行合约校验。
    仅校验本次写回的新图（避免被模板/base 内其他图的“真源差异”噪声影响）。
    """
    report_name = f"{Path(output_gil_path).name}.postcheck.graph_variable_writeback_contract.report.json"

    from ugc_file_tools.node_graph_writeback.graph_variable_writeback_contract import (
        check_graph_variable_writeback_contract_or_raise,
    )

    return check_graph_variable_writeback_contract_or_raise(
        inputs=[Path(output_gil_path).resolve()],
        focus_graph_ids=[int(focus_graph_id_int)],
        output_json_name=str(report_name),
    )


