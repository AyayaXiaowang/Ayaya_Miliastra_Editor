from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Dict, Optional

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


ProgressCallback = Callable[[int, int, str], None]

_INFRA_GAP_LABEL_MISSING_SECTION11 = "缺 root4/11（初始阵营基础设施段）"
_INFRA_GAP_LABEL_MISSING_SECTION11_FACTION_ENTRIES = "root4/11 缺阵营 entries"
_INFRA_GAP_LABEL_MISSING_SECTION11_FACTION_FIELD13 = "root4/11 阵营 entries 存在缺 key=13"
_INFRA_GAP_LABEL_MISSING_SECTION35 = "缺 root4/35（默认分组段）"
_INFRA_GAP_LABEL_MISSING_SECTION35_DEFAULT_GROUPS = "root4/35 缺默认分组列表"
_INFRA_GAP_LABEL_MISSING_SECTION6 = "缺 root4/6（关键字段口径不完整）"
_INFRA_GAP_LABEL_MISSING_SECTION22 = "缺 root4/22（关键字段口径不完整）"
_INFRA_GAP_LABEL_MISSING_SECTION2 = "缺 root4/2（存档显示名/标识）"


def _format_infrastructure_gaps_for_progress(gaps: object) -> str:
    """将基础设施缺口摘要格式化为进度展示文本。"""
    # 说明：避免在模块顶层强依赖 gil 域类型；这里使用 duck-typing 读取属性。
    labels: list[str] = []
    if bool(getattr(gaps, "missing_section11", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION11)
    if bool(getattr(gaps, "missing_section11_faction_entries", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION11_FACTION_ENTRIES)
    if bool(getattr(gaps, "missing_section11_faction_field13", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION11_FACTION_FIELD13)
    if bool(getattr(gaps, "missing_section35", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION35)
    if bool(getattr(gaps, "missing_section35_default_groups", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION35_DEFAULT_GROUPS)
    if bool(getattr(gaps, "missing_section6", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION6)
    if bool(getattr(gaps, "missing_section22", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION22)
    if bool(getattr(gaps, "missing_section2", False)):
        labels.append(_INFRA_GAP_LABEL_MISSING_SECTION2)
    if not labels:
        return "未发现缺口"
    return "；".join(labels)


def _format_infrastructure_bootstrap_result_for_progress(report: object) -> str:
    """将基础设施补齐结果格式化为进度展示文本。"""
    if not bool(getattr(report, "changed", False)):
        return "无需补齐（未发生写盘）"

    patched: list[str] = []
    patched_root4_11_faction_field13_count = int(getattr(report, "patched_root4_11_faction_field13_count", 0))
    if patched_root4_11_faction_field13_count > 0:
        patched.append(f"root4/11：补齐阵营 entries 的 key=13 共 {patched_root4_11_faction_field13_count} 条")
    elif bool(getattr(report, "patched_root4_11_copied_from_bootstrap", False)):
        patched.append("root4/11：整段复制自 bootstrap")
    if bool(getattr(report, "patched_root4_35_copied_from_bootstrap", False)) or bool(
        getattr(report, "patched_root4_35_default_groups_copied", False)
    ):
        groups_len = getattr(report, "patched_root4_35_default_groups_len", None)
        if groups_len is None:
            patched.append("root4/35：补齐默认分组列表")
        else:
            patched.append(f"root4/35：补齐默认分组 {int(groups_len)} 组")
    if bool(getattr(report, "patched_root4_6_copied_from_bootstrap", False)):
        patched.append("root4/6：补齐关键字段口径（item17['3']['5']）")
    if bool(getattr(report, "patched_root4_22_copied_from_bootstrap", False)):
        patched.append("root4/22：补齐关键字段口径（含 key=1/2）")
    if bool(getattr(report, "patched_root4_2_copied_from_bootstrap", False)):
        patched.append("root4/2：补齐存档显示名/标识")

    if not patched:
        return "补齐完成（changed=True 但未记录到具体 patched_* 字段）"
    return "；".join(patched)


def _emit_progress(cb: ProgressCallback | None, current: int, total: int, label: str) -> None:
    if cb is None:
        return
    cb(int(current), int(total), str(label or ""))


def _atomic_copy2(*, src: Path, dst: Path) -> None:
    """
    原子复制：先 copy 到同目录临时文件，再用 os.replace 覆盖目标，避免：
    - 大文件复制过程中被其它进程读到“半文件”导致报错/无法解析；
    - 复制中断时把目标文件直接写坏。

    说明：
    - 不使用 try/except：失败直接抛出；可能残留 tmp 文件（可手工清理）。
    """
    src_path = Path(src).resolve()
    dst_path = Path(dst).resolve()
    if not src_path.is_file():
        raise FileNotFoundError(str(src_path))

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    # 临时文件必须与目标在同一目录，才能保证 replace 原子性。
    tmp_path = dst_path.with_name(f"{dst_path.name}.tmp.{uuid.uuid4().hex}")
    if tmp_path.exists():
        tmp_path.unlink()

    shutil.copy2(src_path, tmp_path)
    os.replace(tmp_path, dst_path)


@dataclass(frozen=True, slots=True)
class ProjectWritebackPlan:
    project_archive_path: Path
    input_gil_file_path: Path
    output_gil_user_path: Path

    export_templates: bool
    export_instances: bool
    export_structs: bool
    export_signals: bool
    export_graphs: bool
    export_ui_widget_templates: bool

    # === selection manifest（可选：按资源集合过滤写回范围） ===
    selected_struct_ids: list[str] | None = None
    selected_ingame_struct_ids: list[str] | None = None
    selected_signal_ids: list[str] | None = None
    # 自定义变量（注册表）：按 owner_ref+variable_id 精确选择（可跨：关卡实体/玩家/第三方 owner）。
    selected_custom_variable_refs: list[dict[str, str]] | None = None
    # 关卡实体（root4/5/1 name=关卡实体）需要写回的“自定义变量（LevelVariableDefinition.variable_id）”选择列表。
    # - selection-json 仅携带 variable_id 列表；写回阶段再按 variable_id 查表并写入实体 override_variables(group1)
    # - None/空：不做额外写回
    selected_level_custom_variable_ids: list[str] | None = None
    selected_graph_code_files: list[Path] | None = None
    selected_template_json_files: list[Path] | None = None
    selected_instance_json_files: list[Path] | None = None
    graph_source_roots: list[Path] | None = None  # project/shared，用于“稳定分配 graph_id_int”
    # UI 写回选择过滤：仅写回这些 layout_name（对应 `UI源码/<stem>.html` 的 stem；bundle 文件名同 stem）。
    # - None/空：不做过滤；写回全部 Workbench bundle（或 raw_template）。
    selected_ui_layout_names: list[str] | None = None
    # 节点图写回时的“同名节点图冲突策略”（导出中心交互用；按 graph_code_file 精确匹配）。
    # - action="overwrite"：默认行为（按 (scope, graph_name) 复用 base 中同名图的 graph_id_int 并替换写回）
    # - action="add"：以 new_graph_name 作为输出名写回，避免命中“同名复用”，从而写入为新图
    # - action="skip"：跳过该图
    node_graph_conflict_resolutions: list[dict[str, str]] | None = None
    # 元件库模板写回时的“同名模板冲突策略”（导出中心交互用；按 template_json_file 精确匹配）。
    # - action="overwrite"：若 base `.gil` 已存在同名模板，则复用其 template_id_int 覆盖写回，避免同名重复
    # - action="add"：以 new_template_name 作为输出名写回（并确保 template_id_int 不冲突），避免命中同名覆盖
    # - action="skip"：跳过该模板
    template_conflict_resolutions: list[dict[str, str]] | None = None
    # 实体摆放写回时的“同名实体冲突策略”（导出中心交互用；按 instance_json_file 精确匹配）。
    # - action="overwrite"：若 base `.gil` 已存在同名实体，则复用其 instance_id_int 覆盖写回，避免同名重复
    # - action="add"：以 new_instance_name 作为输出名写回（instance_id_int 仍以 InstanceConfig 为准），避免同名重复
    # - action="skip"：跳过该实体
    instance_conflict_resolutions: list[dict[str, str]] | None = None

    templates_mode: str = "overwrite"  # "merge" | "overwrite"
    include_placeholder_templates: bool = False

    instances_mode: str = "overwrite"  # "merge" | "overwrite"

    struct_mode: str = "merge"  # "merge" | "overwrite"

    signals_param_build_mode: str = "semantic"  # "semantic" | "template"
    signals_template_gil: Path | None = None
    signals_bootstrap_gil: Path | None = None
    # 当 base `.gil` 没有任何信号且选择 0x6000/0x6080 口径时，是否写入“占位无参信号”（常见名：新建的没有参数的信号）。
    # - False（默认）：不写入占位信号 entry，但预留其应占用的 node_def_id/端口块（更干净的导出产物）
    # - True：写入占位信号 entry（兼容旧口径/对照样本）
    signals_emit_reserved_placeholder_signal: bool = False

    graphs_scope: str = "all"  # "all" | "server" | "client"
    graph_scan_all: bool = True
    graph_strict_graph_code_files: bool = False
    graph_output_model_dir_name: str = ""
    graph_server_template_gil: Path | None = None
    graph_server_template_library_dir: Path | None = None
    graph_client_template_gil: Path | None = None
    graph_client_template_library_dir: Path | None = None
    graph_mapping_json: Path | None = None
    prefer_signal_specific_type_id: bool = False  # 兼容参数：信号节点 type_id 提升为 0x6000xxxx/0x6080xxxx 的策略当前为默认/固定；该字段保留旧口径

    ui_widget_templates_mode: str = "merge"  # "merge" | "overwrite"
    ui_auto_sync_custom_variables: bool = True  # 是否自动同步写入 UI 引用到的实体自定义变量（关卡/玩家自身）
    # UI Workbench bundle（UI源码/__workbench_out__/*.ui_bundle.json）写回时的“同名布局冲突策略”：
    # - action="overwrite"：复用 base 中同名布局 GUID，写入到同一布局（默认行为）
    # - action="add"：创建一个新布局（new_layout_name 必填）
    # - action="skip"：跳过该 bundle（不写回该布局）
    #
    # 约定：该字段仅对“Workbench bundle 写回”生效；当存在 raw_template 时会走 raw_template 写回并忽略此字段。
    ui_layout_conflict_resolutions: list[dict[str, str]] | None = None
    ui_export_record_id: str | None = None  # 可选：指定 UI 导出记录（record_id 或 latest），用于节点图 ui_key 回填
    # 可选：参考 `.gil` 文件，用于回填节点图中的 entity_key/component_key 占位符（按名称匹配，取第一个）。
    # 若不提供：节点图写回会默认使用 input_gil_file_path 作为参考（通常就是用户选择的 base gil）。
    id_ref_gil_file: Path | None = None
    # 可选：entity_key/component_key 占位符手动覆盖映射 JSON（占位符 name → ID）。
    id_ref_overrides_json_file: Path | None = None


def _dedupe_text_list_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in list(items or []):
        text = str(item or "").strip()
        if text == "":
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _collect_signal_ids_from_graph_model_payload(*, graph_model_payload: object) -> set[str]:
    out: set[str] = set()
    nodes = graph_model_payload.get("nodes") if isinstance(graph_model_payload, dict) else None
    if not isinstance(nodes, list):
        return out
    for node in nodes:
        if not isinstance(node, dict):
            continue
        input_constants = node.get("input_constants")
        if not isinstance(input_constants, dict):
            continue
        signal_id = input_constants.get("__signal_id")
        if not isinstance(signal_id, str):
            continue
        sid = str(signal_id).strip()
        if sid != "":
            out.add(sid)
    return out


def _collect_graph_signal_ids_for_plan(*, project_root: Path, plan: ProjectWritebackPlan) -> list[str]:
    from ugc_file_tools.project_archive_importer.node_graphs_importer import (
        build_graph_specs as _build_graph_specs,
        build_graph_specs_by_scanning_roots as _build_graph_specs_by_scanning_roots,
        build_overview_object_by_scanning_node_graph_dir as _build_overview_object_by_scanning_node_graph_dir,
        export_graph_model_json_from_graph_code_with_context as _export_graph_model_json_from_graph_code_with_context,
        prepare_graph_generater_context as _prepare_graph_generater_context,
        resolve_graph_generater_root as _resolve_graph_generater_root,
    )
    from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir
    from ugc_file_tools.node_graph_semantics.signal_usage import collect_static_signal_names_from_graph_model_payload
    from engine.graph.graph_code_parser import GraphParseError

    package_id = str(Path(project_root).resolve().name or "").strip()
    if package_id == "":
        raise ValueError("package_id 不能为空（项目存档目录名为空）")

    scope = str(plan.graphs_scope or "").strip().lower() or "all"
    if scope not in {"all", "server", "client"}:
        raise ValueError(f"unsupported graphs_scope: {scope!r}")
    include_server = scope in {"all", "server"}
    include_client = scope in {"all", "client"}

    explicit_files = [Path(p).resolve() for p in list(plan.selected_graph_code_files or []) if p is not None]
    explicit_files = [p for p in explicit_files if str(p)]
    if explicit_files:
        roots = [Path(project_root).resolve()]
        extra_roots = [Path(p).resolve() for p in list(plan.graph_source_roots or []) if p is not None]
        for r in extra_roots:
            if r not in roots:
                roots.append(r)

        all_specs = _build_graph_specs_by_scanning_roots(
            graph_source_roots=roots,
            include_server=bool(include_server),
            include_client=bool(include_client),
            strict_graph_code_files=bool(plan.graph_strict_graph_code_files),
        )
        by_file = {Path(s.graph_code_file).resolve(): s for s in all_specs}
        missing = [str(p) for p in explicit_files if Path(p).resolve() not in by_file]
        if missing:
            raise ValueError(f"显式写回的 graph_code_files 中包含无法识别为节点图的文件（缺少 graph_id metadata）：{missing}")
        specs = [by_file[Path(p).resolve()] for p in explicit_files]
    else:
        if bool(plan.graph_scan_all):
            overview_object = _build_overview_object_by_scanning_node_graph_dir(package_root=Path(project_root).resolve())
        else:
            overview_json = (Path(project_root).resolve() / f"{package_id}总览.json").resolve()
            if not overview_json.is_file():
                raise FileNotFoundError(f"overview_json 不存在：{str(overview_json)}")
            overview_object = json.loads(overview_json.read_text(encoding="utf-8"))
            if not isinstance(overview_object, dict):
                raise TypeError("overview_json root must be dict")

        specs = _build_graph_specs(
            package_root=Path(project_root).resolve(),
            overview_object=overview_object,
            include_server=bool(include_server),
            include_client=bool(include_client),
            strict_graph_code_files=bool(plan.graph_strict_graph_code_files),
        )

    if not specs:
        return []

    gg_root = _resolve_graph_generater_root(Path(project_root).resolve())
    gg_ctx = _prepare_graph_generater_context(gg_root=gg_root, package_id=str(package_id))

    probe_dir = resolve_output_dir_path_in_out_dir(Path(f"{package_id}_auto_signal_probe_models"))
    probe_dir.mkdir(parents=True, exist_ok=True)

    required_signal_ids: set[str] = set()
    required_signal_names: set[str] = set()
    for spec in specs:
        graph_model_json_path = (
            probe_dir / f"{str(spec.scope)}_{int(spec.assigned_graph_id_int)}_{Path(spec.graph_code_file).stem}.graph_model.json"
        )
        try:
            export_report = _export_graph_model_json_from_graph_code_with_context(
                ctx=gg_ctx,
                graph_code_file=Path(spec.graph_code_file),
                output_json_file=graph_model_json_path,
            )
        except GraphParseError:
            # 导出中心：单图严格解析失败不应阻断整体写回（跳过该图并继续探测其它图的信号依赖）。
            # 失败原因会在 node_graphs 写回阶段的 skipped_graphs 中体现。
            continue
        graph_json_object = json.loads(Path(export_report["output_json"]).read_text(encoding="utf-8"))
        if not isinstance(graph_json_object, dict):
            raise TypeError("graph_model_json must be dict")
        graph_payload = graph_json_object.get("data")
        required_signal_ids.update(_collect_signal_ids_from_graph_model_payload(graph_model_payload=graph_payload))
        required_signal_names.update(collect_static_signal_names_from_graph_model_payload(graph_model_payload=graph_payload))

    if required_signal_names:
        from ugc_file_tools.project_archive_importer.signals_importer import collect_signal_payloads_by_id_in_scope

        payloads_by_id, sources_by_id = collect_signal_payloads_by_id_in_scope(project_archive_path=Path(project_root).resolve())
        ids_by_name: dict[str, list[str]] = {}
        for sid, payload in payloads_by_id.items():
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("signal_name") or "").strip()
            if name == "":
                continue
            ids_by_name.setdefault(name, []).append(str(sid))

        missing_names = sorted([n for n in required_signal_names if n not in ids_by_name], key=lambda t: t.casefold())
        if missing_names:
            raise ValueError(f"节点图引用了未定义的信号（共享+项目作用域均未找到）：{missing_names}")

        # 同名消歧：尽量自动解决“同一信号名在作用域内出现多个 SIGNAL_ID”的常见场景。
        # - 优先规则（保守）：当存在 `__<package_id>` 形式的项目内别名/拷贝，与一个“非后缀版”并存时，
        #   自动选择“非后缀版”（通常为更稳定的 canonical id）。
        # - 次优规则：若仍冲突但候选中只有一个来自 shared_root（共享根），则选择 shared（优先公共定义）。
        # - 其余情况：仍 fail-fast，要求用户消除重名或显式选择 SIGNAL_ID。
        shared_root = (Path(gg_root) / "assets" / "资源库" / "共享").resolve()
        def _try_resolve_ambiguous_signal_id(*, signal_name: str, candidates: list[str]) -> str | None:
            cand = [str(x) for x in list(candidates or []) if str(x).strip() != ""]
            # 去重（保持顺序）
            seen: set[str] = set()
            deduped: list[str] = []
            for x in cand:
                k = x.casefold()
                if k in seen:
                    continue
                seen.add(k)
                deduped.append(x)
            cand = deduped
            if len(cand) <= 1:
                return cand[0] if cand else None

            suffix = f"__{package_id}"
            without_suffix = [sid for sid in cand if not str(sid).endswith(suffix)]
            with_suffix = [sid for sid in cand if str(sid).endswith(suffix)]
            if with_suffix and without_suffix and len(without_suffix) == 1:
                return str(without_suffix[0])

            # shared 优先：只有一个候选来自 shared_root 时才自动选择（避免 silently 选错）
            shared_sids: list[str] = []
            for sid in cand:
                src = sources_by_id.get(str(sid))
                if not isinstance(src, str) or src.strip() == "":
                    continue
                sp = Path(src).resolve()
                if sp == shared_root or shared_root in sp.parents:
                    shared_sids.append(str(sid))
            if len(shared_sids) == 1:
                return str(shared_sids[0])

            return None

        for name in sorted(list(required_signal_names), key=lambda t: t.casefold()):
            candidates = ids_by_name.get(str(name)) or []
            if len(candidates) <= 1:
                continue
            resolved = _try_resolve_ambiguous_signal_id(signal_name=str(name), candidates=list(candidates))
            if resolved is not None:
                ids_by_name[str(name)] = [str(resolved)]

        ambiguous: list[dict[str, object]] = []
        for name in sorted(list(required_signal_names), key=lambda t: t.casefold()):
            candidates = ids_by_name.get(name) or []
            if len(candidates) <= 1:
                continue
            choices: list[dict[str, str]] = []
            for sid in candidates:
                src = str(sources_by_id.get(sid) or "")
                choices.append({"signal_id": str(sid), "source": src})
            ambiguous.append({"signal_name": str(name), "candidates": choices})
        if ambiguous:
            raise ValueError(
                "节点图按信号名反查 SIGNAL_ID 时发现同名冲突（无法稳定决定写回哪一个定义）。\n"
                "请先消除同名信号定义（共享/项目内重名），或改为显式选择要写回的信号 ID。\n"
                f"conflicts={ambiguous}"
            )

        for name in required_signal_names:
            sid_list = ids_by_name.get(str(name)) or []
            if len(sid_list) == 1:
                required_signal_ids.add(str(sid_list[0]))

    return sorted(required_signal_ids, key=lambda text: text.casefold())


def run_project_writeback_to_gil(
    *,
    plan: ProjectWritebackPlan,
    progress_cb: ProgressCallback | None = None,
) -> Dict[str, object]:
    started_at = perf_counter()
    project_root = Path(plan.project_archive_path).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    package_id = str(project_root.name).strip()
    if package_id == "":
        raise ValueError("package_id 不能为空（项目存档目录名为空）")

    input_gil_path = Path(plan.input_gil_file_path).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_user_raw = Path(plan.output_gil_user_path)
    output_tool_path = resolve_output_file_path_in_out_dir(output_user_raw)
    output_tool_path.parent.mkdir(parents=True, exist_ok=True)

    output_user_abs: Optional[Path] = output_user_raw.resolve() if output_user_raw.is_absolute() else None
    # 允许输出路径与输入 base `.gil` 相同：写回产物会先落到 ugc_file_tools/out/，最后用原子 replace 覆盖用户目标文件。
    # 背景：导出中心/脚本场景常见“就地覆盖写回”（用户显式选择覆盖模式）。

    timings_sec: Dict[str, float] = {}

    # 节点图里使用信号时：自动从 GraphModel 的 `input_constants.__signal_id` 收集依赖并补齐到信号写回选择集。
    # 设计目标：用户仅勾选“节点图”时也能产出可在游戏侧正确识别信号端口的 `.gil`。
    auto_signal_ids_from_graphs: list[str] = []
    auto_enabled_signals_for_graphs = False
    effective_export_signals = bool(plan.export_signals)
    effective_selected_signal_ids = _dedupe_text_list_keep_order(
        [str(x or "").strip() for x in list(plan.selected_signal_ids or [])]
    )
    if bool(plan.export_graphs):
        t0 = perf_counter()
        auto_signal_ids_from_graphs = _collect_graph_signal_ids_for_plan(project_root=project_root, plan=plan)
        timings_sec["collect_graph_signal_ids_sec"] = float(perf_counter() - t0)
        if auto_signal_ids_from_graphs:
            effective_selected_signal_ids = _dedupe_text_list_keep_order(
                list(effective_selected_signal_ids) + list(auto_signal_ids_from_graphs)
            )
            if not bool(effective_export_signals):
                effective_export_signals = True
                auto_enabled_signals_for_graphs = True

    # 结构体导出会拆成两个子段（若存在）：
    # - 基础结构体：decoded-json 或 基础结构体/*.py
    # - 局内存档结构体：局内存档结构体/*.py
    has_basic_structs = False
    has_ingame_structs = False
    if bool(plan.export_structs):
        from ugc_file_tools.project_archive_importer.struct_definitions_importer import (
            collect_basic_struct_py_files_in_scope,
            iter_struct_decoded_files,
        )
        from ugc_file_tools.project_archive_importer.ingame_save_structs_importer import (
            collect_ingame_save_struct_py_files_in_scope,
        )

        t0 = perf_counter()
        has_basic_structs = bool(iter_struct_decoded_files(project_root) or collect_basic_struct_py_files_in_scope(project_root))
        has_ingame_structs = bool(collect_ingame_save_struct_py_files_in_scope(project_root))
        timings_sec["scan_project_structs_sec"] = float(perf_counter() - t0)

    effective_export_instances = bool(plan.export_instances)

    # ===== base `.gil` 基础设施段补齐（可选）=====
    # 说明：
    # - 已观测：部分“空存档 base”缺失 root4/11 的初始阵营互斥字段（entries 缺 key=13），以及 root4/35 的默认分组列表；
    # - 这类差异在编辑器侧可能仍可渲染，但官方侧更严格校验可能失败；
    # - 因此写回管线在必要时会先用一个 bootstrap `.gil` 补齐缺失字段（只补齐缺失，不覆盖 base 其它业务段）。
    from ugc_file_tools.gil.infrastructure_bootstrap import detect_gil_infrastructure_gaps_in_payload_root
    from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message

    t0 = perf_counter()
    payload_root_for_infra_scan = load_gil_payload_as_numeric_message(input_gil_path, max_depth=64, prefer_raw_hex_for_utf8=True)
    timings_sec["decode_base_gil_for_infra_scan_sec"] = float(perf_counter() - t0)

    t0 = perf_counter()
    infrastructure_gaps = detect_gil_infrastructure_gaps_in_payload_root(payload_root=payload_root_for_infra_scan)
    timings_sec["scan_infrastructure_gaps_sec"] = float(perf_counter() - t0)

    # 计算步数：每个导出段 + 复制步骤（若需要 copy）
    need_copy = output_user_abs is not None and output_user_abs.resolve() != output_tool_path.resolve()
    want_custom_variables = bool(plan.selected_custom_variable_refs) or bool(plan.selected_level_custom_variable_ids)

    # 基础设施补齐策略（避免“仅写回节点图”时意外改动 base 其它段）：
    # - 当本次仅写回节点图（以及为节点图自动启用的信号写回）时：跳过基础设施补齐，只展示扫描缺口。
    # - 当本次写回包含其它资源段（模板/实体/UI/结构体/自定义变量/显式信号等）时：按缺口检测结果决定是否补齐。
    is_graph_only_writeback = bool(plan.export_graphs) and not (
        bool(plan.export_templates)
        or bool(effective_export_instances)
        or bool(want_custom_variables)
        or bool(plan.export_structs)
        or bool(plan.export_ui_widget_templates)
        or (bool(plan.export_signals) and not bool(auto_enabled_signals_for_graphs))
    )
    need_infrastructure_bootstrap = bool(infrastructure_gaps.needs_bootstrap) and (not bool(is_graph_only_writeback))
    total_steps = 0
    if need_infrastructure_bootstrap:
        total_steps += 1
    if bool(plan.export_templates):
        total_steps += 1
    if bool(effective_export_instances):
        total_steps += 1
    if want_custom_variables:
        total_steps += 1
    if bool(plan.export_structs):
        if has_basic_structs:
            total_steps += 1
        if has_ingame_structs:
            total_steps += 1
    if bool(effective_export_signals):
        total_steps += 1
    if bool(plan.export_graphs):
        total_steps += 1
    if bool(plan.export_ui_widget_templates):
        total_steps += 1
    if need_copy:
        total_steps += 1

    if total_steps <= 0:
        raise ValueError("未选择任何写回内容（export_* 均为 False）")

    current_step = 0
    _emit_progress(progress_cb, current_step, total_steps, "准备写回…")

    current_input = input_gil_path
    steps: list[dict[str, object]] = []
    report: Dict[str, object] = {
        "project_archive": str(project_root),
        "input_gil": str(input_gil_path),
        "output_gil": str(output_tool_path),
        "output_gil_user": (str(output_user_abs) if output_user_abs is not None else str(output_user_raw)),
        "steps": steps,
    }

    # ===== 预检：节点图 mount 依赖（尽早提示缺失映射；不阻断写回）=====
    if bool(plan.export_graphs):
        try:
            from ugc_file_tools.id_ref_from_gil import (
                build_id_ref_mappings_from_gil_file,
                build_id_ref_mappings_from_payload_root,
            )
            from ugc_file_tools.id_ref_overrides import apply_id_ref_overrides, load_id_ref_overrides_json_file
            from ugc_file_tools.project_archive_importer.node_graphs_importer import (
                build_graph_specs,
                build_graph_specs_by_scanning_roots,
                build_overview_object_by_scanning_node_graph_dir,
            )
            from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.graph_mounts import (
                preflight_graph_mount_targets_for_graph_code_files,
            )

            scope = str(plan.graphs_scope or "").strip().lower() or "all"
            if scope not in {"all", "server", "client"}:
                raise ValueError(f"unsupported graphs_scope: {scope!r}")
            include_server = scope in {"all", "server"}
            include_client = scope in {"all", "client"}

            explicit_files = [Path(p).resolve() for p in list(plan.selected_graph_code_files or []) if p is not None]
            explicit_files = [p for p in explicit_files if str(p)]

            skip_graph_code_files_casefold: set[str] = set()
            raw_conflicts = list(plan.node_graph_conflict_resolutions or [])
            for idx, item in enumerate(raw_conflicts):
                if not isinstance(item, dict):
                    continue
                graph_code_file = str(item.get("graph_code_file") or "").strip()
                if graph_code_file == "":
                    continue
                action = str(item.get("action") or "").strip().lower()
                if action != "skip":
                    continue
                key = str(Path(graph_code_file).resolve()).casefold()
                skip_graph_code_files_casefold.add(key)

            if explicit_files:
                roots = [Path(project_root).resolve()]
                extra_roots = [Path(p).resolve() for p in list(plan.graph_source_roots or []) if p is not None]
                for r in extra_roots:
                    if r not in roots:
                        roots.append(r)
                all_specs = build_graph_specs_by_scanning_roots(
                    graph_source_roots=roots,
                    include_server=bool(include_server),
                    include_client=bool(include_client),
                    strict_graph_code_files=bool(plan.graph_strict_graph_code_files),
                )
                by_file = {Path(s.graph_code_file).resolve(): s for s in all_specs}
                graph_code_files = [Path(p).resolve() for p in explicit_files if Path(p).resolve() in by_file]
            else:
                if bool(plan.graph_scan_all):
                    overview_object = build_overview_object_by_scanning_node_graph_dir(package_root=Path(project_root).resolve())
                else:
                    overview_json = (Path(project_root).resolve() / f"{package_id}总览.json").resolve()
                    if not overview_json.is_file():
                        raise FileNotFoundError(f"overview_json 不存在：{str(overview_json)}")
                    overview_object = json.loads(overview_json.read_text(encoding="utf-8"))
                    if not isinstance(overview_object, dict):
                        raise TypeError("overview_json root must be dict")
                specs = build_graph_specs(
                    package_root=Path(project_root).resolve(),
                    overview_object=overview_object,
                    include_server=bool(include_server),
                    include_client=bool(include_client),
                    strict_graph_code_files=bool(plan.graph_strict_graph_code_files),
                )
                graph_code_files = [Path(s.graph_code_file).resolve() for s in list(specs or [])]

            if skip_graph_code_files_casefold:
                graph_code_files = [p for p in graph_code_files if str(p).casefold() not in skip_graph_code_files_casefold]

            id_ref_gil_path = Path(plan.id_ref_gil_file).resolve() if plan.id_ref_gil_file is not None else Path(current_input).resolve()
            if id_ref_gil_path == Path(input_gil_path).resolve():
                component_name_to_id, entity_name_to_guid = build_id_ref_mappings_from_payload_root(
                    payload_root=payload_root_for_infra_scan
                )
            else:
                component_name_to_id, entity_name_to_guid = build_id_ref_mappings_from_gil_file(gil_file_path=Path(id_ref_gil_path))

            id_ref_overrides_path = plan.id_ref_overrides_json_file
            if id_ref_overrides_path is not None:
                overrides = load_id_ref_overrides_json_file(Path(id_ref_overrides_path))
                component_name_to_id, entity_name_to_guid = apply_id_ref_overrides(
                    component_name_to_id=component_name_to_id or None,
                    entity_name_to_guid=entity_name_to_guid or None,
                    overrides=overrides,
                )

            preflight = preflight_graph_mount_targets_for_graph_code_files(
                graph_code_files=graph_code_files,
                entity_name_to_guid=entity_name_to_guid or None,
                component_name_to_id=component_name_to_id or None,
            )
            report["graph_mount_preflight"] = list(preflight)

            unresolved_entities: dict[str, set[str]] = {}
            unresolved_components: dict[str, set[str]] = {}
            scan_errors: list[dict[str, str]] = []
            for item in list(preflight or []):
                if not isinstance(item, dict):
                    continue
                graph_code_file = str(item.get("graph_code_file") or "").strip()
                scan_error = str(item.get("scan_error") or "").strip()
                if scan_error != "":
                    scan_errors.append({"graph_code_file": graph_code_file, "error": scan_error})
                    continue
                unresolved = item.get("unresolved_targets")
                if not isinstance(unresolved, list):
                    continue
                for t in unresolved:
                    if not isinstance(t, dict):
                        continue
                    kind = str(t.get("kind") or "").strip()
                    name = str(t.get("name") or "").strip()
                    if kind == "" or name == "" or graph_code_file == "":
                        continue
                    if kind == "entity":
                        unresolved_entities.setdefault(name, set()).add(graph_code_file)
                    elif kind == "component":
                        unresolved_components.setdefault(name, set()).add(graph_code_file)

            if scan_errors:
                _emit_progress(
                    progress_cb,
                    current_step,
                    total_steps,
                    f"[WARN] mount 预检：存在无法扫描 mount metadata 的节点图文件：count={int(len(scan_errors))}",
                )
            if unresolved_entities:
                names = sorted(list(unresolved_entities.keys()), key=lambda t: t.casefold())
                _emit_progress(
                    progress_cb,
                    current_step,
                    total_steps,
                    f"[WARN] mount 预检：缺失实体映射（将跳过挂载但继续导出）：{names}",
                )
            if unresolved_components:
                names = sorted(list(unresolved_components.keys()), key=lambda t: t.casefold())
                _emit_progress(
                    progress_cb,
                    current_step,
                    total_steps,
                    f"[WARN] mount 预检：缺失元件映射（将跳过挂载但继续导出）：{names}",
                )
        except Exception as e:
            report["graph_mount_preflight_error"] = f"{type(e).__name__}: {str(e)}"
            _emit_progress(
                progress_cb,
                current_step,
                total_steps,
                f"[WARN] mount 预检失败（不阻断写回）：{type(e).__name__}: {str(e)}",
            )

    if bool(need_infrastructure_bootstrap):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在补齐 base 基础设施段…")
        _emit_progress(
            progress_cb,
            current_step,
            total_steps,
            f"基础设施扫描结果：{_format_infrastructure_gaps_for_progress(infrastructure_gaps)}",
        )

        from ugc_file_tools.gil.infrastructure_bootstrap import bootstrap_gil_infrastructure_sections
        from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

        # 说明：这里不直接依赖 writeback_defaults 的导入（避免在极简环境中出现 stale bytecode/导入不一致），
        # 默认 bootstrap 源固定选择“内置 seed”（仅用于复制缺失基础设施字段，不会覆盖业务段）。
        bootstrap_path = (ugc_file_tools_builtin_resources_root() / "seeds" / "infrastructure_bootstrap.gil").resolve()
        t0 = perf_counter()
        step_report = bootstrap_gil_infrastructure_sections(
            input_gil_file_path=current_input,
            output_gil_file_path=output_tool_path,
            bootstrap_gil_file_path=bootstrap_path,
        )
        _emit_progress(
            progress_cb,
            current_step,
            total_steps,
            f"基础设施补齐结果：{_format_infrastructure_bootstrap_result_for_progress(step_report)}",
        )
        duration_sec = float(perf_counter() - t0)
        timings_sec["step_bootstrap_infrastructure_sec"] = duration_sec
        steps.append(
            {
                "kind": "bootstrap_infrastructure",
                "duration_sec": duration_sec,
                "report": asdict(step_report),
                "summary": {
                    "gaps": _format_infrastructure_gaps_for_progress(step_report.gaps),
                    "patched": _format_infrastructure_bootstrap_result_for_progress(step_report),
                },
            }
        )
        # bootstrap 可能判定“无需写盘”（changed=False）；此时 output_tool_path 并不存在，
        # 不应切换 current_input，否则后续步骤会因 input_gil 不存在而直接失败。
        if bool(step_report.changed) and output_tool_path.is_file():
            current_input = output_tool_path.resolve()
    else:
        # 说明：仅写回节点图时，为避免改动 base 其它段，这里只展示缺口，不执行 bootstrap 写盘。
        if bool(infrastructure_gaps.needs_bootstrap):
            _emit_progress(
                progress_cb,
                current_step,
                total_steps,
                f"基础设施扫描结果：{_format_infrastructure_gaps_for_progress(infrastructure_gaps)}（本次仅写回节点图，跳过基础设施补齐）",
            )

    # 当 “UI + 节点图” 同次写回时，由 UI 写回阶段产出的 ui_key→guid 映射（不落盘 registry），
    # 会在节点图写回阶段用于解析/回填 `ui_key:` 占位符。
    ui_key_to_guid_for_graph_writeback: dict[str, int] | None = None
    # 可选：为 UI 回填记录补充的元信息（例如 layout_names）
    ui_export_record_extra: dict[str, object] | None = None

    if bool(plan.export_templates):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在写回元件库模板…")

        from ugc_file_tools.project_archive_importer.templates_importer import (
            TemplatesImportOptions,
            import_templates_from_project_archive_to_gil,
        )

        t0 = perf_counter()
        step_report = import_templates_from_project_archive_to_gil(
            project_archive_path=project_root,
            input_gil_file_path=current_input,
            output_gil_file_path=output_tool_path,
            options=TemplatesImportOptions(
                mode=str(plan.templates_mode),
                skip_placeholders=(not bool(plan.include_placeholder_templates)),
                include_template_json_files=(
                    list(plan.selected_template_json_files) if plan.selected_template_json_files else None
                ),
                template_conflict_resolutions=(
                    list(plan.template_conflict_resolutions) if plan.template_conflict_resolutions else None
                ),
            ),
        )
        duration_sec = float(perf_counter() - t0)
        timings_sec["step_templates_sec"] = duration_sec
        steps.append({"kind": "templates", "duration_sec": duration_sec, "report": step_report})
        current_input = output_tool_path.resolve()

    if bool(effective_export_instances):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在写回实体摆放…")

        from ugc_file_tools.project_archive_importer.instances_importer import (
            InstancesImportOptions,
            import_instances_from_project_archive_to_gil,
        )

        t0 = perf_counter()
        step_report = import_instances_from_project_archive_to_gil(
            project_archive_path=project_root,
            input_gil_file_path=current_input,
            output_gil_file_path=output_tool_path,
            options=InstancesImportOptions(
                mode=str(plan.instances_mode),
                include_instance_json_files=(
                    list(plan.selected_instance_json_files) if plan.selected_instance_json_files else None
                ),
                instance_conflict_resolutions=(
                    list(plan.instance_conflict_resolutions) if plan.instance_conflict_resolutions else None
                ),
            ),
        )
        duration_sec = float(perf_counter() - t0)
        timings_sec["step_instances_sec"] = duration_sec
        steps.append({"kind": "instances", "duration_sec": duration_sec, "report": step_report})
        current_input = output_tool_path.resolve()

    if want_custom_variables:
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在写回自定义变量（注册表）…")

        from ugc_file_tools.project_archive_importer.registry_custom_variables_importer import (
            RegistryCustomVariablesImportOptions,
            import_selected_registry_custom_variables_from_project_archive_to_gil,
        )

        # 兼容旧字段：若 selection 未提供 owner_ref+variable_id，则按 level owner 兜底构造 refs。
        refs = [dict(x) for x in list(plan.selected_custom_variable_refs or []) if isinstance(x, dict)]
        if not refs:
            refs = [{"owner_ref": "level", "variable_id": str(x)} for x in list(plan.selected_level_custom_variable_ids or [])]

        t0 = perf_counter()
        step_report = import_selected_registry_custom_variables_from_project_archive_to_gil(
            project_archive_path=project_root,
            input_gil_file_path=current_input,
            output_gil_file_path=output_tool_path,
            options=RegistryCustomVariablesImportOptions(
                selected_custom_variable_refs=list(refs),
                overwrite_when_type_mismatched=False,
            ),
        )
        duration_sec = float(perf_counter() - t0)
        timings_sec["step_custom_variables_registry_sec"] = duration_sec
        steps.append({"kind": "custom_variables_registry", "duration_sec": duration_sec, "report": step_report})
        current_input = output_tool_path.resolve()

    if bool(plan.export_structs):
        if not has_basic_structs and not has_ingame_structs:
            raise ValueError("已选择写回结构体，但项目存档内未发现任何可写回的结构体定义（基础/局内存档均为空）。")

        if has_basic_structs:
            current_step += 1
            _emit_progress(progress_cb, current_step, total_steps, "正在写回结构体定义（基础）…")

            from ugc_file_tools.project_archive_importer.struct_definitions_importer import (
                StructImportOptions,
                import_struct_definitions_from_project_archive_to_gil,
            )

            t0 = perf_counter()
            step_report = import_struct_definitions_from_project_archive_to_gil(
                project_archive_path=project_root,
                input_gil_file_path=current_input,
                output_gil_file_path=output_tool_path,
                options=StructImportOptions(
                    mode=str(plan.struct_mode),
                    include_struct_ids=list(plan.selected_struct_ids or []) if plan.selected_struct_ids else None,
                ),
            )
            duration_sec = float(perf_counter() - t0)
            timings_sec["step_struct_definitions_sec"] = duration_sec
            steps.append({"kind": "struct_definitions", "duration_sec": duration_sec, "report": step_report})
            current_input = output_tool_path.resolve()

        if has_ingame_structs:
            current_step += 1
            _emit_progress(progress_cb, current_step, total_steps, "正在写回结构体定义（局内存档）…")

            from ugc_file_tools.project_archive_importer.ingame_save_structs_importer import (
                IngameSaveStructImportOptions,
                import_ingame_save_structs_from_project_archive_to_gil,
            )

            t0 = perf_counter()
            step_report = import_ingame_save_structs_from_project_archive_to_gil(
                project_archive_path=project_root,
                input_gil_file_path=current_input,
                output_gil_file_path=output_tool_path,
                options=IngameSaveStructImportOptions(
                    mode=str(plan.struct_mode),
                    include_struct_ids=list(plan.selected_ingame_struct_ids or []) if plan.selected_ingame_struct_ids else None,
                ),
                bootstrap_template_gil_file_path=None,
            )
            duration_sec = float(perf_counter() - t0)
            timings_sec["step_ingame_save_structs_sec"] = duration_sec
            steps.append({"kind": "ingame_save_structs", "duration_sec": duration_sec, "report": step_report})
            current_input = output_tool_path.resolve()

    if bool(effective_export_signals):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在写回信号定义…")

        from ugc_file_tools.project_archive_importer.signals_importer import (
            SignalsImportOptions,
            import_signals_from_project_archive_to_gil,
        )

        t0 = perf_counter()
        step_report = import_signals_from_project_archive_to_gil(
            project_archive_path=project_root,
            input_gil_file_path=current_input,
            output_gil_file_path=output_tool_path,
            template_gil_file_path=(Path(plan.signals_template_gil).resolve() if plan.signals_template_gil else None),
            bootstrap_template_gil_file_path=(Path(plan.signals_bootstrap_gil).resolve() if plan.signals_bootstrap_gil else None),
            options=SignalsImportOptions(
                param_build_mode=str(plan.signals_param_build_mode),
                include_signal_ids=(list(effective_selected_signal_ids) if effective_selected_signal_ids else None),
                duplicate_name_policy=("keep_first" if effective_selected_signal_ids else "error"),
                emit_reserved_placeholder_signal=bool(plan.signals_emit_reserved_placeholder_signal),
            ),
        )
        duration_sec = float(perf_counter() - t0)
        timings_sec["step_signals_sec"] = duration_sec
        steps.append({"kind": "signals", "duration_sec": duration_sec, "report": step_report})
        current_input = output_tool_path.resolve()

    if bool(plan.export_ui_widget_templates):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在写回 UI（界面）…")

        # 重要：当“节点图 + UI”同时写回时，必须先写 UI，再写节点图。
        # 原因：节点图写回阶段会解析/回填 ui_key 占位符（例如切换布局/按钮组等），
        # 需要以“当前输出 gil 内的 UI records”为准反查 GUID。若 UI 最后写回，会导致回填缺失/错填。
        #
        # 因此这里将 UI 写回放在节点图写回之前（node_graphs 在下方）。

        # 统一用户心智：UI 的目标是“把 HTML/样式写进 base 存档”。
        # 优先走你们当前主用链路：UI源码（Workbench bundle）→ 写回 .gil；
        # 若项目存档存在 raw_template(record bundle)，则按该更保守的方式写回（更接近真源 bytes 形态）。
        from ugc_file_tools.project_archive_importer.ui_widget_templates_importer import UIWidgetTemplatesImportOptions
        from ugc_file_tools.project_archive_importer.ui_widget_templates_importer import (
            import_ui_widget_templates_from_project_archive_to_gil,
        )
        from ugc_file_tools.project_archive_importer.ui_html_workbench_importer import (
            import_ui_from_workbench_bundles_to_gil,
        )

        ui_dir = project_root / "管理配置" / "UI控件模板" / "原始解析"
        has_raw_template = bool(ui_dir.is_dir() and any(ui_dir.glob("ugc_ui_widget_template_*.raw.json")))
        if has_raw_template:
            t0 = perf_counter()
            step_report = import_ui_widget_templates_from_project_archive_to_gil(
                project_archive_path=project_root,
                input_gil_file_path=current_input,
                output_gil_file_path=output_tool_path,
                options=UIWidgetTemplatesImportOptions(mode=str(plan.ui_widget_templates_mode)),
            )
            duration_sec = float(perf_counter() - t0)
            timings_sec["step_ui_widget_templates_raw_template_sec"] = duration_sec
            steps.append({"kind": "ui_widget_templates_raw_template", "duration_sec": duration_sec, "report": step_report})
        else:
            t0 = perf_counter()
            step_report = import_ui_from_workbench_bundles_to_gil(
                project_archive_path=project_root,
                input_gil_file_path=current_input,
                output_gil_file_path=output_tool_path,
                auto_sync_custom_variables=bool(plan.ui_auto_sync_custom_variables),
                include_layout_names=(list(plan.selected_ui_layout_names) if plan.selected_ui_layout_names else None),
                layout_conflict_resolutions=(list(plan.ui_layout_conflict_resolutions) if plan.ui_layout_conflict_resolutions else None),
            )
            duration_sec = float(perf_counter() - t0)
            timings_sec["step_ui_html_workbench_bundles_sec"] = duration_sec
            steps.append({"kind": "ui_html_workbench_bundles", "duration_sec": duration_sec, "report": step_report})

            # UI 回填记录元信息：按 bundle 文件名推断的 layout_name 列表（用于 `.gia` 导出侧的 LayoutIndex 辅助回填）
            try:
                bundles = step_report.get("bundles") if isinstance(step_report, dict) else None
                if isinstance(bundles, list) and bundles:
                    names: list[str] = []
                    seen: set[str] = set()
                    for b in bundles:
                        if not isinstance(b, dict):
                            continue
                        # 优先使用“实际写入的布局名”（冲突策略可能会 rename/add），否则回退到 bundle 文件名推断名。
                        n = str(b.get("layout_name_written") or b.get("layout_name") or "").strip()
                        if n == "" or n in seen:
                            continue
                        seen.add(n)
                        names.append(n)
                    if names:
                        ui_export_record_extra = {"layout_names": list(names)}
            except Exception:
                # 记录缺失不应影响 UI 写回主流程
                ui_export_record_extra = ui_export_record_extra

            raw_ui_map = step_report.get("ui_key_to_guid_for_writeback") if isinstance(step_report, dict) else None
            if isinstance(raw_ui_map, dict) and raw_ui_map:
                cleaned: dict[str, int] = {}
                for k, v in raw_ui_map.items():
                    key = str(k or "").strip()
                    if key == "":
                        continue
                    if not isinstance(v, int) or int(v) <= 0:
                        continue
                    cleaned[key] = int(v)
                ui_key_to_guid_for_graph_writeback = cleaned if cleaned else None
        current_input = output_tool_path.resolve()

    if bool(plan.export_graphs):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在写回节点图…")

        from ugc_file_tools.project_archive_importer.node_graphs_importer import (
            NodeGraphsImportOptions,
            import_node_graphs_from_project_archive_to_gil,
        )

        if plan.graph_server_template_gil is None or plan.graph_server_template_library_dir is None:
            raise ValueError("graph_server_template_gil and graph_server_template_library_dir are required when export_graphs is True")
        if plan.graph_client_template_gil is None or plan.graph_client_template_library_dir is None:
            raise ValueError("graph_client_template_gil and graph_client_template_library_dir are required when export_graphs is True")
        if plan.graph_mapping_json is None:
            raise ValueError("graph_mapping_json is required when export_graphs is True")

        output_model_dir_name = str(plan.graph_output_model_dir_name or "").strip()
        if output_model_dir_name == "":
            output_model_dir_name = f"{project_root.name}_graph_models"

        def _graph_progress_cb(inner_label: str) -> None:
            _emit_progress(progress_cb, current_step, total_steps, f"正在写回节点图… {inner_label}")

        t0 = perf_counter()
        step_report = import_node_graphs_from_project_archive_to_gil(
            project_archive_path=project_root,
            input_gil_file_path=current_input,
            output_gil_file_path=output_tool_path,
            server_template_gil_file_path=Path(plan.graph_server_template_gil),
            server_template_library_dir=Path(plan.graph_server_template_library_dir),
            client_template_gil_file_path=Path(plan.graph_client_template_gil),
            client_template_library_dir=Path(plan.graph_client_template_library_dir),
            mapping_json_path=Path(plan.graph_mapping_json),
            options=NodeGraphsImportOptions(
                scope=str(plan.graphs_scope),
                scan_all=bool(plan.graph_scan_all),
                strict_graph_code_files=bool(plan.graph_strict_graph_code_files),
                output_model_dir_name=output_model_dir_name,
                prefer_signal_specific_type_id=bool(plan.prefer_signal_specific_type_id),
                graph_code_files=(
                    [Path(p).resolve() for p in list(plan.selected_graph_code_files or [])]
                    if plan.selected_graph_code_files
                    else None
                ),
                graph_source_roots=(
                    [Path(p).resolve() for p in list(plan.graph_source_roots or [])]
                    if plan.graph_source_roots
                    else None
                ),
                node_graph_conflict_resolutions=(
                    list(plan.node_graph_conflict_resolutions)
                    if plan.node_graph_conflict_resolutions
                    else None
                ),
                ui_export_record_id=(
                    str(plan.ui_export_record_id).strip()
                    if str(plan.ui_export_record_id or "").strip() != ""
                    else None
                ),
                ui_key_to_guid_for_writeback=ui_key_to_guid_for_graph_writeback,
                id_ref_gil_file=(Path(plan.id_ref_gil_file).resolve() if plan.id_ref_gil_file is not None else None),
                id_ref_overrides_json_file=(
                    Path(plan.id_ref_overrides_json_file).resolve() if plan.id_ref_overrides_json_file is not None else None
                ),
            ),
            progress_cb=_graph_progress_cb,
        )
        duration_sec = float(perf_counter() - t0)
        timings_sec["step_node_graphs_sec"] = duration_sec
        steps.append({"kind": "node_graphs", "duration_sec": duration_sec, "report": step_report})
        current_input = output_tool_path.resolve()

    if need_copy:
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在复制导出产物…")
        if output_user_abs is None:
            raise RuntimeError("internal error: need_copy but output_user_abs is None")
        t0 = perf_counter()
        _atomic_copy2(src=output_tool_path, dst=output_user_abs)
        timings_sec["step_copy_output_sec"] = float(perf_counter() - t0)

    report["output_gil_resolved"] = str(output_tool_path.resolve())
    report["output_gil_user_resolved"] = str(output_user_abs.resolve()) if output_user_abs is not None else str(output_user_raw)
    report["auto_signal_ids_from_graphs"] = list(auto_signal_ids_from_graphs)
    report["effective_selected_signal_ids"] = list(effective_selected_signal_ids)
    report["auto_enabled_signals_for_graphs"] = bool(auto_enabled_signals_for_graphs)
    report["effective_export_signals"] = bool(effective_export_signals)
    report["timings_sec"] = dict(timings_sec)

    # ===== 最近导出 gil 记录（供 UI 基底选择器复用）=====
    # 只记录真实存在的 .gil 文件；workspace_root 从 project_root 路径结构推断：
    # <workspace>/assets/资源库/项目存档/<package_id>/...
    try:
        parts = list(project_root.resolve().parts)
        assets_index: int | None = None
        for i, part in enumerate(parts):
            if str(part) == "assets":
                assets_index = int(i)
                break
        if assets_index is not None:
            workspace_root = Path(*parts[:assets_index]).resolve()

            # ===== UI 回填记录（供后续 `.gia` 导出选择回填 UIKey→GUID）=====
            # 设计目标：即使用户只使用“导出中心”链路写回 UI（不走网页工具），
            # 也能生成一条 UI 导出记录，使节点图 `.gia` 导出可默认选择最新记录进行回填。
            if bool(plan.export_ui_widget_templates):
                try:
                    from ugc_file_tools.ui.export_records import append_ui_export_record_from_mapping

                    ui_record = append_ui_export_record_from_mapping(
                        workspace_root=Path(workspace_root),
                        package_id=str(project_root.name),
                        title=f"writeback_ui:{project_root.name}",
                        kind="project_writeback_ui",
                        output_gil_file=Path(output_tool_path).resolve(),
                        ui_key_to_guid=dict(ui_key_to_guid_for_graph_writeback or {}),
                        base_gil_path=Path(input_gil_path).resolve(),
                        base_gil_file_name_hint=str(Path(input_gil_path).name),
                        extra=(dict(ui_export_record_extra) if isinstance(ui_export_record_extra, dict) else None),
                    )
                    report["ui_export_record"] = dict(ui_record)
                except Exception:
                    # 记录失败不应影响导出主流程
                    pass

            from ugc_file_tools.recent_artifacts import append_recent_exported_gil

            append_recent_exported_gil(
                workspace_root=workspace_root,
                gil_path=str(output_tool_path.resolve()),
                source="project_writeback",
                title=f"writeback:{project_root.name}",
            )
            if output_user_abs is not None and output_user_abs.resolve() != output_tool_path.resolve():
                append_recent_exported_gil(
                    workspace_root=workspace_root,
                    gil_path=str(output_user_abs.resolve()),
                    source="project_writeback",
                    title=f"writeback:{project_root.name}",
                )
    except Exception:
        # 记录失败不应影响导出主流程
        pass

    report["timings_sec"]["total_sec"] = float(perf_counter() - started_at)
    return report


