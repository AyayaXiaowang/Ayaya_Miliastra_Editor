import {
    PALETTE_ALLOWED_HEX_COLORS,
    PALETTE_DARK1_VARIANT_TO_BASE_HEX,
    PALETTE_DARK2_VARIANT_TO_BASE_HEX,
    PALETTE_DARK3_VARIANT_TO_BASE_HEX,
    PALETTE_DARK_VARIANT_TO_BASE_HEX,
    PALETTE_SHADE_OVERLAY_RGBA,
    PALETTE_SHADE_OVERLAY_RGBA_25,
    PALETTE_SHADE_OVERLAY_HEX,
    PALETTE_SHADE_OVERLAY_HEX_25
} from "../config.js";
import { formatColorTextAsHex } from "../preview/color.js";

var _paletteAllowedHexSet = new Set((PALETTE_ALLOWED_HEX_COLORS || []).map(function (item) { return String(item || "").trim().toLowerCase(); }));
var _paletteBaseHexList = (PALETTE_ALLOWED_HEX_COLORS || []).filter(function (x) { return String(x || "").trim().length > 0; });

function _hexToRgb(hexText) {
    var hex = String(hexText || "").trim().toLowerCase();
    if (!hex || hex[0] !== "#") {
        return null;
    }
    if (hex.length === 4) {
        // #rgb
        var r3 = parseInt(hex[1] + hex[1], 16);
        var g3 = parseInt(hex[2] + hex[2], 16);
        var b3 = parseInt(hex[3] + hex[3], 16);
        return { r: r3, g: g3, b: b3 };
    }
    if (hex.length >= 7) {
        // #rrggbb or #rrggbbaa
        var r6 = parseInt(hex.slice(1, 3), 16);
        var g6 = parseInt(hex.slice(3, 5), 16);
        var b6 = parseInt(hex.slice(5, 7), 16);
        if (!isFinite(r6) || !isFinite(g6) || !isFinite(b6)) {
            return null;
        }
        return { r: r6, g: g6, b: b6 };
    }
    return null;
}

function _distSq(a, b) {
    var dr = a.r - b.r;
    var dg = a.g - b.g;
    var db = a.b - b.b;
    return dr * dr + dg * dg + db * db;
}

function _pickNearestAllowedHex(hexText) {
    var src = _hexToRgb(hexText);
    if (!src) {
        return null;
    }
    var bestHex = null;
    var bestDist = null;
    for (var i = 0; i < _paletteBaseHexList.length; i++) {
        var candHex = String(_paletteBaseHexList[i] || "").trim().toLowerCase();
        if (!candHex || candHex[0] !== "#") continue;
        // 注意：允许列表里也包含 dark variant / shade overlay；但对“矩形底色/边框”我们更倾向吸附到 base 色或 dark->base。
        var rgb = _hexToRgb(candHex);
        if (!rgb) continue;
        var d = _distSq(src, rgb);
        if (bestDist === null || d < bestDist) {
            bestDist = d;
            bestHex = candHex;
        }
    }
    return bestHex;
}

function _hexToRgba(hexText) {
    var hex = String(hexText || "").trim().toLowerCase();
    if (!hex || hex[0] !== "#") {
        return null;
    }
    if (hex.length === 5) {
        // #rgba
        var r4 = parseInt(hex[1] + hex[1], 16);
        var g4 = parseInt(hex[2] + hex[2], 16);
        var b4 = parseInt(hex[3] + hex[3], 16);
        var a4 = parseInt(hex[4] + hex[4], 16);
        if (!isFinite(r4) || !isFinite(g4) || !isFinite(b4) || !isFinite(a4)) return null;
        return { r: r4, g: g4, b: b4, a: a4 / 255.0 };
    }
    if (hex.length === 9) {
        // #rrggbbaa
        var r8 = parseInt(hex.slice(1, 3), 16);
        var g8 = parseInt(hex.slice(3, 5), 16);
        var b8 = parseInt(hex.slice(5, 7), 16);
        var a8 = parseInt(hex.slice(7, 9), 16);
        if (!isFinite(r8) || !isFinite(g8) || !isFinite(b8) || !isFinite(a8)) return null;
        return { r: r8, g: g8, b: b8, a: a8 / 255.0 };
    }
    // #rgb / #rrggbb：当作不透明
    var rgb = _hexToRgb(hex);
    if (!rgb) return null;
    return { r: rgb.r, g: rgb.g, b: rgb.b, a: 1.0 };
}

function _pickShadeOverlayHexByAlpha(alpha) {
    // 两档吸附：<= ~0.33 → 25%，其余 → 45%
    if (alpha <= 0.34) {
        return PALETTE_SHADE_OVERLAY_HEX_25;
    }
    return PALETTE_SHADE_OVERLAY_HEX;
}

function _isForbiddenSolidBlackRgba(rgba) {
    // 仅禁止“不透明纯黑”（#000/#000000/rgb(0,0,0)/rgba(0,0,0,1) 等）
    // - 目的：避免扁平化/写回链路里出现“黑色盖色层异常”，从而导致文字被底色遮挡或不可读。
    // - 不限制文本 color（文字颜色允许任意）。
    if (!rgba) {
        return false;
    }
    var a = Number(rgba.a);
    if (!isFinite(a)) {
        return false;
    }
    if (a < 0.999) {
        return false;
    }
    return Number(rgba.r) === 0 && Number(rgba.g) === 0 && Number(rgba.b) === 0;
}

export function normalizeColorTextAsHex(colorText) {
    var hex = formatColorTextAsHex(colorText || "");
    if (!hex) {
        return "";
    }
    return String(hex || "").trim().toLowerCase();
}

export function isTransparentColor(colorText) {
    var hex = normalizeColorTextAsHex(colorText || "");
    return hex === "#00000000";
}

export function mapRectFillColorForPalette(colorText, opts) {
    var o = opts || {};
    var diagnostics = o.diagnostics || null;
    var target = o.target || null;
    var context = String(o.context || "").trim();

    var hex = normalizeColorTextAsHex(colorText || "");
    if (!hex) { // If colorText is empty or invalid, return it as is with no overlay
        return { colorText: String(colorText || ""), needsShadeOverlay: false, needsShadeOverlayCount: 0, needsShadeOverlayRgba: "", sourceHex: "" };
    }

    // 强约束：禁止不透明纯黑（矩形底色/边框/阴影）
    // 说明：
    // - 该规则只对“矩形类颜色”（background/border/shadow）生效；
    // - 文本颜色不走这里（不受影响）。
    // - 这里既输出 diagnostics（供 UI 面板提示），也做“自动映射到允许的墨色”，降低预览/后续流程的随机性。
    var rgba = _hexToRgba(hex);
    if (_isForbiddenSolidBlackRgba(rgba)) {
        if (diagnostics && diagnostics.error) {
            diagnostics.error({
                code: "COLOR.FORBIDDEN_SOLID_BLACK",
                message: "检测到不透明纯黑（#000/#000000）：禁止用于矩形底色/边框/阴影；会在部分写回链路中触发盖色异常（常见表现：文字被底色盖住）。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { sourceHex: hex, raw: String(colorText || "") },
                fix: { kind: "manual", suggestion: "请改用允许的墨色：#0e0e0e73（45%）或 #0e0e0e40（25%）；或使用 rgba(14,14,14,0.45/0.25)。" }
            });
        }
        // 显式映射为“允许的墨色”，避免继续走“最近色吸附”导致的不稳定。
        return { colorText: String(PALETTE_SHADE_OVERLAY_HEX || ""), needsShadeOverlay: false, needsShadeOverlayCount: 0, needsShadeOverlayRgba: "", sourceHex: hex };
    }

    // 半透明黑/灰：优先视作“阴影遮罩”，吸附到允许的两档 overlay（避免被调色板量化成“更黑”）
    // 典型场景：作者写 rgba(0,0,0,0.14/0.22/0.25/0.45) 想做浅/深阴影。
    if (rgba && rgba.a < 0.999) {
        // 只对“黑/深灰”启用该规则，避免误伤其它半透明彩色设计。
        if (rgba.r <= 24 && rgba.g <= 24 && rgba.b <= 24) {
            var mappedOverlayHex = _pickShadeOverlayHexByAlpha(rgba.a);
            if (diagnostics && diagnostics.warn) {
                diagnostics.warn({
                    code: "DOWNGRADE.ALPHA_BLACK_MAPPED_TO_SHADE_OVERLAY",
                    message: "半透明黑底色将吸附为允许的阴影遮罩档位（25%/45%），避免调色板量化导致变深。" + (context ? (" context=" + context) : ""),
                    target: target,
                    evidence: { sourceHex: hex, alpha: rgba.a, mappedHex: mappedOverlayHex },
                    fix: { kind: "downgrade", suggestion: "建议直接使用 #0e0e0e40（25%）或 #0e0e0e73（45%），或使用 rgba(14,14,14,0.25/0.45)。" }
                });
            }
            return { colorText: String(mappedOverlayHex || ""), needsShadeOverlay: false, needsShadeOverlayCount: 0, needsShadeOverlayRgba: "", sourceHex: hex };
        }
    }

    // 关键：如果颜色本身就在“允许调色板”中（包含 base / dark1/2/3 / shade overlay hex），
    // 则应直接保留为实色。
    //
    // 之前的策略会把 dark1/2/3 变体“归一化”为 base + 盖色阴影层（shade overlay），
    // 这会额外生成 `shade-*` 扁平层；在部分写回/导出链路中，盖色层可能被误处理成纯黑 #000000，
    // 从而造成“项目不支持的黑色矩形层”。
    if (_paletteAllowedHexSet.has(hex)) {
        return { colorText: hex, needsShadeOverlay: false, needsShadeOverlayCount: 0, needsShadeOverlayRgba: "", sourceHex: hex };
    }

    // Dark3（压暗 3 级）：Base + 两层 45% shade overlay
    var baseHex3 = PALETTE_DARK3_VARIANT_TO_BASE_HEX ? PALETTE_DARK3_VARIANT_TO_BASE_HEX[hex] : null;
    if (baseHex3) {
        if (diagnostics && diagnostics.warn) {
            diagnostics.warn({
                code: "DOWNGRADE.COLOR_DARK3_VARIANT_TO_BASE",
                message: "压暗 3 级色将导出为 Base + 两层 45% 盖色阴影（扁平化归一化）。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { sourceHex: hex, baseHex: String(baseHex3 || ""), overlayCount: 2, overlayRgba: PALETTE_SHADE_OVERLAY_RGBA },
                fix: { kind: "downgrade", suggestion: "建议直接使用 Base 色；按下态/更暗由引擎用盖色阴影叠加表达。" }
            });
        }
        return { colorText: String(baseHex3 || ""), needsShadeOverlay: true, needsShadeOverlayCount: 2, needsShadeOverlayRgba: PALETTE_SHADE_OVERLAY_RGBA, sourceHex: hex };
    }

    // Dark2（压暗 2 级）：Base + 一层 45% shade overlay（历史兼容名：PALETTE_DARK_VARIANT_TO_BASE_HEX）
    var baseHex2 = PALETTE_DARK2_VARIANT_TO_BASE_HEX ? PALETTE_DARK2_VARIANT_TO_BASE_HEX[hex] : null;
    var baseHex2Compat = (!baseHex2 && PALETTE_DARK_VARIANT_TO_BASE_HEX) ? PALETTE_DARK_VARIANT_TO_BASE_HEX[hex] : null;
    var baseHexForDark2 = baseHex2 || baseHex2Compat;
    if (baseHexForDark2) {
        if (diagnostics && diagnostics.warn) {
            diagnostics.warn({
                code: "DOWNGRADE.COLOR_DARK2_VARIANT_TO_BASE",
                message: "压暗 2 级色将导出为 Base + 45% 盖色阴影（扁平化归一化）。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { sourceHex: hex, baseHex: String(baseHexForDark2 || ""), overlayCount: 1, overlayRgba: PALETTE_SHADE_OVERLAY_RGBA },
                fix: { kind: "downgrade", suggestion: "建议直接使用 Base 色；按下态/压暗由引擎用盖色阴影表达。" }
            });
        }
        return { colorText: String(baseHexForDark2 || ""), needsShadeOverlay: true, needsShadeOverlayCount: 1, needsShadeOverlayRgba: PALETTE_SHADE_OVERLAY_RGBA, sourceHex: hex };
    }

    // Dark1（压暗 1 级）：Base + 一层 25% shade overlay
    var baseHex1 = PALETTE_DARK1_VARIANT_TO_BASE_HEX ? PALETTE_DARK1_VARIANT_TO_BASE_HEX[hex] : null;
    if (baseHex1) {
        if (diagnostics && diagnostics.warn) {
            diagnostics.warn({
                code: "DOWNGRADE.COLOR_DARK1_VARIANT_TO_BASE",
                message: "压暗 1 级色将导出为 Base + 25% 盖色阴影（扁平化归一化）。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { sourceHex: hex, baseHex: String(baseHex1 || ""), overlayCount: 1, overlayRgba: PALETTE_SHADE_OVERLAY_RGBA_25 },
                fix: { kind: "downgrade", suggestion: "建议直接使用 Base 色；小幅压暗由引擎用 25% 盖色阴影表达。" }
            });
        }
        return { colorText: String(baseHex1 || ""), needsShadeOverlay: true, needsShadeOverlayCount: 1, needsShadeOverlayRgba: PALETTE_SHADE_OVERLAY_RGBA_25, sourceHex: hex };
    }

    // Web-first：允许 AI 自由写色，但导出/写回最终只能表达有限调色板，因此这里做“吸附量化”并给出 warning。
    var nearest = _pickNearestAllowedHex(hex);
    if (nearest && _paletteAllowedHexSet.has(nearest)) {
        if (diagnostics && diagnostics.warn) {
            diagnostics.warn({
                code: "DOWNGRADE.COLOR_QUANTIZED_TO_PALETTE",
                message: "颜色不在调色板内，已吸附到最接近的允许色。" + (context ? (" context=" + context) : ""),
                target: target,
                evidence: { sourceHex: hex, mappedHex: nearest },
                fix: { kind: "downgrade", suggestion: "如需精确颜色，请改用调色板色值；或把差异视为可接受的风格降级。" }
            });
        }
        return { colorText: nearest, needsShadeOverlay: false, needsShadeOverlayCount: 0, needsShadeOverlayRgba: "", sourceHex: hex };
    }
    if (diagnostics && diagnostics.warn) {
        diagnostics.warn({
            code: "DOWNGRADE.COLOR_PARSE_OR_MAP_FAILED",
            message: "颜色不在调色板内，且未能可靠吸附；将按原色保留（可能导致写回失败）。" + (context ? (" context=" + context) : ""),
            target: target,
            evidence: { sourceHex: hex, raw: String(colorText || "") },
            fix: { kind: "manual", suggestion: "将颜色替换为调色板允许的 5 基础色或其压暗色。" }
        });
    }
    return { colorText: String(colorText || ""), needsShadeOverlay: false, needsShadeOverlayCount: 0, needsShadeOverlayRgba: "", sourceHex: hex };
}

