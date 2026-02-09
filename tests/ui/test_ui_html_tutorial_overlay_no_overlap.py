from __future__ import annotations

import importlib.util
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests._helpers.project_paths import get_repo_root
from tests._helpers.ui_preview_mock_server import start_ui_preview_mock_server


def _require_playwright() -> None:
    if importlib.util.find_spec("playwright") is None:
        pytest.skip("requires playwright (pip install playwright; python -m playwright install chromium)")


def _wait_for_text_contains(*, page, selector: str, expected_substring: str, timeout_ms: int) -> str:
    start_time = time.monotonic()
    while True:
        current_value = page.eval_on_selector(selector, "el => el ? String(el.textContent || '') : ''")
        if expected_substring in str(current_value):
            return str(current_value)
        if (time.monotonic() - start_time) * 1000.0 > float(timeout_ms):
            raise TimeoutError(
                f"等待文本超时: selector={selector} expected~={expected_substring!r} got={current_value!r}"
            )
        time.sleep(0.05)


def _wait_for_textarea_contains(*, page, selector: str, expected_substring: str, timeout_ms: int) -> str:
    start_time = time.monotonic()
    while True:
        current_value = page.eval_on_selector(selector, "el => (el && 'value' in el) ? String(el.value || '') : ''")
        if expected_substring in str(current_value):
            return str(current_value)
        if (time.monotonic() - start_time) * 1000.0 > float(timeout_ms):
            raise TimeoutError(
                f"等待 textarea 超时: selector={selector} expected~={expected_substring!r} got={current_value!r}"
            )
        time.sleep(0.05)


@dataclass(frozen=True, slots=True)
class _Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class _FlatLayer:
    debug_label: str
    classes: str
    z: int
    rect: _Rect
    ui_state_group: str
    ui_state: str


def _rect_intersect_area(a: _Rect, b: _Rect) -> float:
    x0 = max(a.left, b.left)
    y0 = max(a.top, b.top)
    x1 = min(a.right, b.right)
    y1 = min(a.bottom, b.bottom)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _rect_union(rects: list[_Rect]) -> _Rect:
    if not rects:
        raise ValueError("rects is empty")
    left = min(r.left for r in rects)
    top = min(r.top for r in rects)
    right = max(r.right for r in rects)
    bottom = max(r.bottom for r in rects)
    return _Rect(left=left, top=top, right=right, bottom=bottom)


def _collect_flat_layers_in_preview_iframe(*, page, size_key: str, timeout_ms: int) -> list[_FlatLayer]:
    frame = page.frame_locator("#previewIframe")
    # 必须取“当前选中尺寸”的可见区域（display:block），否则 clientWidth/clientHeight 可能为 0。
    area = frame.locator(f'.flat-display-area[data-size-key="{size_key}"][style*="display: block"]')
    area.wait_for(timeout=timeout_ms, state="attached")
    area.locator("[data-layer-key]").first.wait_for(timeout=timeout_ms, state="attached")

    rows = area.locator("[data-layer-key][data-debug-label]").evaluate_all(
        """
        (els) => {
          const out = [];
          for (const el of els) {
            const st = el.style || {};
            const left = st.left ? Number(String(st.left).replace('px','')) : NaN;
            const top = st.top ? Number(String(st.top).replace('px','')) : NaN;
            const width = st.width ? Number(String(st.width).replace('px','')) : NaN;
            const height = st.height ? Number(String(st.height).replace('px','')) : NaN;
            const z = st.zIndex ? Number(st.zIndex) : 0;
            if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) {
              continue;
            }
            out.push({
              debug_label: String(el.dataset && el.dataset.debugLabel ? el.dataset.debugLabel : ''),
              classes: String(el.className || ''),
              z: Number.isFinite(z) ? z : 0,
              left, top, width, height,
              ui_state_group: String(el.dataset && el.dataset.uiStateGroup ? el.dataset.uiStateGroup : ''),
              ui_state: String(el.dataset && el.dataset.uiState ? el.dataset.uiState : ''),
            });
          }
          return out;
        }
        """
    )

    out: list[_FlatLayer] = []
    for r in rows:
        left = float(r["left"])
        top = float(r["top"])
        width = float(r["width"])
        height = float(r["height"])
        out.append(
            _FlatLayer(
                debug_label=str(r.get("debug_label") or ""),
                classes=str(r.get("classes") or ""),
                z=int(float(r.get("z") or 0)),
                rect=_Rect(left=left, top=top, right=left + width, bottom=top + height),
                ui_state_group=str(r.get("ui_state_group") or ""),
                ui_state=str(r.get("ui_state") or ""),
            )
        )
    return out


def _get_canvas_size_in_iframe(*, page, size_key: str, timeout_ms: int) -> tuple[float, float]:
    frame = page.frame_locator("#previewIframe")
    # 必须取“当前选中尺寸”的可见区域（display:block），否则 clientWidth/clientHeight 可能为 0。
    area = frame.locator(f'.flat-display-area[data-size-key="{size_key}"][style*="display: block"]')
    area.wait_for(timeout=timeout_ms, state="attached")
    meta = area.evaluate(
        """
        (el) => {
          const w = Number(el && el.clientWidth ? el.clientWidth : 0);
          const h = Number(el && el.clientHeight ? el.clientHeight : 0);
          return { w, h };
        }
        """
    )
    w = float(meta.get("w") or 0)
    h = float(meta.get("h") or 0)
    if w <= 0 or h <= 0:
        raise AssertionError(f"[{size_key}] 无法获取 flat-display-area 画布尺寸：meta={meta!r}")
    return w, h


def _assert_rect_in_canvas(*, rect: _Rect, canvas_w: float, canvas_h: float, label: str) -> None:
    # 允许少量浮点误差
    eps = 0.51
    if rect.left < -eps or rect.top < -eps:
        raise AssertionError(f"{label} 超出画布左/上边界：rect={rect} canvas={canvas_w}x{canvas_h}")
    if rect.right > float(canvas_w) + eps or rect.bottom > float(canvas_h) + eps:
        raise AssertionError(f"{label} 超出画布右/下边界：rect={rect} canvas={canvas_w}x{canvas_h}")


def _find_flat_text_rect_union_in_iframe(
    *,
    page,
    size_key: str,
    texts: list[str],
    timeout_ms: int,
    allow_substring: bool = False,
) -> _Rect:
    """
    在扁平化预览 iframe 内，用“文本内容”定位目标区域（例如按钮上的文案）。

    设计目的：
    - 避免仅依赖 highlight-dim 推导 hole（某些情况下 hole 推导可能偏差）
    - 把“高亮目标区域”锚定到实际 UI 元素（用户肉眼看到的区域）
    """
    frame = page.frame_locator("#previewIframe")
    # 必须取“当前选中尺寸”的可见区域（display:block），否则 clientWidth/clientHeight 可能为 0。
    area = frame.locator(f'.flat-display-area[data-size-key="{size_key}"][style*="display: block"]')
    area.wait_for(timeout=timeout_ms, state="attached")
    area.locator(".flat-text-inner").first.wait_for(timeout=timeout_ms, state="attached")

    want = [str(t).strip() for t in texts if str(t).strip()]
    if not want:
        raise ValueError("texts is empty")

    rects = area.locator(".flat-text-inner").evaluate_all(
        """
        (els, cfg) => {
          const want = (cfg && cfg.want ? cfg.want : []).map(s => String(s || '').trim()).filter(Boolean);
          const allowSubstring = !!(cfg && cfg.allowSubstring);
          const out = [];
          for (const inner of els) {
            const t = String(inner.textContent || '').trim();
            let ok = false;
            if (allowSubstring) {
              for (const w of want) {
                if (w && t.includes(w)) { ok = true; break; }
              }
            } else {
              for (const w of want) {
                if (w && t === w) { ok = true; break; }
              }
            }
            if (!ok) continue;
            const host = inner.closest('.flat-text');
            if (!host) continue;
            const st = host.style || {};
            const left = st.left ? Number(String(st.left).replace('px','')) : NaN;
            const top = st.top ? Number(String(st.top).replace('px','')) : NaN;
            const width = st.width ? Number(String(st.width).replace('px','')) : NaN;
            const height = st.height ? Number(String(st.height).replace('px','')) : NaN;
            if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) continue;
            out.push({ left, top, right: left + width, bottom: top + height });
          }
          return out;
        }
        """,
        {"want": want, "allowSubstring": bool(allow_substring)},
    )
    if not rects:
        raise AssertionError(f"[{size_key}] 未找到目标文本的扁平文字层：texts={want}")
    return _rect_union([_Rect(left=float(r["left"]), top=float(r["top"]), right=float(r["right"]), bottom=float(r["bottom"])) for r in rects])


def _compute_highlight_hole_from_dim_layers(dim_layers: list[_FlatLayer]) -> _Rect:
    if len(dim_layers) != 4:
        labels = [d.debug_label for d in dim_layers]
        raise AssertionError(f"highlight-dim 层数量应为 4（上/下/左/右），当前={len(dim_layers)} labels={labels}")

    canvas = _rect_union([d.rect for d in dim_layers])

    # 候选边界：由 dim rect 的边界构成（hole 的边界必在这些边界上）
    xs = sorted({canvas.left, canvas.right} | {d.rect.left for d in dim_layers} | {d.rect.right for d in dim_layers})
    ys = sorted({canvas.top, canvas.bottom} | {d.rect.top for d in dim_layers} | {d.rect.bottom for d in dim_layers})
    if len(xs) < 2 or len(ys) < 2:
        raise AssertionError(f"highlight-dim 边界不足，无法推导 hole：xs={xs} ys={ys}")

    def _covered(px: float, py: float) -> bool:
        for d in dim_layers:
            r = d.rect
            if px >= r.left and px < r.right and py >= r.top and py < r.bottom:
                return True
        return False

    uncovered_cells: list[_Rect] = []
    for xi in range(len(xs) - 1):
        for yi in range(len(ys) - 1):
            x0, x1 = float(xs[xi]), float(xs[xi + 1])
            y0, y1 = float(ys[yi]), float(ys[yi + 1])
            if x1 <= x0 or y1 <= y0:
                continue
            px = (x0 + x1) * 0.5
            py = (y0 + y1) * 0.5
            if not _covered(px, py):
                uncovered_cells.append(_Rect(left=x0, top=y0, right=x1, bottom=y1))

    if not uncovered_cells:
        raise AssertionError("未找到 highlight hole（dim 层似乎覆盖了整个画布，可能 marker 生成异常）。")

    # 过滤浮点误差导致的“细缝”：右侧/底部可能出现 < 1px 的未覆盖条带，
    # 直接 union 会把 hole 扩张成巨大的外接矩形导致误报。
    significant = [r for r in uncovered_cells if r.width > 2.0 and r.height > 2.0 and r.area > 16.0]
    hole = _rect_union(significant if significant else uncovered_cells)
    # hole 必须在 canvas 内且有面积
    if hole.area <= 0:
        raise AssertionError(f"highlight hole 面积为 0：hole={hole}")
    if hole.left < canvas.left - 0.51 or hole.top < canvas.top - 0.51 or hole.right > canvas.right + 0.51 or hole.bottom > canvas.bottom + 0.51:
        raise AssertionError(f"highlight hole 超出 canvas：hole={hole} canvas={canvas}")
    return hole


def _compute_tutorial_card_rect(*, layers: list[_FlatLayer], ui_state: str) -> _Rect:
    state_layers = [l for l in layers if l.ui_state_group == "tutorial_overlay" and l.ui_state == ui_state]
    base_candidates = [l for l in state_layers if l.debug_label == "tutorial-card" and "flat-element" in l.classes.split()]
    if not base_candidates:
        raise AssertionError(f"[{ui_state}] 未找到 tutorial-card 扁平层（debug_label='tutorial-card'）")
    base = sorted(base_candidates, key=lambda x: (-x.rect.area, -x.z))[0]

    # 计算指引面板 bbox：以 tutorial-card 为锚点，聚合其内部子层 + 边框/阴影，但排除 highlight-dim（否则会把全屏遮罩算进去）
    eps = 0.51
    anchor = _Rect(
        left=base.rect.left - eps,
        top=base.rect.top - eps,
        right=base.rect.right + eps,
        bottom=base.rect.bottom + eps,
    )
    related: list[_Rect] = []
    for l in state_layers:
        if l.debug_label.startswith("highlight-dim-"):
            continue
        if _rect_intersect_area(anchor, l.rect) > 0:
            related.append(l.rect)
    if not related:
        return base.rect
    return _rect_union(related)


@pytest.fixture(scope="module")
def _repo_root() -> Path:
    return get_repo_root()


@pytest.fixture(scope="module")
def _workbench_server(_repo_root: Path):
    httpd, port = start_ui_preview_mock_server(repo_root=_repo_root, package_id="示例项目模板", host="127.0.0.1", port=0)
    yield port
    httpd.shutdown()


def test_ui_html_tutorial_overlay_card_does_not_overlap_highlight_area_in_all_sizes(_repo_root: Path, _workbench_server: int) -> None:
    """
    目标（强约束）：
    - UI HTML 经过 Workbench 扁平化后
    - 在多个分辨率（4 档画布）下
    - “指引面板（tutorial-card）”不得与其对应的“高亮挖空区域（highlight hole）”发生任何重叠
      否则等价于“指引卡片遮挡了用户需要关注的高亮区域”。

    当前用例覆盖：示例项目模板/管理配置/UI源码/2.html 的 guide_1~guide_6。
    """
    _require_playwright()
    from tests._helpers.playwright_utils import require_playwright_chromium

    require_playwright_chromium(reason="需要 Playwright chromium 用于 headless 浏览器驱动。")
    from playwright.sync_api import sync_playwright

    entry_url = f"http://127.0.0.1:{int(_workbench_server)}/ui_app_ui_preview.html"
    timeout_ms = 60_000

    sizes: list[tuple[str, int, int]] = [
        ("1920x1080", 1920, 1080),
        ("1600x900", 1600, 900),
        ("1560x720", 1560, 720),
        ("1280x720", 1280, 720),
    ]
    guide_states = ["guide_1", "guide_2", "guide_3", "guide_4", "guide_5", "guide_6"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 通过 localStorage 预注入“最近选择文件”，并走预览页的“强制扁平化”生成链路：
        # 这条链路与用户日常在 Workbench 中点击的按钮一致，避免“看的是预览页，但测的是 editor 页”。
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        ctx.add_init_script("window.localStorage.setItem('ui_preview:last_selected', " + json.dumps("project:2.html") + ");")
        page = ctx.new_page()
        page.goto(entry_url, wait_until="load", timeout=timeout_ms)
        _wait_for_text_contains(page=page, selector="#exportWidgetListStatusText", expected_substring="已生成", timeout_ms=timeout_ms)

        failures: list[str] = []
        for size_key, w, h in sizes:
            size_button_id = {
                "1920x1080": "#sizeButton1920x1080",
                "1600x900": "#sizeButton1600x900",
                "1560x720": "#sizeButton1560x720",
                "1280x720": "#sizeButton1280x720",
            }[size_key]
            page.click(size_button_id)

            # 切到扁平预览并等待该尺寸的扁平层可用（display:block）。
            page.click("#previewVariantFlattenedButton")

            layers = _collect_flat_layers_in_preview_iframe(page=page, size_key=size_key, timeout_ms=timeout_ms)
            canvas_w, canvas_h = _get_canvas_size_in_iframe(page=page, size_key=size_key, timeout_ms=timeout_ms)

            for ui_state in guide_states:
                state_layers = [l for l in layers if l.ui_state_group == "tutorial_overlay" and l.ui_state == ui_state]
                if not state_layers:
                    failures.append(f"[{size_key}][{ui_state}] 未找到 tutorial_overlay 的扁平层（可能 state 丢失/未入库）")
                    continue

                card = _compute_tutorial_card_rect(layers=layers, ui_state=ui_state)

                # “不许跑到屏幕外”：指引卡片必须完全落在画布内（以 iframe 的 flat-display-area 为准）
                _assert_rect_in_canvas(
                    rect=card, canvas_w=float(canvas_w), canvas_h=float(canvas_h), label=f"[{size_key}][{ui_state}] tutorial_card"
                )

                # 额外锚定：用“真实 UI 元素文本”确认高亮目标区域，并要求指引卡片不与该目标重叠。
                # 这用于捕捉“肉眼看到卡片挡住按钮，但 hole 推导/选择没抓到”的情况。
                target_rect: _Rect | None = None
                if ui_state == "guide_6":
                    target_rect = _find_flat_text_rect_union_in_iframe(
                        page=page, size_key=size_key, texts=["拒绝进入", "允许进入"], timeout_ms=timeout_ms
                    )

                if target_rect is not None:
                    _assert_rect_in_canvas(
                        rect=target_rect,
                        canvas_w=float(canvas_w),
                        canvas_h=float(canvas_h),
                        label=f"[{size_key}][{ui_state}] highlight_target",
                    )
                    overlap_target = _rect_intersect_area(card, target_rect)
                    if overlap_target > 0.51:
                        failures.append(
                            f"[2.html][{size_key}][{ui_state}] overlap_target={overlap_target:.2f} "
                            f"card=({card.left:.2f},{card.top:.2f},{card.right:.2f},{card.bottom:.2f}) "
                            f"target=({target_rect.left:.2f},{target_rect.top:.2f},{target_rect.right:.2f},{target_rect.bottom:.2f})"
                        )

        if failures:
            raise AssertionError("指引卡片与高亮区域重叠检查未通过：\n- " + "\n- ".join(failures))

        ctx.close()
        browser.close()

