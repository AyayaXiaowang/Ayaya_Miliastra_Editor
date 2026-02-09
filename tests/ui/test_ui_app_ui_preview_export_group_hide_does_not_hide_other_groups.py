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
def test_ui_app_ui_preview_export_group_hide_does_not_hide_other_groups() -> None:
    """
    回归：在“导出控件”视图点击某个组的“眼睛”隐藏时，
    不应误把其它组的 layer 一起隐藏（常见原因：groupKey 撞名/口径不一致导致 setGroupHidden 误伤）。
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
        _wait_for_eval_true(
            page,
            "window.__wb_export_widget_preview_model && (window.__wb_export_widget_preview_model.groups||[]).length>=2",
            timeout_ms=60_000,
        )

        # 切到扁平预览，等待 layerKey 可用
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

        info = page.evaluate(
            """() => {
  const model = window.__wb_export_widget_preview_model || null;
  if (!model) return null;
  const groups = model.groups || [];
  // pick first two groups that have at least one widget with flat_layer_key
  function firstLayerKey(g) {
    const ws = g && g.widgets ? g.widgets : [];
    for (const w of ws) {
      const lk = String(w.flat_layer_key || w.__flat_layer_key || '').trim();
      if (lk) return lk;
    }
    return '';
  }
  let g1 = null;
  let g2 = null;
  for (const g of groups) {
    if (!g) continue;
    const lk = firstLayerKey(g);
    if (!lk) continue;
    if (!g1) { g1 = g; continue; }
    if (!g2 && String(g.group_key||'') !== String(g1.group_key||'')) { g2 = g; break; }
  }
  if (!g1 || !g2) return null;
  return {
    g1: { group_key: String(g1.group_key||''), layer_key: firstLayerKey(g1) },
    g2: { group_key: String(g2.group_key||''), layer_key: firstLayerKey(g2) },
  };
}"""
        )
        assert info and info.get("g1") and info.get("g2"), f"无法挑选两个可测试的组：{info}"

        g1_key = str(info["g1"]["group_key"]).strip()
        g1_lk = str(info["g1"]["layer_key"]).strip()
        g2_lk = str(info["g2"]["layer_key"]).strip()
        assert g1_key and g1_lk and g2_lk

        # 点击 g1 的组级眼睛（隐藏）
        btn = page.locator(f'.wb-tree-toggle[data-toggle-kind="group"][data-group-key="{g1_key}"]').first
        assert btn.count() == 1, f"未找到组级眼睛按钮: group_key={g1_key!r}"
        btn.click()

        # 断言：g2 的 layer 仍可见（display != none）
        _wait_for_eval_true(
            page,
            f"""(() => {{
  const f = document.getElementById('previewIframe');
  const d = f && f.contentDocument;
  if (!d) return false;
  const el = d.querySelector('[data-layer-key="{g2_lk}"]');
  if (!el) return false;
  return String(el.style.display || '') !== 'none';
}})()""",
            timeout_ms=10_000,
        )

        context.close()
        browser.close()

    httpd.shutdown()

