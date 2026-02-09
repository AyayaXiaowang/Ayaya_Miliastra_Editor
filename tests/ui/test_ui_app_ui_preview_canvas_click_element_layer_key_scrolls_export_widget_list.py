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


def test_ui_app_ui_preview_canvas_click_element_layer_key_scrolls_export_widget_list() -> None:
    """
    用户补充回归：
    - 扁平化后，点选画布上的 element 层（用户现场提供 layer_key），右侧检查器会更新；
      同时左下角“导出控件”也必须跳转/高亮到对应条目（避免“只更新检查器但列表没反应”）。

    注意：layerKey 在不同环境/字体/舍入口径下可能轻微漂移，因此此用例会：
    - 先把目标 layerKey 解析为 rect/z；
    - 在 iframe 内用“最近邻”方式挑选最接近的 `.flat-element` 来执行点击；
    - 再以“实际点选到的 layerKey”作为后续断言真源。
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()
    package_id = "示例项目模板"
    file_name = "ceshi_rect.html"

    # 用户现场提供（目标区域）：element 层
    target_layer_key = "element__203.31__463.88__508.63__63.31__235"

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id, host="127.0.0.1", port=0)
    entry_url = f"http://127.0.0.1:{port}/ui_app_ui_preview.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        context.add_init_script(f"window.localStorage.setItem('ui_preview:last_selected', 'project:{file_name}');")
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=20_000)

        page.click("#sizeButton1600x900")
        page.click("#leftBottomTabExportWidgetsButton")

        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)
        _wait_for_eval_true(
            page,
            "window.__wb_export_widget_preview_model && (window.__wb_export_widget_preview_model.groups||[]).length>0",
            timeout_ms=60_000,
        )

        page.click("#previewVariantFlattenedButton")
        _wait_for_eval_true(page, "document.getElementById('previewIframe').style.width === '1600px'", timeout_ms=10_000)
        _wait_for_eval_true(page, "document.getElementById('previewIframe').style.height === '900px'", timeout_ms=10_000)

        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area[data-size-key='1600x900'][style*='display: block']").first.wait_for(timeout=60_000, state="attached")
        frame.locator("[data-layer-key]").first.wait_for(timeout=60_000, state="attached")

        # 先把列表滚到底部，确保“跳转”可被观察到（若可滚动）
        page.eval_on_selector("#exportWidgetListContainer", "el => { el.scrollTop = el.scrollHeight; }")

        click_pt = page.evaluate(
            """(targetKey) => {
  function parseKey(k) {
    const s = String(k || '').trim();
    const parts = s.split('__');
    if (parts.length < 6) return null;
    const kind = String(parts[0] || '').trim();
    const left = Number(parts[1]);
    const top = Number(parts[2]);
    const width = Number(parts[3]);
    const height = Number(parts[4]);
    const z = Number(parts[5]);
    if (!kind) return null;
    if (![left, top, width, height].every(Number.isFinite)) return null;
    return { kind, left, top, width, height, z: Number.isFinite(z) ? z : 0 };
  }
  const want = parseKey(targetKey);
  if (!want) return { ok: false, reason: 'bad_target_key', targetKey };

  const iframe = document.getElementById('previewIframe');
  if (!iframe) return { ok: false, reason: 'no_iframe' };
  const doc = iframe.contentDocument;
  if (!doc) return { ok: false, reason: 'no_doc' };
  const area = doc.querySelector(".flat-display-area[data-size-key='1600x900'][style*='display: block']");
  if (!area) return { ok: false, reason: 'no_visible_area' };

  const iw = iframe.clientWidth || 0;
  const ih = iframe.clientHeight || 0;
  const ir = iframe.getBoundingClientRect();
  if (!(iw > 0) || !(ih > 0) || !(ir.width > 0) || !(ir.height > 0)) {
    return { ok: false, reason: 'bad_iframe_rect', iw, ih, ir: { w: ir.width, h: ir.height } };
  }
  const scaleX = ir.width / iw;
  const scaleY = ir.height / ih;

  // 关键：预览的“画布点选”会在候选层中按优先级选择（文本 > element > border > shadow）。
  // 因此这里不尝试“直接点到 element DOM”（它可能 pointer-events:none），而是搜索一个点击点，使得选择结果为 element__...，
  // 且几何上尽量接近用户提供的目标 rect。
  function parsePicked(pickedKey) {
    const s = String(pickedKey || '').trim();
    const parts = s.split('__');
    if (parts.length < 6) return null;
    const kind = String(parts[0] || '').trim();
    const left = Number(parts[1]);
    const top = Number(parts[2]);
    const width = Number(parts[3]);
    const height = Number(parts[4]);
    const z = Number(parts[5]);
    if (!kind) return null;
    if (![left, top, width, height].every(Number.isFinite)) return null;
    return { kind, left, top, width, height, z: Number.isFinite(z) ? z : 0 };
  }

  function metricForPicked(p) {
    if (!p) return Number.POSITIVE_INFINITY;
    return Math.abs(p.left - want.left) + Math.abs(p.top - want.top) + Math.abs(p.width - want.width) + Math.abs(p.height - want.height) + Math.abs(p.z - want.z) * 0.01;
  }

  function dispatchClickAt(x, y) {
    const t = doc.elementFromPoint(x, y) || doc.body;
    if (!t) return false;
    const ev = new MouseEvent('click', { bubbles: true, cancelable: true, view: doc.defaultView, clientX: x, clientY: y });
    t.dispatchEvent(ev);
    return true;
  }

  const pad = 2;
  const left = Math.max(0, Math.floor(want.left + pad));
  const top = Math.max(0, Math.floor(want.top + pad));
  const right = Math.min(iw - 1, Math.ceil(want.left + want.width - pad));
  const bottom = Math.min(ih - 1, Math.ceil(want.top + want.height - pad));
  if (!(right > left) || !(bottom > top)) {
    return { ok: false, reason: 'degenerate_target_rect', want };
  }

  let best = null;
  let bestMetric = Number.POSITIVE_INFINITY;
  let lastKey = '';

  const steps = 10; // -> 11x11
  for (let yi = 0; yi <= steps; yi++) {
    for (let xi = 0; xi <= steps; xi++) {
      const x = left + Math.round((right - left) * (xi / steps));
      const y = top + Math.round((bottom - top) * (yi / steps));
      if (!dispatchClickAt(x, y)) continue;

      const pickedKey = String((window.__wb_last_preview_selected_layer_key || '')).trim();
      if (!pickedKey) continue;
      lastKey = pickedKey;
      const p = parsePicked(pickedKey);
      if (!p) continue;
      if (String(p.kind || '') !== 'element') continue;
      const m = metricForPicked(p);
      if (m < bestMetric) {
        bestMetric = m;
        best = { x, y, pickedKey };
      }
    }
  }

  if (!best) {
    return { ok: false, reason: 'no_element_selection_point', lastKey };
  }

  const clickX = ir.left + best.x * scaleX;
  const clickY = ir.top + best.y * scaleY;
  return { ok: true, clickX, clickY, pickedKey: best.pickedKey, metric: bestMetric };
}""",
            target_layer_key,
        )
        assert bool(click_pt.get("ok")), f"无法计算目标 element 的可点击坐标：{click_pt}"
        page.mouse.click(float(click_pt["clickX"]), float(click_pt["clickY"]))

        picked_layer_key = _wait_for_last_selected_layer_key_non_empty(page, timeout_ms=10_000)
        assert picked_layer_key.startswith("element__"), f"预期点到 element 层，但实际选中为：{picked_layer_key}"

        # 左下导出控件必须出现选中行
        selected_row = page.locator('#exportWidgetListContainer .wb-tree-item.selected[data-export-widget="1"]').first
        assert selected_row.count() == 1, "点击 element 层后未选中任何导出控件条目（预期左下应跳转高亮）"

        # 若我们能拿到 debugLabel，则导出控件条目文本至少应包含它（避免误跳到完全无关条目）
        dbg = str(click_pt.get("debugLabel") or "").strip()
        if dbg:
            assert dbg in (selected_row.inner_text() or ""), (
                "导出控件：点击 element 层后，高亮条目未包含对应 debug_label（疑似映射到无关控件）。\n"
                f"- debug_label: {dbg}\n"
                f"- selected row text: {selected_row.inner_text()}\n"
            )

        # 选中行必须处于可视区内（用户肉眼能看到高亮）
        visible = page.evaluate(
            """() => {
  const container = document.getElementById('exportWidgetListContainer');
  const row = container ? container.querySelector('.wb-tree-item.selected[data-export-widget="1"]') : null;
  if (!container || !row) return { ok: false, reason: 'missing_dom' };
  const cr = container.getBoundingClientRect();
  const rr = row.getBoundingClientRect();
  const pad = 2;
  const ok = (rr.top >= cr.top - pad) && (rr.bottom <= cr.bottom + pad);
  return { ok, cr: { top: cr.top, bottom: cr.bottom }, rr: { top: rr.top, bottom: rr.bottom }, scrollTop: container.scrollTop };
}"""
        )
        assert bool(visible.get("ok")), f"选中条目未滚动到可视区：{visible}"

        context.close()
        browser.close()

    httpd.shutdown()

