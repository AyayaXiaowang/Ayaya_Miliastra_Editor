import * as preview from "../preview/index.js";

export var ALLOWED_GAME_FONT_SIZES = [
    10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36,
    48, 72, 96, 128, 256, 512
];
var _allowedGameFontSizeSet = new Set(ALLOWED_GAME_FONT_SIZES.map(function (x) { return Number(x); }));

// 小字号文本的“暗色”告警：用于规避引擎灰色描边在小字上“吃掉文字”的情况。
// 说明：这里使用 WCAG 相对亮度（relative luminance），而不是简单 RGB 平均值。
export var SMALL_TEXT_FONT_SIZE_WARN_LT = 30;
// 告警策略：主要针对“灰/低饱和”的中间亮度文字（接近描边灰，容易糊），
// 不希望误报“纯黑/纯白”等高可读性文字。
export var SMALL_TEXT_DARK_LUMINANCE_WARN_LT = 0.38; // (保留导出给 UI 文案使用；真实判定见 shouldWarnSmallTextDarkColor)
export var SMALL_TEXT_GRAYISH_SATURATION_WARN_LT = 0.18;
export var SMALL_TEXT_LUMINANCE_NO_WARN_LE = 0.08;  // 近黑：不告警
export var SMALL_TEXT_LUMINANCE_NO_WARN_GE = 0.92;  // 近白：不告警

export function parsePxNumber(valueText) {
    var trimmed = String(valueText || "").trim();
    if (!trimmed) {
        return null;
    }
    var match = /^([+-]?\d+(\.\d+)?)(px)?$/i.exec(trimmed);
    if (!match) {
        return null;
    }
    var numberValue = Number(match[1]);
    if (!isFinite(numberValue)) {
        return null;
    }
    return numberValue;
}

function parseHexToRgba(hexText) {
    var trimmed = String(hexText || "").trim();
    var match = /^#([a-fA-F0-9]{3,8})$/.exec(trimmed);
    if (!match) {
        return null;
    }
    var hex = match[1];
    if (hex.length === 3) {
        var r3 = parseInt(hex[0] + hex[0], 16);
        var g3 = parseInt(hex[1] + hex[1], 16);
        var b3 = parseInt(hex[2] + hex[2], 16);
        return { r: r3, g: g3, b: b3, a: 255 };
    }
    if (hex.length === 4) {
        var r4 = parseInt(hex[0] + hex[0], 16);
        var g4 = parseInt(hex[1] + hex[1], 16);
        var b4 = parseInt(hex[2] + hex[2], 16);
        var a4 = parseInt(hex[3] + hex[3], 16);
        return { r: r4, g: g4, b: b4, a: a4 };
    }
    if (hex.length === 6) {
        var r6 = parseInt(hex.slice(0, 2), 16);
        var g6 = parseInt(hex.slice(2, 4), 16);
        var b6 = parseInt(hex.slice(4, 6), 16);
        return { r: r6, g: g6, b: b6, a: 255 };
    }
    if (hex.length === 8) {
        var r8 = parseInt(hex.slice(0, 2), 16);
        var g8 = parseInt(hex.slice(2, 4), 16);
        var b8 = parseInt(hex.slice(4, 6), 16);
        var a8 = parseInt(hex.slice(6, 8), 16);
        return { r: r8, g: g8, b: b8, a: a8 };
    }
    return null;
}

function cssColorToRgba(colorText) {
    var hex = preview.formatColorTextAsHex(colorText || "");
    if (!hex || hex[0] !== "#") {
        return null;
    }
    return parseHexToRgba(hex);
}

function srgbByteToLinear01(byteValue) {
    var cs = clampNumber(byteValue, 0, 255) / 255.0;
    if (cs <= 0.04045) {
        return cs / 12.92;
    }
    return Math.pow((cs + 0.055) / 1.055, 2.4);
}

export function computeRelativeLuminanceFromCssColor(colorText) {
    // Returns [0..1], higher = brighter. If alpha exists, returns Y * alpha (treat semi-transparent text as dimmer).
    var rgba = cssColorToRgba(colorText || "");
    if (!rgba) {
        return null;
    }
    var r = srgbByteToLinear01(rgba.r);
    var g = srgbByteToLinear01(rgba.g);
    var b = srgbByteToLinear01(rgba.b);
    var y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    var a = clampNumber(rgba.a, 0, 255) / 255.0;
    return y * a;
}

function computeSaturation01FromCssColor(colorText) {
    var rgba = cssColorToRgba(colorText || "");
    if (!rgba) {
        return null;
    }
    var r = clampNumber(rgba.r, 0, 255) / 255.0;
    var g = clampNumber(rgba.g, 0, 255) / 255.0;
    var b = clampNumber(rgba.b, 0, 255) / 255.0;
    var max = Math.max(r, g, b);
    var min = Math.min(r, g, b);
    var delta = max - min;
    if (max <= 1e-9) {
        return 0;
    }
    return delta / max;
}

export function shouldWarnSmallTextDarkColor(fontSizeNumber, colorText) {
    var size = Number(fontSizeNumber);
    if (!isFinite(size)) {
        return false;
    }
    if (size >= SMALL_TEXT_FONT_SIZE_WARN_LT) {
        return false;
    }
    var lum = computeRelativeLuminanceFromCssColor(colorText || "");
    if (lum === null) {
        return false;
    }
    // 黑/白：通常仍然清晰（黑字不“灰”，白字也不“灰”），不告警
    if (lum <= SMALL_TEXT_LUMINANCE_NO_WARN_LE || lum >= SMALL_TEXT_LUMINANCE_NO_WARN_GE) {
        return false;
    }
    // 主要针对“灰/低饱和”颜色（接近引擎描边灰）
    var sat = computeSaturation01FromCssColor(colorText || "");
    if (sat === null) {
        return false;
    }
    if (sat >= SMALL_TEXT_GRAYISH_SATURATION_WARN_LT) {
        return false;
    }
    // 兜底：仍保留一个亮度下限，避免过暗导致“看不见”的情况
    return lum < SMALL_TEXT_DARK_LUMINANCE_WARN_LT;
}

export function isShadowOverlayColor(colorText) {
    // 阴影规范色：rgba(14,14,14,0.45) / #0E0E0E73
    var rgba = cssColorToRgba(colorText || "");
    if (!rgba) {
        return false;
    }
    var r = Number(rgba.r);
    var g = Number(rgba.g);
    var b = Number(rgba.b);
    var a = Number(rgba.a);
    if (!isFinite(r) || !isFinite(g) || !isFinite(b) || !isFinite(a)) {
        return false;
    }
    if (Math.abs(r - 14) > 1 || Math.abs(g - 14) > 1 || Math.abs(b - 14) > 1) {
        return false;
    }
    var alpha = a / 255.0;
    return Math.abs(alpha - 0.45) <= 0.03;
}

export function isShadowOverlayColor25(colorText) {
    // 阴影规范色（25%）：rgba(14,14,14,0.25) / #0E0E0E40
    var rgba = cssColorToRgba(colorText || "");
    if (!rgba) {
        return false;
    }
    var r = Number(rgba.r);
    var g = Number(rgba.g);
    var b = Number(rgba.b);
    var a = Number(rgba.a);
    if (!isFinite(r) || !isFinite(g) || !isFinite(b) || !isFinite(a)) {
        return false;
    }
    if (Math.abs(r - 14) > 1 || Math.abs(g - 14) > 1 || Math.abs(b - 14) > 1) {
        return false;
    }
    var alpha = a / 255.0;
    return Math.abs(alpha - 0.25) <= 0.03;
}

export function getShadowOverlayAlpha(colorText) {
    if (isShadowOverlayColor(colorText)) {
        return 0.45;
    }
    if (isShadowOverlayColor25(colorText)) {
        return 0.25;
    }
    return null;
}

export function pickNearestAllowedGameFontSize(sizeInt) {
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

export function pickUniformTextFontSizeOverride(layer, exportOptions) {
    if (!layer) {
        return null;
    }
    var opts = exportOptions || {};
    var map = opts.uniform_text_font_size_by_element_index || null;
    if (!map) {
        return null;
    }
    var src = layer.source || null;
    if (!src || !Number.isFinite(src.elementIndex)) {
        return null;
    }
    var key = String(Math.trunc(src.elementIndex));
    var raw = map[key];
    var num = Number(raw);
    if (!isFinite(num) || num <= 0) {
        return null;
    }
    return Math.max(1, Math.round(num));
}

export function clampNumber(value, minValue, maxValue) {
    var numberValue = Number(value);
    if (!isFinite(numberValue)) {
        return minValue;
    }
    return Math.max(minValue, Math.min(maxValue, numberValue));
}

// 进度条颜色：必须对齐千星沙箱编辑器“颜色枚举”能力，避免导出不可表达的颜色。
// 已确认：默认(绿色)/红色/黄色/蓝色/白色；不存在紫色/橙色。
// 注意：这里的 value 必须使用写回链路认可的“统一调色板 hex”，与写回端完全一致。
export var PROGRESS_BAR_COLOR_OPTIONS = [
    { name: "white", label: "白色 (White)", value: "#E2DBCE", rgb: { r: 226, g: 219, b: 206 } },
    { name: "green", label: "默认绿色 (Default Green)", value: "#92CD21", rgb: { r: 146, g: 205, b: 33 } },
    { name: "yellow", label: "黄色 (Yellow)", value: "#F3C330", rgb: { r: 243, g: 195, b: 48 } },
    { name: "blue", label: "蓝色 (Blue)", value: "#36F3F3", rgb: { r: 54, g: 243, b: 243 } },
    { name: "red", label: "红色 (Red)", value: "#F47B7B", rgb: { r: 244, g: 123, b: 123 } }
];

function colorDistanceSq(leftRgb, rightRgb) {
    var dr = (leftRgb.r - rightRgb.r);
    var dg = (leftRgb.g - rightRgb.g);
    var db = (leftRgb.b - rightRgb.b);
    return dr * dr + dg * dg + db * db;
}

function rgbToHueDegrees(rgb) {
    if (!rgb) {
        return null;
    }
    var r = clampNumber(rgb.r, 0, 255) / 255;
    var g = clampNumber(rgb.g, 0, 255) / 255;
    var b = clampNumber(rgb.b, 0, 255) / 255;
    var max = Math.max(r, g, b);
    var min = Math.min(r, g, b);
    var delta = max - min;
    if (delta <= 1e-9) {
        return 0;
    }
    var hue = 0;
    if (max === r) {
        hue = 60 * (((g - b) / delta) % 6);
    } else if (max === g) {
        hue = 60 * (((b - r) / delta) + 2);
    } else {
        hue = 60 * (((r - g) / delta) + 4);
    }
    if (!isFinite(hue)) {
        return 0;
    }
    if (hue < 0) {
        hue += 360;
    }
    return hue;
}

function rgbToSaturation(rgb) {
    if (!rgb) {
        return 0;
    }
    var r = clampNumber(rgb.r, 0, 255) / 255;
    var g = clampNumber(rgb.g, 0, 255) / 255;
    var b = clampNumber(rgb.b, 0, 255) / 255;
    var max = Math.max(r, g, b);
    var min = Math.min(r, g, b);
    var delta = max - min;
    if (max <= 1e-9) {
        return 0;
    }
    return delta / max;
}

function pickPaletteColorByHue(rgb) {
    var saturation = rgbToSaturation(rgb);
    if (saturation < 0.12) {
        return PROGRESS_BAR_COLOR_OPTIONS[0]; // white
    }
    var hue = rgbToHueDegrees(rgb);
    // Hue buckets tuned for “语义更像”：偏红→红，偏黄/金→黄，偏绿→绿，其余→蓝
    if (hue < 25 || hue >= 335) {
        return PROGRESS_BAR_COLOR_OPTIONS[4]; // red
    }
    if (hue < 70) {
        return PROGRESS_BAR_COLOR_OPTIONS[2]; // yellow
    }
    if (hue < 170) {
        return PROGRESS_BAR_COLOR_OPTIONS[1]; // green
    }
    return PROGRESS_BAR_COLOR_OPTIONS[3]; // blue
}

export function mapToNearestProgressBarColor(colorText, warningList, contextLabel) {
    var rgba = cssColorToRgba(colorText || "");
    if (!rgba) {
        // fallback: 解析失败时，使用默认绿色（避免写回端报错）
        return { color: PROGRESS_BAR_COLOR_OPTIONS[1].value, mappedFrom: String(colorText || ""), distanceSq: null };
    }
    var rgb = { r: rgba.r, g: rgba.g, b: rgba.b };
    var best = pickPaletteColorByHue(rgb);
    var bestDist = colorDistanceSq(best.rgb, rgb);
    // 粗略阈值：当颜色非常“不像任何预设色”时，提示用户
    if (warningList && bestDist > 30_000) {
        warningList.push("颜色映射偏差较大: " + (contextLabel ? ("[" + contextLabel + "] ") : "") + String(colorText || "") + " -> " + best.value);
    }
    return { color: best.value, mappedFrom: String(colorText || ""), distanceSq: bestDist };
}

export function detectProgressBarShapeForRect(rect, source) {
    if (!rect) {
        return "横向";
    }
    var w = Number(rect.width || 0);
    var h = Number(rect.height || 0);
    if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
        return "横向";
    }

    // 尝试识别“圆形/圆角”：仅在“明确声明为进度条语义”时才输出圆环。
    //
    // 背景：
    // - Workbench 会用“进度条控件”承载大量纯视觉矩形/圆角矩形（底色/边框/阴影等）；
    // - 但游戏侧“圆环进度条”是带洞的环形，不适合拿来表达“实心圆按钮/徽章”等装饰；
    // - 因此：圆环必须显式声明（data-ui-role="progressbar" 或提供 data-progress-*-var 绑定），否则保持横/纵向。
    var attrs0 = (source && source.attributes) ? source.attributes : null;
    var uiRole0 = attrs0 && attrs0.dataUiRole ? String(attrs0.dataUiRole || "").trim().toLowerCase() : "";
    var isExplicitProgressbar = uiRole0 === "progressbar";
    var hasProgressBinding = !!(
        (attrs0 && attrs0.dataProgressCurrentVar) ||
        (attrs0 && attrs0.dataProgressMinVar) ||
        (attrs0 && attrs0.dataProgressMaxVar)
    );
    var allowRing = isExplicitProgressbar || hasProgressBinding;

    var borderRadiusText = "";
    if (source && source.styleHints && source.styleHints.borderRadius) {
        borderRadiusText = String(source.styleHints.borderRadius || "");
    }
    if (allowRing && borderRadiusText) {
        if (borderRadiusText.indexOf("%") >= 0) {
            var percentNumber = Number.parseFloat(borderRadiusText);
            if (isFinite(percentNumber) && percentNumber >= 45) {
                return "圆环";
            }
        }
        var radiusPx = parsePxNumber(borderRadiusText.split(/\s+/)[0]);
        var minSide = Math.min(w, h);
        if (radiusPx !== null && isFinite(radiusPx) && minSide > 0 && radiusPx >= minSide * 0.45) {
            return "圆环";
        }
    }

    if (h > w * 1.35) {
        return "纵向";
    }
    return "横向";
}

export function normalizeTextAlignment(layer) {
    // 显式覆盖（优先级最高）：
    // - HTML 元素可声明 data-ui-text-align / data-ui-text-valign（由 dom_extract 采集到 layer.source.attributes）
    // - 目的：让作者能“显式定义 TextBox 的对齐方式”，避免依赖 computed style 推断而在扁平化后漂移。
    var src = layer && layer.source ? layer.source : null;
    var attrs = (src && src.attributes) ? src.attributes : null;
    var explicitH = attrs && attrs.dataUiTextAlign ? String(attrs.dataUiTextAlign || "").trim().toLowerCase() : "";
    var explicitV = attrs && attrs.dataUiTextValign ? String(attrs.dataUiTextValign || "").trim().toLowerCase() : "";

    function _mapH(v) {
        var x = String(v || "").trim().toLowerCase();
        if (!x) return null;
        if (x === "left" || x === "start" || x === "flex-start" || x === "左" || x === "左侧") return "左侧对齐";
        if (x === "center" || x === "middle" || x === "centered" || x === "中" || x === "居中") return "水平居中";
        if (x === "right" || x === "end" || x === "flex-end" || x === "右" || x === "右侧") return "右侧对齐";
        return null;
    }
    function _mapV(v) {
        var x = String(v || "").trim().toLowerCase();
        if (!x) return null;
        if (x === "top" || x === "start" || x === "flex-start" || x === "上" || x === "顶部") return "顶部对齐";
        if (x === "center" || x === "middle" || x === "居中" || x === "中" || x === "垂直居中") return "垂直居中";
        if (x === "bottom" || x === "end" || x === "flex-end" || x === "下" || x === "底部") return "底部对齐";
        return null;
    }

    var explicitMappedH = _mapH(explicitH);
    var explicitMappedV = _mapV(explicitV);

    var textAlign = layer && layer.textAlign ? String(layer.textAlign || "") : "";
    var justify = layer && layer.justifyContent ? String(layer.justifyContent || "") : "";
    var alignItems = layer && layer.alignItems ? String(layer.alignItems || "") : "";

    // 新规则：所有文本默认上下左右居中。
    // - 若作者需要非居中，必须显式声明 data-ui-text-align / data-ui-text-valign 覆盖。
    // - 保留 computed style 读取仅用于调试与兼容（但默认值不再从 CSS 推断）。
    var alignmentH = "水平居中";
    var alignmentV = "垂直居中";

    return {
        alignment_h: explicitMappedH ? explicitMappedH : alignmentH,
        alignment_v: explicitMappedV ? explicitMappedV : alignmentV
    };
}

