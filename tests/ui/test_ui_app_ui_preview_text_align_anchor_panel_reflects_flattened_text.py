from __future__ import annotations

import time

from tests._helpers.project_paths import get_repo_root
from tests._helpers.ui_preview_mock_server import start_ui_preview_mock_server


def _wait_for_text(page, selector: str, expected_substring: str, timeout_ms: int = 30_000) -> None:
    start = time.monotonic()
    while True:
        val = page.eval_on_selector(selector, "el => el ? String(el.textContent || '') : ''")
        if expected_substring in val:
            return
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            raise TimeoutError(f"等待文本超时: selector={selector} expected~={expected_substring!r} got={val!r}")
        time.sleep(0.05)


def _wait_for_active_text_align_button(page, expected_h: str, expected_v: str, timeout_ms: int = 10_000) -> None:
    expected_h = str(expected_h or "").strip().lower()
    expected_v = str(expected_v or "").strip().lower()
    start = time.monotonic()
    while True:
        got = page.evaluate(
            """() => {
  const g = document.getElementById('textAlignGrid');
  if (!g) return null;
  const btn = g.querySelector('button.active[data-h][data-v]');
  const h = btn ? String(btn.getAttribute('data-h') || '').trim().toLowerCase() : '';
  const v = btn ? String(btn.getAttribute('data-v') || '').trim().toLowerCase() : '';
  return { h, v };
}"""
        )
        if isinstance(got, dict) and str(got.get("h") or "").lower() == expected_h and str(got.get("v") or "").lower() == expected_v:
            return
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            hint = page.eval_on_selector("#textAlignHint", "el => el ? String(el.textContent || '') : ''")
            raise TimeoutError(
                "等待文本对齐锚点面板刷新超时：\n"
                f"- expected: ({expected_h}, {expected_v})\n"
                f"- got: {got!r}\n"
                f"- hint: {hint!r}\n"
            )
        time.sleep(0.05)


def test_ui_app_ui_preview_text_align_anchor_panel_reflects_flat_text_inner_flex_alignment() -> None:
    """
    回归：右侧“文本对齐锚点（3×3）”面板必须展示“扁平化后的真实对齐”，而不是永远卡在左中。

    典型场景：
    - 预览侧点选扁平化文本层时，selection 会把 `.flat-text-inner` 提升为外层 `.flat-text`；
    - 但扁平化产物把对齐样式（display:flex + justify-content/align-items + text-align）写在 `.flat-text-inner`；
    - 因此检查器必须回看 inner 的 computedStyle，才能正确高亮 3×3。
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()
    package_id = "示例项目模板"

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id, host="127.0.0.1", port=0)
    entry_url = f"http://127.0.0.1:{port}/ui_app_ui_preview.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=20_000)

        # 选中一个已知包含“退出/关卡选择”的页面（示例项目模板/1.html）。
        page.wait_for_selector('#fileList button.item[data-scope="project"][data-file-name="1.html"]', timeout=20_000)
        page.click('#fileList button.item[data-scope="project"][data-file-name="1.html"]')

        # 等待导出控件列表生成完成，确保预览状态机已就绪（避免旧选择残留导致误判）。
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)

        # 固定画布尺寸，确保扁平层与 UI 一致（同多数回归用例口径）。
        page.click("#sizeButton1600x900")
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)

        # 切到扁平化预览，并等待扁平层注入完成。
        page.click("#previewVariantFlattenedButton")
        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area").first.wait_for(timeout=60_000, state="attached")
        frame.locator(".flat-text-inner").first.wait_for(timeout=60_000, state="attached")

        # 点击“退出”按钮的扁平文本层（排除 shadow 文本层，避免 pointer-events:none 干扰）。
        # 说明：扁平化预览切换/刷新可能导致 iframe 内 DOM 重建；因此这里用 frame.evaluate 做“查找+点击”原子操作，
        # 避免 Locator 在 scroll/click 前后跨一次渲染而变成 detached。
        clicked = frame.locator("body").evaluate(
            """(body) => {
  const candidates = Array.from(body.querySelectorAll('.flat-text:not(.flat-text-shadow)[data-debug-label*="btn-text"] .flat-text-inner'));
  for (const el of candidates) {
    const t = String(el ? (el.textContent || '') : '').trim();
    if (t !== '退出') continue;
    el.scrollIntoView({ block: 'center', inline: 'center' });
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    return true;
  }
  return false;
}"""
        )
        if clicked is not True:
            raise AssertionError("未在扁平化预览中找到可点击的 btn-text 文本层：'退出'")

        # 断言右侧对齐锚点面板高亮为“居中”（data-ui-text-align/valign 显式标注 -> 扁平产物 flex 对齐）。
        _wait_for_active_text_align_button(page, expected_h="center", expected_v="middle", timeout_ms=10_000)

        context.close()
        browser.close()

    httpd.shutdown()

