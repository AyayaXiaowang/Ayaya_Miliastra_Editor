from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .plans import ImportGiaPlan, ImportGilPlan, ImportGilSelectedPlan


DATA_BLOB_MIN_BYTES_FOR_DECODE = 512
GENERIC_SCAN_MIN_BYTES = 256
GIA_IMPORT_TOTAL_STEPS = 3
GIA_DEFAULT_INSTANCES_MODE = "decorations_carrier"


def _safe_dict(obj: object) -> dict[str, object]:
    """将对象转换为可序列化的 dict 用于 UI 展示。"""
    if isinstance(obj, dict):
        return dict(obj)
    return {"value": repr(obj)}


def _safe_exception_text(exc: BaseException) -> str:
    """将异常格式化为可复制的文本。"""
    import traceback

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return tb.strip() if tb.strip() else f"{type(exc).__name__}: {exc}"


class GilImportWorker:
    """在后台线程执行 `.gil` 导入 pipeline 并上报进度。"""

    def __init__(self, *, QtCore: Any, plan: ImportGilPlan, workspace_root: Path, package_index_manager: object) -> None:
        """初始化 `.gil` 导入 worker。"""
        self._QtCore = QtCore
        self._plan = plan
        self._workspace_root = Path(workspace_root).resolve()
        self._package_index_manager = package_index_manager

        self.QThread = QtCore.QThread
        self.pyqtSignal = QtCore.pyqtSignal

        class _Worker(QtCore.QThread):
            progress_changed = QtCore.pyqtSignal(int, int, str)
            succeeded = QtCore.pyqtSignal(object)
            failed = QtCore.pyqtSignal(str)

            def __init__(self, outer: "GilImportWorker") -> None:
                """保存外部上下文以便在 run 中调用。"""
                super().__init__()
                self._outer = outer

            def run(self) -> None:
                """执行 `.gil` 导入并捕获异常用于 UI 展示。"""
                try:
                    from ugc_file_tools.pipelines.gil_to_project_archive import (
                        GilToProjectArchivePlan,
                        run_gil_to_project_archive,
                    )

                    ensure_structure = getattr(self._outer._package_index_manager, "ensure_package_directory_structure", None)
                    if not callable(ensure_structure):
                        raise RuntimeError("PackageIndexManager 缺少 ensure_package_directory_structure，无法补齐目录结构")

                    report = run_gil_to_project_archive(
                        plan=GilToProjectArchivePlan(
                            input_gil_file_path=Path(self._outer._plan.input_gil_path),
                            output_package_root=Path(self._outer._plan.output_package_root),
                            package_id=str(self._outer._plan.package_id),
                            enable_dll_dump=bool(self._outer._plan.enable_dll_dump),
                            data_blob_min_bytes_for_decode=int(DATA_BLOB_MIN_BYTES_FOR_DECODE),
                            generic_scan_min_bytes=int(GENERIC_SCAN_MIN_BYTES),
                            focus_graph_id=None,
                            ensure_package_structure_fn=ensure_structure,
                            generate_graph_code=bool(self._outer._plan.generate_graph_code),
                            overwrite_graph_code=bool(self._outer._plan.overwrite_existing),
                            validate_graph_code_after_generate=bool(self._outer._plan.validate_after_generate),
                            graph_generater_root_for_validation=Path(self._outer._workspace_root),
                            set_last_opened=False,
                        ),
                        progress_cb=lambda current, total, label: self.progress_changed.emit(int(current), int(total), str(label)),
                    )
                    payload = {"kind": "gil_full", "plan": asdict(self._outer._plan), "report": _safe_dict(report)}
                    self.succeeded.emit(payload)
                except BaseException as exc:
                    self.failed.emit(_safe_exception_text(exc))

        self.thread = _Worker(self)


class GilSelectedImportWorker:
    """在后台线程执行“选择性 `.gil` 导入” pipeline 并上报进度。"""

    def __init__(
        self,
        *,
        QtCore: Any,
        plan: ImportGilSelectedPlan,
        workspace_root: Path,
        package_index_manager: object,
    ) -> None:
        """初始化“选择性 `.gil` 导入” worker。"""
        self._QtCore = QtCore
        self._plan = plan
        self._workspace_root = Path(workspace_root).resolve()
        self._package_index_manager = package_index_manager

        class _Worker(QtCore.QThread):
            progress_changed = QtCore.pyqtSignal(int, int, str)
            succeeded = QtCore.pyqtSignal(object)
            failed = QtCore.pyqtSignal(str)

            def __init__(self, outer: "GilSelectedImportWorker") -> None:
                """保存外部上下文以便在 run 中调用。"""
                super().__init__()
                self._outer = outer

            def run(self) -> None:
                """执行选择性导入并捕获异常用于 UI 展示。"""
                try:
                    from ugc_file_tools.pipelines.gil_to_project_archive import (
                        GilToProjectArchivePlan,
                        run_gil_to_project_archive,
                    )

                    ensure_structure = getattr(self._outer._package_index_manager, "ensure_package_directory_structure", None)
                    if not callable(ensure_structure):
                        raise RuntimeError("PackageIndexManager 缺少 ensure_package_directory_structure，无法补齐目录结构")

                    report = run_gil_to_project_archive(
                        plan=GilToProjectArchivePlan(
                            input_gil_file_path=Path(self._outer._plan.input_gil_path),
                            output_package_root=Path(self._outer._plan.output_package_root),
                            package_id=str(self._outer._plan.package_id),
                            enable_dll_dump=bool(self._outer._plan.enable_dll_dump),
                            data_blob_min_bytes_for_decode=int(DATA_BLOB_MIN_BYTES_FOR_DECODE),
                            generic_scan_min_bytes=int(GENERIC_SCAN_MIN_BYTES),
                            focus_graph_id=None,
                            selected_node_graph_id_ints=list(self._outer._plan.selected_node_graph_id_ints),
                            export_raw_pyugc_dump=bool(self._outer._plan.export_raw_pyugc_dump),
                            export_node_graphs=bool(self._outer._plan.export_node_graphs),
                            export_templates=bool(self._outer._plan.export_templates),
                            export_instances=bool(self._outer._plan.export_instances),
                            export_combat_presets=bool(self._outer._plan.export_combat_presets),
                            export_section15=bool(self._outer._plan.export_section15),
                            export_struct_definitions=bool(self._outer._plan.export_struct_definitions),
                            export_signals=bool(self._outer._plan.export_signals),
                            export_data_blobs=bool(self._outer._plan.export_data_blobs),
                            export_decoded_dtype_type3=bool(self._outer._plan.export_decoded_dtype_type3),
                            export_decoded_generic=bool(self._outer._plan.export_decoded_generic),
                            ensure_package_structure_fn=ensure_structure,
                            generate_graph_code=bool(self._outer._plan.generate_graph_code),
                            overwrite_graph_code=bool(self._outer._plan.overwrite_existing),
                            validate_graph_code_after_generate=bool(self._outer._plan.validate_after_generate),
                            graph_generater_root_for_validation=Path(self._outer._workspace_root),
                            set_last_opened=False,
                        ),
                        progress_cb=lambda current, total, label: self.progress_changed.emit(int(current), int(total), str(label)),
                    )
                    payload = {"kind": "gil_selected", "plan": asdict(self._outer._plan), "report": _safe_dict(report)}
                    self.succeeded.emit(payload)
                except BaseException as exc:
                    self.failed.emit(_safe_exception_text(exc))

        self.thread = _Worker(self)


class GiaImportWorker:
    """在后台线程执行 `.gia` 导入 pipeline 并上报进度。"""

    def __init__(self, *, QtCore: Any, plan: ImportGiaPlan, package_index_manager: object) -> None:
        """初始化 `.gia` 导入 worker。"""
        self._QtCore = QtCore
        self._plan = plan
        self._package_index_manager = package_index_manager

        class _Worker(QtCore.QThread):
            progress_changed = QtCore.pyqtSignal(int, int, str)
            succeeded = QtCore.pyqtSignal(object)
            failed = QtCore.pyqtSignal(str)

            def __init__(self, outer: "GiaImportWorker") -> None:
                """保存外部上下文以便在 run 中调用。"""
                super().__init__()
                self._outer = outer

            def run(self) -> None:
                """执行 `.gia` 导入并捕获异常用于 UI 展示。"""
                try:
                    total_steps = int(GIA_IMPORT_TOTAL_STEPS)
                    self.progress_changed.emit(0, total_steps, "准备导入 .gia…")

                    output_root = Path(self._outer._plan.output_package_root).resolve()
                    if not output_root.exists():
                        output_root.mkdir(parents=True, exist_ok=True)

                    kind = str(self._outer._plan.import_kind or "").strip()
                    self.progress_changed.emit(1, total_steps, "正在导入 .gia → 项目存档…")

                    if kind == "templates_instances":
                        from ugc_file_tools.pipelines.gia_templates_and_instances_to_project_archive import (
                            ImportGiaTemplatesAndInstancesPlan,
                            run_import_gia_templates_and_instances_to_project_archive,
                        )

                        report = run_import_gia_templates_and_instances_to_project_archive(
                            plan=ImportGiaTemplatesAndInstancesPlan(
                                input_gia_file=Path(self._outer._plan.input_gia_path),
                                project_archive_path=Path(output_root),
                                overwrite=bool(self._outer._plan.overwrite_existing),
                                decode_max_depth=int(self._outer._plan.decode_max_depth),
                                skip_templates=not bool(self._outer._plan.import_templates),
                                skip_instances=not bool(self._outer._plan.import_instances),
                                instances_mode=str(self._outer._plan.instances_mode or str(GIA_DEFAULT_INSTANCES_MODE)),
                            )
                        )
                    elif kind == "player_template":
                        from ugc_file_tools.pipelines.player_template_gia_to_project_archive import (
                            ImportPlayerTemplateGiaPlan,
                            run_import_player_template_gia_to_project_archive,
                        )

                        report = run_import_player_template_gia_to_project_archive(
                            plan=ImportPlayerTemplateGiaPlan(
                                input_gia_file=Path(self._outer._plan.input_gia_path),
                                project_archive_path=Path(output_root),
                                overwrite=bool(self._outer._plan.overwrite_existing),
                                output_variable_file_id="",
                                output_variable_file_name="",
                                output_template_id="",
                            )
                        )
                    elif kind == "node_graphs":
                        from ugc_file_tools.pipelines.gia_node_graphs_to_project_archive import (
                            ImportGiaNodeGraphsPlan,
                            run_import_gia_node_graphs_to_project_archive,
                        )

                        report = run_import_gia_node_graphs_to_project_archive(
                            plan=ImportGiaNodeGraphsPlan(
                                input_gia_file=Path(self._outer._plan.input_gia_path),
                                project_archive_path=Path(output_root),
                                package_id=str(self._outer._plan.package_id),
                                overwrite_graph_code=bool(self._outer._plan.overwrite_existing),
                                check_header=False,
                                decode_max_depth=int(self._outer._plan.decode_max_depth),
                                validate_after_import=bool(self._outer._plan.validate_after_import),
                                set_last_opened=False,
                            )
                        )
                    else:
                        raise ValueError(f"未知的 import_kind：{kind!r}")

                    self.progress_changed.emit(2, total_steps, "正在补齐项目存档目录骨架…")
                    ensure_structure = getattr(self._outer._package_index_manager, "ensure_package_directory_structure", None)
                    if not callable(ensure_structure):
                        raise RuntimeError("PackageIndexManager 缺少 ensure_package_directory_structure，无法补齐目录结构")
                    ensure_structure(str(self._outer._plan.package_id))

                    self.progress_changed.emit(3, total_steps, "完成")
                    payload = {"kind": "gia", "plan": asdict(self._outer._plan), "report": _safe_dict(report)}
                    self.succeeded.emit(payload)
                except BaseException as exc:
                    self.failed.emit(_safe_exception_text(exc))

        self.thread = _Worker(self)


class GilScanGraphsWorker:
    """在后台线程分析 `.gil` 的节点图清单并返回列表。"""

    def __init__(self, *, QtCore: Any, input_gil: Path) -> None:
        """初始化节点图清单分析 worker。"""
        self._QtCore = QtCore
        self._input_gil = Path(input_gil).resolve()

        class _Worker(QtCore.QThread):
            succeeded = QtCore.pyqtSignal(object)
            failed = QtCore.pyqtSignal(str)

            def __init__(self, outer: "GilScanGraphsWorker") -> None:
                """保存外部上下文以便在 run 中调用。"""
                super().__init__()
                self._outer = outer

            def run(self) -> None:
                """扫描 `.gil` 并捕获异常用于 UI 展示。"""
                try:
                    from ugc_file_tools.gil_package_exporter.node_graph_listing import list_gil_node_graphs
                    from ugc_file_tools.gil_package_exporter.paths import resolve_default_dtype_path

                    dtype = Path(resolve_default_dtype_path()).resolve()
                    graphs = list_gil_node_graphs(input_gil_file_path=Path(self._outer._input_gil), dtype_path=dtype)
                    self.succeeded.emit(graphs)
                except BaseException as exc:
                    self.failed.emit(_safe_exception_text(exc))

        self.thread = _Worker(self)

