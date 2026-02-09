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
            status = page.eval_on_selector("#exportWidgetListStatusText", "el => el ? String(el.textContent || '') : ''")
            tip = page.eval_on_selector("#exportWidgetListContainer", "el => el ? String(el.textContent || '') : ''")
            export_panel = page.eval_on_selector("#exportStatusTextArea", "el => (el && 'value' in el) ? String(el.value || '') : ''")
            raise TimeoutError(
                f"等待文本超时: selector={selector} expected~={expected_substring!r} got={val!r}\n"
                f"- exportWidgetListStatusText: {status!r}\n"
                f"- exportWidgetListContainer(text): {tip[:800]!r}\n"
                f"- exportStatusTextArea(value): {export_panel[:1200]!r}\n"
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


def test_ui_app_ui_preview_canvas_click_text_level_name_scrolls_export_widget_list() -> None:
    """
    复现/回归（用户反馈）：
    - 扁平化后，在画布里点击“第4关”（组件：text-level-name）时，
      左下角“导出控件”列表必须跳转/高亮到对应控件条目（而不是保持不动/不选中）。
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
        # 稳定选择目标文件：让预览页启动后自动打开
        context.add_init_script(f"window.localStorage.setItem('ui_preview:last_selected', 'project:{file_name}');")
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=20_000)

        # 固定画布尺寸（与用户复现场景一致）
        page.click("#sizeButton1600x900")
        page.click("#leftBottomTabExportWidgetsButton")

        # 等导出控件列表就绪
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)
        _wait_for_eval_true(
            page,
            "document.querySelectorAll('#exportWidgetListContainer .wb-tree-item[data-export-widget=\"1\"]').length > 0",
            timeout_ms=60_000,
        )

        # 确保已进入扁平预览并拥有 data-layer-key（否则画布点选不会触发稳定映射）
        page.click("#previewVariantFlattenedButton")
        # NOTE: 新版 Workbench 已移除“强制扁平化”按钮，扁平化由预览渲染统一入口按需生成/缓存。
        # 等待 iframe 内出现扁平层（data-layer-key 会由分组树索引后写入）。
        # 断言当前画布尺寸确实落在 1600×900（避免误点到隐藏的 display-area）
        _wait_for_eval_true(page, "document.getElementById('previewIframe').style.width === '1600px'", timeout_ms=10_000)
        _wait_for_eval_true(page, "document.getElementById('previewIframe').style.height === '900px'", timeout_ms=10_000)

        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area[data-size-key='1600x900'][style*='display: block']").first.wait_for(timeout=60_000, state="attached")
        frame.locator("[data-layer-key]").first.wait_for(timeout=60_000, state="attached")

        # 先把左下列表滚到一个“很可能不在目标项附近”的位置，避免“本来就在可视区”导致跳转缺陷被掩盖
        page.eval_on_selector("#exportWidgetListContainer", "el => { el.scrollTop = el.scrollHeight; }")
        before_scroll_top = int(page.evaluate("() => document.getElementById('exportWidgetListContainer').scrollTop || 0"))

        # 点击画布文字：第4关（组件 text-level-name）
        #
        # 关键：在 `ceshi_rect.html` 中，“关卡名/作者”等文本层的 hit-rect 可能存在重叠。
        # 因此这里不直接点 `.flat-text-inner`，而是：
        # - 先在 iframe 内找到“第4关”对应的 `data-debug-label="text-level-name"` 扁平层；
        # - 在其矩形内采样一个点，确保 `elementFromPoint` 命中该层（避免被相邻文本拦截）；
        # - 再把该点转换为顶层坐标做真实鼠标点击（触发预览的 elementFromPoint 选中逻辑）。
        # NOTE: headless 环境下 iframe 的 transform/scale 会让“顶层 mouse.click 坐标换算”出现不稳定。
        # 这里直接在 iframe 内 dispatch click，覆盖 Workbench 的“预览点击选中 -> 导出控件列表高亮/滚动”链路。
        click_result = page.evaluate(
            """() => {
  const iframe = document.getElementById('previewIframe');
  if (!iframe) return { ok: false, reason: 'no_iframe' };
  const doc = iframe.contentDocument;
  if (!doc) return { ok: false, reason: 'no_doc' };
  const area = doc.querySelector(".flat-display-area[data-size-key='1600x900'][style*='display: block']");
  if (!area) return { ok: false, reason: 'no_visible_area' };
  const candidates = Array.from(area.querySelectorAll(".flat-text[data-debug-label='text-level-name']"));
  if (!candidates || candidates.length <= 0) return { ok: false, reason: 'no_candidates' };
  let target = null;
  for (const c of candidates) {
    const t = String((c.textContent || '')).trim();
    if (t.includes('第4关') || t.includes('第四关')) { target = c; break; }
  }
  if (!target) {
    const sample = candidates.slice(0, 10).map(x => String((x.textContent || '')).trim()).filter(Boolean);
    return { ok: false, reason: 'no_target_level4', candidates: candidates.length, sample };
  }
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: doc.defaultView }));
  return { ok: true, debugLabel: String(target.getAttribute('data-debug-label')||''), text: String(target.textContent||'').trim() };
}"""
        )
        assert bool(click_result.get("ok")), f"无法点击 text-level-name：{click_result}"

        # 等待 selection_changed 回调生效（比等检查器文本更稳）
        _wait_for_last_selected_layer_key_non_empty(page, timeout_ms=10_000)

        # 检查器至少应包含组件名（证明点选确实命中目标层）
        _wait_for_eval_true(
            page,
            "String((document.getElementById('inspectorImportantTextArea')||{}).value||'').includes('text-level-name')",
            timeout_ms=10_000,
        )

        # 左下导出控件必须出现选中行，并且行文案里应包含 text-level-name
        selected_row = page.locator('#exportWidgetListContainer .wb-tree-item.selected[data-export-widget="1"]').first
        assert selected_row.count() == 1, "点击“第4关”后未选中任何导出控件条目（预期左下应跳转高亮）"
        selected_widget_id = (selected_row.get_attribute("data-widget-id") or "").strip()
        assert selected_widget_id, "选中条目缺失 data-widget-id"

        # 断言前置条件：导出控件列表中必须存在 text-level-name（否则用户期望的“跳到对应条目”无从实现）
        has_name_in_list = page.evaluate(
            "() => String((document.getElementById('exportWidgetListContainer')||{}).textContent||'').includes('text-level-name')"
        )
        assert bool(has_name_in_list), (
            "导出控件列表中不存在 text-level-name 条目：当前页面的导出模型未生成该控件，无法回归“画布点选 -> 列表跳转”。\n"
            f"- selected row text: {selected_row.inner_text()}\n"
        )

        # 若列表包含 text-level-name，则选中行也必须命中它（避免误选到 level-author）
        assert "text-level-name" in (selected_row.inner_text() or ""), (
            "画布点选 text-level-name 后，导出控件列表未选中对应条目（疑似误映射到 level-author）。\n"
            f"- selected row text: {selected_row.inner_text()}\n"
        )

        # 选中行必须处于容器可视区内（等价于“跳转/滚动已生效”）
        visible = page.evaluate(
            """() => {
  const container = document.getElementById('exportWidgetListContainer');
  const row = container ? container.querySelector('.wb-tree-item.selected[data-export-widget="1"]') : null;
  if (!container || !row) return { ok: false, reason: 'missing_dom' };
  const cr = container.getBoundingClientRect();
  const rr = row.getBoundingClientRect();
  const pad = 2;
  const ok = (rr.top >= cr.top - pad) && (rr.bottom <= cr.bottom + pad);
  return {
    ok,
    cr: { top: cr.top, bottom: cr.bottom },
    rr: { top: rr.top, bottom: rr.bottom },
    scrollTop: container.scrollTop,
    scrollHeight: container.scrollHeight,
    clientHeight: container.clientHeight,
  };
}"""
        )
        assert bool(visible.get("ok")), f"选中条目未滚动到可视区：{visible}"
        # 仅当容器确实可滚动时，才要求 scrollTop 发生变化（否则 scrollTop 恒为 0 是正常现象）。
        if before_scroll_top > 0 or int(visible.get("scrollHeight") or 0) > int(visible.get("clientHeight") or 0) + 2:
            after_scroll_top = int(page.evaluate("() => document.getElementById('exportWidgetListContainer').scrollTop || 0"))
            assert after_scroll_top != before_scroll_top, (
                "导出控件：点击画布后未发生任何滚动（用户肉眼等价于“没跳转”）。\n"
                f"- before scrollTop: {before_scroll_top}\n"
                f"- after scrollTop: {after_scroll_top}\n"
                f"- container clientHeight: {visible.get('clientHeight')}\n"
                f"- container scrollHeight: {visible.get('scrollHeight')}\n"
                f"- selected row text: {selected_row.inner_text()}\n"
            )

        context.close()
        browser.close()

    httpd.shutdown()

