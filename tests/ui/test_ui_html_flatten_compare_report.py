from __future__ import annotations

import http.server
import os
import shutil
import threading
import time
from pathlib import Path

from PIL import Image
import pytest


def _get_repo_root() -> Path:
    """避免 `tests` 命名空间与外部环境冲突：向上查找包含 app/engine/assets 的仓库根目录。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "app").is_dir() and (parent / "engine").is_dir() and (parent / "assets").is_dir():
            return parent
    raise RuntimeError(f"无法定位仓库根目录（from={here}）")


def _copy_html_sources(*, out_dir: Path, source_html: Path, flattened_html: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    dst_source = (out_dir / "original.html").resolve()
    dst_flattened = (out_dir / "flattened.html").resolve()
    shutil.copyfile(source_html, dst_source)
    src_flattened = Path(flattened_html).resolve()
    if src_flattened != dst_flattened:
        shutil.copyfile(src_flattened, dst_flattened)
    return dst_source, dst_flattened


def _write_compare_report(*, out_dir: Path, original_html: Path, flattened_html: Path) -> Path:
    report_path = (out_dir / "compare_report.html").resolve()

    # 注意：不依赖 JS；仅用 iframe 并排展示，便于人工对照。
    # 资源路径：使用相对路径，保证 report 目录可整体拷贝。
    report_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>UI HTML 对比（原稿 vs 扁平化）</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; font-family: "Microsoft YaHei", sans-serif; }}
    .root {{ width: 100%; height: 100%; display: flex; flex-direction: column; gap: 8px; padding: 8px; background: #111; color: #fff; }}
    .header {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
    .title {{ font-weight: 900; }}
    .hint {{ opacity: 0.85; font-size: 12px; }}
    .grid {{ flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .panel {{ min-height: 0; display: flex; flex-direction: column; gap: 6px; border: 1px solid #333; background: #1b1b1b; }}
    .panel-title {{ padding: 6px 8px; font-weight: 800; border-bottom: 1px solid #333; }}
    .frame-wrap {{ flex: 1; min-height: 0; background: #000; }}
    iframe {{ width: 100%; height: 100%; border: 0; background: #000; }}
  </style>
</head>
<body>
  <div class="root">
    <div class="header">
      <div class="title">UI HTML 对比（原稿 vs 扁平化）</div>
      <div class="hint">左：原稿（original.html）｜右：扁平化（flattened.html）</div>
    </div>
    <div class="grid">
      <div class="panel">
        <div class="panel-title">原稿</div>
        <div class="frame-wrap"><iframe src="original.html"></iframe></div>
      </div>
      <div class="panel">
        <div class="panel-title">扁平化</div>
        <div class="frame-wrap"><iframe src="flattened.html"></iframe></div>
      </div>
    </div>
  </div>
</body>
</html>
"""
    report_path.write_text(report_html, encoding="utf-8")
    return report_path


def _playwright_available() -> bool:
    from tests._helpers.playwright_utils import is_playwright_chromium_ready

    return is_playwright_chromium_ready()


def _start_static_server(root_dir: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    class _WorkbenchRequestHandler(http.server.SimpleHTTPRequestHandler):
        extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".map": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }

    handler_class = lambda *args, **kwargs: _WorkbenchRequestHandler(*args, directory=str(root_dir), **kwargs)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def _wait_for_textarea_non_empty(page, css_selector: str, timeout_ms: int) -> None:
    start_time = time.monotonic()
    timeout_s = timeout_ms / 1000.0
    while True:
        current_value = page.eval_on_selector(css_selector, "el => (el && 'value' in el) ? String(el.value || '') : ''")
        if current_value.strip():
            return
        if time.monotonic() - start_time > timeout_s:
            raise TimeoutError(f"等待 textarea 输出超时: {css_selector}")
        time.sleep(0.05)


def _generate_flattened_with_workbench(
    *,
    out_dir: Path,
    source_html_text: str,
    timeout_ms: int = 20_000,
) -> tuple[Path, Path]:
    """
    用 Workbench（浏览器 DOM/CSS 计算样式）生成当前源码的扁平化结果，保证不使用旧缓存。
    依赖：Playwright 已安装且 chromium 可用。
    """
    from playwright.sync_api import sync_playwright

    repo_root = _get_repo_root()
    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(f"Workbench 目录不存在：{workbench_dir}")

    httpd, port = _start_static_server(workbench_dir)
    # ui_html_workbench.html 默认会跳转到 ui_app_ui_preview.html（统一入口策略）。
    # 测试需要使用 Workbench 的“编辑器 DOM”驱动扁平化，因此显式声明 internal=1 禁用跳转。
    entry_url = f"http://127.0.0.1:{port}/ui_html_workbench.html?mode=editor&internal=1"

    out_dir.mkdir(parents=True, exist_ok=True)
    flattened_path = (out_dir / "flattened.html").resolve()
    validation_path = (out_dir / "validation.txt").resolve()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=timeout_ms)

        if page.query_selector("#inputHtmlTextArea") is None:
            raise RuntimeError("未找到 Workbench 编辑器 DOM（#inputHtmlTextArea），入口页可能已变化。")

        # 关键：切到 1920×1080 画布（Workbench 内部默认可能是 1600×900，导致扁平化坐标系不一致）
        if page.query_selector("#sizeButton1920x1080") is None:
            raise RuntimeError("未找到画布尺寸按钮 DOM（#sizeButton1920x1080），无法强制画布尺寸。")
        page.evaluate("() => { const b = document.getElementById('sizeButton1920x1080'); if (b) b.click(); }")

        page.fill("#inputHtmlTextArea", source_html_text)
        # 使用“自动修正并校验”：会注入禁滚动等修正，避免预览环境差异导致误报。
        page.click("#autoFixAndRenderButtonInline")
        page.click("#generateFlattenedButtonInline")
        _wait_for_textarea_non_empty(page, "#flattenedOutputTextArea", timeout_ms)

        flattened_output = page.eval_on_selector("#flattenedOutputTextArea", "el => String(el.value || '')")
        validation_output = page.eval_on_selector("#validationErrorsTextArea", "el => String(el.value || '')")

        flattened_path.write_text(flattened_output, encoding="utf-8")
        validation_path.write_text(validation_output, encoding="utf-8")

        context.close()
        browser.close()

    httpd.shutdown()
    return flattened_path, validation_path


def _assert_workbench_validation_passed(validation_text: str) -> None:
    """
    Workbench 的 validation.txt 分为两段：
    - 【校验（结构/运行态）】：必须无 errors/warnings（否则认为网页本身有问题）
    - 【扁平化（降级/近似/归一化提示）】：允许有 warnings（属于导出链路能力差异提示）
    """
    for line in validation_text.splitlines():
        s = line.strip()
        if not s.startswith("【校验（结构/运行态）】"):
            continue
        # 例：【校验（结构/运行态）】 errors=0 warnings=0 infos=0 total=0
        parts = s.replace("【校验（结构/运行态）】", "").strip().split()
        kv = {}
        for p in parts:
            if "=" not in p:
                continue
            k, v = p.split("=", 1)
            kv[k.strip()] = v.strip()
        try:
            errors = int(kv.get("errors", "999999"))
            warnings = int(kv.get("warnings", "999999"))
        except ValueError:
            raise AssertionError(f"validation.txt 解析失败：{s}")
        if errors != 0:
            raise AssertionError(
                "Workbench 结构/运行态校验失败（errors 非 0），请先修复 HTML/CSS 结构问题。\n"
                "---- validation.txt ----\n"
                + validation_text.strip()
            )
        return
    raise AssertionError(
        "validation.txt 未找到结构/运行态校验摘要行（【校验（结构/运行态）】...），无法判断是否通过。\n"
        "---- validation.txt ----\n"
        + validation_text.strip()
    )


def _render_pngs_with_playwright(*, out_dir: Path, original_html: Path, flattened_html: Path) -> tuple[Path, Path]:
    # 依赖：pip install playwright && python -m playwright install chromium
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    original_png = (out_dir / "original.png").resolve()
    flattened_png = (out_dir / "flattened.png").resolve()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = context.new_page()

        page.goto(original_html.as_uri(), wait_until="load")
        page.screenshot(path=str(original_png), full_page=False)

        page.goto(flattened_html.as_uri(), wait_until="load")
        page.screenshot(path=str(flattened_png), full_page=False)

        context.close()
        browser.close()

    return original_png, flattened_png


def _concat_side_by_side(*, left_png: Path, right_png: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    left = Image.open(left_png).convert("RGBA")
    right = Image.open(right_png).convert("RGBA")

    gutter = 16
    out_w = int(left.width + gutter + right.width)
    out_h = int(max(left.height, right.height))
    canvas = Image.new("RGBA", (out_w, out_h), (17, 17, 17, 255))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + gutter, 0))
    canvas.save(out_path)
    return out_path


def _get_default_source_html_relpath_list() -> list[str]:
    # 默认对比列表：保证“示例关卡选择页”与“春节保卫战识亲页”都有对比产物。
    # 允许通过环境变量覆盖：UI_COMPARE_HTMLS=ceshi.html;2.html
    raw = os.environ.get("UI_COMPARE_HTMLS", "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        if parts:
            return parts
    return ["ceshi.html", "2.html"]


@pytest.mark.parametrize("source_html_name", _get_default_source_html_relpath_list())
def test_ui_html_flatten_compare_report_outputs_files(source_html_name: str) -> None:
    repo_root = _get_repo_root()
    package_id = "示例项目模板"

    # 目标：一键生成“原稿 vs 扁平化”的可视化对照产物（至少是 HTML 报告）
    source_html = (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id
        / "管理配置"
        / "UI源码"
        / source_html_name
    )
    if not source_html.is_file():
        raise FileNotFoundError(f"source_html 不存在：{source_html}")

    out_dir = (repo_root / "app" / "runtime" / "cache" / "ui_compare" / package_id / source_html.stem).resolve()

    # 关键：确保扁平化结果“与当前源码同步”，避免对比时误用旧缓存。
    validation_errors = ""
    if _playwright_available():
        source_html_text = source_html.read_text(encoding="utf-8")
        flattened_html, validation_path = _generate_flattened_with_workbench(out_dir=out_dir, source_html_text=source_html_text)
        validation_errors = validation_path.read_text(encoding="utf-8")
    else:
        cached_flattened_dir = (repo_root / "app" / "runtime" / "cache" / "ui_html_bundle_cli" / package_id).resolve()
        flattened_candidates = []
        if cached_flattened_dir.is_dir():
            flattened_candidates = sorted(
                [p for p in cached_flattened_dir.glob(f"{source_html.stem}*.flattened.html") if p.is_file()],
                key=lambda p: float(p.stat().st_mtime),
                reverse=True,
            )
        flattened_html = flattened_candidates[0] if flattened_candidates else None

        if flattened_html is None or (not flattened_html.is_file()):
            pytest.skip(
                "未检测到可用的 Playwright chromium，且未找到本机缓存 flattened_html，跳过该用例。\n"
                f"- cache_dir: {cached_flattened_dir}\n"
                f"- expected_glob: app/runtime/cache/ui_html_bundle_cli/{package_id}/{source_html.stem}*.flattened.html\n"
                "- 如需运行：请先在你的环境里执行 `playwright install` 下载浏览器，或先生成对应 flattened 缓存。"
            )
    copied_original, copied_flattened = _copy_html_sources(
        out_dir=out_dir,
        source_html=source_html,
        flattened_html=flattened_html,
    )

    report_path = _write_compare_report(
        out_dir=out_dir,
        original_html=copied_original,
        flattened_html=copied_flattened,
    )
    assert report_path.is_file()

    if _playwright_available():
        _assert_workbench_validation_passed(validation_errors)

        original_png, flattened_png = _render_pngs_with_playwright(
            out_dir=out_dir,
            original_html=copied_original,
            flattened_html=copied_flattened,
        )
        compare_png = _concat_side_by_side(
            left_png=original_png,
            right_png=flattened_png,
            out_path=(out_dir / "compare.png").resolve(),
        )
        assert compare_png.is_file()

    # 用 pytest 输出可直接点击的路径（IDE/终端中可见）
    print("UI compare artifacts:", str(out_dir))

