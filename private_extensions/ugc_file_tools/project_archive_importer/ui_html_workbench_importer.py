from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _iter_ui_workbench_bundle_files(project_root: Path) -> List[Path]:
    """
    UI源码（HTML）转换器的输出目录约定：
    - 管理配置/UI源码/__workbench_out__/*.ui_bundle.json
    """
    out_dir = (Path(project_root) / "管理配置" / "UI源码" / "__workbench_out__").resolve()
    if not out_dir.is_dir():
        return []
    return [p.resolve() for p in sorted(out_dir.glob("*.ui_bundle.json"), key=lambda x: x.as_posix()) if p.is_file()]


def _infer_layout_name_from_bundle_file(bundle_path: Path) -> str:
    """
    Workbench 输出的 `layout.layout_name` 在多个页面之间可能重复（常见：全部叫“HTML导入_界面布局”），
    导致写回后在编辑器里难以区分，也更容易让人误判“导入没反应”。

    因此这里以文件名为准：`adventure_ui_mockup.ui_bundle.json` -> `adventure_ui_mockup`。
    """
    name = str(Path(bundle_path).name)
    suffix = ".ui_bundle.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return str(Path(bundle_path).stem)


def _try_find_existing_layout_guid_by_name(gil_file_path: Path, *, layout_name: str) -> int | None:
    """
    若 base .gil 已存在同名布局 root，则优先复用该布局 GUID（写入同一布局，用户才“看得到变化”）。

    注意：
    - 这里只做“尽力而为”的匹配：命中则复用，未命中则返回 None 走新建布局流程；
    - 不在这里做复杂推断（避免引入错误匹配导致覆盖不该覆盖的布局）。
    """
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import dump_gil_to_raw_json_object
    from ugc_file_tools.ui.readable_dump import (
        extract_primary_guid as _extract_primary_guid,
        extract_primary_name as _extract_primary_name,
        extract_ui_record_list as _extract_ui_record_list,
    )

    target = str(layout_name or "").strip()
    if target == "":
        return None

    raw_dump = dump_gil_to_raw_json_object(Path(gil_file_path).resolve())
    payload_root = raw_dump.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")

    # 兼容：空/极简基底 .gil 可能缺失 UI 段（root4/9=None），此时视为“没有可复用布局”，
    # 继续走后续新建布局/写回 bootstrap（由 web_ui_import_prepare 负责注入最小 UI 段）。
    node9 = payload_root.get("9")
    if node9 is None:
        return None

    ui_record_list = _extract_ui_record_list(raw_dump)
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        # 布局 root：无 parent（504）
        if "504" in record:
            continue
        name_text = _extract_primary_name(record)
        if str(name_text or "").strip() != target:
            continue
        guid = _extract_primary_guid(record)
        if isinstance(guid, int):
            return int(guid)
    return None


def import_ui_from_workbench_bundles_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    auto_sync_custom_variables: bool = True,
    include_layout_names: list[str] | None = None,
    layout_conflict_resolutions: list[dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """
    将 UI源码转换器（Workbench）导出的 ui_bundle.json 写回到 .gil。

    说明：
    - 该入口是“从项目存档导出 .gil”链路的一部分；
    - 不依赖 raw_template（record bundle），直接走 web import 生成/更新 UI record；
    - 每个 bundle 会写回一次，按顺序链式叠加到输出 .gil（即 output 作为下一轮 input）。
    """
    project_root = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    # layout_name -> resolution dict
    # 约定：只对 Workbench bundle 写回生效；raw_template 写回不走本模块。
    resolution_by_layout_name: Dict[str, Dict[str, str]] = {}
    if layout_conflict_resolutions:
        seen: set[str] = set()
        for idx, item in enumerate(list(layout_conflict_resolutions)):
            if not isinstance(item, dict):
                raise TypeError(f"layout_conflict_resolutions[{idx}] must be dict")
            layout_name = str(item.get("layout_name") or "").strip()
            if layout_name == "":
                raise ValueError(f"layout_conflict_resolutions[{idx}].layout_name 不能为空")
            action = str(item.get("action") or "").strip().lower()
            if action not in {"overwrite", "add", "skip"}:
                raise ValueError(
                    f"layout_conflict_resolutions[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
                )
            new_layout_name = str(item.get("new_layout_name") or "").strip()
            if action == "add" and new_layout_name == "":
                raise ValueError(f"layout_conflict_resolutions[{idx}] action=add 时 new_layout_name 不能为空")
            key = layout_name.casefold()
            if key in seen:
                raise ValueError(f"layout_conflict_resolutions 中存在重复 layout_name（忽略大小写）：{layout_name!r}")
            seen.add(key)
            res: Dict[str, str] = {"layout_name": layout_name, "action": action}
            if action == "add":
                res["new_layout_name"] = new_layout_name
            resolution_by_layout_name[layout_name] = res

    bundle_files = _iter_ui_workbench_bundle_files(project_root)
    if not bundle_files:
        raise FileNotFoundError(
            f"未找到 UI Workbench bundle：{str(project_root / '管理配置' / 'UI源码' / '__workbench_out__')}/*.ui_bundle.json"
        )

    # 可选：按 layout_name 过滤写回范围（由导出中心 selection-json 提供）。
    # 说明：
    # - layout_name 口径与 `_infer_layout_name_from_bundle_file` 保持一致（按 bundle 文件名推断）。
    # - 仅当调用方明确提供 include_layout_names 时才启用过滤；缺省仍写回全部 bundle。
    if include_layout_names is not None:
        want: list[str] = []
        seen_cf: set[str] = set()
        for x in list(include_layout_names or []):
            name = str(x or "").strip()
            if name == "":
                continue
            k = name.casefold()
            if k in seen_cf:
                continue
            seen_cf.add(k)
            want.append(name)

        if want:
            want_cf = {n.casefold() for n in want}
            filtered = [p for p in list(bundle_files) if _infer_layout_name_from_bundle_file(p).casefold() in want_cf]
            if not filtered:
                existing = [_infer_layout_name_from_bundle_file(p) for p in list(bundle_files)]
                raise ValueError(
                    "指定的 UI 页面未找到对应 Workbench bundle（按 bundle 文件名推断 layout_name）。\n"
                    f"- selected_ui_layout_names={want}\n"
                    f"- existing_bundles={existing}"
                )
            bundle_files = list(filtered)

    from ugc_file_tools.ui_patchers import import_web_ui_control_group_template_to_gil_layout

    # 设计调整：不再在项目存档内维护 `管理配置/UI控件GUID映射/ui_guid_registry.json`。
    #
    # 原因：
    # - registry 易随导出顺序/去重策略漂移，且会成为“UI+节点图同次写回”的脆弱前置条件；
    # - 节点图写回阶段应以“本次写回后的 output .gil UI records”为真源反查 GUID，
    #   从而让同次导出天然一致，不要求用户维护映射表文件。
    ui_guid_registry_path = None

    current_input = input_path
    bundle_reports: List[Dict[str, Any]] = []
    merged_ui_key_to_guid_for_writeback: Dict[str, int] = {}
    merged_conflicts: List[Dict[str, Any]] = []
    skipped_total = 0
    for bundle_path in bundle_files:
        layout_name = _infer_layout_name_from_bundle_file(bundle_path)
        resolution = resolution_by_layout_name.get(layout_name)
        action = str(resolution.get("action") if isinstance(resolution, dict) else "" or "").strip().lower()
        if action == "":
            action = "overwrite"

        if action == "skip":
            skipped_total += 1
            bundle_reports.append(
                {
                    "bundle": str(bundle_path),
                    "layout_name": str(layout_name),
                    "layout_name_written": None,
                    "action": "skip",
                    "skipped": True,
                }
            )
            continue

        layout_name_written = str(layout_name)
        target_layout_guid: int | None = None
        if action == "add":
            layout_name_written = str(resolution.get("new_layout_name") or "").strip() if isinstance(resolution, dict) else ""
            if layout_name_written == "":
                raise ValueError(f"layout_conflict_resolutions 缺少 new_layout_name（layout_name={layout_name!r}）")
            # guard：避免误生成“同名新增”导致编辑器里两条同名布局难以区分
            existing_guid = _try_find_existing_layout_guid_by_name(Path(current_input), layout_name=layout_name_written)
            if existing_guid is not None:
                raise ValueError(
                    f"新增布局名与目标 gil 已存在布局冲突：new_layout_name={layout_name_written!r}, existing_guid={int(existing_guid)}"
                )
            target_layout_guid = None
        elif action == "overwrite":
            target_layout_guid = _try_find_existing_layout_guid_by_name(Path(current_input), layout_name=layout_name_written)
        else:
            raise ValueError(f"unsupported layout conflict action: {action!r}")

        step_output = output_path
        step_output.parent.mkdir(parents=True, exist_ok=True)
        report = import_web_ui_control_group_template_to_gil_layout(
            input_gil_file_path=Path(current_input),
            output_gil_file_path=Path(step_output),
            template_json_file_path=Path(bundle_path),
            target_layout_guid=(int(target_layout_guid) if target_layout_guid is not None else None),
            new_layout_name=str(layout_name_written),
            base_layout_guid=None,
            empty_layout=False,
            clone_children=True,
            enable_progressbars=True,
            enable_textboxes=True,
            textbox_template_gil_file_path=None,
            item_display_template_gil_file_path=None,
            verify_with_dll_dump=False,
            ui_guid_registry_file_path=None,
            auto_sync_custom_variables=bool(auto_sync_custom_variables),
            # 导出中心链路：暂不接入“固有控件初始显隐覆盖”（HUD builtin visibility overrides）。
            # 原因：目标 base `.gil` 可能不含这些固有控件，强制应用会 fail-fast 阻断整次导出。
            enable_builtin_widgets_visibility_overrides=False,
        )

        ui_key_to_guid_for_writeback = report.get("ui_key_to_guid_for_writeback")
        if isinstance(ui_key_to_guid_for_writeback, dict):
            for k, v in ui_key_to_guid_for_writeback.items():
                key = str(k or "").strip()
                if key == "":
                    continue
                if not isinstance(v, int) or int(v) <= 0:
                    continue
                prev = merged_ui_key_to_guid_for_writeback.get(key)
                if prev is None:
                    merged_ui_key_to_guid_for_writeback[key] = int(v)
                elif int(prev) != int(v):
                    merged_conflicts.append(
                        {
                            "ui_key": str(key),
                            "existing_guid": int(prev),
                            "new_guid": int(v),
                            "bundle": str(bundle_path),
                            "layout_name": str(layout_name),
                        }
                    )
        bundle_reports.append(
            {
                "bundle": str(bundle_path),
                "layout_name": str(layout_name),
                "layout_name_written": str(layout_name_written),
                "action": str(action),
                "skipped": False,
                "target_layout_guid": (int(target_layout_guid) if target_layout_guid is not None else None),
                "report": report,
            }
        )
        current_input = step_output.resolve()

    # 若全部跳过：仍需确保输出存在（保持“链式写回”的后续步骤可继续以 output 作为 current_input）
    if not Path(output_path).is_file():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copyfile(input_path, output_path)

    return {
        "project_archive": str(project_root),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "bundles_total": int(len(bundle_files)),
        "bundles_skipped_total": int(skipped_total),
        "layout_conflict_resolutions_total": int(len(resolution_by_layout_name)),
        "bundles": bundle_reports,
        "ui_key_to_guid_for_writeback": dict(merged_ui_key_to_guid_for_writeback),
        "ui_key_to_guid_for_writeback_total": int(len(merged_ui_key_to_guid_for_writeback)),
        "ui_key_to_guid_for_writeback_conflicts_total": int(len(merged_conflicts)),
        "ui_key_to_guid_for_writeback_conflicts": merged_conflicts[:50],
        "options": {
            "auto_sync_custom_variables": bool(auto_sync_custom_variables),
            "layout_conflict_resolutions_enabled": bool(bool(layout_conflict_resolutions)),
        },
    }


__all__ = ["import_ui_from_workbench_bundles_to_gil"]

