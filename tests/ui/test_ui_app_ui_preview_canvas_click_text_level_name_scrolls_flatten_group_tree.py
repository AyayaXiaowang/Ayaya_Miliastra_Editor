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
            export_panel = page.eval_on_selector("#exportStatusTextArea", "el => (el && 'value' in el) ? String(el.value || '') : ''")
            raise TimeoutError(
                f"等待文本超时: selector={selector} expected~={expected_substring!r} got={val!r}\n"
                f"- flattenGroupTreeStatusText: {status!r}\n"
                f"- flattenGroupTreeContainer(text): {tip[:800]!r}\n"
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


def test_ui_app_ui_preview_canvas_click_text_level_name_scrolls_flatten_group_tree() -> None:
    """
    回归（用户需求）：
    - 扁平化后，在画布里点击“第4关”（组件：text-level-name）时，
      左下角“扁平分组”必须跳转/高亮到对应层条目（至少应展开父组并滚动到可视区）。
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

        # 固定画布尺寸（与用户复现场景一致）+ 切到“扁平分组”
        page.click("#sizeButton1600x900")
        page.click("#leftBottomTabFlattenGroupsButton")

        # 等待目标文件确实已被自动打开（否则强制扁平化按钮点击会是 no-op）
        _wait_for_eval_true(
            page,
            f"String((document.getElementById('selectedFileText')||{{}}).textContent||'').includes('{file_name}')",
            timeout_ms=60_000,
        )

        # 强制扁平化并等待完成（确保 iframe 内有 data-layer-key）
        page.click("#previewVariantFlattenedButton")
        # NOTE: 新版 Workbench 已移除“强制扁平化”按钮，扁平化由预览渲染统一入口按需生成/缓存。
        # 等待 iframe 内出现扁平层（data-layer-key 会由分组树索引后写入）。

        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area[data-size-key='1600x900'][style*='display: block']").first.wait_for(timeout=60_000, state="attached")
        frame.locator("[data-layer-key]").first.wait_for(timeout=60_000, state="attached")

        # 等扁平分组树就绪
        _wait_for_text(page, "#flattenGroupTreeStatusText", "已生成", timeout_ms=60_000)
        _wait_for_eval_true(
            page,
            "document.querySelectorAll('#flattenGroupTreeContainer .wb-tree-item[data-layer-key]').length > 0",
            timeout_ms=30_000,
        )

        # 先把左下列表滚到“很可能不在目标项附近”的位置，避免“本来就在可视区”掩盖跳转缺陷
        page.eval_on_selector("#flattenGroupTreeContainer", "el => { el.scrollTop = el.scrollHeight; }")
        before_scroll_top = int(page.evaluate("() => document.getElementById('flattenGroupTreeContainer').scrollTop || 0"))

        # 点击画布文字：第4关（组件 text-level-name）
        #
        # NOTE: headless 环境下 iframe 的 transform/scale 会让“顶层 mouse.click 坐标换算”出现不稳定。
        # 这里直接在 iframe 内 dispatch click，覆盖 Workbench 的“预览点击选中”核心链路（事件仍在 iframe 文档中触发）。
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

        picked_layer_key = _wait_for_last_selected_layer_key_non_empty(page, timeout_ms=10_000)

        # 检查器至少应包含组件名（证明点选确实命中目标层）
        _wait_for_eval_true(
            page,
            "String((document.getElementById('inspectorImportantTextArea')||{}).value||'').includes('text-level-name')",
            timeout_ms=10_000,
        )

        # 左下扁平分组必须出现选中行，并且滚动到可视区（否则用户看不到变化）
        _wait_for_eval_true(
            page,
            "document.querySelectorAll('#flattenGroupTreeContainer .wb-tree-item.selected[data-layer-key]').length === 1",
            timeout_ms=10_000,
        )

        meta = page.evaluate(
            """(pickedKey) => {
  const container = document.getElementById('flattenGroupTreeContainer');
  if (!container) return { ok: false, reason: 'no_container' };
  const row = container.querySelector('.wb-tree-item.selected[data-layer-key]');
  if (!row) return { ok: false, reason: 'no_selected_row' };
  const selectedKey = String(row.getAttribute('data-layer-key') || '').trim();
  const cr = container.getBoundingClientRect();
  const rr = row.getBoundingClientRect();
  const visibleTop = Math.max(cr.top, rr.top);
  const visibleBottom = Math.min(cr.bottom, rr.bottom);
  const visibleH = Math.max(0, visibleBottom - visibleTop);
  const ratio = (rr.height > 0) ? (visibleH / rr.height) : 0;

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
  const a = parseKey(pickedKey);
  const b = parseKey(selectedKey);
  let same = false;
  if (a && b && a.kind === b.kind) {
        // 扁平分组树的 layerKey 与预览层的 layerKey 在少数页面会出现“Y 口径漂移”（例如文本 baseline/行高归一化差异），
        // 这里允许 top 有更宽容的容差；但 left/width/height 仍按严格容差保证“对应同一块区域”。
        const eps = 0.6;
        const epsTop = 25.0;
    same = (
      Math.abs(a.left - b.left) <= eps &&
          Math.abs(a.top - b.top) <= epsTop &&
      Math.abs(a.width - b.width) <= eps &&
      Math.abs(a.height - b.height) <= eps
    );
  }
  const parentDetails = row.closest ? row.closest('details[data-group-key]') : null;
  const groupOpen = parentDetails ? !!parentDetails.open : null;
  return {
    ok: true,
    pickedKey: String(pickedKey || ''),
    selectedKey,
    approxSameKey: same,
    visibleRatio: ratio,
    scrollTop: container.scrollTop || 0,
    groupOpen,
    rowText: String(row.textContent || '').trim().slice(0, 200),
  };
}""",
            picked_layer_key,
        )
        assert bool(meta.get("ok")), f"无法获取扁平分组选中行信息：{meta}"
        assert "text-level-name" in str(meta.get("rowText") or ""), (
            "扁平分组：画布点选 text-level-name 后，左下高亮条目不是 text-level-name（用户肉眼等价于“选错”）。\n"
            f"- picked layerKey: {meta.get('pickedKey')}\n"
            f"- selected row layerKey: {meta.get('selectedKey')}\n"
            f"- rowText(sample): {meta.get('rowText')}\n"
        )
        assert ("第4关" in str(meta.get("rowText") or "")) or ("第四关" in str(meta.get("rowText") or "")), (
            "扁平分组：画布点选“第4关”后，左下高亮条目不是“第4关”（用户肉眼等价于“选错”）。\n"
            f"- picked layerKey: {meta.get('pickedKey')}\n"
            f"- selected row layerKey: {meta.get('selectedKey')}\n"
            f"- rowText(sample): {meta.get('rowText')}\n"
        )
        assert float(meta.get("visibleRatio") or 0.0) >= 0.4, (
            "扁平分组：选中行未滚动到足够可见（用户肉眼等价于“没跳转”）。\n"
            f"- meta: {meta}\n"
        )
        # 仅当容器确实可滚动时，才要求 scrollTop 发生变化（否则 scrollTop 恒为 0 是正常现象）。
        if before_scroll_top > 0:
            after_scroll_top = int(page.evaluate("() => document.getElementById('flattenGroupTreeContainer').scrollTop || 0"))
            assert after_scroll_top != before_scroll_top, (
                "扁平分组：点击画布后未发生任何滚动（用户肉眼等价于“没跳转”）。\n"
                f"- before scrollTop: {before_scroll_top}\n"
                f"- after scrollTop: {after_scroll_top}\n"
                f"- meta: {meta}\n"
            )
        assert meta.get("groupOpen") is True, (
            "扁平分组：选中行所在父组未展开（即便滚动了也可能看不到条目）。\n"
            f"- meta: {meta}\n"
        )

        context.close()
        browser.close()

    httpd.shutdown()

