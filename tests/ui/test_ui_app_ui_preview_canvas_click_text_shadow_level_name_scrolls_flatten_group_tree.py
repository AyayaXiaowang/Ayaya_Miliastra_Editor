from __future__ import annotations

import time

from tests._helpers.project_paths import get_repo_root
from tests._helpers.ui_preview_mock_server import start_ui_preview_mock_server


def _wait_for_text(page, selector: str, expected_substring: str, timeout_ms: int = 20_000) -> None:
    start = time.monotonic()
    while True:
        val = page.eval_on_selector(selector, "el => el ? String(el.textContent || '') : ''")
        if expected_substring in val:
            return
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            status = page.eval_on_selector("#flattenGroupTreeStatusText", "el => el ? String(el.textContent || '') : ''")
            tip = page.eval_on_selector("#flattenGroupTreeContainer", "el => el ? String(el.textContent || '') : ''")
            imp = page.eval_on_selector("#inspectorImportantTextArea", "el => (el && 'value' in el) ? String(el.value || '') : ''")
            raise TimeoutError(
                f"等待文本超时: selector={selector} expected~={expected_substring!r} got={val!r}\n"
                f"- flattenGroupTreeStatusText: {status!r}\n"
                f"- flattenGroupTreeContainer(text): {tip[:800]!r}\n"
                f"- inspectorImportantTextArea(value): {imp[:1200]!r}\n"
            )
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


def _wait_for_last_selected_layer_key_non_empty(page, timeout_ms: int = 10_000) -> str:
    start = time.monotonic()
    while True:
        got = page.evaluate("() => String((window.__wb_last_preview_selected_layer_key || '')).trim()")
        if str(got or "").strip():
            return str(got)
        if (time.monotonic() - start) * 1000.0 > timeout_ms:
            last = page.evaluate("() => window.__wb_last_preview_selected || null")
            imp = page.eval_on_selector("#inspectorImportantTextArea", "el => (el && 'value' in el) ? String(el.value || '') : ''")
            raise TimeoutError(
                "等待 window.__wb_last_preview_selected_layer_key 超时（预览点选未生效）。\n"
                f"- window.__wb_last_preview_selected: {last}\n"
                f"- inspectorImportantTextArea:\n{imp}\n"
            )
        time.sleep(0.05)


def test_ui_app_ui_preview_canvas_click_text_shadow_level_name_scrolls_flatten_group_tree() -> None:
    """
    回归（用户反馈）：
    - 扁平化后，在画布里点击“第2关”的阴影文字层（组件：text-shadow-level-name-0）时，
      左下角“扁平分组”必须高亮到对应层条目，而不是误选到 level-panel 等底层大面板。
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

        page.click("#sizeButton1600x900")
        page.click("#leftBottomTabFlattenGroupsButton")

        _wait_for_eval_true(
            page,
            f"String((document.getElementById('selectedFileText')||{{}}).textContent||'').includes('{file_name}')",
            timeout_ms=60_000,
        )

        page.click("#previewVariantFlattenedButton")

        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area[data-size-key='1600x900'][style*='display: block']").first.wait_for(timeout=60_000, state="attached")
        frame.locator("[data-layer-key]").first.wait_for(timeout=60_000, state="attached")

        _wait_for_text(page, "#flattenGroupTreeStatusText", "已生成", timeout_ms=60_000)
        _wait_for_eval_true(
            page,
            "document.querySelectorAll('#flattenGroupTreeContainer .wb-tree-item[data-layer-key]').length > 0",
            timeout_ms=30_000,
        )

        # 直接在 iframe 内 dispatch click（避免 headless 下坐标换算不稳定）
        click_result = page.evaluate(
            """() => {
  const iframe = document.getElementById('previewIframe');
  if (!iframe) return { ok: false, reason: 'no_iframe' };
  const doc = iframe.contentDocument;
  if (!doc) return { ok: false, reason: 'no_doc' };
  const area = doc.querySelector(".flat-display-area[data-size-key='1600x900'][style*='display: block']");
  if (!area) return { ok: false, reason: 'no_visible_area' };
  const candidates = Array.from(area.querySelectorAll(".flat-text.flat-text-shadow[data-debug-label='text-shadow-level-name-0']"));
  if (!candidates || candidates.length <= 0) return { ok: false, reason: 'no_candidates' };
  let target = null;
  for (const c of candidates) {
    const t = String((c.textContent || '')).trim();
    if (t.includes('第2关') || t.includes('第二关')) { target = c; break; }
  }
  if (!target) {
    const sample = candidates.slice(0, 10).map(x => String((x.textContent || '')).trim()).filter(Boolean);
    return { ok: false, reason: 'no_target_level2', candidates: candidates.length, sample };
  }
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: doc.defaultView }));
  return { ok: true, debugLabel: String(target.getAttribute('data-debug-label')||''), text: String(target.textContent||'').trim() };
}"""
        )
        assert bool(click_result.get("ok")), f"无法点击 text-shadow-level-name-0：{click_result}"

        _wait_for_last_selected_layer_key_non_empty(page, timeout_ms=10_000)

        # 检查器必须显示该组件名（证明点选命中的是 shadow 文本层，而不是底板）
        _wait_for_eval_true(
            page,
            "String((document.getElementById('inspectorImportantTextArea')||{}).value||'').includes('text-shadow-level-name-0')",
            timeout_ms=10_000,
        )

        _wait_for_eval_true(
            page,
            "document.querySelectorAll('#flattenGroupTreeContainer .wb-tree-item.selected[data-layer-key]').length === 1",
            timeout_ms=10_000,
        )

        meta = page.evaluate(
            """() => {
  const container = document.getElementById('flattenGroupTreeContainer');
  if (!container) return { ok: false, reason: 'no_container' };
  const row = container.querySelector('.wb-tree-item.selected[data-layer-key]');
  if (!row) return { ok: false, reason: 'no_selected_row' };
  const rowText = String(row.textContent || '').trim().slice(0, 260);
  return { ok: true, rowText };
}"""
        )
        assert bool(meta.get("ok")), f"无法获取扁平分组选中行信息：{meta}"
        assert "text-shadow-level-name-0" in str(meta.get("rowText") or ""), (
            "扁平分组：画布点选 text-shadow-level-name-0 后，左下高亮条目不是该阴影文字层。\n"
            f"- rowText(sample): {meta.get('rowText')}\n"
        )
        assert ("第2关" in str(meta.get("rowText") or "")) or ("第二关" in str(meta.get("rowText") or "")), (
            "扁平分组：画布点选“第2关”的阴影文字层后，左下高亮条目不是“第2关”。\n"
            f"- rowText(sample): {meta.get('rowText')}\n"
        )
        assert "level-panel" not in str(meta.get("rowText") or ""), (
            "扁平分组：画布点选 text-shadow-level-name-0 后，左下高亮误落在 level-panel。\n"
            f"- rowText(sample): {meta.get('rowText')}\n"
        )

        context.close()
        browser.close()

    httpd.shutdown()

