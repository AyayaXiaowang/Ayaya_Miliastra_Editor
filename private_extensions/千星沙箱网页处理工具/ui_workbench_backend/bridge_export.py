from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .bridge_base import _ExportGiaResult, _ExportGilResult
from .bridge_export_token_store import _UiWorkbenchBridgeExportTokenStoreMixin
from .bridge_export_utils import _UiWorkbenchBridgeExportUtilsMixin


class _UiWorkbenchBridgeExportMixin(
    _UiWorkbenchBridgeExportTokenStoreMixin,
    _UiWorkbenchBridgeExportUtilsMixin,
):
    # typing-only: these attributes are provided by the composed bridge (see `bridge_base.py` / `bridge.py`)
    _main_window: Any
    _workspace_root: Path
    _workbench_dir: Path
    _exported_gil_paths_by_token: dict[str, Path]
    _exported_gia_paths_by_token: dict[str, Path]

    def _resolve_default_beyond_local_export_dir(self) -> Path: ...

    def _validate_ui_variables_or_raise(self) -> None:
        main_window = self._main_window
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip() if current_package_id is not None else ""
        if not package_id_text or package_id_text in {"global_view", "unclassified_view"}:
            return
        ui_source_dir = (
            self._workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / package_id_text
            / "管理配置"
            / "UI源码"
        )
        from app.cli.ui_variable_validator import format_ui_issues_text, validate_ui_source_dir

        allowed_scopes = {"ps", "lv", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"}
        issues = validate_ui_source_dir(
            ui_source_dir,
            allowed_scopes=allowed_scopes,
            workspace_root=self._workspace_root,
            package_id=package_id_text,
        )
        if issues:
            raise RuntimeError(format_ui_issues_text(issues))

    # --------------------------------------------------------------------- export: bundle -> gil (ugc_file_tools)
    def export_gil_from_bundle_payload(
        self,
        *,
        layout_name: str,
        bundle_payload: dict,
        verify_with_dll_dump: bool = True,
        save_button_groups_as_custom_templates: bool = False,
        base_gil_upload_bytes: Optional[bytes] = None,
        base_gil_upload_file_name: Optional[str] = None,
        base_gil_path: Optional[str] = None,
        target_layout_guid: Optional[int] = None,
        base_layout_guid: Optional[int] = None,
        pc_canvas_size_override: Optional[tuple[float, float]] = None,
    ) -> _ExportGilResult:
        """
        将 Workbench 导出的 UILayout bundle JSON 直接写回为 `.gil`（落盘到 ugc_file_tools/out/）。
        """
        # 方案 S：自定义变量只在注册表统一定义；导出前必须确保 UI源码 占位符引用闭包成立。
        self._validate_ui_variables_or_raise()

        # Workbench UI JSON 文本框允许人工编辑/粘贴历史 JSON：
        # - 旧版本可能写入了“纯色 hex”（#FFFFFF/#00FF00...），而写回端只接受统一调色板 hex；
        # - 为避免在写回阶段抛 ValueError，这里做一次“颜色归一化”（把任意 hex 量化到 5 色调色板）。
        self._sanitize_bundle_payload_for_gil_writeback(bundle_payload)

        # 说明（重要）：
        # - “导入到项目存档”场景需要 templates（便于管理/复用）；
        # - “写回 .gil”场景不需要 templates/custom_groups：写回端只需要一个 widgets 列表并挂到 layout children 下即可。
        # 因此这里将 bundle 转为 inline widgets 形态（layout.widgets），并移除 templates/custom_groups，
        # 避免在该场景下产生“必须引用模板/写入模板库”的误解。
        bundle_payload = self._convert_ui_bundle_to_inline_widgets_bundle(bundle_payload)

        normalized_layout_name = str(layout_name or "").strip()
        if normalized_layout_name == "":
            layout_node = bundle_payload.get("layout") if isinstance(bundle_payload, dict) else None
            if isinstance(layout_node, dict):
                normalized_layout_name = str(layout_node.get("layout_name") or layout_node.get("name") or "").strip()
        if normalized_layout_name == "":
            normalized_layout_name = "HTML导出_界面布局"

        canvas_size_key = str(bundle_payload.get("canvas_size_key") or "").strip() if isinstance(bundle_payload, dict) else ""
        pc_canvas_size = pc_canvas_size_override or self._parse_canvas_size_key(canvas_size_key) or (1600.0, 900.0)
        mobile_canvas_size = (1280.0, 720.0)

        # 输出文件名：布局名 + 时间戳（避免覆盖）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._sanitize_windows_file_stem(normalized_layout_name)
        # 注意：不再添加 "web_ui_" 等前缀，保持文件名可读且与 HTML/布局名一一对应。
        output_file_name = f"{safe_name}_{timestamp}.gil"

        # 延迟导入 ugc_file_tools：避免私有扩展 import 阶段引入不必要依赖
        import tempfile

        from ugc_file_tools.ui_patchers import import_web_ui_control_group_template_to_gil_layout
        from ugc_file_tools.ui_schema_library.library import find_schema_ids_by_label

        # 工程化：UIKey -> GUID 注册表
        # - 若基底存档属于“当前项目存档目录”，则写入项目内的 registry（便于节点图/协作引用）
        # - 若基底存档为外部文件/上传文件（例如 QQ 缓存里的别人存档），则使用 out 下“按基底分组”的 registry：
        #   - 目的：避免项目 registry 的 GUID 复用策略误命中外部存档里已有 GUID，从而覆盖别人的控件或触发结构不匹配报错
        #   - 同时保证后续重复导出到同一个外部基底时，可稳定复用“我们写进去的那批 GUID”
        package_id_text = ""
        main_window = self._main_window
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        if current_package_id is not None:
            package_id_text = str(current_package_id or "").strip()

        with tempfile.TemporaryDirectory(prefix="ugc_web_ui_export_") as tmpdir:
            # 选择基底存档（默认内置样本）。支持：
            # - base_gil_upload_bytes：来自前端文件选择上传（优先）
            # - base_gil_path：相对 repo_root 或绝对路径（保留给 CLI/自动化）
            base_gil_path_obj: Path
            if base_gil_upload_bytes is not None:
                raw_name = str(base_gil_upload_file_name or "").strip() or "base.gil"
                safe_uploaded_name = self._sanitize_windows_file_stem(raw_name)
                if not safe_uploaded_name.lower().endswith(".gil"):
                    safe_uploaded_name = safe_uploaded_name + ".gil"
                base_gil_path_obj = (Path(tmpdir) / safe_uploaded_name).resolve()
                base_gil_path_obj.write_bytes(bytes(base_gil_upload_bytes))
            else:
                base_gil_text = str(base_gil_path or "").strip()
                if base_gil_text != "":
                    candidate = Path(base_gil_text)
                    repo_root = self._workbench_dir.parent.parent
                    resolved_base = (candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve())
                    if resolved_base.suffix.lower() != ".gil":
                        raise ValueError(f"base_gil_path 不是 .gil 文件：{resolved_base}")
                    if not resolved_base.is_file():
                        raise FileNotFoundError(str(resolved_base))
                    base_gil_path_obj = resolved_base
                else:
                    base_gil_path_obj = (
                        self._workbench_dir.parent
                        / "ugc_file_tools"
                        / "builtin_resources"
                        / "空的界面控件组"
                        / "进度条样式.gil"
                    ).resolve()
                    if not base_gil_path_obj.is_file():
                        raise FileNotFoundError(str(base_gil_path_obj))

            def _is_path_under(child: Path, parent: Path) -> bool:
                child_parts = [str(p).lower() for p in child.resolve().parts]
                parent_parts = [str(p).lower() for p in parent.resolve().parts]
                if len(child_parts) < len(parent_parts):
                    return False
                return child_parts[: len(parent_parts)] == parent_parts

            # 选择 registry 路径（见上方注释）
            registry_path: Optional[Path] = None
            base_gil_text = str(base_gil_path or "").strip()
            base_is_in_current_package = False
            if base_gil_text != "" and package_id_text and package_id_text not in {"global_view", "unclassified_view"}:
                package_root = (
                    self._workspace_root / "assets" / "资源库" / "项目存档" / package_id_text
                ).resolve()
                base_is_in_current_package = _is_path_under(base_gil_path_obj, package_root)

            if base_is_in_current_package:
                registry_path = (
                    self._workspace_root
                    / "assets"
                    / "资源库"
                    / "项目存档"
                    / package_id_text
                    / "管理配置"
                    / "UI控件GUID映射"
                    / "ui_guid_registry.json"
                ).resolve()
            else:
                # 外部/上传基底：按“基底文件名”分组 registry，避免每次输出产生一个新 registry 文件
                raw_base_name = ""
                if base_gil_text != "":
                    raw_base_name = Path(base_gil_text).name
                if raw_base_name.strip() == "":
                    raw_base_name = str(base_gil_upload_file_name or "").strip() or "uploaded_base.gil"
                safe_base_stem = self._sanitize_windows_file_stem(Path(raw_base_name).stem)
                registry_file_name = f"ui_guid_registry__{safe_base_stem}.json"
                registry_path = (self._workbench_dir.parent / "ugc_file_tools" / "out" / registry_file_name).resolve()

            tmp_path = Path(tmpdir) / "ui_bundle.json"
            tmp_path.write_text(json.dumps(bundle_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            need_textbox = False
            need_item_display = False
            need_progressbar = False
            for w in self._iter_ui_widgets_from_bundle(bundle_payload):
                t = str(w.get("widget_type") or "").strip()
                if t == "文本框":
                    need_textbox = True
                    continue
                if t == "道具展示":
                    need_item_display = True
                    continue
                if t == "进度条":
                    need_progressbar = True
                    continue

            textbox_template_gil_path: Optional[Path] = None
            item_display_template_gil_path: Optional[Path] = None
            progressbar_template_gil_path: Optional[Path] = None

            if need_textbox and not find_schema_ids_by_label("textbox"):
                candidate = (
                    self._workbench_dir.parent
                    / "ugc_file_tools"
                    / "builtin_resources"
                    / "空的界面控件组"
                    / "文本框样式.gil"
                ).resolve()
                if not candidate.is_file():
                    raise FileNotFoundError(str(candidate))
                textbox_template_gil_path = candidate

            if need_item_display and not find_schema_ids_by_label("item_display"):
                candidate = (
                    self._workbench_dir.parent
                    / "ugc_file_tools"
                    / "builtin_resources"
                    / "空的界面控件组"
                    / "道具展示.gil"
                ).resolve()
                if not candidate.is_file():
                    raise FileNotFoundError(str(candidate))
                item_display_template_gil_path = candidate

            if need_progressbar and not find_schema_ids_by_label("progressbar"):
                # schema library 尚未沉淀 ProgressBar 模板：使用内置样本 seed 一次（后续即可省略）
                candidate = (
                    self._workbench_dir.parent
                    / "ugc_file_tools"
                    / "builtin_resources"
                    / "空的界面控件组"
                    / "进度条样式.gil"
                ).resolve()
                if not candidate.is_file():
                    raise FileNotFoundError(str(candidate))
                progressbar_template_gil_path = candidate

            report = import_web_ui_control_group_template_to_gil_layout(
                input_gil_file_path=base_gil_path_obj,
                output_gil_file_path=Path(output_file_name),
                template_json_file_path=tmp_path,
                target_layout_guid=(int(target_layout_guid) if target_layout_guid is not None else None),
                new_layout_name=normalized_layout_name,
                base_layout_guid=(int(base_layout_guid) if base_layout_guid is not None else None),
                # 固有内容必须克隆（新建布局必须带“固有内容”），不再提供可选项
                empty_layout=False,
                clone_children=True,
                pc_canvas_size=pc_canvas_size,
                mobile_canvas_size=mobile_canvas_size,
                enable_progressbars=True,
                enable_textboxes=True,
                progressbar_template_gil_file_path=progressbar_template_gil_path,
                textbox_template_gil_file_path=textbox_template_gil_path,
                item_display_template_gil_file_path=item_display_template_gil_path,
                verify_with_dll_dump=bool(verify_with_dll_dump),
                ui_guid_registry_file_path=registry_path,
            )

        output_path_text = str(report.get("output_gil") or "")
        if output_path_text.strip() == "":
            raise RuntimeError("export_gil: report.output_gil 为空（内部错误）。")
        output_path = Path(output_path_text).resolve()
        if not output_path.is_file():
            raise FileNotFoundError(str(output_path))

        # 可选：把“组件组”同步沉淀到控件组库的自定义模板（template root）
        #
        # 约定：
        # - HTML 可在组件根元素上标注 `data-ui-save-template`（在 bundle 中透传为 widget.__ui_custom_template_name）。
        #   - 非空且不为 "1"/"true"：作为模板名（若基底已存在同名模板则复用）
        #   - "1"/"true"：表示需要沉淀，模板名由导出端按 group_key 生成默认名
        # - 仍保留旧的“按钮组自动沉淀”开关（save_button_groups_as_custom_templates=true）：
        #   当勾选时，会额外把“识别到的按钮组件组（可交互道具展示锚点）”批量沉淀为模板。
        component_groups = report.get("component_groups") if isinstance(report, dict) else None
        groups = component_groups.get("groups") if isinstance(component_groups, dict) else None
        widgets = self._iter_ui_widgets_from_bundle(bundle_payload)

        selected_group_guids: list[int] = []
        selected_template_names: list[str] = []
        selected_group_guid_set: set[int] = set()
        selected_template_name_set: set[str] = set()

        def _select_group(group_guid: int, template_name: str) -> None:
            gg = int(group_guid)
            tn = str(template_name or "").strip()
            if gg <= 0 or tn == "":
                return
            if gg in selected_group_guid_set:
                return
            # 同名模板复用：同一次导出里若多个 group 都指向同名模板，仅需沉淀一次（后续由写回端复用/跳过）。
            if tn in selected_template_name_set:
                return
            selected_group_guid_set.add(int(gg))
            selected_template_name_set.add(str(tn))
            selected_group_guids.append(int(gg))
            selected_template_names.append(str(tn))

        def _is_truthy_template_mark(text: str) -> bool:
            t = str(text or "").strip().lower()
            return t in {"1", "true", "yes", "y", "on"}

        def _derive_default_template_name_from_group_key(group_key: str) -> str:
            # 默认命名：<布局名>_模板_<简名>
            # group_key 形如：HTML导入_界面布局__btn_exit / ceshi_html__level_unselected__level_01 ...
            parts = [p for p in str(group_key or "").split("__") if p != ""]
            short = parts[-1] if parts else "组件"
            return f"{normalized_layout_name}_模板_{short}"

        def _is_interactive_item_display_widget(w: dict) -> bool:
            if str(w.get("widget_type") or "").strip() != "道具展示":
                return False
            settings = w.get("settings")
            if isinstance(settings, dict) and isinstance(settings.get("can_interact"), bool):
                return bool(settings.get("can_interact"))
            return False

        def _pick_button_label_from_widget(w: dict) -> str:
            name = str(w.get("widget_name") or "").strip()
            if name.startswith("按钮_道具展示_"):
                return name[len("按钮_道具展示_") :].strip() or name
            if name.startswith("按钮_"):
                return name[len("按钮_") :].strip() or name
            return name or str(w.get("widget_id") or "").strip() or "按钮"

        if isinstance(groups, list) and groups:
            # 1) 显式标记：data-ui-save-template
            for g in groups:
                if not isinstance(g, dict):
                    continue
                group_guid = g.get("group_guid")
                if not isinstance(group_guid, int) or int(group_guid) <= 0:
                    continue
                group_key = str(g.get("group_key") or "").strip()
                children = g.get("children")
                if not isinstance(children, list) or not children:
                    continue

                mark_value: str = ""
                for ch in children:
                    if not isinstance(ch, dict):
                        continue
                    widget_index = ch.get("widget_index")
                    if not isinstance(widget_index, int):
                        continue
                    if widget_index < 0 or widget_index >= len(widgets):
                        continue
                    w = widgets[int(widget_index)]
                    if not isinstance(w, dict):
                        continue
                    raw_mark = str(w.get("__ui_custom_template_name") or "").strip()
                    if raw_mark:
                        mark_value = raw_mark
                        break

                if not mark_value:
                    continue

                if _is_truthy_template_mark(mark_value):
                    _select_group(int(group_guid), _derive_default_template_name_from_group_key(group_key))
                else:
                    _select_group(int(group_guid), str(mark_value))

            # 2) 旧逻辑（可选）：按钮组自动沉淀
            if bool(save_button_groups_as_custom_templates):
                for g in groups:
                    if not isinstance(g, dict):
                        continue
                    group_guid = g.get("group_guid")
                    if not isinstance(group_guid, int) or int(group_guid) <= 0:
                        continue
                    children = g.get("children")
                    if not isinstance(children, list) or not children:
                        continue

                    anchor_widget: dict | None = None
                    for ch in children:
                        if not isinstance(ch, dict):
                            continue
                        widget_index = ch.get("widget_index")
                        if not isinstance(widget_index, int):
                            continue
                        if widget_index < 0 or widget_index >= len(widgets):
                            continue
                        w = widgets[int(widget_index)]
                        if not isinstance(w, dict):
                            continue
                        if _is_interactive_item_display_widget(w):
                            anchor_widget = w
                            break
                    if anchor_widget is None:
                        continue

                    label = _pick_button_label_from_widget(anchor_widget)
                    auto_name = f"{normalized_layout_name}_按钮_{label}".strip() or f"{normalized_layout_name}_按钮"
                    _select_group(int(group_guid), auto_name)

        if selected_group_guids:
            from ugc_file_tools.ui_patchers import save_component_groups_as_custom_templates

            templates_report = save_component_groups_as_custom_templates(
                input_gil_file_path=Path(output_path),
                output_gil_file_path=Path(output_path),
                component_group_guids=list(selected_group_guids),
                template_names=list(selected_template_names),
                verify_with_dll_dump=bool(verify_with_dll_dump),
            )
            report["custom_templates"] = templates_report
        else:
            report["custom_templates"] = {
                "created_total": 0,
                "created": [],
                "skipped": True,
                "reason": "未选择任何需要沉淀为模板的组件组（未标注 data-ui-save-template，且未启用按钮组自动沉淀）。",
            }

        # 工程化：记录本次导出（供后续节点图 .gia 导出选择“回填记录”）
        if package_id_text and package_id_text not in {"global_view", "unclassified_view"} and registry_path is not None:
            from ugc_file_tools.ui.export_records import append_ui_export_record

            base_hint = ""
            if base_gil_upload_bytes is not None:
                base_hint = str(base_gil_upload_file_name or "").strip()
            elif str(base_gil_path or "").strip() != "":
                base_hint = str(Path(base_gil_path_obj).name)

            base_path_for_record = None
            if base_gil_upload_bytes is None and str(base_gil_path or "").strip() != "" and Path(base_gil_path_obj).is_file():
                base_path_for_record = Path(base_gil_path_obj).resolve()

            record = append_ui_export_record(
                workspace_root=Path(self._workspace_root),
                package_id=str(package_id_text),
                title=str(normalized_layout_name),
                kind="export_gil",
                output_gil_file=Path(output_path),
                ui_guid_registry_path=Path(registry_path),
                base_gil_path=base_path_for_record,
                base_gil_file_name_hint=str(base_hint),
                extra={
                    "layout_name": str(normalized_layout_name),
                    "target_layout_guid": report.get("layout", {}).get("target_layout_guid") if isinstance(report.get("layout"), dict) else None,
                    "layout_index": report.get("layout", {}).get("layout_index") if isinstance(report.get("layout"), dict) else None,
                },
            )
            report["ui_export_record"] = record

        token = uuid4().hex[:8]
        self._exported_gil_paths_by_token[token] = output_path
        return _ExportGilResult(
            output_gil_path=str(output_path),
            output_file_name=output_file_name,
            report=report,
            download_token=token,
        )

    # --------------------------------------------------------------------- export: multiple bundles -> one gil
    def export_gil_from_bundle_payloads(
        self,
        *,
        bundles: list[dict],
        verify_with_dll_dump: bool = True,
        save_button_groups_as_custom_templates: bool = False,
        base_gil_upload_bytes: Optional[bytes] = None,
        base_gil_upload_file_name: Optional[str] = None,
        base_gil_path: Optional[str] = None,
    ) -> _ExportGilResult:
        """
        批量写回：把多个 Workbench 导出的 UILayout bundle JSON 依次写入同一份 `.gil`。

        约定：
        - 每个 bundle 对应一个“新布局”（target_layout_guid 仍可在 bundle 内指定，但批量导出主要面向“新建多个布局”）。
        - 输出仍落到 `ugc_file_tools/out/`，文件名为 “UI批量导出_<N>页_<timestamp>.gil”。
        """
        self._validate_ui_variables_or_raise()

        if not isinstance(bundles, list) or len(bundles) <= 0:
            raise ValueError("bundles 不能为空")

        # 预处理：清洗 + 转为 inline widgets（写回 `.gil` 场景不需要 templates/custom_groups）
        normalized_items: list[dict[str, Any]] = []
        for item in bundles:
            if not isinstance(item, dict):
                continue
            layout_name = str(item.get("layout_name") or "").strip()
            bundle_payload = item.get("bundle")
            if not isinstance(bundle_payload, dict):
                continue

            pc_canvas_size_override: Optional[tuple[float, float]] = None
            pc_node = item.get("pc_canvas_size")
            if isinstance(pc_node, dict):
                x = pc_node.get("x")
                y = pc_node.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    fx = float(x)
                    fy = float(y)
                    if fx > 0 and fy > 0:
                        pc_canvas_size_override = (fx, fy)

            self._sanitize_bundle_payload_for_gil_writeback(bundle_payload)
            inline_bundle = self._convert_ui_bundle_to_inline_widgets_bundle(bundle_payload)

            normalized_layout_name = layout_name
            if normalized_layout_name == "":
                layout_node = inline_bundle.get("layout") if isinstance(inline_bundle, dict) else None
                if isinstance(layout_node, dict):
                    normalized_layout_name = str(layout_node.get("layout_name") or layout_node.get("name") or "").strip()
            if normalized_layout_name == "":
                normalized_layout_name = "HTML导出_界面布局"

            normalized_items.append(
                {
                    "layout_name": str(normalized_layout_name),
                    "bundle": inline_bundle,
                    "pc_canvas_size_override": pc_canvas_size_override,
                }
            )

        if len(normalized_items) <= 0:
            raise ValueError("bundles 中没有可用的 bundle（需要至少一个 dict bundle）")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._sanitize_windows_file_stem(f"UI批量导出_{len(normalized_items)}页")
        output_file_name = f"{safe_name}_{timestamp}.gil"

        import tempfile

        from ugc_file_tools.ui_patchers import import_web_ui_control_group_template_to_gil_layout
        from ugc_file_tools.ui_schema_library.library import find_schema_ids_by_label

        # 统计：确定是否需要 seed schema library
        need_textbox = False
        need_item_display = False
        need_progressbar = False
        for it in normalized_items:
            for w in self._iter_ui_widgets_from_bundle(it["bundle"]):
                t = str(w.get("widget_type") or "").strip()
                if t == "文本框":
                    need_textbox = True
                    continue
                if t == "道具展示":
                    need_item_display = True
                    continue
                if t == "进度条":
                    need_progressbar = True
                    continue

        textbox_template_gil_path: Optional[Path] = None
        item_display_template_gil_path: Optional[Path] = None
        progressbar_template_gil_path: Optional[Path] = None

        if need_textbox and not find_schema_ids_by_label("textbox"):
            candidate = (
                self._workbench_dir.parent
                / "ugc_file_tools"
                / "builtin_resources"
                / "空的界面控件组"
                / "文本框样式.gil"
            ).resolve()
            if not candidate.is_file():
                raise FileNotFoundError(str(candidate))
            textbox_template_gil_path = candidate

        if need_item_display and not find_schema_ids_by_label("item_display"):
            candidate = (
                self._workbench_dir.parent
                / "ugc_file_tools"
                / "builtin_resources"
                / "空的界面控件组"
                / "道具展示.gil"
            ).resolve()
            if not candidate.is_file():
                raise FileNotFoundError(str(candidate))
            item_display_template_gil_path = candidate

        if need_progressbar and not find_schema_ids_by_label("progressbar"):
            candidate = (
                self._workbench_dir.parent
                / "ugc_file_tools"
                / "builtin_resources"
                / "空的界面控件组"
                / "进度条样式.gil"
            ).resolve()
            if not candidate.is_file():
                raise FileNotFoundError(str(candidate))
            progressbar_template_gil_path = candidate

        # registry 路径选择规则沿用单 bundle 逻辑
        package_id_text = ""
        main_window = self._main_window
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        if current_package_id is not None:
            package_id_text = str(current_package_id or "").strip()

        with tempfile.TemporaryDirectory(prefix="ugc_web_ui_export_multi_") as tmpdir:
            base_gil_path_obj: Path
            if base_gil_upload_bytes is not None:
                raw_name = str(base_gil_upload_file_name or "").strip() or "base.gil"
                safe_uploaded_name = self._sanitize_windows_file_stem(raw_name)
                if not safe_uploaded_name.lower().endswith(".gil"):
                    safe_uploaded_name = safe_uploaded_name + ".gil"
                base_gil_path_obj = (Path(tmpdir) / safe_uploaded_name).resolve()
                base_gil_path_obj.write_bytes(bytes(base_gil_upload_bytes))
            else:
                base_gil_text = str(base_gil_path or "").strip()
                if base_gil_text != "":
                    candidate = Path(base_gil_text)
                    repo_root = self._workbench_dir.parent.parent
                    resolved_base = (candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve())
                    if resolved_base.suffix.lower() != ".gil":
                        raise ValueError(f"base_gil_path 不是 .gil 文件：{resolved_base}")
                    if not resolved_base.is_file():
                        raise FileNotFoundError(str(resolved_base))
                    base_gil_path_obj = resolved_base
                else:
                    base_gil_path_obj = (
                        self._workbench_dir.parent
                        / "ugc_file_tools"
                        / "builtin_resources"
                        / "空的界面控件组"
                        / "进度条样式.gil"
                    ).resolve()
                    if not base_gil_path_obj.is_file():
                        raise FileNotFoundError(str(base_gil_path_obj))

            def _is_path_under(child: Path, parent: Path) -> bool:
                child_parts = [str(p).lower() for p in child.resolve().parts]
                parent_parts = [str(p).lower() for p in parent.resolve().parts]
                if len(child_parts) < len(parent_parts):
                    return False
                return child_parts[: len(parent_parts)] == parent_parts

            registry_path: Optional[Path] = None
            base_gil_text2 = str(base_gil_path or "").strip()
            base_is_in_current_package = False
            if base_gil_text2 != "" and package_id_text and package_id_text not in {"global_view", "unclassified_view"}:
                package_root = (self._workspace_root / "assets" / "资源库" / "项目存档" / package_id_text).resolve()
                base_is_in_current_package = _is_path_under(base_gil_path_obj, package_root)

            if base_is_in_current_package:
                registry_path = (
                    self._workspace_root
                    / "assets"
                    / "资源库"
                    / "项目存档"
                    / package_id_text
                    / "管理配置"
                    / "UI控件GUID映射"
                    / "ui_guid_registry.json"
                ).resolve()
            else:
                raw_base_name = ""
                if base_gil_text2 != "":
                    raw_base_name = Path(base_gil_text2).name
                if raw_base_name.strip() == "":
                    raw_base_name = str(base_gil_upload_file_name or "").strip() or "uploaded_base.gil"
                safe_base_stem = self._sanitize_windows_file_stem(Path(raw_base_name).stem)
                registry_file_name = f"ui_guid_registry__{safe_base_stem}.json"
                registry_path = (self._workbench_dir.parent / "ugc_file_tools" / "out" / registry_file_name).resolve()

            # 关键修复（批量导出）：
            # - 写回端在 base_layout_guid=None 时会基于“当前 input_gil”的 UI records 推断 base_layout_guid；
            # - 批量导出是“上一轮输出作为下一轮输入”的递推过程，因此推断结果会随着新建布局而漂移：
            #   第二页开始可能会错误地把“上一页新建布局”当作 base，从而克隆上一页 children，表现为页面串页/混乱。
            # - 正确语义：整次批量导出应固定使用“最初基底存档”推断出的 base_layout_guid 作为克隆来源。
            pinned_base_layout_guid: Optional[int] = None
            force_empty_layout_for_all = False
            force_clone_children_for_all = True

            from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
                dump_gil_to_raw_json_object,
                infer_base_layout_guid,
            )

            dump_object = dump_gil_to_raw_json_object(base_gil_path_obj)
            node9 = dump_object.get("4", {}).get("9")
            if isinstance(node9, dict):
                ui_record_list = node9.get("502")
                if isinstance(ui_record_list, dict):
                    ui_record_list = [ui_record_list]
                if isinstance(ui_record_list, list) and ui_record_list:
                    pinned_base_layout_guid = int(infer_base_layout_guid(ui_record_list))
                else:
                    # 极端：存在 4/9 但没有 record list，视为“无法克隆固有内容”，批量导出改为创建空布局。
                    force_empty_layout_for_all = True
                    force_clone_children_for_all = False
            else:
                # 基底缺失 UI 段（4/9）或结构异常：prepare 会 bootstrap，但后续页也必须保持空布局语义。
                force_empty_layout_for_all = True
                force_clone_children_for_all = False

            current_input = base_gil_path_obj
            output_path: Optional[Path] = None
            bundle_reports: list[dict[str, Any]] = []

            # 组件组模板沉淀：跨 bundle 汇总后一次性写回（减少重复操作）
            selected_group_guids: list[int] = []
            selected_template_names: list[str] = []
            selected_group_guid_set: set[int] = set()
            selected_template_name_set: set[str] = set()

            def _select_group(group_guid: int, template_name: str) -> None:
                gg = int(group_guid)
                tn = str(template_name or "").strip()
                if gg <= 0 or tn == "":
                    return
                if gg in selected_group_guid_set:
                    return
                if tn in selected_template_name_set:
                    return
                selected_group_guid_set.add(int(gg))
                selected_template_name_set.add(str(tn))
                selected_group_guids.append(int(gg))
                selected_template_names.append(str(tn))

            def _is_truthy_template_mark(text: str) -> bool:
                t = str(text or "").strip().lower()
                return t in {"1", "true", "yes", "y", "on"}

            def _derive_default_template_name_from_group_key(layout_name2: str, group_key: str) -> str:
                parts = [p for p in str(group_key or "").split("__") if p != ""]
                short = parts[-1] if parts else "组件"
                return f"{layout_name2}_模板_{short}"

            def _is_interactive_item_display_widget(w: dict) -> bool:
                if str(w.get("widget_type") or "").strip() != "道具展示":
                    return False
                settings = w.get("settings")
                if isinstance(settings, dict) and isinstance(settings.get("can_interact"), bool):
                    return bool(settings.get("can_interact"))
                return False

            def _pick_button_label_from_widget(w: dict) -> str:
                name = str(w.get("widget_name") or "").strip()
                if name.startswith("按钮_道具展示_"):
                    return name[len("按钮_道具展示_") :].strip() or name
                if name.startswith("按钮_"):
                    return name[len("按钮_") :].strip() or name
                return name or str(w.get("widget_id") or "").strip() or "按钮"

            for idx, it2 in enumerate(normalized_items):
                layout_name2 = str(it2.get("layout_name") or "").strip() or "HTML导出_界面布局"
                bundle_payload2 = it2.get("bundle")
                if not isinstance(bundle_payload2, dict):
                    continue

                canvas_size_key = str(bundle_payload2.get("canvas_size_key") or "").strip()
                pc_canvas_size = (
                    it2.get("pc_canvas_size_override")
                    or self._parse_canvas_size_key(canvas_size_key)
                    or (1600.0, 900.0)
                )
                mobile_canvas_size = (1280.0, 720.0)

                tmp_path = Path(tmpdir) / f"ui_bundle_{idx}.json"
                tmp_path.write_text(json.dumps(bundle_payload2, ensure_ascii=False, indent=2), encoding="utf-8")

                report = import_web_ui_control_group_template_to_gil_layout(
                    input_gil_file_path=Path(current_input),
                    output_gil_file_path=(Path(output_file_name) if output_path is None else Path(output_path)),
                    template_json_file_path=tmp_path,
                    target_layout_guid=None,
                    new_layout_name=layout_name2,
                    base_layout_guid=(int(pinned_base_layout_guid) if pinned_base_layout_guid is not None else None),
                    empty_layout=bool(force_empty_layout_for_all),
                    clone_children=bool(force_clone_children_for_all),
                    pc_canvas_size=pc_canvas_size,
                    mobile_canvas_size=mobile_canvas_size,
                    enable_progressbars=True,
                    enable_textboxes=True,
                    progressbar_template_gil_file_path=progressbar_template_gil_path,
                    textbox_template_gil_file_path=textbox_template_gil_path,
                    item_display_template_gil_file_path=item_display_template_gil_path,
                    verify_with_dll_dump=bool(verify_with_dll_dump),
                    ui_guid_registry_file_path=registry_path,
                )

                output_path_text = str(report.get("output_gil") or "")
                if output_path_text.strip() == "":
                    raise RuntimeError("export_gil(bundles): report.output_gil 为空（内部错误）。")
                output_path = Path(output_path_text).resolve()
                if not output_path.is_file():
                    raise FileNotFoundError(str(output_path))

                current_input = output_path
                bundle_reports.append(
                    {
                        "layout_name": layout_name2,
                        "output_gil": str(output_path),
                        "report": report,
                    }
                )

                # 组件组模板沉淀：收集选中项（不立即写回）
                component_groups = report.get("component_groups") if isinstance(report, dict) else None
                groups = component_groups.get("groups") if isinstance(component_groups, dict) else None
                widgets = self._iter_ui_widgets_from_bundle(bundle_payload2)
                if isinstance(groups, list) and groups:
                    for g in groups:
                        if not isinstance(g, dict):
                            continue
                        group_guid = g.get("group_guid")
                        if not isinstance(group_guid, int) or int(group_guid) <= 0:
                            continue
                        group_key = str(g.get("group_key") or "").strip()
                        children = g.get("children")
                        if not isinstance(children, list) or not children:
                            continue

                        mark_value: str = ""
                        for ch in children:
                            if not isinstance(ch, dict):
                                continue
                            widget_index = ch.get("widget_index")
                            if not isinstance(widget_index, int):
                                continue
                            if widget_index < 0 or widget_index >= len(widgets):
                                continue
                            w = widgets[int(widget_index)]
                            if not isinstance(w, dict):
                                continue
                            raw_mark = str(w.get("__ui_custom_template_name") or "").strip()
                            if raw_mark:
                                mark_value = raw_mark
                                break
                        if mark_value:
                            if _is_truthy_template_mark(mark_value):
                                _select_group(int(group_guid), _derive_default_template_name_from_group_key(layout_name2, group_key))
                            else:
                                _select_group(int(group_guid), str(mark_value))

                    if bool(save_button_groups_as_custom_templates):
                        for g2 in groups:
                            if not isinstance(g2, dict):
                                continue
                            group_guid2 = g2.get("group_guid")
                            if not isinstance(group_guid2, int) or int(group_guid2) <= 0:
                                continue
                            children2 = g2.get("children")
                            if not isinstance(children2, list) or not children2:
                                continue
                            anchor_widget: dict | None = None
                            for ch2 in children2:
                                if not isinstance(ch2, dict):
                                    continue
                                widget_index2 = ch2.get("widget_index")
                                if not isinstance(widget_index2, int):
                                    continue
                                if widget_index2 < 0 or widget_index2 >= len(widgets):
                                    continue
                                w2 = widgets[int(widget_index2)]
                                if not isinstance(w2, dict):
                                    continue
                                if _is_interactive_item_display_widget(w2):
                                    anchor_widget = w2
                                    break
                            if anchor_widget is None:
                                continue
                            label2 = _pick_button_label_from_widget(anchor_widget)
                            auto_name2 = f"{layout_name2}_按钮_{label2}".strip() or f"{layout_name2}_按钮"
                            _select_group(int(group_guid2), auto_name2)

            if output_path is None:
                raise RuntimeError("export_gil(bundles): output_path 为空（内部错误）。")

            merged_report: dict[str, Any] = {
                "exported_bundles_total": len(bundle_reports),
                "skipped_bundles_total": max(0, len(normalized_items) - len(bundle_reports)),
                "bundle_reports": bundle_reports,
            }
            # 便于前端展示：总 referenced_variables_total
            referenced_total = 0
            for br in bundle_reports:
                rep = br.get("report")
                if isinstance(rep, dict):
                    v = rep.get("referenced_variables_total")
                    if isinstance(v, int):
                        referenced_total += int(v)
            merged_report["referenced_variables_total"] = referenced_total

            if selected_group_guids:
                from ugc_file_tools.ui_patchers import save_component_groups_as_custom_templates

                templates_report = save_component_groups_as_custom_templates(
                    input_gil_file_path=Path(output_path),
                    output_gil_file_path=Path(output_path),
                    component_group_guids=list(selected_group_guids),
                    template_names=list(selected_template_names),
                    verify_with_dll_dump=bool(verify_with_dll_dump),
                )
                merged_report["custom_templates"] = templates_report
            else:
                merged_report["custom_templates"] = {
                    "created_total": 0,
                    "created": [],
                    "skipped": True,
                    "reason": "未选择任何需要沉淀为模板的组件组（未标注 data-ui-save-template，且未启用按钮组自动沉淀）。",
                }

            # 工程化：记录本次批量导出（供后续节点图 .gia 导出选择“回填记录”）
            if package_id_text and package_id_text not in {"global_view", "unclassified_view"} and registry_path is not None:
                from ugc_file_tools.ui.export_records import append_ui_export_record

                base_hint = ""
                if base_gil_upload_bytes is not None:
                    base_hint = str(base_gil_upload_file_name or "").strip()
                elif str(base_gil_path or "").strip() != "":
                    base_hint = str(Path(base_gil_path_obj).name)

                base_path_for_record = None
                if base_gil_upload_bytes is None and str(base_gil_path or "").strip() != "" and Path(base_gil_path_obj).is_file():
                    base_path_for_record = Path(base_gil_path_obj).resolve()

                record = append_ui_export_record(
                    workspace_root=Path(self._workspace_root),
                    package_id=str(package_id_text),
                    title=f"UI批量导出_{int(len(bundle_reports))}页",
                    kind="export_gil_bundles",
                    output_gil_file=Path(output_path),
                    ui_guid_registry_path=Path(registry_path),
                    base_gil_path=base_path_for_record,
                    base_gil_file_name_hint=str(base_hint),
                    extra={
                        "exported_bundles_total": int(len(bundle_reports)),
                        "layout_names": [str(br.get("layout_name") or "") for br in list(bundle_reports) if isinstance(br, dict)],
                    },
                )
                merged_report["ui_export_record"] = record

        token = uuid4().hex[:8]
        self._exported_gil_paths_by_token[token] = Path(output_path).resolve()
        return _ExportGilResult(
            output_gil_path=str(Path(output_path).resolve()),
            output_file_name=output_file_name,
            report=merged_report,
            download_token=token,
        )

    # --------------------------------------------------------------------- export: bundle -> gil (custom variables only)
    def export_gil_custom_variables_only_from_bundle_payload(
        self,
        *,
        layout_name: str,
        bundle_payload: dict,
        base_gil_upload_bytes: Optional[bytes] = None,
        base_gil_upload_file_name: Optional[str] = None,
        base_gil_path: Optional[str] = None,
    ) -> _ExportGilResult:
        """
        仅写回“实体自定义变量”（关卡/玩家自身）到 `.gil`：
        - 从 Workbench bundle JSON 中提取进度条/道具展示的变量绑定引用
        - 将变量定义补齐到 base `.gil` 的 root4/5/1（关卡实体/玩家实体/默认模版(角色编辑)）

        注意：该入口**不会**写回 UI 控件/布局记录。
        """
        # 同 `export_gil`：导出前必须确保 UI源码 占位符引用闭包成立（方案 S：注册表单文件真源）。
        self._validate_ui_variables_or_raise()

        normalized_layout_name = str(layout_name or "").strip()
        if normalized_layout_name == "":
            layout_node = bundle_payload.get("layout") if isinstance(bundle_payload, dict) else None
            if isinstance(layout_node, dict):
                normalized_layout_name = str(layout_node.get("layout_name") or layout_node.get("name") or "").strip()
        if normalized_layout_name == "":
            normalized_layout_name = "HTML导出_界面布局"

        # 输出文件名：布局名 + 时间戳（避免覆盖）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._sanitize_windows_file_stem(normalized_layout_name)
        output_file_name = f"{safe_name}_vars_{timestamp}.gil"

        if base_gil_upload_bytes is None and str(base_gil_path or "").strip() == "":
            raise ValueError("custom_variables_only 模式必须先选择一个基底存档 (.gil)。")

        import tempfile

        from ugc_file_tools.ui_patchers import patch_web_ui_referenced_custom_variables_in_gil

        with tempfile.TemporaryDirectory(prefix="ugc_web_ui_export_vars_") as tmpdir:
            # 选择基底存档（必须显式提供）
            base_gil_path_obj: Path
            if base_gil_upload_bytes is not None:
                raw_name = str(base_gil_upload_file_name or "").strip() or "base.gil"
                safe_uploaded_name = self._sanitize_windows_file_stem(raw_name)
                if not safe_uploaded_name.lower().endswith(".gil"):
                    safe_uploaded_name = safe_uploaded_name + ".gil"
                base_gil_path_obj = (Path(tmpdir) / safe_uploaded_name).resolve()
                base_gil_path_obj.write_bytes(bytes(base_gil_upload_bytes))
            else:
                base_gil_text = str(base_gil_path or "").strip()
                candidate = Path(base_gil_text)
                repo_root = self._workbench_dir.parent.parent
                resolved_base = (candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve())
                if resolved_base.suffix.lower() != ".gil":
                    raise ValueError(f"base_gil_path 不是 .gil 文件：{resolved_base}")
                if not resolved_base.is_file():
                    raise FileNotFoundError(str(resolved_base))
                base_gil_path_obj = resolved_base

            tmp_path = Path(tmpdir) / "ui_bundle.json"
            tmp_path.write_text(json.dumps(bundle_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            report = patch_web_ui_referenced_custom_variables_in_gil(
                input_gil_file_path=base_gil_path_obj,
                output_gil_file_path=Path(output_file_name),
                template_json_file_path=tmp_path,
                enable_progressbars=True,
                enable_item_displays=True,
            )

        output_path_text = str(report.get("output_gil") or "")
        if output_path_text.strip() == "":
            raise RuntimeError("export_gil_custom_variables_only: report.output_gil 为空（内部错误）。")
        output_path = Path(output_path_text).resolve()
        if not output_path.is_file():
            raise FileNotFoundError(str(output_path))

        token = uuid4().hex[:8]
        self._exported_gil_paths_by_token[token] = output_path
        return _ExportGilResult(
            output_gil_path=str(output_path),
            output_file_name=output_file_name,
            report=report,
            download_token=token,
        )

    # --------------------------------------------------------------------- export: bundle -> layout asset gia (via gil)
    def export_gia_from_bundle_payload(
        self,
        *,
        layout_name: str,
        bundle_payload: dict,
        verify_with_dll_dump: bool = True,
        base_gil_upload_bytes: Optional[bytes] = None,
        base_gil_upload_file_name: Optional[str] = None,
        base_gil_path: Optional[str] = None,
        target_layout_guid: Optional[int] = None,
        base_layout_guid: Optional[int] = None,
        pc_canvas_size_override: Optional[tuple[float, float]] = None,
        game_version: str = "6.3.0",
    ) -> _ExportGiaResult:
        """
        Workbench bundle JSON → `.gil`（复用 export_gil）→ “布局资产 `.gia`”。

        说明：
        - 布局资产 `.gia` 的 payload 直接承载 `.gil` 的 UI records（lossless 数值键 dict），
          因此这里必须先生成 `.gil` 再打包为 `.gia`。
        """
        gil_result = self.export_gil_from_bundle_payload(
            layout_name=layout_name,
            bundle_payload=bundle_payload,
            verify_with_dll_dump=verify_with_dll_dump,
            base_gil_upload_bytes=base_gil_upload_bytes,
            base_gil_upload_file_name=base_gil_upload_file_name,
            base_gil_path=base_gil_path,
            target_layout_guid=target_layout_guid,
            base_layout_guid=base_layout_guid,
            pc_canvas_size_override=pc_canvas_size_override,
        )

        report = gil_result.report if isinstance(gil_result.report, dict) else {}
        layout_node = report.get("layout") if isinstance(report, dict) else None
        layout_root_guid: Optional[int] = None
        if isinstance(layout_node, dict):
            v = layout_node.get("target_layout_guid")
            if isinstance(v, int) and int(v) > 0:
                layout_root_guid = int(v)
            elif isinstance(v, str) and v.strip().isdigit():
                parsed = int(v.strip())
                if parsed > 0:
                    layout_root_guid = parsed
            if layout_root_guid is None:
                created = layout_node.get("created_layout")
                if isinstance(created, dict):
                    gv = created.get("guid")
                    if isinstance(gv, int) and int(gv) > 0:
                        layout_root_guid = int(gv)
                    elif isinstance(gv, str) and gv.strip().isdigit():
                        parsed2 = int(gv.strip())
                        if parsed2 > 0:
                            layout_root_guid = parsed2
        if layout_root_guid is None:
            raise RuntimeError("export_gia: 无法从 report.layout 解析 layout_root_guid（内部错误）。")

        output_gia_file_name = str(Path(gil_result.output_file_name).with_suffix(".gia").name)

        # 关键：布局资产 GIA 的层级关系不完全来自 `.gil` 的 record children 字段。
        # Web 写回端的“组件打组”会创建 group_container，但 group_container 的 children 关系需要
        # 通过 report.component_groups 显式补齐，否则导出会缺少若干条目（游戏侧可能直接拒绝解析）。
        extra_children_by_guid: dict[int, list[int]] = {}
        cg = report.get("component_groups") if isinstance(report, dict) else None
        groups = cg.get("groups") if isinstance(cg, dict) else None
        if isinstance(groups, list):
            for g in groups:
                if not isinstance(g, dict):
                    continue
                group_guid = g.get("group_guid")
                if not isinstance(group_guid, int) or int(group_guid) <= 0:
                    continue
                children_node = g.get("children")
                if not isinstance(children_node, list) or not children_node:
                    continue
                child_guids: list[int] = []
                for ch in children_node:
                    if not isinstance(ch, dict):
                        continue
                    guid_value = ch.get("guid")
                    if isinstance(guid_value, int) and int(guid_value) > 0:
                        child_guids.append(int(guid_value))
                if len(child_guids) >= 2:
                    extra_children_by_guid[int(group_guid)] = list(child_guids)

        from ugc_file_tools.ui_patchers.layout.layout_asset_gia import (
            create_layout_asset_gia_from_gil_by_patching_base_gia,
        )

        base_gia = (
            self._workbench_dir.parent
            / "ugc_file_tools"
            / "builtin_resources"
            / "gia_templates"
            / "layout_asset_template.gia"
        ).resolve()
        if not base_gia.is_file():
            raise FileNotFoundError(str(base_gia))

        gia_report = create_layout_asset_gia_from_gil_by_patching_base_gia(
            input_gil_file_path=Path(gil_result.output_gil_path),
            layout_root_guid=int(layout_root_guid),
            base_gia_file_path=base_gia,
            output_gia_path=Path(output_gia_file_name),
            output_file_name=output_gia_file_name,
            game_version=str(game_version or "6.3.0"),
            sort_entries_by_guid=True,
            sort_children_by_guid=False,
            extra_entry_children_by_guid=extra_children_by_guid,
        )

        output_gia_path_text = str(gia_report.get("output_gia_file") or "").strip()
        if output_gia_path_text == "":
            raise RuntimeError("export_gia: gia_report.output_gia_file 为空（内部错误）。")
        output_gia_path = Path(output_gia_path_text).resolve()
        if not output_gia_path.is_file():
            raise FileNotFoundError(str(output_gia_path))

        token = uuid4().hex[:8]
        # 生成后自动复制到 Beyond 导出目录（用户期望目录）
        beyond_dir = self._resolve_default_beyond_local_export_dir()
        beyond_dir.mkdir(parents=True, exist_ok=True)
        copied_output_gia_path = (beyond_dir / output_gia_path.name).resolve()
        shutil.copy2(output_gia_path, copied_output_gia_path)

        self._exported_gia_paths_by_token[token] = copied_output_gia_path
        return _ExportGiaResult(
            output_gia_path=str(copied_output_gia_path),
            output_file_name=output_gia_file_name,
            report={
                "gil_report": report,
                "gia_report": gia_report,
                "original_output_gia_file": str(output_gia_path),
                "copied_output_gia_file": str(copied_output_gia_path),
            },
            download_token=token,
            output_gil_path=str(Path(gil_result.output_gil_path).resolve()),
        )

