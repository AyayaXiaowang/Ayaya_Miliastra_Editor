from __future__ import annotations

"""
sync_graph_code_to_gil_preserve_graph_variables.py

目标：
- 将本地 Graph Code（节点图 .py）写回覆盖到目标 `.gil` 中；
- GraphVariables（节点图变量表）的 **增删改** 始终以本地 Graph Code 为准；
- 但对“同名变量的 default_value 是否保留目标 `.gil` 的值”提供参数开关（用户可能改过变量值）。

说明：
- 不使用 try/except；失败直接抛错，便于定位写回缺口/类型不一致/缺失目标图等问题。
- 输出 `.gil` 仍会先落到 `ugc_file_tools/out/`（遵循工具约定），再复制到用户指定的输出路径（通常为输入同目录）。
"""

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 兼容：允许以脚本方式运行 `python ugc_file_tools/commands/<tool>.py ...`
# 此时 sys.path 默认不包含仓库根目录，导致 `import ugc_file_tools.*` 失败。
if __package__ is None:
    this_file = Path(__file__).resolve()
    repo_root_dir = this_file.parents[3]
    private_extensions_dir = this_file.parents[2]
    for p in (repo_root_dir, private_extensions_dir):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.graph_variable_scanner import scan_gil_file_graph_variables
from ugc_file_tools.node_data_index import resolve_default_node_data_index_path
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root
from ugc_file_tools.commands.parse_gil_payload_to_graph_ir import export_readable_graph_ir_from_gil_payload
from ugc_file_tools.node_graph_writeback.writer import run_precheck_and_write_and_postcheck
from ugc_file_tools.ui.export_records import (
    UIExportRecord,
    load_ui_export_records,
    load_ui_guid_registry_snapshot,
    try_get_ui_export_record_by_id,
)
from ugc_file_tools.project_archive_importer.node_graphs_importer import (
    collect_required_ui_keys_from_graph_code_files as _collect_required_ui_keys_from_graph_code_files,
    export_graph_model_json_from_graph_code_with_context as _export_graph_model_json_from_graph_code_with_context,
    pick_template_graph_id_int as _pick_template_graph_id_int,
    prepare_graph_generater_context as _prepare_graph_generater_context,
    resolve_graph_generater_root as _resolve_graph_generater_root,
)


_SCAN_HEAD_CHARS = 8192
_GRAPH_NAME_LINE_RE = re.compile(r"(?m)^\s*graph_name\s*:\s*(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class _TargetGraph:
    graph_code_file: Path
    graph_name: str
    target_graph_id_int: int  # from input .gil


def _resolve_path_under_repo_root(path_text: str) -> Path:
    p = Path(str(path_text or "").strip())
    if p.is_absolute():
        return p.resolve()
    return (repo_root() / p).resolve()


def _scan_graph_name_from_graph_code_file(graph_code_file: Path) -> str:
    path = Path(graph_code_file).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    head = path.read_text(encoding="utf-8")[: int(_SCAN_HEAD_CHARS)]
    m = _GRAPH_NAME_LINE_RE.search(head)
    if m is None:
        raise ValueError(f"节点图源码未声明 graph_name（docstring metadata）：{str(path)!r}")
    name = str(m.group(1) or "").strip()
    if name == "":
        raise ValueError(f"节点图源码 graph_name 为空：{str(path)!r}")
    return name


def _iter_graph_code_files_in_dir(graph_code_dir: Path) -> List[Path]:
    root = Path(graph_code_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    return sorted([p.resolve() for p in root.glob("*.py") if p.is_file()], key=lambda p: p.name.casefold())


def _build_graph_name_to_id_map_from_gil(gil_path: Path) -> Dict[str, int]:
    obs = scan_gil_file_graph_variables(Path(gil_path).resolve())
    out: Dict[str, int] = {}
    for g in obs.graphs:
        name = str(g.graph_name or "").strip()
        if name == "":
            continue
        if name in out and int(out[name]) != int(g.graph_id_int):
            raise ValueError(f"目标 .gil 内存在同名但不同 graph_id_int 的节点图：name={name!r} a={out[name]} b={g.graph_id_int}")
        out[name] = int(g.graph_id_int)
    return out


def _is_optional_hidden_ui_key(ui_key: str) -> bool:
    k = str(ui_key or "").strip()
    # 1) hidden 语义：同组存在其它状态时可不要求独立 GUID（写回阶段允许 unresolved=0）
    if "__hidden__group" in k:
        return True
    # 2) UI_STATE_GROUP 稳定别名：写回阶段可通过 base `.gil` 的 UI records 反查补齐，
    #    因此快照选择阶段不将其视为“必须命中”的 key（避免误判无可用快照）。
    return k.startswith("UI_STATE_GROUP__")


def _pick_ui_export_record_and_snapshot_for_graph_code(
    *,
    workspace_root: Path,
    package_id: str,
    graph_code_files: Sequence[Path],
    ui_export_record_id: str,
) -> Tuple[UIExportRecord, Path]:
    """
    选择一个“包含所需 ui_key 的 registry snapshot”。

    - ui_export_record_id:
      - "latest"：从最新记录开始尝试，选第一个满足的 snapshot
      - 其它：视为 record_id，必须存在且满足
    """
    record_id_text = str(ui_export_record_id or "").strip().lower() or "latest"
    required_keys = _collect_required_ui_keys_from_graph_code_files(graph_code_files=list(graph_code_files))
    required_keys = {k for k in required_keys if not _is_optional_hidden_ui_key(k)}
    if not required_keys:
        raise ValueError("节点图源码未使用任何 ui_key: 占位符，但请求选择 UI 导出记录快照：这通常意味着参数配置错误。")

    records = load_ui_export_records(workspace_root=Path(workspace_root).resolve(), package_id=str(package_id))
    if not records:
        raise FileNotFoundError(
            "未找到任何 UI 导出记录（ui_export_records.json 为空或不存在），无法选择 ui_guid_registry_snapshot 以回填 ui_key。\n"
            "请先在 UI 工具链中导出一次相关页面（会生成 ui_export_records.json 与 ui_guid_registry_snapshots）。"
        )

    candidates: List[UIExportRecord] = []
    if record_id_text == "latest":
        candidates = list(records)
    else:
        rec = try_get_ui_export_record_by_id(
            workspace_root=Path(workspace_root).resolve(),
            package_id=str(package_id),
            record_id=str(ui_export_record_id),
        )
        if rec is None:
            raise ValueError(f"未找到指定的 UI 导出记录：record_id={ui_export_record_id!r}")
        candidates = [rec]

    missing_best: set[str] = set()
    for rec in candidates:
        snapshot_path_text = str(rec.payload.get("ui_guid_registry_snapshot_path") or "").strip()
        if snapshot_path_text == "":
            continue
        snapshot_path = Path(snapshot_path_text).resolve()
        if not snapshot_path.is_file():
            continue
        mapping = load_ui_guid_registry_snapshot(Path(snapshot_path))
        missing = {k for k in required_keys if k not in mapping}
        if not missing:
            return rec, snapshot_path
        if not missing_best or len(missing) < len(missing_best):
            missing_best = set(missing)

    raise ValueError(
        "无法从 UI 导出记录中找到“包含所有所需 ui_key”的 registry snapshot，写回会失败。\n"
        f"- ui_export_record_id: {ui_export_record_id!r}\n"
        f"- required_keys_total(exclude_hidden): {len(required_keys)}\n"
        f"- best_missing_keys_total: {len(missing_best)}\n"
        + (f"- best_missing_keys(head): {sorted(missing_best, key=lambda t: t.casefold())[:20]}\n" if missing_best else "")
        + "建议：重新执行 UI 批量导出（包含本次节点图涉及的页面），确保生成最新的 ui_guid_registry_snapshot。"
    )


def _load_graph_variables_default_values_from_gil(
    *,
    gil_path: Path,
    graph_ids: Sequence[int],
    output_dir_name: str,
) -> Dict[int, Dict[str, Any]]:
    report = export_readable_graph_ir_from_gil_payload(
        Path(gil_path).resolve(),
        output_dir=Path(output_dir_name),
        node_data_index_path=resolve_default_node_data_index_path(),
        graph_ids=sorted({int(x) for x in graph_ids}),
        write_markdown=False,
        max_depth=16,
    )
    out_dir = Path(str(report.get("output_dir") or "")).resolve()
    index_path = Path(str(report.get("index") or "")).resolve()
    if not index_path.is_file():
        raise FileNotFoundError(f"graph ir index.json not found: {str(index_path)!r}")
    index_obj = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(index_obj, list):
        raise TypeError("graph ir index.json root must be list")

    out: Dict[int, Dict[str, Any]] = {}
    for item in index_obj:
        if not isinstance(item, dict):
            continue
        graph_id_int = item.get("graph_id_int")
        if not isinstance(graph_id_int, int):
            continue
        ir_rel = str(item.get("ir_json") or "").strip()
        if ir_rel == "":
            continue
        ir_path = (out_dir / ir_rel).resolve()
        if not ir_path.is_file():
            raise FileNotFoundError(f"graph ir json not found: {str(ir_path)!r}")
        graph_ir = json.loads(ir_path.read_text(encoding="utf-8"))
        if not isinstance(graph_ir, dict):
            raise TypeError(f"graph ir json root must be dict: {str(ir_path)!r}")
        vars_list = graph_ir.get("graph_variables") or []
        if not isinstance(vars_list, list):
            vars_list = []
        var_defaults: Dict[str, Any] = {}
        for v in vars_list:
            if not isinstance(v, dict):
                continue
            name = str(v.get("name") or "").strip()
            if name == "":
                continue
            # 保留“原样 default_value”（可能为 int/float/bool/str/list/dict/null）
            var_defaults[name] = v.get("default_value")
        out[int(graph_id_int)] = var_defaults
    return out


def _patch_graph_model_json_graph_variables_inplace(
    *,
    graph_model_json_object: Dict[str, Any],
    preserved_default_values_by_var_name: Dict[str, Any],
) -> Dict[str, Any]:
    """
    将 GraphModel(JSON) 中的 graph_variables[*].default_value 按 var_name 覆盖为 preserved 值。

    注意：
    - 只覆盖名字命中的变量；
    - 其余字段（variable_type/description/is_exposed 等）以本地 Graph Code 为准。
    """
    data = graph_model_json_object.get("data")
    if not isinstance(data, dict):
        return {"patched_total": 0, "reason": "graph_model_json_missing_data"}
    raw_vars = data.get("graph_variables")
    if not isinstance(raw_vars, list):
        return {"patched_total": 0, "reason": "graph_model_json_missing_graph_variables"}

    patched = 0
    for item in raw_vars:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name == "":
            continue
        if name not in preserved_default_values_by_var_name:
            continue
        item["default_value"] = copy.deepcopy(preserved_default_values_by_var_name[name])
        patched += 1

    return {"patched_total": int(patched)}


def _ensure_user_output_dir_claude_md(
    user_output_dir: Path,
    *,
    note_file_names: Sequence[str],
    preserve_graph_variable_default_values: bool,
) -> None:
    """
    按用户约束：若目录无 claude.md 则创建；随后更新为“用途/状态/注意事项”的实时描述（不写修改历史）。
    """
    d = Path(user_output_dir).resolve()
    d.mkdir(parents=True, exist_ok=True)
    claude_path = (d / "claude.md").resolve()

    # 读一次（满足“修改前阅读”要求；内容不强依赖）
    if claude_path.is_file():
        _ = claude_path.read_text(encoding="utf-8")

    lines: List[str] = []
    lines.append("## 目录用途")
    lines.append("- 存放用户侧需要交付/验证的 `.gil` 存档文件，以及由本工具生成的“旁路更新版”文件。")
    lines.append("")
    lines.append("## 当前状态")
    for name in list(note_file_names or []):
        stem = str(name or "").strip()
        if stem == "":
            continue
        lines.append(f"- `{stem}`：目录内现有/生成的存档文件。")
    lines.append("")
    lines.append("## 注意事项")
    if bool(preserve_graph_variable_default_values):
        lines.append(
            "- 更新节点图时，GraphVariables（节点图变量表）的 **增删改** 以本地 Graph Code 为准；"
            "但对“同名变量”的 default_value 会保留目标 `.gil` 现有值（不覆盖用户改动）。"
        )
    else:
        lines.append(
            "- 更新节点图时，GraphVariables（节点图变量表）的 **增删改**（含 default_value）以本地 Graph Code 为准；"
            "会覆盖目标 `.gil` 中同名变量的 default_value。"
        )
    lines.append("- 建议保留原始 `.gil` 不直接覆盖：先生成旁路文件，确认无误后再人工替换/发布。")
    lines.append("")
    lines.append("---")
    lines.append("注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。")
    lines.append("")
    claude_path.write_text("\n".join(lines), encoding="utf-8")


def _compare_preserved_graph_variable_defaults(
    *,
    input_defaults_by_graph_id_int: Dict[int, Dict[str, Any]],
    output_defaults_by_graph_id_int: Dict[int, Dict[str, Any]],
    focus_graph_ids: Sequence[int],
) -> None:
    """
    校验：对每张目标图，输出产物中“同名变量”的 default_value 必须与输入 .gil 一致。
    """
    diffs: List[Dict[str, Any]] = []
    for gid in list(focus_graph_ids or []):
        in_vars = input_defaults_by_graph_id_int.get(int(gid), {})
        out_vars = output_defaults_by_graph_id_int.get(int(gid), {})
        if not isinstance(in_vars, dict) or not isinstance(out_vars, dict):
            continue
        for name, in_val in in_vars.items():
            if name not in out_vars:
                # 变量被本地节点图移除：不视为“覆盖值”，因此不报错
                continue
            out_val = out_vars.get(name)
            if out_val != in_val:
                diffs.append(
                    {
                        "graph_id_int": int(gid),
                        "var_name": str(name),
                        "input_default_value": in_val,
                        "output_default_value": out_val,
                    }
                )

    if diffs:
        raise ValueError("检测到写回后节点图变量 default_value 被覆盖/漂移（应以输入 .gil 为准）：\n" + json.dumps(diffs[:50], ensure_ascii=False, indent=2))


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    default_graph_code_dir = repo_root() / "assets" / "资源库" / "项目存档" / "测试项目" / "节点图" / "server" / "实体节点图" / "第七关"
    default_project_archive = repo_root() / "assets" / "资源库" / "项目存档" / "测试项目"
    default_template_gil = (
        ugc_file_tools_root()
        / "builtin_resources"
        / "template_library"
        / "test2_server_writeback_samples"
        / "autowire_templates_test2_server_direct_export_v2.gil"
    )
    default_template_library_dir = default_template_gil.parent
    default_mapping_json = ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"

    parser = argparse.ArgumentParser(
        description="将本地 Graph Code 写回覆盖到目标 .gil，并在输入文件同目录生成旁路输出（可选保留同名 GraphVariables.default_value）。"
    )
    parser.add_argument("--input-gil", required=True, help="目标 .gil（用户侧存档）")
    parser.add_argument(
        "--graph-code-dir",
        default=str(default_graph_code_dir),
        help="本地 Graph Code 目录（默认：测试项目/第七关 server 实体节点图目录；扫描 *.py）",
    )
    parser.add_argument(
        "--project-archive",
        default=str(default_project_archive),
        help="Graph_Generater 项目存档根目录（用于解析 Graph Code 依赖与复合节点/资源）",
    )
    parser.add_argument(
        "--output-user-gil",
        default="",
        help="输出到用户路径（默认：在 input-gil 同目录生成 <stem>__synced_graph_code__<mode>.gil）",
    )
    parser.add_argument(
        "--server-template-gil",
        default=str(default_template_gil),
        help="server 节点图写回模板 .gil（用于克隆节点/record 样本）",
    )
    parser.add_argument(
        "--server-template-library-dir",
        default=str(default_template_library_dir),
        help="server 模板库目录（递归扫描 *.gil 以补齐节点样本）",
    )
    parser.add_argument(
        "--mapping-json",
        default=str(default_mapping_json),
        help="node type semantic map（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument(
        "--skip-precheck",
        action="store_true",
        help="跳过写回前/后预检（不推荐；默认会跑节点模板覆盖预检 + 节点图变量写回合约校验）。",
    )
    parser.add_argument(
        "--ui-export-record",
        default="latest",
        help=(
            "用于回填 ui_key: 占位符的 UI 导出记录（record_id 或 latest）。"
            "默认 latest：自动选择一个包含所需 ui_key 的 ui_guid_registry_snapshot。"
        ),
    )
    parser.add_argument(
        "--ui-guid-registry-snapshot",
        default="",
        help=(
            "可选：显式指定 ui_guid_registry_snapshot 路径（优先级高于 --ui-export-record）。"
            "用于在你已知快照文件时，强制写回使用该快照。"
        ),
    )
    parser.add_argument(
        "--preserve-graph-variable-default-values",
        dest="preserve_graph_variable_default_values",
        action="store_true",
        help="保留目标 .gil 中同名 GraphVariables 的 default_value（默认开启）。",
    )
    parser.add_argument(
        "--overwrite-graph-variable-default-values",
        dest="preserve_graph_variable_default_values",
        action="store_false",
        help="不保留目标 .gil 的 default_value：同名变量 default_value 以本地 Graph Code 为准（仍会同步增删变量）。",
    )
    parser.add_argument(
        "--skip-missing-graphs",
        action="store_true",
        help="当本地节点图在目标 .gil 中找不到同名图时跳过（默认 fail-fast 抛错）。",
    )
    parser.set_defaults(preserve_graph_variable_default_values=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    input_gil = Path(str(args.input_gil)).resolve()
    if not input_gil.is_file():
        raise FileNotFoundError(str(input_gil))

    graph_code_dir = _resolve_path_under_repo_root(str(args.graph_code_dir))
    project_archive = _resolve_path_under_repo_root(str(args.project_archive))
    if not project_archive.is_dir():
        raise FileNotFoundError(str(project_archive))

    template_gil = _resolve_path_under_repo_root(str(args.server_template_gil))
    template_library_dir = _resolve_path_under_repo_root(str(args.server_template_library_dir))
    mapping_json = _resolve_path_under_repo_root(str(args.mapping_json))
    if not template_gil.is_file():
        raise FileNotFoundError(str(template_gil))
    if not template_library_dir.is_dir():
        raise FileNotFoundError(str(template_library_dir))
    if not mapping_json.is_file():
        raise FileNotFoundError(str(mapping_json))

    graph_code_files = _iter_graph_code_files_in_dir(graph_code_dir)
    if not graph_code_files:
        raise FileNotFoundError(f"graph_code_dir 下未找到任何 *.py：{str(graph_code_dir)!r}")

    # === 目标 .gil：graph_name -> graph_id_int（用于定位覆盖目标图） ===
    graph_id_by_name = _build_graph_name_to_id_map_from_gil(input_gil)

    missing_names: List[str] = []
    targets: List[_TargetGraph] = []
    for f in graph_code_files:
        name = _scan_graph_name_from_graph_code_file(f)
        gid = graph_id_by_name.get(str(name))
        if gid is None:
            if bool(args.skip_missing_graphs):
                continue
            missing_names.append(str(name))
            continue
        targets.append(_TargetGraph(graph_code_file=Path(f).resolve(), graph_name=str(name), target_graph_id_int=int(gid)))

    if missing_names:
        raise ValueError(
            "以下本地节点图（按 graph_name 匹配）未在目标 .gil 中找到同名图，无法执行节点图同步：\n- "
            + "\n- ".join(sorted(set(missing_names)))
        )
    if not targets:
        raise ValueError("未选中任何可写回的节点图（可能全部被 --skip-missing-graphs 跳过）。")

    focus_graph_ids = [int(t.target_graph_id_int) for t in targets]

    preserve_defaults = bool(args.preserve_graph_variable_default_values)

    # === 从输入 .gil 提取“GraphVariables.default_value（真源）”（可选） ===
    input_defaults_by_graph_id_int: Dict[int, Dict[str, Any]] = {}
    if bool(preserve_defaults):
        input_defaults_by_graph_id_int = _load_graph_variables_default_values_from_gil(
            gil_path=input_gil,
            graph_ids=focus_graph_ids,
            output_dir_name=f"_tmp_preserve_vars__input_{input_gil.stem}",
        )

    # === Graph_Generater：Graph Code -> GraphModel(JSON) ===
    gg_root = _resolve_graph_generater_root(project_archive)
    package_id = str(project_archive.name).strip()
    if package_id == "":
        raise ValueError("package_id 不能为空（project_archive 目录名为空）")
    gg_ctx = _prepare_graph_generater_context(gg_root=gg_root, package_id=package_id)

    template_graph_id_int = _pick_template_graph_id_int(template_gil=template_gil, expected_scope="server")

    # === UI registry snapshot：用于解析 ui_key 占位符 ===
    ui_snapshot_path: Path | None = None
    ui_export_record: UIExportRecord | None = None
    ui_snapshot_path_text = str(args.ui_guid_registry_snapshot or "").strip()
    if ui_snapshot_path_text != "":
        ui_snapshot_path = Path(ui_snapshot_path_text).resolve()
        if not ui_snapshot_path.is_file():
            raise FileNotFoundError(str(ui_snapshot_path))
    else:
        required_ui_keys = _collect_required_ui_keys_from_graph_code_files(graph_code_files=list(graph_code_files))
        required_ui_keys = {k for k in required_ui_keys if not _is_optional_hidden_ui_key(k)}
        if required_ui_keys:
            ui_export_record, ui_snapshot_path = _pick_ui_export_record_and_snapshot_for_graph_code(
                workspace_root=Path(gg_root).resolve(),
                package_id=str(package_id),
                graph_code_files=list(graph_code_files),
                ui_export_record_id=str(args.ui_export_record),
            )

    # out 内输出文件名（最终会复制到用户路径）
    mode_tag = "preserve_defaults" if bool(preserve_defaults) else "overwrite_defaults"
    out_gil_name = f"{input_gil.stem}__synced_graph_code__{mode_tag}.gil"
    out_gil_path = resolve_output_file_path_in_out_dir(Path(out_gil_name))

    # 用户侧输出路径（默认：input 同目录）
    if str(args.output_user_gil or "").strip() != "":
        output_user_gil = Path(str(args.output_user_gil)).resolve()
    else:
        output_user_gil = (input_gil.parent / out_gil_name).resolve()

    # 写入前：确保用户输出目录存在 claude.md（并更新为实时状态描述）
    _ensure_user_output_dir_claude_md(
        output_user_gil.parent,
        note_file_names=[input_gil.name, output_user_gil.name],
        preserve_graph_variable_default_values=bool(preserve_defaults),
    )

    current_base = input_gil
    written_graphs: List[Dict[str, Any]] = []

    for i, t in enumerate(targets, start=1):
        # 1) export GraphModel JSON
        model_out = Path(f"{input_gil.stem}__sync_models") / f"server_{int(t.target_graph_id_int)}_{t.graph_name}.graph_model.json"
        export_report = _export_graph_model_json_from_graph_code_with_context(
            ctx=gg_ctx,
            graph_code_file=Path(t.graph_code_file),
            output_json_file=model_out,
            ui_export_record_id=(
                ui_export_record.record_id
                if ui_export_record is not None
                else (str(args.ui_export_record).strip() or None)
            ),
            ui_guid_registry_snapshot_path=Path(ui_snapshot_path) if ui_snapshot_path is not None else None,
        )
        graph_model_json_path = Path(str(export_report["output_json"])).resolve()

        # 2) patch graph_variables.default_value（可选：保留用户存档的 default_value；变量增删始终以本地 Graph Code 为准）
        patched_path = graph_model_json_path
        patch_report: Dict[str, Any] = {"patched_total": 0, "skipped": True, "reason": "disabled_by_caller"}
        preserved_defaults: Dict[str, Any] = {}
        if bool(preserve_defaults):
            graph_json_object = json.loads(graph_model_json_path.read_text(encoding="utf-8"))
            if not isinstance(graph_json_object, dict):
                raise TypeError("graph_model_json must be dict")

            preserved_defaults = input_defaults_by_graph_id_int.get(int(t.target_graph_id_int), {})
            if not isinstance(preserved_defaults, dict):
                preserved_defaults = {}

            patch_report = _patch_graph_model_json_graph_variables_inplace(
                graph_model_json_object=graph_json_object,
                preserved_default_values_by_var_name=preserved_defaults,
            )

            patched_path = graph_model_json_path.parent / f"{graph_model_json_path.stem}.preserve_defaults.json"
            patched_path.write_text(json.dumps(graph_json_object, ensure_ascii=False, indent=2), encoding="utf-8")

        # 3) writeback to gil (replace existing graph_id_int)
        write_report, precheck_report_path, postcheck_report_path = run_precheck_and_write_and_postcheck(
            graph_model_json_path=Path(patched_path),
            template_gil_path=Path(template_gil),
            base_gil_path=Path(current_base),
            template_library_dir=Path(template_library_dir),
            output_gil_path=Path(out_gil_path.name),  # 强制 out/
            template_graph_id_int=int(template_graph_id_int),
            new_graph_name=str(t.graph_name),
            new_graph_id_int=int(t.target_graph_id_int),
            mapping_path=Path(mapping_json),
            graph_generater_root=Path(gg_root),
            skip_precheck=bool(args.skip_precheck),
            auto_sync_ui_custom_variable_defaults=True,
            # preserve 模式：对“输入 .gil 已存在的同名变量”排除 UI registry 自动回填，确保 default_value 严格保留；
            # 但对“本地新增变量”仍允许 auto-fill（例如 新增布局索引 变量默认 0，需要回填为真实 GUID）。
            auto_fill_graph_variable_defaults_from_ui_registry=True,
            ui_registry_autofill_excluded_graph_variable_names=(
                set(preserved_defaults.keys()) if bool(preserve_defaults) else None
            ),
        )

        output_gil_written = Path(str(write_report.get("output_gil") or "")).resolve()
        if not output_gil_written.is_file():
            raise FileNotFoundError(f"写回产物不存在：{str(output_gil_written)!r}")

        written_graphs.append(
            {
                "index": int(i),
                "graph_name": str(t.graph_name),
                "graph_id_int": int(t.target_graph_id_int),
                "graph_code_file": str(Path(t.graph_code_file).resolve()),
                "graph_model_json": str(graph_model_json_path),
                "graph_model_json_patched": str(patched_path),
                "graph_variables_patch": dict(patch_report),
                "write_report": dict(write_report),
                "precheck_report": str(precheck_report_path) if precheck_report_path is not None else None,
                "postcheck_report": str(postcheck_report_path) if postcheck_report_path is not None else None,
            }
        )

        current_base = output_gil_written

    final_out_gil = Path(current_base).resolve()
    if not final_out_gil.is_file():
        raise FileNotFoundError(f"final output gil not found: {str(final_out_gil)!r}")

    # === 再次导出 output 的 graph_variables，核对“默认值保持一致”（仅 preserve 模式） ===
    if bool(preserve_defaults):
        output_defaults_by_graph_id_int = _load_graph_variables_default_values_from_gil(
            gil_path=final_out_gil,
            graph_ids=focus_graph_ids,
            output_dir_name=f"_tmp_preserve_vars__output_{input_gil.stem}",
        )
        _compare_preserved_graph_variable_defaults(
            input_defaults_by_graph_id_int=input_defaults_by_graph_id_int,
            output_defaults_by_graph_id_int=output_defaults_by_graph_id_int,
            focus_graph_ids=focus_graph_ids,
        )

    # === 复制到用户路径（旁路生成） ===
    output_user_gil.parent.mkdir(parents=True, exist_ok=True)
    output_user_gil.write_bytes(final_out_gil.read_bytes())

    # 更新用户目录 claude.md（实时状态）
    _ensure_user_output_dir_claude_md(
        output_user_gil.parent,
        note_file_names=[input_gil.name, output_user_gil.name],
        preserve_graph_variable_default_values=bool(preserve_defaults),
    )

    summary_path = resolve_output_file_path_in_out_dir(Path(f"{input_gil.stem}__synced_graph_code__{mode_tag}.summary.json"))
    summary_path.write_text(
        json.dumps(
            {
                "input_gil": str(input_gil),
                "graph_code_dir": str(graph_code_dir),
                "project_archive": str(project_archive),
                "preserve_graph_variable_default_values": bool(preserve_defaults),
                "template_gil": str(template_gil),
                "template_library_dir": str(template_library_dir),
                "mapping_json": str(mapping_json),
                "out_gil": str(final_out_gil),
                "output_user_gil": str(output_user_gil),
                "graphs_written": written_graphs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 80)
    print("节点图覆盖写回完成：")
    print(f"- input_gil: {str(input_gil)}")
    print(f"- graph_code_dir: {str(graph_code_dir)}")
    print(f"- preserve_graph_variable_default_values: {bool(preserve_defaults)}")
    print(f"- graphs_written: {len(written_graphs)}")
    print(f"- out_gil: {str(final_out_gil)}")
    print(f"- output_user_gil: {str(output_user_gil)}")
    print(f"- summary: {str(summary_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



