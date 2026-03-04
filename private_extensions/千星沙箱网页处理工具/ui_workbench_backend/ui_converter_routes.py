from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from .export_job_runner import run_ui_workbench_export_job_in_subprocess
from .http_utils import (
    get_bridge_or_503_json,
    get_bridge_or_send_error,
    read_request_body_bytes,
    read_request_json_object,
    send_json,
)


def handle_ui_converter_get(*, handler: object, bridge: object | None, path: str, query_text: str) -> bool:
    if path == "/api/ui_converter/status":
        _handle_status(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/base_gil_cache":
        _handle_base_gil_cache_get(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/download_gil":
        _handle_download_gil(handler=handler, bridge=bridge, query_text=query_text)
        return True
    if path == "/api/ui_converter/download_gia":
        _handle_download_gia(handler=handler, bridge=bridge, query_text=query_text)
        return True
    if path == "/api/ui_converter/ui_source_catalog":
        _handle_ui_source_catalog(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/ui_source":
        _handle_ui_source_get(handler=handler, bridge=bridge, query_text=query_text)
        return True
    if path == "/api/ui_converter/ui_source_raw":
        _handle_ui_source_raw(handler=handler, bridge=bridge, query_text=query_text)
        return True
    if path == "/api/ui_converter/variable_catalog":
        _handle_variable_catalog(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/ui_catalog":
        _handle_ui_catalog(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/ui_layout":
        _handle_ui_layout(handler=handler, bridge=bridge, query_text=query_text)
        return True
    if path == "/api/ui_converter/ui_template":
        _handle_ui_template(handler=handler, bridge=bridge, query_text=query_text)
        return True
    return False


def handle_ui_converter_post(*, handler: object, bridge: object | None, path: str) -> bool:
    if path == "/api/ui_converter/base_gil_cache":
        _handle_base_gil_cache_post(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/import_ui_page":
        _handle_import_ui_page(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/import_layout":
        _handle_import_layout(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/export_gil":
        _handle_export_gil(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/export_gia":
        _handle_export_gia(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/import_variable_defaults":
        _handle_import_variable_defaults(handler=handler, bridge=bridge)
        return True
    if path == "/api/ui_converter/ui_source":
        _handle_ui_source_post(handler=handler, bridge=bridge)
        return True
    return False


# ------------------------------------------------------------------ api handlers
def _handle_status(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    send_json(handler, getattr(b, "get_status_payload")(), status=200)


def _handle_base_gil_cache_get(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    loaded = getattr(b, "try_load_ui_preview_base_gil_cache")()
    if loaded is None:
        getattr(handler, "send_error")(404, "base gil cache not found")
        return
    meta, data = loaded
    name = str((meta or {}).get("file_name") or "base.gil")
    last_modified_ms = int((meta or {}).get("last_modified_ms") or 0)
    name_b64 = base64.b64encode(name.encode("utf-8")).decode("ascii")
    body = bytes(data or b"")
    getattr(handler, "send_response")(200)
    getattr(handler, "send_header")("Content-Type", "application/octet-stream")
    getattr(handler, "send_header")("Content-Length", str(len(body)))
    getattr(handler, "send_header")("Cache-Control", "no-store")
    getattr(handler, "send_header")("X-Ui-Base-Gil-Name-B64", name_b64)
    getattr(handler, "send_header")("X-Ui-Base-Gil-Last-Modified", str(last_modified_ms))
    getattr(handler, "end_headers")()
    getattr(getattr(handler, "wfile"), "write")(body)


def _handle_base_gil_cache_post(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    raw = read_request_body_bytes(handler)

    name_b64 = str(getattr(getattr(handler, "headers", None), "get", lambda *_a, **_k: "")("X-Ui-Base-Gil-Name-B64", "") or "").strip()
    file_name = base64.b64decode(name_b64).decode("utf-8") if name_b64 else "base.gil"
    lm_text = str(getattr(getattr(handler, "headers", None), "get", lambda *_a, **_k: "")("X-Ui-Base-Gil-Last-Modified", "") or "").strip()
    last_modified_ms = int(lm_text) if lm_text.isdigit() else 0

    meta = getattr(b, "save_ui_preview_base_gil_cache")(
        file_name=file_name,
        last_modified_ms=last_modified_ms,
        data=bytes(raw or b""),
    )
    send_json(handler, {"ok": True, "cache": meta}, status=200)


def _handle_ui_catalog(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    send_json(handler, getattr(b, "get_ui_catalog_payload")(), status=200)


def _handle_ui_source_catalog(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    send_json(handler, getattr(b, "get_ui_source_catalog_payload")(), status=200)


def _handle_ui_source_get(*, handler: object, bridge: object | None, query_text: str) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    query = parse_qs(query_text or "")
    scope = (query.get("scope", ["project"])[0] or "").strip()
    rel_path = (query.get("rel_path", [""])[0] or "").strip()
    if not rel_path:
        send_json(handler, {"ok": False, "error": "rel_path is required"}, status=400)
        return
    send_json(handler, getattr(b, "read_ui_source_payload")(scope=scope, rel_path=rel_path), status=200)


def _handle_ui_source_raw(*, handler: object, bridge: object | None, query_text: str) -> None:
    b = get_bridge_or_send_error(handler, bridge, status=503, message="bridge not ready")
    if b is None:
        return
    query = parse_qs(query_text or "")
    scope = (query.get("scope", ["project"])[0] or "").strip()
    rel_path = (query.get("rel_path", [""])[0] or "").strip()
    if not rel_path:
        getattr(handler, "send_error")(400, "rel_path is required")
        return

    payload = getattr(b, "read_ui_source_payload")(scope=scope, rel_path=rel_path)
    html_text = str(payload.get("content") or "")
    body = html_text.encode("utf-8")
    getattr(handler, "send_response")(200)
    getattr(handler, "send_header")("Content-Type", "text/html; charset=utf-8")
    getattr(handler, "send_header")("Content-Length", str(len(body)))
    getattr(handler, "send_header")("Cache-Control", "no-store")
    getattr(handler, "end_headers")()
    getattr(getattr(handler, "wfile"), "write")(body)


def _handle_ui_source_post(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    payload = read_request_json_object(handler)

    rel_path = str(payload.get("rel_path", "") or "").strip()
    content = str(payload.get("content", "") or "")
    if not rel_path:
        send_json(handler, {"ok": False, "error": "rel_path is required"}, status=400)
        return
    send_json(handler, getattr(b, "save_ui_source_payload")(rel_path=rel_path, content=content), status=200)


def _handle_variable_catalog(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    send_json(handler, getattr(b, "get_variable_catalog_payload")(), status=200)


def _handle_import_variable_defaults(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    payload = read_request_json_object(handler)

    source_rel_path = str(payload.get("source_rel_path", "") or "").strip()
    variable_defaults = payload.get("variable_defaults", None)
    if not isinstance(variable_defaults, dict):
        send_json(handler, {"ok": False, "error": "variable_defaults must be object(dict)"}, status=400)
        return

    report = getattr(b, "import_variable_defaults_to_current_project")(
        source_rel_path=source_rel_path,
        variable_defaults=variable_defaults,
    )
    send_json(handler, report, status=200)


def _handle_ui_layout(*, handler: object, bridge: object | None, query_text: str) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    query = parse_qs(query_text or "")
    layout_id = (query.get("layout_id", [""])[0] or "").strip()
    if not layout_id:
        send_json(handler, {"ok": False, "error": "layout_id is required"}, status=400)
        return
    send_json(handler, getattr(b, "get_ui_layout_payload")(layout_id), status=200)


def _handle_ui_template(*, handler: object, bridge: object | None, query_text: str) -> None:
    b = get_bridge_or_503_json(handler, bridge)
    if b is None:
        return
    query = parse_qs(query_text or "")
    template_id = (query.get("template_id", [""])[0] or "").strip()
    if not template_id:
        send_json(handler, {"ok": False, "error": "template_id is required"}, status=400)
        return
    send_json(handler, getattr(b, "get_ui_template_payload")(template_id), status=200)


def _handle_import_ui_page(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    payload = read_request_json_object(handler)

    layout_name = str(payload.get("layout_name", "") or "").strip()
    source_rel_path = str(payload.get("source_rel_path", "") or "").strip()
    bundle = payload.get("bundle", None)

    if not source_rel_path:
        send_json(handler, {"ok": False, "error": "source_rel_path is required"}, status=400)
        return
    if not isinstance(bundle, dict):
        send_json(handler, {"ok": False, "error": "bundle is required"}, status=400)
        return

    raw_templates = bundle.get("templates", None)
    templates_count = 0
    if isinstance(raw_templates, list):
        templates_count = sum(1 for it in raw_templates if isinstance(it, dict))
    elif isinstance(raw_templates, dict):
        templates_count = sum(1 for it in raw_templates.values() if isinstance(it, dict))
    else:
        send_json(handler, {"ok": False, "error": "bundle.templates must be array or object"}, status=400)
        return
    if templates_count <= 0:
        send_json(handler, {"ok": False, "error": "bundle.templates 为空，无法导入（未识别到可导入的控件模板）"}, status=400)
        return

    ok, error = getattr(b, "try_validate_text_placeholders_in_ui_payload")(bundle, autofix_missing_lv_variables=True)
    if not ok:
        send_json(handler, {"ok": False, "error": error}, status=400)
        return

    summary = getattr(b, "import_ui_page_from_bundle_payload")(
        source_rel_path=source_rel_path,
        bundle_payload=bundle,
        layout_name=layout_name,
    )
    send_json(
        handler,
        {
            "ok": True,
            "source_html_relpath": getattr(summary, "source_html_relpath", ""),
            "layout_id": getattr(summary, "layout_id", ""),
            "layout_name": layout_name,
            "template_count": getattr(summary, "template_count", 0),
            "widget_count": getattr(summary, "widget_count", 0),
            "import_mode": "ui_page",
        },
        status=200,
    )


def _handle_import_layout(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    payload = read_request_json_object(handler)

    layout_name = str(payload.get("layout_name", "") or "")
    bundle = payload.get("bundle", None)
    if isinstance(bundle, dict):
        raw_templates = bundle.get("templates", None)
        templates_count = 0
        if isinstance(raw_templates, list):
            templates_count = sum(1 for it in raw_templates if isinstance(it, dict))
        elif isinstance(raw_templates, dict):
            templates_count = sum(1 for it in raw_templates.values() if isinstance(it, dict))
        else:
            send_json(handler, {"ok": False, "error": "bundle.templates must be array or object"}, status=400)
            return
        if templates_count <= 0:
            send_json(handler, {"ok": False, "error": "bundle.templates 为空，无法导入（未识别到可导入的控件模板）"}, status=400)
            return

        ok, error = getattr(b, "try_validate_text_placeholders_in_ui_payload")(bundle, autofix_missing_lv_variables=True)
        if not ok:
            send_json(handler, {"ok": False, "error": error}, status=400)
            return
        result = getattr(b, "import_layout_from_bundle_payload")(layout_name=layout_name, bundle_payload=bundle)
        send_json(
            handler,
            {
                "ok": True,
                "layout_id": getattr(result, "layout_id", ""),
                "layout_name": getattr(result, "layout_name", ""),
                "template_count": getattr(result, "template_count", 0),
                "widget_count": getattr(result, "widget_count", 0),
                "import_mode": "bundle",
            },
            status=200,
        )
        return

    template = payload.get("template", None)
    if not isinstance(template, dict):
        send_json(handler, {"ok": False, "error": "bundle/template is required"}, status=400)
        return

    ok, error = getattr(b, "try_validate_text_placeholders_in_ui_payload")(template, autofix_missing_lv_variables=True)
    if not ok:
        send_json(handler, {"ok": False, "error": error}, status=400)
        return

    result = getattr(b, "import_layout_from_template_payload")(layout_name=layout_name, template_payload=template)
    send_json(
        handler,
        {
            "ok": True,
            "layout_id": getattr(result, "layout_id", ""),
            "layout_name": getattr(result, "layout_name", ""),
            "template_id": getattr(result, "template_id", ""),
            "template_name": getattr(result, "template_name", ""),
            "template_count": getattr(result, "template_count", 0),
            "widget_count": getattr(result, "widget_count", 0),
            "import_mode": "template",
        },
        status=200,
    )


def _handle_export_gil(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    payload = read_request_json_object(handler)

    layout_name = str(payload.get("layout_name", "") or "")
    verify = payload.get("verify_with_dll_dump", True)
    verify_bool = bool(verify) if isinstance(verify, bool) else True
    custom_variables_only = bool(payload.get("custom_variables_only")) if isinstance(payload.get("custom_variables_only"), bool) else False
    save_button_groups_as_custom_templates = (
        bool(payload.get("save_button_groups_as_custom_templates"))
        if isinstance(payload.get("save_button_groups_as_custom_templates"), bool)
        else False
    )
    payload["layout_name"] = str(layout_name)
    payload["verify_with_dll_dump"] = bool(verify_bool)
    payload["custom_variables_only"] = bool(custom_variables_only)
    payload["save_button_groups_as_custom_templates"] = bool(save_button_groups_as_custom_templates)

    base_gil_path = str(payload.get("base_gil_path", "") or "").strip()
    base_gil_upload = payload.get("base_gil_upload", None)
    base_gil_upload_has_content = False
    if isinstance(base_gil_upload, dict):
        base64_text = str(base_gil_upload.get("content_base64", "") or "").strip()
        base_gil_upload_has_content = bool(base64_text)

    if custom_variables_only and (not bool(base_gil_upload_has_content)) and (base_gil_path.strip() == ""):
        send_json(handler, {"ok": False, "error": "custom_variables_only 模式必须先选择一个基底存档 (.gil)。"}, status=400)
        return

    bundles_node = payload.get("bundles", None)
    if isinstance(bundles_node, list):
        if custom_variables_only:
            send_json(handler, {"ok": False, "error": "custom_variables_only 不支持 bundles 批量导出。"}, status=400)
            return

        normalized_bundles: list[dict[str, Any]] = []

        for idx, item in enumerate(bundles_node):
            if not isinstance(item, dict):
                send_json(handler, {"ok": False, "error": f"bundles[{idx}] 必须为 object"}, status=400)
                return
            bundle_payload = item.get("bundle", None)
            if not isinstance(bundle_payload, dict):
                send_json(handler, {"ok": False, "error": f"bundles[{idx}].bundle 必须为 object"}, status=400)
                return

            raw_templates = bundle_payload.get("templates", None)
            templates_count = 0
            if isinstance(raw_templates, list):
                templates_count = sum(1 for it in raw_templates if isinstance(it, dict))
            elif isinstance(raw_templates, dict):
                templates_count = sum(1 for it in raw_templates.values() if isinstance(it, dict))
            elif raw_templates is None:
                templates_count = 0
            else:
                send_json(handler, {"ok": False, "error": f"bundles[{idx}].bundle.templates must be array or object"}, status=400)
                return

            inline_widgets_count = 0
            layout_node = bundle_payload.get("layout")
            if isinstance(layout_node, dict):
                widgets_node = layout_node.get("widgets")
                if isinstance(widgets_node, list):
                    inline_widgets_count = sum(1 for w in widgets_node if isinstance(w, dict))

            if templates_count <= 0 and inline_widgets_count <= 0:
                send_json(
                    handler,
                    {
                        "ok": False,
                        "error": f"bundles[{idx}].bundle 为空：bundle.templates 为空且 layout.widgets 为空（未识别到可处理的 widgets）",
                    },
                    status=400,
                )
                return

            ok, error = getattr(b, "try_validate_text_placeholders_in_ui_payload")(bundle_payload, autofix_missing_lv_variables=True)
            if not ok:
                send_json(handler, {"ok": False, "error": str(error)}, status=400)
                return

            per_layout_name = str(item.get("layout_name", "") or "").strip()
            pc_canvas_size_per = item.get("pc_canvas_size", None)
            normalized_bundles.append(
                {
                    "layout_name": per_layout_name,
                    "bundle": bundle_payload,
                    "pc_canvas_size": pc_canvas_size_per if isinstance(pc_canvas_size_per, dict) else None,
                }
            )

        payload_for_job = dict(payload)
        payload_for_job["bundles"] = normalized_bundles
        run_result = run_ui_workbench_export_job_in_subprocess(bridge=b, command="export_gil", payload=payload_for_job)
        exit_code = int(run_result.get("exit_code") or 0)
        if exit_code != 0:
            tail = [str(x) for x in list(run_result.get("stderr_tail") or [])[-80:] if str(x).strip() != ""]
            tail_text = "\n".join(tail) if tail else "(stderr 为空)"
            send_json(handler, {"ok": False, "error": f"导出失败：子进程退出码={int(exit_code)}\n\n{tail_text}"}, status=500)
            return

        report = run_result.get("report")
        if not isinstance(report, dict):
            raise TypeError("export job report must be dict")

        token = str(report.get("download_token", "") or "").strip()
        out_path = str(report.get("output_gil_path", "") or "").strip()
        if token and out_path:
            m = getattr(b, "_exported_gil_paths_by_token", None)
            if isinstance(m, dict):
                p = Path(out_path).resolve()
                if p.is_file():
                    m[token] = p

        # 记录最近导出 gil（供导出中心/写回对话框的“基底 gil 最近列表”复用）
        try:
            from ugc_file_tools.recent_artifacts import append_recent_exported_gil

            append_recent_exported_gil(
                workspace_root=Path(getattr(b, "_workspace_root")),
                gil_path=str(out_path),
                source="ui_workbench",
                title="ui_workbench:export_gil",
            )
        except Exception:
            pass

        send_json(handler, {"ok": True, **dict(report)}, status=200)
        return

    bundle = payload.get("bundle", None)
    if not isinstance(bundle, dict):
        send_json(handler, {"ok": False, "error": "bundle is required"}, status=400)
        return

    if custom_variables_only:
        run_result = run_ui_workbench_export_job_in_subprocess(bridge=b, command="export_gil", payload=dict(payload))
        exit_code = int(run_result.get("exit_code") or 0)
        if exit_code != 0:
            tail = [str(x) for x in list(run_result.get("stderr_tail") or [])[-80:] if str(x).strip() != ""]
            tail_text = "\n".join(tail) if tail else "(stderr 为空)"
            send_json(handler, {"ok": False, "error": f"导出失败：子进程退出码={int(exit_code)}\n\n{tail_text}"}, status=500)
            return

        report = run_result.get("report")
        if not isinstance(report, dict):
            raise TypeError("export job report must be dict")

        token = str(report.get("download_token", "") or "").strip()
        out_path = str(report.get("output_gil_path", "") or "").strip()
        if token and out_path:
            m = getattr(b, "_exported_gil_paths_by_token", None)
            if isinstance(m, dict):
                p = Path(out_path).resolve()
                if p.is_file():
                    m[token] = p

        # 记录最近导出 gil（供导出中心/写回对话框的“基底 gil 最近列表”复用）
        try:
            from ugc_file_tools.recent_artifacts import append_recent_exported_gil

            append_recent_exported_gil(
                workspace_root=Path(getattr(b, "_workspace_root")),
                gil_path=str(out_path),
                source="ui_workbench",
                title="ui_workbench:export_gil",
            )
        except Exception:
            pass

        send_json(handler, {"ok": True, **dict(report)}, status=200)
        return

    raw_templates = bundle.get("templates", None)
    templates_count = 0
    if isinstance(raw_templates, list):
        templates_count = sum(1 for it in raw_templates if isinstance(it, dict))
    elif isinstance(raw_templates, dict):
        templates_count = sum(1 for it in raw_templates.values() if isinstance(it, dict))
    elif raw_templates is None:
        templates_count = 0
    else:
        send_json(handler, {"ok": False, "error": "bundle.templates must be array or object"}, status=400)
        return

    inline_widgets_count = 0
    layout_node = bundle.get("layout")
    if isinstance(layout_node, dict):
        widgets_node = layout_node.get("widgets")
        if isinstance(widgets_node, list):
            inline_widgets_count = sum(1 for w in widgets_node if isinstance(w, dict))

    if templates_count <= 0 and inline_widgets_count <= 0:
        send_json(
            handler,
            {"ok": False, "error": "bundle.templates 为空，且 layout.widgets 为空，无法导出（未识别到可处理的 widgets）"},
            status=400,
        )
        return

    ok, error = getattr(b, "try_validate_text_placeholders_in_ui_payload")(bundle, autofix_missing_lv_variables=True)
    if not ok:
        send_json(handler, {"ok": False, "error": error}, status=400)
        return

    run_result = run_ui_workbench_export_job_in_subprocess(bridge=b, command="export_gil", payload=dict(payload))
    exit_code = int(run_result.get("exit_code") or 0)
    if exit_code != 0:
        tail = [str(x) for x in list(run_result.get("stderr_tail") or [])[-80:] if str(x).strip() != ""]
        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
        send_json(handler, {"ok": False, "error": f"导出失败：子进程退出码={int(exit_code)}\n\n{tail_text}"}, status=500)
        return

    report = run_result.get("report")
    if not isinstance(report, dict):
        raise TypeError("export job report must be dict")

    token = str(report.get("download_token", "") or "").strip()
    out_path = str(report.get("output_gil_path", "") or "").strip()
    if token and out_path:
        m = getattr(b, "_exported_gil_paths_by_token", None)
        if isinstance(m, dict):
            p = Path(out_path).resolve()
            if p.is_file():
                m[token] = p

    send_json(handler, {"ok": True, **dict(report)}, status=200)


def _handle_export_gia(*, handler: object, bridge: object | None) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    payload = read_request_json_object(handler)

    layout_name = str(payload.get("layout_name", "") or "")
    verify = payload.get("verify_with_dll_dump", True)
    verify_bool = bool(verify) if isinstance(verify, bool) else True
    payload["layout_name"] = str(layout_name)
    payload["verify_with_dll_dump"] = bool(verify_bool)

    game_version = str(payload.get("game_version", "") or "").strip() or "6.3.0"

    bundle = payload.get("bundle", None)
    if not isinstance(bundle, dict):
        send_json(handler, {"ok": False, "error": "bundle is required"}, status=400)
        return

    raw_templates = bundle.get("templates", None)
    templates_count = 0
    if isinstance(raw_templates, list):
        templates_count = sum(1 for it in raw_templates if isinstance(it, dict))
    elif isinstance(raw_templates, dict):
        templates_count = sum(1 for it in raw_templates.values() if isinstance(it, dict))
    else:
        send_json(handler, {"ok": False, "error": "bundle.templates must be array or object"}, status=400)
        return
    if templates_count <= 0:
        send_json(handler, {"ok": False, "error": "bundle.templates 为空，无法导出（未识别到可写回的控件模板）"}, status=400)
        return

    ok, error = getattr(b, "try_validate_text_placeholders_in_ui_payload")(bundle, autofix_missing_lv_variables=True)
    if not ok:
        send_json(handler, {"ok": False, "error": error}, status=400)
        return

    payload["game_version"] = str(game_version)

    run_result = run_ui_workbench_export_job_in_subprocess(bridge=b, command="export_gia", payload=dict(payload))
    exit_code = int(run_result.get("exit_code") or 0)
    if exit_code != 0:
        tail = [str(x) for x in list(run_result.get("stderr_tail") or [])[-80:] if str(x).strip() != ""]
        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
        send_json(handler, {"ok": False, "error": f"导出失败：子进程退出码={int(exit_code)}\n\n{tail_text}"}, status=500)
        return

    report = run_result.get("report")
    if not isinstance(report, dict):
        raise TypeError("export job report must be dict")

    token = str(report.get("download_token", "") or "").strip()
    out_gia_path = str(report.get("output_gia_path", "") or "").strip()
    out_gil_path = str(report.get("output_gil_path", "") or "").strip()
    if token:
        m_gia = getattr(b, "_exported_gia_paths_by_token", None)
        if isinstance(m_gia, dict) and out_gia_path:
            p = Path(out_gia_path).resolve()
            if p.is_file():
                m_gia[token] = p
        m_gil = getattr(b, "_exported_gil_paths_by_token", None)
        if isinstance(m_gil, dict) and out_gil_path:
            p2 = Path(out_gil_path).resolve()
            if p2.is_file():
                m_gil[token] = p2

    send_json(handler, {"ok": True, **dict(report)}, status=200)


def _handle_download_gil(*, handler: object, bridge: object | None, query_text: str) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    query = parse_qs(query_text or "")
    token = (query.get("token", [""])[0] or "").strip()
    if not token:
        send_json(handler, {"ok": False, "error": "token is required"}, status=400)
        return
    path = getattr(b, "try_resolve_exported_gil_by_token")(token)
    if path is None:
        send_json(handler, {"ok": False, "error": "token not found"}, status=404)
        return
    data = Path(path).read_bytes()
    file_name = Path(path).name
    getattr(handler, "send_response")(200)
    getattr(handler, "send_header")("Content-Type", "application/octet-stream")
    getattr(handler, "send_header")("Content-Disposition", f'attachment; filename="{file_name}"')
    getattr(handler, "send_header")("Content-Length", str(len(data)))
    getattr(handler, "send_header")("Cache-Control", "no-store")
    getattr(handler, "end_headers")()
    getattr(getattr(handler, "wfile"), "write")(data)


def _handle_download_gia(*, handler: object, bridge: object | None, query_text: str) -> None:
    b = get_bridge_or_503_json(handler, bridge, connected_field=False)
    if b is None:
        return
    query = parse_qs(query_text or "")
    token = (query.get("token", [""])[0] or "").strip()
    if not token:
        send_json(handler, {"ok": False, "error": "token is required"}, status=400)
        return
    path = getattr(b, "try_resolve_exported_gia_by_token")(token)
    if path is None:
        send_json(handler, {"ok": False, "error": "token not found"}, status=404)
        return
    data = Path(path).read_bytes()
    file_name = Path(path).name
    getattr(handler, "send_response")(200)
    getattr(handler, "send_header")("Content-Type", "application/octet-stream")
    getattr(handler, "send_header")("Content-Disposition", f'attachment; filename="{file_name}"')
    getattr(handler, "send_header")("Content-Length", str(len(data)))
    getattr(handler, "send_header")("Cache-Control", "no-store")
    getattr(handler, "end_headers")()
    getattr(getattr(handler, "wfile"), "write")(data)

