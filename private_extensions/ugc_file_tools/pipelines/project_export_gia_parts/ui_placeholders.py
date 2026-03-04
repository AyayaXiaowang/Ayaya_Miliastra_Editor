from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ui_export_context import UiExportContext
from .ui_infer import _infer_primary_ui_layout_name_from_graph_code_file, _resolve_ui_key_guid_from_output_gil


@dataclass(frozen=True, slots=True)
class ResolvedUiKeyPlaceholders:
    effective_ui_key_to_guid: dict[str, int] | None
    implicit_unresolved_ui_keys: list[str]
    allow_unresolved_effective: bool


def resolve_ui_key_placeholders_for_graph(
    *,
    placeholders: set[str],
    graph_code_file: Path,
    ui_ctx: UiExportContext,
    allow_unresolved_ui_keys: bool,
) -> ResolvedUiKeyPlaceholders:
    """
    解析单张图用到的 ui_key 占位符 → guid 映射表（或允许缺映射回填为 0）。

    保持与历史实现一致的行为：
    - 优先从 output_gil UI records 按 layout hint 反查（最可靠）
    - fallback 到 registry snapshot
    - 缺失 key 默认 fail-fast，除非 allow_unresolved 或符合“隐式 state group key”放行规则：
      - UI_STATE_GROUP__*__*__group 缺失会被允许并回填为 0（常见原因：Workbench 未导出可写回组容器）
    - 若记录绑定 output_gil，则校验回填 GUID 必须存在于该 output_gil 的 UI records（避免串包）
    """
    record_id_text = str(ui_ctx.record_id_text or "").strip()
    selected_ui_export_record = ui_ctx.selected_ui_export_record
    selected_ui_export_record_ui_index = ui_ctx.selected_ui_export_record_ui_index
    selected_ui_export_record_ui_guids = ui_ctx.selected_ui_export_record_ui_guids
    ui_key_to_guid_registry = ui_ctx.ui_key_to_guid_registry

    implicit_unresolved_ui_keys: list[str] = []
    allow_unresolved_effective = bool(allow_unresolved_ui_keys)
    effective_ui_key_to_guid: dict[str, int] | None = None

    if placeholders:
        # per-graph registry：避免 legacy key 在多页面间发生冲突（同名控件在不同 layout GUID 不同）
        if selected_ui_export_record_ui_index is not None:
            layout_name_hint = _infer_primary_ui_layout_name_from_graph_code_file(Path(graph_code_file))
            root_name_cache: dict[int, str | None] = {}
            resolved: dict[str, int] = {}
            for k in sorted(placeholders):
                guid = _resolve_ui_key_guid_from_output_gil(
                    ui_key=str(k),
                    layout_name_hint=layout_name_hint,
                    ui_index=selected_ui_export_record_ui_index,
                    root_name_cache=root_name_cache,
                )
                if isinstance(guid, int) and int(guid) > 0:
                    resolved[str(k)] = int(guid)

            # fallback: 若 output_gil 反查失败，则退回使用 snapshot registry（适配无 output_gil 或部分特殊 key）
            if ui_key_to_guid_registry is not None:
                for k in sorted(placeholders):
                    if str(k) in resolved:
                        continue
                    guid = ui_key_to_guid_registry.get(str(k))
                    if isinstance(guid, int) and int(guid) > 0:
                        resolved[str(k)] = int(guid)

            effective_ui_key_to_guid = resolved
        else:
            effective_ui_key_to_guid = ui_key_to_guid_registry

        if effective_ui_key_to_guid is None and not bool(allow_unresolved_ui_keys):
            raise ValueError(
                "检测到节点图使用了 ui_key: 占位符，但当前导出未选择任何 UI 导出记录，无法回填后导出 .gia。\n"
                "- 解决方案：在导出对话框中选择正确的 UI 导出记录（或先从网页导出一次 GIL 生成记录），再导出 .gia；\n"
                "- 或显式允许缺映射继续导出（缺失的 ui_key 将回填为 0，游戏内交互通常会失效）。\n"
                f"- 本图占位符 keys：{sorted(placeholders)}"
            )

        if effective_ui_key_to_guid is not None:
            missing = sorted([k for k in placeholders if str(k) not in effective_ui_key_to_guid])
            if missing and not bool(allow_unresolved_ui_keys):

                def _is_implicit_optional_state_group_key(k: str) -> bool:
                    kk = str(k or "").strip()
                    if not kk.startswith("UI_STATE_GROUP__"):
                        return False
                    return bool(kk.endswith("__group"))

                def _try_parse_implicit_hidden_state_group_key(k: str) -> str | None:
                    kk = str(k or "").strip()
                    if not kk.startswith("UI_STATE_GROUP__"):
                        return None
                    parts = [p for p in kk.split("__") if str(p)]
                    if len(parts) >= 4 and parts[0] == "UI_STATE_GROUP" and parts[-1] == "group":
                        group = str(parts[1]).strip()
                        state = str(parts[2]).strip().lower()
                        if group != "" and state in {"hidden", "hide"}:
                            return group
                    return None

                def _has_any_non_hidden_state_mapping_for_group(group_name: str) -> bool:
                    group = str(group_name or "").strip()
                    if group == "":
                        return False
                    candidates = [group]
                    if group.endswith("_state"):
                        short = str(group[: -len("_state")]).strip()
                        if short:
                            candidates.append(short)
                    else:
                        candidates.append(f"{group}_state")
                    seen: set[str] = set()
                    for gname in candidates:
                        gg = str(gname).strip()
                        if gg == "" or gg in seen:
                            continue
                        seen.add(gg)
                        prefix = f"UI_STATE_GROUP__{gg}__"
                        for raw_key, raw_guid in (effective_ui_key_to_guid or {}).items():
                            if not isinstance(raw_guid, int) or int(raw_guid) <= 0:
                                continue
                            kk = str(raw_key or "").strip()
                            if not (kk.startswith(prefix) and kk.endswith("__group")):
                                continue
                            parts = [p for p in kk.split("__") if str(p)]
                            if len(parts) < 4 or parts[0] != "UI_STATE_GROUP":
                                continue
                            state = str(parts[2]).strip().lower()
                            if state != "" and state not in {"hidden", "hide"}:
                                return True
                    return False

                implicit_missing: list[str] = []
                fatal_missing: list[str] = []
                for k in list(missing):
                    if _is_implicit_optional_state_group_key(str(k)):
                        implicit_missing.append(str(k))
                        continue
                    group = _try_parse_implicit_hidden_state_group_key(str(k))
                    if group is None:
                        fatal_missing.append(str(k))
                        continue
                    if _has_any_non_hidden_state_mapping_for_group(str(group)):
                        implicit_missing.append(str(k))
                        continue
                    fatal_missing.append(str(k))

                if implicit_missing:
                    implicit_unresolved_ui_keys = sorted({str(x) for x in implicit_missing if str(x).strip() != ""})
                    allow_unresolved_effective = True

                missing = sorted({str(x) for x in fatal_missing if str(x).strip() != ""})

            if missing and not bool(allow_unresolved_effective):
                extra_hint_lines: list[str] = []
                if selected_ui_export_record is not None:
                    extra_hint_lines.append(f"- ui_export_record_id: {record_id_text!r}")
                    extra_hint_lines.append(f"- output_gil_file: {str(selected_ui_export_record.get('output_gil_file') or '')}")
                extra_hint_text = ("\n".join(extra_hint_lines) + "\n") if extra_hint_lines else ""
                raise ValueError(
                    "检测到节点图使用了 ui_key: 占位符，但注册表缺少部分 key，无法回填后导出 .gia。\n"
                    + extra_hint_text
                    + f"- 缺失 keys：{missing}\n"
                    + "- 解决方案：选择正确的 UI 导出记录（或重新从网页导出一次 GIL）后再导出；\n"
                    + "- 或显式允许缺映射继续导出（缺失的 ui_key 将回填为 0）。"
                )

        if selected_ui_export_record is not None and selected_ui_export_record_ui_guids is not None and effective_ui_key_to_guid is not None:
            mismatched: list[dict[str, object]] = []
            for k in sorted(placeholders):
                guid = effective_ui_key_to_guid.get(str(k))
                if not isinstance(guid, int):
                    continue
                gg = int(guid)
                if gg < 1_000_000_000:
                    continue
                if gg not in selected_ui_export_record_ui_guids:
                    mismatched.append({"ui_key": str(k), "guid": int(gg)})
            if mismatched and not bool(allow_unresolved_ui_keys):
                raise ValueError(
                    "所选 UI 导出记录的 output_gil 不包含部分回填后的控件 GUID，无法保证节点图交互对得上。\n"
                    f"- ui_export_record_id: {record_id_text!r}\n"
                    f"- output_gil_file: {str(selected_ui_export_record.get('output_gil_file') or '')}\n"
                    f"- mismatched (showing first 30): {mismatched[:30]}\n"
                    "解决方案：在导出对话框中选择正确的 UI 导出记录，或重新从网页导出一次 GIL 后再导出节点图 GIA。"
                )

    return ResolvedUiKeyPlaceholders(
        effective_ui_key_to_guid=effective_ui_key_to_guid,
        implicit_unresolved_ui_keys=list(implicit_unresolved_ui_keys),
        allow_unresolved_effective=bool(allow_unresolved_effective),
    )

