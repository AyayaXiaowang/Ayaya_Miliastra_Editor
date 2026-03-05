from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .gil_backfill_analysis_cache import GilBackfillAnalysis, load_or_compute_gil_backfill_analysis


@dataclass(frozen=True, slots=True)
class UiKeyPlaceholderUsage:
    """
    从 Graph Code（节点图源码）中扫描到的 ui_key/ui 占位符使用情况。

    说明：
    - 仅扫描 **Python 字符串字面量**（tokenize.STRING），避免把注释/代码片段误判为占位符。
    - 支持两种前缀（与写回/导出链路一致）：
      - ui_key:<UIKey>
      - ui:<UIKey>（legacy）
    - layout_name_hint：用于 UI records 消歧（当多个 layout 都存在同名控件时）。
    """

    ui_keys: frozenset[str]
    layout_hints_by_ui_key: dict[str, frozenset[str]]

    @property
    def is_used(self) -> bool:
        return bool(self.ui_keys)


_LAYOUT_NAME_HINT_RE = re.compile(r"管理配置[\\/]+UI源码[\\/]+([^\\/`\"']+?)\.html")

# cache: graph_code_file_posix -> (mtime_ns, ui_keys, layout_hint)
_UI_KEY_PLACEHOLDER_CACHE: dict[str, tuple[int, frozenset[str], str | None]] = {}

# progress callback: (current, total, label)
ProgressCallback = Callable[[int, int, str], None]


def _emit_progress(cb: ProgressCallback | None, current: int, total: int, label: str) -> None:
    if callable(cb):
        cb(int(current), int(total), str(label or "").strip())


def _scan_ui_key_candidates_from_workbench_bundles(
    *,
    ui_source_dir: Path,
    selected_html_stems: Sequence[str] | None,
) -> tuple[dict[str, int], set[str], dict[str, int], set[tuple[str, str]]]:
    """
    从 UI Workbench bundle（`UI源码/__workbench_out__/*.ui_bundle.json`）提取 ui_key 候选：
    - 返回 key->dummy_guid（仅用于存在性判定；GUID 真实值由写回阶段决定）
    - 返回 alias_key 冲突集合（同一个 alias_key 来源于多个不同 key 时视为歧义）
    - 返回原始 key 在 bundle 内出现次数（用于判定“ui_key 不唯一”）

    约束：
    - 不做 try/except；bundle 缺失或格式异常直接抛错（避免 UI 误判“可用”）。
    """
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_bundle import load_ui_control_group_template_json
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_guid_registry import add_html_stem_ui_key_aliases

    ui_dir = Path(ui_source_dir).resolve()
    bundle_dir = (ui_dir / "__workbench_out__").resolve()
    if not bundle_dir.is_dir():
        raise FileNotFoundError(str(bundle_dir))

    stems = [str(x).strip() for x in list(selected_html_stems or []) if str(x).strip() != ""]
    stems_cf = {str(x).casefold() for x in stems}

    bundle_files: list[Path] = []
    if stems:
        for stem in stems:
            p = (bundle_dir / f"{stem}.ui_bundle.json").resolve()
            if p.is_file():
                bundle_files.append(p)
        missing = [stem for stem in stems if not (bundle_dir / f"{stem}.ui_bundle.json").resolve().is_file()]
        if missing:
            raise FileNotFoundError(f"缺少 UI Workbench bundle：{str(bundle_dir)} / {missing}")
    else:
        bundle_files = [p.resolve() for p in sorted(bundle_dir.glob("*.ui_bundle.json"), key=lambda x: x.as_posix()) if p.is_file()]

    key_counts: dict[str, int] = {}
    mapping: dict[str, int] = {}
    dummy = 1

    def _bump(key0: object) -> None:
        nonlocal dummy
        k = str(key0 or "").strip()
        if k == "":
            return
        key_counts[k] = int(key_counts.get(k, 0)) + 1
        if k not in mapping:
            mapping[k] = int(dummy)
            dummy += 1

    for bf in list(bundle_files):
        template = load_ui_control_group_template_json(Path(bf))
        widgets = template.get("widgets")
        if not isinstance(widgets, list):
            raise TypeError(f"ui_bundle widgets must be list: {str(bf)}")
        for w in widgets:
            if not isinstance(w, dict):
                continue
            _bump(w.get("ui_key"))
            _bump(w.get("widget_id"))

    alias_conflicts: set[str] = set()
    for bf in list(bundle_files):
        name = str(Path(bf).name)
        suffix = ".ui_bundle.json"
        html_stem = name[: -len(suffix)] if name.endswith(suffix) else str(Path(bf).stem)
        html_stem = str(html_stem).strip()
        if html_stem == "":
            continue
        mapping2, rep = add_html_stem_ui_key_aliases(mapping, html_stem=html_stem)
        mapping = dict(mapping2)
        conflicts = rep.get("aliases_conflicts") if isinstance(rep, dict) else None
        if isinstance(conflicts, list):
            for it in conflicts:
                if not isinstance(it, dict):
                    continue
                ak = str(it.get("alias_key") or "").strip()
                if ak != "":
                    alias_conflicts.add(ak)

    # 若用户显式选择了 UI 页面，则限制 alias 只来自这些页面（避免“别的页面有同名 alias”误判）
    if stems:
        allowed_prefixes = [f"{stem}_html__" for stem in stems if stem.strip() != ""]
        mapping = {
            str(k): int(v)
            for k, v in mapping.items()
            if any(str(k).startswith(pref) for pref in allowed_prefixes)
            or str(k).startswith("HTML导入_")
            or str(k).startswith("UI_STATE_GROUP__")
            or str(k).startswith("LAYOUT_INDEX__")
        }
        alias_conflicts = {k for k in alias_conflicts if any(str(k).startswith(pref) for pref in allowed_prefixes)}

        # 只保留 stems_filter 内的原始 key 计数（避免误判其它页面的重复）
        if stems_cf:
            # 原始 key 不带 stem 前缀，无法按 stem 过滤；这里不做过滤，保持“真实出现次数”。
            pass

    token_pairs: set[tuple[str, str]] = set()
    for k in list(mapping.keys()):
        parts = [p for p in str(k).split("__") if str(p).strip() != ""]
        if len(parts) < 3:
            continue
        # 跳过 parts[0]（通常是 `HTML导入_界面布局` 或 `<stem>_html` 前缀），从后续 token 提取相邻二元组
        for i in range(1, len(parts) - 1):
            a = str(parts[i]).strip()
            b = str(parts[i + 1]).strip()
            if a != "" and b != "":
                token_pairs.add((a, b))

    return dict(mapping), set(alias_conflicts), dict(key_counts), set(token_pairs)


def _infer_layout_name_hint_from_graph_code_text(text: str) -> str | None:
    raw = str(text or "")
    m = _LAYOUT_NAME_HINT_RE.search(raw)
    if not m:
        return None
    name = str(m.group(1) or "").strip()
    return name if name != "" else None


def _scan_ui_key_placeholders_in_graph_code_file(*, graph_code_file: Path) -> tuple[frozenset[str], str | None]:
    """
    扫描单个节点图源码文件内的 ui_key/ui 占位符，并做缓存（按 mtime_ns）。
    """
    from .._common import _iter_python_string_literals_from_file

    from ugc_file_tools.ui.guid_registry import extract_ui_key_from_placeholder_text

    p = Path(graph_code_file).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    cache_key = p.as_posix()
    mtime_ns = int(p.stat().st_mtime_ns)
    cached = _UI_KEY_PLACEHOLDER_CACHE.get(cache_key)
    if cached is not None and int(cached[0]) == int(mtime_ns):
        return cached[1], cached[2]

    file_text = p.read_text(encoding="utf-8", errors="strict")
    layout_hint = _infer_layout_name_hint_from_graph_code_text(file_text)

    ui_keys: set[str] = set()
    for s in _iter_python_string_literals_from_file(file_path=p):
        k = extract_ui_key_from_placeholder_text(str(s))
        if k is not None:
            ui_keys.add(str(k))

    keys = frozenset(ui_keys)
    _UI_KEY_PLACEHOLDER_CACHE[cache_key] = (int(mtime_ns), keys, layout_hint)
    return keys, layout_hint


def scan_ui_key_placeholders_in_graph_code_files(*, graph_code_files: Sequence[Path]) -> UiKeyPlaceholderUsage:
    """
    扫描一组节点图源码文件，返回合并后的 ui_key 使用集合（去重）与 layout hint（用于消歧）。

    返回：
    - ui_keys：所有 ui_key（不含前缀）
    - layout_hints_by_ui_key：{ui_key: {hint1, hint2, ...}}（仅记录非空 hint；同一个 key 可能来自多张图）
    """
    all_keys: set[str] = set()
    hints_by_key: dict[str, set[str]] = {}
    for p in list(graph_code_files or []):
        keys, hint = _scan_ui_key_placeholders_in_graph_code_file(graph_code_file=Path(p))
        for k in keys:
            all_keys.add(str(k))
        if hint is not None:
            for k in keys:
                hints_by_key.setdefault(str(k), set()).add(str(hint))

    out_hints: dict[str, frozenset[str]] = {}
    for k, v in hints_by_key.items():
        if not v:
            continue
        out_hints[str(k)] = frozenset(sorted({str(x) for x in v if str(x).strip() != ""}))

    return UiKeyPlaceholderUsage(
        ui_keys=frozenset(sorted({str(x) for x in all_keys if str(x).strip() != ""})),
        layout_hints_by_ui_key=dict(out_hints),
    )


def _format_ui_var_ref(group: str, var_name: str, field_path: Tuple[str, ...]) -> str:
    g = str(group or "").strip()
    n = str(var_name or "").strip()
    if not field_path:
        return f"{g}.{n}"
    return f"{g}.{n}." + ".".join([str(x) for x in field_path])


def identify_gil_backfill_comparison(
    *,
    base_gil_file_path: Path,
    id_ref_gil_file_path: Path | None,
    use_base_as_id_ref_fallback: bool,
    workspace_root: Path | None,
    package_id: str,
    ui_export_record_id: str | None,
    required_entity_names: Iterable[str],
    required_component_names: Iterable[str],
    required_ui_keys: Iterable[str],
    ui_key_layout_hints_by_key: Mapping[str, Iterable[str]] | None,
    required_level_custom_variables: Sequence[Mapping[str, str]] | None,
    scan_ui_placeholder_variables: bool,
    ui_source_dir: Path | None,
    ui_selected_html_stems: Sequence[str] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> Dict[str, object]:
    """
    识别一个 `.gil` 文件可提供的回填内容，并与“回填依赖清单”做对比。

    返回 dict 结构（供 UI 线程/表格渲染直接使用）：
    - base_gil_path: str
    - id_ref_gil_path: str
    - rows: list[{category,key,value,status,note}]
    - summary: {total, ok, bundled, missing, mismatch, ambiguous}
    """
    from ugc_file_tools.ui.guid_resolution import resolve_ui_key_guid_from_output_gil
    from ugc_file_tools.ui.export_records import load_ui_guid_registry_snapshot, try_get_ui_export_record_by_id

    required_entity_list = sorted(
        {str(x).strip() for x in list(required_entity_names or []) if str(x).strip() != ""},
        key=lambda t: t.casefold(),
    )
    required_component_list = sorted(
        {str(x).strip() for x in list(required_component_names or []) if str(x).strip() != ""},
        key=lambda t: t.casefold(),
    )
    required_ui_key_list = sorted(
        {str(x).strip() for x in list(required_ui_keys or []) if str(x).strip() != ""},
        key=lambda t: t.casefold(),
    )

    need_entity_component = bool(required_entity_list or required_component_list)
    need_ui_keys = bool(required_ui_key_list)
    need_level_custom_vars = bool(required_level_custom_variables)
    need_scan_ui_placeholder_vars = bool(scan_ui_placeholder_variables) and ui_source_dir is not None
    need_scan_ui_workbench_for_ui_keys = bool(need_ui_keys) and ui_source_dir is not None

    # step-based progress; keep it coarse to avoid UI event flood
    total_steps = (
        4  # parse base / id_ref mapping / ui index+snapshot / custom vars
        + (1 if need_entity_component else 0)
        + (1 if need_ui_keys else 0)
        + (1 if need_level_custom_vars else 0)
        + (1 if need_scan_ui_workbench_for_ui_keys else 0)
        + (1 if need_scan_ui_placeholder_vars else 0)
        + 1  # summary
    )
    step = 0
    _emit_progress(progress_cb, step, total_steps, "准备识别…")

    base = Path(base_gil_file_path).resolve()
    if not base.is_file():
        raise FileNotFoundError(str(base))

    id_ref_path = Path(id_ref_gil_file_path).resolve() if id_ref_gil_file_path is not None else None
    use_fallback = bool(use_base_as_id_ref_fallback)
    effective_id_ref: Path | None
    if id_ref_path is not None:
        effective_id_ref = Path(id_ref_path)
    elif use_fallback:
        effective_id_ref = Path(base)
    else:
        effective_id_ref = None

    step += 1
    _emit_progress(progress_cb, step, total_steps, "解析 base .gil…（缓存可用时将复用）")

    base_analysis: GilBackfillAnalysis
    base_analysis, base_cache_hit = load_or_compute_gil_backfill_analysis(
        workspace_root=(Path(workspace_root) if workspace_root is not None else None),
        gil_file_path=Path(base),
    )

    step += 1
    _emit_progress(progress_cb, step, total_steps, "构建占位符参考映射（entity/component）…（缓存可用时将复用）")
    # --- id_ref mappings (entity/component) ---
    if effective_id_ref is None:
        component_name_to_id: dict[str, int] = {}
        entity_name_to_guid: dict[str, int] = {}
        id_ref_cache_hit = False
    else:
        effective = Path(effective_id_ref).resolve()
        if str(effective) == str(base):
            # 复用 base 分析结果：避免对同一份 base `.gil` 重复解码
            component_name_to_id = dict(base_analysis.component_name_to_id)
            entity_name_to_guid = dict(base_analysis.entity_name_to_guid)
            id_ref_cache_hit = bool(base_cache_hit)
        else:
            id_ref_analysis, id_ref_cache_hit = load_or_compute_gil_backfill_analysis(
                workspace_root=(Path(workspace_root) if workspace_root is not None else None),
                gil_file_path=Path(effective),
            )
            component_name_to_id = dict(id_ref_analysis.component_name_to_id)
            entity_name_to_guid = dict(id_ref_analysis.entity_name_to_guid)

    step += 1
    _emit_progress(progress_cb, step, total_steps, "构建 UI records 索引 / 加载 UI 回填记录快照…")
    # --- UI records index ---
    ui_index = base_analysis.ui_index
    ui_records_total = int(base_analysis.ui_records_total)
    root_name_cache: dict[int, str | None] = {}

    # --- UI export record snapshot mapping (optional) ---
    ui_snapshot_mapping: dict[str, int] | None = None
    rid = str(ui_export_record_id or "").strip()
    pkg = str(package_id or "").strip()
    if rid != "" and workspace_root is not None and pkg != "":
        rec = try_get_ui_export_record_by_id(workspace_root=Path(workspace_root), package_id=str(pkg), record_id=str(rid))
        if rec is not None:
            snap_path = str(rec.payload.get("ui_guid_registry_snapshot_path") or "").strip()
            if snap_path != "":
                ui_snapshot_mapping = load_ui_guid_registry_snapshot(Path(snap_path))

    step += 1
    _emit_progress(progress_cb, step, total_steps, "扫描自定义变量（实体 override_variables）…")
    # --- custom variables (existing) ---
    custom_vars_by_entity_name = dict(base_analysis.custom_vars_by_entity_name)

    rows: list[dict[str, str]] = []

    def _add_row(*, category: str, key: str, value: str, status: str, note: str) -> None:
        rows.append(
            {
                "category": str(category),
                "key": str(key),
                "value": str(value),
                "status": str(status),
                "note": str(note),
            }
        )

    # -------------------- entity_key / component_key --------------------
    if need_entity_component:
        step += 1
        _emit_progress(progress_cb, step, total_steps, "识别实体/元件占位符（entity_key/component_key）…")

    for name in required_entity_list:
        guid = entity_name_to_guid.get(str(name))
        if isinstance(guid, int) and int(guid) > 0:
            src = "来源：占位符参考 .gil" if id_ref_path is not None else "来源：base .gil"
            _add_row(category="实体ID(entity)", key=str(name), value=str(int(guid)), status="OK", note=src)
        else:
            _add_row(
                category="实体ID(entity)",
                key=str(name),
                value="",
                status="缺失",
                note=(
                    "未选择占位符参考 .gil：导出时 entity_key/entity 将回填为 0。"
                    if effective_id_ref is None
                    else "未在参考 .gil 中找到同名实体（entity_key/entity）。"
                ),
            )

    for name in required_component_list:
        cid = component_name_to_id.get(str(name))
        if isinstance(cid, int) and int(cid) > 0:
            src = "来源：占位符参考 .gil" if id_ref_path is not None else "来源：base .gil"
            _add_row(category="元件ID(component)", key=str(name), value=str(int(cid)), status="OK", note=src)
        else:
            _add_row(
                category="元件ID(component)",
                key=str(name),
                value="",
                status="缺失",
                note=(
                    "未选择占位符参考 .gil：导出时 component_key/component 将回填为 0。"
                    if effective_id_ref is None
                    else "未在参考 .gil 中找到同名元件（component_key/component）。"
                ),
            )

    # -------------------- ui_key / ui --------------------
    workbench_ui_key_mapping: dict[str, int] | None = None
    workbench_ui_key_alias_conflicts: set[str] = set()
    workbench_ui_key_counts: dict[str, int] = {}
    workbench_token_pairs: set[tuple[str, str]] = set()

    if need_scan_ui_workbench_for_ui_keys and ui_source_dir is not None:
        step += 1
        _emit_progress(progress_cb, step, total_steps, "扫描 UI Workbench bundle（用于 UIKey 回填判定）…")
        (
            workbench_ui_key_mapping,
            workbench_ui_key_alias_conflicts,
            workbench_ui_key_counts,
            workbench_token_pairs,
        ) = _scan_ui_key_candidates_from_workbench_bundles(
            ui_source_dir=Path(ui_source_dir),
            selected_html_stems=ui_selected_html_stems,
        )

    if need_ui_keys:
        step += 1
        _emit_progress(progress_cb, step, total_steps, "识别 UIKey 占位符（ui_key/ui）…")

    hints_by_key: Mapping[str, Iterable[str]] = dict(ui_key_layout_hints_by_key or {})
    for key in required_ui_key_list:
        key_norm = str(key).strip()
        # UI_STATE_GROUP 是“组件打组容器”的特殊 key（由 UI 写回阶段生成/注入），格式必须严格：
        # UI_STATE_GROUP__<group_name>__<state_name>__group
        # 用户常见误用：写成单下划线或缺少 state 段（例如 UI_STATE_GROUP_xxx_group），会导致无法解析。
        if key_norm.upper().startswith("UI_STATE_GROUP_") and not key_norm.startswith("UI_STATE_GROUP__"):
            _add_row(
                category="UI控件ID(ui_key)",
                key=str(key_norm),
                value="",
                status="缺失",
                note="UI_STATE_GROUP key 格式不正确：期望 `UI_STATE_GROUP__<group_name>__<state_name>__group`（注意双下划线 `__`，且必须包含 state_name）。",
            )
            continue
        if key_norm.startswith("UI_STATE_GROUP__"):
            parts = [p for p in key_norm.split("__") if str(p)]
            if len(parts) < 4 or parts[0] != "UI_STATE_GROUP" or parts[-1] != "group":
                _add_row(
                    category="UI控件ID(ui_key)",
                    key=str(key_norm),
                    value="",
                    status="缺失",
                    note="UI_STATE_GROUP key 结构不完整：期望 `UI_STATE_GROUP__<group_name>__<state_name>__group`。",
                )
                continue
            # 若本次同时导出启用了 UI 写回（有 Workbench bundle），则可从 bundle 的 token 对推断该 state group 会被写回生成。
            group_name = str(parts[1]).strip()
            state_name = str(parts[2]).strip()
            if group_name != "" and state_name != "" and workbench_token_pairs:
                candidates_group: list[str] = [group_name]
                if group_name.endswith("_state"):
                    short = str(group_name[: -len("_state")]).strip()
                    if short:
                        candidates_group.append(short)
                else:
                    candidates_group.append(group_name + "_state")
                if any((g, state_name) in workbench_token_pairs for g in candidates_group):
                    _add_row(
                        category="UI控件ID(ui_key)",
                        key=str(key_norm),
                        value="",
                        status="一同导出",
                        note="来源：本次同时导出（UI Workbench bundle 推断 state group）；写回阶段会生成/复用该组容器 GUID 供节点图回填使用。",
                    )
                    continue

        if ui_snapshot_mapping is not None:
            key_text = str(key_norm)
            guid0 = ui_snapshot_mapping.get(key_text)
            alias_note = ""

            # 工程化兜底：UI_STATE_GROUP 的 group 名在不同链路可能出现 `_state` 后缀差异，
            # 回填识别应与写回/导出口径一致，允许在快照内按别名互转命中。
            if (not isinstance(guid0, int) or int(guid0) <= 0) and key_text.startswith("UI_STATE_GROUP__"):
                parts = [p for p in key_text.split("__") if str(p)]
                if len(parts) >= 4 and parts[0] == "UI_STATE_GROUP" and parts[-1] == "group":
                    group = str(parts[1]).strip()
                    state = str(parts[2]).strip()
                    if group != "" and state != "":
                        candidates_group: list[str] = [group]
                        if group.endswith("_state"):
                            short = str(group[: -len("_state")]).strip()
                            if short:
                                candidates_group.append(short)
                        else:
                            candidates_group.append(group + "_state")

                        for gname in candidates_group:
                            cand_key = f"UI_STATE_GROUP__{gname}__{state}__group"
                            guid1 = ui_snapshot_mapping.get(cand_key)
                            if isinstance(guid1, int) and int(guid1) > 0:
                                guid0 = int(guid1)
                                if cand_key != key_text:
                                    alias_note = f"（别名命中：{cand_key}）"
                                break

            if isinstance(guid0, int) and int(guid0) > 0:
                _add_row(
                    category="UI控件ID(ui_key)",
                    key=str(key_text),
                    value=str(int(guid0)),
                    status="OK",
                    note=f"来源：UI 回填记录快照{alias_note}",
                )
                continue

        if ui_index is None:
            if workbench_ui_key_mapping is not None and str(key_norm) in workbench_ui_key_mapping:
                ambiguous = bool(
                    str(key_norm) in workbench_ui_key_alias_conflicts or int(workbench_ui_key_counts.get(str(key_norm), 0)) >= 2
                )
                _add_row(
                    category="UI控件ID(ui_key)",
                    key=str(key_norm),
                    value="",
                    status=("歧义" if ambiguous else "一同导出"),
                    note=(
                        "来源：本次同时导出（UI Workbench bundle）；但该 ui_key 在 bundle 内不唯一/alias 冲突，写回会自动规范化（补稳定后缀），建议改用更具体 key（或使用 <页面>_html__ 前缀）。"
                        if ambiguous
                        else "来源：本次同时导出（UI Workbench bundle）；base .gil 缺少 UI records，但 UI 写回会生成/复用 GUID 并供节点图回填使用。"
                    ),
                )
            else:
                _add_row(
                    category="UI控件ID(ui_key)",
                    key=str(key_norm),
                    value="",
                    status="缺失",
                    note="来源：base .gil（缺少 UI records：4/9/502），且本次未选择可用的 UI Workbench bundle，无法解析 ui_key。",
                )
            continue

        hint_list = sorted({str(x).strip() for x in list(hints_by_key.get(str(key), [])) if str(x).strip() != ""})
        # best-effort: try no hint first, then try all hints observed from graphs
        attempted_hints: list[str | None] = [None] + hint_list
        resolved: list[tuple[int, str | None]] = []
        for hint in attempted_hints:
            got = resolve_ui_key_guid_from_output_gil(
                ui_key=str(key),
                layout_name_hint=(str(hint).strip() if hint is not None else None),
                ui_index=ui_index,
                root_name_cache=root_name_cache,
            )
            if isinstance(got, int) and int(got) > 0:
                resolved.append((int(got), hint))

        uniq = sorted({int(g) for g, _h in resolved if int(g) > 0})
        if len(uniq) == 1:
            note_parts: list[str] = []
            used_hints = sorted({str(h) for _g, h in resolved if h is not None and str(h).strip() != ""})
            if used_hints:
                note_parts.append(f"layout_hint={used_hints[0]}" if len(used_hints) == 1 else f"layout_hint候选={used_hints}")
            if ui_snapshot_mapping is not None:
                note_parts.insert(0, "来源：base UI records（快照缺失）")
            else:
                note_parts.insert(0, "来源：base UI records")
            _add_row(
                category="UI控件ID(ui_key)",
                key=str(key_norm),
                value=str(int(uniq[0])),
                status="OK",
                note="；".join([p for p in note_parts if str(p).strip() != ""]),
            )
            continue
        if len(uniq) >= 2:
            _add_row(
                category="UI控件ID(ui_key)",
                key=str(key_norm),
                value="",
                status="歧义",
                note=f"同一 ui_key 在不同 layout 下解析到多个 GUID：{uniq}（建议在节点图描述中包含 UI源码/<name>.html 以提供 layout hint）。",
            )
            continue

        if workbench_ui_key_mapping is not None and str(key_norm) in workbench_ui_key_mapping:
            ambiguous2 = bool(
                str(key_norm) in workbench_ui_key_alias_conflicts or int(workbench_ui_key_counts.get(str(key_norm), 0)) >= 2
            )
            _add_row(
                category="UI控件ID(ui_key)",
                key=str(key_norm),
                value="",
                status=("歧义" if ambiguous2 else "一同导出"),
                note=(
                    "来源：本次同时导出（UI Workbench bundle）；但该 ui_key 在 bundle 内不唯一/alias 冲突，写回会自动规范化（补稳定后缀），建议改用更具体 key（或使用 <页面>_html__ 前缀）。"
                    if ambiguous2
                    else "来源：本次同时导出（UI Workbench bundle）；base UI records 未命中，但写回会生成/复用 GUID 并供节点图回填使用。"
                ),
            )
        else:
            _add_row(
                category="UI控件ID(ui_key)",
                key=str(key_norm),
                value="",
                status="缺失",
                note=(
                    "UI 回填记录快照缺少该 key，且未能从 base UI records 反查 GUID（可能控件不存在/命名不一致/缺少 layout hint）。"
                    if ui_snapshot_mapping is not None
                    else "未能从 UI records 中反查该 ui_key 对应的 GUID（可能控件不存在/命名不一致/缺少 layout hint）。"
                ),
            )

    # -------------------- level custom variables (explicit deps list) --------------------
    if required_level_custom_variables:
        step += 1
        _emit_progress(progress_cb, step, total_steps, "识别关卡实体自定义变量（全部）…")

        from ugc_file_tools.var_type_map import map_server_port_type_text_to_var_type_id_or_raise

        level_existing = custom_vars_by_entity_name.get("关卡实体", {})
        for meta in sorted(
            [dict(x) for x in list(required_level_custom_variables or []) if isinstance(x, Mapping)],
            key=lambda d: str(d.get("variable_name") or d.get("variable_id") or "").casefold(),
        ):
            vid = str(meta.get("variable_id") or "").strip()
            vname = str(meta.get("variable_name") or "").strip()
            vtype = str(meta.get("variable_type") or "").strip()
            display = f"{vname} ({vid})" if vname and vid else (vname or vid or "<unknown>")
            want_type = int(map_server_port_type_text_to_var_type_id_or_raise(vtype)) if vtype else 0

            existed_type = level_existing.get(str(vname).casefold()) if vname else None
            if existed_type is None:
                _add_row(
                    category="自定义变量(关卡实体)",
                    key=str(display),
                    value=f"type={want_type if want_type else vtype!r}",
                    status="缺失",
                    note="来源：base .gil（关卡实体 override_variables 缺少该变量）。",
                )
                continue
            if int(existed_type) == int(want_type) or int(want_type) == 0:
                _add_row(
                    category="自定义变量(关卡实体)",
                    key=str(display),
                    value=f"type={int(existed_type)}",
                    status="OK",
                    note="来源：base .gil",
                )
                continue
            _add_row(
                category="自定义变量(关卡实体)",
                key=str(display),
                value=f"type={int(existed_type)}",
                status="类型不匹配",
                note=(
                    f"来源：base .gil；同名变量已存在但类型不同：existing={int(existed_type)} want={int(want_type)}"
                    "（默认不覆盖，导出报告会列出）。"
                ),
            )

    # -------------------- UI placeholder variables (auto sync) --------------------
    if bool(scan_ui_placeholder_variables) and ui_source_dir is not None:
        step += 1
        _emit_progress(progress_cb, step, total_steps, "扫描 UI 源码占位符变量（自动同步）…")

        from ugc_file_tools.node_graph_writeback.ui_custom_variable_sync import (
            scan_ui_source_dir_for_placeholder_variable_refs_and_defaults,
        )

        scan = scan_ui_source_dir_for_placeholder_variable_refs_and_defaults(Path(ui_source_dir))
        if scan.variable_refs:
            # group by scalar/dict
            scalar_refs: set[tuple[str, str]] = set()
            dict_refs: dict[tuple[str, str], set[Tuple[str, ...]]] = {}
            for group_name, var_name, field_path in set(scan.variable_refs):
                g = str(group_name or "").strip()
                n = str(var_name or "").strip()
                fp = tuple(str(x) for x in (field_path or ()))
                if g == "" or n == "":
                    continue
                if not fp:
                    scalar_refs.add((g, n))
                else:
                    dict_refs.setdefault((g, n), set()).add(fp)

            # determine target entity mapping
            level_existing = custom_vars_by_entity_name.get("关卡实体", {})
            player_existing = custom_vars_by_entity_name.get("玩家实体", {})
            default_player_existing = custom_vars_by_entity_name.get("默认模版(角色编辑)", {})

            def _pick_existing(group_name: str) -> tuple[dict[str, int], str]:
                g = str(group_name or "").strip()
                if g == "关卡":
                    return level_existing, "关卡实体"
                if g == "玩家自身":
                    if player_existing:
                        return player_existing, "玩家实体"
                    if default_player_existing:
                        return default_player_existing, "默认模版(角色编辑)"
                    return {}, "<缺少玩家实体>"
                return {}, "<未知变量组>"

            # scalar -> string (type=6)
            for g, n in sorted(scalar_refs, key=lambda t: (t[0].casefold(), t[1].casefold())):
                existed_map, target_name = _pick_existing(g)
                existed_type = existed_map.get(n.casefold())
                if existed_type is None:
                    _add_row(
                        category="UI占位符变量",
                        key=_format_ui_var_ref(g, n, ()),
                        value="type=6（随导出补齐）",
                        status="一同导出",
                        note=f"来源：本次同时导出（UI 自动同步）；目标实体={target_name} 缺少变量（UI源码已引用：写回会自动补齐）。",
                    )
                    continue
                if int(existed_type) == 6:
                    _add_row(
                        category="UI占位符变量",
                        key=_format_ui_var_ref(g, n, ()),
                        value=f"type={int(existed_type)}",
                        status="OK",
                        note=f"目标实体={target_name}",
                    )
                    continue
                _add_row(
                    category="UI占位符变量",
                    key=_format_ui_var_ref(g, n, ()),
                    value=f"type={int(existed_type)}",
                    status="类型不匹配",
                    note=f"目标实体={target_name} 同名变量已存在但类型不是字符串(6)：existing={int(existed_type)}。",
                )

            # dict -> type=27 (keys are best-effort)
            for (g, n), key_paths in sorted(dict_refs.items(), key=lambda t: (t[0][0].casefold(), t[0][1].casefold())):
                existed_map, target_name = _pick_existing(g)
                existed_type = existed_map.get(n.casefold())
                key_strs = sorted({".".join(path) for path in key_paths if path and all(str(x).strip() for x in path)})
                keys_note = f"keys={key_strs[:6]}{'…' if len(key_strs) > 6 else ''}" if key_strs else ""
                if existed_type is None:
                    _add_row(
                        category="UI占位符变量",
                        key=_format_ui_var_ref(g, n, ("<dict>",)),
                        value="type=27（随导出补齐）",
                        status="一同导出",
                        note=(
                            f"来源：本次同时导出（UI 自动同步）；目标实体={target_name} 缺少字典变量（UI源码已引用：写回会自动补齐）。{keys_note}"
                        ),
                    )
                    continue
                if int(existed_type) == 27:
                    _add_row(
                        category="UI占位符变量",
                        key=_format_ui_var_ref(g, n, ("<dict>",)),
                        value=f"type={int(existed_type)}",
                        status="OK",
                        note=f"目标实体={target_name} {keys_note}".strip(),
                    )
                    continue
                _add_row(
                    category="UI占位符变量",
                    key=_format_ui_var_ref(g, n, ("<dict>",)),
                    value=f"type={int(existed_type)}",
                    status="类型不匹配",
                    note=f"目标实体={target_name} 同名变量已存在但类型不是字典(27)：existing={int(existed_type)}。{keys_note}",
                )

    # -------------------- summary --------------------
    step += 1
    _emit_progress(progress_cb, step, total_steps, "汇总…")

    total = int(len(rows))
    ok = sum(1 for r in rows if str(r.get("status")) == "OK")
    bundled = sum(1 for r in rows if str(r.get("status")) == "一同导出")
    missing = sum(1 for r in rows if str(r.get("status")) == "缺失")
    mismatch = sum(1 for r in rows if str(r.get("status")) == "类型不匹配")
    ambiguous = sum(1 for r in rows if str(r.get("status")) == "歧义")

    return {
        "base_gil_path": str(base),
        "id_ref_gil_path": str(id_ref_path if id_ref_path is not None else (base if use_fallback else "")),
        "id_ref_effective_enabled": bool(effective_id_ref is not None),
        "id_ref_used_fallback_base": bool(effective_id_ref is not None and id_ref_path is None and use_fallback),
        "cache": {
            "enabled": bool(workspace_root is not None),
            "base_hit": bool(base_cache_hit),
            "id_ref_hit": bool(id_ref_cache_hit),
        },
        "ui_export_record_id": str(rid),
        "rows": list(rows),
        "summary": {
            "total": int(total),
            "ok": int(ok),
            "bundled": int(bundled),
            "missing": int(missing),
            "mismatch": int(mismatch),
            "ambiguous": int(ambiguous),
            "ui_records_total": int(ui_records_total),
        },
    }


__all__ = [
    "UiKeyPlaceholderUsage",
    "scan_ui_key_placeholders_in_graph_code_files",
    "identify_gil_backfill_comparison",
]

