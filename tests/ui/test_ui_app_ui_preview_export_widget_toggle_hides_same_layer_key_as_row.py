from __future__ import annotations

import importlib.util
import time

import pytest

from tests._helpers.project_paths import get_repo_root
from tests._helpers.ui_preview_mock_server import start_ui_preview_mock_server


def _wait_for_text(page, selector: str, expected_substring: str, timeout_ms: int = 20_000) -> None:
    start = time.monotonic()
    while True:
        val = page.eval_on_selector(selector, "el => el ? String(el.textContent || '') : ''")
        if expected_substring in val:
            return
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            raise TimeoutError(f"等待文本超时: selector={selector} expected~={expected_substring!r} got={val!r}")
        time.sleep(0.05)


def _wait_for_eval_true(page, expr_js: str, timeout_ms: int = 30_000) -> None:
    start = time.monotonic()
    while True:
        ok = page.evaluate(f"() => !!({expr_js})")
        if ok:
            return
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            raise TimeoutError(f"等待条件超时: {expr_js}")
        time.sleep(0.05)


@pytest.mark.skipif(importlib.util.find_spec("playwright") is None, reason="requires playwright")
def test_ui_app_ui_preview_export_widget_toggle_hides_same_layer_key_as_row() -> None:
    """
    回归：导出控件列表中点击“眼睛/隐藏”时，必须隐藏“该行 data-flat-layer-key 对应的扁平层”。
    也就是说：隐藏逻辑必须与选中/定位口径一致（用户点这行会选中谁，隐藏就隐藏谁）。
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()
    package_id = "示例项目模板"
    file_name = "ceshi_rect.html"

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id, host="127.0.0.1", port=0)
    entry_url = f"http://127.0.0.1:{port}/ui_app_ui_preview.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        context.add_init_script(f"window.localStorage.setItem('ui_preview:last_selected', 'project:{file_name}');")
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=20_000)

        page.click("#leftBottomTabExportWidgetsButton")
        page.click("#sizeButton1600x900")
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)

        # 切到扁平预览，等待 iframe 内出现 data-layer-key
        page.click("#previewVariantFlattenedButton")
        _wait_for_eval_true(
            page,
            """(() => {
  const f = document.getElementById('previewIframe');
  const d = f && f.contentDocument;
  if (!d) return false;
  const area = d.querySelector(".flat-display-area[data-size-key='1600x900'][style*='display: block']");
  if (!area) return false;
  return (area.querySelectorAll('[data-layer-key]').length || 0) > 0;
})()""",
            timeout_ms=120_000,
        )
        _wait_for_eval_true(page, "document.querySelectorAll('#exportWidgetListContainer [data-export-widget=\"1\"]').length >= 2", timeout_ms=30_000)

        picked = page.evaluate(
            """() => {
  const rows = Array.from(document.querySelectorAll('#exportWidgetListContainer [data-export-widget="1"][data-widget-id][data-flat-layer-key]'));
  const ok = rows.filter(r => String(r.getAttribute('data-flat-layer-key')||'').trim());
  if (ok.length < 2) return null;
  return {
    a: { widget_id: ok[0].getAttribute('data-widget-id'), flat_layer_key: ok[0].getAttribute('data-flat-layer-key') },
    b: { widget_id: ok[1].getAttribute('data-widget-id'), flat_layer_key: ok[1].getAttribute('data-flat-layer-key') },
  };
}"""
        )
        assert picked, f"未能从列表中挑选两个带 data-flat-layer-key 的条目：{picked}"

        a_wid = str(picked["a"]["widget_id"] or "").strip()
        a_lk = str(picked["a"]["flat_layer_key"] or "").strip()
        b_lk = str(picked["b"]["flat_layer_key"] or "").strip()
        assert a_wid and a_lk and b_lk

        # 点击 A 的眼睛
        eye = page.locator(f'.wb-tree-toggle[data-toggle-kind="widget"][data-widget-id="{a_wid}"]').first
        assert eye.count() == 1, f"未找到 widget 眼睛按钮: widget_id={a_wid!r}"
        eye.click()

        # A 的 layer 必须被隐藏，B 的 layer 必须仍可见
        _wait_for_eval_true(
            page,
            f"""(() => {{
  const f = document.getElementById('previewIframe');
  const d = f && f.contentDocument;
  if (!d) return false;
  const a = d.querySelector('[data-layer-key="{a_lk}"]');
  const b = d.querySelector('[data-layer-key="{b_lk}"]');
  if (!a || !b) return false;
  return (String(a.style.display||'') === 'none') && (String(b.style.display||'') !== 'none');
}})()""",
            timeout_ms=10_000,
        )

        context.close()
        browser.close()

    httpd.shutdown()

