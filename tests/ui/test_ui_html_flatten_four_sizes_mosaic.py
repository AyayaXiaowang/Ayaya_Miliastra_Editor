from __future__ import annotations

import http.server
import os
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw
import pytest


def _get_repo_root() -> Path:
    """避免 `tests` 命名空间与外部环境冲突：向上查找包含 app/engine/assets 的仓库根目录。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "app").is_dir() and (parent / "engine").is_dir() and (parent / "assets").is_dir():
            return parent
    raise RuntimeError(f"无法定位仓库根目录（from={here}）")


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


def _render_flattened_html_text_with_workbench(
    *,
    page,
    source_html_text: str,
    canvas_size_key: str,
    timeout_ms: int,
) -> str:
    if page.query_selector("#inputHtmlTextArea") is None:
        raise RuntimeError("未找到 Workbench 编辑器 DOM（#inputHtmlTextArea），入口页可能已变化。")

    size_button_id = "sizeButton" + str(canvas_size_key)
    if page.query_selector("#" + size_button_id) is None:
        raise RuntimeError(f"未找到画布尺寸按钮 DOM（#{size_button_id}），无法强制画布尺寸。")
    page.evaluate("(buttonId) => { const b = document.getElementById(buttonId); if (b) b.click(); }", size_button_id)

    page.fill("#inputHtmlTextArea", source_html_text)

    # 清空旧输出，避免 wait 误判
    page.evaluate("() => { const t = document.getElementById('flattenedOutputTextArea'); if (t) t.value = ''; }")
    # 使用“自动修正并校验”：会注入禁滚动等修正，避免预览环境差异导致误报。
    page.click("#autoFixAndRenderButtonInline")
    page.click("#generateFlattenedButtonInline")
    _wait_for_textarea_non_empty(page, "#flattenedOutputTextArea", timeout_ms)
    return page.eval_on_selector("#flattenedOutputTextArea", "el => String(el.value || '')")


def _force_show_flat_area(page, *, size_key: str) -> None:
    # 将目标 size_key 的 flat-display-area 置为 block，其余置为 none
    page.evaluate(
        """
        (key) => {
          const list = document.querySelectorAll('.flat-display-area');
          for (const el of list) {
            const k = el && el.dataset ? String(el.dataset.sizeKey || '') : '';
            el.style.display = (k === String(key)) ? 'block' : 'none';
          }
        }
        """,
        size_key,
    )


def _assert_key_elements_in_viewport(*, page, size_key: str, viewport_w: int, viewport_h: int, debug_labels: list[str]) -> None:
    # “硬性规则”：四档画布下关键元素必须完全落在画布内（不裁切）
    for debug_label in debug_labels:
        rect = page.evaluate(
            """
            ({ label, sizeKey }) => {
              const area = document.querySelector(`.flat-display-area[data-size-key="${String(sizeKey)}"]`);
              if (!area) return null;
              const el =
                area.querySelector(`[data-debug-label="${label}"]`) ||
                area.querySelector(`[data-debug-label="text-${label}"]`) ||
                null;
              if (!el) return null;
              const r = el.getBoundingClientRect();
              return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
            }
            """,
            {"label": debug_label, "sizeKey": size_key},
        )
        if rect is None:
            raise AssertionError(f"未找到关键扁平层 data-debug-label={debug_label!r}（size={size_key}，无法做适配断言）")

        # 允许少量浮点误差
        eps = 0.51
        if rect["left"] < -eps or rect["top"] < -eps:
            raise AssertionError(f"{debug_label} 超出画布左/上边界：{rect}")
        if rect["right"] > float(viewport_w) + eps or rect["bottom"] > float(viewport_h) + eps:
            raise AssertionError(f"{debug_label} 超出画布右/下边界：{rect} (viewport={viewport_w}x{viewport_h})")


def _get_area_rect(page, *, size_key: str, debug_label: str) -> dict:
    rect = page.evaluate(
        """
        ({ label, sizeKey }) => {
          const area = document.querySelector(`.flat-display-area[data-size-key="${String(sizeKey)}"]`);
          if (!area) return null;
          // 注意：存在 game-cutout 时，“背景矩形”会被扁平化切成多个碎片（label / label-cutout-*）。
          // 这里对同一 label 的所有碎片取 unionRect，得到真实外接矩形。
          const nodes = [];
          const base = String(label || '');
          const list = area.querySelectorAll('[data-debug-label]');
          for (const el of list) {
            const v = String(el.dataset && el.dataset.debugLabel ? el.dataset.debugLabel : '');
            if (!v) continue;
            if (v === base || v.startsWith(base + '-cutout-')) nodes.push(el);
          }
          if (nodes.length === 0) {
            const single =
              area.querySelector(`[data-debug-label="${base}"]`) ||
              area.querySelector(`[data-debug-label="text-${base}"]`) ||
              null;
            if (!single) return null;
            const r = single.getBoundingClientRect();
            return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
          }
          let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
          for (const el of nodes) {
            const r = el.getBoundingClientRect();
            if (r.left < left) left = r.left;
            if (r.top < top) top = r.top;
            if (r.right > right) right = r.right;
            if (r.bottom > bottom) bottom = r.bottom;
          }
          const w = Math.max(0, right - left);
          const h = Math.max(0, bottom - top);
          return { left, top, right, bottom, width: w, height: h };
        }
        """,
        {"label": debug_label, "sizeKey": size_key},
    )
    if rect is None:
        raise AssertionError(f"未找到关键扁平层 data-debug-label={debug_label!r}（size={size_key}）")
    return rect


def _render_flattened_for_sizes(*, source_html_text: str, out_dir: Path) -> dict[str, Path]:
    from playwright.sync_api import sync_playwright

    sizes: list[tuple[str, int, int]] = [
        ("1920x1080", 1920, 1080),
        ("1600x900", 1600, 900),
        ("1560x720", 1560, 720),
        ("1280x720", 1280, 720),
    ]

    repo_root = _get_repo_root()
    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(f"Workbench 目录不存在：{workbench_dir}")

    httpd, port = _start_static_server(workbench_dir)
    entry_url = f"http://127.0.0.1:{port}/ui_html_workbench.html?mode=editor"

    out_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    timeout_ms = 20_000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 用一个 Workbench 页循环生成每档 flattened（避免在同一进程内嵌套 sync_playwright）
        wb_ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        wb_page = wb_ctx.new_page()
        wb_page.goto(entry_url, wait_until="load", timeout=timeout_ms)

        panel_wh_by_size: dict[str, tuple[float, float]] = {}
        for size_key, w, h in sizes:
            flattened_text = _render_flattened_html_text_with_workbench(
                page=wb_page,
                source_html_text=source_html_text,
                canvas_size_key=size_key,
                timeout_ms=timeout_ms,
            )
            flattened_html_path = (out_dir / f"flattened__{size_key}.html").resolve()
            flattened_html_path.write_text(flattened_text, encoding="utf-8")

            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
            page = ctx.new_page()
            page.goto(flattened_html_path.as_uri(), wait_until="load")
            _force_show_flat_area(page, size_key=size_key)
            _assert_key_elements_in_viewport(
                page=page,
                size_key=size_key,
                viewport_w=w,
                viewport_h=h,
                debug_labels=["game-panel"],
            )

            # 硬性规则（适配）：主弹窗必须随画布尺寸等比变化（16:9 四档同比例）
            panel_rect = _get_area_rect(page, size_key=size_key, debug_label="game-panel")
            panel_wh_by_size[size_key] = (float(panel_rect["width"]), float(panel_rect["height"]))

            page.wait_for_timeout(50)
            png_path = (out_dir / f"flattened_{size_key}.png").resolve()
            page.screenshot(path=str(png_path), full_page=False)
            out[size_key] = png_path
            ctx.close()

        # 校验“确实发生了缩放”：1280x720 的弹窗必须显著小于 1920x1080
        w1920, h1920 = panel_wh_by_size["1920x1080"]
        w1280, h1280 = panel_wh_by_size["1280x720"]
        if not (w1280 < w1920 * 0.80 and h1280 < h1920 * 0.80):
            raise AssertionError(
                "四档适配失败：主弹窗尺寸未随分辨率缩放（看起来只是外框变了）。"
                f" panel 1920=({w1920:.2f},{h1920:.2f}) panel 1280=({w1280:.2f},{h1280:.2f})"
            )

        wb_ctx.close()
        browser.close()

    httpd.shutdown()
    return out


def _build_2x2_mosaic(*, images: dict[str, Path], out_path: Path) -> Path:
    # 固定 cell 为 1920×1080，便于直接看“是否适配/是否溢出/是否偏移”
    cell_w, cell_h = 1920, 1080
    gutter = 24
    out_w = cell_w * 2 + gutter
    out_h = cell_h * 2 + gutter

    canvas = Image.new("RGBA", (out_w, out_h), (17, 17, 17, 255))
    draw = ImageDraw.Draw(canvas)

    order = [
        ("1920x1080", 0, 0),
        ("1600x900", 1, 0),
        ("1560x720", 0, 1),
        ("1280x720", 1, 1),
    ]

    for key, col, row in order:
        img_path = images.get(key)
        if img_path is None:
            raise RuntimeError(f"缺少截图：{key}")
        img = Image.open(img_path).convert("RGBA")
        x0 = col * (cell_w + gutter)
        y0 = row * (cell_h + gutter)
        cx = x0 + (cell_w - img.width) // 2
        cy = y0 + (cell_h - img.height) // 2
        canvas.paste(img, (int(cx), int(cy)))

        # label
        label_bg = (0, 0, 0, 180)
        draw.rectangle([x0 + 12, y0 + 12, x0 + 220, y0 + 54], fill=label_bg)
        draw.text((x0 + 20, y0 + 20), key, fill=(255, 255, 255, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def test_ui_html_flatten_four_sizes_mosaic_outputs_image() -> None:
    if not _playwright_available():
        pytest.skip("requires playwright (pip install playwright; python -m playwright install chromium)")

    # 默认对 ceshi.html 与 2.html 生成四分辨率拼图；可通过环境变量覆盖（分号分隔，如 UI_MOSAIC_HTMLS=2.html）。
    raw = os.environ.get("UI_MOSAIC_HTMLS", "").strip()
    html_list = [p.strip() for p in raw.split(";") if p.strip()] if raw else ["ceshi.html", "2.html"]

    repo_root = _get_repo_root()
    package_id = "示例项目模板"

    for html_name in html_list:
        source_html = (
            repo_root
            / "assets"
            / "资源库"
            / "项目存档"
            / package_id
            / "管理配置"
            / "UI源码"
            / html_name
        )
        if not source_html.is_file():
            raise FileNotFoundError(f"source_html 不存在：{source_html}")

        out_dir = (repo_root / "app" / "runtime" / "cache" / "ui_compare" / package_id / source_html.stem).resolve()
        source_html_text = source_html.read_text("utf-8")

        # 对不同页面采用不同的关键元素断言：ceshi 是弹窗式布局，2 是主面板布局。
        if source_html.stem == "ceshi":
            screenshots = _render_flattened_for_sizes(source_html_text=source_html_text, out_dir=out_dir)
        else:
            screenshots = _render_flattened_for_sizes_generic_panel(
                source_html_text=source_html_text,
                out_dir=out_dir,
                panel_debug_label="main-panel",
            )

        mosaic_path = _build_2x2_mosaic(
            images=screenshots,
            out_path=(out_dir / "flattened_4sizes_mosaic.png").resolve(),
        )
        assert mosaic_path.is_file()
        print("flattened 4-sizes mosaic:", str(mosaic_path))


def _render_flattened_for_sizes_generic_panel(
    *,
    source_html_text: str,
    out_dir: Path,
    panel_debug_label: str,
) -> dict[str, Path]:
    from playwright.sync_api import sync_playwright

    sizes: list[tuple[str, int, int]] = [
        ("1920x1080", 1920, 1080),
        ("1600x900", 1600, 900),
        ("1560x720", 1560, 720),
        ("1280x720", 1280, 720),
    ]

    repo_root = _get_repo_root()
    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(f"Workbench 目录不存在：{workbench_dir}")

    httpd, port = _start_static_server(workbench_dir)
    entry_url = f"http://127.0.0.1:{port}/ui_html_workbench.html?mode=editor"

    out_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    timeout_ms = 20_000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        wb_ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        wb_page = wb_ctx.new_page()
        wb_page.goto(entry_url, wait_until="load", timeout=timeout_ms)

        panel_wh_by_size: dict[str, tuple[float, float]] = {}
        for size_key, w, h in sizes:
            flattened_text = _render_flattened_html_text_with_workbench(
                page=wb_page,
                source_html_text=source_html_text,
                canvas_size_key=size_key,
                timeout_ms=timeout_ms,
            )
            flattened_html_path = (out_dir / f"flattened__{size_key}.html").resolve()
            flattened_html_path.write_text(flattened_text, encoding="utf-8")

            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
            page = ctx.new_page()
            page.goto(flattened_html_path.as_uri(), wait_until="load")
            _force_show_flat_area(page, size_key=size_key)

            _assert_key_elements_in_viewport(
                page=page,
                size_key=size_key,
                viewport_w=w,
                viewport_h=h,
                debug_labels=[panel_debug_label],
            )

            panel_rect = _get_area_rect(page, size_key=size_key, debug_label=panel_debug_label)
            panel_wh_by_size[size_key] = (float(panel_rect["width"]), float(panel_rect["height"]))

            page.wait_for_timeout(50)
            png_path = (out_dir / f"flattened_{size_key}.png").resolve()
            page.screenshot(path=str(png_path), full_page=False)
            out[size_key] = png_path
            ctx.close()

        # 校验“至少随分辨率缩小/不放大”：避免小分辨率反而更大导致裁切。
        w1920, h1920 = panel_wh_by_size["1920x1080"]
        w1280, h1280 = panel_wh_by_size["1280x720"]
        eps = 0.51
        if not (w1280 <= w1920 + eps and h1280 <= h1920 + eps):
            raise AssertionError(
                "四档适配失败：主面板尺寸未随分辨率缩小（小分辨率不应更大）。"
                f" panel 1920=({w1920:.2f},{h1920:.2f}) panel 1280=({w1280:.2f},{h1280:.2f})"
            )

        wb_ctx.close()
        browser.close()

    httpd.shutdown()
    return out

