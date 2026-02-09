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


def _wait_for_last_selected_layer_key(page, expected: str, timeout_ms: int = 10_000) -> None:
    start = time.monotonic()
    while True:
        got = page.evaluate("() => String((window.__wb_last_preview_selected_layer_key || '')).trim()")
        if got == expected:
            return
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            last = page.evaluate("() => window.__wb_last_preview_selected || null")
            imp = page.eval_on_selector("#inspectorImportantTextArea", "el => (el && 'value' in el) ? String(el.value || '') : ''")
            raise AssertionError(
                "列表点击后，实际选中的 layerKey 与期望不一致。\n"
                f"- expected layerKey: {expected}\n"
                f"- got layerKey: {got}\n"
                f"- window.__wb_last_preview_selected: {last}\n"
                f"- inspectorImportantTextArea:\n{imp}\n"
            )
        time.sleep(0.05)


@pytest.mark.skipif(importlib.util.find_spec("playwright") is None, reason="requires playwright")
def test_ui_export_widget_list_click_selection_consistency_for_all_flattened_widgets() -> None:
    """
    全量回归：对导出控件列表里的所有 widgets（只测试具备 flat_layer_key 的条目），逐个点击并断言：
    - 列表条目的 data-flat-layer-key == 预览实际选中的 window.__wb_last_preview_selected_layer_key

    目标：根治“点击列表却选中全屏遮罩层（vote-overlay）/误选到底层大底板”等问题。
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()
    package_id = "示例项目模板"
    file_name = "ceshi_rect.html"

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id, host="127.0.0.1", port=0)
    base_url = f"http://127.0.0.1:{port}"
    entry_url = base_url + "/ui_app_ui_preview.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        context.add_init_script(
            "window.localStorage.setItem('ui_preview:last_selected', 'project:" + file_name + "');"
        )
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=20_000)

        # 固定画布尺寸（与问题复现场景一致）
        page.click("#sizeButton1600x900")

        # 等导出控件模型就绪
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)
        _wait_for_eval_true(page, "window.__wb_export_widget_preview_model && (window.__wb_export_widget_preview_model.groups||[]).length>0", timeout_ms=60_000)

        # 切到扁平预览（确保 iframe 内层可被定位）
        page.click("#previewVariantFlattenedButton")

        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area").first.wait_for(timeout=60_000, state="attached")
        frame.locator("[data-layer-key]").first.wait_for(timeout=60_000, state="attached")

        # 拉取“全量 widgets 清单”
        widgets = page.evaluate(
            """() => {
  const model = window.__wb_export_widget_preview_model || null;
  const groups = model ? (model.groups || []) : [];
  const out = [];
  for (let gi = 0; gi < groups.length; gi++) {
    const g = groups[gi] || {};
    const ws = g.widgets || [];
    for (let wi = 0; wi < ws.length; wi++) {
      const w = ws[wi] || {};
      const wid = String(w.widget_id || '').trim();
      const lk = String(w.flat_layer_key || w.__flat_layer_key || '').trim();
      if (!wid) continue;
      out.push({ widget_id: wid, flat_layer_key: lk });
    }
  }
  return out;
}"""
        )
        assert isinstance(widgets, list) and len(widgets) > 0, "导出控件模型 widgets 为空（无法回归）"

        # 逐个点击（只对具备 flat_layer_key 的做硬断言）
        tested = 0
        for item in widgets:
            wid = str(item.get("widget_id") or "").strip()
            expected_lk = str(item.get("flat_layer_key") or "").strip()
            if not wid:
                continue
            if not expected_lk:
                # 虚拟控件/缺失 key：无法做严格一致性断言，跳过
                continue

            row = page.locator(f'#exportWidgetListContainer [data-export-widget="1"][data-widget-id="{wid}"]').first
            if row.count() != 1:
                raise AssertionError(f"未找到导出控件列表条目: widget_id={wid!r}")
            row.scroll_into_view_if_needed()
            row.click()

            _wait_for_last_selected_layer_key(page, expected_lk, timeout_ms=10_000)
            tested += 1

        assert tested > 0, "没有任何带 flat_layer_key 的 widget 被测试到（异常）"

        context.close()
        browser.close()

    httpd.shutdown()

