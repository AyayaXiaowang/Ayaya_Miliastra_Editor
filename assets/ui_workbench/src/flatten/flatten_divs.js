import { PALETTE_SHADE_OVERLAY_RGBA } from "../config.js";
import { escapeHtmlText } from "../utils.js";
import { collectGameCutoutRects as _collectGameCutoutRects, filterCutoutsForElement as _filterCutoutsForElement, isGameCutoutElementInfo as _isGameCutoutElementInfo, subtractRectByCutouts as _subtractRectByCutouts } from "./internal/cutouts.js";
import { buildDimSurroundingRectsForHighlightArea as _buildDimSurroundingRectsForHighlightArea, collectHighlightDisplayAreaInfos as _collectHighlightDisplayAreaInfos, isHighlightDisplayAreaElementInfo as _isHighlightDisplayAreaElementInfo, normalizeHighlightOverlayColorFromAlpha as _normalizeHighlightOverlayColorFromAlpha } from "./internal/highlight_areas.js";
import { pruneFullyOccludedGroups as _pruneFullyOccludedGroups } from "./internal/occlusion.js";
import { mapRectFillColorForPalette, isTransparentColor } from "./colors.js";
import { parseBoxShadow, parseTextShadow } from "./shadows.js";
import { parseBorder, collectBorderColors } from "./borders.js";
import { computeExpandedTextRect, computeExpandedTextHitRect, normalizeFontSizeForFlatText } from "./text_layout.js";
import { buildFlattenedGroupDebugOverlayHtml } from "./group_debug_overlay.js";

// 扁平化策略：无视所有 border 的“可视化输出”，但仍按 border 宽度缩小 innerRect。
// 需求：
// - 对类似 `border: var(--border-width) solid var(--c-ink);` 的写法不再做“复制一个更大的矩形来表达边框”的转化（不输出 border 层）。
// - 但控件内容区域（element/text）应使用“去掉边框后的大小”（innerRect = borderBox - borderWidths）。
// 注意：边框转化代码暂时保留（便于未来回退/对照），但默认不再执行。
var FLATTEN_IGNORE_ALL_BORDERS = true;

function _pickUniformBorderOutlineStyle(borders, borderTopWidth, borderRightWidth, borderBottomWidth, borderLeftWidth) {
    // 目标：扁平化后仍“显示边框”，但不单独拆成 border 层。
    // 方案：仅对“统一边框（四边同宽同色）”用 outline 模拟：
    // - outline 不占布局，能画在元素 box 外侧；
    // - 本文件的 element rect 使用 innerRect（去掉边框后的内容区域），outline 恰好补回 borderBox 的视觉边框。
    if (!FLATTEN_IGNORE_ALL_BORDERS) {
        return null;
    }
    if (!borders) {
        return null;
    }
    var hasAnyBorder = !!(borders.top || borders.right || borders.bottom || borders.left);
    if (!hasAnyBorder) {
        return null;
    }
    var wTop = Number(borderTopWidth || 0);
    var wRight = Number(borderRightWidth || 0);
    var wBottom = Number(borderBottomWidth || 0);
    var wLeft = Number(borderLeftWidth || 0);
    if (!isFinite(wTop) || !isFinite(wRight) || !isFinite(wBottom) || !isFinite(wLeft)) {
        return null;
    }
    if (!(wTop > 0 && Math.abs(wTop - wRight) <= 1e-6 && Math.abs(wTop - wBottom) <= 1e-6 && Math.abs(wTop - wLeft) <= 1e-6)) {
        return null;
    }
    var colorInfo = collectBorderColors(borders);
    if (!colorInfo || !colorInfo.firstColor || colorInfo.distinctCount !== 1) {
        return null;
    }
    var mapped = mapRectFillColorForPalette(String(colorInfo.firstColor || ""), { diagnostics: null, target: null, context: "border_outline" });
    var colorText = (mapped && mapped.colorText) ? String(mapped.colorText || "") : String(colorInfo.firstColor || "");
    colorText = String(colorText || "").trim();
    if (!colorText) {
        return null;
    }
    return {
        width: Math.max(0, wTop),
        color: colorText
    };
}

function _normalizeTextContent(text) {
    var raw = String(text || "");
    if (!raw) {
        return "";
    }
    // 仅做 whitespace 归一化：ICON/emoji 的“是否允许/如何导出”为上层导出规则处理
    return raw.replace(/\s+/g, " ").trim();
}

function _resolveEffectiveScaleFromStyles(styles) {
    var raw = styles ? Number(styles.effectiveScale || 1) : 1;
    if (!isFinite(raw) || raw <= 0) {
        return 1;
    }
    return Math.max(0.05, Math.min(8.0, raw));
}

function _scalePxText(pxText, scale) {
    var s = Number(scale);
    if (!isFinite(s) || s <= 0) {
        s = 1;
    }
    if (Math.abs(s - 1) <= 1e-6) {
        return String(pxText || "");
    }
    var raw = String(pxText || "").trim().toLowerCase();
    if (!raw) {
        return raw;
    }
    if (raw.endsWith("px")) {
        raw = raw.slice(0, -2).trim();
    }
    var n = Number.parseFloat(raw);
    if (!isFinite(n) || n <= 0) {
        return String(pxText || "");
    }
    return String(n * s) + "px";
}

function _scaleLineHeightText(lineHeightText, scale) {
    var t = String(lineHeightText || "").trim();
    if (!t || t === "normal") {
        return t;
    }
    var lowered = t.toLowerCase();
    if (lowered.endsWith("px")) {
        return _scalePxText(lowered, scale);
    }
    return t;
}

function _buildUiStateDataAttrs(elementInfo) {
    var attrs = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
    if (!attrs) {
        return "";
    }
    var group = String(attrs.dataUiStateGroup || "").trim();
    if (!group) {
        return "";
    }
    var state = String(attrs.dataUiState || "").trim();
    var isDefault = String(attrs.dataUiStateDefault || "").trim();
    // 仅用于预览侧“状态切换/筛选”（例如 ui_app_ui_preview 的下拉切换）。
    // 必须做 HTML 转义，避免属性值包含引号导致注入。
    return (
        ' data-ui-state-group="' + escapeHtmlText(group) + '"' +
        ' data-ui-state="' + escapeHtmlText(state) + '"' +
        ' data-ui-state-default="' + (isDefault === "1" ? "1" : "0") + '"'
    );
}

function _buildUiTextDataAttrs(elementInfo) {
    var attrs = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
    if (!attrs) {
        return "";
    }
    var raw = String(attrs.dataUiText || "").trim();
    if (!raw) {
        return "";
    }
    // 预览/调试用：把“写回到游戏的文本占位符”透传到扁平层文字节点上，
    // 以便预览页在不切换“扁平/原稿”模式的情况下做“示例文本 ↔ 占位符”切换。
    return ' data-ui-text="' + escapeHtmlText(raw) + '"';
}

function _normalizeExplicitTextAlignToken(v) {
    var s = String(v || "").trim().toLowerCase();
    if (!s) {
        return "";
    }
    if (s === "start") return "left";
    if (s === "end") return "right";
    return s;
}

function _resolveExplicitTextAlignOverrides(elementInfo) {
    // 与 ui_export/color_font.js 的显式覆盖口径一致：
    // - data-ui-text-align / data-ui-text-align-h: left|center|right
    // - data-ui-text-valign / data-ui-text-align-v: top|middle|bottom
    var attrs = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
    if (!attrs) {
        return { h: "center", v: "middle" };
    }
    var h = _normalizeExplicitTextAlignToken(attrs.dataUiTextAlign || "");
    var v = _normalizeExplicitTextAlignToken(attrs.dataUiTextValign || "");
    if (!h) h = "center";
    if (!v) v = "middle";
    if (v === "center") {
        v = "middle";
    }
    return { h: h, v: v };
}

function _applyExplicitTextAlignToFlex(h, v, fallbackTextAlign, fallbackJustify, fallbackAlignItems) {
    var hh = _normalizeExplicitTextAlignToken(h);
    var vv = _normalizeExplicitTextAlignToken(v);
    var textAlignValue = String(fallbackTextAlign || "start");
    var justifyContentValue = String(fallbackJustify || "flex-start");
    var alignItemsValue = String(fallbackAlignItems || "flex-start");

    if (hh === "left") {
        textAlignValue = "left";
        justifyContentValue = "flex-start";
    } else if (hh === "center") {
        textAlignValue = "center";
        justifyContentValue = "center";
    } else if (hh === "right") {
        textAlignValue = "right";
        justifyContentValue = "flex-end";
    }

    if (vv === "top") {
        alignItemsValue = "flex-start";
    } else if (vv === "middle") {
        alignItemsValue = "center";
    } else if (vv === "bottom") {
        alignItemsValue = "flex-end";
    }

    return { textAlignValue: textAlignValue, justifyContentValue: justifyContentValue, alignItemsValue: alignItemsValue };
}

function _buildIssueTargetForElementInfo(elementInfo, elementIndex) {
    var attrs = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
    var uiKey = attrs ? (attrs.componentOwnerDataUiKey || attrs.dataUiKey || null) : null;
    var id = elementInfo ? (elementInfo.id || (attrs ? attrs.componentOwnerId : null) || null) : null;
    return {
        id: id ? String(id || "") : "",
        ui_key: uiKey ? String(uiKey || "") : "",
        element_index: elementIndex
    };
}

function _warnUnsupportedVisualFeature(diagnostics, code, message, target, evidence, suggestion) {
    if (!diagnostics || !diagnostics.warn) {
        return;
    }
    diagnostics.warn({
        code: code,
        message: message,
        target: target,
        evidence: evidence || null,
        fix: { kind: "downgrade", suggestion: suggestion || "该效果会在导出/写回时降级或忽略。" }
    });
}

function _isButtonLikeElementAttrs(attrs) {
    // 与 layer_data.js / ui_export/widgets/button_semantics.js 保持一致：只认“显式语义标注”。
    if (!attrs) {
        return false;
    }
    var uiRole = String(attrs.dataUiRole || "").trim().toLowerCase();
    if (uiRole === "button") {
        return true;
    }
    var ariaRole = String(attrs.role || "").trim().toLowerCase();
    if (ariaRole === "button") {
        return true;
    }
    var interactKey = String(attrs.dataUiInteractKey || "").trim();
    if (interactKey) {
        return true;
    }
    var uiAction = String(attrs.dataUiAction || "").trim();
    if (uiAction) {
        return true;
    }
    return false;
}

function _parseFlatZBiasFromElementInfo(elementInfo) {
    var attrs = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
    var raw = attrs ? String(attrs.dataFlatZBias || "").trim() : "";
    if (!raw) {
        return 0;
    }
    var n = Number.parseInt(raw, 10);
    if (!isFinite(n)) {
        return 0;
    }
    // 防止作者误填极端值导致溢出/排序异常
    return Math.max(-5_000_000, Math.min(5_000_000, n));
}

export function generateFlattenedDivs(elementsData, sizeKey, opts) {
    var o = opts || {};
    var diagnostics = o.diagnostics || null;

    var elements = elementsData.elements || [];
    var bodySize = elementsData && elementsData.bodySize ? elementsData.bodySize : { width: 0, height: 0 };
    var gameCutoutRects = _collectGameCutoutRects(elements);
    var highlightAreas = _collectHighlightDisplayAreaInfos(elements);
    var shadowDivList = [];
    var borderDivList = [];
    var elementDivList = [];
    var textDivList = [];
    var _pushSeq = 0;

    var elementIndex = 0;

    for (var index = 0; index < elements.length; index++) {
        var elementInfo = elements[index];
        var target = _buildIssueTargetForElementInfo(elementInfo, elementIndex);
        var uiStateDataAttrs = _buildUiStateDataAttrs(elementInfo);
        var uiTextDataAttrs = _buildUiTextDataAttrs(elementInfo);
        var rect = elementInfo.rect;
        var styles = elementInfo.styles || {};
        var tagName = elementInfo.tagName;
        var padding = elementInfo.padding || { top: 0, right: 0, bottom: 0, left: 0 };
        var shouldApplyCutouts = !elementInfo.inGameCutout;
        var effectiveCutouts = shouldApplyCutouts ? _filterCutoutsForElement(elementInfo, index, gameCutoutRects) : [];

        if (tagName === "html" || tagName === "body") {
            continue;
        }
        if (_isGameCutoutElementInfo(elementInfo)) {
            elementIndex += 1;
            continue;
        }
        if (_isHighlightDisplayAreaElementInfo(elementInfo)) {
            // 高亮展示区域（Dim Surroundings）：
            // - 元素本体不输出任何扁平层；
            // - 生成 4 个包围该区域的“压暗遮罩矩形”（shadow layer），用于让周围暗下来达到高亮效果。
            //
            // 叠放语义：
            // - 遮罩层的 z-index 由该 marker 的 elementIndex 决定；
            // - 作者可通过把 marker 放到 DOM 更后面（或放到特定 data-ui-state-* 容器内）控制其覆盖范围与显隐。
            var markerRect = rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : null;
            var overlayColor = (function () {
                // collectHighlightDisplayAreaInfos 以 sourceElementIndex 关联；这里按当前 index 匹配。
                for (var hi = 0; hi < highlightAreas.length; hi++) {
                    var info = highlightAreas[hi];
                    if (info && Number(info.sourceElementIndex) === Number(index)) {
                        return _normalizeHighlightOverlayColorFromAlpha(info.overlayAlpha);
                    }
                }
                return _normalizeHighlightOverlayColorFromAlpha(0.45);
            })();
            var overlayRects = _buildDimSurroundingRectsForHighlightArea(markerRect, bodySize);
            var overlayZIndex = elementIndex * 10 + _parseFlatZBiasFromElementInfo(elementInfo) + 9; // 覆盖在该 marker 之前的内容之上（含文本）
            for (var oi = 0; oi < overlayRects.length; oi++) {
                var r0 = overlayRects[oi];
                var safeW = Math.max(0, Number(r0.width || 0));
                var safeH = Math.max(0, Number(r0.height || 0));
                if (!isFinite(safeW) || !isFinite(safeH) || safeW <= 0.001 || safeH <= 0.001) {
                    continue;
                }
                var overlayStyleText = [
                    "position: absolute",
                    "left: " + Number(r0.left || 0).toFixed(2) + "px",
                    "top: " + Number(r0.top || 0).toFixed(2) + "px",
                    "width: " + safeW.toFixed(2) + "px",
                    "height: " + safeH.toFixed(2) + "px",
                    "background-color: " + overlayColor,
                    "z-index: " + overlayZIndex
                ].join("; ") + ";";
                shadowDivList.push({
                    seq: _pushSeq++,
                    z: overlayZIndex,
                    kind: "shadow",
                    groupKey: "highlight_area_" + String(elementIndex),
                    rect: { left: Number(r0.left || 0), top: Number(r0.top || 0), width: safeW, height: safeH },
                    source: elementInfo,
                    html:
                        '<div class="flat-shadow debug-target size-' + sizeKey + '"' +
                        uiStateDataAttrs +
                        ' style="' + overlayStyleText + '"' +
                        ' data-debug-label="highlight-dim-' + elementIndex + "-" + oi + '"></div>'
                });
            }
            elementIndex += 1;
            continue;
        }

        var left = rect.left;
        var top = rect.top;
        var width = rect.width;
        var height = rect.height;

        var borderTopWidth = Number(String(styles.borderTopWidth || "0px").replace("px", "")) || 0;
        var borderRightWidth = Number(String(styles.borderRightWidth || "0px").replace("px", "")) || 0;
        var borderBottomWidth = Number(String(styles.borderBottomWidth || "0px").replace("px", "")) || 0;
        var borderLeftWidth = Number(String(styles.borderLeftWidth || "0px").replace("px", "")) || 0;

        var bgImage = String(styles.backgroundImage || "").trim();
        var rawBackgroundColor = styles.backgroundColor || "transparent";
        // 降级策略（关键）：若元素主要靠 background-image（渐变/贴图）呈现，但 background-color 是透明，
        // 直接丢弃会导致“只剩文字层”，用户会误以为导出失败。
        // 因此为该类元素补一个可写回的“兜底底色”，同时记录 warning。
        if (isTransparentColor(rawBackgroundColor) && bgImage && bgImage !== "none") {
            _warnUnsupportedVisualFeature(
                diagnostics,
                "DOWNGRADE.BACKGROUND_IMAGE_FALLBACK_FILL",
                "background-image 将被忽略；已自动补一个兜底底色以保留元素轮廓。",
                target,
                { backgroundImage: bgImage, fallbackColor: "#e2dbce" },
                "建议显式设置可写回的 background-color（调色板色），避免依赖渐变/图片。"
            );
            rawBackgroundColor = "#e2dbce";
        }

        var backgroundMapping = mapRectFillColorForPalette(rawBackgroundColor, { diagnostics: diagnostics, target: target, context: "background" });
        var backgroundColor = backgroundMapping.colorText || rawBackgroundColor;
        var shadeOverlayCountForBackground = Number(backgroundMapping.needsShadeOverlayCount || 0);
        if (!isFinite(shadeOverlayCountForBackground) || shadeOverlayCountForBackground < 0) {
            shadeOverlayCountForBackground = 0;
        }
        if (shadeOverlayCountForBackground === 0 && backgroundMapping.needsShadeOverlay) {
            shadeOverlayCountForBackground = 1;
        }
        var shadeOverlayRgbaForBackground = String(backgroundMapping.needsShadeOverlayRgba || "").trim();
        if (!shadeOverlayRgbaForBackground) {
            shadeOverlayRgbaForBackground = PALETTE_SHADE_OVERLAY_RGBA;
        }
        var isTransparentBackground = isTransparentColor(rawBackgroundColor);
        // 对“视觉是否为空”的判断：border 仍视为“可见要素”（即便不拆层，也需要在扁平化里显示边框）。
        var hasBorder =
            borderTopWidth > 0 ||
            borderRightWidth > 0 ||
            borderBottomWidth > 0 ||
            borderLeftWidth > 0;
        var hasShadow = (styles.boxShadow || "none") !== "none" && (styles.boxShadow || "") !== "";
        var rawTextContent = (elementInfo.textContent || "").trim();
        var normalizedTextContent = _normalizeTextContent(rawTextContent);
        // 允许“混合内容”（元素有子节点，但仍有直接文本节点）导出 directTextContent。
        var hasText = !!normalizedTextContent;

        if (isTransparentBackground && !hasBorder && !hasShadow && !hasText) {
            // 与 layer_data.js 保持一致：
            // 若元素具备显式按钮语义但“视觉为空”，补一个专用锚点层（button_anchor），
            // 以便预览侧/导出侧能做到 1:1 的 flat_layer_key 精确定位（避免列表点击靠 rect 猜）。
            var attrsForButton = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
            var tagLower = String(tagName || "").trim().toLowerCase();
            var isButtonTagWithUiKey = (
                tagLower === "button" &&
                attrsForButton &&
                String(attrsForButton.dataUiKey || "").trim() !== ""
            );
            var isButtonLike = _isButtonLikeElementAttrs(attrsForButton) || isButtonTagWithUiKey;
            if (isButtonLike) {
                // 与后续 elementBaseZIndex = elementIndex * 10 对齐；这里要避免依赖后续赋值顺序。
                var anchorZIndex = elementIndex * 10;
                var anchorStyleText = [
                    "position: absolute",
                    "left: " + left.toFixed(2) + "px",
                    "top: " + top.toFixed(2) + "px",
                    "width: " + Math.max(0, width).toFixed(2) + "px",
                    "height: " + Math.max(0, height).toFixed(2) + "px",
                    "background-color: transparent",
                    "border: none",
                    "box-shadow: none",
                    "pointer-events: none",
                    "z-index: " + anchorZIndex
                ].join("; ") + ";";
                elementDivList.push({
                    seq: _pushSeq++,
                    z: anchorZIndex,
                    kind: "button_anchor",
                    groupKey: "e" + String(elementIndex),
                    rect: { left: left, top: top, width: Math.max(0, width), height: Math.max(0, height) },
                    source: elementInfo,
                    html: '<div class="flat-button-anchor debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + anchorStyleText + '" data-debug-label="button-anchor-' + elementIndex + '"></div>'
                });
                elementIndex += 1;
                continue;
            }
            elementIndex += 1;
            continue;
        }

        // “自由发挥”允许出现的 CSS 特性：在写回链路不可表达时，这里会被忽略/降级，并输出结构化 warning。
        if (bgImage && bgImage !== "none") {
            _warnUnsupportedVisualFeature(
                diagnostics,
                "DOWNGRADE.BACKGROUND_IMAGE_IGNORED",
                "background-image 无法写回为矩形层底色，已忽略（仅保留 background-color）。",
                target,
                { backgroundImage: bgImage },
                "请用纯色 background-color 表达；如必须渐变，接受降级为纯色。"
            );
        }
        var opacity = Number(String(styles.opacity || "1").trim());
        if (isFinite(opacity) && Math.abs(opacity - 1) > 1e-6) {
            _warnUnsupportedVisualFeature(
                diagnostics,
                "DOWNGRADE.OPACITY_IGNORED",
                "opacity 无法稳定写回为 UI 层透明度，已忽略（将按不透明处理）。",
                target,
                { opacity: opacity },
                "尽量避免 opacity；需要半透明请用带 alpha 的 rgba()/#rrggbbaa（仍可能被量化）。"
            );
        }
        var transform = String(styles.transform || "").trim();
        if (transform && transform !== "none") {
            _warnUnsupportedVisualFeature(
                diagnostics,
                "DOWNGRADE.TRANSFORM_IGNORED",
                "transform（旋转/缩放/倾斜）无法写回，已忽略（将按未变换矩形处理）。",
                target,
                { transform: transform },
                "避免 transform；如要斜切/旋转装饰，建议改用位图资源或接受降级。"
            );
        }
        var borderRadiusText = String(styles.borderRadius || "").trim();
        if (borderRadiusText && borderRadiusText !== "0px" && borderRadiusText !== "0px 0px 0px 0px" && borderRadiusText !== "50%" && borderRadiusText !== "50% 50% 50% 50%") {
            _warnUnsupportedVisualFeature(
                diagnostics,
                "DOWNGRADE.BORDER_RADIUS_IGNORED",
                "border-radius 将被忽略（写回链路以矩形层为主）。",
                target,
                { borderRadius: borderRadiusText },
                "尽量使用 0 或 50%；否则接受圆角被降级为直角。"
            );
        }

        // 扁平化的层级必须尽可能贴近浏览器真实绘制顺序：
        var elementBaseZIndex = elementIndex * 10 + _parseFlatZBiasFromElementInfo(elementInfo);

        var boxShadowValue = styles.boxShadow || "";
        var shadowList = parseBoxShadow(boxShadowValue, { diagnostics: diagnostics, target: target, context: "box-shadow" });
        for (var shadowIndex = 0; shadowIndex < shadowList.length; shadowIndex++) {
            var shadow = shadowList[shadowIndex];
            var shadowExpansionRadius = shadow.spread + shadow.blur;
            var shadowLeft = left + shadow.offsetX - shadowExpansionRadius;
            var shadowTop = top + shadow.offsetY - shadowExpansionRadius;
            var shadowWidth = width + shadowExpansionRadius * 2;
            var shadowHeight = height + shadowExpansionRadius * 2;
            shadowWidth = Math.max(0, shadowWidth);
            shadowHeight = Math.max(0, shadowHeight);

            var shadowZIndex = elementBaseZIndex + 0;
            var shadowBaseRect = { left: shadowLeft, top: shadowTop, width: shadowWidth, height: shadowHeight };
            var shadowRects = shouldApplyCutouts ? _subtractRectByCutouts(shadowBaseRect, effectiveCutouts) : [shadowBaseRect];
            for (var shadowSegIndex = 0; shadowSegIndex < shadowRects.length; shadowSegIndex++) {
                var shadowRect = shadowRects[shadowSegIndex];
                var shadowStyleText = [
                    "position: absolute",
                    "left: " + shadowRect.left.toFixed(2) + "px",
                    "top: " + shadowRect.top.toFixed(2) + "px",
                    "width: " + Math.max(0, shadowRect.width).toFixed(2) + "px",
                    "height: " + Math.max(0, shadowRect.height).toFixed(2) + "px",
                    "background-color: " + shadow.color,
                    "z-index: " + shadowZIndex
                ].join("; ") + ";";
                shadowDivList.push({
                    seq: _pushSeq++,
                    z: shadowZIndex,
                    kind: "shadow",
                    groupKey: "e" + String(elementIndex),
                    rect: {
                        left: shadowRect.left,
                        top: shadowRect.top,
                        width: Math.max(0, shadowRect.width),
                        height: Math.max(0, shadowRect.height)
                    },
                    source: elementInfo,
                    html: '<div class="flat-shadow debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + shadowStyleText + '" data-debug-label="shadow-' + elementIndex + (shadowSegIndex > 0 ? ("-cutout-" + shadowSegIndex) : "") + '"></div>'
                });
            }
        }

        var borders = {
            top: parseBorder(styles.borderTop || ""),
            right: parseBorder(styles.borderRight || ""),
            bottom: parseBorder(styles.borderBottom || ""),
            left: parseBorder(styles.borderLeft || "")
        };
        var hasAnyBorder = !!(borders.top || borders.right || borders.bottom || borders.left);

        if (!FLATTEN_IGNORE_ALL_BORDERS && hasAnyBorder) {
            var borderZIndex = elementBaseZIndex + 2;

            // 边框优先以“一个更大的矩形”表达：把 border-box 作为底层色块，主体层（innerRect）覆盖中间，从而露出边框厚度。
            var borderColorInfo = collectBorderColors(borders);
            var canUseUnifiedBorder = !isTransparentBackground && borderColorInfo.firstColor && borderColorInfo.distinctCount === 1;

            if (canUseUnifiedBorder) {
                var unifiedBorderMapping = mapRectFillColorForPalette(borderColorInfo.firstColor || "", { diagnostics: diagnostics, target: target, context: "border" });
                var unifiedBorderColor = unifiedBorderMapping.colorText || (borderColorInfo.firstColor || "");
                var borderBaseRect = { left: left, top: top, width: Math.max(0, width), height: Math.max(0, height) };
                var borderRects = shouldApplyCutouts ? _subtractRectByCutouts(borderBaseRect, effectiveCutouts) : [borderBaseRect];
                for (var borderSegIndex = 0; borderSegIndex < borderRects.length; borderSegIndex++) {
                    var borderRect = borderRects[borderSegIndex];
                    var borderStyleText = [
                        "position: absolute",
                        "left: " + borderRect.left.toFixed(2) + "px",
                        "top: " + borderRect.top.toFixed(2) + "px",
                        "width: " + Math.max(0, borderRect.width).toFixed(2) + "px",
                        "height: " + Math.max(0, borderRect.height).toFixed(2) + "px",
                        "background-color: " + unifiedBorderColor,
                        "z-index: " + borderZIndex
                    ].join("; ") + ";";
                borderDivList.push({
                    seq: _pushSeq++,
                        z: borderZIndex,
                        kind: "border",
                        groupKey: "e" + String(elementIndex),
                        rect: {
                            left: borderRect.left,
                            top: borderRect.top,
                            width: Math.max(0, borderRect.width),
                            height: Math.max(0, borderRect.height)
                        },
                        source: elementInfo,
                        html: '<div class="flat-border debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + borderStyleText + '" data-debug-label="border-' + elementIndex + '-unified' + (borderSegIndex > 0 ? ("-cutout-" + borderSegIndex) : "") + '"></div>'
                    });
                }

                if (unifiedBorderMapping.needsShadeOverlay) {
                    var unifiedShadeZIndex = borderZIndex + 1;
                    for (var ubShadeIndex = 0; ubShadeIndex < borderRects.length; ubShadeIndex++) {
                        var ubShadeRect = borderRects[ubShadeIndex];
                        var shadeStyleText = [
                            "position: absolute",
                            "left: " + ubShadeRect.left.toFixed(2) + "px",
                            "top: " + ubShadeRect.top.toFixed(2) + "px",
                            "width: " + Math.max(0, ubShadeRect.width).toFixed(2) + "px",
                            "height: " + Math.max(0, ubShadeRect.height).toFixed(2) + "px",
                            "background-color: " + PALETTE_SHADE_OVERLAY_RGBA,
                            "z-index: " + unifiedShadeZIndex
                        ].join("; ") + ";";
                        shadowDivList.push({
                            seq: _pushSeq++,
                            z: unifiedShadeZIndex,
                            kind: "shadow",
                            groupKey: "e" + String(elementIndex),
                            rect: {
                                left: ubShadeRect.left,
                                top: ubShadeRect.top,
                                width: Math.max(0, ubShadeRect.width),
                                height: Math.max(0, ubShadeRect.height)
                            },
                            source: elementInfo,
                            html: '<div class="flat-shadow debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + shadeStyleText + '" data-debug-label="shade-border-' + elementIndex + '-unified' + (ubShadeIndex > 0 ? ("-cutout-" + ubShadeIndex) : "") + '"></div>'
                        });
                    }
                }
            } else {
                function pushBorderSegment(segmentLabel, segmentLeft, segmentTop, segmentWidth, segmentHeight, segmentColor) {
                    var safeWidth = Math.max(0, segmentWidth);
                    var safeHeight = Math.max(0, segmentHeight);
                    if (safeWidth <= 0.001 || safeHeight <= 0.001) {
                        return;
                    }
                    var segmentMapping = mapRectFillColorForPalette(segmentColor || "", { diagnostics: diagnostics, target: target, context: "border:" + segmentLabel });
                    var mappedSegmentColor = segmentMapping.colorText || segmentColor;
                    var segmentBaseRect = { left: segmentLeft, top: segmentTop, width: safeWidth, height: safeHeight };
                    var segmentRects = shouldApplyCutouts ? _subtractRectByCutouts(segmentBaseRect, effectiveCutouts) : [segmentBaseRect];
                    for (var segIndex = 0; segIndex < segmentRects.length; segIndex++) {
                        var segRect = segmentRects[segIndex];
                        var borderStyleText = [
                            "position: absolute",
                            "left: " + segRect.left.toFixed(2) + "px",
                            "top: " + segRect.top.toFixed(2) + "px",
                            "width: " + Math.max(0, segRect.width).toFixed(2) + "px",
                            "height: " + Math.max(0, segRect.height).toFixed(2) + "px",
                            "background-color: " + mappedSegmentColor,
                            "z-index: " + borderZIndex
                        ].join("; ") + ";";
                        borderDivList.push({
                            seq: _pushSeq++,
                            z: borderZIndex,
                            kind: "border",
                            groupKey: "e" + String(elementIndex),
                            rect: {
                                left: segRect.left,
                                top: segRect.top,
                                width: Math.max(0, segRect.width),
                                height: Math.max(0, segRect.height)
                            },
                            source: elementInfo,
                            html: '<div class="flat-border debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + borderStyleText + '" data-debug-label="border-' + elementIndex + "-" + segmentLabel + (segIndex > 0 ? ("-cutout-" + segIndex) : "") + '"></div>'
                        });
                    }

                    if (segmentMapping.needsShadeOverlay) {
                        var shadeZIndex = borderZIndex + 1;
                        for (var segShadeIndex = 0; segShadeIndex < segmentRects.length; segShadeIndex++) {
                            var segShadeRect = segmentRects[segShadeIndex];
                            var shadeStyleText = [
                                "position: absolute",
                                "left: " + segShadeRect.left.toFixed(2) + "px",
                                "top: " + segShadeRect.top.toFixed(2) + "px",
                                "width: " + Math.max(0, segShadeRect.width).toFixed(2) + "px",
                                "height: " + Math.max(0, segShadeRect.height).toFixed(2) + "px",
                                "background-color: " + PALETTE_SHADE_OVERLAY_RGBA,
                                "z-index: " + shadeZIndex
                            ].join("; ") + ";";
                            shadowDivList.push({
                                seq: _pushSeq++,
                                z: shadeZIndex,
                                kind: "shadow",
                                groupKey: "e" + String(elementIndex),
                                rect: {
                                    left: segShadeRect.left,
                                    top: segShadeRect.top,
                                    width: Math.max(0, segShadeRect.width),
                                    height: Math.max(0, segShadeRect.height)
                                },
                                source: elementInfo,
                                html: '<div class="flat-shadow debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + shadeStyleText + '" data-debug-label="shade-border-' + elementIndex + "-" + segmentLabel + (segShadeIndex > 0 ? ("-cutout-" + segShadeIndex) : "") + '"></div>'
                            });
                        }
                    }
                }

                if (borders.top && borders.top.width > 0) {
                    var topHeight = Math.min(borders.top.width, height);
                    pushBorderSegment("top", left, top, width, topHeight, borders.top.color);
                }
                if (borders.bottom && borders.bottom.width > 0) {
                    var bottomHeight = Math.min(borders.bottom.width, height);
                    pushBorderSegment("bottom", left, top + height - bottomHeight, width, bottomHeight, borders.bottom.color);
                }
                if (borders.left && borders.left.width > 0) {
                    var leftWidth = Math.min(borders.left.width, width);
                    pushBorderSegment("left", left, top, leftWidth, height, borders.left.color);
                }
                if (borders.right && borders.right.width > 0) {
                    var rightWidth = Math.min(borders.right.width, width);
                    pushBorderSegment("right", left + width - rightWidth, top, rightWidth, height, borders.right.color);
                }
            }
        }

        var innerLeft = left + borderLeftWidth;
        var innerTop = top + borderTopWidth;
        var innerWidth = Math.max(0, width - borderLeftWidth - borderRightWidth);
        var innerHeight = Math.max(0, height - borderTopWidth - borderBottomWidth);

        var originalClassName = elementInfo.className ? String(elementInfo.className) : "";
        var dataLabel = "";
        // 优先使用显式声明（更稳定、可读性更好）：
        // - data-ui-key：导出/写回/分组的主要稳定键
        // - data-debug-label：调试/定位辅助键
        // 再回退到 id / class（历史逻辑）。
        var attrs = elementInfo.attributes || null;
        var explicitUiKey = attrs ? String(attrs.dataUiKey || "").trim() : "";
        var explicitDbg = attrs ? String(attrs.dataDebugLabel || "").trim() : "";
        if (explicitUiKey) {
            dataLabel = explicitUiKey;
        } else if (explicitDbg) {
            dataLabel = explicitDbg;
        } else if (elementInfo.id) {
            dataLabel = elementInfo.id;
        } else if (originalClassName) {
            var classParts = originalClassName.split(/\s+/).filter(function (part) { return part.trim().length > 0; });
            for (var classIndex = 0; classIndex < classParts.length; classIndex++) {
                var className = classParts[classIndex];
                if (className !== "debug-target") {
                    dataLabel = className;
                    break;
                }
            }
        }
        // 文本层 debug-label 的“基底”（用于拼 text- / text-shadow- 前缀）：
        // - 若作者已经写成 text-xxx，则这里去掉 text-，避免生成 text-text-xxx
        // - 若作者写成 text-shadow-xxx，则去掉 text-shadow-，避免生成 text-shadow-text-shadow-xxx
        var textLabelBase = (function () {
            var s = String(dataLabel || "").trim();
            if (s.indexOf("text-shadow-") === 0) {
                s = s.slice(String("text-shadow-").length);
            }
            if (s.indexOf("text-") === 0) {
                s = s.slice(String("text-").length);
            }
            return s;
        })();

        // 边框“只显示不拆层”：对统一边框用 outline 模拟。
        // 注意：若存在 cutout 切分，则 elementRects 会是多个碎片；outline 会围绕每个碎片画边框。
        // 这在视觉上可能出现“碎片化边框”，但相比完全看不到边框更符合“仍要显示边框”的需求。
        var outlineBorder = null;
        outlineBorder = _pickUniformBorderOutlineStyle(borders, borderTopWidth, borderRightWidth, borderBottomWidth, borderLeftWidth);

        if (!isTransparentBackground || outlineBorder) {
            var elementZIndex = elementBaseZIndex + 5;
            var elementBaseRect = { left: innerLeft, top: innerTop, width: innerWidth, height: innerHeight };
            var elementRects = shouldApplyCutouts ? _subtractRectByCutouts(elementBaseRect, effectiveCutouts) : [elementBaseRect];
            for (var segIndex = 0; segIndex < elementRects.length; segIndex++) {
                var segRect = elementRects[segIndex];
                var elementStyleParts = [
                    "position: absolute",
                    "left: " + segRect.left.toFixed(2) + "px",
                    "top: " + segRect.top.toFixed(2) + "px",
                    "width: " + Math.max(0, segRect.width).toFixed(2) + "px",
                    "height: " + Math.max(0, segRect.height).toFixed(2) + "px",
                    "background-color: " + backgroundColor,
                    "z-index: " + elementZIndex,
                    "border: none",
                    "box-shadow: none"
                ];
                if (outlineBorder) {
                    elementStyleParts.push("outline: " + Number(outlineBorder.width || 0).toFixed(2) + "px solid " + String(outlineBorder.color || ""));
                    elementStyleParts.push("outline-offset: 0px");
                }
                var elementStyleText = elementStyleParts.join("; ") + ";";

                elementDivList.push({
                    seq: _pushSeq++,
                    z: elementZIndex,
                    kind: "element",
                    groupKey: "e" + String(elementIndex),
                    rect: {
                        left: segRect.left,
                        top: segRect.top,
                        width: Math.max(0, segRect.width),
                        height: Math.max(0, segRect.height)
                    },
                    source: elementInfo,
                    html: '<div class="flat-element debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + elementStyleText + '" data-debug-label="' + escapeHtmlText(dataLabel) + (segIndex > 0 ? ("-cutout-" + segIndex) : "") + '"></div>'
                });
            }

            // Dark1 / Dark2 / Dark3（压暗 1/2/3 级）→ Base + 盖色阴影（可叠加多层；覆盖在元素主体上，但不盖住文本）
            if (!isTransparentBackground && shadeOverlayCountForBackground > 0) {
                // 放在 element（+5）与 text（+8）之间：从 +6 开始叠加，支持 1~2 层。
                var shadeZIndexBase = elementBaseZIndex + 6;
                for (var shadeLayer = 0; shadeLayer < shadeOverlayCountForBackground; shadeLayer++) {
                    var shadeZIndex = shadeZIndexBase + shadeLayer;
                    var shadeLabelPrefix = (shadeLayer === 0) ? "shade-" : ("shade" + String(shadeLayer + 1) + "-");
                    for (var shadeSegIndex = 0; shadeSegIndex < elementRects.length; shadeSegIndex++) {
                        var shadeRect = elementRects[shadeSegIndex];
                        var shadeStyleText = [
                            "position: absolute",
                            "left: " + shadeRect.left.toFixed(2) + "px",
                            "top: " + shadeRect.top.toFixed(2) + "px",
                            "width: " + Math.max(0, shadeRect.width).toFixed(2) + "px",
                            "height: " + Math.max(0, shadeRect.height).toFixed(2) + "px",
                            "background-color: " + shadeOverlayRgbaForBackground,
                            "z-index: " + shadeZIndex
                        ].join("; ") + ";";
                        shadowDivList.push({
                            seq: _pushSeq++,
                            z: shadeZIndex,
                            kind: "shadow",
                            groupKey: "e" + String(elementIndex),
                            rect: {
                                left: shadeRect.left,
                                top: shadeRect.top,
                                width: Math.max(0, shadeRect.width),
                                height: Math.max(0, shadeRect.height)
                            },
                            source: elementInfo,
                            html: '<div class="flat-shadow debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + shadeStyleText + '" data-debug-label="' + shadeLabelPrefix + escapeHtmlText(dataLabel) + (shadeSegIndex > 0 ? ("-cutout-" + shadeSegIndex) : "") + '"></div>'
                        });
                    }
                }
            }
        }

        var textContent = normalizedTextContent;
        if (textContent) {
            var textZIndex = elementBaseZIndex + 8;
            var fontFamilyText = String(styles.fontFamily || "sans-serif").replace(/"/g, "'");

            var textAlignValue = styles.textAlign || "start";
            var justifyContentValue = "flex-start";
            if (textAlignValue === "center") {
                justifyContentValue = "center";
            } else if (textAlignValue === "right" || textAlignValue === "end") {
                justifyContentValue = "flex-end";
            }

            var isFlexContainerForText = String(styles.display || "").toLowerCase().indexOf("flex") >= 0;
            if (isFlexContainerForText) {
                var computedJustify = String(styles.justifyContent || "").trim();
                if (computedJustify && computedJustify !== "normal") {
                    justifyContentValue = computedJustify;
                }
            }
            // 文本层在扁平化输出中统一用 `display:flex` 承载。
            // 关键：若源元素本身不是 flex 容器，但高度被布局（如 flex:1）拉大，
            // 扁平层若默认 `align-items:center` 会把文字垂直居中，导致“原稿左上，扁平后跑中间”。
            // 因此：非 flex 容器默认用 `flex-start`（顶对齐）；flex 容器则尊重其 align-items。
            var alignItemsValue = isFlexContainerForText ? "center" : "flex-start";
            if (isFlexContainerForText) {
                var computedAlign = String(styles.alignItems || "").trim();
                if (computedAlign && computedAlign !== "normal") {
                    alignItemsValue = computedAlign;
                }
            }

            // 显式覆盖（优先级最高）：让作者可以控制扁平化文字层的对齐方式，
            // 避免“导出 TextBox 已居中，但扁平化预览仍左上”的错觉。
            var explicit = _resolveExplicitTextAlignOverrides(elementInfo);
            var applied = _applyExplicitTextAlignToFlex(explicit.h, explicit.v, textAlignValue, justifyContentValue, alignItemsValue);
            textAlignValue = applied.textAlignValue;
            justifyContentValue = applied.justifyContentValue;
            alignItemsValue = applied.alignItemsValue;

            // 额外兜底（按钮文本）：span.btn-text 通常处于按钮视觉中心。
            // 当源元素不是 flex 容器且未显式声明 valign 时，默认策略会是 flex-start（顶对齐），会导致按钮文字看起来“贴上”。
            // 仅对“位于 button 内 + class 含 btn-text + 当前仍为 flex-start”启用垂直居中，避免影响普通长文本块。
            if (alignItemsValue === "flex-start" && elementInfo && elementInfo.inButton === true) {
                var cls0 = elementInfo.className ? String(elementInfo.className || "") : "";
                if (cls0 && cls0.split(/\s+/).indexOf("btn-text") >= 0) {
                    alignItemsValue = "center";
                }
            }

            // 关键：处理“整体 transform scale（--ui-scale）”导致的字号未缩放问题。
            var effScale = _resolveEffectiveScaleFromStyles(styles);
            var textStyles = styles;
            if (Math.abs(effScale - 1) > 1e-6) {
                textStyles = Object.assign({}, styles, {
                    fontSize: _scalePxText(styles.fontSize || "16px", effScale),
                    lineHeight: _scaleLineHeightText(styles.lineHeight || "normal", effScale),
                });
            }

            var renderTextRect = computeExpandedTextRect(innerLeft, innerTop, innerWidth, innerHeight, textStyles, alignItemsValue);
            var hitTextRect = computeExpandedTextHitRect(renderTextRect, textStyles, justifyContentValue);

            var outerTextStyleParts = [
                "position: absolute",
                "left: " + hitTextRect.left.toFixed(2) + "px",
                "top: " + hitTextRect.top.toFixed(2) + "px",
                "width: " + hitTextRect.width.toFixed(2) + "px",
                "height: " + hitTextRect.height.toFixed(2) + "px",
                "z-index: " + textZIndex,
                "background: transparent",
                "border: none",
                "box-shadow: none"
            ];
            var outerTextStyleText = outerTextStyleParts.join("; ") + ";";

            var innerTextStyleParts = [
                "position: absolute",
                "left: " + hitTextRect.innerOffsetX.toFixed(2) + "px",
                "top: 0px",
                "width: " + renderTextRect.width.toFixed(2) + "px",
                "height: " + renderTextRect.height.toFixed(2) + "px",
                "padding: " + padding.top.toFixed(2) + "px " + padding.right.toFixed(2) + "px " + padding.bottom.toFixed(2) + "px " + padding.left.toFixed(2) + "px",
                "box-sizing: border-box",
                "color: " + (styles.color || "#000000"),
                "font-size: " + normalizeFontSizeForFlatText(textStyles.fontSize || "16px", { diagnostics: diagnostics, target: target, context: "text" }),
                "font-weight: " + (styles.fontWeight || "400"),
                "font-family: " + fontFamilyText,
                "line-height: " + (textStyles.lineHeight || "normal"),
                "text-align: " + textAlignValue,
                "display: flex",
                "align-items: " + alignItemsValue,
                "justify-content: " + justifyContentValue
            ];

            if (styles.textTransform && styles.textTransform !== "none") {
                innerTextStyleParts.push("text-transform: " + styles.textTransform);
            }
            if (styles.whiteSpace && styles.whiteSpace !== "normal") {
                innerTextStyleParts.push("white-space: " + styles.whiteSpace);
            }
            if (styles.overflow && styles.overflow !== "visible") {
                innerTextStyleParts.push("overflow: " + styles.overflow);
            }
            if (styles.textOverflow && styles.textOverflow !== "clip" && styles.textOverflow !== "none") {
                innerTextStyleParts.push("text-overflow: " + styles.textOverflow);
            }
            if (styles.wordBreak && styles.wordBreak !== "normal") {
                innerTextStyleParts.push("word-break: " + styles.wordBreak);
            }
            if (styles.wordWrap && styles.wordWrap !== "normal") {
                innerTextStyleParts.push("word-wrap: " + styles.wordWrap);
            }
            if (styles.letterSpacing && styles.letterSpacing !== "normal") {
                innerTextStyleParts.push("letter-spacing: " + styles.letterSpacing);
            }
            // text-shadow：为了让“多重阴影”在扁平层里体现为多个图层，这里将每个 shadow 拆成一个独立的“阴影文本层”。
            // 做法：阴影层文本 color=transparent，仅保留单条 text-shadow；主文本层不再带 text-shadow，避免重复。
            var textShadowList = parseTextShadow(styles.textShadow || "");
            if (textShadowList && textShadowList.length > 0) {
                for (var tsi = 0; tsi < textShadowList.length; tsi++) {
                    var ts = textShadowList[tsi];
                    if (!ts) continue;
                    var tsZIndex = textZIndex - 1; // 位于主文字下方
                    var shadowOuterStyleText = [
                        outerTextStyleText.replace(/z-index:\s*[^;]+;/i, "z-index: " + tsZIndex + ";"),
                        "pointer-events: none"
                    ].join(" ");
                    var shadowInnerParts = innerTextStyleParts.slice();
                    // 只显示阴影，不显示文本本体
                    for (var spi = 0; spi < shadowInnerParts.length; spi++) {
                        if (String(shadowInnerParts[spi] || "").indexOf("color:") === 0) {
                            shadowInnerParts[spi] = "color: transparent";
                        }
                    }
                    var colorText = String(ts.color || PALETTE_SHADE_OVERLAY_RGBA);
                    var blurText = isFinite(ts.blur) ? (Number(ts.blur || 0).toFixed(2) + "px") : "0px";
                    var oxText = isFinite(ts.offsetX) ? (Number(ts.offsetX || 0).toFixed(2) + "px") : "0px";
                    var oyText = isFinite(ts.offsetY) ? (Number(ts.offsetY || 0).toFixed(2) + "px") : "0px";
                    shadowInnerParts.push("text-shadow: " + oxText + " " + oyText + " " + blurText + " " + colorText);
                    var shadowInnerText = shadowInnerParts.join("; ") + ";";
                    textDivList.push({
                        seq: _pushSeq++,
                        z: tsZIndex,
                        kind: "text",
                        groupKey: "e" + String(elementIndex),
                        rect: {
                            left: hitTextRect.left,
                            top: hitTextRect.top,
                            width: hitTextRect.width,
                            height: hitTextRect.height
                        },
                        source: elementInfo,
                        html:
                            '<div class="flat-text flat-text-shadow debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + shadowOuterStyleText + '" data-debug-label="text-shadow-' + escapeHtmlText(textLabelBase) + "-" + String(tsi) + '">' +
                            '<div class="flat-text-inner"' + uiTextDataAttrs + ' style="' + shadowInnerText + '">' + escapeHtmlText(textContent) + "</div>" +
                            "</div>"
                    });
                }
            } else if (styles.textShadow && styles.textShadow !== "none") {
                // 兜底：无法解析时仍保留原始 text-shadow（但不会拆层）
                innerTextStyleParts.push("text-shadow: " + styles.textShadow);
            }

            var innerTextStyleText = innerTextStyleParts.join("; ") + ";";
            textDivList.push({
                seq: _pushSeq++,
                z: textZIndex,
                kind: "text",
                groupKey: "e" + String(elementIndex),
                rect: {
                    left: hitTextRect.left,
                    top: hitTextRect.top,
                    width: hitTextRect.width,
                    height: hitTextRect.height
                },
                source: elementInfo,
                html:
                    '<div class="flat-text debug-target size-' + sizeKey + '"' + uiStateDataAttrs + ' style="' + outerTextStyleText + '" data-debug-label="text-' + escapeHtmlText(textLabelBase) + '">' +
                    '<div class="flat-text-inner"' + uiTextDataAttrs + ' style="' + innerTextStyleText + '">' + escapeHtmlText(textContent) + "</div>" +
                    "</div>"
            });
        }

        elementIndex += 1;
    }

    var allDivList = shadowDivList.concat(borderDivList).concat(elementDivList).concat(textDivList);
    allDivList.sort(function (leftItem, rightItem) {
        if (leftItem.z !== rightItem.z) {
            return leftItem.z - rightItem.z;
        }
        // 同 z-index 下按插入顺序稳定排序：保证“背景 shade -> 文本阴影 -> 文本本体”叠放关系可控
        var ls = Number(leftItem.seq || 0);
        var rs = Number(rightItem.seq || 0);
        return ls - rs;
    });

    var options = arguments.length >= 3 ? arguments[2] : null;
    var opts = options || {};
    var debugShowAll = !!opts.debug_show_all_controls;
    var debugShowGroups = !!opts.debug_show_groups;
    var uiKeyPrefix = String(opts.ui_key_prefix || "").trim();

    // 扁平化阶段默认剔除“完全被覆盖”的碎片（按“组”剔除；阴影/文本不参与遮挡判定）
    var occlusionDebug = {};
    var visible = debugShowAll ? allDivList : _pruneFullyOccludedGroups(allDivList, occlusionDebug);
    if (!debugShowAll && visible.length === 0 && allDivList.length > 0) {
        if (diagnostics && diagnostics.warn) {
            diagnostics.warn({
                code: "OCCLUSION.ALL_PRUNED",
                message: "遮挡剔除导致扁平层为空，已回退为不过滤。",
                evidence: {
                    inputCount: occlusionDebug.inputCount || allDivList.length,
                    groupCount: occlusionDebug.groupCount || 0,
                    droppedGroups: occlusionDebug.droppedGroups || []
                },
                fix: { kind: "investigate", suggestion: "检查是否存在覆盖全屏的矩形层，或遮挡判定是否过于激进。" }
            });
        }
        // 兜底：若遮挡剔除导致全空，则回退为“不过滤”以避免扁平预览空白。
        visible = allDivList;
    }

    var htmlList = visible.map(function (item) { return item.html; });
    if (debugShowGroups) {
        htmlList.push(buildFlattenedGroupDebugOverlayHtml(visible, sizeKey, uiKeyPrefix));
    }
    return htmlList.join("\n            ");
}

