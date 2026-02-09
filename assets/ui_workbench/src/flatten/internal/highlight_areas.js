import { HIGHLIGHT_DISPLAY_AREA_CLASS, PALETTE_SHADE_OVERLAY_RGBA, PALETTE_SHADE_OVERLAY_RGBA_25 } from "../../config.js";

function _normalizeClassToken(token) {
    return String(token || "").trim();
}

function _splitClassTokens(classNameText) {
    var raw = String(classNameText || "");
    if (!raw) {
        return [];
    }
    return raw.split(/\s+/).map(_normalizeClassToken).filter(function (t) { return !!t; });
}

function _elementInfoHasClass(elementInfo, classToken) {
    var token = _normalizeClassToken(classToken);
    if (!token) {
        return false;
    }
    var classNameText = elementInfo && elementInfo.className ? String(elementInfo.className) : "";
    var tokens = _splitClassTokens(classNameText);
    for (var i = 0; i < tokens.length; i++) {
        if (tokens[i] === token) {
            return true;
        }
    }
    return false;
}

function _parseHighlightOverlayAlphaFromElementInfo(elementInfo) {
    // 约定：
    // - data-highlight-overlay-alpha="0.45|0.25"（不填默认 0.45）
    var attrs = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
    var raw = attrs ? String(attrs.dataHighlightOverlayAlpha || "").trim().toLowerCase() : "";
    if (!raw) {
        return 0.45;
    }
    if (raw === "0.25" || raw === ".25" || raw === "25" || raw === "light") {
        return 0.25;
    }
    if (raw === "0.45" || raw === ".45" || raw === "45" || raw === "dark") {
        return 0.45;
    }
    var n = Number(raw);
    if (isFinite(n) && Math.abs(n - 0.25) <= 0.03) {
        return 0.25;
    }
    return 0.45;
}

export function isHighlightDisplayAreaElementInfo(elementInfo) {
    return _elementInfoHasClass(elementInfo, HIGHLIGHT_DISPLAY_AREA_CLASS);
}

export function collectHighlightDisplayAreaInfos(elements) {
    var out = [];
    for (var i = 0; i < (elements ? elements.length : 0); i++) {
        var elementInfo = elements[i];
        if (!isHighlightDisplayAreaElementInfo(elementInfo)) {
            continue;
        }
        var rect = elementInfo && elementInfo.rect ? elementInfo.rect : null;
        if (!rect) {
            continue;
        }
        var w = Number(rect.width || 0);
        var h = Number(rect.height || 0);
        if (!isFinite(w) || !isFinite(h) || w <= 0.001 || h <= 0.001) {
            continue;
        }
        out.push({
            rect: {
                left: Number(rect.left || 0),
                top: Number(rect.top || 0),
                width: w,
                height: h
            },
            sourceElementIndex: i,
            overlayAlpha: _parseHighlightOverlayAlphaFromElementInfo(elementInfo),
        });
    }
    return out;
}

export function normalizeHighlightOverlayColorFromAlpha(alpha) {
    var a = Number(alpha);
    if (!isFinite(a)) {
        a = 0.45;
    }
    if (Math.abs(a - 0.25) <= 0.03) {
        return PALETTE_SHADE_OVERLAY_RGBA_25;
    }
    return PALETTE_SHADE_OVERLAY_RGBA;
}

export function buildDimSurroundingRectsForHighlightArea(highlightRect, canvasSize) {
    // 将 “整张画布” 减去 highlightRect 的区域表达为 4 个矩形（上/下/左/右）。
    var cw = canvasSize ? Number(canvasSize.width || 0) : 0;
    var ch = canvasSize ? Number(canvasSize.height || 0) : 0;
    if (!isFinite(cw) || cw <= 0.001 || !isFinite(ch) || ch <= 0.001) {
        return [];
    }
    if (!highlightRect) {
        return [];
    }
    var left = Number(highlightRect.left || 0);
    var top = Number(highlightRect.top || 0);
    var width = Number(highlightRect.width || 0);
    var height = Number(highlightRect.height || 0);
    if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height) || width <= 0.001 || height <= 0.001) {
        return [];
    }
    var right = left + width;
    var bottom = top + height;

    // clamp 到画布范围内（避免作者写出边界外值导致负尺寸）
    var x0 = Math.max(0, Math.min(cw, left));
    var x1 = Math.max(0, Math.min(cw, right));
    var y0 = Math.max(0, Math.min(ch, top));
    var y1 = Math.max(0, Math.min(ch, bottom));
    if (x1 - x0 <= 0.001 || y1 - y0 <= 0.001) {
        return [];
    }

    var rects = [];
    // top
    if (y0 > 0.001) {
        rects.push({ left: 0, top: 0, width: cw, height: y0 });
    }
    // bottom
    if (ch - y1 > 0.001) {
        rects.push({ left: 0, top: y1, width: cw, height: ch - y1 });
    }
    // left
    if (x0 > 0.001) {
        rects.push({ left: 0, top: y0, width: x0, height: y1 - y0 });
    }
    // right
    if (cw - x1 > 0.001) {
        rects.push({ left: x1, top: y0, width: cw - x1, height: y1 - y0 });
    }
    return rects;
}

