from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests._helpers.project_paths import get_repo_root
from tests._helpers.ui_preview_mock_server import start_ui_preview_mock_server


@dataclass(frozen=True, slots=True)
class _SpanText:
    text: str
    attrs: dict[str, str]


class _SpanTextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, dict[str, str]]] = []
        self._buf: list[str] = []
        self.items: list[_SpanText] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "span":
            return
        attr_map: dict[str, str] = {}
        for k, v in attrs:
            if not k:
                continue
            attr_map[str(k)] = "" if v is None else str(v)
        cls = str(attr_map.get("class") or "")
        if "btn-text" not in cls.split():
            return
        # 只收集“按钮中间的单独文本”：span.btn-text 本身直接承载文本（不关心子孙节点）。
        self._stack.append((tag.lower(), attr_map))
        self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        if tag.lower() != "span":
            return
        _tag, attr_map = self._stack.pop()
        text = "".join(self._buf).strip()
        self._buf = []
        if text:
            self.items.append(_SpanText(text=text, attrs=attr_map))

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        self._buf.append(str(data or ""))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_btn_text_has_explicit_centering(*, html_text: str, expected_texts: list[str]) -> None:
    parser = _SpanTextCollector()
    parser.feed(html_text)
    found: dict[str, list[_SpanText]] = {t: [] for t in expected_texts}
    for it in parser.items:
        if it.text in found:
            found[it.text].append(it)

    missing = [t for t, items in found.items() if not items]
    if missing:
        raise AssertionError(f"未在 span.btn-text 中找到文本：{missing!r}")

    for t, items in found.items():
        for it in items:
            h = str(it.attrs.get("data-ui-text-align") or "").strip().lower()
            v = str(it.attrs.get("data-ui-text-valign") or "").strip().lower()
            if h != "center" or v not in ("middle", "center"):
                raise AssertionError(
                    f"span.btn-text 文本={t!r} 缺少显式居中标注："
                    f"data-ui-text-align={h!r} data-ui-text-valign={v!r} attrs={it.attrs!r}"
                )


def test_ui_html_top_actions_btn_text_has_explicit_centering_attrs() -> None:
    """
    目的：对“左上角 退出/关卡选择 的按钮文字”做静态合同校验：
    - 必须显式标注 data-ui-text-align/valign，避免扁平化/导出后 TextBox 退回左上对齐。
    """
    repo_root = get_repo_root()
    ui_dir = repo_root / "assets" / "资源库" / "项目存档" / "示例项目模板" / "管理配置" / "UI源码"
    files = ["1.html", "2.html", "3.html", "ceshi_rect.html"]

    for name in files:
        p = (ui_dir / name).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"UI源码缺失：{p}")
        _assert_btn_text_has_explicit_centering(
            html_text=_read_text(p),
            expected_texts=["退出", "关卡选择"],
        )


def test_ui_html_header_labels_have_explicit_centering_attrs() -> None:
    """
    静态合同：顶部栏的“房名/倒计时/标题”等标签通常是“单矩形内只有一个文本”，必须显式居中。
    """
    repo_root = get_repo_root()
    ui_dir = repo_root / "assets" / "资源库" / "项目存档" / "示例项目模板" / "管理配置" / "UI源码"

    def _assert_has_attrs(file_path: Path, data_ui_keys: list[str]) -> None:
        html_text = _read_text(file_path)
        for k in data_ui_keys:
            pattern = re.compile(
                r'<[^>]+\bdata-ui-key\s*=\s*"' + re.escape(k) + r'"[^>]*\bdata-ui-text-align\s*=\s*"center"[^>]*\bdata-ui-text-valign\s*=\s*"middle"[^>]*>',
                re.IGNORECASE,
            )
            if not pattern.search(html_text):
                raise AssertionError(
                    f"[{file_path.name}] data-ui-key={k!r} 未显式声明 data-ui-text-align/valign=居中"
                )

    _assert_has_attrs((ui_dir / "1.html").resolve(), data_ui_keys=["room_title", "room_timer"])
    _assert_has_attrs((ui_dir / "3.html").resolve(), data_ui_keys=["header_title", "room_title", "room_timer_text"])


@pytest.mark.skipif(importlib.util.find_spec("playwright") is None, reason="requires playwright")
def test_ui_top_actions_textboxes_export_alignment_is_centered() -> None:
    """
    目的：端到端验证“显式对齐标注”真的影响导出 TextBox：
    - 对 1/2/3.html：强制扁平化后读取 export_widget_preview_model
    - 找到文本内容为“退出/关卡选择”的 TextBox，并断言 alignment_h/v 为居中
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()
    package_id = "示例项目模板"
    files = ["1.html", "2.html", "3.html"]
    timeout_ms = 120_000

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id, host="127.0.0.1", port=0)
    entry_url = f"http://127.0.0.1:{port}/ui_app_ui_preview.html"

    def _strip_rich_text(text: str) -> str:
        return re.sub(r"<[^>]+>", "", str(text or "")).strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for file_name in files:
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            context.add_init_script(f"window.localStorage.setItem('ui_preview:last_selected', 'project:{file_name}');")
            page = context.new_page()
            page.goto(entry_url, wait_until="load", timeout=20_000)

            # 该预览页已移除“强制扁平化”按钮：选中文件时会自动 renderPreview + 刷新导出控件列表。
            # 因此这里等待：
            # - selectedFileText 切换到当前 file
            # - exportWidgetListStatusText 变为 “已生成”
            # - export_widget_preview_model 就绪
            start = page.evaluate("() => Date.now()")
            while True:
                selected_text = page.eval_on_selector("#selectedFileText", "el => el ? String(el.textContent || '') : ''")
                status_text = page.eval_on_selector("#exportWidgetListStatusText", "el => el ? String(el.textContent || '') : ''")
                model_ok = page.evaluate(
                    """() => {
  const m = window.__wb_export_widget_preview_model || null;
  const groups = m && m.groups ? m.groups : [];
  return !!(m && groups && groups.length > 0);
}"""
                )
                if (("project:" + file_name) in selected_text or file_name in selected_text) and ("已生成" in status_text) and bool(model_ok):
                    break
                now = page.evaluate("() => Date.now()")
                if int(now) - int(start) > timeout_ms:
                    raise TimeoutError(
                        f"[{file_name}] 等待预览就绪超时：selected={selected_text!r} status={status_text!r} model_ok={model_ok!r}"
                    )

            model = page.evaluate("() => window.__wb_export_widget_preview_model || null")
            if not model:
                raise RuntimeError(f"[{file_name}] 未获取到 export_widget_preview_model")

            # 端到端口径：直接调用导出链路生成 bundlePayload，再从 payload 中检查 TextBox 的 alignment。
            result = page.evaluate(
                """
                async () => {
                  const mod = await import('/src/ui_app_ui_preview/bundle.js');
                  const res = await mod.buildBundlePayloadForCurrentSelection();
                  if (!res || res.ok !== true) {
                    return { ok: false, error: res ? String(res.error || '') : 'no result' };
                  }
                  const bundle = res.bundlePayload || {};
                  const templates = Array.isArray(bundle.templates) ? bundle.templates : [];
                  const hits = [];
                  function stripTags(s) { return String(s || '').replace(/<[^>]+>/g, '').trim(); }
                  for (const tpl of templates) {
                    const ws = (tpl && tpl.widgets) ? tpl.widgets : [];
                    for (const w of ws) {
                      if (!w) continue;
                      if (String(w.widget_type || '') !== '文本框') continue;
                      const s = (w.settings || {});
                      const txt = stripTags(String(s.text_content || ''));
                      if (txt !== '退出' && txt !== '关卡选择') continue;
                      hits.push({
                        text: txt,
                        ui_key: String(w.ui_key || ''),
                        widget_name: String(w.widget_name || ''),
                        alignment_h: String(s.alignment_h || ''),
                        alignment_v: String(s.alignment_v || ''),
                      });
                    }
                  }
                  return { ok: true, hits };
                }
                """
            )

            if not result or result.get("ok") is not True:
                raise AssertionError(f"[{file_name}] buildBundlePayloadForCurrentSelection 失败：{result!r}")

            hits = result.get("hits") or []
            by_text: dict[str, list[dict]] = {"退出": [], "关卡选择": []}
            for h in hits:
                t = _strip_rich_text(str(h.get("text") or ""))
                if t in by_text:
                    by_text[t].append(h)

            for t in ["退出", "关卡选择"]:
                items = by_text[t]
                if not items:
                    raise AssertionError(f"[{file_name}] bundlePayload 中未找到文本={t!r} 的 TextBox（可能被合并为其它控件类型）")
                for h in items:
                    if str(h.get("alignment_h") or "") != "水平居中" or str(h.get("alignment_v") or "") != "垂直居中":
                        raise AssertionError(
                            f"[{file_name}] bundlePayload TextBox 文本={t!r} 对齐不为居中："
                            f"alignment_h={h.get('alignment_h')!r} alignment_v={h.get('alignment_v')!r} "
                            f"ui_key={h.get('ui_key')!r} name={h.get('widget_name')!r}"
                        )

            context.close()

        browser.close()

    httpd.shutdown()


@pytest.mark.skipif(importlib.util.find_spec("playwright") is None, reason="requires playwright")
def test_ui_top_actions_flat_text_preview_alignment_is_centered() -> None:
    """
    目的：回归 Workbench 扁平化预览层（flat-text）对齐也要吃 data-ui-text-align/valign。

    用户痛点：即便导出 TextBox 已居中，若扁平化预览的 text layer 仍左上，会产生“没生效”的直观结论。
    因此这里直接断言扁平化输出 HTML 中，对应的 `.flat-text-inner` inline style 包含：
    - justify-content: center
    - align-items: center
    （针对文本=退出/关卡选择）
    """
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    repo_root = get_repo_root()
    source_dir = (
        repo_root / "assets" / "资源库" / "项目存档" / "示例项目模板" / "管理配置" / "UI源码"
    ).resolve()
    files = ["1.html", "2.html", "3.html", "ceshi_rect.html"]

    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(f"Workbench 目录不存在：{workbench_dir}")

    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id="示例项目模板")
    entry_url = f"http://127.0.0.1:{port}/ui_html_workbench.html?mode=editor&internal=1"
    timeout_ms = 60_000

    def _wait_for_textarea_non_empty(page, css_selector: str) -> None:
        start_time = page.evaluate("() => Date.now()")
        while True:
            current_value = page.eval_on_selector(
                css_selector, "el => (el && 'value' in el) ? String(el.value || '') : ''"
            )
            if str(current_value).strip():
                return
            now = page.evaluate("() => Date.now()")
            if int(now) - int(start_time) > timeout_ms:
                raise TimeoutError(f"等待 textarea 输出超时: {css_selector}")

    def _render_flattened_html(page, source_html_text: str) -> str:
        if page.query_selector("#inputHtmlTextArea") is None:
            raise RuntimeError("未找到 Workbench 编辑器 DOM（#inputHtmlTextArea），入口页可能已变化。")

        # 写入 HTML（用 direct assign 避免 page.fill 超时）
        page.evaluate(
            "(htmlText) => { const t = document.getElementById('inputHtmlTextArea'); if (!t) return; t.value = String(htmlText || ''); t.dispatchEvent(new Event('input', { bubbles: true })); }",
            source_html_text,
        )
        _wait_for_textarea_non_empty(page, "#inputHtmlTextArea")

        # 清空旧输出
        page.evaluate("() => { const t = document.getElementById('flattenedOutputTextArea'); if (t) t.value = ''; }")
        page.evaluate("() => { const t = document.getElementById('validationErrorsTextArea'); if (t) t.value = ''; }")

        # 自动修正并校验 + 生成扁平化
        page.click("#autoFixAndRenderButtonInline")
        page.click("#generateFlattenedButtonInline")
        _wait_for_textarea_non_empty(page, "#flattenedOutputTextArea")

        flattened_text = page.eval_on_selector("#flattenedOutputTextArea", "el => String(el.value || '')")
        return str(flattened_text or "")

    def _assert_text_layer_centered(flattened_html: str, text: str) -> None:
        # 找出 flat-text-inner 的 style（同一个页面可能有多个同名文本，必须限定到按钮文字层）。
        raw = str(flattened_html or "")
        if not raw.strip():
            raise AssertionError("flattened_html 为空")
        # 只断言 “btn-text” 这类按钮文本层（避免误匹配到页面其它同名标题/说明文案）。
        # 允许任意属性顺序；只要同一个 flat-text-inner 块里同时包含 align-items/justify-content=center
        pattern = re.compile(
            r'<div class="flat-text[^"]*"[^>]*data-debug-label="text[^"]*btn-text[^"]*"[^>]*>\s*'
            r'<div class="flat-text-inner"[^>]*style="([^"]+)"[^>]*>\s*' + re.escape(text) + r"\s*</div>",
            re.IGNORECASE,
        )
        styles = pattern.findall(raw)
        if not styles:
            raise AssertionError(f"未在 flattened_html 中找到 flat-text-inner 文本={text!r}")
        for st in styles:
            s = str(st or "").lower()
            if "display: flex" not in s:
                raise AssertionError(f"flat-text-inner 未使用 flex：text={text!r} style={st!r}")
            if "justify-content: center" not in s:
                raise AssertionError(f"flat-text-inner 未水平居中：text={text!r} style={st!r}")
            if "align-items: center" not in s:
                raise AssertionError(f"flat-text-inner 未垂直居中：text={text!r} style={st!r}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            page = ctx.new_page()
            page.goto(entry_url, wait_until="load", timeout=30_000)

            for name in files:
                html_path = (source_dir / name).resolve()
                if not html_path.is_file():
                    raise FileNotFoundError(f"UI源码缺失：{html_path}")
                html_text = html_path.read_text(encoding="utf-8")
                flattened = _render_flattened_html(page, html_text)
                _assert_text_layer_centered(flattened, "退出")
                _assert_text_layer_centered(flattened, "关卡选择")

            ctx.close()
            browser.close()
    finally:
        httpd.shutdown()

