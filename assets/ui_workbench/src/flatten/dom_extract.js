import { GAME_CUTOUT_CLASS, GAME_CUTOUT_NAME_ATTR, HIGHLIGHT_OVERLAY_ALPHA_ATTR } from "../config.js";

function _parsePx(text, fallbackValue) {
    var trimmed = String(text || "").trim().toLowerCase();
    if (!trimmed) {
        return fallbackValue;
    }
    if (trimmed.endsWith("px")) {
        trimmed = trimmed.slice(0, -2).trim();
    }
    var numberValue = Number.parseFloat(trimmed);
    if (!isFinite(numberValue) || numberValue <= 0) {
        return fallbackValue;
    }
    return numberValue;
}

function _getCanvasSizeFromDocument(targetDocument, bodyRect) {
    if (!targetDocument || !targetDocument.documentElement) {
        return { width: bodyRect ? bodyRect.width : 0, height: bodyRect ? bodyRect.height : 0 };
    }
    var style = targetDocument.documentElement.style;
    var widthText = style ? style.getPropertyValue("--canvas-width") : "";
    var heightText = style ? style.getPropertyValue("--canvas-height") : "";
    var fallbackWidth = bodyRect ? bodyRect.width : 0;
    var fallbackHeight = bodyRect ? bodyRect.height : 0;
    return {
        width: _parsePx(widthText, fallbackWidth),
        height: _parsePx(heightText, fallbackHeight)
    };
}

function _parseNumberOrNull(text) {
    var raw = String(text || "").trim();
    if (!raw) {
        return null;
    }
    var n = Number.parseFloat(raw);
    if (!isFinite(n)) {
        return null;
    }
    return n;
}

function _parsePxFromComputedText(text, fallbackValue) {
    var raw = String(text || "").trim().toLowerCase();
    if (!raw) {
        return fallbackValue;
    }
    // computed style usually returns px, but keep it tolerant.
    if (raw.endsWith("px")) {
        raw = raw.slice(0, -2).trim();
    }
    var n = Number.parseFloat(raw);
    if (!isFinite(n) || n <= 0) {
        return fallbackValue;
    }
    return n;
}

function _getRootCssVarPx(targetDocument, varName, fallbackValue) {
    if (!targetDocument || !targetDocument.documentElement || !targetDocument.defaultView) {
        return fallbackValue;
    }
    var view = targetDocument.defaultView;
    if (!view.getComputedStyle) {
        return fallbackValue;
    }
    var cs = view.getComputedStyle(targetDocument.documentElement);
    if (!cs || !cs.getPropertyValue) {
        return fallbackValue;
    }
    var v = cs.getPropertyValue(varName);
    return _parsePxFromComputedText(v, fallbackValue);
}

function _extractScaleFromTransformText(transformText) {
    // NOTE:
    // - getBoundingClientRect() 会包含 transform 影响（例如 scale），但 computedStyle.fontSize 不会。
    // - 当作者使用 `transform: scale(var(--ui-scale))` 做整体缩放时，如果不补偿字号，
    //   导出到 GIL 会出现“盒子缩小但字号没变” -> 游戏侧文字溢出/遮挡（典型：1600x900 全乱）。
    //
    // 这里只提取 scale（旋转/倾斜在上游 validation 里已禁止/降级），保持实现轻量。
    var raw = String(transformText || "").trim();
    if (!raw || raw === "none") {
        return { sx: 1, sy: 1 };
    }

    function _parseNumbers(innerText) {
        var parts = String(innerText || "").split(",").map(function (x) { return Number.parseFloat(String(x || "").trim()); });
        for (var i = 0; i < parts.length; i++) {
            if (!isFinite(parts[i])) {
                return null;
            }
        }
        return parts;
    }

    if (raw.indexOf("matrix3d(") === 0 && raw.endsWith(")")) {
        var inner3d = raw.slice("matrix3d(".length, -1);
        var nums3d = _parseNumbers(inner3d);
        if (!nums3d || nums3d.length !== 16) {
            return { sx: 1, sy: 1 };
        }
        // matrix3d is column-major. Scale is length of basis vectors.
        // x basis: (m11, m12, m13)
        // y basis: (m21, m22, m23)
        var m11 = nums3d[0], m12 = nums3d[1], m13 = nums3d[2];
        var m21 = nums3d[4], m22 = nums3d[5], m23 = nums3d[6];
        var sx3 = Math.sqrt(m11 * m11 + m12 * m12 + m13 * m13);
        var sy3 = Math.sqrt(m21 * m21 + m22 * m22 + m23 * m23);
        if (!isFinite(sx3) || sx3 <= 0) sx3 = 1;
        if (!isFinite(sy3) || sy3 <= 0) sy3 = 1;
        return { sx: sx3, sy: sy3 };
    }

    if (raw.indexOf("matrix(") === 0 && raw.endsWith(")")) {
        var inner2d = raw.slice("matrix(".length, -1);
        var nums2d = _parseNumbers(inner2d);
        if (!nums2d || nums2d.length !== 6) {
            return { sx: 1, sy: 1 };
        }
        // matrix(a,b,c,d,e,f): scaleX = sqrt(a^2 + b^2), scaleY = sqrt(c^2 + d^2)
        var a = nums2d[0], b = nums2d[1], c = nums2d[2], d = nums2d[3];
        var sx2 = Math.sqrt(a * a + b * b);
        var sy2 = Math.sqrt(c * c + d * d);
        if (!isFinite(sx2) || sx2 <= 0) sx2 = 1;
        if (!isFinite(sy2) || sy2 <= 0) sy2 = 1;
        return { sx: sx2, sy: sy2 };
    }

    return { sx: 1, sy: 1 };
}

function _clampScale(value) {
    var n = Number(value);
    if (!isFinite(n) || n <= 0) {
        return 1;
    }
    // 保护：避免极端错误 transform 导致字号变成 0 或无穷大
    return Math.max(0.05, Math.min(8.0, n));
}

function _computeEffectiveScaleForElement(element, view, cache) {
    if (!element) {
        return { sx: 1, sy: 1 };
    }
    if (cache && cache.has(element)) {
        return cache.get(element);
    }
    var parent = element.parentElement || null;
    var parentScale = parent ? _computeEffectiveScaleForElement(parent, view, cache) : { sx: 1, sy: 1 };
    var st = view && view.getComputedStyle ? view.getComputedStyle(element) : null;
    var local = _extractScaleFromTransformText(st ? st.transform : "");
    var combined = {
        sx: _clampScale((parentScale.sx || 1) * (local.sx || 1)),
        sy: _clampScale((parentScale.sy || 1) * (local.sy || 1))
    };
    if (cache) {
        cache.set(element, combined);
    }
    return combined;
}

function _unionRects(rectList) {
    var u = null; // {left, top, right, bottom}
    for (var i = 0; i < (rectList ? rectList.length : 0); i++) {
        var r = rectList[i];
        if (!r) {
            continue;
        }
        var l = Number(r.left || 0);
        var t = Number(r.top || 0);
        var w = Number(r.width || 0);
        var h = Number(r.height || 0);
        if (!isFinite(l) || !isFinite(t) || !isFinite(w) || !isFinite(h) || w <= 0.001 || h <= 0.001) {
            continue;
        }
        var rr = l + w;
        var bb = t + h;
        if (!u) {
            u = { left: l, top: t, right: rr, bottom: bb };
            continue;
        }
        if (l < u.left) u.left = l;
        if (t < u.top) u.top = t;
        if (rr > u.right) u.right = rr;
        if (bb > u.bottom) u.bottom = bb;
    }
    if (!u) {
        return null;
    }
    var uw = u.right - u.left;
    var uh = u.bottom - u.top;
    if (!isFinite(uw) || !isFinite(uh) || uw <= 0.001 || uh <= 0.001) {
        return null;
    }
    return { left: u.left, top: u.top, width: uw, height: uh, right: u.right, bottom: u.bottom };
}

function _clamp(n, minValue, maxValue) {
    var x = Number(n);
    if (!isFinite(x)) {
        x = 0;
    }
    var lo = Number(minValue);
    var hi = Number(maxValue);
    if (!isFinite(lo)) lo = 0;
    if (!isFinite(hi)) hi = lo;
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

function _applyAnchoredTutorialCards(targetDocument, bodyRect, canvasSize) {
    // 目的：
    // - 解决“指引卡片（position:fixed/absolute）写死 left/top”在不同分辨率/媒体查询下与高亮区域脱钩的问题。
    // - 在**不注入脚本**的前提下，于扁平化前（compute iframe）把卡片坐标预计算为 px，从而保持相对关系稳定。
    //
    // HTML 写法（推荐）：
    // - 在 `.tutorial-card` 上添加：data-tutorial-anchor="highlight"
    // - 可选：data-tutorial-anchor-placement="auto|top|right|bottom|left"
    // - 可选：data-tutorial-anchor-gap="16"
    //
    // 锚点来源（默认）：
    // - 查找同一 state 的 `.highlight-display-area.tutorial-marker[data-ui-state-group=...][data-ui-state=...]`
    // - 若找到多个，按 unionRect 作为高亮区域。
    if (!targetDocument || !targetDocument.querySelectorAll) {
        return;
    }
    var cards = targetDocument.querySelectorAll(".tutorial-card[data-tutorial-anchor]");
    if (!cards || cards.length <= 0) {
        return;
    }
    var cw = canvasSize ? Number(canvasSize.width || 0) : 0;
    var ch = canvasSize ? Number(canvasSize.height || 0) : 0;
    if (!isFinite(cw) || !isFinite(ch) || cw <= 1 || ch <= 1) {
        return;
    }

    var safeMargin = _getRootCssVarPx(targetDocument, "--safe-margin", 16);
    var defaultGap = _getRootCssVarPx(targetDocument, "--gap", 16);

    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        if (!card || !card.getAttribute || !card.closest || !card.getBoundingClientRect) {
            continue;
        }
        var anchorKind = String(card.getAttribute("data-tutorial-anchor") || "").trim().toLowerCase();
        if (!anchorKind) {
            continue;
        }
        if (anchorKind !== "highlight") {
            throw new Error("不支持的 data-tutorial-anchor 值：" + anchorKind + "（仅支持 highlight）。");
        }
        var groupNode = card.closest("[data-ui-state-group]");
        if (!groupNode || !groupNode.getAttribute) {
            throw new Error("tutorial-card 声明了 data-tutorial-anchor，但未处于 data-ui-state-group 容器内。");
        }
        var group = String(groupNode.getAttribute("data-ui-state-group") || "").trim();
        if (!group) {
            throw new Error("tutorial-card 所在的 data-ui-state-group 为空。");
        }
        var stateNode = card.closest("[data-ui-state]");
        if (!(stateNode && groupNode.contains && groupNode.contains(stateNode))) {
            throw new Error("tutorial-card 声明了 data-tutorial-anchor，但未处于 data-ui-state 节点内。");
        }
        var state = String(stateNode.getAttribute("data-ui-state") || "").trim();
        if (!state) {
            throw new Error("tutorial-card 所在的 data-ui-state 为空。");
        }

        var placement = String(card.getAttribute("data-tutorial-anchor-placement") || "").trim().toLowerCase();
        if (!placement) {
            placement = "auto";
        }
        if (placement !== "auto" && placement !== "top" && placement !== "right" && placement !== "bottom" && placement !== "left") {
            throw new Error("不支持的 data-tutorial-anchor-placement：" + placement + "（支持 auto/top/right/bottom/left）。");
        }

        var gap = (function () {
            var n = _parseNumberOrNull(card.getAttribute("data-tutorial-anchor-gap"));
            if (n === null) {
                return defaultGap;
            }
            if (!isFinite(n) || n < 0) {
                return defaultGap;
            }
            return n;
        })();

        // Avoid relying on CSS.escape() (not guaranteed across all browser engines).
        // Filter markers by attributes in JS.
        var markers = [];
        var allMarkers = targetDocument.querySelectorAll(".highlight-display-area.tutorial-marker");
        for (var ai = 0; ai < (allMarkers ? allMarkers.length : 0); ai++) {
            var m0 = allMarkers[ai];
            if (!(m0 && m0.getAttribute)) {
                continue;
            }
            var g0 = String(m0.getAttribute("data-ui-state-group") || "").trim();
            var s0 = String(m0.getAttribute("data-ui-state") || "").trim();
            if (g0 === group && s0 === state) {
                markers.push(m0);
            }
        }
        if (!markers || markers.length <= 0) {
            throw new Error("tutorial-card 需要锚定高亮区域，但找不到对应 marker（group/state 不匹配）：group=" + group + ", state=" + state);
        }

        var markerRects = [];
        for (var mi = 0; mi < markers.length; mi++) {
            var m = markers[mi];
            if (!m || !m.getBoundingClientRect) {
                continue;
            }
            markerRects.push(m.getBoundingClientRect());
        }
        var highlightRectRaw = _unionRects(markerRects);
        if (!highlightRectRaw) {
            throw new Error("tutorial-card 需要锚定高亮区域，但 markerRect 为空（可能为 0 尺寸）。group=" + group + ", state=" + state);
        }

        var cardRectRaw = card.getBoundingClientRect();
        var cardW = Number(cardRectRaw.width || 0);
        var cardH = Number(cardRectRaw.height || 0);
        if (!isFinite(cardW) || !isFinite(cardH) || cardW <= 1 || cardH <= 1) {
            throw new Error("tutorial-card 尺寸为 0，无法锚定定位（检查是否 display:none）。group=" + group + ", state=" + state);
        }

        // Convert viewport rects to canvas-local coordinates (consistent with later extraction: rect - bodyRect).
        var hl = {
            left: highlightRectRaw.left - bodyRect.left,
            top: highlightRectRaw.top - bodyRect.top,
            right: highlightRectRaw.right - bodyRect.left,
            bottom: highlightRectRaw.bottom - bodyRect.top
        };
        var hlCx = (hl.left + hl.right) / 2;
        var hlCy = (hl.top + hl.bottom) / 2;

        function _fitCandidate(x, y) {
            var xx = Number(x);
            var yy = Number(y);
            if (!isFinite(xx) || !isFinite(yy)) {
                return null;
            }
            var minX = safeMargin;
            var minY = safeMargin;
            var maxX = cw - safeMargin - cardW;
            var maxY = ch - safeMargin - cardH;
            if (maxX < minX) {
                maxX = minX;
            }
            if (maxY < minY) {
                maxY = minY;
            }
            var clampedX = _clamp(xx, minX, maxX);
            var clampedY = _clamp(yy, minY, maxY);
            var fullyFits = (clampedX === xx && clampedY === yy);
            return { x: clampedX, y: clampedY, fullyFits: fullyFits };
        }

        var candidates = [];
        function _pushPlacement(p) {
            if (p === "right") {
                candidates.push(_fitCandidate(hl.right + gap, hlCy - cardH / 2));
                return;
            }
            if (p === "left") {
                candidates.push(_fitCandidate(hl.left - gap - cardW, hlCy - cardH / 2));
                return;
            }
            if (p === "bottom") {
                candidates.push(_fitCandidate(hlCx - cardW / 2, hl.bottom + gap));
                return;
            }
            if (p === "top") {
                candidates.push(_fitCandidate(hlCx - cardW / 2, hl.top - gap - cardH));
                return;
            }
        }

        if (placement === "auto") {
            // 优先策略：尽量不遮挡高亮区域（右/左/下/上）。
            _pushPlacement("right");
            _pushPlacement("left");
            _pushPlacement("bottom");
            _pushPlacement("top");
        } else {
            _pushPlacement(placement);
        }

        var chosen = null;
        for (var ci = 0; ci < candidates.length; ci++) {
            var c = candidates[ci];
            if (!c) continue;
            if (c.fullyFits) {
                chosen = c;
                break;
            }
            if (!chosen) {
                // fallback：即便不 fully fit，也至少保证在画布内
                chosen = c;
            }
        }
        if (!chosen) {
            continue;
        }

        // NOTE:
        // - chosen.x/y 是“画布坐标”（viewport rect - bodyRect），与后续 dom_extract 输出 rect 口径一致。
        // - 但绝对定位元素的 left/top 是相对其 offsetParent 的 padding box（而不是画布原点）。
        //   若不做坐标系转换，卡片会在存在 offsetParent（例如容器内 absolute 布局）时整体偏移，
        //   进而导致“卡片跑出画布”或与高亮区域重叠的回归。
        var chosenViewportX = chosen.x + bodyRect.left;
        var chosenViewportY = chosen.y + bodyRect.top;
        var baseLeft = 0;
        var baseTop = 0;
        var offsetParent = card.offsetParent || null;
        if (offsetParent && offsetParent.getBoundingClientRect) {
            var parentRect = offsetParent.getBoundingClientRect();
            // containing block is offsetParent's padding box; getBoundingClientRect() is border box.
            var parentClientLeft = Number(offsetParent.clientLeft || 0);
            var parentClientTop = Number(offsetParent.clientTop || 0);
            baseLeft = Number(parentRect.left || 0) + parentClientLeft;
            baseTop = Number(parentRect.top || 0) + parentClientTop;
        }
        card.style.left = String(Math.round(chosenViewportX - baseLeft)) + "px";
        card.style.top = String(Math.round(chosenViewportY - baseTop)) + "px";
        // Avoid mixing top/bottom/transform layouts after anchoring.
        card.style.right = "auto";
        card.style.bottom = "auto";
        card.style.transform = "none";
    }
}

export function extractDisplayElementsData(targetDocument) {
    if (!targetDocument || !targetDocument.body) {
        return {
            elements: [],
            bodySize: { width: 0, height: 0 },
            variableDefaults: {},
            diagnostics: {
                reason: "NO_DOCUMENT_OR_BODY",
                bodyRect: null,
                canvasSize: { width: 0, height: 0 },
                canvasRect: null,
                cssVars: {
                    inline: { canvasWidth: "", canvasHeight: "" },
                    computed: { canvasWidth: "", canvasHeight: "" }
                },
                stats: {
                    totalVisited: 0,
                    totalEmitted: 0,
                    skippedNoTagName: 0,
                    skippedTagIgnored: 0,
                    skippedExcludedElement: 0,
                    skippedNoViewOrComputedStyle: 0,
                    skippedNoComputedStyle: 0,
                    skippedDisplayNone: 0,
                    skippedVisibilityHiddenWithoutUiState: 0,
                    skippedZeroRectNonButton: 0,
                    skippedZeroRectButtonNoUnionRect: 0,
                    skippedOutsideCanvas: 0
                }
            }
        };
    }

    function _extractVariableDefaultsFromDocument(doc) {
        // Web UI 变量默认值（写回端用于“自动创建的实体自定义变量”的默认值）。
        //
        // 约定：页面任意元素可声明：
        //   data-ui-variable-defaults='{"关卡.some_int":100,"玩家自身.some_text":"hello","lv.level_name":"xx"}'
        //
        // - 支持多个声明（按 DOM 顺序合并，后者覆盖前者同名 key）
        // - 元素可为 display:none；该数据不参与扁平化导出与几何计算，仅作为“导出附加元信息”
        // - 若 JSON 非法或非 object，将直接抛错（fail-fast，避免 silently 生成错误存档）
        var out = {};
        if (!doc || !doc.querySelectorAll) {
            return out;
        }
        var nodes = doc.querySelectorAll("[data-ui-variable-defaults]");
        if (!nodes || nodes.length <= 0) {
            return out;
        }
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el || !el.getAttribute) {
                continue;
            }
            var text = String(el.getAttribute("data-ui-variable-defaults") || "").trim();
            if (!text) {
                continue;
            }
            var parsed = JSON.parse(text);
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                throw new Error("data-ui-variable-defaults 必须是 JSON object，例如 {\"关卡.hp\":100}。");
            }
            for (var k in parsed) {
                if (!Object.prototype.hasOwnProperty.call(parsed, k)) {
                    continue;
                }
                var key = String(k || "").trim();
                if (!key) {
                    continue;
                }
                out[key] = parsed[k];
            }
        }
        return out;
    }

    function _normalizeUiStateAttr(text) {
        return String(text || "").trim();
    }

    function _parseUiStateBool(text) {
        var lowered = String(text || "").trim().toLowerCase();
        if (!lowered) {
            return false;
        }
        return lowered === "1" || lowered === "true" || lowered === "yes" || lowered === "on";
    }

    function _getFlatZBiasFromNearestAncestor(element) {
        // `data-flat-z-bias` 语义：作为“局部 stacking context 的抬升”使用。
        // 扁平化会把一个组件拆成很多独立图层，因此必须让 bias 对子节点生效，否则会出现：
        // - 外层卡片被抬高了，但卡片内部标题/正文/按钮仍被其它层遮挡
        //
        // 规则：向上寻找最近的 `[data-flat-z-bias]`，并把该值透传到当前元素。
        // - 允许子节点显式声明新的 bias 覆盖祖先值
        if (!element) {
            return null;
        }
        var cur = element;
        while (cur) {
            if (cur.getAttribute) {
                var v = cur.getAttribute("data-flat-z-bias");
                if (v !== null && v !== undefined) {
                    var trimmed = String(v || "").trim();
                    if (trimmed) {
                        return trimmed;
                    }
                }
            }
            cur = cur.parentElement || null;
        }
        return null;
    }

    function _getUiStateMetaForElement(element) {
        // UI 多状态语义（兼容两种作者写法）：
        //
        // A) “组+状态在同一节点”（老写法/按钮子层常用）：
        //    <div data-ui-state-group="g" data-ui-state="a" data-ui-state-default="1">...</div>
        //
        // B) “组在根节点，状态在子节点”（更自然的容器写法）：
        //    <section data-ui-state-group="g">
        //      <div data-ui-state="a" data-ui-state-default="1">...</div>
        //      <div data-ui-state="b">...</div>
        //    </section>
        //
        // 规则：
        // - group 取最近的 `[data-ui-state-group]`
        // - state/default 优先取“同组范围内最近的 `[data-ui-state]`”，否则回退到 group 节点自身
        //
        // 说明：
        // - 扁平化输出会丢失原始 DOM 层级，state 的初始显隐只能靠透传的数据属性恢复。
        // - 因此这里必须把“组 + 当前 state”正确绑定到每个可视元素上。
        if (!element) {
            return null;
        }
        if (!element.closest) {
            return null;
        }
        var groupNode = element.closest("[data-ui-state-group]");
        if (!groupNode || !groupNode.getAttribute) {
            return null;
        }
        var group = _normalizeUiStateAttr(groupNode.getAttribute("data-ui-state-group"));
        if (!group) {
            return null;
        }

        var stateNode = element.closest("[data-ui-state]");
        if (stateNode && groupNode && groupNode.contains && !groupNode.contains(stateNode)) {
            stateNode = null;
        }
        if (!stateNode) {
            stateNode = groupNode;
        }
        var state = _normalizeUiStateAttr(stateNode.getAttribute ? stateNode.getAttribute("data-ui-state") : "");
        var isDefault = _parseUiStateBool(stateNode.getAttribute ? stateNode.getAttribute("data-ui-state-default") : "");
        return { group: group, state: state, isDefault: isDefault };
    }

    function _findAtomicComponentRoot(element) {
        // 原子组件根：用于把“按钮内部的 span 文本”等叶子元素归属到按钮本体
        // 关键规则：
        // - 若元素位于某个 <button> 内部，则强制把该 <button> 作为组件根。
        //   这能避免“按钮内部的子层（例如高亮底板）自己带 data-ui-key 时，
        //   被误当成独立组件根”从而导致预览页/导出控件列表把多个按钮的同名子控件合并到同一个组。
        if (element && element.closest) {
            var closestButton = element.closest("button");
            if (closestButton) {
                return closestButton;
            }
        }
        var cur = element;
        while (cur) {
            if (!cur.tagName) {
                break;
            }
            var tag = String(cur.tagName || "").toLowerCase();
            if (tag === "button") {
                return cur;
            }
            if (cur.classList && cur.classList.contains("btn")) {
                return cur;
            }
            if (cur.getAttribute) {
                var dataUiKey = cur.getAttribute("data-ui-key");
                if (dataUiKey) {
                    return cur;
                }
                if (cur.id) {
                    return cur;
                }
                var debugLabel = cur.getAttribute("data-debug-label");
                if (debugLabel) {
                    return cur;
                }
                var role = cur.getAttribute("role");
                if (String(role || "").trim().toLowerCase() === "button") {
                    return cur;
                }
                var uiRole = cur.getAttribute("data-ui-role");
                if (String(uiRole || "").trim().toLowerCase() === "button") {
                    return cur;
                }
            }
            cur = cur.parentElement || null;
        }
        return element;
    }

    var variableDefaults = _extractVariableDefaultsFromDocument(targetDocument);
    var resultElements = [];
    var processedElements = new Set();
    var elementIndexByNode = new Map();
    var effectiveScaleCache = new WeakMap();
    var bodyRect = targetDocument.body.getBoundingClientRect();
    var canvasSize = _getCanvasSizeFromDocument(targetDocument, bodyRect);

    // 扁平化前：对“指引卡片”做锚定布局修正（不注入脚本，仅在 compute 文档里改 style）。
    _applyAnchoredTutorialCards(targetDocument, bodyRect, canvasSize);

    var canvasRect = {
        left: bodyRect.left,
        top: bodyRect.top,
        right: bodyRect.left + canvasSize.width,
        bottom: bodyRect.top + canvasSize.height
    };

    // Diagnostics: explain why extraction might be empty (for non-programmers + programmers).
    var _cssInline = (function () {
        var style = targetDocument && targetDocument.documentElement ? targetDocument.documentElement.style : null;
        return {
            canvasWidth: style ? String(style.getPropertyValue("--canvas-width") || "") : "",
            canvasHeight: style ? String(style.getPropertyValue("--canvas-height") || "") : ""
        };
    })();
    var _cssComputed = (function () {
        var view = (targetDocument && targetDocument.defaultView) ? targetDocument.defaultView : null;
        if (!view || !view.getComputedStyle || !targetDocument.documentElement) {
            return { canvasWidth: "", canvasHeight: "" };
        }
        var cs = view.getComputedStyle(targetDocument.documentElement);
        if (!cs || !cs.getPropertyValue) {
            return { canvasWidth: "", canvasHeight: "" };
        }
        return {
            canvasWidth: String(cs.getPropertyValue("--canvas-width") || ""),
            canvasHeight: String(cs.getPropertyValue("--canvas-height") || "")
        };
    })();
    var _diagnostics = {
        reason: "",
        bodyRect: {
            left: Number(bodyRect.left || 0),
            top: Number(bodyRect.top || 0),
            width: Number(bodyRect.width || 0),
            height: Number(bodyRect.height || 0)
        },
        canvasSize: {
            width: Number(canvasSize.width || 0),
            height: Number(canvasSize.height || 0)
        },
        canvasRect: {
            left: Number(canvasRect.left || 0),
            top: Number(canvasRect.top || 0),
            right: Number(canvasRect.right || 0),
            bottom: Number(canvasRect.bottom || 0)
        },
        cssVars: {
            inline: _cssInline,
            computed: _cssComputed
        },
        stats: {
            totalVisited: 0,
            totalEmitted: 0,
            skippedNoTagName: 0,
            skippedTagIgnored: 0,
            skippedExcludedElement: 0,
            skippedNoViewOrComputedStyle: 0,
            skippedNoComputedStyle: 0,
            skippedDisplayNone: 0,
            skippedVisibilityHiddenWithoutUiState: 0,
            skippedZeroRectNonButton: 0,
            skippedZeroRectButtonNoUnionRect: 0,
            skippedOutsideCanvas: 0
        }
    };

    function isExcludedElement(element) {
        if (!element) {
            return true;
        }
        if (element.classList) {
            if (element.classList.contains("canvas-toolbar") || element.classList.contains("page-switch-toolbar")) {
                return true;
            }
        }
        var elementId = element.id || "";
        if (
            elementId === "debug-overlay" ||
            elementId === "debug-text-panel" ||
            elementId === "selection-overlay" ||
            elementId === "selection-box" ||
            elementId === "debug-copy-toast" ||
            elementId === "debug-reverse-toggle" ||
            elementId === "debug-reverse-toggle-label"
        ) {
            return true;
        }
        return false;
    }

    function isDisplayAreaIntersection(elementRect) {
        if (!elementRect) {
            return false;
        }
        return (
            elementRect.right > canvasRect.left &&
            elementRect.left < canvasRect.right &&
            elementRect.bottom > canvasRect.top &&
            elementRect.top < canvasRect.bottom
        );
    }

    function processElement(element, depth) {
        if (!element || processedElements.has(element)) {
            return;
        }

        var tagNameUpper = element.tagName;
        if (!tagNameUpper) {
            _diagnostics.stats.skippedNoTagName += 1;
            return;
        }
        _diagnostics.stats.totalVisited += 1;
        var tagName = tagNameUpper.toUpperCase();
        if (tagName === "SCRIPT" || tagName === "STYLE" || tagName === "LINK" || tagName === "META" || tagName === "HEAD") {
            _diagnostics.stats.skippedTagIgnored += 1;
            return;
        }

        if (isExcludedElement(element)) {
            _diagnostics.stats.skippedExcludedElement += 1;
            return;
        }

        processedElements.add(element);

        var elementRect = element.getBoundingClientRect();
        // 某些环境（例如 headless / 早期加载阶段）下，`document.defaultView` 可能为 null，
        // 直接访问会抛错并中断整页扁平化；此处做降级兜底到全局 window（同源 about:srcdoc 下可用）。
        var view = (targetDocument && targetDocument.defaultView) ? targetDocument.defaultView : window;
        if (!view || !view.getComputedStyle) {
            _diagnostics.stats.skippedNoViewOrComputedStyle += 1;
            return;
        }
        var computedStyle = view.getComputedStyle(element);

        if (!computedStyle) {
            _diagnostics.stats.skippedNoComputedStyle += 1;
            return;
        }

        var effectiveScale = _computeEffectiveScaleForElement(element, view, effectiveScaleCache);
        var effectiveScaleX = _clampScale(effectiveScale.sx);
        var effectiveScaleY = _clampScale(effectiveScale.sy);
        // 文字字号等一般假设等比缩放；此处用较小轴作为“保守字号缩放”。
        var effectiveUniformScale = Math.min(effectiveScaleX, effectiveScaleY);

        var uiStateMeta = _getUiStateMetaForElement(element);

        // display:none：没有盒子/几何信息，无法导出（多状态也不例外）
        if (computedStyle.display === "none") {
            _diagnostics.stats.skippedDisplayNone += 1;
            return;
        }
        // visibility:hidden：默认跳过；但若属于“多状态容器”，仍需导出并在 bundle 中由可见性覆盖控制初始态
        if (computedStyle.visibility === "hidden" && !uiStateMeta) {
            _diagnostics.stats.skippedVisibilityHiddenWithoutUiState += 1;
            return;
        }

        function _isExplicitButtonSemantic(el) {
            if (!el || !el.getAttribute) {
                return false;
            }
            var uiRole = String(el.getAttribute("data-ui-role") || "").trim().toLowerCase();
            if (uiRole === "button") {
                return true;
            }
            var role = String(el.getAttribute("role") || "").trim().toLowerCase();
            if (role === "button") {
                return true;
            }
            var interactKey = String(el.getAttribute("data-ui-interact-key") || "").trim();
            if (interactKey) {
                return true;
            }
            var uiAction = String(el.getAttribute("data-ui-action") || "").trim();
            if (uiAction) {
                return true;
            }
            return false;
        }

        function _unionDescendantsRect(el) {
            if (!el) {
                return null;
            }
            // 注意：仅看 direct children 在某些布局下会取不到（例如 button 本体 0 尺寸，
            // 但实际可见盒子由更深层的文字/span 生成）。因此这里扩展为 union 整个子树。
            var nodes = [];
            if (el.children && el.children.length > 0) {
                for (var ci = 0; ci < el.children.length; ci++) {
                    nodes.push(el.children[ci]);
                }
            }
            if (el.querySelectorAll) {
                var desc = el.querySelectorAll("*");
                for (var di = 0; di < (desc ? desc.length : 0); di++) {
                    nodes.push(desc[di]);
                }
            }
            if (!nodes || nodes.length <= 0) {
                return null;
            }
            var u = null; // {left, top, right, bottom}
            // 防御：避免极端大 DOM 导致过慢
            var cap = Math.min(nodes.length, 500);
            for (var i = 0; i < cap; i++) {
                var c = nodes[i];
                if (!c || !c.getBoundingClientRect) {
                    continue;
                }
                var r = c.getBoundingClientRect();
                var w = Number(r.width || 0);
                var h = Number(r.height || 0);
                if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
                    continue;
                }
                var l = Number(r.left || 0);
                var t = Number(r.top || 0);
                var rr = l + w;
                var bb = t + h;
                if (!u) {
                    u = { left: l, top: t, right: rr, bottom: bb };
                } else {
                    if (l < u.left) u.left = l;
                    if (t < u.top) u.top = t;
                    if (rr > u.right) u.right = rr;
                    if (bb > u.bottom) u.bottom = bb;
                }
            }
            if (!u) {
                return null;
            }
            var uw = u.right - u.left;
            var uh = u.bottom - u.top;
            if (!isFinite(uw) || !isFinite(uh) || uw <= 0 || uh <= 0) {
                return null;
            }
            return { left: u.left, top: u.top, width: uw, height: uh, right: u.right, bottom: u.bottom };
        }

        // 兼容：某些布局下（尤其是 grid/flex + 绝对定位子层），按钮本体可能被浏览器计算为 0 尺寸，
        // 但其子层（背景/文字）是有尺寸的。若按钮具备“显式按钮语义”，则用子层 unionRect 作为按钮盒子，
        // 以保证后续 layer_data 能生成 button_anchor，从而导出“道具展示”按钮锚点。
        if (elementRect.width === 0 || elementRect.height === 0) {
            if (_isExplicitButtonSemantic(element)) {
                var unionRect = _unionDescendantsRect(element);
                if (unionRect) {
                    elementRect = unionRect;
                } else {
                    _diagnostics.stats.skippedZeroRectButtonNoUnionRect += 1;
                    var childNodeList0 = element.children || [];
                    for (var childIndex0 = 0; childIndex0 < childNodeList0.length; childIndex0++) {
                        processElement(childNodeList0[childIndex0], depth + 1);
                    }
                    return;
                }
            } else {
                _diagnostics.stats.skippedZeroRectNonButton += 1;
                var childNodeList = element.children || [];
                for (var childIndex = 0; childIndex < childNodeList.length; childIndex++) {
                    processElement(childNodeList[childIndex], depth + 1);
                }
                return;
            }
        }

        if (!isDisplayAreaIntersection(elementRect)) {
            _diagnostics.stats.skippedOutsideCanvas += 1;
            return;
        }

        var paddingTop = Number.parseFloat(computedStyle.paddingTop) || 0;
        var paddingRight = Number.parseFloat(computedStyle.paddingRight) || 0;
        var paddingBottom = Number.parseFloat(computedStyle.paddingBottom) || 0;
        var paddingLeft = Number.parseFloat(computedStyle.paddingLeft) || 0;

        var directTextContent = "";
        var fullTextContent = String(element.textContent || "").trim();
        var childNodesList = element.childNodes || [];
        for (var nodeIndex = 0; nodeIndex < childNodesList.length; nodeIndex++) {
            var nodeItem = childNodesList[nodeIndex];
            if (nodeItem && nodeItem.nodeType === Node.TEXT_NODE) {
                var nodeText = String(nodeItem.textContent || "").trim();
                if (nodeText) {
                    directTextContent += (directTextContent ? " " : "") + nodeText;
                }
            }
        }

        var isInsideButton = false;
        if (element && element.closest) {
            var closestButton = element.closest("button");
            if (closestButton && closestButton !== element) {
                isInsideButton = true;
            }
        }
        var isInsideGameCutout = false;
        if (element && element.closest) {
            var closestCutout = element.closest("." + String(GAME_CUTOUT_CLASS || "game-cutout"));
            if (closestCutout && closestCutout !== element) {
                isInsideGameCutout = true;
            }
        }

        var ownerNode = _findAtomicComponentRoot(element);
        var ownerIndex = elementIndexByNode.has(ownerNode) ? elementIndexByNode.get(ownerNode) : null;
        var ownerDerivedDebugLabel = (function () {
            // 兜底：当 owner 是 `.btn` 容器但没有任何显式 key（data-ui-key/id/data-debug-label）时，用其文本内容生成可读标签
            if (!ownerNode || !ownerNode.classList || !ownerNode.classList.contains("btn") || !ownerNode.getAttribute) {
                return null;
            }
            var explicitUiKey = ownerNode.getAttribute("data-ui-key");
            if (String(explicitUiKey || "").trim()) {
                return null;
            }
            var explicitDbg = ownerNode.getAttribute("data-debug-label");
            if (String(explicitDbg || "").trim()) {
                return null;
            }
            if (ownerNode.id) {
                return null;
            }
            var raw = String(ownerNode.textContent || "").trim().replace(/\s+/g, " ");
            if (!raw) {
                return null;
            }
            if (raw.length > 30) {
                raw = raw.slice(0, 30);
            }
            return raw;
        })();

        resultElements.push({
            tagName: element.tagName.toLowerCase(),
            id: element.id || null,
            className: element.className || null,
            attributes: {
                ariaLabel: element.getAttribute ? (element.getAttribute("aria-label") || null) : null,
                role: element.getAttribute ? (element.getAttribute("role") || null) : null,
                onclick: element.getAttribute ? (element.getAttribute("onclick") || null) : null,
                dataDebugLabel: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-debug-label") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.debugLabel ? String(ds.debugLabel || "") : null;
                })(),
                dataUiKey: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-key") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiKey ? String(ds.uiKey || "") : null;
                })(),
                // 可选：显式声明“组件组 key”（用于把多个控件强制归到同一个组件组里）。
                //
                // 说明：
                // - 写回端的“组件打组/组容器”是按 widget.__html_component_key 分组创建组容器；
                // - 浏览器导出侧的 widget.__html_component_key 来自 `src/ui_export/keys.js`；
                // - 若多个控件希望被视为同一个“控件组”（例如“选关 + 退出”两个按钮作为一个可复用控件组模板），
                //   可在它们的根元素上写相同的 `data-ui-component-key="top_actions"`；
                // - `data-ui-save-template` 仍用于“沉淀模板名”，二者配合可精确控制“存成模板”的范围。
                dataUiComponentKey: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-component-key") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiComponentKey ? String(ds.uiComponentKey || "") : null;
                })(),
                dataUiRole: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-role") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiRole ? String(ds.uiRole || "") : null;
                })(),
                // 导出语义提示（可选）：
                // - data-ui-export-as="decor"：保持元素可见/可分组，但导出时强制不把它当“按钮语义”，
                //   用于解决 `<button data-ui-key>` 仅用于视觉而不应生成“道具展示按钮锚点”的场景。
                dataUiExportAs: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-export-as") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiExportAs ? String(ds.uiExportAs || "") : null;
                })(),
                // 可选：将“写回到游戏的文本内容”与“网页用于排版的示例文本”解耦。
                // - data-ui-text：导出为 TextBox 的 settings.text_content（允许写 {{lv.xxx}}/{1:lv.xxx} 等占位符）
                // - 元素自身的文本内容用于网页排版测量（建议写短示例，避免用长变量路径把宽度撑爆）
                dataUiText: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-text") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiText ? String(ds.uiText || "") : null;
                })(),
                // 文本框对齐（显式覆盖，新增）：
                // - 目的：让作者能直接声明“导出到 TextBox 的对齐方式”，不再依赖 computed style 推断。
                // - 用法：
                //   - data-ui-text-align="left|center|right"
                //   - data-ui-text-valign="top|middle|bottom"
                //   - 兼容别名：data-ui-text-align-h / data-ui-text-align-v
                dataUiTextAlign: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-text-align") || null) : null;
                    if (a) return a;
                    var a2 = element.getAttribute ? (element.getAttribute("data-ui-text-align-h") || null) : null;
                    if (a2) return a2;
                    var ds = element.dataset || null;
                    return ds && ds.uiTextAlign ? String(ds.uiTextAlign || "") : null;
                })(),
                dataUiTextValign: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-text-valign") || null) : null;
                    if (a) return a;
                    var a2 = element.getAttribute ? (element.getAttribute("data-ui-text-align-v") || null) : null;
                    if (a2) return a2;
                    var ds = element.dataset || null;
                    return ds && ds.uiTextValign ? String(ds.uiTextValign || "") : null;
                })(),
                // Alignment intent (optional): used by validation/lints to avoid "dev missed right-align" issues.
                dataUiAlign: element.getAttribute ? (element.getAttribute("data-ui-align") || null) : null,
                dataUiAlignOk: element.getAttribute ? (element.getAttribute("data-ui-align-ok") || null) : null,
                dataProgressCurrentVar: element.getAttribute ? (element.getAttribute("data-progress-current-var") || null) : null,
                dataProgressMinVar: element.getAttribute ? (element.getAttribute("data-progress-min-var") || null) : null,
                dataProgressMaxVar: element.getAttribute ? (element.getAttribute("data-progress-max-var") || null) : null,
                // 进度条形状（可选）：用于覆盖导出端的 shape 推断（横向/纵向/圆环三选一）
                dataProgressShape: element.getAttribute ? (element.getAttribute("data-progress-shape") || null) : null,
                dataInventoryItemId: element.getAttribute ? (element.getAttribute("data-inventory-item-id") || null) : null,
                dataGameAreaName: element.getAttribute ? (element.getAttribute(String(GAME_CUTOUT_NAME_ATTR || "data-game-area")) || null) : null,
                dataGameCutoutAllowNonSquare: element.getAttribute ? (element.getAttribute("data-game-cutout-allow-non-square") || null) : null,
                // 高亮展示区域（可选）：控制“周围压暗遮罩”的强度。
                // 约定：
                // - data-highlight-overlay-alpha="0.45|0.25"（不填默认 0.45）
                dataHighlightOverlayAlpha: element.getAttribute ? (element.getAttribute(String(HIGHLIGHT_OVERLAY_ALPHA_ATTR || "data-highlight-overlay-alpha")) || null) : null,
                // 扁平化层级偏移（可选）：用于把某些控件“整体抬高”到更上层。
                // 约定：
                // - data-flat-z-bias="1000000"（整数，允许负数；默认 0）
                // 用途：
                // - 指引/遮罩类 UI：确保压暗层能盖住所有普通 UI，但指引卡片仍可通过更高 bias 保持可见
                dataFlatZBias: (function () {
                    // 注意：这里必须支持“祖先继承”，否则组件内部层会丢 bias。
                    if (!element) return null;
                    var explicit = element.getAttribute ? (element.getAttribute("data-flat-z-bias") || null) : null;
                    if (explicit !== null && explicit !== undefined) {
                        var trimmed = String(explicit || "").trim();
                        if (trimmed) return trimmed;
                    }
                    return _getFlatZBiasFromNearestAncestor(element);
                })(),
                dataUiAction: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-action") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiAction ? String(ds.uiAction || "") : null;
                })(),
                dataUiActionArgs: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-action-args") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiActionArgs ? String(ds.uiActionArgs || "") : null;
                })(),
                // 可选：标记“该组件组需要沉淀为控件组库自定义模板”。
                // - 建议在组件根元素上声明（即拥有 data-ui-key 的元素）。
                // - 也允许后代元素继承 owner 标记（见 componentOwnerDataUiSaveTemplate）。
                //
                // 约定：
                // - data-ui-save-template="<模板名>"：导出/写回时会尝试把该组件组保存为“自定义模板”（控件组库 + template_root）。
                // - data-ui-save-template="1"/"true"：表示“需要保存为模板”，名称由导出端根据 group_key 生成默认名。
                dataUiSaveTemplate: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-save-template") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiSaveTemplate ? String(ds.uiSaveTemplate || "") : null;
                })(),
                dataUiInteractKey: (function () {
                    if (!element) return null;
                    var a = element.getAttribute ? (element.getAttribute("data-ui-interact-key") || null) : null;
                    if (a) return a;
                    var ds = element.dataset || null;
                    return ds && ds.uiInteractKey ? String(ds.uiInteractKey || "") : null;
                })(),
                dataUiStateGroup: uiStateMeta ? String(uiStateMeta.group || "") : null,
                dataUiState: uiStateMeta ? String(uiStateMeta.state || "") : null,
                dataUiStateDefault: uiStateMeta ? (uiStateMeta.isDefault ? "1" : "0") : null,
                componentOwnerId: (function () {
                    var owner = ownerNode;
                    return owner && owner.id ? String(owner.id || "") : null;
                })(),
                componentOwnerDataUiKey: (function () {
                    var owner = ownerNode;
                    return owner && owner.getAttribute ? (owner.getAttribute("data-ui-key") || null) : null;
                })(),
                componentOwnerDataUiComponentKey: (function () {
                    var owner = ownerNode;
                    if (!(owner && owner.getAttribute)) {
                        return null;
                    }
                    var a = owner.getAttribute("data-ui-component-key") || null;
                    if (a) {
                        return a;
                    }
                    var ds = owner.dataset || null;
                    return ds && ds.uiComponentKey ? String(ds.uiComponentKey || "") : null;
                })(),
                componentOwnerDataDebugLabel: (function () {
                    var owner = ownerNode;
                    if (!(owner && owner.getAttribute)) {
                        return null;
                    }
                    var explicit = owner.getAttribute("data-debug-label") || null;
                    if (explicit) {
                        return explicit;
                    }
                    return ownerDerivedDebugLabel;
                })(),
                componentOwnerDataUiExportAs: (function () {
                    var owner = ownerNode;
                    if (!(owner && owner.getAttribute)) {
                        return null;
                    }
                    var a = owner.getAttribute("data-ui-export-as") || null;
                    if (a) {
                        return a;
                    }
                    var ds = owner.dataset || null;
                    return ds && ds.uiExportAs ? String(ds.uiExportAs || "") : null;
                })(),
                componentOwnerDataUiSaveTemplate: (function () {
                    var owner = ownerNode;
                    if (!(owner && owner.getAttribute)) {
                        return null;
                    }
                    var a = owner.getAttribute("data-ui-save-template") || null;
                    if (a) {
                        return a;
                    }
                    var ds = owner.dataset || null;
                    return ds && ds.uiSaveTemplate ? String(ds.uiSaveTemplate || "") : null;
                })(),
                componentOwnerElementIndex: (ownerIndex !== null && ownerIndex !== undefined) ? String(ownerIndex) : null
            },
            inButton: isInsideButton,
            inGameCutout: isInsideGameCutout,
            depth: depth,
            rect: {
                left: elementRect.left - bodyRect.left,
                top: elementRect.top - bodyRect.top,
                width: elementRect.width,
                height: elementRect.height
            },
            padding: {
                top: paddingTop,
                right: paddingRight,
                bottom: paddingBottom,
                left: paddingLeft
            },
            styles: {
                backgroundColor: computedStyle.backgroundColor,
                backgroundImage: computedStyle.backgroundImage,
                borderTopColor: computedStyle.borderTopColor,
                borderRightColor: computedStyle.borderRightColor,
                borderBottomColor: computedStyle.borderBottomColor,
                borderLeftColor: computedStyle.borderLeftColor,
                color: computedStyle.color,
                fontSize: computedStyle.fontSize,
                fontWeight: computedStyle.fontWeight,
                fontFamily: computedStyle.fontFamily,
                textAlign: computedStyle.textAlign,
                textTransform: computedStyle.textTransform,
                lineHeight: computedStyle.lineHeight,
                letterSpacing: computedStyle.letterSpacing,
                borderRadius: computedStyle.borderRadius,
                borderTop: computedStyle.borderTop,
                borderRight: computedStyle.borderRight,
                borderBottom: computedStyle.borderBottom,
                borderLeft: computedStyle.borderLeft,
                borderTopWidth: computedStyle.borderTopWidth,
                borderRightWidth: computedStyle.borderRightWidth,
                borderBottomWidth: computedStyle.borderBottomWidth,
                borderLeftWidth: computedStyle.borderLeftWidth,
                boxShadow: computedStyle.boxShadow,
                textShadow: computedStyle.textShadow,
                opacity: computedStyle.opacity,
                transform: computedStyle.transform,
                cursor: computedStyle.cursor,
                whiteSpace: computedStyle.whiteSpace,
                overflow: computedStyle.overflow,
                visibility: computedStyle.visibility,
                textOverflow: computedStyle.textOverflow,
                wordBreak: computedStyle.wordBreak,
                wordWrap: computedStyle.wordWrap,
                display: computedStyle.display,
                position: computedStyle.position,
                zIndex: computedStyle.zIndex,
                justifyContent: computedStyle.justifyContent,
                alignItems: computedStyle.alignItems,
                // 额外字段：用于“整体 transform scale”场景下补偿字号/行高等（避免导出到 GIL 后文字溢出）。
                effectiveScaleX: effectiveScaleX,
                effectiveScaleY: effectiveScaleY,
                effectiveScale: effectiveUniformScale,
                flexDirection: computedStyle.flexDirection
            },
            textContent: directTextContent,
            fullTextContent: fullTextContent,
            hasChildren: !!(element.children && element.children.length > 0)
        });
        _diagnostics.stats.totalEmitted += 1;

        elementIndexByNode.set(element, resultElements.length - 1);

        var childElements = element.children || [];
        for (var elementChildIndex = 0; elementChildIndex < childElements.length; elementChildIndex++) {
            processElement(childElements[elementChildIndex], depth + 1);
        }
    }

    var bodyChildren = targetDocument.body.children || [];
    for (var rootChildIndex = 0; rootChildIndex < bodyChildren.length; rootChildIndex++) {
        processElement(bodyChildren[rootChildIndex], 0);
    }

    return {
        elements: resultElements,
        bodySize: {
            width: canvasSize.width,
            height: canvasSize.height
        },
        variableDefaults: variableDefaults || {},
        diagnostics: _diagnostics
    };
}

