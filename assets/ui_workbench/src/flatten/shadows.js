import { PALETTE_SHADE_OVERLAY_RGBA, PALETTE_SHADE_OVERLAY_RGBA_25, PALETTE_SHADE_OVERLAY_HEX, PALETTE_SHADE_OVERLAY_HEX_25 } from "../config.js";
import { splitCssByTopLevelCommas } from "../utils.js";

function _clamp01(x) {
    if (!isFinite(x)) return 1;
    if (x < 0) return 0;
    if (x > 1) return 1;
    return x;
}

function _parseAlphaFromColorToken(colorToken) {
    var t = String(colorToken || "").trim().toLowerCase();
    if (!t) return null;

    // 允许的“规范阴影色”快捷识别
    if (t === String(PALETTE_SHADE_OVERLAY_HEX || "").trim().toLowerCase()) return 0.45;
    if (t === String(PALETTE_SHADE_OVERLAY_HEX_25 || "").trim().toLowerCase()) return 0.25;

    // #rrggbbaa
    if (t[0] === "#" && t.length === 9) {
        var aa = parseInt(t.slice(7, 9), 16);
        if (isFinite(aa)) {
            return _clamp01(aa / 255.0);
        }
        return null;
    }

    // rgba(r,g,b,a) / rgb(r,g,b)
    var m = /^rgba?\(([^)]+)\)$/.exec(t);
    if (!m) return null;
    var parts = String(m[1] || "")
        .split(",")
        .map(function (x) { return String(x || "").trim(); })
        .filter(function (x) { return x.length > 0; });
    if (parts.length < 3) return null;
    if (parts.length >= 4) {
        var a = Number.parseFloat(parts[3]);
        if (isFinite(a)) return _clamp01(a);
        return null;
    }
    // rgb(...) 没有 alpha
    return 1;
}

function _pickNormalizedShadowColorByAlpha(alpha) {
    // 两档吸附：<= ~0.33 → 25%，其余 → 45%
    // 这里用 0.34 作为边界，避免 1/3 四舍五入导致抖动。
    if (alpha <= 0.34) {
        return PALETTE_SHADE_OVERLAY_RGBA_25;
    }
    return PALETTE_SHADE_OVERLAY_RGBA;
}

export function parseBoxShadow(shadowText, opts) {
    var o = opts || {};
    var diagnostics = o.diagnostics || null;
    var target = o.target || null;
    var context = String(o.context || "").trim();

    var shadowValue = String(shadowText || "").trim();
    if (!shadowValue || shadowValue === "none") {
        return [];
    }

    var layers = splitCssByTopLevelCommas(shadowValue);
    var parsedShadows = [];
    var ignoredInsetTotal = 0;
    var hadNonZeroBlurOrSpread = false;
    var hadExplicitColor = false;
    var normalizedColorChoice = null;

    for (var layerIndex = 0; layerIndex < layers.length; layerIndex++) {
        var layerText = layers[layerIndex].trim();
        if (!layerText || layerText === "none") {
            continue;
        }
        if (layerText.toLowerCase().indexOf("inset") === 0) {
            ignoredInsetTotal += 1;
            continue;
        }

        var colorValue = null;
        var colorPattern = /(rgba?\s*\([^)]+\)|#[a-fA-F0-9]{3,8})/;
        var colorMatch = colorPattern.exec(layerText);
        if (colorMatch) {
            colorValue = colorMatch[1];
            layerText = (layerText.slice(0, colorMatch.index) + layerText.slice(colorMatch.index + colorMatch[0].length)).trim();
        }

        var numericPattern = /(-?[\d.]+)(?:px)?/g;
        var numericMatches = layerText.match(numericPattern) || [];
        if (numericMatches.length < 2) {
            continue;
        }

        var offsetX = Number.parseFloat(numericMatches[0]);
        var offsetY = Number.parseFloat(numericMatches[1]);
        var blurRadius = numericMatches.length >= 3 ? Number.parseFloat(numericMatches[2]) : 0;
        var spreadRadius = numericMatches.length >= 4 ? Number.parseFloat(numericMatches[3]) : 0;
        if (!isFinite(offsetX) || !isFinite(offsetY) || !isFinite(blurRadius) || !isFinite(spreadRadius)) {
            continue;
        }
        if (Math.abs(blurRadius) > 1e-6 || Math.abs(spreadRadius) > 1e-6) {
            hadNonZeroBlurOrSpread = true;
        }
        if (colorValue) {
            hadExplicitColor = true;
        }

        var pickedColor = PALETTE_SHADE_OVERLAY_RGBA;
        if (colorValue) {
            var a = _parseAlphaFromColorToken(colorValue);
            if (a !== null) {
                pickedColor = _pickNormalizedShadowColorByAlpha(a);
            }
        }
        normalizedColorChoice = pickedColor;

        parsedShadows.push({
            offsetX: offsetX,
            offsetY: offsetY,
            blur: blurRadius,
            spread: spreadRadius,
            // 规范：投影阴影颜色只允许两档（25%/45%），按输入 alpha 自动吸附。
            color: pickedColor
        });
    }

    if (diagnostics && diagnostics.warn) {
        if (ignoredInsetTotal > 0) {
            diagnostics.warn({
                code: "DOWNGRADE.BOX_SHADOW_INSET_IGNORED",
                message: "box-shadow inset 阴影无法写回为矩形投影层，已忽略（不影响其他层）。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { ignoredInsetLayers: ignoredInsetTotal },
                fix: { kind: "downgrade", suggestion: "尽量避免 inset；需要内阴影效果请用“盖色阴影 overlay 元素”表达。" }
            });
        }
        if (hadExplicitColor) {
            diagnostics.warn({
                code: "DOWNGRADE.BOX_SHADOW_COLOR_NORMALIZED",
                message: "box-shadow 颜色已归一化为允许的阴影色档位（25%/45%）。（写回链路仅支持这两档）" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { normalizedColor: normalizedColorChoice || PALETTE_SHADE_OVERLAY_RGBA },
                fix: { kind: "downgrade", suggestion: "在 HTML 中直接使用 rgba(14,14,14,0.45) 或 rgba(14,14,14,0.25) 以减少降级提示。" }
            });
        }
        if (hadNonZeroBlurOrSpread) {
            diagnostics.warn({
                code: "DOWNGRADE.BOX_SHADOW_BLUR_SPREAD_APPROX",
                message: "box-shadow 的 blur/spread 将用“矩形外扩近似”表达（可能与浏览器效果有差异）。" + (context ? (" context=" + context) : ""),
                target: target,
                fix: { kind: "downgrade", suggestion: "如需更一致效果，请把 blur/spread 写为 0，只用 offset 表达厚度阴影。" }
            });
        }
    }

    return parsedShadows;
}

export function parseTextShadow(shadowText) {
    var shadowValue = String(shadowText || "").trim();
    if (!shadowValue || shadowValue === "none") {
        return [];
    }

    var layers = splitCssByTopLevelCommas(shadowValue);
    var parsed = [];

    for (var layerIndex = 0; layerIndex < layers.length; layerIndex++) {
        var layerText = String(layers[layerIndex] || "").trim();
        if (!layerText || layerText === "none") {
            continue;
        }

        // 允许：rgb/rgba/#hex（computed style 下 var() 会被解析成 rgb）
        var colorValue = null;
        var colorPattern = /(rgba?\s*\([^)]+\)|#[a-fA-F0-9]{3,8})/;
        var colorMatch = colorPattern.exec(layerText);
        if (colorMatch) {
            colorValue = colorMatch[1];
            layerText = (layerText.slice(0, colorMatch.index) + layerText.slice(colorMatch.index + colorMatch[0].length)).trim();
        }

        // text-shadow: offset-x offset-y blur-radius? color?
        var numericPattern = /(-?[\d.]+)(?:px)?/g;
        var numericMatches = layerText.match(numericPattern) || [];
        if (numericMatches.length < 2) {
            continue;
        }

        var offsetX = Number.parseFloat(numericMatches[0]);
        var offsetY = Number.parseFloat(numericMatches[1]);
        var blurRadius = numericMatches.length >= 3 ? Number.parseFloat(numericMatches[2]) : 0;
        if (!isFinite(offsetX) || !isFinite(offsetY) || !isFinite(blurRadius)) {
            continue;
        }

        parsed.push({
            offsetX: offsetX,
            offsetY: offsetY,
            blur: blurRadius,
            color: colorValue ? String(colorValue || "") : PALETTE_SHADE_OVERLAY_RGBA
        });
    }

    return parsed;
}

