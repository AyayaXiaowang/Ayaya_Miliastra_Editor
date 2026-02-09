var ALLOWED_GAME_FONT_SIZES = [
    10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36,
    48, 72, 96, 128, 256, 512
];
var _allowedGameFontSizeSet = new Set(ALLOWED_GAME_FONT_SIZES.map(function (x) { return Number(x); }));

function _parsePxNumber(text) {
    var trimmed = String(text || "").trim().toLowerCase();
    if (!trimmed) {
        return null;
    }
    if (trimmed.endsWith("px")) {
        trimmed = trimmed.slice(0, -2).trim();
    }
    var numberValue = Number.parseFloat(trimmed);
    if (!isFinite(numberValue)) {
        return null;
    }
    return numberValue;
}

function _pickNearestAllowedGameFontSize(sizeInt) {
    var raw = Number(sizeInt);
    if (!isFinite(raw) || raw <= 0) {
        return 16;
    }
    var best = ALLOWED_GAME_FONT_SIZES[0];
    var bestDiff = Math.abs(raw - best);
    for (var i = 1; i < ALLOWED_GAME_FONT_SIZES.length; i++) {
        var cand = ALLOWED_GAME_FONT_SIZES[i];
        var diff = Math.abs(raw - cand);
        if (diff < bestDiff) {
            best = cand;
            bestDiff = diff;
        }
    }
    return best;
}

export function normalizeFontSizeForFlatText(fontSizeText) {
    var opts = arguments.length >= 2 ? (arguments[1] || {}) : {};
    var diagnostics = opts.diagnostics || null;
    var target = opts.target || null;
    var context = String(opts.context || "").trim();

    var raw = String(fontSizeText || "").trim();
    if (!raw) {
        return "16px";
    }
    var px = _parsePxNumber(raw);
    if (px === null || !isFinite(px) || px <= 0) {
        return raw;
    }
    var rounded = Math.round(px);
    // 只要不是“整数 px 且在白名单”，就吸附（包含 15.8px/15px/34px 这种）
    if (Math.abs(px - rounded) > 0.02 || !_allowedGameFontSizeSet.has(rounded)) {
        var snapped = _pickNearestAllowedGameFontSize(rounded);
        if (diagnostics && diagnostics.warn && snapped !== rounded) {
            diagnostics.warn({
                code: "DOWNGRADE.FONT_SIZE_SNAPPED",
                message: "字号将吸附到游戏可表达的字号白名单。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { sourcePx: px, rounded: rounded, snapped: snapped },
                fix: { kind: "downgrade", suggestion: "如需减少差异，请在 HTML 中直接使用允许字号（10/12/14/.../36/48/72...）。" }
            });
        }
        return String(snapped) + "px";
    }
    return String(rounded) + "px";
}

export function estimateLineHeightPx(styles) {
    var fontSizePx = _parsePxNumber(styles && styles.fontSize ? String(styles.fontSize || "") : "");
    if (fontSizePx === null || !isFinite(fontSizePx) || fontSizePx <= 0) {
        fontSizePx = 16;
    }

    var lineHeightText = styles && styles.lineHeight ? String(styles.lineHeight || "") : "";
    var lineHeightTrimmed = String(lineHeightText || "").trim().toLowerCase();
    if (!lineHeightTrimmed || lineHeightTrimmed === "normal") {
        return fontSizePx * 1.2;
    }

    var pxNumber = _parsePxNumber(lineHeightTrimmed);
    if (pxNumber !== null && isFinite(pxNumber) && pxNumber > 0) {
        return pxNumber;
    }

    if (lineHeightTrimmed.endsWith("%")) {
        var percentNumber = Number.parseFloat(lineHeightTrimmed.slice(0, -1).trim());
        if (isFinite(percentNumber) && percentNumber > 0) {
            return fontSizePx * (percentNumber / 100);
        }
    }

    if (lineHeightTrimmed.endsWith("em")) {
        var emNumber = Number.parseFloat(lineHeightTrimmed.slice(0, -2).trim());
        if (isFinite(emNumber) && emNumber > 0) {
            return fontSizePx * emNumber;
        }
    }

    if (lineHeightTrimmed.endsWith("rem")) {
        var remNumber = Number.parseFloat(lineHeightTrimmed.slice(0, -3).trim());
        if (isFinite(remNumber) && remNumber > 0) {
            return fontSizePx * remNumber;
        }
    }

    var unitlessNumber = Number.parseFloat(lineHeightTrimmed);
    if (isFinite(unitlessNumber) && unitlessNumber > 0) {
        return fontSizePx * unitlessNumber;
    }

    return fontSizePx * 1.2;
}

function _normalizeVerticalAnchorFromAlignItems(alignItemsValue) {
    var lowered = String(alignItemsValue || "").trim().toLowerCase();
    if (lowered === "flex-start" || lowered === "start") {
        return "top";
    }
    if (lowered === "flex-end" || lowered === "end") {
        return "bottom";
    }
    return "center";
}

function _normalizeHorizontalAnchorFromJustifyContent(justifyContentValue) {
    var lowered = String(justifyContentValue || "").trim().toLowerCase();
    if (lowered === "flex-end" || lowered === "end") {
        return "right";
    }
    if (lowered === "center") {
        return "center";
    }
    return "left";
}

export function computeExpandedTextRect(innerLeft, innerTop, innerWidth, innerHeight, styles, alignItemsValue) {
    var lineHeightPx = estimateLineHeightPx(styles || {});
    if (!isFinite(lineHeightPx) || lineHeightPx <= 0) {
        return {
            left: innerLeft,
            top: innerTop,
            width: innerWidth,
            height: innerHeight,
            extraHeight: 0
        };
    }

    // 需求：文本层“高度更大”，上下各扩展 0.5 行高；同时文字渲染位置不变。
    // 实现：总扩展量 = 1 行高；再按垂直对齐锚点决定 top 的上移量，保证锚点（上/中/下）不变。
    //
    // 额外约束（工程化）：对“小字号（例如 10/12/14）”额外扩展需更大。
    // 原因：游戏侧渲染存在描边/像素取整，字号越小越容易在文本框上下边缘发生裁切。
    // 策略：当字号 < 16px 时，按线性比例放大扩展量；并叠加少量像素兜底，避免“刚好差 1~2px”。
    var fontSizePx = _parsePxNumber(styles && styles.fontSize ? String(styles.fontSize || "") : "");
    if (fontSizePx === null || !isFinite(fontSizePx) || fontSizePx <= 0) {
        fontSizePx = lineHeightPx / 1.2;
    }
    if (!isFinite(fontSizePx) || fontSizePx <= 0) {
        fontSizePx = 16;
    }
    // 更激进的小字号扩展曲线（用户反馈：12px 仍会裁切）
    // - 18px+: 1.0 行高
    // - 16~18px: 1.4 行高
    // - 14~16px: 1.8 行高
    // - 12~14px: 2.2 行高
    // - 10~12px: 2.6 行高
    // - <=10px : 3.0 行高
    var scale = 1;
    if (fontSizePx < 18) scale = 1.4;
    if (fontSizePx <= 16) scale = 1.8;
    if (fontSizePx <= 14) scale = 2.2;
    if (fontSizePx <= 12) scale = 2.6;
    if (fontSizePx <= 10) scale = 3.0;

    // 小字号额外给固定像素兜底，抵抗渲染取整/描边造成的 1~几像素裁切
    var extraPadPx = 0;
    if (fontSizePx <= 14) {
        extraPadPx = 10;
    } else if (fontSizePx < 18) {
        extraPadPx = 6;
    }

    var extraHeight = lineHeightPx * scale + extraPadPx;
    var anchor = _normalizeVerticalAnchorFromAlignItems(alignItemsValue);
    var topShift = 0;
    if (anchor === "bottom") {
        topShift = extraHeight;
    } else if (anchor === "center") {
        topShift = extraHeight / 2;
    }

    return {
        left: innerLeft,
        top: innerTop - topShift,
        width: innerWidth,
        height: Math.max(0, innerHeight + extraHeight),
        extraHeight: extraHeight
    };
}

export function computeExpandedTextHitRect(renderTextRect, styles, justifyContentValue) {
    // 需求：文本层“宽度更大”，但文字渲染保持不变（字号/位置/换行都不变）。
    // 实现：把“更大的宽度”用作外层 hitbox；内层仍按原 renderTextRect 的 width 渲染。
    // 注意：外层 left 会按水平锚点（左/中/右）做偏移，以保证锚点不变。
    if (!renderTextRect) {
        return null;
    }
    var lineHeightPx = estimateLineHeightPx(styles || {});
    if (!isFinite(lineHeightPx) || lineHeightPx <= 0) {
        return {
            left: renderTextRect.left,
            top: renderTextRect.top,
            width: renderTextRect.width,
            height: renderTextRect.height,
            innerOffsetX: 0,
            extraWidth: 0
        };
    }

    // 宽度扩展需要与字号相关，且至少能“多容纳约 2 个字”的宽度（常见中文：1 字≈font-size）。
    var fontSizePx = _parsePxNumber(styles && styles.fontSize ? String(styles.fontSize || "") : "");
    if (fontSizePx === null || !isFinite(fontSizePx) || fontSizePx <= 0) {
        fontSizePx = lineHeightPx / 1.2;
    }
    if (!isFinite(fontSizePx) || fontSizePx <= 0) {
        fontSizePx = 16;
    }
    var extraWidth = Math.max(lineHeightPx, fontSizePx * 2);
    var anchor = _normalizeHorizontalAnchorFromJustifyContent(justifyContentValue);
    var leftShift = 0;
    if (anchor === "right") {
        leftShift = extraWidth;
    } else if (anchor === "center") {
        leftShift = extraWidth / 2;
    }

    var hitLeft = renderTextRect.left - leftShift;
    var hitWidth = Math.max(0, renderTextRect.width + extraWidth);
    var innerOffsetX = renderTextRect.left - hitLeft;

    return {
        left: hitLeft,
        top: renderTextRect.top,
        width: hitWidth,
        height: renderTextRect.height,
        innerOffsetX: innerOffsetX,
        extraWidth: extraWidth
    };
}

