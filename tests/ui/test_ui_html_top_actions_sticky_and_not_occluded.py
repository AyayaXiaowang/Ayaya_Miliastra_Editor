from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest


def _playwright_available() -> bool:
    from tests._helpers.playwright_utils import is_playwright_chromium_ready

    return is_playwright_chromium_ready()


def _ensure_repo_root_on_sys_path() -> Path:
    """避免 `tests` 命名空间与外部环境冲突：向上查找包含 app/engine/assets 的仓库根目录。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "app").is_dir() and (parent / "engine").is_dir() and (parent / "assets").is_dir():
            # 允许直接 `python tests/ui/test_xxx.py` 运行：脚本模式下 sys.path 不包含 repo root。
            root_str = str(parent)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return parent
    raise RuntimeError(f"无法定位仓库根目录（from={here}）")


def _get_repo_root() -> Path:
    return _ensure_repo_root_on_sys_path()

def _wait_for_textarea_non_empty(page, css_selector: str, timeout_ms: int) -> None:
    start_time = time.monotonic()
    timeout_s = timeout_ms / 1000.0
    while True:
        current_value = page.eval_on_selector(css_selector, "el => (el && 'value' in el) ? String(el.value || '') : ''")
        if current_value.strip():
            return
        if time.monotonic() - start_time > timeout_s:
            raise TimeoutError(f"等待 textarea 输出超时: {css_selector}")
        time.sleep(0.05)


def _render_flattened_html_text_with_workbench(
    *,
    page,
    source_html_text: str,
    canvas_size_key: str,
    timeout_ms: int,
) -> tuple[str, str]:
    if page.query_selector("#inputHtmlTextArea") is None:
        raise RuntimeError("未找到 Workbench 编辑器 DOM（#inputHtmlTextArea），入口页可能已变化。")

    size_button_id = "sizeButton" + str(canvas_size_key)
    if page.query_selector("#" + size_button_id) is None:
        raise RuntimeError(f"未找到画布尺寸按钮 DOM（#{size_button_id}），无法强制画布尺寸。")
    page.evaluate("(buttonId) => { const b = document.getElementById(buttonId); if (b) b.click(); }", size_button_id)

    # `page.fill()` 在较大的 HTML 文本下可能非常慢（30s 超时），改用“直接赋值 + 触发 input”：
    # - 更接近 Workbench 本身的“编辑器内容变更”语义
    # - 不依赖逐字符输入性能，避免 CI/弱机上不稳定超时
    page.evaluate(
        "(htmlText) => { const t = document.getElementById('inputHtmlTextArea'); if (!t) return; t.value = String(htmlText || ''); t.dispatchEvent(new Event('input', { bubbles: true })); }",
        source_html_text,
    )
    _wait_for_textarea_non_empty(page, "#inputHtmlTextArea", timeout_ms)

    # 清空旧输出，避免 wait 误判
    page.evaluate("() => { const t = document.getElementById('flattenedOutputTextArea'); if (t) t.value = ''; }")
    page.evaluate("() => { const t = document.getElementById('validationErrorsTextArea'); if (t) t.value = ''; }")

    # 使用“自动修正并校验”：会注入禁滚动等修正，避免预览环境差异导致误报。
    page.click("#autoFixAndRenderButtonInline")
    page.click("#generateFlattenedButtonInline")

    _wait_for_textarea_non_empty(page, "#validationErrorsTextArea", timeout_ms)
    _wait_for_textarea_non_empty(page, "#flattenedOutputTextArea", timeout_ms)

    validation_text = page.eval_on_selector("#validationErrorsTextArea", "el => String(el.value || '')")
    flattened_text = page.eval_on_selector("#flattenedOutputTextArea", "el => String(el.value || '')")
    return flattened_text, validation_text


def _assert_workbench_no_errors(validation_text: str) -> None:
    """
    目标：断言存在 errors=0（否则属于“导出/生成被阻断”的根因，不应继续做布局断言）。

    注意：validation 输出包含多段摘要；这里只做最稳妥的“errors=0”硬断言。
    """
    lines = [s.strip() for s in str(validation_text or "").splitlines() if s.strip()]
    for s in lines:
        if "errors=" not in s:
            continue
        if s.startswith("【") and "errors=0" in s:
            return
    raise AssertionError("Workbench 校验未通过（存在 errors）。\n---- validation.txt ----\n" + str(validation_text).strip())


@dataclass(frozen=True, slots=True)
class _FlatLayer:
    size_key: str
    debug_label: str
    z: int
    left: float
    top: float
    width: float
    height: float
    classes: str
    background_color: str
    ui_state_group: str
    ui_state: str

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def is_element(self) -> bool:
        return "flat-element" in self.classes.split()


def _parse_style(style_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(style_text or "").split(";"):
        item = part.strip()
        if not item or ":" not in item:
            continue
        k, v = item.split(":", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _parse_px(v: str) -> float:
    s = str(v or "").strip()
    if s.endswith("px"):
        s = s[:-2].strip()
    return float(s)


def _parse_int(v: str) -> int:
    return int(float(str(v or "").strip()))


def _collect_flat_layers_from_dom(*, page, size_key: str) -> list[_FlatLayer]:
    # 在浏览器内从 DOM 读取 (bbox + z-index + bg + label)，避免在 Python 侧手写 HTML parser。
    rows = page.evaluate(
        """
        (sizeKey) => {
          const area = document.querySelector(`.flat-display-area[data-size-key="${String(sizeKey)}"]`);
          if (!area) return [];
          const out = [];
          const nodes = area.querySelectorAll('div[data-debug-label][style*="left"][style*="top"][style*="z-index"]');
          for (const el of nodes) {
            const s = el.getAttribute("style") || "";
            const st = el.style || {};
            const z = st.zIndex ? Number(st.zIndex) : 0;
            const left = st.left ? Number(String(st.left).replace("px","")) : NaN;
            const top = st.top ? Number(String(st.top).replace("px","")) : NaN;
            const width = st.width ? Number(String(st.width).replace("px","")) : NaN;
            const height = st.height ? Number(String(st.height).replace("px","")) : NaN;
            if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) continue;
            out.push({
              size_key: String(sizeKey),
              debug_label: String(el.dataset && el.dataset.debugLabel ? el.dataset.debugLabel : ""),
              classes: String(el.className || ""),
              z: Number.isFinite(z) ? z : 0,
              left,
              top,
              width,
              height,
              background_color: String(st.backgroundColor || st.background || ""),
              ui_state_group: String(el.dataset && el.dataset.uiStateGroup ? el.dataset.uiStateGroup : ""),
              ui_state: String(el.dataset && el.dataset.uiState ? el.dataset.uiState : ""),
            });
          }
          return out;
        }
        """,
        size_key,
    )
    out: list[_FlatLayer] = []
    for r in rows:
        out.append(
            _FlatLayer(
                size_key=str(r["size_key"]),
                debug_label=str(r.get("debug_label") or ""),
                z=_parse_int(r.get("z")),
                left=float(r.get("left")),
                top=float(r.get("top")),
                width=float(r.get("width")),
                height=float(r.get("height")),
                classes=str(r.get("classes") or ""),
                background_color=str(r.get("background_color") or ""),
                ui_state_group=str(r.get("ui_state_group") or ""),
                ui_state=str(r.get("ui_state") or ""),
            )
        )
    return out


def _layer_matches_any_label(layer: _FlatLayer, patterns: list[str]) -> bool:
    lbl = str(layer.debug_label or "")
    if not lbl:
        return False
    for p in patterns:
        if p in lbl:
            return True
    return False


def _is_opaque_fill_color(color_text: str) -> bool:
    # 极保守：只把 rgb() / #rrggbb 视为不透明填充；rgba/#rrggbbaa 不算（避免误报遮挡）。
    c = str(color_text or "").strip().lower()
    if not c or c == "transparent":
        return False
    if c.startswith("rgba("):
        return False
    if c.startswith("#"):
        return len(c) == 7
    if c.startswith("rgb("):
        return True
    return False


def _cover_is_visible_when_target_visible(*, cover: _FlatLayer, target: _FlatLayer) -> bool:
    # 保守口径：target 若无 state-group，则 cover 也必须无 state-group（始终可见）。
    if not target.ui_state_group:
        return not cover.ui_state_group
    if not cover.ui_state_group:
        return True
    return cover.ui_state_group == target.ui_state_group and cover.ui_state == target.ui_state


def _find_full_covering_opaque_layer(
    *,
    layers: list[_FlatLayer],
    target: _FlatLayer,
) -> _FlatLayer | None:
    # 只找“单层完全覆盖且不透明”的 cover（极保守）。
    for cover in layers:
        if cover.z <= target.z:
            continue
        if not cover.is_element:
            continue
        if not _is_opaque_fill_color(cover.background_color):
            continue
        if not _cover_is_visible_when_target_visible(cover=cover, target=target):
            continue
        if cover.left <= target.left and cover.top <= target.top and cover.right >= target.right and cover.bottom >= target.bottom:
            return cover
    return None


def test_ui_html_top_actions_sticky_and_not_occluded() -> None:
    """
    回归目标：
    - 4 档画布尺寸下，扁平化后左上角“退出/关卡选择”必须贴近顶部（不应被布局 padding 推下去）
    - 且不应被主面板/遮罩等不透明底板完全遮挡（否则等价于“按钮不在顶部可用层”）
    """
    if not _playwright_available():
        pytest.skip("requires playwright (pip install playwright; python -m playwright install chromium)")

    from playwright.sync_api import sync_playwright

    repo_root = _get_repo_root()
    from tests._helpers.ui_preview_mock_server import start_ui_preview_mock_server

    package_id = "示例项目模板"
    source_dir = (
        repo_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码"
    ).resolve()
    html_paths = [source_dir / "1.html", source_dir / "2.html", source_dir / "3.html"]
    for p in html_paths:
        if not p.is_file():
            raise FileNotFoundError(f"UI源码缺失：{p}")

    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(f"Workbench 目录不存在：{workbench_dir}")

    # 使用 mock /api，避免 Workbench 首屏轮询后端 status 导致时序卡死或长时间无输出。
    httpd, port = start_ui_preview_mock_server(repo_root=repo_root, package_id=package_id)
    entry_url = f"http://127.0.0.1:{port}/ui_html_workbench.html?mode=editor&internal=1"
    timeout_ms = 30_000

    sizes: list[tuple[str, int, int]] = [
        ("1920x1080", 1920, 1080),
        ("1600x900", 1600, 900),
        ("1560x720", 1560, 720),
        ("1280x720", 1280, 720),
    ]

    # “必须在顶部”的工程口径：top 应落在 ~ 0~40px（corner-slot-top clamp 范围为 16~24）。
    max_top_px = 40.0
    max_left_px = 60.0

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            wb_ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            wb_page = wb_ctx.new_page()
            wb_page.goto(entry_url, wait_until="load", timeout=timeout_ms)

            # 复用一个预览 context/page，避免每档尺寸重复创建浏览器上下文导致“看起来卡住”。
            preview_ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            preview_page = preview_ctx.new_page()

            for html_path in html_paths:
                html_text = html_path.read_text(encoding="utf-8")

                for size_key, w, h in sizes:
                    print(f"[TOP_ACTIONS] flatten {html_path.name} size={size_key}", flush=True)
                    flattened_text, validation_text = _render_flattened_html_text_with_workbench(
                        page=wb_page,
                        source_html_text=html_text,
                        canvas_size_key=size_key,
                        timeout_ms=timeout_ms,
                    )
                    _assert_workbench_no_errors(validation_text)

                    # 用同一张 page 直接渲染扁平化 HTML，并按目标 size 强制显示对应 flat-display-area。
                    preview_page.set_viewport_size({"width": w, "height": h})
                    preview_page.set_content(flattened_text, wait_until="load")
                    preview_page.evaluate(
                        """
                        (key) => {
                          const list = document.querySelectorAll('.flat-display-area');
                          for (const el of list) {
                            const k = el && el.dataset ? String(el.dataset.sizeKey || '') : '';
                            el.style.display = (k === String(key)) ? 'block' : 'none';
                          }
                        }
                        """,
                        size_key,
                    )

                    layers = _collect_flat_layers_from_dom(page=preview_page, size_key=size_key)

                    # 用扁平化后的文字层定位按钮（避免依赖 data-debug-label 的派生规则）
                    anchors = preview_page.evaluate(
                        """
                        ({ sizeKey }) => {
                          const area = document.querySelector(`.flat-display-area[data-size-key="${String(sizeKey)}"]`);
                          if (!area) return { exit: [], level: [] };
                          function pick(text) {
                            const out = [];
                            const list = area.querySelectorAll('.flat-text-inner');
                            for (const inner of list) {
                              const t = String(inner.textContent || '').trim();
                              if (t !== String(text)) continue;
                              const host = inner.closest('.flat-text');
                              if (!host) continue;
                              const r = host.getBoundingClientRect();
                              const z = host && host.style && host.style.zIndex ? Number(host.style.zIndex) : 0;
                              out.push({
                                left: r.left, top: r.top, width: r.width, height: r.height,
                                z: Number.isFinite(z) ? z : 0,
                                debug_label: String(host.dataset && host.dataset.debugLabel ? host.dataset.debugLabel : ''),
                              });
                            }
                            return out;
                          }
                          return { exit: pick('退出'), level: pick('关卡选择') };
                        }
                        """,
                        {"sizeKey": size_key},
                    )

                    exit_candidates = anchors.get("exit") or []
                    level_candidates = anchors.get("level") or []
                    if not exit_candidates:
                        raise AssertionError(f"[{html_path.name}][{size_key}] 未找到文本=退出 的扁平文字层（无法定位退出按钮）")
                    if not level_candidates:
                        raise AssertionError(f"[{html_path.name}][{size_key}] 未找到文本=关卡选择 的扁平文字层（无法定位关卡选择按钮）")

                    exit_anchor_raw = sorted(exit_candidates, key=lambda x: (float(x["top"]), float(x["left"]), -float(x["z"])))[0]
                    level_anchor_raw = sorted(level_candidates, key=lambda x: (float(x["top"]), float(x["left"]), -float(x["z"])))[0]

                    exit_anchor = _FlatLayer(
                        size_key=size_key,
                        debug_label=str(exit_anchor_raw.get("debug_label") or ""),
                        z=_parse_int(exit_anchor_raw.get("z")),
                        left=float(exit_anchor_raw.get("left")),
                        top=float(exit_anchor_raw.get("top")),
                        width=float(exit_anchor_raw.get("width")),
                        height=float(exit_anchor_raw.get("height")),
                        classes="flat-text",
                        background_color="transparent",
                        ui_state_group="",
                        ui_state="",
                    )
                    level_anchor = _FlatLayer(
                        size_key=size_key,
                        debug_label=str(level_anchor_raw.get("debug_label") or ""),
                        z=_parse_int(level_anchor_raw.get("z")),
                        left=float(level_anchor_raw.get("left")),
                        top=float(level_anchor_raw.get("top")),
                        width=float(level_anchor_raw.get("width")),
                        height=float(level_anchor_raw.get("height")),
                        classes="flat-text",
                        background_color="transparent",
                        ui_state_group="",
                        ui_state="",
                    )

                    if exit_anchor.top > max_top_px or exit_anchor.left > max_left_px:
                        raise AssertionError(
                            f"[{html_path.name}][{size_key}] 退出按钮未贴顶（疑似被 padding/布局推下去）。"
                            f" top={exit_anchor.top:.2f} left={exit_anchor.left:.2f} dbg={exit_anchor.debug_label} z={exit_anchor.z}"
                        )
                    if level_anchor.top > max_top_px:
                        raise AssertionError(
                            f"[{html_path.name}][{size_key}] 关卡选择按钮未贴顶。"
                            f" top={level_anchor.top:.2f} left={level_anchor.left:.2f} dbg={level_anchor.debug_label} z={level_anchor.z}"
                        )

                    # 遮挡检查：找是否存在“完全覆盖按钮锚点”的不透明底板层（z 更高且可见条件覆盖）
                    exit_cover = _find_full_covering_opaque_layer(layers=layers, target=exit_anchor)
                    if exit_cover is not None:
                        raise AssertionError(
                            f"[{html_path.name}][{size_key}] 退出按钮被不透明底板完全遮挡："
                            f" target(dbg={exit_anchor.debug_label},z={exit_anchor.z},rect=({exit_anchor.left:.1f},{exit_anchor.top:.1f},{exit_anchor.width:.1f},{exit_anchor.height:.1f}))"
                            f" cover(dbg={exit_cover.debug_label},z={exit_cover.z},bg={exit_cover.background_color},rect=({exit_cover.left:.1f},{exit_cover.top:.1f},{exit_cover.width:.1f},{exit_cover.height:.1f}))"
                        )

                    level_cover = _find_full_covering_opaque_layer(layers=layers, target=level_anchor)
                    if level_cover is not None:
                        raise AssertionError(
                            f"[{html_path.name}][{size_key}] 关卡选择按钮被不透明底板完全遮挡："
                            f" target(dbg={level_anchor.debug_label},z={level_anchor.z},rect=({level_anchor.left:.1f},{level_anchor.top:.1f},{level_anchor.width:.1f},{level_anchor.height:.1f}))"
                            f" cover(dbg={level_cover.debug_label},z={level_cover.z},bg={level_cover.background_color},rect=({level_cover.left:.1f},{level_cover.top:.1f},{level_cover.width:.1f},{level_cover.height:.1f}))"
                        )

                    print(
                        f"[TOP_ACTIONS] ok {html_path.name} size={size_key} "
                        f"exit(top={exit_anchor.top:.2f},left={exit_anchor.left:.2f}) "
                        f"level(top={level_anchor.top:.2f},left={level_anchor.left:.2f})",
                        flush=True,
                    )

            preview_ctx.close()
            wb_ctx.close()
            browser.close()
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    # 允许直接 `python .../test_ui_html_top_actions_sticky_and_not_occluded.py` 运行，
    # 避免“pytest 用例文件直接运行没反应”的困惑。
    test_ui_html_top_actions_sticky_and_not_occluded()
    print("OK", flush=True)

