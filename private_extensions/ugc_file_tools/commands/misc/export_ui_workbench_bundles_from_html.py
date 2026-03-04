from __future__ import annotations

"""
export_ui_workbench_bundles_from_html.py

用途：
- 将项目存档 `管理配置/UI源码/*.html` 通过 UI Workbench（浏览器计算样式）导出为 Workbench bundle JSON，
  并写入：`管理配置/UI源码/__workbench_out__/<stem>.ui_bundle.json`。

设计目的：
- 配合导出中心：当用户修改了 HTML 但 bundle 未更新时，自动补齐 bundle，避免导出旧页面。

依赖：
- 需要安装 Playwright + chromium：
  - `pip install playwright`
  - `playwright install chromium`
"""

import argparse
import http.server
import json
import threading
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import repo_root


def _print_progress(current: int, total: int, label: str) -> None:
    import sys

    print(f"[{int(current)}/{int(total)}] {str(label)}", file=sys.stderr)


def _start_static_server(root_dir: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    class _WorkbenchRequestHandler(http.server.SimpleHTTPRequestHandler):
        extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".map": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }

        def log_message(self, _format: str, *_args: object) -> None:
            # 导出中心会解析 stderr 进度；静默静态资源请求日志以减少噪音。
            return

    handler_class = lambda *args, **kwargs: _WorkbenchRequestHandler(*args, directory=str(root_dir), **kwargs)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def _wait_for_textarea_non_empty(page: Any, css_selector: str, timeout_ms: int) -> None:
    start_time = time.monotonic()
    timeout_s = float(timeout_ms) / 1000.0
    while True:
        current_value = page.eval_on_selector(
            css_selector,
            "el => (el && 'value' in el) ? String(el.value || '') : ''",
        )
        if str(current_value).strip():
            return
        if time.monotonic() - start_time > timeout_s:
            raise TimeoutError(f"等待 textarea 输出超时: {css_selector}")
        time.sleep(0.05)


def _assert_workbench_no_errors(validation_text: str) -> None:
    lines = [s.strip() for s in str(validation_text or "").splitlines() if s.strip()]
    for s in lines:
        if "errors=" not in s:
            continue
        if s.startswith("【") and "errors=0" in s:
            return
    raise AssertionError("Workbench 校验未通过（存在 errors）。\n---- validation.txt ----\n" + str(validation_text).strip())


def _export_bundle_payload_for_html_text(
    *,
    page: Any,
    html_text: str,
    canvas_size_key: str,
    timeout_ms: int,
) -> tuple[dict, str]:
    if page.query_selector("#inputHtmlTextArea") is None:
        raise RuntimeError("未找到 Workbench 编辑器 DOM（#inputHtmlTextArea），入口页可能已变化。")

    size_button_id = "sizeButton" + str(canvas_size_key)
    if page.query_selector("#" + size_button_id) is None:
        raise RuntimeError(f"未找到画布尺寸按钮 DOM（#{size_button_id}），无法强制画布尺寸。")
    page.evaluate(
        "(buttonId) => { const b = document.getElementById(buttonId); if (b) b.click(); }",
        size_button_id,
    )

    # 大 HTML：用赋值 textarea.value + dispatch input，避免逐字符 fill 超时
    page.evaluate(
        "(text) => { const t = document.getElementById('inputHtmlTextArea'); if (!t) return; t.value = String(text || ''); t.dispatchEvent(new Event('input', { bubbles: true })); }",
        str(html_text),
    )
    _wait_for_textarea_non_empty(page, "#inputHtmlTextArea", timeout_ms)

    # 清空旧输出，避免 wait 误判
    page.evaluate("() => { const t = document.getElementById('flattenedOutputTextArea'); if (t) t.value = ''; }")
    page.evaluate("() => { const t = document.getElementById('validationErrorsTextArea'); if (t) t.value = ''; }")
    page.evaluate("() => { const t = document.getElementById('uiControlGroupJsonOutputTextArea'); if (t) t.value = ''; }")

    # 自动修正并校验 + 扁平化（bundle 依赖扁平 layers）
    page.click("#autoFixAndRenderButtonInline")
    page.click("#generateFlattenedButtonInline")

    _wait_for_textarea_non_empty(page, "#validationErrorsTextArea", timeout_ms)
    _wait_for_textarea_non_empty(page, "#flattenedOutputTextArea", timeout_ms)
    validation_text = page.eval_on_selector("#validationErrorsTextArea", "el => String(el.value || '')")
    _assert_workbench_no_errors(str(validation_text))

    page.click("#exportUiControlGroupJsonButtonInline")
    _wait_for_textarea_non_empty(page, "#uiControlGroupJsonOutputTextArea", timeout_ms)
    bundle_text = page.eval_on_selector("#uiControlGroupJsonOutputTextArea", "el => String(el.value || '')")

    bundle_payload = json.loads(bundle_text)
    if not isinstance(bundle_payload, dict):
        raise TypeError("Workbench 导出的 bundle JSON 不是 object(dict)")
    return dict(bundle_payload), str(validation_text)


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="从项目存档 UI源码 HTML 导出/更新 UI Workbench bundle（写入 UI源码/__workbench_out__/*.ui_bundle.json）。"
    )
    parser.add_argument(
        "--project-root",
        dest="project_root",
        required=True,
        help="项目存档根目录（例如 assets/资源库/项目存档/<package_id>）",
    )
    parser.add_argument(
        "--html",
        dest="html_files",
        action="append",
        required=True,
        help="要导出的 UI源码 HTML 文件路径（可重复传入）。",
    )
    parser.add_argument(
        "--pc-canvas-size",
        dest="pc_canvas_size_key",
        default="1920x1080",
        help="Workbench 生成 bundle 时使用的画布尺寸 key（默认 1920x1080）。",
    )
    parser.add_argument(
        "--timeout-ms",
        dest="timeout_ms",
        type=int,
        default=180_000,
        help="单页导出超时（毫秒，默认 180000）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    html_paths = [Path(p).resolve() for p in list(args.html_files or [])]
    html_paths = [p for p in html_paths if str(p)]
    if not html_paths:
        raise ValueError("--html 不能为空")
    for p in html_paths:
        if not p.is_file():
            raise FileNotFoundError(str(p))
        if p.suffix.lower() not in {".html", ".htm"}:
            raise ValueError(f"不是 HTML 文件：{str(p)}")

    # 输出目录：项目存档内（非 out/）
    ui_src_dir = (project_root / "管理配置" / "UI源码").resolve()
    if not ui_src_dir.is_dir():
        raise FileNotFoundError(str(ui_src_dir))
    out_dir = (ui_src_dir / "__workbench_out__").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Playwright 依赖检查（不在 import 阶段触发重依赖）
    import importlib.util

    if importlib.util.find_spec("playwright") is None:
        raise RuntimeError(
            "缺少 Playwright（python 包 playwright）。需要：\n"
            "- `pip install playwright`\n"
            "- `playwright install chromium`\n"
            "（本工具依赖 headless chromium 来运行 UI Workbench 生成 bundle。）"
        )

    workbench_dir = (repo_root() / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(str(workbench_dir))

    httpd, port = _start_static_server(workbench_dir)
    entry_url = f"http://127.0.0.1:{port}/ui_html_workbench.html?mode=editor&internal=1"

    from playwright.sync_api import sync_playwright

    total = int(len(html_paths))
    _print_progress(0, total, "准备 Workbench…")

    reports: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = ctx.new_page()
        page.goto(entry_url, wait_until="load", timeout=int(args.timeout_ms))

        canvas_size_key = str(args.pc_canvas_size_key).strip()
        if canvas_size_key == "":
            raise ValueError("--pc-canvas-size 不能为空")

        for i, html_path in enumerate(list(html_paths), start=1):
            _print_progress(i, total, f"导出 bundle：{html_path.name}")
            html_text = html_path.read_text(encoding="utf-8")
            bundle_payload, validation_text = _export_bundle_payload_for_html_text(
                page=page,
                html_text=html_text,
                canvas_size_key=canvas_size_key,
                timeout_ms=int(args.timeout_ms),
            )

            out_path = (out_dir / f"{html_path.stem}.ui_bundle.json").resolve()
            out_path.write_text(
                json.dumps(bundle_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            reports.append(
                {
                    "html": str(html_path),
                    "output_bundle": str(out_path),
                    "validation_summary": str(validation_text).splitlines()[-1] if str(validation_text).strip() else "",
                }
            )

        ctx.close()
        browser.close()

    httpd.shutdown()

    # stdout: JSON 摘要（便于人工运行时查看）
    print(
        json.dumps(
            {
                "project_root": str(project_root),
                "ui_src_dir": str(ui_src_dir),
                "output_dir": str(out_dir),
                "exported_total": int(len(reports)),
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

