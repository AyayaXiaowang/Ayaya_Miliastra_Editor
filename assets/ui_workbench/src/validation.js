import { GAME_CUTOUT_CLASS, GAME_CUTOUT_NAME_ATTR, HIGHLIGHT_DISPLAY_AREA_CLASS, HIGHLIGHT_OVERLAY_ALPHA_ATTR } from "./config.js";
import { createIssue } from "./diagnostics.js";

function _safeTrim(text) {
    return String(text || "").trim();
}

function _rectIntersects(a, b) {
    if (!a || !b) return false;
    var ax2 = a.left + a.width;
    var ay2 = a.top + a.height;
    var bx2 = b.left + b.width;
    var by2 = b.top + b.height;
    return !(ax2 <= b.left || bx2 <= a.left || ay2 <= b.top || by2 <= a.top);
}

function _parsePxNumber(valueText) {
    var raw = String(valueText || "").trim().toLowerCase();
    if (!raw) return null;
    if (raw.endsWith("px")) raw = raw.slice(0, -2).trim();
    var n = Number.parseFloat(raw);
    if (!isFinite(n)) return null;
    return n;
}

function _isElementVisibleForValidation(win, el) {
    if (!win || !el) return false;
    var st = win.getComputedStyle(el);
    if (!st) return false;
    var display = _safeTrim(st.display).toLowerCase();
    if (display === "none") return false;
    var vis = _safeTrim(st.visibility).toLowerCase();
    if (vis === "hidden" || vis === "collapse") return false;
    // opacity is generally forbidden in CSS rules, but still handle it defensively.
    var opacity = Number.parseFloat(String(st.opacity || "1"));
    if (isFinite(opacity) && opacity <= 0.01) return false;
    return true;
}

function _rectFromDomRect(r) {
    if (!r) return null;
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
}

function _pickNearestBorderContainerRect(win, el) {
    // Find a reasonable "container" for alignment checks:
    // the nearest ancestor with a visible border (border width > 0), otherwise fall back to body.
    var cur = el;
    while (cur) {
        var p = cur.parentElement || null;
        if (!p) break;
        if (!_isElementVisibleForValidation(win, p)) {
            cur = p;
            continue;
        }
        var st = win.getComputedStyle(p);
        var bwL = _parsePxNumber(st.borderLeftWidth);
        var bwR = _parsePxNumber(st.borderRightWidth);
        var bwT = _parsePxNumber(st.borderTopWidth);
        var bwB = _parsePxNumber(st.borderBottomWidth);
        var hasBorder =
            (bwL !== null && bwL > 0) ||
            (bwR !== null && bwR > 0) ||
            (bwT !== null && bwT > 0) ||
            (bwB !== null && bwB > 0);
        if (hasBorder && p.getBoundingClientRect) {
            return _rectFromDomRect(p.getBoundingClientRect());
        }
        cur = p;
    }
    return null;
}

function _hasDirectNonWhitespaceTextNode(el) {
    if (!el || !el.childNodes) {
        return false;
    }
    for (var i = 0; i < el.childNodes.length; i++) {
        var n = el.childNodes[i];
        if (!n) continue;
        if (n.nodeType === 3) { // TEXT_NODE
            if (_safeTrim(n.nodeValue || "")) {
                return true;
            }
        }
    }
    return false;
}

function _hasElementChildren(el) {
    return !!(el && el.children && el.children.length > 0);
}

function _hasDecorativeClassToken(el) {
    if (!el || !el.classList || !el.classList.length) {
        return false;
    }
    for (var i = 0; i < el.classList.length; i++) {
        var token = String(el.classList[i] || "").trim().toLowerCase();
        if (!token) {
            continue;
        }
        if (token === "deco" || token.indexOf("deco-") === 0 || token.indexOf("deco_") === 0) {
            return true;
        }
    }
    return false;
}

function _isDecorativeElementForOrdering(el, win) {
    if (!el) {
        return false;
    }
    if (el.getAttribute && String(el.getAttribute("data-ui-deco") || "").trim() === "1") {
        return true;
    }
    if (!_hasDecorativeClassToken(el)) {
        return false;
    }
    if (!win || !win.getComputedStyle) {
        return true;
    }
    var st = win.getComputedStyle(el);
    if (!st) {
        return true;
    }
    var pos = _safeTrim(st.position).toLowerCase();
    return pos === "absolute" || pos === "fixed";
}

function _describeElementForEvidence(el) {
    if (!el) {
        return { tag: "", id: "", class_name: "" };
    }
    return {
        tag: el.tagName ? String(el.tagName || "").toLowerCase() : "",
        id: el.id ? String(el.id || "") : "",
        class_name: el.className ? String(el.className || "") : ""
    };
}

function _shouldConsiderAsTextElement(el) {
    if (!el) return false;
    // Only consider elements that "own" text directly (avoid container nodes that merely wrap other text nodes).
    if (!_hasDirectNonWhitespaceTextNode(el)) {
        return false;
    }
    var text = _safeTrim(el.textContent || "");
    if (!text) return false;
    return true;
}

export function validateHtmlSource(htmlText) {
    var issues = [];
    var raw = String(htmlText || "");
    var trimmed = raw.trim();
    if (!trimmed) {
        return issues;
    }

    if (!/<html[\s>]/i.test(raw)) {
        issues.push(createIssue({
            code: "HTML.MISSING_HTML_TAG",
            severity: "error",
            message: "源码不是完整 HTML 文档：缺少 <html>。",
            fix: { kind: "manual", suggestion: "补齐完整 HTML 文档结构（包含 <html> / <head> / <body>）。" }
        }));
    }
    if (!/<body[\s>]/i.test(raw)) {
        issues.push(createIssue({
            code: "HTML.MISSING_BODY_TAG",
            severity: "error",
            message: "源码不是完整 HTML 文档：缺少 <body>。",
            fix: { kind: "manual", suggestion: "补齐 <body>（Workbench 需要在 <body> 内注入/预览）。" }
        }));
    }
    if (/<script[\s>]/i.test(raw)) {
        issues.push(createIssue({
            code: "HTML.SCRIPT_FORBIDDEN",
            severity: "error",
            message: "禁止包含 <script>：Workbench 预览 iframe 默认禁用脚本（sandbox 无 allow-scripts）。",
            fix: { kind: "manual", suggestion: "删除所有 <script>（含内联/外链）。" }
        }));
    }
    if (/<meta\b[^>]*http-equiv\s*=\s*["']?\s*refresh\s*["']?[^>]*>/i.test(raw)) {
        issues.push(createIssue({
            code: "HTML.META_REFRESH_FORBIDDEN",
            severity: "error",
            message: "禁止使用 meta refresh（会导致预览自导航/自刷新）。",
            fix: { kind: "manual", suggestion: "删除 <meta http-equiv=\"refresh\" ...>。" }
        }));
    }
    if (/(::?before|::?after)\b/i.test(raw)) {
        issues.push(createIssue({
            code: "CSS.PSEUDO_ELEMENT_FORBIDDEN",
            severity: "error",
            message: "禁止使用 ::before/::after 伪元素：扁平化不会导出伪元素层。",
            fix: { kind: "manual", suggestion: "改为真实 DOM 子元素（例如 <span>）并设置同等样式。" }
        }));
    }

    // -----------------------------------------------------------------------------
    // Hard rule: font-size must be fixed px (no responsive units/functions).
    // Motivation:
    // - We require text metrics to be stable across canvas sizes for export/writeback.
    // - Avoid vw/vh/vmin/vmax/%/em/rem and calc()/clamp()/min()/max() in font size declarations.
    // -----------------------------------------------------------------------------
    var forbiddenFontSizeUnitRe = /font-size\s*:\s*[^;}{]*(vw|vh|vmin|vmax|%|em|rem)\b/i;
    var forbiddenFontSizeFuncRe = /font-size\s*:\s*[^;}{]*(clamp|min|max|calc)\s*\(/i;
    if (forbiddenFontSizeUnitRe.test(raw) || forbiddenFontSizeFuncRe.test(raw)) {
        issues.push(createIssue({
            code: "TEXT.FONT_SIZE_NOT_FIXED_PX",
            severity: "error",
            message: "硬性约束：font-size 必须写死为固定 px（禁止 vw/vh/vmin/vmax/%/em/rem 以及 calc()/clamp()/min()/max()）。",
            fix: { kind: "manual", suggestion: "建议统一用 :root 的 --fs-* 定义固定 px 字号，并在元素上用 font-size: var(--fs-xxx) 引用。" }
        }));
    }

    // Also forbid responsive definitions for --fs-* variables themselves.
    var forbiddenFsVarUnitRe = /--fs-[a-z0-9_-]+\s*:\s*[^;}{]*(vw|vh|vmin|vmax|%|em|rem)\b/i;
    var forbiddenFsVarFuncRe = /--fs-[a-z0-9_-]+\s*:\s*[^;}{]*(clamp|min|max|calc)\s*\(/i;
    if (forbiddenFsVarUnitRe.test(raw) || forbiddenFsVarFuncRe.test(raw)) {
        issues.push(createIssue({
            code: "TEXT.FONT_SIZE_VAR_NOT_FIXED_PX",
            severity: "error",
            message: "硬性约束：字号变量 --fs-* 必须为固定 px（禁止 vw/vh/%/em/rem 与 calc()/clamp()/min()/max()）。",
            fix: { kind: "manual", suggestion: "把 --fs-* 改为形如 --fs-body: 16px; 并在元素上引用 var(--fs-body)。" }
        }));
    }

    // Forbid transform scale in source CSS: it triggers effective scale compensation during flattening,
    // which will change exported/flattened text font-size.
    var forbiddenScaleRe = /transform\s*:\s*[^;}{]*\bscale\s*\(/i;
    if (forbiddenScaleRe.test(raw)) {
        issues.push(createIssue({
            code: "TEXT.TRANSFORM_SCALE_FORBIDDEN",
            severity: "error",
            message: "硬性约束：禁止 transform: scale(...)（会触发扁平化字号补偿，导致扁平/导出后的文字字号变化）。",
            fix: { kind: "manual", suggestion: "请用 box-shadow/outline/border/颜色对比来做强调，不要用 scale。" }
        }));
    }
    return issues;
}

export function autoFixHtmlSource(htmlText) {
    var raw = String(htmlText || "");
    var applied = [];
    var updated = raw;

    // Idempotent style injection to enforce preview stability: no scrollbars.
    var styleId = "ui-html-workbench-autofix";
    var styleTag = [
        "<style id=\"" + styleId + "\">",
        "html, body {",
        "  height: 100%;",
        "  margin: 0;",
        "  padding: 0;",
        "  overflow: hidden !important;",
        "}",
        "</style>",
    ].join("\n");

    var styleRe = new RegExp("<style\\s+id\\s*=\\s*[\"']" + styleId + "[\"'][^>]*>[\\s\\S]*?<\\/style>", "i");
    var hasStyleTag = styleRe.test(updated);
    if (hasStyleTag) {
        updated = updated.replace(styleRe, styleTag);
        applied.push(createIssue({
            code: "AUTOFIX.INJECT_NO_SCROLL_STYLE_REFRESH",
            severity: "info",
            message: "刷新自动修正样式（禁滚动/标准化 html/body）。",
            fix: { kind: "autofix", suggestion: "已自动刷新 Workbench 稳定性样式。" }
        }));
    } else if (/<head[\s>]/i.test(updated)) {
        updated = updated.replace(/<head([^>]*)>/i, function (m) {
            return m + "\n" + styleTag + "\n";
        });
        applied.push(createIssue({
            code: "AUTOFIX.INJECT_NO_SCROLL_STYLE",
            severity: "info",
            message: "注入自动修正样式（禁滚动/标准化 html/body）。",
            fix: { kind: "autofix", suggestion: "已自动注入 Workbench 稳定性样式（防滚动条）。" }
        }));
    }

    function _wrapMixedTextNodesInHtml(htmlText) {
        if (typeof DOMParser === "undefined") {
            return { html: htmlText, changed: false, count: 0 };
        }
        var parser = new DOMParser();
        var doc = parser.parseFromString(String(htmlText || ""), "text/html");
        if (!doc || !doc.body || !doc.body.querySelectorAll) {
            return { html: htmlText, changed: false, count: 0 };
        }
        var nodes = doc.body.querySelectorAll("*");
        var count = 0;
        for (var i = 0; i < (nodes ? nodes.length : 0); i++) {
            var el = nodes[i];
            if (!el || !_hasElementChildren(el) || !el.childNodes) {
                continue;
            }
            var childList = Array.prototype.slice.call(el.childNodes || []);
            for (var ci = 0; ci < childList.length; ci++) {
                var child = childList[ci];
                if (!child || child.nodeType !== 3) {
                    continue;
                }
                var rawText = String(child.nodeValue || "");
                if (!_safeTrim(rawText)) {
                    continue;
                }
                var span = doc.createElement("span");
                span.textContent = rawText;
                el.replaceChild(span, child);
                count += 1;
            }
        }
        if (count <= 0) {
            return { html: htmlText, changed: false, count: 0 };
        }
        var doctypeMatch = String(htmlText || "").match(/<!doctype[^>]*>/i);
        var serialized = doc.documentElement ? doc.documentElement.outerHTML : String(htmlText || "");
        if (doctypeMatch) {
            serialized = doctypeMatch[0] + "\n" + serialized;
        }
        return { html: serialized, changed: true, count: count };
    }

    var wrapResult = _wrapMixedTextNodesInHtml(updated);
    if (wrapResult && wrapResult.changed) {
        updated = String(wrapResult.html || updated);
        applied.push(createIssue({
            code: "AUTOFIX.WRAP_MIXED_TEXT_NODES",
            severity: "info",
            message: "自动包裹混排文本节点为 <span>，避免扁平化文本漂移。",
            evidence: { wrapped_count: wrapResult.count },
            fix: { kind: "autofix", suggestion: "已把直写文本节点包进 <span>文本</span>。" }
        }));
    }

    function _moveDecorativeElementsToEnd(htmlText) {
        if (typeof DOMParser === "undefined") {
            return { html: htmlText, changed: false, moved_nodes: 0, moved_parents: 0 };
        }
        var parser = new DOMParser();
        var doc = parser.parseFromString(String(htmlText || ""), "text/html");
        if (!doc || !doc.body || !doc.body.querySelectorAll) {
            return { html: htmlText, changed: false, moved_nodes: 0, moved_parents: 0 };
        }
        function _isDecorativeElementByMarkup(el) {
            if (!el) {
                return false;
            }
            if (el.getAttribute && String(el.getAttribute("data-ui-deco") || "").trim() === "1") {
                return true;
            }
            return _hasDecorativeClassToken(el);
        }
        var parents = new Set();
        var all = doc.body.querySelectorAll("*");
        for (var i = 0; i < (all ? all.length : 0); i++) {
            var el = all[i];
            if (!el || !el.parentElement) {
                continue;
            }
            if (_isDecorativeElementByMarkup(el)) {
                parents.add(el.parentElement);
            }
        }
        var movedNodes = 0;
        var movedParents = 0;
        parents.forEach(function (parent) {
            if (!parent || !parent.children || parent.children.length <= 1) {
                return;
            }
            var children = Array.prototype.slice.call(parent.children || []);
            var seenDeco = false;
            var violation = false;
            for (var ci = 0; ci < children.length; ci++) {
                var child = children[ci];
                if (_isDecorativeElementByMarkup(child)) {
                    seenDeco = true;
                    continue;
                }
                if (seenDeco) {
                    violation = true;
                    break;
                }
            }
            if (!violation) {
                return;
            }
            var decoChildren = [];
            for (var di = 0; di < children.length; di++) {
                var child2 = children[di];
                if (_isDecorativeElementByMarkup(child2)) {
                    decoChildren.push(child2);
                }
            }
            if (decoChildren.length <= 0) {
                return;
            }
            for (var di2 = 0; di2 < decoChildren.length; di2++) {
                parent.appendChild(decoChildren[di2]);
                movedNodes += 1;
            }
            movedParents += 1;
        });
        if (movedNodes <= 0) {
            return { html: htmlText, changed: false, moved_nodes: 0, moved_parents: 0 };
        }
        var doctypeMatch = String(htmlText || "").match(/<!doctype[^>]*>/i);
        var serialized = doc.documentElement ? doc.documentElement.outerHTML : String(htmlText || "");
        if (doctypeMatch) {
            serialized = doctypeMatch[0] + "\n" + serialized;
        }
        return { html: serialized, changed: true, moved_nodes: movedNodes, moved_parents: movedParents };
    }

    var decoMoveResult = _moveDecorativeElementsToEnd(updated);
    if (decoMoveResult && decoMoveResult.changed) {
        updated = String(decoMoveResult.html || updated);
        applied.push(createIssue({
            code: "AUTOFIX.MOVE_DECORATION_TO_END",
            severity: "info",
            message: "自动将装饰层移动到同级末尾，保持扁平化层级正确。",
            evidence: { moved_nodes: decoMoveResult.moved_nodes, moved_parents: decoMoveResult.moved_parents },
            fix: { kind: "autofix", suggestion: "已把 deco-* / data-ui-deco=1 的装饰元素移到同级末尾。" }
        }));
    }

    return {
        fixed_html_text: updated,
        applied_fixes: applied,
    };
}

export function validatePreviewComputedRules(previewDocument) {
    var issues = [];
    var doc = previewDocument;
    if (!doc || !doc.defaultView) {
        return issues;
    }
    var win = doc.defaultView;

    var html = doc.documentElement;
    var body = doc.body;
    // IMPORTANT:
    // 仅检查 computedStyle 的 overflowX/Y 在部分浏览器/布局下会出现假阳性（html 读出来是 visible，但实际不会出现滚动条）。
    // 因此这里改为“是否真的产生滚动条”为准：只要 scrollWidth/Height 超出 clientWidth/Height，就判定失败。
    function _hasScrollbars(el) {
        if (!el) return { x: false, y: false, dx: 0, dy: 0 };
        var cw = Number(el.clientWidth || 0);
        var ch = Number(el.clientHeight || 0);
        var sw = Number(el.scrollWidth || 0);
        var sh = Number(el.scrollHeight || 0);
        var dx = sw - cw;
        var dy = sh - ch;
        // allow 1px rounding jitter
        return { x: dx > 1, y: dy > 1, dx: dx, dy: dy };
    }

    var htmlScroll = _hasScrollbars(html);
    var bodyScroll = _hasScrollbars(body);
    if (htmlScroll.x || htmlScroll.y || bodyScroll.x || bodyScroll.y) {
        issues.push(createIssue({
            code: "PREVIEW.SCROLLBAR_FORBIDDEN",
            severity: "error",
            message: "预览检测：页面出现滚动条（禁止）。",
            evidence: {
                html: { dx: htmlScroll.dx, dy: htmlScroll.dy, client: { w: html ? html.clientWidth : 0, h: html ? html.clientHeight : 0 } },
                body: { dx: bodyScroll.dx, dy: bodyScroll.dy, client: { w: body ? body.clientWidth : 0, h: body ? body.clientHeight : 0 } },
            },
            fix: {
                kind: "autofix",
                suggestion: "优先使用“自动修正并校验”注入禁滚动样式；并检查是否有元素使用 100vh/100vw + 额外 margin/padding 导致超出。",
            },
        }));
    }

    // -----------------------------------------------------------------------------
    // Hard rule: forbid transform scaling on visible text elements.
    // Motivation:
    // - Even if computed font-size is fixed, transform scale changes element rects.
    // - Flattening compensates font-size/line-height by effective scale to avoid overflow,
    //   which would violate the "font-size must not change" requirement.
    // -----------------------------------------------------------------------------
    function _extractScaleFromTransformText(transformText) {
        var raw = String(transformText || "").trim();
        if (!raw || raw === "none") {
            return { sx: 1, sy: 1 };
        }
        var lowered = raw.toLowerCase();

        // scale(a) or scale(a,b) or transform list containing scale(...)
        if (lowered.indexOf("scale(") >= 0) {
            var m = lowered.match(/scale\(\s*([+-]?[0-9.]+)(?:\s*,\s*([+-]?[0-9.]+))?\s*\)/);
            if (m) {
                var sx0 = Number.parseFloat(m[1]);
                var sy0 = (m[2] !== undefined && m[2] !== null && String(m[2]).trim() !== "") ? Number.parseFloat(m[2]) : sx0;
                if (!isFinite(sx0) || sx0 <= 0) sx0 = 1;
                if (!isFinite(sy0) || sy0 <= 0) sy0 = 1;
                return { sx: sx0, sy: sy0 };
            }
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

        if (lowered.indexOf("matrix3d(") === 0 && lowered.endsWith(")")) {
            var inner3d = lowered.slice("matrix3d(".length, -1);
            var nums3d = _parseNumbers(inner3d);
            if (!nums3d || nums3d.length !== 16) {
                return { sx: 1, sy: 1 };
            }
            var m11 = nums3d[0], m12 = nums3d[1], m13 = nums3d[2];
            var m21 = nums3d[4], m22 = nums3d[5], m23 = nums3d[6];
            var sx3 = Math.sqrt(m11 * m11 + m12 * m12 + m13 * m13);
            var sy3 = Math.sqrt(m21 * m21 + m22 * m22 + m23 * m23);
            if (!isFinite(sx3) || sx3 <= 0) sx3 = 1;
            if (!isFinite(sy3) || sy3 <= 0) sy3 = 1;
            return { sx: sx3, sy: sy3 };
        }

        if (lowered.indexOf("matrix(") === 0 && lowered.endsWith(")")) {
            var inner2d = lowered.slice("matrix(".length, -1);
            var nums2d = _parseNumbers(inner2d);
            if (!nums2d || nums2d.length !== 6) {
                return { sx: 1, sy: 1 };
            }
            var a = nums2d[0], b = nums2d[1], c = nums2d[2], d = nums2d[3];
            var sx2 = Math.sqrt(a * a + b * b);
            var sy2 = Math.sqrt(c * c + d * d);
            if (!isFinite(sx2) || sx2 <= 0) sx2 = 1;
            if (!isFinite(sy2) || sy2 <= 0) sy2 = 1;
            return { sx: sx2, sy: sy2 };
        }

        return { sx: 1, sy: 1 };
    }

    var SCALE_TOL = 1e-3;
    var allForScale = doc.body && doc.body.querySelectorAll ? doc.body.querySelectorAll("*") : [];
    for (var si = 0; si < (allForScale ? allForScale.length : 0); si++) {
        var elS = allForScale[si];
        if (!elS || !elS.getBoundingClientRect) continue;
        if (!_shouldConsiderAsTextElement(elS)) continue;
        if (!_isElementVisibleForValidation(win, elS)) continue;
        var stS = win.getComputedStyle(elS);
        if (!stS) continue;
        var t = _safeTrim(stS.transform);
        if (!t || t === "none") continue;
        var sc = _extractScaleFromTransformText(t);
        var sx = Number(sc.sx || 1);
        var sy = Number(sc.sy || 1);
        if (!isFinite(sx) || sx <= 0) sx = 1;
        if (!isFinite(sy) || sy <= 0) sy = 1;
        if (Math.abs(sx - 1) <= SCALE_TOL && Math.abs(sy - 1) <= SCALE_TOL) {
            continue;
        }
        issues.push(createIssue({
            code: "TEXT.TRANSFORM_SCALE_FORBIDDEN",
            severity: "error",
            message: "硬性约束：含文字的元素禁止使用 transform 缩放（scale/matrix scale），否则扁平化会做字号补偿导致导出字号变化。",
            evidence: { element: _describeElementForEvidence(elS), transform: t, scale: { sx: sx, sy: sy } },
            fix: { kind: "manual", suggestion: "删除 scale（含 hover/非 hover）；需要强调请改用 box-shadow/outline/border/颜色对比。" }
        }));
    }

    // -----------------------------------------------------------------------------
    // Forbidden color rule (hard error):
    // - For rect-like visuals (background/border/box-shadow), forbid solid black (#000/#000000/rgb(0,0,0)/rgba(0,0,0,1)).
    // - Motivation: solid black often triggers "shade overlay / quantization / layer" pitfalls in export/writeback,
    //   leading to readability issues (e.g. text covered by a background layer).
    // - Do NOT restrict text color (`color`) here.
    // -----------------------------------------------------------------------------
    function _isForbiddenSolidBlackColorText(colorText) {
        var raw = String(colorText || "").trim().toLowerCase();
        if (!raw) return false;
        if (raw === "transparent") return false;
        if (raw === "black") return true;
        if (raw.indexOf("rgb(") === 0) {
            var m0 = raw.match(/^rgb\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)$/);
            if (!m0) return false;
            var r0 = Math.round(Number(m0[1]));
            var g0 = Math.round(Number(m0[2]));
            var b0 = Math.round(Number(m0[3]));
            if (!isFinite(r0) || !isFinite(g0) || !isFinite(b0)) return false;
            return r0 === 0 && g0 === 0 && b0 === 0;
        }
        if (raw.indexOf("rgba(") === 0) {
            var m1 = raw.match(/^rgba\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)$/);
            if (!m1) return false;
            var r1 = Math.round(Number(m1[1]));
            var g1 = Math.round(Number(m1[2]));
            var b1 = Math.round(Number(m1[3]));
            var a1 = Number(m1[4]);
            if (!isFinite(r1) || !isFinite(g1) || !isFinite(b1) || !isFinite(a1)) return false;
            if (a1 < 0.999) return false;
            return r1 === 0 && g1 === 0 && b1 === 0;
        }
        if (raw[0] === "#") {
            // Normalize to #rrggbbaa if possible; only treat "alpha=ff" as forbidden.
            var hex = raw;
            if (hex.length === 4) {
                // #rgb
                hex = "#" + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3] + "ff";
            } else if (hex.length === 5) {
                // #rgba
                hex = "#" + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3] + hex[4] + hex[4];
            } else if (hex.length === 7) {
                // #rrggbb
                hex = hex + "ff";
            } else if (hex.length !== 9) {
                return false;
            }
            var rr = hex.slice(1, 3);
            var gg = hex.slice(3, 5);
            var bb = hex.slice(5, 7);
            var aa = hex.slice(7, 9);
            return rr === "00" && gg === "00" && bb === "00" && aa === "ff";
        }
        return false;
    }

    function _maybeAddForbiddenSolidBlackIssue(el, st, hitList) {
        if (!hitList || hitList.length <= 0) {
            return;
        }
        var tag = el && el.tagName ? String(el.tagName || "").toLowerCase() : "";
        var id = el && el.id ? String(el.id || "") : "";
        var uiKey = el && el.getAttribute ? String(el.getAttribute("data-ui-key") || "").trim() : "";
        issues.push(createIssue({
            code: "COLOR.FORBIDDEN_SOLID_BLACK",
            severity: "error",
            message: "禁止使用不透明纯黑（#000/#000000/rgb(0,0,0)）作为矩形底色/边框/阴影：会在部分写回链路触发盖色/层级异常（常见表现：文字被底色盖住）。",
            target: { id: id, ui_key: uiKey, tag: tag },
            evidence: {
                element: _describeElementForEvidence(el),
                hits: hitList,
                computed: st ? {
                    backgroundColor: String(st.backgroundColor || ""),
                    borderStyle: String(st.borderStyle || ""),
                    boxShadow: String(st.boxShadow || "")
                } : null
            },
            fix: { kind: "manual", suggestion: "请改用允许的墨色：#0e0e0e73（45%）或 #0e0e0e40（25%）；或使用 rgba(14,14,14,0.45/0.25)。" }
        }));
    }

    // Scan all visible elements once for forbidden solid black (rect-like properties only).
    var allForColor = doc.body && doc.body.querySelectorAll ? doc.body.querySelectorAll("*") : [];
    for (var ci = 0; ci < (allForColor ? allForColor.length : 0); ci++) {
        var elC = allForColor[ci];
        if (!elC) continue;
        if (!_isElementVisibleForValidation(win, elC)) continue;
        var stC = win.getComputedStyle(elC);
        if (!stC) continue;

        var hits = [];

        // background-color
        var bgC = _safeTrim(stC.backgroundColor).toLowerCase();
        if (bgC && bgC !== "transparent" && _isForbiddenSolidBlackColorText(bgC)) {
            hits.push({ property: "backgroundColor", value: bgC });
        }

        // border (only when border is effectively present)
        var borderStyle = _safeTrim(stC.borderStyle).toLowerCase();
        if (borderStyle && borderStyle !== "none") {
            var bwL = _parsePxNumber(stC.borderLeftWidth);
            var bwR = _parsePxNumber(stC.borderRightWidth);
            var bwT = _parsePxNumber(stC.borderTopWidth);
            var bwB = _parsePxNumber(stC.borderBottomWidth);
            if (bwT !== null && bwT > 0) {
                var cTop = _safeTrim(stC.borderTopColor).toLowerCase();
                if (cTop && _isForbiddenSolidBlackColorText(cTop)) hits.push({ property: "borderTopColor", value: cTop });
            }
            if (bwB !== null && bwB > 0) {
                var cBottom = _safeTrim(stC.borderBottomColor).toLowerCase();
                if (cBottom && _isForbiddenSolidBlackColorText(cBottom)) hits.push({ property: "borderBottomColor", value: cBottom });
            }
            if (bwL !== null && bwL > 0) {
                var cLeft = _safeTrim(stC.borderLeftColor).toLowerCase();
                if (cLeft && _isForbiddenSolidBlackColorText(cLeft)) hits.push({ property: "borderLeftColor", value: cLeft });
            }
            if (bwR !== null && bwR > 0) {
                var cRight = _safeTrim(stC.borderRightColor).toLowerCase();
                if (cRight && _isForbiddenSolidBlackColorText(cRight)) hits.push({ property: "borderRightColor", value: cRight });
            }
        }

        // box-shadow (scan any explicit color tokens; only forbid if token is solid black)
        var bsC = _safeTrim(stC.boxShadow).toLowerCase();
        if (bsC && bsC !== "none") {
            var colorTokenRe = /(rgba?\([^)]+\)|#[0-9a-f]{3,8}\b)/gi;
            var tokenMatch;
            var seenTokens = {};
            while ((tokenMatch = colorTokenRe.exec(bsC)) !== null) {
                var tok = String(tokenMatch[1] || "").trim().toLowerCase();
                if (!tok) continue;
                if (seenTokens[tok]) continue;
                seenTokens[tok] = 1;
                if (_isForbiddenSolidBlackColorText(tok)) {
                    hits.push({ property: "boxShadow", value: bsC, forbidden_color: tok });
                }
            }
        }

        _maybeAddForbiddenSolidBlackIssue(elC, stC, hits);
    }

    // -----------------------------------------------------------------------------
    // UI 多状态（data-ui-state-*）规则：
    // - 初始态语义以 data-ui-state-default 为准；不要依赖 visibility/opacity 的“是否隐藏”推断语义。
    // - 同一 group 内最多允许一个 default=1；0 个 default 视为“初始全部隐藏”（允许但会给 warning）。
    // - 禁止在状态节点上使用 display:none（会导致无盒子，扁平化/导出无法定位）。
    // - 禁止“hidden=1px 占位符”这类状态节点：建议改为“单 show 态 + 运行时开关可见性（或无默认态）”，
    //   避免 tiny placeholder 参与几何/容器尺寸推导引发导出与本地预览差异。
    // -----------------------------------------------------------------------------
    function _parseUiStateBool(text) {
        var lowered = String(text || "").trim().toLowerCase();
        if (!lowered) return false;
        return lowered === "1" || lowered === "true" || lowered === "yes" || lowered === "on";
    }

    function _hasAncestorWithSameUiStateGroup(element, groupName) {
        var g = _safeTrim(groupName);
        if (!g) {
            return false;
        }
        if (!element || !element.parentElement) {
            return false;
        }
        var cur = element.parentElement;
        while (cur) {
            if (cur.getAttribute) {
                var g2 = _safeTrim(cur.getAttribute("data-ui-state-group"));
                if (g2 === g) {
                    return true;
                }
            }
            cur = cur.parentElement || null;
        }
        return false;
    }

    function _collectTopLevelStateNodesUnderGroupContainer(groupContainer) {
        // 兼容两种作者写法：
        // A) group+state 在同一节点（老写法/按钮子层常用）：
        //    <div data-ui-state-group="g" data-ui-state="a" data-ui-state-default="1">...</div>
        // B) group 在容器，state 在子节点（overlay/多页常用）：
        //    <section data-ui-state-group="g"><div data-ui-state="a" ...>...</div></section>
        //
        // 这里收集“同组范围内的顶层 state 节点”（避免把 state 节点内部的嵌套 state 重复计入统计）。
        var out = [];
        if (!groupContainer || !groupContainer.querySelectorAll) {
            return out;
        }
        var candidates = [];
        if (groupContainer.getAttribute && _safeTrim(groupContainer.getAttribute("data-ui-state"))) {
            candidates.push(groupContainer);
        }
        var list = groupContainer.querySelectorAll("[data-ui-state]");
        for (var i = 0; i < (list ? list.length : 0); i++) {
            candidates.push(list[i]);
        }

        for (var j = 0; j < candidates.length; j++) {
            var el = candidates[j];
            if (!el || !el.getAttribute) continue;
            if (!(groupContainer.contains && groupContainer.contains(el))) continue;
            var parentState = el.parentElement && el.parentElement.closest ? el.parentElement.closest("[data-ui-state]") : null;
            if (parentState && groupContainer.contains && groupContainer.contains(parentState)) {
                continue;
            }
            out.push(el);
        }
        return out;
    }

    // 注意：某些页面会在 state 节点内部重复写 data-ui-state-group（用于锚定/定位或历史遗留）。
    // 这种“同名 group 的嵌套节点”不应参与 group 的默认态/约束统计，否则会出现：
    // - group 容器本身被误当成 state（缺 stateName）
    // - 子 marker 被误当成 state（导致 defaultCount=0）
    var uiStateGroupMap = {}; // group -> { defaultCount, statesSet, samples: [] }
    var uiGroupContainersForValidation = doc.querySelectorAll ? doc.querySelectorAll("[data-ui-state-group]") : [];
    for (var ui = 0; ui < (uiGroupContainersForValidation ? uiGroupContainersForValidation.length : 0); ui++) {
        var groupContainer = uiGroupContainersForValidation[ui];
        if (!groupContainer || !groupContainer.getAttribute) continue;
        var groupName = _safeTrim(groupContainer.getAttribute("data-ui-state-group"));
        if (!groupName) continue;
        if (_hasAncestorWithSameUiStateGroup(groupContainer, groupName)) {
            continue;
        }

        var stateNodes = _collectTopLevelStateNodesUnderGroupContainer(groupContainer);
        if (!stateNodes || stateNodes.length <= 0) {
            continue;
        }

        for (var si = 0; si < stateNodes.length; si++) {
            var elUi = stateNodes[si];
            if (!elUi || !elUi.getAttribute) continue;
            var stateName = _safeTrim(elUi.getAttribute("data-ui-state"));
            var isDefaultUi = _parseUiStateBool(elUi.getAttribute("data-ui-state-default"));

            if (!uiStateGroupMap[groupName]) {
                uiStateGroupMap[groupName] = { defaultCount: 0, statesSet: {}, samples: [] };
            }
            if (stateName) {
                uiStateGroupMap[groupName].statesSet[stateName] = 1;
            }
            if (isDefaultUi) {
                uiStateGroupMap[groupName].defaultCount += 1;
            }
            if (uiStateGroupMap[groupName].samples.length < 6) {
                uiStateGroupMap[groupName].samples.push({
                    state: stateName,
                    isDefault: !!isDefaultUi,
                    element: _describeElementForEvidence(elUi),
                });
            }

            if (!stateName) {
                issues.push(createIssue({
                    code: "UI_STATE.MISSING_STATE_NAME",
                    severity: "error",
                    message: "多状态节点缺少 data-ui-state（状态名不能为空）。",
                    evidence: { group: groupName, element: _describeElementForEvidence(elUi) },
                    fix: { kind: "manual", suggestion: "为该节点补齐 data-ui-state=\"<状态名>\"（建议用稳定枚举名，如 normal/selected/disabled 或 level_01 等）。" },
                }));
            }

            var stUi = win.getComputedStyle(elUi);
            if (stUi) {
                var disp = _safeTrim(stUi.display).toLowerCase();
                if (disp === "none") {
                    issues.push(createIssue({
                        code: "UI_STATE.DISPLAY_NONE_FORBIDDEN",
                        severity: "error",
                        message: "多状态节点禁止使用 display:none（会导致元素没有盒子，无法扁平化/导出/定位）。",
                        evidence: { group: groupName, state: stateName, element: _describeElementForEvidence(elUi), display: disp },
                        fix: { kind: "manual", suggestion: "改用 visibility:hidden 或 opacity:0 + pointer-events:none；初始态语义请用 data-ui-state-default 表达。" },
                    }));
                } else {
                    // 仅提示：非默认态若仍可见，源码预览会“全摊开”；建议隐藏以贴近初始态，但不是强制。
                    if (!isDefaultUi && _isElementVisibleForValidation(win, elUi)) {
                        issues.push(createIssue({
                            code: "UI_STATE.NON_DEFAULT_VISIBLE_SUGGEST_HIDE",
                            severity: "info",
                            message: "非默认态在源码预览中仍为可见：建议隐藏以贴近“初始态”，但不影响导出语义。",
                            evidence: { group: groupName, state: stateName, element: _describeElementForEvidence(elUi) },
                            fix: { kind: "manual", suggestion: "建议给非默认态加 visibility:hidden（或 opacity:0 + pointer-events:none）。初始态仍以 data-ui-state-default 为准。" },
                        }));
                    }
                }
            }
        }
    }

    var groupKeys = Object.keys(uiStateGroupMap).sort(function (a, b) { return a.localeCompare(b); });
    for (var gi = 0; gi < groupKeys.length; gi++) {
        var gk = groupKeys[gi];
        var entry = uiStateGroupMap[gk];
        var defaultCount = entry ? Number(entry.defaultCount || 0) : 0;
        if (!isFinite(defaultCount)) defaultCount = 0;
        if (defaultCount > 1) {
            issues.push(createIssue({
                code: "UI_STATE.MULTIPLE_DEFAULT_FORBIDDEN",
                severity: "error",
                message: "同一 data-ui-state-group 内最多只能有一个默认态（data-ui-state-default=\"1\"）。",
                evidence: { group: gk, default_count: defaultCount, samples: entry ? entry.samples : null },
                fix: { kind: "manual", suggestion: "只保留一个 default=1；其余改为 default=0/移除该属性。" },
            }));
        } else if (defaultCount === 0) {
            issues.push(createIssue({
                code: "UI_STATE.NO_DEFAULT_WARN",
                severity: "warning",
                message: "该 data-ui-state-group 没有默认态（初始会全部隐藏）。",
                evidence: { group: gk, samples: entry ? entry.samples : null },
                fix: { kind: "manual", suggestion: "若需要初始显示某个状态，为其中一个状态节点加 data-ui-state-default=\"1\"；若确实希望初始全隐藏，可忽略该提示。" },
            }));
        }
    }

    // -----------------------------------------------------------------------------
    // UI 多状态（补充规则）：禁止 tiny hidden placeholder
    //
    // 典型“坏味道”：
    //   <div data-ui-state-group="g" data-ui-state="hidden" data-ui-state-default="1" style="width:1px;height:1px"></div>
    //
    // 这类写法的动机通常是“默认隐藏但要保留节点”，但它会引入：
    // - 容器尺寸被 1px 默认态影响（尤其当作者使用 inset:0 / fill-parent 类布局时）；
    // - 扁平化/导出在抽取“非默认态几何”时更容易出现被压扁/裁剪的差异。
    //
    // 更推荐的表达：
    // - 仅保留 show 态节点；
    // - 初始不写 data-ui-state-default（=初始全隐藏），需要显示时由运行时/节点图把 show 设为 default。
    // -----------------------------------------------------------------------------
    function _collectStateNodesUnderGroupContainer(groupContainer) {
        var out = [];
        if (!groupContainer || !groupContainer.getAttribute) {
            return out;
        }
        // Pattern A: group+state 在同一节点
        if (_safeTrim(groupContainer.getAttribute("data-ui-state"))) {
            out.push(groupContainer);
        }
        // Pattern B: group 在容器，state 在直接子节点
        var children = groupContainer.children || [];
        for (var i = 0; i < children.length; i++) {
            var c = children[i];
            if (!c || !c.getAttribute) continue;
            if (_safeTrim(c.getAttribute("data-ui-state"))) {
                out.push(c);
            }
        }
        return out;
    }

    var uiGroupContainers = doc.querySelectorAll ? doc.querySelectorAll("[data-ui-state-group]") : [];
    for (var ui2 = 0; ui2 < (uiGroupContainers ? uiGroupContainers.length : 0); ui2++) {
        var gEl = uiGroupContainers[ui2];
        if (!gEl || !gEl.getAttribute) continue;
        var gName2 = _safeTrim(gEl.getAttribute("data-ui-state-group"));
        if (!gName2) continue;

        var stateNodes = _collectStateNodesUnderGroupContainer(gEl);
        if (!stateNodes || stateNodes.length <= 0) continue;

        // 需要至少“两个不同 state”，才有“hidden vs show”的语义对照；否则不报，避免误伤。
        var stateKeySet = {};
        for (var si = 0; si < stateNodes.length; si++) {
            var n0 = stateNodes[si];
            var sn = _safeTrim(n0.getAttribute ? n0.getAttribute("data-ui-state") : "");
            if (sn) stateKeySet[sn] = 1;
        }
        var distinctStates = Object.keys(stateKeySet);
        if (!distinctStates || distinctStates.length < 2) continue;

        for (var sj = 0; sj < stateNodes.length; sj++) {
            var stEl = stateNodes[sj];
            if (!stEl || !stEl.getAttribute || !stEl.getBoundingClientRect) continue;
            var stName = _safeTrim(stEl.getAttribute("data-ui-state"));
            if (stName !== "hidden") continue;

            // 仅针对“空占位符”类型（无子节点、无文本），避免误伤真正的“隐藏页/遮罩”。
            var hasChild = !!(stEl.children && stEl.children.length > 0);
            var hasText = !!_safeTrim(stEl.textContent || "");
            if (hasChild || hasText) continue;

            var r0 = stEl.getBoundingClientRect();
            var w0 = Number(r0 && r0.width !== undefined ? r0.width : 0);
            var h0 = Number(r0 && r0.height !== undefined ? r0.height : 0);
            if (!isFinite(w0)) w0 = 0;
            if (!isFinite(h0)) h0 = 0;

            // tiny 阈值：<=2px 认为是“占位符”而非真实页面/弹窗态
            if (w0 <= 2 && h0 <= 2) {
                issues.push(createIssue({
                    code: "UI_STATE.HIDDEN_TINY_PLACEHOLDER_FORBIDDEN",
                    severity: "error",
                    message: "禁止使用 tiny 的 hidden 占位状态（例如 1px placeholder）。请改用“单 show 态 + 运行时开关可见性（或无默认态=初始全隐藏）”。",
                    evidence: { group: gName2, state: stName, element: _describeElementForEvidence(stEl), rect: { w: w0, h: h0 } },
                    fix: {
                        kind: "manual",
                        suggestion:
                            "建议：删除该 hidden 占位节点；仅保留 show 节点。\n" +
                            "- 初始隐藏：不要写 data-ui-state-default=\"1\"（让组初始全隐藏）\n" +
                            "- 需要显示：运行时把 show 节点设为 default（或通过状态组切换使 show 成为默认态）",
                    },
                }));
            }
        }
    }

    // game-cutout rules (minimal but useful)
    var cutouts = doc.querySelectorAll ? doc.querySelectorAll("." + GAME_CUTOUT_CLASS) : [];
    var rects = [];
    for (var i = 0; i < (cutouts ? cutouts.length : 0); i++) {
        var el = cutouts[i];
        if (!el || !el.getBoundingClientRect) continue;
        var r = el.getBoundingClientRect();
        rects.push({ rect: { left: r.left, top: r.top, width: r.width, height: r.height } });

        var w = Number(r.width || 0);
        var h = Number(r.height || 0);
        var allowNonSquareAttr = _safeTrim(el.getAttribute ? (el.getAttribute("data-game-cutout-allow-non-square") || "") : "");
        var allowNonSquare =
            allowNonSquareAttr === "1" ||
            allowNonSquareAttr.toLowerCase() === "true" ||
            allowNonSquareAttr.toLowerCase() === "yes" ||
            allowNonSquareAttr.toLowerCase() === "on" ||
            !!_safeTrim(el.getAttribute ? (el.getAttribute(String(GAME_CUTOUT_NAME_ATTR || "data-game-area")) || "") : "");

        // 语义调整：`.game-cutout` 只要存在就应作为矩形挖空参与扁平化裁切；
        // 因此不再强制要求近似正方形，也不再要求显式放行矩形。

        var st3 = win.getComputedStyle(el);
        var bg = _safeTrim(st3.backgroundColor).toLowerCase();
        // 语义调整：cutout 作为“挖空标记”，不再强制要求本身视觉为透明。
        var bs = _safeTrim(st3.boxShadow);
        // 语义调整：不再阻断 box-shadow/border；保留 overlap 检查防止“裁空一切”类误用。
        var br = _safeTrim(st3.borderStyle).toLowerCase();
        // 语义调整：不再阻断 box-shadow/border；保留 overlap 检查防止“裁空一切”类误用。
    }
    for (var a = 0; a < rects.length; a++) {
        for (var b = a + 1; b < rects.length; b++) {
            if (_rectIntersects(rects[a].rect, rects[b].rect)) {
                issues.push(createIssue({
                    code: "CUTOUT.OVERLAP_FORBIDDEN",
                    severity: "error",
                    message: ".game-cutout 之间禁止重叠。",
                    fix: { kind: "manual", suggestion: "调整 cutout 的位置/大小，保证互不重叠。" }
                }));
                a = rects.length;
                break;
            }
        }
    }

    // -----------------------------------------------------------------------------
    // highlight-display-area rules (Dim Surroundings / 高亮展示区域)
    // -----------------------------------------------------------------------------
    // 语义：该元素本体不参与扁平化输出；扁平化阶段会把它转换成 4 个“压暗遮罩矩形”，
    // 用“周围变暗”实现“展示区域高亮”。
    var highlightAreas = doc.querySelectorAll ? doc.querySelectorAll("." + String(HIGHLIGHT_DISPLAY_AREA_CLASS || "highlight-display-area")) : [];
    if (highlightAreas && highlightAreas.length > 1) {
        // 允许“多步高亮”（每个 state 一个 marker），但要求 marker 显式绑定同一 state-group 且 state 不重复：
        // - 例如 tutorial overlay：guide_1~guide_N
        // - dom_extract 会按 group/state 查找 tutorial-marker 用于卡片锚定
        var allowMultiByState = true;
        var gName = "";
        var stateKeySet = {};
        for (var hh = 0; hh < highlightAreas.length; hh++) {
            var hEl = highlightAreas[hh];
            if (!hEl || !hEl.getAttribute) {
                allowMultiByState = false;
                break;
            }
            var gg = _safeTrim(hEl.getAttribute("data-ui-state-group"));
            var ss = _safeTrim(hEl.getAttribute("data-ui-state"));
            if (!gg || !ss) {
                allowMultiByState = false;
                break;
            }
            if (!gName) {
                gName = gg;
            }
            if (gg !== gName) {
                allowMultiByState = false;
                break;
            }
            if (stateKeySet[ss]) {
                allowMultiByState = false;
                break;
            }
            stateKeySet[ss] = 1;
        }
        if (!allowMultiByState) {
            issues.push(createIssue({
                code: "HIGHLIGHT_AREA.MULTIPLE_FORBIDDEN",
                severity: "error",
                message: "同一页面最多只能有一个 .highlight-display-area（高亮展示区域）。",
                fix: { kind: "manual", suggestion: "只保留一个高亮展示区域；若需要多步高亮，请将 marker 放到同一 data-ui-state-group 下，并确保每个 state 至多一个 marker（常见：guide_1/guide_2/...）。" }
            }));
        }
    }
    for (var hi = 0; hi < (highlightAreas ? highlightAreas.length : 0); hi++) {
        var elh = highlightAreas[hi];
        if (!elh || !elh.getBoundingClientRect) continue;
        var rh = elh.getBoundingClientRect();
        var hw = Number(rh.width || 0);
        var hh = Number(rh.height || 0);
        if (!isFinite(hw) || !isFinite(hh) || hw <= 1 || hh <= 1) {
            issues.push(createIssue({
                code: "HIGHLIGHT_AREA.ZERO_SIZE_FORBIDDEN",
                severity: "error",
                message: ".highlight-display-area 的尺寸必须 > 0（否则无法生成包围遮罩）。",
                fix: { kind: "manual", suggestion: "为该元素设置明确的 left/top/width/height（通常 position:absolute）。" }
            }));
        }
        var rawAlpha = _safeTrim(elh.getAttribute ? (elh.getAttribute(String(HIGHLIGHT_OVERLAY_ALPHA_ATTR || "data-highlight-overlay-alpha")) || "") : "");
        if (rawAlpha) {
            var alphaLower = rawAlpha.toLowerCase();
            var ok =
                alphaLower === "0.45" || alphaLower === ".45" || alphaLower === "45" || alphaLower === "dark" ||
                alphaLower === "0.25" || alphaLower === ".25" || alphaLower === "25" || alphaLower === "light";
            if (!ok) {
                issues.push(createIssue({
                    code: "HIGHLIGHT_AREA.ALPHA_UNSUPPORTED",
                    severity: "warning",
                    message: "data-highlight-overlay-alpha 只支持 0.45 或 0.25（其它值会被吸附为默认 0.45）。",
                    evidence: { value: rawAlpha },
                    fix: { kind: "manual", suggestion: "改为 data-highlight-overlay-alpha=\"0.45\"（更暗）或 \"0.25\"（更浅）。" }
                }));
            }
        }
        var text0 = _safeTrim(elh.textContent || "");
        if (text0) {
            issues.push(createIssue({
                code: "HIGHLIGHT_AREA.TEXT_IGNORED",
                severity: "info",
                message: ".highlight-display-area 仅作为标记使用，其文本/样式不会出现在扁平化输出中。",
                evidence: { text: text0.slice(0, 50) },
                fix: { kind: "manual", suggestion: "建议保持该元素为空（只负责提供展示区域的 rect）。" }
            }));
        }
    }

    // -----------------------------------------------------------------------------
    // Text alignment heuristics:
    // Problem: programmers often miss "should be right-aligned" for labels close to a right border.
    //
    // Rules:
    // - If element has data-ui-align="right": enforce text-align is right/end (error).
    // - Else: if a leaf text element is close to its nearest border-container's right edge but text-align is left/start,
    //   emit a warning suggesting right alignment.
    // - Opt-out: data-ui-align-ok="1" disables this check for that element.
    // -----------------------------------------------------------------------------
    // Note: "should be right aligned" is a UX-intent check; we prefer catching more cases (warn-only),
    // but keep it scoped to short labels to reduce false positives.
    var RIGHT_EDGE_NEAR_PX = 80;
    var allEls = doc.body && doc.body.querySelectorAll ? doc.body.querySelectorAll("*") : [];
    for (var ti = 0; ti < (allEls ? allEls.length : 0); ti++) {
        var el2 = allEls[ti];
        if (!el2 || !el2.getBoundingClientRect) continue;
        if (!_shouldConsiderAsTextElement(el2)) continue;
        if (!_isElementVisibleForValidation(win, el2)) continue;

        if (el2.getAttribute && String(el2.getAttribute("data-ui-align-ok") || "").trim() === "1") {
            continue;
        }

        var stTxt = win.getComputedStyle(el2);
        if (!stTxt) continue;
        var textAlign = _safeTrim(stTxt.textAlign).toLowerCase();
        // Browser computed can return "start"; treat as left for our purpose.
        var isLeftish = (textAlign === "left" || textAlign === "start" || textAlign === "");
        var isRightish = (textAlign === "right" || textAlign === "end");

        var expectedAlign = el2.getAttribute ? String(el2.getAttribute("data-ui-align") || "").trim().toLowerCase() : "";
        if (expectedAlign === "right") {
            if (!isRightish) {
                issues.push(createIssue({
                    code: "TEXT.ALIGNMENT_EXPECT_RIGHT",
                    severity: "error",
                    message: "该文本声明了 data-ui-align=\"right\"，但 computed text-align 不是 right/end。",
                    target: { kind: "element", tag: String(el2.tagName || "").toLowerCase(), text: _safeTrim(el2.textContent || "") },
                    evidence: { text_align: textAlign },
                    fix: { kind: "manual", suggestion: "为该元素设置 text-align: right;（或在容器上使用 flex-end 并确保该元素占据可对齐的宽度）。" }
                }));
            }
            continue;
        }

        if (!isLeftish) {
            continue;
        }
        var elRect = _rectFromDomRect(el2.getBoundingClientRect());
        if (!elRect) continue;
        var containerRect = _pickNearestBorderContainerRect(win, el2);
        if (!containerRect) continue;

        // Close to right edge: element's right side is near container right border,
        // and the element itself lives in the right half of container (reduce false positives).
        var distToRight = Number(containerRect.right - elRect.right);
        if (!isFinite(distToRight)) continue;
        if (distToRight < 0) continue;
        if (distToRight > RIGHT_EDGE_NEAR_PX) continue;
        // Reduce false positives: "full-width" text blocks naturally have a right edge close to container.
        // We only want small labels near the corner.
        var containerW = Number(containerRect.width || 0);
        var elW = Number(elRect.width || 0);
        if (isFinite(containerW) && containerW > 1 && isFinite(elW) && elW > 0) {
            if (elW / containerW > 0.75) {
                continue;
            }
        }
        var elCenterX = Number((elRect.left + elRect.right) * 0.5);
        var containerMidX = Number((containerRect.left + containerRect.right) * 0.5);
        if (!isFinite(elCenterX) || !isFinite(containerMidX)) continue;
        if (elCenterX < containerMidX) continue;

        // Additional heuristics: prefer short labels (common for headers / corner hints).
        var rawText = _safeTrim(el2.textContent || "");
        if (rawText.length > 20) {
            continue;
        }
        if (elRect.width > 260) {
            continue;
        }

        issues.push(createIssue({
            code: "TEXT.ALIGNMENT_SUGGEST_RIGHT",
            severity: "warning",
            message: "文本靠近右边框但仍为左对齐（text=" + rawText + "）：建议改为右对齐以贴合边界（减少人工遗漏）。",
            target: { kind: "element", tag: String(el2.tagName || "").toLowerCase(), text: rawText },
            evidence: {
                text_align: textAlign,
                element_rect: elRect,
                container_rect: containerRect,
                dist_to_container_right: distToRight,
            },
            fix: { kind: "manual", suggestion: "给该元素加 text-align:right; 或加 data-ui-align=\"right\" 并配合 CSS 落地。若确实不需要，设置 data-ui-align-ok=\"1\" 忽略该条。"}
        }));
    }

    // -----------------------------------------------------------------------------
    // Decorative layers must be placed after normal content within the same parent.
    // Reason: flattening uses DOM order for z stacking, ignoring CSS z-index.
    // -----------------------------------------------------------------------------
    var decoParents = new Set();
    var allEls3 = doc.body && doc.body.querySelectorAll ? doc.body.querySelectorAll("*") : [];
    for (var di = 0; di < (allEls3 ? allEls3.length : 0); di++) {
        var el3 = allEls3[di];
        if (!el3 || !el3.parentElement) continue;
        if (!_isElementVisibleForValidation(win, el3)) continue;
        if (!_isDecorativeElementForOrdering(el3, win)) continue;
        decoParents.add(el3.parentElement);
    }
    decoParents.forEach(function (parent) {
        if (!parent || !parent.children || parent.children.length <= 1) {
            return;
        }
        var children = parent.children || [];
        var seenDeco = false;
        var firstDeco = null;
        var afterNonDeco = null;
        for (var ci = 0; ci < children.length; ci++) {
            var child = children[ci];
            if (!_isElementVisibleForValidation(win, child)) {
                continue;
            }
            if (_isDecorativeElementForOrdering(child, win)) {
                if (!seenDeco) {
                    firstDeco = child;
                }
                seenDeco = true;
                continue;
            }
            if (seenDeco) {
                afterNonDeco = child;
                break;
            }
        }
        if (!afterNonDeco) {
            return;
        }
        issues.push(createIssue({
            code: "CSS.DECO_LAYER_NOT_LAST",
            severity: "error",
            message: "装饰层必须后置：装饰元素在同级非装饰元素之前，扁平化会导致层级反转。",
            target: { kind: "element", tag: String(parent.tagName || "").toLowerCase(), id: String(parent.id || "") },
            evidence: {
                deco: _describeElementForEvidence(firstDeco),
                after: _describeElementForEvidence(afterNonDeco)
            },
            fix: { kind: "manual", suggestion: "把装饰元素移动到同级末尾（或单独放在装饰层容器的最后）。" }
        }));
    });

    // -----------------------------------------------------------------------------
    // Mixed text nodes inside flex/grid containers are forbidden:
    // flex/grid containers that have element children + direct text nodes will
    // shift text positions after flattening (anonymous flex items are not tracked).
    // -----------------------------------------------------------------------------
    var allEls2 = doc.body && doc.body.querySelectorAll ? doc.body.querySelectorAll("*") : [];
    for (var mi = 0; mi < (allEls2 ? allEls2.length : 0); mi++) {
        var el3 = allEls2[mi];
        if (!el3 || !el3.getBoundingClientRect) continue;
        if (!_isElementVisibleForValidation(win, el3)) continue;
        if (!_hasElementChildren(el3)) continue;
        if (!_hasDirectNonWhitespaceTextNode(el3)) continue;
        var stMix = win.getComputedStyle(el3);
        if (!stMix) continue;
        var displayMix = _safeTrim(stMix.display).toLowerCase();
        if (displayMix.indexOf("flex") < 0 && displayMix.indexOf("grid") < 0) {
            continue;
        }
        var textSnippet = _safeTrim(el3.textContent || "");
        if (textSnippet.length > 30) {
            textSnippet = textSnippet.slice(0, 30) + "...";
        }
        issues.push(createIssue({
            code: "CSS.MIXED_TEXT_NODE_IN_FLEX_CONTAINER",
            severity: "error",
            message: "禁止在 flex/grid 容器内直接书写文本节点并混排子元素：扁平化会导致文本漂移。",
            target: { kind: "element", tag: String(el3.tagName || "").toLowerCase(), text: textSnippet },
            evidence: { display: displayMix },
            fix: { kind: "manual", suggestion: "把文本包进 <span>（例如 <span class=\"panel-title-text\">文本</span>），避免匿名 flex item 产生偏移。" }
        }));
    }

    return issues;
}

export async function validateTextFontSizeUniformAcrossCanvasSizes(preview, canvasSizeCatalog, waitForNextFrame) {
    // Hard requirement:
    // For any visible text element, its computed font-size must NOT change across canvas sizes.
    //
    // Motivation:
    // - Prevent vw/vh/clamp()/media-query driven font scaling.
    // - Ensure text metrics are stable for export/writeback and for "what you see is what you get".
    var issues = [];
    var catalog = Array.isArray(canvasSizeCatalog) ? canvasSizeCatalog : [];
    if (!preview || typeof preview.getComputePreviewDocument !== "function") {
        return issues;
    }
    if (!catalog || catalog.length <= 0) {
        return issues;
    }

    var computeDoc = preview.getComputePreviewDocument();
    if (!computeDoc || !computeDoc.defaultView || !computeDoc.body || !computeDoc.body.querySelectorAll) {
        return issues;
    }
    var win = computeDoc.defaultView;

    // Snapshot candidate text-owning elements once (DOM stays the same; we only change canvas vars).
    var all = computeDoc.body.querySelectorAll("*");
    var candidates = [];
    for (var i = 0; i < (all ? all.length : 0); i++) {
        var el = all[i];
        if (!el) continue;
        if (!_shouldConsiderAsTextElement(el)) continue;
        candidates.push(el);
    }
    if (candidates.length <= 0) {
        return issues;
    }

    function _findCanvasSizeOptionByKey(key) {
        var k = String(key || "").trim();
        if (!k) return null;
        for (var ci = 0; ci < catalog.length; ci++) {
            var it = catalog[ci];
            if (it && String(it.key || "") === k) {
                return it;
            }
        }
        return null;
    }

    var originalCanvasSizeKey = (typeof preview.getCurrentSelectedCanvasSizeKey === "function")
        ? String(preview.getCurrentSelectedCanvasSizeKey() || "")
        : "";
    var originalCanvasSizeOption = _findCanvasSizeOptionByKey(originalCanvasSizeKey) || (catalog.length > 0 ? catalog[0] : null);

    var fontSizeByCandidateIndexBySizeKey = {}; // sizeKey -> { indexText -> fontSizePxNumber }
    var evidenceByCandidateIndex = {}; // indexText -> { element, text }
    for (var si = 0; si < catalog.length; si++) {
        var canvasSizeOption = catalog[si];
        if (!canvasSizeOption || !canvasSizeOption.key) {
            continue;
        }
        if (typeof preview.setComputePreviewCanvasSize === "function") {
            preview.setComputePreviewCanvasSize(canvasSizeOption);
        }
        if (typeof preview.applyCanvasSizeToPreviewDocument === "function") {
            preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
        }
        if (typeof waitForNextFrame === "function") {
            await waitForNextFrame();
            await waitForNextFrame();
        }

        var perSize = {};
        for (var ei = 0; ei < candidates.length; ei++) {
            var el2 = candidates[ei];
            if (!el2) continue;
            var indexText = String(ei);
            if (!evidenceByCandidateIndex[indexText]) {
                evidenceByCandidateIndex[indexText] = {
                    element: _describeElementForEvidence(el2),
                    text: _safeTrim(el2.textContent || "").slice(0, 80),
                };
            }

            if (!_isElementVisibleForValidation(win, el2)) {
                continue;
            }
            var st = win.getComputedStyle(el2);
            if (!st) {
                continue;
            }
            var fontSizeText = _safeTrim(st.fontSize);
            if (!fontSizeText) {
                continue;
            }
            var px = _parsePxNumber(fontSizeText);
            if (px === null || !isFinite(px) || px <= 0) {
                continue;
            }
            perSize[indexText] = px;
        }
        fontSizeByCandidateIndexBySizeKey[String(canvasSizeOption.key)] = perSize;
    }

    // Restore compute iframe size to avoid surprising later steps.
    if (originalCanvasSizeOption) {
        if (typeof preview.setComputePreviewCanvasSize === "function") {
            preview.setComputePreviewCanvasSize(originalCanvasSizeOption);
        }
        if (typeof preview.applyCanvasSizeToPreviewDocument === "function") {
            preview.applyCanvasSizeToPreviewDocument(computeDoc, originalCanvasSizeOption);
        }
        if (typeof waitForNextFrame === "function") {
            await waitForNextFrame();
        }
    }

    var TOLERANCE_PX = 0.01;
    for (var candidateIndex = 0; candidateIndex < candidates.length; candidateIndex++) {
        var idxText = String(candidateIndex);
        var values = [];
        var bySizeKey = {};
        for (var sk = 0; sk < catalog.length; sk++) {
            var opt = catalog[sk];
            if (!opt || !opt.key) continue;
            var sizeKey = String(opt.key);
            var perSizeMap = fontSizeByCandidateIndexBySizeKey[sizeKey] || {};
            var v = perSizeMap[idxText];
            if (v === undefined) {
                continue;
            }
            var n = Number(v);
            if (!isFinite(n) || n <= 0) {
                continue;
            }
            values.push(n);
            bySizeKey[sizeKey] = n;
        }
        if (values.length <= 1) {
            continue;
        }
        var minV = values[0];
        var maxV = values[0];
        for (var vi = 1; vi < values.length; vi++) {
            var vv = values[vi];
            if (vv < minV) minV = vv;
            if (vv > maxV) maxV = vv;
        }
        if (Math.abs(maxV - minV) <= TOLERANCE_PX) {
            continue;
        }

        var ev = evidenceByCandidateIndex[idxText] || null;
        issues.push(createIssue({
            code: "TEXT.FONT_SIZE_CHANGES_WITH_CANVAS_SIZE",
            severity: "error",
            message: "硬性约束：文字字号禁止随画布尺寸变化（任何分辨率下 font-size 必须恒定）。",
            target: { kind: "text", index: candidateIndex },
            evidence: {
                element: ev ? ev.element : null,
                text: ev ? ev.text : "",
                font_size_by_size_key_px: bySizeKey,
            },
            fix: {
                kind: "manual",
                suggestion:
                    "请把字号改为固定 px，并避免在字号中使用 vw/vh/vmin/vmax/%/em/rem/calc()/clamp()/min()/max() 或基于 data-size-mode 的字号分支。",
            }
        }));
    }

    return issues;
}

