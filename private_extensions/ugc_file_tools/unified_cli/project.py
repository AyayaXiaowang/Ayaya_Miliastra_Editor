from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import try_find_graph_generater_root, ugc_file_tools_root
from ugc_file_tools.writeback_defaults import (
    default_ingame_save_structs_bootstrap_gil_path,
    default_node_graph_client_template_gil_path,
    default_node_graph_client_template_library_dir,
    default_node_graph_mapping_json_path,
    default_node_graph_server_template_gil_path,
    default_node_graph_server_template_library_dir,
    default_signal_template_gil_path,
    default_struct_template_gil_hint_path,
)


_INVALID_WINDOWS_FILENAME_CHARS = '<>:"/\\|?*'


@dataclass(frozen=True, slots=True)
class _ProjectWritebackSelection:
    selected_struct_ids: list[str]
    selected_ingame_struct_ids: list[str]
    selected_signal_ids: list[str]
    # 关卡实体自定义变量：selection-json 仅携带 variable_id 列表；写回阶段再按 variable_id 查表并写入 root4/5/1(关卡实体).override_variables(group1)。
    selected_level_custom_variable_ids: list[str]
    selected_graph_code_files: list[Path]
    selected_template_json_files: list[Path]
    selected_instance_json_files: list[Path]
    graph_source_roots: list[Path]
    write_ui: bool
    ui_auto_sync_custom_variables: bool
    # UI Workbench bundle（UI源码/__workbench_out__/*.ui_bundle.json）写回时的“同名布局冲突策略”
    # item schema（dict）：
    # - layout_name: str
    # - action: "overwrite" | "add" | "skip"
    # - new_layout_name: str（仅 action="add" 时需要）
    ui_layout_conflict_resolutions: list[dict[str, str]]
    # 节点图写回时的“同名节点图冲突策略”（导出中心交互用；按 graph_code_file 精确匹配）。
    # item schema（dict）：
    # - graph_code_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_graph_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    node_graph_conflict_resolutions: list[dict[str, str]]
    # 元件库模板写回时的“同名模板冲突策略”（导出中心交互用；按 template_json_file 精确匹配）。
    # item schema（dict）：
    # - template_json_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_template_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    template_conflict_resolutions: list[dict[str, str]]
    # 实体摆放写回时的“同名实体冲突策略”（导出中心交互用；按 instance_json_file 精确匹配）。
    # item schema（dict）：
    # - instance_json_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_instance_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    instance_conflict_resolutions: list[dict[str, str]]
    prefer_signal_specific_type_id: bool


def _load_project_writeback_selection(*, selection_json_file: Path) -> _ProjectWritebackSelection:
    selection_path = Path(selection_json_file).resolve()
    if not selection_path.is_file():
        raise FileNotFoundError(str(selection_path))

    data = json.loads(selection_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("selection-json root must be dict")

    def _read_str_list(key: str) -> list[str]:
        raw = data.get(key, None)
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"selection-json field {key!r} must be list[str]")
        out: list[str] = []
        for idx, item in enumerate(raw):
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError(f"selection-json field {key!r}[{idx}] must be str")
            text = str(item).strip()
            if text:
                out.append(text)
        # 去重（保持顺序）
        seen: set[str] = set()
        deduped: list[str] = []
        for x in out:
            k = x.casefold()
            if k in seen:
                continue
            seen.add(k)
            deduped.append(x)
        return deduped

    def _read_abs_path_list(key: str) -> list[Path]:
        raw = _read_str_list(key)
        paths: list[Path] = []
        for idx, text in enumerate(raw):
            p = Path(text)
            if not p.is_absolute():
                raise ValueError(f"selection-json field {key!r}[{idx}] must be absolute path: {text!r}")
            paths.append(p.resolve())
        # 去重（保持顺序）
        seen: set[str] = set()
        deduped_paths: list[Path] = []
        for p in paths:
            k = str(p).casefold()
            if k in seen:
                continue
            seen.add(k)
            deduped_paths.append(p)
        return deduped_paths

    def _read_layout_conflict_resolutions(key: str) -> list[dict[str, str]]:
        raw = data.get(key, None)
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"selection-json field {key!r} must be list[dict]")
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise TypeError(f"selection-json field {key!r}[{idx}] must be dict")
            layout_name = str(item.get("layout_name") or "").strip()
            if layout_name == "":
                raise ValueError(f"selection-json field {key!r}[{idx}].layout_name 不能为空")
            action = str(item.get("action") or "").strip().lower()
            if action not in {"overwrite", "add", "skip"}:
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
                )
            new_layout_name = str(item.get("new_layout_name") or "").strip()
            if action == "add" and new_layout_name == "":
                raise ValueError(f"selection-json field {key!r}[{idx}] action=add 时 new_layout_name 不能为空")
            k = layout_name.casefold()
            if k in seen:
                raise ValueError(f"selection-json field {key!r} 中存在重复 layout_name（忽略大小写）：{layout_name!r}")
            seen.add(k)
            obj: dict[str, str] = {"layout_name": layout_name, "action": action}
            if action == "add":
                obj["new_layout_name"] = new_layout_name
            out.append(obj)
        return out

    def _read_node_graph_conflict_resolutions(key: str) -> list[dict[str, str]]:
        raw = data.get(key, None)
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"selection-json field {key!r} must be list[dict]")
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise TypeError(f"selection-json field {key!r}[{idx}] must be dict")
            graph_code_file = str(item.get("graph_code_file") or "").strip()
            if graph_code_file == "":
                raise ValueError(f"selection-json field {key!r}[{idx}].graph_code_file 不能为空")
            p = Path(graph_code_file)
            if not p.is_absolute():
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].graph_code_file must be absolute path: {graph_code_file!r}"
                )
            action = str(item.get("action") or "").strip().lower()
            if action not in {"overwrite", "add", "skip"}:
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
                )
            new_graph_name = str(item.get("new_graph_name") or "").strip()
            if action == "add" and new_graph_name == "":
                raise ValueError(f"selection-json field {key!r}[{idx}] action=add 时 new_graph_name 不能为空")
            k = str(p.resolve()).casefold()
            if k in seen:
                raise ValueError(
                    f"selection-json field {key!r} 中存在重复 graph_code_file（忽略大小写）：{str(p.resolve())!r}"
                )
            seen.add(k)
            obj: dict[str, str] = {"graph_code_file": str(p.resolve()), "action": action}
            if action == "add":
                obj["new_graph_name"] = new_graph_name
            out.append(obj)
        return out

    def _read_template_conflict_resolutions(key: str) -> list[dict[str, str]]:
        raw = data.get(key, None)
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"selection-json field {key!r} must be list[dict]")
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise TypeError(f"selection-json field {key!r}[{idx}] must be dict")
            template_json_file = str(item.get("template_json_file") or "").strip()
            if template_json_file == "":
                raise ValueError(f"selection-json field {key!r}[{idx}].template_json_file 不能为空")
            p = Path(template_json_file)
            if not p.is_absolute():
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].template_json_file must be absolute path: {template_json_file!r}"
                )
            action = str(item.get("action") or "").strip().lower()
            if action not in {"overwrite", "add", "skip"}:
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
                )
            new_template_name = str(item.get("new_template_name") or "").strip()
            if action == "add" and new_template_name == "":
                raise ValueError(f"selection-json field {key!r}[{idx}] action=add 时 new_template_name 不能为空")
            k = str(p.resolve()).casefold()
            if k in seen:
                raise ValueError(
                    f"selection-json field {key!r} 中存在重复 template_json_file（忽略大小写）：{str(p.resolve())!r}"
                )
            seen.add(k)
            obj: dict[str, str] = {"template_json_file": str(p.resolve()), "action": action}
            if action == "add":
                obj["new_template_name"] = new_template_name
            out.append(obj)
        return out

    def _read_instance_conflict_resolutions(key: str) -> list[dict[str, str]]:
        raw = data.get(key, None)
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError(f"selection-json field {key!r} must be list[dict]")
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise TypeError(f"selection-json field {key!r}[{idx}] must be dict")
            instance_json_file = str(item.get("instance_json_file") or "").strip()
            if instance_json_file == "":
                raise ValueError(f"selection-json field {key!r}[{idx}].instance_json_file 不能为空")
            p = Path(instance_json_file)
            if not p.is_absolute():
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].instance_json_file must be absolute path: {instance_json_file!r}"
                )
            action = str(item.get("action") or "").strip().lower()
            if action not in {"overwrite", "add", "skip"}:
                raise ValueError(
                    f"selection-json field {key!r}[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
                )
            new_instance_name = str(item.get("new_instance_name") or "").strip()
            if action == "add" and new_instance_name == "":
                raise ValueError(f"selection-json field {key!r}[{idx}] action=add 时 new_instance_name 不能为空")
            k = str(p.resolve()).casefold()
            if k in seen:
                raise ValueError(
                    f"selection-json field {key!r} 中存在重复 instance_json_file（忽略大小写）：{str(p.resolve())!r}"
                )
            seen.add(k)
            obj: dict[str, str] = {"instance_json_file": str(p.resolve()), "action": action}
            if action == "add":
                obj["new_instance_name"] = new_instance_name
            out.append(obj)
        return out

    write_ui = bool(data.get("write_ui", False))
    ui_auto_sync_custom_variables = bool(data.get("ui_auto_sync_custom_variables", True))
    # 默认开启：对齐真源端口展开/绑定口径；仅在满足“静态绑定 + base 映射可用”时才会实际切换。
    prefer_signal_specific_type_id = bool(data.get("prefer_signal_specific_type_id", True))

    return _ProjectWritebackSelection(
        selected_struct_ids=_read_str_list("selected_struct_ids"),
        selected_ingame_struct_ids=_read_str_list("selected_ingame_struct_ids"),
        selected_signal_ids=_read_str_list("selected_signal_ids"),
        selected_level_custom_variable_ids=_read_str_list("selected_level_custom_variable_ids"),
        selected_graph_code_files=_read_abs_path_list("selected_graph_code_files"),
        selected_template_json_files=_read_abs_path_list("selected_template_json_files"),
        selected_instance_json_files=_read_abs_path_list("selected_instance_json_files"),
        graph_source_roots=_read_abs_path_list("graph_source_roots"),
        write_ui=bool(write_ui),
        ui_auto_sync_custom_variables=bool(ui_auto_sync_custom_variables),
        ui_layout_conflict_resolutions=_read_layout_conflict_resolutions("ui_layout_conflict_resolutions"),
        node_graph_conflict_resolutions=_read_node_graph_conflict_resolutions("node_graph_conflict_resolutions"),
        template_conflict_resolutions=_read_template_conflict_resolutions("template_conflict_resolutions"),
        instance_conflict_resolutions=_read_instance_conflict_resolutions("instance_conflict_resolutions"),
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
    )


def _default_project_archive_root() -> Path:
    gg_root = try_find_graph_generater_root(start_path=Path(__file__))
    if gg_root is None:
        raise ValueError(
            "无法定位 Graph_Generater 根目录（需要包含 engine/assets；通常包含 app/plugins 或 tools）。"
            "请显式指定 --project-root 或 --project-archive。"
        )
    return Path(gg_root) / "assets" / "资源库" / "项目存档"


def _sanitize_package_id(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned == "":
        return ""
    for ch in _INVALID_WINDOWS_FILENAME_CHARS:
        cleaned = cleaned.replace(ch, "_")
    # Windows: 目录名不能以空格/点结尾
    cleaned = cleaned.rstrip(" .")
    return cleaned


def _set_graph_generater_last_opened_package(graph_generater_root: Path, package_id: str) -> None:
    state_file = graph_generater_root / "app" / "runtime" / "package_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}
    data["last_opened_package_id"] = str(package_id)
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _command_project_supported(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.project_archive_importer.supported import get_supported_importers

    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(get_supported_importers(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _command_project_import(arguments: argparse.Namespace) -> None:
    if not bool(getattr(arguments, "dangerous", False)):
        raise SystemExit(
            "该命令会将项目存档内容写回到 .gil（危险写盘）。\n"
            "为避免误操作，必须显式添加 --dangerous 才允许运行。\n"
            "示例：\n"
            "  python -X utf8 -m ugc_file_tools project import --dangerous --help\n"
        )

    from ugc_file_tools.pipelines.project_writeback import ProjectWritebackPlan, run_project_writeback_to_gil
    from ugc_file_tools.project_archive_importer.struct_definitions_importer import resolve_project_archive_path

    project_archive_path = resolve_project_archive_path(
        project_archive=arguments.project_archive,
        project_id=arguments.project_id,
        project_root=arguments.project_root,
    )

    project_path = Path(project_archive_path).resolve()

    selection_json_text = str(getattr(arguments, "selection_json_file", "") or "").strip()
    selection: _ProjectWritebackSelection | None = None
    if selection_json_text:
        selection = _load_project_writeback_selection(selection_json_file=Path(selection_json_text))

    want_templates = False
    want_instances = False
    want_structs = False
    want_signals = False
    want_graphs = False
    want_ui_widget_templates = False
    want_level_custom_variables = False

    # ===== 选择导入内容 =====
    if selection is None:
        # 不 silent skip：若所有内容都不可导入则报错
        from ugc_file_tools.writeback_parts import WritebackPartId, compute_writeback_availability

        gg_root = try_find_graph_generater_root(start_path=project_path)
        availability = compute_writeback_availability(
            project_root=project_path,
            workspace_root=(gg_root if gg_root is not None else project_path),
        )

        want_templates = (not bool(getattr(arguments, "skip_templates", False))) and bool(
            availability.get(WritebackPartId.TEMPLATES, False)
        )
        want_instances = (not bool(getattr(arguments, "skip_instances", False))) and bool(
            availability.get(WritebackPartId.INSTANCES, False)
        )

        # 结构体导入（写回 .gil）判定：
        # - decoded-json：读取 .gil 导入项目存档后产生（精确对齐 blob）
        # - code-level：手工维护的基础结构体/局内存档结构体（.py）
        # - 作用域：项目本身 + 共享根（若项目为空也可能仅依赖共享）
        want_structs = False
        if not bool(getattr(arguments, "skip_structs", False)):
            want_structs = bool(availability.get(WritebackPartId.STRUCTS, False))
            if not want_structs and gg_root is None:
                # 无法定位 Graph_Generater 根目录时仍尝试导入，让下游 importer 给出更明确报错。
                want_structs = True

        want_signals = False
        if not bool(getattr(arguments, "skip_signals", False)):
            want_signals = bool(availability.get(WritebackPartId.SIGNALS, False))
            if not want_signals and gg_root is None:
                # 无法定位 Graph_Generater 根目录时仍尝试导入，让下游 importer 提供更明确的报错与指引。
                want_signals = True

        want_graphs = (not bool(getattr(arguments, "skip_graphs", False))) and bool(
            availability.get(WritebackPartId.GRAPHS, False)
        )

        want_ui_widget_templates = (not bool(getattr(arguments, "skip_ui_widget_templates", False))) and bool(
            availability.get(WritebackPartId.UI_WIDGET_TEMPLATES, False)
        )
    else:
        # 选择式写回：只写回 selection-json 指定的内容（struct/signal/graphs/templates/instances/ui/level_vars）。
        want_templates = bool(selection.selected_template_json_files)
        want_instances = bool(selection.selected_instance_json_files)
        want_level_custom_variables = bool(selection.selected_level_custom_variable_ids)
        want_structs = bool(selection.selected_struct_ids or selection.selected_ingame_struct_ids)
        want_signals = bool(selection.selected_signal_ids)
        want_graphs = bool(selection.selected_graph_code_files)
        want_ui_widget_templates = bool(selection.write_ui)

        if bool(getattr(arguments, "skip_structs", False)) and want_structs:
            raise ValueError("--skip-structs 与 --selection-json 冲突：selection 指定了结构体写回")
        if bool(getattr(arguments, "skip_signals", False)) and want_signals:
            raise ValueError("--skip-signals 与 --selection-json 冲突：selection 指定了信号写回")
        if bool(getattr(arguments, "skip_graphs", False)) and want_graphs:
            raise ValueError("--skip-graphs 与 --selection-json 冲突：selection 指定了节点图写回")
        if bool(getattr(arguments, "skip_templates", False)) and want_templates:
            raise ValueError("--skip-templates 与 --selection-json 冲突：selection 指定了元件模板写回")
        if bool(getattr(arguments, "skip_instances", False)) and want_instances:
            raise ValueError("--skip-instances 与 --selection-json 冲突：selection 指定了实体摆放写回")
        if bool(getattr(arguments, "skip_ui_widget_templates", False)) and want_ui_widget_templates:
            raise ValueError("--skip-ui-widget-templates 与 --selection-json 冲突：selection 指定了 UI 写回")

    if (
        not want_templates
        and not want_instances
        and not want_level_custom_variables
        and not want_structs
        and not want_signals
        and not want_graphs
        and not want_ui_widget_templates
    ):
        if selection is not None:
            raise ValueError(
                "selection-json 未选择任何写回内容（struct/signal/graphs/templates/instances/ui/level_vars 均为空）。"
            )
        raise ValueError(
            "项目存档缺少可导入内容（元件库/实体/结构体/信号/节点图/UI控件模板均为空或被跳过）："
            f"{str(project_path)}"
        )

    input_gil_path = Path(arguments.input_gil_file).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_user_path = Path(arguments.output_gil_file)

    # 统一收口：走 pipeline（与 UI 导出共用）
    # 注意：pipeline 可能在“只写回节点图(export_graphs=True)但未显式写回信号(export_signals=False)”时
    # 自动启用信号写回（补齐节点图依赖的信号闭包）。因此这里即使 want_signals=False，也需要解析并透传
    # `--signals-template-gil/--signals-bootstrap-template-gil` 等信号配置，以保证 CLI 参数不会被静默忽略。
    template_text = str(getattr(arguments, "signals_template_gil_file", "") or "").strip()
    signals_template_gil: Path | None = None
    if template_text:
        template_gil = Path(template_text)
        if not template_gil.is_absolute():
            candidate = ugc_file_tools_root() / template_gil
            if candidate.is_file():
                template_gil = candidate
        signals_template_gil = template_gil.resolve()
    else:
        # 留空：下游会按 base → bootstrap → 内置默认模板 自动选择可用样本
        signals_template_gil = None

    bootstrap_text = str(getattr(arguments, "signals_bootstrap_template_gil_file", "") or "").strip()
    signals_bootstrap_gil: Path | None = None
    if bootstrap_text:
        bootstrap_gil_path = Path(bootstrap_text)
        if not bootstrap_gil_path.is_absolute():
            candidate = ugc_file_tools_root() / bootstrap_gil_path
            if candidate.is_file():
                bootstrap_gil_path = candidate
        signals_bootstrap_gil = bootstrap_gil_path.resolve()

    signals_emit_reserved_placeholder_signal_flag = getattr(arguments, "signals_emit_reserved_placeholder_signal", None)
    signals_emit_reserved_placeholder_signal = (
        False
        if signals_emit_reserved_placeholder_signal_flag is None
        else bool(signals_emit_reserved_placeholder_signal_flag)
    )

    graphs_scope = str(getattr(arguments, "graphs_scope", "all") or "all").strip().lower()
    if graphs_scope not in {"all", "server", "client"}:
        raise ValueError(f"unsupported graphs_scope: {graphs_scope!r}")
    graphs_source = str(getattr(arguments, "graphs_source", "scan_all") or "scan_all").strip().lower()
    if graphs_source not in {"scan_all", "overview"}:
        raise ValueError(f"unsupported graphs_source: {graphs_source!r}")

    ui_auto_sync_custom_variables_flag = getattr(arguments, "ui_auto_sync_custom_variables", None)
    ui_auto_sync_custom_variables = True if ui_auto_sync_custom_variables_flag is None else bool(ui_auto_sync_custom_variables_flag)
    if selection is not None:
        ui_auto_sync_custom_variables = bool(selection.ui_auto_sync_custom_variables)
        if ui_auto_sync_custom_variables_flag is not None:
            ui_auto_sync_custom_variables = bool(ui_auto_sync_custom_variables_flag)

    prefer_signal_specific_type_id_flag = getattr(arguments, "prefer_signal_specific_type_id", None)
    # 默认开启：对齐真源端口展开/绑定口径；仅在满足“静态绑定 + base 映射可用”时才会实际切换。
    prefer_signal_specific_type_id = (
        True if prefer_signal_specific_type_id_flag is None else bool(prefer_signal_specific_type_id_flag)
    )
    if selection is not None:
        prefer_signal_specific_type_id = bool(selection.prefer_signal_specific_type_id)
        if prefer_signal_specific_type_id_flag is not None:
            prefer_signal_specific_type_id = bool(prefer_signal_specific_type_id_flag)
    ui_export_record_id_text = str(getattr(arguments, "ui_export_record_id", "") or "").strip()
    ui_export_record_id = str(ui_export_record_id_text) if ui_export_record_id_text != "" else None

    id_ref_text = str(getattr(arguments, "id_ref_gil_file", "") or "").strip()
    id_ref_gil_file: Path | None = None
    if id_ref_text != "":
        p = Path(id_ref_text)
        if not p.is_absolute():
            candidate = ugc_file_tools_root() / p
            if candidate.is_file():
                p = candidate
        id_ref_gil_file = p.resolve()

    overrides_text = str(getattr(arguments, "id_ref_overrides_json_file", "") or "").strip()
    id_ref_overrides_json_file: Path | None = None
    if overrides_text != "":
        p2 = Path(overrides_text)
        if not p2.is_absolute():
            candidate2 = ugc_file_tools_root() / p2
            if candidate2.is_file():
                p2 = candidate2
        id_ref_overrides_json_file = p2.resolve()

    plan = ProjectWritebackPlan(
        project_archive_path=project_path,
        input_gil_file_path=input_gil_path,
        output_gil_user_path=output_user_path,
        export_templates=bool(want_templates),
        export_instances=bool(want_instances),
        export_structs=bool(want_structs),
        export_signals=bool(want_signals),
        export_graphs=bool(want_graphs),
        export_ui_widget_templates=bool(want_ui_widget_templates),
        selected_struct_ids=(list(selection.selected_struct_ids) if (selection is not None and selection.selected_struct_ids) else None),
        selected_ingame_struct_ids=(
            list(selection.selected_ingame_struct_ids)
            if (selection is not None and selection.selected_ingame_struct_ids)
            else None
        ),
        selected_signal_ids=(list(selection.selected_signal_ids) if (selection is not None and selection.selected_signal_ids) else None),
        selected_level_custom_variable_ids=(
            list(selection.selected_level_custom_variable_ids)
            if (selection is not None and selection.selected_level_custom_variable_ids)
            else None
        ),
        selected_graph_code_files=(
            list(selection.selected_graph_code_files)
            if (selection is not None and selection.selected_graph_code_files)
            else None
        ),
        selected_template_json_files=(
            list(selection.selected_template_json_files)
            if (selection is not None and selection.selected_template_json_files)
            else None
        ),
        selected_instance_json_files=(
            list(selection.selected_instance_json_files)
            if (selection is not None and selection.selected_instance_json_files)
            else None
        ),
        graph_source_roots=(
            list(selection.graph_source_roots)
            if (selection is not None and selection.graph_source_roots)
            else None
        ),
        templates_mode=str(getattr(arguments, "templates_mode", "overwrite") or "overwrite"),
        include_placeholder_templates=bool(getattr(arguments, "include_placeholder_templates", False)),
        instances_mode=str(getattr(arguments, "instances_mode", "overwrite") or "overwrite"),
        struct_mode=str(getattr(arguments, "mode", "merge") or "merge"),
        signals_param_build_mode=str(getattr(arguments, "signals_param_build_mode", "semantic") or "semantic"),
        signals_template_gil=signals_template_gil,
        signals_bootstrap_gil=signals_bootstrap_gil,
        signals_emit_reserved_placeholder_signal=bool(signals_emit_reserved_placeholder_signal),
        graphs_scope=graphs_scope,
        graph_scan_all=(graphs_source == "scan_all"),
        graph_strict_graph_code_files=bool(getattr(arguments, "graphs_strict", False)),
        graph_output_model_dir_name=str(getattr(arguments, "graphs_output_model_dir_name", "") or "").strip(),
        graph_server_template_gil=Path(
            str(getattr(arguments, "graphs_server_template_gil", str(default_node_graph_server_template_gil_path())))
        ),
        graph_server_template_library_dir=Path(
            str(getattr(arguments, "graphs_server_template_library_dir", str(default_node_graph_server_template_library_dir())))
        ),
        graph_client_template_gil=Path(
            str(getattr(arguments, "graphs_client_template_gil", str(default_node_graph_client_template_gil_path())))
        ),
        graph_client_template_library_dir=Path(
            str(getattr(arguments, "graphs_client_template_library_dir", str(default_node_graph_client_template_library_dir())))
        ),
        graph_mapping_json=Path(str(getattr(arguments, "graphs_mapping_json", str(default_node_graph_mapping_json_path())))),
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
        ui_widget_templates_mode=(
            str(getattr(arguments, "ui_widget_templates_mode", "") or "").strip()
            or str(getattr(arguments, "mode", "merge") or "merge")
        ),
        ui_auto_sync_custom_variables=bool(ui_auto_sync_custom_variables),
        ui_layout_conflict_resolutions=(
            list(selection.ui_layout_conflict_resolutions)
            if (selection is not None and selection.ui_layout_conflict_resolutions)
            else None
        ),
        node_graph_conflict_resolutions=(
            list(selection.node_graph_conflict_resolutions)
            if (selection is not None and selection.node_graph_conflict_resolutions)
            else None
        ),
        template_conflict_resolutions=(
            list(selection.template_conflict_resolutions)
            if (selection is not None and selection.template_conflict_resolutions)
            else None
        ),
        instance_conflict_resolutions=(
            list(selection.instance_conflict_resolutions)
            if (selection is not None and selection.instance_conflict_resolutions)
            else None
        ),
        ui_export_record_id=ui_export_record_id,
        id_ref_gil_file=id_ref_gil_file,
        id_ref_overrides_json_file=id_ref_overrides_json_file,
    )

    # 简单进度打印（避免沉默导致误判卡死）
    def _print_progress(current: int, total: int, label: str) -> None:
        import sys

        print(f"[{int(current)}/{int(total)}] {str(label)}", file=sys.stderr)

    combined_report = run_project_writeback_to_gil(plan=plan, progress_cb=_print_progress)

    report_path_text = str(arguments.report_json_file or "").strip()
    if report_path_text:
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(combined_report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(combined_report, ensure_ascii=False, indent=2))


def _command_project_import_ingame_save_structs(arguments: argparse.Namespace) -> None:
    if not bool(getattr(arguments, "dangerous", False)):
        raise SystemExit(
            "该命令会将局内存档结构体写回到 .gil（危险写盘）。\n"
            "为避免误操作，必须显式添加 --dangerous 才允许运行。\n"
            "示例：\n"
            "  python -X utf8 -m ugc_file_tools project import-ingame-save-structs --dangerous --help\n"
        )

    from ugc_file_tools.project_archive_importer.ingame_save_structs_importer import (
        IngameSaveStructImportOptions,
        import_ingame_save_structs_from_project_archive_to_gil,
    )
    from ugc_file_tools.project_archive_importer.struct_definitions_importer import resolve_project_archive_path

    project_archive_path = resolve_project_archive_path(
        project_archive=arguments.project_archive,
        project_id=arguments.project_id,
        project_root=arguments.project_root,
    )

    input_gil_path = Path(arguments.input_gil_file).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_user_path_raw = Path(arguments.output_gil_file)
    output_tool_path = resolve_output_file_path_in_out_dir(output_user_path_raw)
    output_tool_path.parent.mkdir(parents=True, exist_ok=True)

    output_user_path: Path | None = output_user_path_raw.resolve() if output_user_path_raw.is_absolute() else None
    if output_user_path is not None and output_user_path.resolve() == input_gil_path.resolve():
        raise ValueError(f"输出路径不能与输入路径相同（会覆盖 base gil）：{str(output_user_path)}")

    report = import_ingame_save_structs_from_project_archive_to_gil(
        project_archive_path=project_archive_path,
        input_gil_file_path=input_gil_path,
        output_gil_file_path=Path(output_tool_path),
        options=IngameSaveStructImportOptions(mode=str(arguments.mode)),
        bootstrap_template_gil_file_path=(
            Path(arguments.bootstrap_template_gil_file) if arguments.bootstrap_template_gil_file else None
        ),
    )

    if output_user_path is not None and Path(output_tool_path).resolve() != output_user_path.resolve():
        output_user_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(output_tool_path).resolve(), output_user_path.resolve())

    report_path_text = str(arguments.report_json_file or "").strip()
    if report_path_text:
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def _command_project_import_basic_structs(arguments: argparse.Namespace) -> None:
    """
    仅写回“基础结构体”（decoded-json 或 基础结构体/*.py）。

    用途：与 `project import-ingame-save-structs` 配合做二分定位：当真源导入失败时，
    先确认到底是基础结构体段还是局内存档结构体段导致。
    """
    if not bool(getattr(arguments, "dangerous", False)):
        raise SystemExit(
            "该命令会将基础结构体写回到 .gil（危险写盘）。\n"
            "为避免误操作，必须显式添加 --dangerous 才允许运行。\n"
            "示例：\n"
            "  python -X utf8 -m ugc_file_tools project import-basic-structs --dangerous --help\n"
        )

    from ugc_file_tools.project_archive_importer.struct_definitions_importer import (
        StructImportOptions,
        import_struct_definitions_from_project_archive_to_gil,
        resolve_project_archive_path,
    )

    project_archive_path = resolve_project_archive_path(
        project_archive=arguments.project_archive,
        project_id=arguments.project_id,
        project_root=arguments.project_root,
    )

    input_gil_path = Path(arguments.input_gil_file).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_user_path_raw = Path(arguments.output_gil_file)
    output_tool_path = resolve_output_file_path_in_out_dir(output_user_path_raw)
    output_tool_path.parent.mkdir(parents=True, exist_ok=True)

    output_user_path: Path | None = output_user_path_raw.resolve() if output_user_path_raw.is_absolute() else None
    if output_user_path is not None and output_user_path.resolve() == input_gil_path.resolve():
        raise ValueError(f"输出路径不能与输入路径相同（会覆盖 base gil）：{str(output_user_path)}")

    report = import_struct_definitions_from_project_archive_to_gil(
        project_archive_path=project_archive_path,
        input_gil_file_path=input_gil_path,
        output_gil_file_path=Path(output_tool_path),
        options=StructImportOptions(mode=str(getattr(arguments, "mode", "merge") or "merge")),
    )

    if output_user_path is not None and Path(output_tool_path).resolve() != output_user_path.resolve():
        output_user_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(output_tool_path).resolve(), output_user_path.resolve())

    report_path_text = str(arguments.report_json_file or "").strip()
    if report_path_text:
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def _command_project_export_from_gil(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.pipelines.gil_to_project_archive import (
        GilToProjectArchivePlan,
        run_gil_to_project_archive,
    )

    input_gil_file_path = Path(arguments.input_gil_file).resolve()
    if not input_gil_file_path.is_file():
        raise FileNotFoundError(str(input_gil_file_path))

    project_root = Path(arguments.project_root).resolve() if str(arguments.project_root or "").strip() else _default_project_archive_root()
    if not project_root.exists() or not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    project_id_text = str(arguments.project_id or "").strip()
    if project_id_text == "":
        project_id_text = input_gil_file_path.stem
    project_id = _sanitize_package_id(project_id_text)
    if project_id == "":
        raise ValueError("无法从输入文件推导项目存档目录名，请显式指定 --project-id")

    output_package_root = (project_root / project_id).resolve()
    if output_package_root.exists():
        if bool(arguments.overwrite):
            shutil.rmtree(output_package_root)
        else:
            raise ValueError(
                f"目标项目存档目录已存在：{str(output_package_root)}。"
                "请更换 --project-id，或使用 --overwrite 覆盖。"
            )

    parse_status_root_text = str(arguments.parse_status_root or "").strip()
    parse_status_root = Path(parse_status_root_text).resolve() if parse_status_root_text else None

    dtype_text = str(arguments.dtype_path or "").strip()
    dtype_path = Path(dtype_text).resolve() if dtype_text else None

    focus_graph_id = int(arguments.focus_graph_id) if arguments.focus_graph_id is not None else None

    validate_graph_code = bool(getattr(arguments, "validate_graph_code", False))
    if validate_graph_code and not bool(arguments.generate_graph_code):
        raise ValueError("--validate-graph-code 需要与 --generate-graph-code 同时使用")

    def _print_progress(current: int, total: int, label: str) -> None:
        import sys

        print(f"[{int(current)}/{int(total)}] {str(label)}", file=sys.stderr)

    report = run_gil_to_project_archive(
        plan=GilToProjectArchivePlan(
            input_gil_file_path=input_gil_file_path,
            output_package_root=output_package_root,
            package_id=str(project_id),
            enable_dll_dump=bool(arguments.enable_dll_dump),
            dtype_path=dtype_path,
            parse_status_root=parse_status_root,
            data_blob_min_bytes_for_decode=int(arguments.data_min_bytes),
            generic_scan_min_bytes=int(arguments.generic_scan_min_bytes),
            focus_graph_id=focus_graph_id,
            ensure_package_structure_fn=None,
            generate_graph_code=bool(arguments.generate_graph_code),
            overwrite_graph_code=bool(arguments.overwrite_graph_code),
            validate_graph_code_after_generate=(bool(validate_graph_code) if bool(arguments.generate_graph_code) else False),
            graph_generater_root_for_validation=None,
            set_last_opened=bool(arguments.set_last_opened),
        ),
        progress_cb=_print_progress,
    )

    _ = report

    print(str(output_package_root))


def add_subparser_project(subparsers: argparse._SubParsersAction) -> None:
    project_parser = subparsers.add_parser("project", help="Graph_Generater 项目存档与 .gil 的互通（导出/导入）")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)

    supported_parser = project_subparsers.add_parser("supported", help="输出当前支持导入的内容清单（JSON）")
    supported_parser.add_argument(
        "--output",
        dest="output_json_file",
        required=True,
        help="输出 JSON 文件路径",
    )
    supported_parser.set_defaults(entrypoint=_command_project_supported)

    import_parser = project_subparsers.add_parser(
        "import",
        help="将项目存档中已支持的内容写回到 .gil（元件库/实体/结构体/信号/节点图/UI控件模板）",
    )
    import_parser.add_argument(
        "--dangerous",
        dest="dangerous",
        action="store_true",
        help="允许运行写回命令（危险写盘，需要你明确确认风险）。",
    )
    import_parser.add_argument("--project-archive", dest="project_archive", default=None, help="项目存档目录路径（优先）")
    import_parser.add_argument("--project-id", dest="project_id", default=None, help="项目存档目录名（与 --project-root 配合）")
    import_parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        help="项目存档根目录（默认自动指向 Graph_Generater/assets/资源库/项目存档）",
    )
    import_parser.add_argument(
        "--mode",
        choices=["merge", "overwrite"],
        default="merge",
        help="merge=保留旧的并补齐缺失；overwrite=覆盖同 ID（结构体）/同 GUID（UI控件模板）",
    )
    import_parser.add_argument("--skip-templates", dest="skip_templates", action="store_true", help="跳过元件库模板写回")
    import_parser.add_argument("--skip-instances", dest="skip_instances", action="store_true", help="跳过实体摆放写回")
    import_parser.add_argument("--skip-structs", dest="skip_structs", action="store_true", help="跳过结构体定义导入")
    import_parser.add_argument("--skip-signals", dest="skip_signals", action="store_true", help="跳过信号定义导入")
    import_parser.add_argument("--skip-graphs", dest="skip_graphs", action="store_true", help="跳过节点图写回")
    import_parser.add_argument(
        "--skip-ui-widget-templates",
        dest="skip_ui_widget_templates",
        action="store_true",
        help="跳过 UI控件模板（界面控件组模板）导入",
    )
    import_parser.add_argument(
        "--selection-json",
        dest="selection_json_file",
        default="",
        help=(
            "可选：选择式写回 selection.json（仅写回所选 struct/signal/graphs/templates/instances/ui/level_vars）。"
            "适用于 UI 的“按选择导出 .gil”。"
        ),
    )

    import_parser.add_argument(
        "--templates-mode",
        dest="templates_mode",
        choices=["merge", "overwrite"],
        default="overwrite",
        help="元件库模板写回模式：merge=保留旧的；overwrite=覆盖名称",
    )
    import_parser.add_argument(
        "--include-placeholder-templates",
        dest="include_placeholder_templates",
        action="store_true",
        help="包含占位模板（metadata.ugc.placeholder=true）（不推荐）",
    )

    import_parser.add_argument(
        "--instances-mode",
        dest="instances_mode",
        choices=["merge", "overwrite"],
        default="overwrite",
        help="实体摆放写回模式：merge=保留旧的；overwrite=覆盖位置/名字/引用等",
    )

    import_parser.add_argument(
        "--graphs-scope",
        dest="graphs_scope",
        choices=["all", "server", "client"],
        default="all",
        help="节点图写回作用域：all/server/client",
    )
    import_parser.add_argument(
        "--graphs-source",
        dest="graphs_source",
        choices=["scan_all", "overview"],
        default="scan_all",
        help="节点图来源：scan_all=扫描 节点图/**.py；overview=仅导出 <package>总览.json 声明的图",
    )
    import_parser.add_argument(
        "--graphs-strict",
        dest="graphs_strict",
        action="store_true",
        help="严格模式：更严格校验节点图源码是否符合预期（用于排查不一致）",
    )
    import_parser.add_argument(
        "--graphs-output-model-dir",
        dest="graphs_output_model_dir_name",
        default="",
        help="可选：GraphModel JSON 输出目录名（默认 <package_id>_graph_models，强制落盘到 out/）",
    )
    import_parser.add_argument(
        "--id-ref-gil",
        dest="id_ref_gil_file",
        default="",
        help=(
            "可选：占位符参考 `.gil` 文件，用于回填节点图中的 entity_key/component_key。\n"
            "留空：默认使用本次写回的 input_gil 作为参考（通常就是你选择的 base gil）。"
        ),
    )
    import_parser.add_argument(
        "--id-ref-overrides-json",
        dest="id_ref_overrides_json_file",
        default="",
        help="可选：entity_key/component_key 占位符手动覆盖映射 JSON（占位符 name → ID）。",
    )
    import_parser.add_argument(
        "--graphs-server-template-gil",
        dest="graphs_server_template_gil",
        default=str(default_node_graph_server_template_gil_path()),
        help="server 节点图写回用模板 .gil（提供节点/record 样本）",
    )
    import_parser.add_argument(
        "--graphs-server-template-library-dir",
        dest="graphs_server_template_library_dir",
        default=str(default_node_graph_server_template_library_dir()),
        help="server 节点图写回用模板样本库目录",
    )
    import_parser.add_argument(
        "--graphs-client-template-gil",
        dest="graphs_client_template_gil",
        default=str(default_node_graph_client_template_gil_path()),
        help="client 节点图写回用模板 .gil（提供节点/record 样本）",
    )
    import_parser.add_argument(
        "--graphs-client-template-library-dir",
        dest="graphs_client_template_library_dir",
        default=str(default_node_graph_client_template_library_dir()),
        help="client 节点图写回用模板样本库目录",
    )
    import_parser.add_argument(
        "--graphs-mapping-json",
        dest="graphs_mapping_json",
        default=str(default_node_graph_mapping_json_path()),
        help="节点类型语义映射 JSON（node_type_semantic_map.json）",
    )
    import_parser.add_argument(
        "--prefer-signal-specific-type-id",
        dest="prefer_signal_specific_type_id",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "兼容参数（保留旧 CLI 口径）：当节点图中的信号节点满足“静态绑定 + base `.gil` 映射可用”时，"
            "写回侧会自动将其 runtime type_id 提升为 signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx）。\n"
            "当前实现中该行为为默认/固定策略：即使传入 --no-prefer-signal-specific-type-id 也不会关闭（参数仅用于兼容旧脚本）。"
        ),
    )
    import_parser.add_argument(
        "--ui-export-record",
        dest="ui_export_record_id",
        default="",
        help=(
            "可选：节点图写回时使用指定 UI 导出记录绑定的 ui_guid_registry 快照（record_id 或 latest）。"
            "留空=不指定（使用当前 ui_guid_registry）。"
        ),
    )

    import_parser.add_argument(
        "--ui-widget-templates-mode",
        dest="ui_widget_templates_mode",
        choices=["merge", "overwrite"],
        default="",
        help="UI控件模板写回模式：merge=保留旧的并补齐缺失；overwrite=覆盖同 GUID（默认跟随 --mode）",
    )
    import_parser.add_argument(
        "--ui-auto-sync-custom-variables",
        dest="ui_auto_sync_custom_variables",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "是否自动同步写入 UI 引用到的实体自定义变量（关卡/玩家）。"
            "仅在写回 UI 且走 workbench bundle 写回时生效；默认开启。"
        ),
    )
    import_parser.add_argument(
        "--signals-template-gil",
        dest="signals_template_gil_file",
        default="",
        help=(
            "可选：信号导入用模板 .gil（需包含至少一个“无参信号”作为 node_def 基底）。"
            "留空则由下游按 base → bootstrap → 内置默认模板 → cache 自动选择可用样本。"
        ),
    )
    import_parser.add_argument(
        "--signals-bootstrap-template-gil",
        dest="signals_bootstrap_template_gil_file",
        default=None,
        help="可选：信号导入自举模板 .gil（当 input_gil 过于空壳时用于补齐 root4/10 基底）",
    )
    import_parser.add_argument(
        "--signals-param-build-mode",
        dest="signals_param_build_mode",
        choices=["semantic", "template"],
        default="semantic",
        help="信号参数口构建模式：semantic=按 type_id 规则构造；template=按模板克隆（需模板覆盖参数类型）",
    )
    import_parser.add_argument(
        "--signals-emit-reserved-placeholder-signal",
        dest="signals_emit_reserved_placeholder_signal",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "当 base `.gil` 没有任何信号且选择 0x6000/0x6080 口径时，是否写入“占位无参信号”（常见名："
            "`新建的没有参数的信号`）。\n"
            "默认关闭（更干净的导出产物）：不写入占位信号 entry，但仍会预留其应占用的 node_def_id/端口块，"
            "避免第一条业务信号误占用保留槽。\n"
            "如需对齐旧样本/对照，请显式开启。"
        ),
    )
    import_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    import_parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    import_parser.add_argument("--report", dest="report_json_file", default=None, help="可选：输出 report.json 路径")
    import_parser.set_defaults(entrypoint=_command_project_import)

    import_ingame_save_structs_parser = project_subparsers.add_parser(
        "import-ingame-save-structs",
        help="将项目存档中的局内存档结构体写回到 .gil（struct_message.field_2.int=2）",
    )
    import_ingame_save_structs_parser.add_argument(
        "--dangerous",
        dest="dangerous",
        action="store_true",
        help="允许运行写回命令（危险写盘，需要你明确确认风险）。",
    )
    import_ingame_save_structs_parser.add_argument(
        "--project-archive",
        dest="project_archive",
        default=None,
        help="项目存档目录路径（优先）",
    )
    import_ingame_save_structs_parser.add_argument(
        "--project-id",
        dest="project_id",
        default=None,
        help="项目存档目录名（与 --project-root 配合）",
    )
    import_ingame_save_structs_parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        help="项目存档根目录（默认自动指向 Graph_Generater/assets/资源库/项目存档）",
    )
    import_ingame_save_structs_parser.add_argument(
        "--mode",
        choices=["merge", "overwrite"],
        default="merge",
        help="merge=同名结构体已存在则跳过；overwrite=同名结构体已存在则覆盖（struct_name 作为匹配键）",
    )
    import_ingame_save_structs_parser.add_argument(
        "--bootstrap-template-gil",
        dest="bootstrap_template_gil_file",
        default=str(default_ingame_save_structs_bootstrap_gil_path()),
        help=(
            "当目标存档的 root4/10/6 为空时，用该 .gil 提供结构体系统模板"
            "（默认 ugc_file_tools/builtin_resources/seeds/ingame_save_structs_bootstrap.gil）"
        ),
    )
    import_ingame_save_structs_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    import_ingame_save_structs_parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    import_ingame_save_structs_parser.add_argument("--report", dest="report_json_file", default=None, help="可选：输出 report.json 路径")
    import_ingame_save_structs_parser.set_defaults(entrypoint=_command_project_import_ingame_save_structs)

    import_basic_structs_parser = project_subparsers.add_parser(
        "import-basic-structs",
        help="将项目存档中的基础结构体写回到 .gil（decoded-json 或 基础结构体/*.py）",
    )
    import_basic_structs_parser.add_argument(
        "--dangerous",
        dest="dangerous",
        action="store_true",
        help="允许运行写回命令（危险写盘，需要你明确确认风险）。",
    )
    import_basic_structs_parser.add_argument(
        "--project-archive",
        dest="project_archive",
        default=None,
        help="项目存档目录路径（优先）",
    )
    import_basic_structs_parser.add_argument(
        "--project-id",
        dest="project_id",
        default=None,
        help="项目存档目录名（与 --project-root 配合）",
    )
    import_basic_structs_parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        help="项目存档根目录（默认自动指向 Graph_Generater/assets/资源库/项目存档）",
    )
    import_basic_structs_parser.add_argument(
        "--mode",
        choices=["merge", "overwrite"],
        default="merge",
        help="merge=同名结构体已存在则跳过；overwrite=同名结构体已存在则覆盖（struct_name 作为匹配键）",
    )
    import_basic_structs_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    import_basic_structs_parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    import_basic_structs_parser.add_argument("--report", dest="report_json_file", default=None, help="可选：输出 report.json 路径")
    import_basic_structs_parser.set_defaults(entrypoint=_command_project_import_basic_structs)

    export_parser = project_subparsers.add_parser(
        "export",
        help="解析 .gil 并导出为 Graph_Generater 可直接打开的项目存档目录（assets/资源库/项目存档/<package_id>）",
    )
    export_parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        help="项目存档根目录（默认自动指向 Graph_Generater/assets/资源库/项目存档）",
    )
    export_parser.add_argument(
        "--project-id",
        dest="project_id",
        default=None,
        help="项目存档目录名（默认使用输入 .gil 文件名推导）",
    )
    export_parser.add_argument(
        "--overwrite",
        dest="overwrite",
        action="store_true",
        help="若目标项目存档目录已存在则删除后重建（危险：会清空整个目录）",
    )
    export_parser.add_argument(
        "--generate-graph-code",
        dest="generate_graph_code",
        action="store_true",
        help="导出后从 节点图/原始解析/pyugc_graphs 生成 Graph_Generater 可识别的 Graph Code（写入 节点图/server 与 节点图/client）",
    )
    export_parser.add_argument(
        "--overwrite-graph-code",
        dest="overwrite_graph_code",
        action="store_true",
        help="生成 Graph Code 时若目标节点图文件已存在则覆盖（默认不覆盖）。",
    )
    export_parser.add_argument(
        "--validate-graph-code",
        dest="validate_graph_code",
        action="store_true",
        help="若启用 --generate-graph-code，则在生成后对该包执行一次校验（用于确保可打开/可验证闭环）。",
    )
    export_parser.add_argument(
        "--set-last-opened",
        dest="set_last_opened",
        action="store_true",
        help="导出后写入 Graph_Generater/app/runtime/package_state.json，将该存档设置为最近打开",
    )
    export_parser.add_argument(
        "--parse-status-root",
        dest="parse_status_root",
        default=None,
        help="解析状态输出根目录（默认 ugc_file_tools/parse_status）",
    )
    export_parser.add_argument(
        "--dtype",
        dest="dtype_path",
        default=None,
        help="dtype.json 路径（默认使用 ugc_file_tools/builtin_resources/dtype/dtype.json）",
    )
    export_parser.add_argument(
        "--enable-dll-dump",
        dest="enable_dll_dump",
        action="store_true",
        help="额外执行一次 dump-json，并从中提取 UI 相关数据（用于导出 UI 控件模板）",
    )
    export_parser.add_argument(
        "--data-min-bytes",
        dest="data_min_bytes",
        type=int,
        default=512,
        help="对 data blob 进行二次解码的最小字节阈值（默认 512）",
    )
    export_parser.add_argument(
        "--generic-scan-min-bytes",
        dest="generic_scan_min_bytes",
        type=int,
        default=256,
        help="通用解码扫描的最小字节阈值（默认 256，会做 utf8 统计与关键字命中定位）",
    )
    export_parser.add_argument(
        "--focus-graph-id",
        dest="focus_graph_id",
        type=int,
        default=None,
        help="可选：定向定位某个节点图/节点ID（例如 1073741832），会额外导出命中 @data 的通用解码结果。",
    )
    export_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    export_parser.set_defaults(entrypoint=_command_project_export_from_gil)


