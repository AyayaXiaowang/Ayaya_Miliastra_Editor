from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..writeback_feature_flags import is_writeback_feature_enabled


def _extract_ui_record_primary_guid(record: Dict[str, Any]) -> Optional[int]:
    from ugc_file_tools.ui.guid_resolution import extract_ui_record_primary_guid

    return extract_ui_record_primary_guid(record)  # type: ignore[arg-type]


def _extract_ui_record_primary_name(record: Dict[str, Any]) -> Optional[str]:
    from ugc_file_tools.ui.guid_resolution import extract_ui_record_primary_name

    return extract_ui_record_primary_name(record)  # type: ignore[arg-type]


def _extract_ui_record_component_type_ids(record: Dict[str, Any]) -> set[int]:
    from ugc_file_tools.ui.guid_resolution import extract_ui_record_component_type_ids

    return extract_ui_record_component_type_ids(record)  # type: ignore[arg-type]


def _maybe_sync_ui_key_guid_registry_with_base_ui_records(
    *,
    ui_key_to_guid_registry: Optional[Dict[str, int]],
    registry_path: Optional[Path],
    base_raw_dump_object: Dict[str, Any],
) -> Optional[Dict[str, int]]:
    """
    工程化修复：当 registry 与 base `.gil` 的 UI 记录不一致时，尝试“按命名约定”自愈修正 registry。

    触发场景（用户常见）：
    - 节点图使用 `ui_key:HTML导入_界面布局__btn_unselect__btn_item`，
      但 base `.gil` 内实际该按钮的 guid 是 1073742012，而 registry 中却记录为 1073742543，
      导致写回阶段把占位符回填成错误 id。

    自愈策略（保守）：
    - 仅对 suffix 为 `__group` / `__btn_item` 的 key 尝试修正（这两类是节点图最常用的 UI 引用）。
    - `__group`：按 UI record 名称精确匹配 `组件组_<data-ui-key>` 定位 group guid。
    - `__btn_item`：先找到 group guid，再在其子项中挑选“道具展示按钮”(component 502==15) 的 guid。
    - 若无法定位，保持原值（fail-fast 行为由下游常量解析负责）。
    """
    if ui_key_to_guid_registry is None or registry_path is None:
        return ui_key_to_guid_registry

    root_data = base_raw_dump_object.get("4")
    if not isinstance(root_data, dict):
        return ui_key_to_guid_registry
    field9 = root_data.get("9")
    if not isinstance(field9, dict):
        return ui_key_to_guid_registry
    record_list = field9.get("502")
    if not isinstance(record_list, list):
        return ui_key_to_guid_registry

    from ugc_file_tools.ui.guid_resolution import infer_ui_key_guid_registry_overrides_from_ui_records_for_group_and_btn_item

    overrides = infer_ui_key_guid_registry_overrides_from_ui_records_for_group_and_btn_item(
        ui_key_to_guid_registry=dict(ui_key_to_guid_registry or {}),
        ui_records=list(record_list),
    )
    if not overrides:
        return ui_key_to_guid_registry

    updated = dict(ui_key_to_guid_registry)
    for k, v in overrides.items():
        updated[str(k)] = int(v)

    # 写回 registry（带历史留档）
    from ugc_file_tools.ui.guid_registry_format import save_ui_guid_registry

    save_ui_guid_registry(Path(registry_path), updated)
    return updated


def maybe_sync_ui_key_guid_registry_with_base_ui_records(
    *,
    ui_key_to_guid_registry: Optional[Dict[str, int]],
    registry_path: Optional[Path],
    base_raw_dump_object: Dict[str, Any],
) -> Optional[Dict[str, int]]:
    return _maybe_sync_ui_key_guid_registry_with_base_ui_records(
        ui_key_to_guid_registry=ui_key_to_guid_registry,
        registry_path=registry_path,
        base_raw_dump_object=base_raw_dump_object,
    )


def _maybe_fill_missing_ui_keys_with_base_ui_records(
    *,
    ui_key_to_guid_registry: Dict[str, int],
    registry_path: Optional[Path],
    required_ui_keys: set[str],
    base_raw_dump_object: Dict[str, Any],
    layout_name_hint: Optional[str] = None,
) -> Dict[str, int]:
    """
    工程化兜底：当 registry 缺失某些 UIKey 时，尝试从 base `.gil` 的 UI records 反查 GUID 并补齐。

    - 仅补齐当前 GraphModel 里实际用到的 key（required_ui_keys）。
    - 若 registry_path 存在，则在补齐后持久化写回（带历史留档）；否则仅在本次写回过程内生效。
    """
    if not required_ui_keys:
        return ui_key_to_guid_registry

    # ------------------------------------------------------------------ 旧 UIKey 别名兜底（纯规则，无 IO）
    from ugc_file_tools.ui.guid_resolution import apply_legacy_ui_key_aliases_for_required_keys

    ui_key_to_guid_registry = apply_legacy_ui_key_aliases_for_required_keys(
        ui_key_to_guid_registry=dict(ui_key_to_guid_registry or {}),
        required_ui_keys=set(required_ui_keys),
    )

    root_data = base_raw_dump_object.get("4")
    if not isinstance(root_data, dict):
        return ui_key_to_guid_registry
    field9 = root_data.get("9")
    if not isinstance(field9, dict):
        return ui_key_to_guid_registry
    record_list = field9.get("502")
    if not isinstance(record_list, list):
        return ui_key_to_guid_registry

    from ugc_file_tools.ui.guid_resolution import fill_missing_required_ui_keys_from_ui_records

    updated, changes = fill_missing_required_ui_keys_from_ui_records(
        ui_key_to_guid_registry=dict(ui_key_to_guid_registry or {}),
        required_ui_keys=set(required_ui_keys),
        ui_records=list(record_list),
        layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
    )

    if changes and registry_path is not None:
        from ugc_file_tools.ui.guid_registry_format import save_ui_guid_registry

        save_ui_guid_registry(Path(registry_path), updated)

    return updated


def _infer_layout_name_hint_from_graph_json_object(graph_json_object: Dict[str, Any]) -> Optional[str]:
    """
    尝试从 GraphModel(JSON) 元信息中推断 layout_name_hint（用于 UI records 消歧）：

    典型场景：
    - 多个页面都存在同名控件（例如 btn_exit），而 Graph Code 仍使用旧口径
      `HTML导入_界面布局__btn_exit__btn_item`；
    - 若不提供 layout_name_hint，基于 UI record_name 的反查可能命中多个 layout，导致无法唯一确定 GUID。

    推断策略（保守）：
    - 优先从 description 中提取 `管理配置/UI源码/<name>.html` 的 <name>（与 Workbench bundle 文件名一致）；
    - 兼容反斜杠路径；
    - 未命中则返回 None（保持旧行为）。
    """
    import re

    desc = str(graph_json_object.get("description") or "")
    if desc:
        # 例：配套 `管理配置/UI源码/第七关-游戏中.html` 的交互...
        m = re.search(r"管理配置[\\/]+UI源码[\\/]+([^\\/`\"']+?)\.html", desc)
        if m:
            name = str(m.group(1) or "").strip()
            return name if name else None
    return None


def _try_parse_optional_hidden_state_group_key(ui_key: str) -> str | None:
    key = str(ui_key or "").strip()
    if not key.startswith("UI_STATE_GROUP__"):
        return None
    parts = [p for p in key.split("__") if str(p)]
    if len(parts) < 4 or parts[0] != "UI_STATE_GROUP" or parts[-1] != "group":
        return None
    group = str(parts[1]).strip()
    state = str(parts[2]).strip().lower()
    if group == "" or state not in {"hidden", "hide"}:
        return None
    return group


def _try_parse_state_group_key(ui_key: str) -> tuple[str, str] | None:
    key = str(ui_key or "").strip()
    if not key.startswith("UI_STATE_GROUP__"):
        return None
    parts = [p for p in key.split("__") if str(p)]
    if len(parts) < 4 or parts[0] != "UI_STATE_GROUP" or parts[-1] != "group":
        return None
    group = str(parts[1]).strip()
    state = str(parts[2]).strip()
    if group == "" or state == "":
        return None
    return str(group), str(state)


def _iter_state_group_name_candidates(group_name: str) -> List[str]:
    group = str(group_name or "").strip()
    if group == "":
        return []
    out: List[str] = [group]
    if group.endswith("_state"):
        short = str(group[: -len("_state")]).strip()
        if short:
            out.append(short)
    else:
        out.append(f"{group}_state")

    deduped: List[str] = []
    seen: set[str] = set()
    for item in out:
        s = str(item).strip()
        if s == "" or s in seen:
            continue
        seen.add(s)
        deduped.append(s)
    return deduped


def _infer_expected_ui_record_names_for_state_group_key(ui_key: str) -> List[str]:
    parsed = _try_parse_state_group_key(str(ui_key))
    if parsed is None:
        return []
    group, state = parsed
    group_candidates = _iter_state_group_name_candidates(str(group))
    out: List[str] = []
    for g in group_candidates:
        out.append(f"组件组_{g}__{state}")
    # 去重保持顺序
    seen: set[str] = set()
    deduped: List[str] = []
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _registry_has_any_non_hidden_state_alias_for_group(
    *,
    group_name: str,
    ui_key_to_guid_registry: Mapping[str, int] | None,
) -> bool:
    if not isinstance(ui_key_to_guid_registry, Mapping) or not ui_key_to_guid_registry:
        return False
    group_names = _iter_state_group_name_candidates(str(group_name))
    if not group_names:
        return False

    for gname in group_names:
        prefix = f"UI_STATE_GROUP__{gname}__"
        for raw_key, raw_guid in ui_key_to_guid_registry.items():
            if not isinstance(raw_guid, int) or int(raw_guid) <= 0:
                continue
            k = str(raw_key or "").strip()
            if not (k.startswith(prefix) and k.endswith("__group")):
                continue
            parts = [p for p in k.split("__") if str(p)]
            if len(parts) < 4 or parts[0] != "UI_STATE_GROUP":
                continue
            state = str(parts[2]).strip().lower()
            if state != "" and state not in {"hidden", "hide"}:
                return True
    return False


def _classify_missing_ui_keys_with_optional_hidden_semantics(
    *,
    required_ui_keys: set[str],
    ui_key_to_guid_registry: Mapping[str, int] | None,
) -> Tuple[List[str], List[str]]:
    """
    hidden 语义可选：允许 `UI_STATE_GROUP__<group>__hidden__group` 缺失，
    前提是同组存在任一非 hidden 状态映射（表示该组已可被显隐逻辑控制）。
    """
    registry: Dict[str, int] = {}
    if isinstance(ui_key_to_guid_registry, Mapping):
        for k, v in ui_key_to_guid_registry.items():
            key = str(k or "").strip()
            if key == "":
                continue
            if isinstance(v, int) and int(v) > 0:
                registry[key] = int(v)

    optional_hidden_missing: List[str] = []
    fatal_missing: List[str] = []
    for key in sorted({str(k or "").strip() for k in required_ui_keys if str(k or "").strip()}):
        existing = registry.get(str(key))
        if isinstance(existing, int) and int(existing) > 0:
            continue
        hidden_group = _try_parse_optional_hidden_state_group_key(str(key))
        if hidden_group is None:
            fatal_missing.append(str(key))
            continue
        if _registry_has_any_non_hidden_state_alias_for_group(
            group_name=str(hidden_group),
            ui_key_to_guid_registry=registry,
        ):
            optional_hidden_missing.append(str(key))
            continue
        fatal_missing.append(str(key))
    return optional_hidden_missing, fatal_missing


def _collect_ui_key_placeholder_occurrences_from_graph_json_object(graph_json_object: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    收集 GraphModel(JSON) 内所有 `ui_key:` / `ui:` 占位符出现位置（用于缺失映射时报更详细上下文）。

    返回：
    - key -> [path, ...]

    path 采用轻量 JSONPath 风格（便于 grep/肉眼定位），例如：
    - $.nodes[3].input_constants.对白框_show组
    - $.graph_variables[0].default_value
    """

    def _path_to_text(parts: List[str]) -> str:
        if not parts:
            return "$"
        return "$" + "".join(parts)

    occurrences: Dict[str, List[str]] = {}

    def _walk(obj: Any, path_parts: List[str]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key_text = str(k)
                # dict key 用 .<key>；特殊字符不转义（与 repo 内多数字段命名一致，便于直观定位）
                _walk(v, path_parts + [f".{key_text}"])
            return
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, path_parts + [f"[{int(i)}]"])
            return
        if isinstance(obj, str):
            s = str(obj).strip()
            if s.startswith("ui_key:"):
                key = str(s[len("ui_key:") :]).strip()
                if key != "":
                    occurrences.setdefault(key, []).append(_path_to_text(path_parts))
            elif s.startswith("ui:"):
                key = str(s[len("ui:") :]).strip()
                if key != "":
                    occurrences.setdefault(key, []).append(_path_to_text(path_parts))
            return

    if isinstance(graph_json_object, dict):
        _walk(graph_json_object, [])
    return occurrences


def _build_missing_ui_keys_debug_text(
    *,
    graph_model_json_path: Path,
    graph_json_object: Dict[str, Any],
    missing_ui_keys: List[str],
    required_ui_keys: set[str],
    ui_key_to_guid_registry: Mapping[str, int] | None,
    base_gil_path: Path,
    base_raw_dump_object: Dict[str, Any],
    layout_name_hint: Optional[str],
) -> str:
    """
    仅在缺失 ui_key 时构造额外诊断信息：尽量把“缺在哪、可能为什么缺、从哪修”一次性打印出来。
    """
    missing = [str(x or "").strip() for x in list(missing_ui_keys) if str(x or "").strip() != ""]
    if not missing:
        return ""

    registry: Dict[str, int] = {}
    if isinstance(ui_key_to_guid_registry, Mapping):
        for k, v in ui_key_to_guid_registry.items():
            kk = str(k or "").strip()
            if kk == "":
                continue
            if isinstance(v, int) and int(v) > 0:
                registry[kk] = int(v)

    # base UI records index（仅用于诊断；与 fill 逻辑一致）
    base_ui_records_total = 0
    ui_names: set[str] = set()
    root_data = base_raw_dump_object.get("4")
    if isinstance(root_data, dict):
        field9 = root_data.get("9")
        if isinstance(field9, dict):
            record_list = field9.get("502")
            if isinstance(record_list, list):
                base_ui_records_total = int(len(record_list))
                for r0 in record_list:
                    if not isinstance(r0, dict):
                        continue
                    nm = _extract_ui_record_primary_name(r0)
                    if isinstance(nm, str) and nm != "":
                        ui_names.add(str(nm))

    occurrences = _collect_ui_key_placeholder_occurrences_from_graph_json_object(graph_json_object)

    def _pick_similar_keys(key: str, limit: int = 30) -> List[str]:
        k = str(key or "").strip()
        if k == "":
            return []
        # UI_STATE_GROUP：优先同组
        if k.startswith("UI_STATE_GROUP__"):
            parts = [p for p in k.split("__") if str(p)]
            if len(parts) >= 4 and parts[0] == "UI_STATE_GROUP":
                group = str(parts[1]).strip()
                if group != "":
                    prefixes = [f"UI_STATE_GROUP__{group}__", f"UI_STATE_GROUP__{group}_state__"]
                    cands = [x for x in registry.keys() if any(str(x).startswith(p) for p in prefixes)]
                    return sorted({str(x) for x in cands}, key=lambda t: t.casefold())[: int(limit)]
        # fallback：同前缀（前三段）
        parts2 = [p for p in k.split("__") if str(p)]
        if len(parts2) >= 3:
            pref = "__".join(parts2[:3]) + "__"
            cands2 = [x for x in registry.keys() if str(x).startswith(pref)]
            if cands2:
                return sorted({str(x) for x in cands2}, key=lambda t: t.casefold())[: int(limit)]
        return []

    lines: List[str] = []
    lines.append("\n\n--- 缺失 ui_key 诊断信息（增强）---")
    lines.append(f"- graph_model: {str(Path(graph_model_json_path).resolve())}")
    lines.append(f"- base_gil: {str(Path(base_gil_path).resolve())}")
    if layout_name_hint is not None and str(layout_name_hint).strip() != "":
        lines.append(f"- layout_name_hint: {str(layout_name_hint).strip()}")
    graph_code_file = str(graph_json_object.get("graph_code_file") or "").strip()
    if graph_code_file != "":
        lines.append(f"- graph_code_file: {graph_code_file}")
    lines.append(f"- required_ui_keys_total: {int(len(required_ui_keys))}")
    lines.append(f"- ui_key_registry_total(available>0): {int(len(registry))}")
    lines.append(f"- base_ui_records_total: {int(base_ui_records_total)}")

    # 每个缺失 key 给出“出现位置 + 可能原因线索”
    for key in sorted({str(x) for x in missing if str(x)}, key=lambda t: t.casefold()):
        lines.append(f"\n- missing_ui_key: {key}")
        occ = occurrences.get(str(key), [])
        if occ:
            lines.append(f"  - occurrences_in_graph_model(total={int(len(occ))}):")
            for p in occ[:20]:
                lines.append(f"    - {p}")
            if len(occ) > 20:
                lines.append("    - ... (more omitted)")
        else:
            lines.append("  - occurrences_in_graph_model: <not_found_by_recursive_scan>")

        expected_names = _infer_expected_ui_record_names_for_state_group_key(str(key))
        if expected_names:
            lines.append("  - ui_record_name_expected_for_state_group:")
            for nm in expected_names:
                exists = nm in ui_names
                lines.append(f"    - {nm}  (exists_in_base_ui_records={str(bool(exists)).lower()})")
            lines.append(
                "  - hint: 若这些 record 名称都不存在，通常表示该 state-group 容器没有被 UI Workbench 导出为可写回的控件/组容器；"
                "常见原因是 HTML 元素缺少 data-ui-key 或导出规则只导出带 ui_key 的元素。"
            )

        similar = _pick_similar_keys(str(key))
        if similar:
            lines.append(f"  - similar_keys_in_registry(sample={int(len(similar))}):")
            for s in similar[:30]:
                lines.append(f"    - {s}")
        else:
            lines.append("  - similar_keys_in_registry: <none>")

    return "\n".join(lines)


def _prepare_ui_key_to_guid_registry_for_writeback(
    *,
    ui_key_to_guid_registry: Dict[str, int],
    required_ui_keys: set[str],
    base_raw_dump_object: Dict[str, Any],
    layout_name_hint: Optional[str],
) -> Dict[str, int]:
    effective_registry: Dict[str, int] = dict(ui_key_to_guid_registry or {})
    if is_writeback_feature_enabled("ui_key_registry_fill_missing_from_base_ui_records"):
        effective_registry = _maybe_fill_missing_ui_keys_with_base_ui_records(
            ui_key_to_guid_registry=effective_registry,
            registry_path=None,
            required_ui_keys=set(required_ui_keys),
            base_raw_dump_object=base_raw_dump_object,
            layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
        )
    return dict(effective_registry)


def _validate_required_ui_keys_or_raise(
    *,
    graph_model_json_path: Path,
    graph_json_object: Dict[str, Any],
    required_ui_keys: set[str],
    ui_key_to_guid_registry: Mapping[str, int] | None,
    base_gil_path: Path,
    base_raw_dump_object: Dict[str, Any],
    layout_name_hint: Optional[str],
) -> Tuple[bool, List[str]]:
    optional_hidden_missing_ui_keys, fatal_missing_ui_keys = _classify_missing_ui_keys_with_optional_hidden_semantics(
        required_ui_keys=set(required_ui_keys),
        ui_key_to_guid_registry=ui_key_to_guid_registry,
    )
    # 导出/模板场景常见：UI_STATE_GROUP 容器未被 Workbench 导出为可写回控件/组容器，
    # 从而无法建立稳定的 ui_key→GUID 映射。此时阻断写回/导出并无帮助；
    # 改为允许缺失并在常量回填阶段将其回填为 0（保持 fail-fast 仅针对“非状态组”UIKey）。
    optional_missing_state_group_ui_keys = [
        str(k)
        for k in list(fatal_missing_ui_keys or [])
        if str(k or "").strip().startswith("UI_STATE_GROUP__") and str(k or "").strip().endswith("__group")
    ]
    fatal_missing_ui_keys = [
        str(k)
        for k in list(fatal_missing_ui_keys or [])
        if str(k) not in set(optional_missing_state_group_ui_keys)
    ]

    optional_missing_ui_keys = sorted(
        {str(x or "").strip() for x in list(optional_hidden_missing_ui_keys or []) + list(optional_missing_state_group_ui_keys or []) if str(x or "").strip()},
        key=lambda t: t.casefold(),
    )

    # 需求：缺失不阻断写回，统一允许 unresolved 并回填为 0。
    # - UI_STATE_GROUP 已在上方归入 optional；
    # - 其余缺失 key 也归入 optional（与 `.gia` 导出侧的“允许缺失继续导出”策略对齐）。
    optional_missing_ui_keys2 = sorted(
        {str(x or "").strip() for x in list(optional_missing_ui_keys or []) + list(fatal_missing_ui_keys or []) if str(x or "").strip()},
        key=lambda t: t.casefold(),
    )
    allow_unresolved_ui_keys = bool(optional_missing_ui_keys2)
    return bool(allow_unresolved_ui_keys), list(optional_missing_ui_keys2)

