from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any, Optional


def _ensure_import_roots() -> tuple[Path, Path, Path]:
    """
    让该脚本可在任意工作目录下稳定运行：
    - workspace_root：import engine/app
    - private_extensions：import ugc_file_tools
    - plugin_root：import ui_workbench_backend
    """
    plugin_root = Path(__file__).resolve().parent
    private_extensions_root = plugin_root.parent
    workspace_root = private_extensions_root.parent

    # 插入顺序：先插 plugin_root，再插 private_extensions，再插 workspace_root，
    # 使得 workspace_root 最终位于 sys.path[0]（优先解析主程序代码，如 engine/app）。
    for import_root in (plugin_root, private_extensions_root, workspace_root):
        root_text = str(import_root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
    return plugin_root, private_extensions_root, workspace_root


def _parse_optional_positive_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and int(value) > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        if parsed > 0:
            return int(parsed)
    return None


def _parse_canvas_component(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        fv = float(v)
        return fv if fv > 0 else None
    if isinstance(v, str) and v.strip().isdigit():
        fv = float(int(v.strip()))
        return fv if fv > 0 else None
    return None


def _parse_pc_canvas_size_override(node: Any) -> Optional[tuple[float, float]]:
    if not isinstance(node, dict):
        return None
    fx = _parse_canvas_component(node.get("x", None))
    fy = _parse_canvas_component(node.get("y", None))
    if fx is None or fy is None:
        return None
    return (float(fx), float(fy))


def _decode_base_gil_upload(payload: dict) -> tuple[Optional[bytes], Optional[str]]:
    base_gil_upload = payload.get("base_gil_upload", None)
    if not isinstance(base_gil_upload, dict):
        return None, None
    file_name = str(base_gil_upload.get("file_name", "") or "").strip() or None
    base64_text = str(base_gil_upload.get("content_base64", "") or "").strip()
    if not base64_text:
        return None, file_name
    return base64.b64decode(base64_text), file_name


def _attach_dummy_main_window_if_needed(bridge: object, package_id: str) -> None:
    package_id_text = str(package_id or "").strip()
    if package_id_text == "" or package_id_text in {"global_view", "unclassified_view"}:
        return

    class _DummyPackageController:
        def __init__(self, package_id: str) -> None:
            self.current_package_id = str(package_id)
            self.current_package = None

    class _DummyMainWindow:
        def __init__(self, package_id: str) -> None:
            self.package_controller = _DummyPackageController(package_id)

    attach = getattr(bridge, "attach_main_window", None)
    if callable(attach):
        attach(_DummyMainWindow(package_id_text))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="UI Workbench export job runner (subprocess)")
    parser.add_argument("--job", dest="job_json_file", required=True, help="输入 job.json（包含 command/package_id/payload）")
    parser.add_argument("--report", dest="report_json_file", required=True, help="输出 report.json（成功才会写入）")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    plugin_root, _, workspace_root = _ensure_import_roots()

    job_path = Path(args.job_json_file).resolve()
    if not job_path.is_file():
        raise FileNotFoundError(str(job_path))
    job = json.loads(job_path.read_text(encoding="utf-8"))
    if not isinstance(job, dict):
        raise TypeError("job root must be dict")

    command = str(job.get("command", "") or "").strip()
    if command not in {"export_gil", "export_gia"}:
        raise ValueError(f"unsupported command: {command!r}")

    package_id = str(job.get("package_id", "") or "").strip()

    payload = job.get("payload", None)
    if not isinstance(payload, dict):
        raise TypeError("job.payload must be dict")

    from ui_workbench_backend.bridge import _UiWorkbenchBridge

    bridge = _UiWorkbenchBridge(workspace_root=Path(workspace_root), workbench_dir=Path(plugin_root))
    _attach_dummy_main_window_if_needed(bridge, package_id)

    base_gil_upload_bytes, base_gil_upload_file_name = _decode_base_gil_upload(payload)
    base_gil_path = str(payload.get("base_gil_path", "") or "").strip() or None

    verify = payload.get("verify_with_dll_dump", True)
    verify_bool = bool(verify) if isinstance(verify, bool) else True

    if command == "export_gil":
        custom_variables_only = (
            bool(payload.get("custom_variables_only")) if isinstance(payload.get("custom_variables_only"), bool) else False
        )
        save_button_groups_as_custom_templates = (
            bool(payload.get("save_button_groups_as_custom_templates"))
            if isinstance(payload.get("save_button_groups_as_custom_templates"), bool)
            else False
        )

        bundles_node = payload.get("bundles", None)
        if isinstance(bundles_node, list):
            result = getattr(bridge, "export_gil_from_bundle_payloads")(
                bundles=list(bundles_node),
                verify_with_dll_dump=bool(verify_bool),
                base_gil_upload_bytes=base_gil_upload_bytes,
                base_gil_upload_file_name=base_gil_upload_file_name,
                base_gil_path=base_gil_path,
                save_button_groups_as_custom_templates=save_button_groups_as_custom_templates,
            )
            result_dict = {
                "output_gil_path": getattr(result, "output_gil_path", ""),
                "output_file_name": getattr(result, "output_file_name", ""),
                "report": getattr(result, "report", {}),
                "download_token": getattr(result, "download_token", ""),
            }
        else:
            layout_name = str(payload.get("layout_name", "") or "")
            bundle = payload.get("bundle", None)
            if not isinstance(bundle, dict):
                raise TypeError("payload.bundle must be dict")

            if custom_variables_only:
                result = getattr(bridge, "export_gil_custom_variables_only_from_bundle_payload")(
                    layout_name=layout_name,
                    bundle_payload=bundle,
                    base_gil_upload_bytes=base_gil_upload_bytes,
                    base_gil_upload_file_name=base_gil_upload_file_name,
                    base_gil_path=base_gil_path,
                )
            else:
                result = getattr(bridge, "export_gil_from_bundle_payload")(
                    layout_name=layout_name,
                    bundle_payload=bundle,
                    verify_with_dll_dump=bool(verify_bool),
                    base_gil_upload_bytes=base_gil_upload_bytes,
                    base_gil_upload_file_name=base_gil_upload_file_name,
                    base_gil_path=base_gil_path,
                    target_layout_guid=_parse_optional_positive_int(payload.get("target_layout_guid", None)),
                    pc_canvas_size_override=_parse_pc_canvas_size_override(payload.get("pc_canvas_size", None)),
                    save_button_groups_as_custom_templates=save_button_groups_as_custom_templates,
                )

            result_dict = {
                "output_gil_path": getattr(result, "output_gil_path", ""),
                "output_file_name": getattr(result, "output_file_name", ""),
                "report": getattr(result, "report", {}),
                "download_token": getattr(result, "download_token", ""),
            }
    else:
        # export_gia
        layout_name = str(payload.get("layout_name", "") or "")
        bundle = payload.get("bundle", None)
        if not isinstance(bundle, dict):
            raise TypeError("payload.bundle must be dict")
        game_version = str(payload.get("game_version", "") or "").strip() or "6.3.0"

        result = getattr(bridge, "export_gia_from_bundle_payload")(
            layout_name=layout_name,
            bundle_payload=bundle,
            verify_with_dll_dump=bool(verify_bool),
            base_gil_upload_bytes=base_gil_upload_bytes,
            base_gil_upload_file_name=base_gil_upload_file_name,
            base_gil_path=base_gil_path,
            target_layout_guid=_parse_optional_positive_int(payload.get("target_layout_guid", None)),
            pc_canvas_size_override=_parse_pc_canvas_size_override(payload.get("pc_canvas_size", None)),
            game_version=game_version,
        )
        result_dict = {
            "output_gia_path": getattr(result, "output_gia_path", ""),
            "output_gil_path": getattr(result, "output_gil_path", ""),
            "output_file_name": getattr(result, "output_file_name", ""),
            "report": getattr(result, "report", {}),
            "download_token": getattr(result, "download_token", ""),
        }

    report_path = Path(args.report_json_file).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result_dict, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

