from __future__ import annotations

from pathlib import Path


UI_WORKBENCH_PC_CANVAS_SIZE = "1920x1080"
_TMP_NAME_UUID_HEX_LEN = 10
_STDERR_TAIL_MAX_LINES = 240
_STDERR_TAIL_DISPLAY_LINES = 120


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

        def _maybe_update_ui_workbench_bundles_for_identify(self) -> bool:
            """在识别前按需更新所选 UI HTML 对应的 Workbench bundle。"""

            if self._ui_source_dir is None or not self._ui_selected_html_stems:
                return True

            import importlib.util

            from ._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress
            from .export_center.dialog_actions_parts.constants import (
                UI_BUNDLE_JSON_SUFFIX,
                UI_BUNDLE_MODE_KEY_BYTES,
                UI_BUNDLE_MODE_REQUIRED_BYTES,
                UI_BUNDLE_MODE_SCAN_WINDOW_BYTES,
                UI_HTML_FILE_SUFFIXES,
            )

            ui_dir = Path(self._ui_source_dir).resolve()
            bundle_dir = (ui_dir / "__workbench_out__").resolve()

            missing_html_stems: list[str] = []
            need_update_htmls: list[Path] = []

            for stem0 in list(self._ui_selected_html_stems):
                stem = str(stem0 or "").strip()
                if stem == "":
                    continue

                html_path: Path | None = None
                for ext in UI_HTML_FILE_SUFFIXES:
                    cand = (ui_dir / f"{stem}{ext}").resolve()
                    if cand.is_file():
                        html_path = Path(cand)
                        break
                if html_path is None:
                    missing_html_stems.append(str(stem))
                    continue

                expected_bundle = (bundle_dir / f"{stem}{UI_BUNDLE_JSON_SUFFIX}").resolve()
                if not expected_bundle.is_file():
                    need_update_htmls.append(Path(html_path))
                    continue

                html_mtime_ns = int(Path(html_path).stat().st_mtime_ns)
                bundle_mtime_ns = int(Path(expected_bundle).stat().st_mtime_ns)
                stale_by_mtime = bool(html_mtime_ns > bundle_mtime_ns)
                stale_by_mode = False
                if not bool(stale_by_mtime):
                    raw = Path(expected_bundle).read_bytes()
                    idx = int(raw.find(UI_BUNDLE_MODE_KEY_BYTES))
                    if idx < 0:
                        stale_by_mode = True
                    else:
                        window = raw[idx : idx + int(UI_BUNDLE_MODE_SCAN_WINDOW_BYTES)]
                        stale_by_mode = UI_BUNDLE_MODE_REQUIRED_BYTES not in window

                if bool(stale_by_mtime) or bool(stale_by_mode):
                    need_update_htmls.append(Path(html_path))

            if missing_html_stems:
                lines = ["回填识别失败：所选 UI 页面不存在对应 HTML 文件："]
                lines.extend([f"- {x}" for x in missing_html_stems])
                self.failed.emit("\n".join(lines).strip())
                return False

            seen_cf: set[str] = set()
            need_update_htmls_dedup: list[Path] = []
            for p in list(need_update_htmls):
                rp = Path(p).resolve()
                k = str(rp).casefold()
                if k in seen_cf:
                    continue
                seen_cf.add(k)
                need_update_htmls_dedup.append(rp)

            if not need_update_htmls_dedup:
                return True

            if importlib.util.find_spec("playwright") is None:
                base_lines: list[str] = []
                base_lines.append("回填识别失败：检测到所选 UI 页面对应的 Workbench bundle 缺失或过期，但当前环境缺少 Playwright，无法自动更新。")
                base_lines.append("识别 UIKey 时只读取：管理配置/UI源码/__workbench_out__/*.ui_bundle.json")
                base_lines.append("不会直接读取：管理配置/UI源码/*.html")
                base_lines.append("")
                base_lines.append("解决方式（任选其一）：")
                base_lines.append("- 在 UI Workbench 手动导出/保存 bundle（更新 __workbench_out__）后再识别")
                base_lines.append("- 或安装依赖：`pip install playwright` 并运行 `playwright install chromium`")
                base_lines.append("")
                base_lines.append("需要更新的 HTML：")
                base_lines.extend([f"- {str(p)}" for p in need_update_htmls_dedup])
                self.failed.emit("\n".join(base_lines).strip())
                return False

            project_root = ui_dir.parent.parent.resolve()
            argv_update_ui: list[str] = [
                "tool",
                "export_ui_workbench_bundles_from_html",
                "--project-root",
                str(Path(project_root).resolve()),
                "--pc-canvas-size",
                str(UI_WORKBENCH_PC_CANVAS_SIZE),
            ]
            for p in list(need_update_htmls_dedup):
                argv_update_ui.extend(["--html", str(Path(p).resolve())])

            command_ui = build_run_ugc_file_tools_command(
                workspace_root=Path(self._workspace_root),
                argv=argv_update_ui,
            )
            result_ui = run_cli_with_progress(
                command=command_ui,
                cwd=Path(self._workspace_root),
                on_progress=lambda current, total, label: self.progress_changed.emit(
                    int(current),
                    int(total),
                    f"更新UI bundle：{label}",
                ),
                stderr_tail_max_lines=int(_STDERR_TAIL_MAX_LINES),
            )
            if int(result_ui.exit_code) != 0:
                tail = [str(x) for x in list(result_ui.stderr_tail)[-int(_STDERR_TAIL_DISPLAY_LINES) :] if str(x).strip() != ""]
                tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                self.failed.emit(f"回填识别失败（更新UI bundle）：子进程退出码={int(result_ui.exit_code)}\n\n{tail_text}")
                return False

            return True

        def run(self) -> None:
            import json
            from uuid import uuid4

            from ._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

            out_dir = (Path(self._workspace_root).resolve() / "private_extensions" / "ugc_file_tools" / "out").resolve()
            tmp_dir = (out_dir / "_tmp_cli").resolve()
            tmp_dir.mkdir(parents=True, exist_ok=True)

            manifest_file = (tmp_dir / f"export_center_identify_manifest_{uuid4().hex[:_TMP_NAME_UUID_HEX_LEN]}.json").resolve()
            report_file = (tmp_dir / f"export_center_identify_report_{uuid4().hex[:_TMP_NAME_UUID_HEX_LEN]}.json").resolve()

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

            if not self._maybe_update_ui_workbench_bundles_for_identify():
                return

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
                stderr_tail_max_lines=int(_STDERR_TAIL_MAX_LINES),
            )
            if int(result.exit_code) != 0:
                tail = [str(x) for x in list(result.stderr_tail)[-int(_STDERR_TAIL_DISPLAY_LINES) :] if str(x).strip() != ""]
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

