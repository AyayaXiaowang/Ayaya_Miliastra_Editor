import * as preview from "../../preview/index.js";
import { buildStableHtmlComponentKey, buildStableUiKey } from "../keys.js";
import { applyUiStateMetaToPayload } from "../ui_state.js";
import { inferInitialVisibleFromSource } from "./visibility.js";
import { ALLOWED_GAME_FONT_SIZES, SMALL_TEXT_DARK_LUMINANCE_WARN_LT, SMALL_TEXT_FONT_SIZE_WARN_LT, clampNumber, computeRelativeLuminanceFromCssColor, normalizeTextAlignment, parsePxNumber, pickNearestAllowedGameFontSize, pickUniformTextFontSizeOverride, shouldWarnSmallTextDarkColor } from "../color_font.js";

export function buildTextBoxWidget(widgetId, widgetName, rect, zIndex, text, layer, warningList, exportOptions, uiKeyKind, backgroundColorName) {
    var rawFontSize = layer && layer.fontSize ? String(layer.fontSize || "") : "";
    var fontSizeNumber = parsePxNumber(rawFontSize);
    if (fontSizeNumber === null) {
        fontSizeNumber = 16;
    }
    // 关键：当上层容器使用 transform: scale(...)（典型：--ui-scale）做响应式缩放时，
    // rect（getBoundingClientRect）已包含缩放，但 computed font-size 不会。
    // 导出到 GIL 必须补偿字号，否则会出现“盒子小、字号大”导致文字溢出/叠字（尤其在 1600x900）。
    var effectiveScale = (function () {
        var s = layer ? Number(layer.effectiveScale || 1) : 1;
        if (!isFinite(s) || s <= 0) {
            return 1;
        }
        return Math.max(0.05, Math.min(8.0, s));
    })();
    var fontSizeEffectiveNumber = Number(fontSizeNumber) * Number(effectiveScale);
    if (!isFinite(fontSizeEffectiveNumber) || fontSizeEffectiveNumber <= 0) {
        fontSizeEffectiveNumber = fontSizeNumber;
    }
    var fontSizeOriginalInt = Math.max(1, Math.round(fontSizeEffectiveNumber));

    // 关键规则（来自需求）：
    // - 默认：字号必须吸附到“游戏合规字号白名单”（不合规 -> 最近值）
    // - 例外：如果该文本在 4 个分辨率下字号完全一致，则允许用富文本 `<size=XX>` 精确表达字号，
    //         此时 **不限制 XX 必须来自白名单**（像 color 一样，直接写在 text_content 里）。
    var uniformOverrideRawInt = pickUniformTextFontSizeOverride(layer, exportOptions);
    var uniformOverrideInt = (uniformOverrideRawInt !== null) ? Math.max(1, Math.round(Number(uniformOverrideRawInt) * Number(effectiveScale))) : null;
    var gameFontSizeInt = uniformOverrideInt !== null ? uniformOverrideInt : pickNearestAllowedGameFontSize(fontSizeOriginalInt);
    var shouldUseRichTextSize = (uniformOverrideInt !== null) ? true : (gameFontSizeInt > 72);

    var _allowedGameFontSizeSet = new Set(ALLOWED_GAME_FONT_SIZES.map(function (x) { return Number(x); }));
    if (warningList) {
        if (uniformOverrideInt !== null) {
            if (!_allowedGameFontSizeSet.has(uniformOverrideInt)) {
                warningList.push("字号不在游戏白名单内，但该文本在 4 分辨率字号一致，已改用富文本 <size=" + String(uniformOverrideInt) + "> 精确表达：[" + widgetName + "] " + rawFontSize + " -> " + String(uniformOverrideInt));
            }
        } else {
            if (!_allowedGameFontSizeSet.has(fontSizeOriginalInt)) {
                warningList.push("字号不在游戏白名单内，已自动取最近值: [" + widgetName + "] " + rawFontSize + " -> " + String(gameFontSizeInt) + "（允许值：" + ALLOWED_GAME_FONT_SIZES.join(",") + "）");
            }
        }
    }
    var alignInfo = normalizeTextAlignment(layer);

    var backgroundColorPreset = String(backgroundColorName || "透明").trim() || "透明";

    // 文本颜色/字号：用富文本写在 text_content 里（对齐编辑器支持的 `<color>` / `<size>` 语义）。
    var src0 = (layer && layer.source) ? layer.source : null;
    var attrsTemplate = (src0 && src0.attributes) ? src0.attributes : null;
    var overrideText = attrsTemplate ? String(attrsTemplate.dataUiText || "") : "";
    // 关键：允许把“网页用于排版测量的短示例文本”和“写回到游戏的占位符长文本”拆开。
    // - 若声明了 data-ui-text，则导出使用它（可写 {{lv.xxx}}/{1:lv.xxx} 等）
    // - 否则退回使用网页当前的文本内容
    var richText = (overrideText && overrideText.trim()) ? overrideText : String(text || "");
    if (!String(richText || "").trim()) {
        richText = "";
    }
    var lowerText = richText.toLowerCase();
    var hasColorTag = lowerText.indexOf("<color") >= 0 || lowerText.indexOf("</color>") >= 0;
    var hasSizeTag = lowerText.indexOf("<size") >= 0 || lowerText.indexOf("</size>") >= 0;

    if (richText && !hasColorTag) {
        var colorHex = preview.formatColorTextAsHex(layer && layer.color ? String(layer.color || "") : "");
        if (colorHex) {
            if (warningList) {
                var fontSizeForWarning = uniformOverrideInt !== null ? uniformOverrideInt : gameFontSizeInt;
                if (shouldWarnSmallTextDarkColor(fontSizeForWarning, colorHex)) {
                    var lum = computeRelativeLuminanceFromCssColor(colorHex);
                    warningList.push(
                        "小字号文本 + 暗色可能被引擎灰色描边“吃掉/发糊”：[" + widgetName + "] size=" + String(fontSizeForWarning) + " color=" + String(colorHex) +
                        "（相对亮度≈" + (lum === null ? "?" : String(Math.round(lum * 100) / 100)) + " < " + String(SMALL_TEXT_DARK_LUMINANCE_WARN_LT) + "）。" +
                        "建议：提高字号到 ≥" + String(SMALL_TEXT_FONT_SIZE_WARN_LT) + "，或改用更亮的颜色。"
                    );
                }
            }
            richText = "<color=" + String(colorHex) + ">" + richText + "</color>";
        }
    }
    if (richText && shouldUseRichTextSize && !hasSizeTag) {
        // 超出编辑器滑条时使用富文本 size；或（例外）4 分辨率字号一致时用富文本精确表达。
        richText = "<size=" + String(gameFontSizeInt) + ">" + richText + "</size>";
    }

    // ---------------------------------------------------------------------
    // 尺寸兜底（关键）：避免“短文本（尤其是数字）在导出到 GIL 后 TextBox 太小而被引擎裁切/不显示”
    //
    // 背景：
    // - 扁平化提取的文字层 rect 往往是“紧包围盒”（字形宽高非常小）；
    // - 游戏侧 TextBox 渲染会有描边/内边距等额外占用，极端情况下会把文字吃掉。
    //
    // 策略：
    // - 对“很窄/很矮”的文本框做最小宽高兜底；
    // - 兜底值随字号变化，但保持保守，尽量不影响正常大文本布局。
    var rawWidth = Number(rect.width || 0);
    var rawHeight = Number(rect.height || 0);
    var safeWidth = rawWidth;
    var safeHeight = rawHeight;

    // 用“去标签后的可见文本”做启发式判断（避免把 <color>/<size> 算进长度）
    var visibleText = String((overrideText && overrideText.trim()) ? overrideText : String(text || ""));
    visibleText = visibleText.replace(/<[^>]+>/g, "").trim();
    var isDigitsOnly = /^[0-9]+$/.test(visibleText);
    var isVerySmallBox = (rawWidth > 0 && rawWidth < 36) || (rawHeight > 0 && rawHeight < 18);
    var isVeryShortText = visibleText.length > 0 && visibleText.length <= 2;

    if ((isDigitsOnly && isVerySmallBox) || isVeryShortText) {
        // 最小宽高：按字号给一个“至少能容纳 2 位数字 + 描边”的保守值
        var minW = Math.max(44, Math.round(gameFontSizeInt * 2.4));
        var minH = Math.max(22, Math.round(gameFontSizeInt * 1.25));
        safeWidth = Math.max(rawWidth, minW);
        safeHeight = Math.max(rawHeight, minH);
    }

    var initialVisible = inferInitialVisibleFromSource(src0, true);
    var dataUiSaveTemplate = attrsTemplate ? (attrsTemplate.dataUiSaveTemplate || attrsTemplate.componentOwnerDataUiSaveTemplate || null) : null;
    return applyUiStateMetaToPayload({
        ui_key: buildStableUiKey(src0, uiKeyKind || "textbox"),
        __html_component_key: buildStableHtmlComponentKey(src0),
        __ui_custom_template_name: (dataUiSaveTemplate ? String(dataUiSaveTemplate || "").trim() : ""),
        widget_id: widgetId,
        widget_type: "文本框",
        widget_name: widgetName,
        position: [Number(rect.left || 0), Number(rect.top || 0)],
        size: [Number(safeWidth || 0), Number(safeHeight || 0)],
        initial_visible: initialVisible,
        layer_index: Number.isFinite(zIndex) ? Math.trunc(zIndex) : 0,
        is_builtin: false,
        settings: {
            background_color: backgroundColorPreset,
            // 说明：编辑器滑条最大通常为 72；当需要更大字号时，用富文本 <size=...> 表达。
            font_size: Math.round(clampNumber(gameFontSizeInt, 8, 72)),
            text_content: richText,
            alignment_h: alignInfo.alignment_h,
            alignment_v: alignInfo.alignment_v
        }
    }, src0);
}

