from __future__ import annotations

from pathlib import Path


def make_export_center_gil_identify_worker_cls(*, QtCore: object):
    """
    延迟定义 QThread（避免模块顶层 import PyQt6）。
    """

    class _Worker(QtCore.QThread):  # type: ignore[misc]
        succeeded = QtCore.pyqtSignal(dict)  # report
        failed = QtCore.pyqtSignal(str)  # message（预留）
        progress_changed = QtCore.pyqtSignal(int, int, str)  # current, total, label

        def __init__(
            self,
            *,
            base_gil_file_path: Path,
            id_ref_gil_file_path: Path | None,
            use_base_as_id_ref_fallback: bool,
            workspace_root: Path,
            package_id: str,
            ui_export_record_id: str | None,
            required_entity_names: frozenset[str],
            required_component_names: frozenset[str],
            required_ui_keys: frozenset[str],
            ui_key_layout_hints_by_key: dict[str, frozenset[str]],
            required_level_custom_variables: list[dict[str, str]],
            scan_ui_placeholder_variables: bool,
            ui_source_dir: Path | None,
            ui_selected_html_stems: list[str],
            parent: object | None = None,
        ) -> None:
            super().__init__(parent)
            self._base_gil_file_path = Path(base_gil_file_path).resolve()
            self._id_ref_gil_file_path = Path(id_ref_gil_file_path).resolve() if id_ref_gil_file_path is not None else None
            self._use_base_as_id_ref_fallback = bool(use_base_as_id_ref_fallback)
            self._workspace_root = Path(workspace_root).resolve()
            self._package_id = str(package_id)
            self._ui_export_record_id = (str(ui_export_record_id).strip() if ui_export_record_id is not None else None)
            self._required_entity_names = frozenset(required_entity_names)
            self._required_component_names = frozenset(required_component_names)
            self._required_ui_keys = frozenset(required_ui_keys)
            self._ui_key_layout_hints_by_key = dict(ui_key_layout_hints_by_key or {})
            self._required_level_custom_variables = [dict(x) for x in list(required_level_custom_variables or [])]
            self._scan_ui_placeholder_variables = bool(scan_ui_placeholder_variables)
            self._ui_source_dir = Path(ui_source_dir).resolve() if ui_source_dir is not None else None
            self._ui_selected_html_stems = [str(x).strip() for x in list(ui_selected_html_stems or []) if str(x).strip() != ""]
            self.setObjectName(f"ExportCenterGilIdentifyWorker:{self._base_gil_file_path.name}")

        def run(self) -> None:
            import json
            from uuid import uuid4

            from ._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

            out_dir = (Path(self._workspace_root).resolve() / "private_extensions" / "ugc_file_tools" / "out").resolve()
            tmp_dir = (out_dir / "_tmp_cli").resolve()
            tmp_dir.mkdir(parents=True, exist_ok=True)

            manifest_file = (tmp_dir / f"export_center_identify_manifest_{uuid4().hex[:10]}.json").resolve()
            report_file = (tmp_dir / f"export_center_identify_report_{uuid4().hex[:10]}.json").resolve()

            manifest = {
                "base_gil_file_path": str(Path(self._base_gil_file_path).resolve()),
                "id_ref_gil_file_path": (str(Path(self._id_ref_gil_file_path).resolve()) if self._id_ref_gil_file_path is not None else None),
                "use_base_as_id_ref_fallback": bool(self._use_base_as_id_ref_fallback),
                "workspace_root": str(Path(self._workspace_root).resolve()),
                "package_id": str(self._package_id),
                "ui_export_record_id": (str(self._ui_export_record_id) if self._ui_export_record_id is not None else None),
                "required_entity_names": sorted(list(self._required_entity_names), key=lambda t: str(t).casefold()),
                "required_component_names": sorted(list(self._required_component_names), key=lambda t: str(t).casefold()),
                "required_ui_keys": sorted(list(self._required_ui_keys), key=lambda t: str(t).casefold()),
                "ui_key_layout_hints_by_key": {
                    str(k): sorted(list(v), key=lambda t: str(t).casefold())
                    for k, v in dict(self._ui_key_layout_hints_by_key or {}).items()
                },
                "required_level_custom_variables": [dict(x) for x in list(self._required_level_custom_variables or [])],
                "scan_ui_placeholder_variables": bool(self._scan_ui_placeholder_variables),
                "ui_source_dir": (str(Path(self._ui_source_dir).resolve()) if self._ui_source_dir is not None else None),
                "ui_selected_html_stems": list(self._ui_selected_html_stems),
            }
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            argv: list[str] = [
                "tool",
                "export_center_identify_gil_backfill_comparison",
                "--manifest",
                str(manifest_file),
                "--report",
                str(report_file),
            ]
            command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv)
            result = run_cli_with_progress(
                command=command,
                cwd=Path(self._workspace_root),
                on_progress=lambda current, total, label: self.progress_changed.emit(int(current), int(total), str(label)),
                stderr_tail_max_lines=240,
            )
            if int(result.exit_code) != 0:
                tail = [str(x) for x in list(result.stderr_tail)[-120:] if str(x).strip() != ""]
                tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                self.failed.emit(f"回填识别失败：子进程退出码={int(result.exit_code)}\n\n{tail_text}")
                return

            if not report_file.is_file():
                raise FileNotFoundError(str(report_file))
            report = json.loads(report_file.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise TypeError("identify report must be dict")
            self.succeeded.emit(dict(report))

    return _Worker


__all__ = ["make_export_center_gil_identify_worker_cls"]

