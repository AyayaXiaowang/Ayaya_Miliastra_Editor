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


def test_ui_app_ui_preview_canvas_selection_maps_to_export_widget_by_layer_key() -> None:
    """
    回归：扁平模式下，点击画布顶部元素（例如文字层）时，
    左下角“导出控件”高亮必须命中同一条扁平层（以预览 iframe 的实际 `data-layer-key` 为准），不能误选到底层大底板/组容器。
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()

    # 约定：tests/ui 目录下多数 UI Web 用例默认使用“示例项目模板/”（入库的公共样例包）
    package_id = "示例项目模板"

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id, host="127.0.0.1", port=0)
    base_url = f"http://127.0.0.1:{port}"
    entry_url = base_url + "/ui_app_ui_preview.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = context.new_page()
        page.goto(entry_url, wait_until="load", timeout=20_000)

        # 选中一个已知页面（测试项目里常用：2.html）
        page.wait_for_selector('#fileList button.item[data-scope="project"][data-file-name="2.html"]', timeout=20_000)
        page.click('#fileList button.item[data-scope="project"][data-file-name="2.html"]')

        # 等待“导出控件列表”生成完成（避免旧缓存/未生成状态下断言）
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=30_000)
        # 稳健性：显式刷新一次，确保当前文件对应的模型与索引已更新（避免“已生成”来自旧选择的误判）
        page.click("#refreshExportWidgetListButton")
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)

        # 固定画布尺寸，保证 group_tree 能在对应 data-size-key 的 .flat-display-area 上建立索引
        page.click("#sizeButton1600x900")
        # 画布尺寸变更会触发导出控件列表强制刷新（依赖 canvas size）；等待其重新生成完成。
        _wait_for_text(page, "#exportWidgetListStatusText", "已生成", timeout_ms=60_000)

        # 强制切到“扁平化”预览并生成最新扁平层（避免旧缓存/无 layerKey）
        page.click("#previewVariantFlattenedButton")
        # NOTE: 新版 Workbench 已移除“强制扁平化”按钮，扁平化由预览渲染统一入口按需生成/缓存。
        # 等待 iframe 内出现扁平层（data-layer-key 会由分组树索引后写入）。
        frame = page.frame_locator("#previewIframe")
        frame.locator(".flat-display-area").first.wait_for(timeout=60_000, state="attached")
        # 等待至少出现一个扁平层（不要求 visible：某些缩放/布局下 Playwright 可能判定为 hidden）
        frame.locator(".flat-shadow, .flat-border, .flat-element, .flat-text").first.wait_for(timeout=60_000, state="attached")
        frame.locator("[data-layer-key]").first.wait_for(timeout=60_000, state="attached")

        # 从“导出控件列表”中挑一个 data-flat-layer-key（这些 key 口径应与 iframe 内 data-layer-key 一致）
        list_layer_keys = page.evaluate(
            """() => {
  const nodes = Array.from(document.querySelectorAll('#exportWidgetListContainer [data-export-widget="1"][data-flat-layer-key]'));
  const out = [];
  for (const n of nodes) {
    const k = String(n.getAttribute('data-flat-layer-key') || '').trim();
    if (k) out.push(k);
  }
  return out;
}"""
        )
        assert isinstance(list_layer_keys, list) and len(list_layer_keys) > 0, "导出控件列表中未找到任何 data-flat-layer-key（无法做映射回归）"

        # 在 iframe 内找到第一个 layerKey 命中的扁平层并触发点击
        clicked_layer_key = frame.locator("body").evaluate(
            """(body, keys) => {
  const arr = Array.isArray(keys) ? keys : [];
  const set = new Set();
  for (const k0 of arr) {
    const k = String(k0 || '').trim();
    if (k) set.add(k);
  }
  // 优先选择“更接近用户真实点选”的层：文本 > 主体 > 边框 > 阴影
  const selectors = [
    '.flat-text[data-layer-key]',
    '.flat-element[data-layer-key]',
    '.flat-border[data-layer-key]',
    '.flat-shadow[data-layer-key]',
  ];
  for (const sel of selectors) {
    const els = Array.from(body.querySelectorAll(sel));
    for (const el of els) {
      const k = String((el.dataset && el.dataset.layerKey) ? el.dataset.layerKey : '').trim();
      if (!k) continue;
      if (!set.has(k)) continue;
      el.scrollIntoView({ block: 'center', inline: 'center' });
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
      return k;
    }
  }
  return '';
}""",
            list_layer_keys,
        )
        clicked_layer_key = str(clicked_layer_key or "").strip()
        assert clicked_layer_key, "未能在预览画布中找到任何与导出控件列表一致的 data-layer-key"

        # 确保 selection_changed 回调已跑完
        picked_layer_key = _wait_for_last_selected_layer_key_non_empty(page, timeout_ms=10_000)
        assert picked_layer_key == clicked_layer_key, (
            "预览实际选中的 layerKey 与触发点击的目标不一致（疑似误点/被遮挡拦截）：\n"
            f"- clicked layerKey: {clicked_layer_key}\n"
            f"- picked layerKey: {picked_layer_key}\n"
        )

        # 左下“导出控件”里当前高亮行必须对应同一个 flat_layer_key
        selected_row = page.locator(
            '#exportWidgetListContainer .wb-tree-item.selected[data-export-widget="1"][data-flat-layer-key]'
        ).first
        assert selected_row.count() == 1, "未找到导出控件列表的选中行（.wb-tree-item.selected[data-export-widget='1']）"

        selected_widget_id = (selected_row.get_attribute("data-widget-id") or "").strip()
        assert selected_widget_id, "选中行缺失 data-widget-id"
        selected_flat_layer_key = (selected_row.get_attribute("data-flat-layer-key") or "").strip()
        assert selected_flat_layer_key, "选中行缺失 data-flat-layer-key"
        assert selected_flat_layer_key == clicked_layer_key, (
            "画布点选与导出控件高亮不是“精确 layerKey 匹配”（会导致点上层选中底层）：\n"
            f"- clicked layerKey: {clicked_layer_key}\n"
            f"- selected row data-flat-layer-key: {selected_flat_layer_key}\n"
            f"- selected row widgetId: {selected_widget_id}\n"
        )

        context.close()
        browser.close()

    httpd.shutdown()

