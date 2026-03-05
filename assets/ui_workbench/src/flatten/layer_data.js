import { PALETTE_SHADE_OVERLAY_RGBA } from "../config.js";
import { collectGameCutoutRects as _collectGameCutoutRects, filterCutoutsForElement as _filterCutoutsForElement, isGameCutoutElementInfo as _isGameCutoutElementInfo, subtractRectByCutouts as _subtractRectByCutouts } from "./internal/cutouts.js";
import { buildDimSurroundingRectsForHighlightArea as _buildDimSurroundingRectsForHighlightArea, collectHighlightDisplayAreaInfos as _collectHighlightDisplayAreaInfos, isHighlightDisplayAreaElementInfo as _isHighlightDisplayAreaElementInfo, normalizeHighlightOverlayColorFromAlpha as _normalizeHighlightOverlayColorFromAlpha } from "./internal/highlight_areas.js";
import { pruneFullyOccludedGroups as _pruneFullyOccludedGroups } from "./internal/occlusion.js";
import { mapRectFillColorForPalette, isTransparentColor } from "./colors.js";
import { parseBoxShadow, parseTextShadow } from "./shadows.js";
import { parseBorder, collectBorderColors } from "./borders.js";
import { computeExpandedTextRect, computeExpandedTextHitRect } from "./text_layout.js";

// 扁平化策略：无视所有 border 的“可视化输出”，但仍按 border 宽度缩小 innerRect。
// 需求：
// - 不输出任何 border 层（kind="border"）。
// - 但控件内容区域（element/text）的 rect 应使用“去掉边框后的大小”（innerRect = borderBox - borderWidths）。
// 注意：border 输出代码暂时保留（便于未来回退/对照），但默认不再执行。
var FLATTEN_IGNORE_ALL_BORDERS = true;

function _normalizeTextContent(text) {
    var raw = String(text || "");
    if (!raw) {
        return "";
    }
    return raw.replace(/\s+/g, " ").trim();
}

function _isButtonLikeElementAttrs(attrs) {
    // 与 ui_export/widgets/button_semantics.js 保持一致：只认“显式语义标注”。
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

function _looksLikeVariablePlaceholderText(text) {
    var s = String(text || "");
    if (!s) {
        return false;
    }
    // 常见占位符写法：
    // - {{lv.xxx}} / {{ps.xxx}}
    // - {1:lv.xxx}（资源库历史写法）
    // 这里只做轻量识别：用于 lint 提示，不作为强校验。
    if (/\{\{\s*(lv|ps)\.[^}]+\}\}/i.test(s)) {
        return true;
    }
    if (/\{\s*1\s*:\s*lv\.[^}]+\}/i.test(s)) {
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
    return Math.max(-5_000_000, Math.min(5_000_000, n));
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
    // 仅对“显式 px 行高”做缩放；单位less/%/em/rem 会随 fontSize 一起被 estimateLineHeightPx 处理。
    var lowered = t.toLowerCase();
    if (lowered.endsWith("px")) {
        return _scalePxText(lowered, scale);
    }
    return t;
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

export function buildFlattenedLayerData(elementsData, opts) {
    var o = opts || {};
    var diagnostics = o.diagnostics || null;

    var elements = (elementsData && elementsData.elements) ? elementsData.elements : [];
    var bodySize = elementsData && elementsData.bodySize ? elementsData.bodySize : { width: 0, height: 0 };
    var gameCutoutRects = _collectGameCutoutRects(elements);
    var highlightAreas = _collectHighlightDisplayAreaInfos(elements);
    var layerList = [];

    var elementIndex = 0;
    // Track ancestor containers by depth to support simple geometry heuristics (e.g. alignment hints).
    // Elements are extracted in DOM pre-order with depth info, so a stack is reliable.
    var _ancestorStack = []; // entries: { depth: number, rect: {left,top,width,height}, hasBorder: boolean }

    for (var index = 0; index < elements.length; index++) {
        var elementInfo = elements[index];
        var target = _buildIssueTargetForElementInfo(elementInfo, elementIndex);
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
            // - marker 本体不输出；
            // - 生成 4 个 shadow layer（上/下/左/右）包围该 rect，压暗周围区域。
            var markerRect = rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : null;
            var overlayColor = (function () {
                for (var hi = 0; hi < highlightAreas.length; hi++) {
                    var info = highlightAreas[hi];
                    if (info && Number(info.sourceElementIndex) === Number(index)) {
                        return _normalizeHighlightOverlayColorFromAlpha(info.overlayAlpha);
                    }
                }
                return _normalizeHighlightOverlayColorFromAlpha(0.45);
            })();
            var overlayRects = _buildDimSurroundingRectsForHighlightArea(markerRect, bodySize);
            var overlayZIndex = elementIndex * 10 + _parseFlatZBiasFromElementInfo(elementInfo) + 9;

            var originalClassName0 = elementInfo.className ? String(elementInfo.className) : "";
            var dataLabel0 = elementInfo.id ? String(elementInfo.id || "") : "";
            if (!dataLabel0 && originalClassName0) {
                var classParts0 = originalClassName0.split(/\s+/).filter(function (part) { return part.trim().length > 0; });
                for (var classIndex0 = 0; classIndex0 < classParts0.length; classIndex0++) {
                    var className0 = classParts0[classIndex0];
                    if (className0 !== "debug-target") {
                        dataLabel0 = className0;
                        break;
                    }
                }
            }
            var commonSource0 = {
                tagName: tagName,
                id: elementInfo.id || null,
                className: elementInfo.className || null,
                attributes: elementInfo.attributes || null,
                dataLabel: dataLabel0 || "",
                elementIndex: elementIndex,
                depth: elementInfo.depth || 0,
                rect: {
                    left: Number(rect.left || 0),
                    top: Number(rect.top || 0),
                    width: Number(rect.width || 0),
                    height: Number(rect.height || 0)
                },
                innerRect: {
                    left: Number(rect.left || 0),
                    top: Number(rect.top || 0),
                    width: Number(rect.width || 0),
                    height: Number(rect.height || 0)
                },
                padding: {
                    top: padding.top,
                    right: padding.right,
                    bottom: padding.bottom,
                    left: padding.left
                },
                styleHints: {
                    backgroundColor: "transparent",
                    borderRadius: styles.borderRadius || "",
                    boxShadow: "none",
                    color: "",
                    fontSize: "",
                    fontWeight: "",
                    textAlign: "",
                    display: styles.display || "",
                    visibility: styles.visibility || "",
                    opacity: styles.opacity || "",
                    justifyContent: styles.justifyContent || "",
                    alignItems: styles.alignItems || ""
                },
                textContent: (elementInfo.textContent || ""),
                fullTextContent: (elementInfo.fullTextContent || "")
            };
            for (var oi = 0; oi < overlayRects.length; oi++) {
                var r0 = overlayRects[oi];
                var safeW = Math.max(0, Number(r0.width || 0));
                var safeH = Math.max(0, Number(r0.height || 0));
                if (!isFinite(safeW) || !isFinite(safeH) || safeW <= 0.001 || safeH <= 0.001) {
                    continue;
                }
                layerList.push({
                    kind: "shadow",
                    z: overlayZIndex,
                    rect: {
                        left: Number(r0.left || 0),
                        top: Number(r0.top || 0),
                        width: safeW,
                        height: safeH
                    },
                    backgroundColor: overlayColor,
                    debugLabel: "highlight-dim-" + elementIndex + "-" + oi,
                    source: commonSource0
                });
            }
            elementIndex += 1;
            continue;
        }

        // Maintain ancestor stack (pop until current element fits).
        var curDepth = Number(elementInfo.depth || 0);
        if (!isFinite(curDepth)) {
            curDepth = 0;
        }
        while (_ancestorStack.length > 0) {
            var last = _ancestorStack[_ancestorStack.length - 1];
            if (last && Number(last.depth) >= curDepth) {
                _ancestorStack.pop();
                continue;
            }
            break;
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
        // 对“视觉是否为空/容器是否有边框”的判断：border 视为不存在（避免仅靠边框的装饰层影响分组/提示）。
        var hasBorder = !FLATTEN_IGNORE_ALL_BORDERS && (
            borderTopWidth > 0 ||
            borderRightWidth > 0 ||
            borderBottomWidth > 0 ||
            borderLeftWidth > 0
        );
        var hasShadow = (styles.boxShadow || "none") !== "none" && (styles.boxShadow || "") !== "";
        var rawTextContent = (elementInfo.textContent || "").trim();
        var normalizedTextContent = _normalizeTextContent(rawTextContent);
        var hasVisibleText = !!normalizedTextContent;
        // 关键：允许“可见文本为空，但声明了 data-ui-text（用于写回到游戏）”的场景仍然生成 text layer，
        // 否则导出阶段拿不到 text layer，就无法创建 TextBox（即使 template_from_layers 已允许 override 文本）。
        var attrsForExportText = elementInfo && elementInfo.attributes ? (elementInfo.attributes || null) : null;
        var declaredExportText = attrsForExportText ? String(attrsForExportText.dataUiText || "").trim() : "";
        var hasDeclaredExportText = !!declaredExportText;
        // ---------------------------------------------------------------------
        // Placeholder-length pitfall (lint):
        // If author uses a long variable placeholder as the *visible* text,
        // the browser will measure a huge width, and the exported widget rect
        // will be huge as well (even if the runtime value is short).
        //
        // Recommended pattern:
        //   <span data-ui-text="{{lv.some_long_variable_path}}">短示例</span>
        //
        // - Keep the visible text short for layout measurement.
        // - Put the real binding/placeholder into data-ui-text for export.
        // ---------------------------------------------------------------------
        if (hasVisibleText && diagnostics && diagnostics.warn && elementInfo && elementInfo.attributes) {
            if (!declaredExportText) {
                if (_looksLikeVariablePlaceholderText(normalizedTextContent) && normalizedTextContent.length >= 18) {
                    diagnostics.warn({
                        code: "TEXT.PLACEHOLDER_USED_FOR_LAYOUT",
                        message: "检测到文本内容疑似变量占位符：直接用占位符做网页排版会把控件宽度撑爆（运行期值可能很短）。",
                        target: target,
                        evidence: { text: normalizedTextContent },
                        fix: {
                            kind: "manual",
                            suggestion:
                                "建议：把占位符挪到 data-ui-text（用于导出写回），并把元素文本改成短示例（用于网页测量）。例如：<span data-ui-text=\"{{lv.xxx}}\">示例</span>。如确实需要长文本，给容器加 max-width + ellipsis 约束。",
                        },
                    });
                }
            }
        }
        // 兼容：部分页面的按钮语义只标了 data-ui-key（而未显式标 data-ui-interact-key/action），
        // 这类 `<button data-ui-key="...">` 在工程语义上通常就是“可交互按钮锚点”。
        // 这里仅对真实 <button> 且具备 data-ui-key 的情况做兜底，避免把纯样式 `<button>` 误判为按钮。
        var attrsForButton = elementInfo && elementInfo.attributes ? elementInfo.attributes : null;
        var isButtonTagWithUiKey = (
            String(tagName || "").toLowerCase() === "button" &&
            attrsForButton &&
            String(attrsForButton.dataUiKey || "").trim() !== ""
        );
        var isButtonLike = _isButtonLikeElementAttrs(attrsForButton) || isButtonTagWithUiKey;

        // Push this element as an ancestor container for later children (after basic flags computed).
        _ancestorStack.push({
            depth: curDepth,
            rect: { left: left, top: top, width: width, height: height },
            hasBorder: !!hasBorder
        });

        // 关键：按钮锚点允许“视觉为空”：
        // 多状态按钮常见写法是 button 本体透明，视觉（底色/边框/文字）放到子层互斥显示。
        // 若这里直接跳过，会导致导出链路看不到 data-ui-interact-key 等语义，从而无法生成“道具展示”按钮锚点。
        if (isTransparentBackground && !hasBorder && !hasShadow && !hasVisibleText && !hasDeclaredExportText && !isButtonLike) {
            elementIndex += 1;
            continue;
        }

        // ---------------------------------------------------------------------
        // Alignment hint (lint): suggest right-align for short labels near a border container's right edge.
        // Motivation: in UI like "关卡选择", the text is visually near the right border,
        // but devs often leave default left/start alignment, causing subtle misalignment.
        //
        // Behavior:
        // - If data-ui-align="right": enforce right alignment (warning, because this is a Web-first lint).
        // - Else: heuristic warning when close to right edge.
        // - data-ui-align-ok="1": opt-out.
        // ---------------------------------------------------------------------
        if (hasVisibleText && diagnostics && diagnostics.warn && elementInfo && elementInfo.attributes) {
            var attrs = elementInfo.attributes || null;
            var alignOk = attrs ? String(attrs.dataUiAlignOk || "").trim() : "";
            if (alignOk !== "1") {
                var alignIntent = attrs ? String(attrs.dataUiAlign || "").trim().toLowerCase() : "";
                var textAlignValue = String(styles.textAlign || "start").trim().toLowerCase();
                var isRightish = (textAlignValue === "right" || textAlignValue === "end");
                var isLeftish = (textAlignValue === "" || textAlignValue === "left" || textAlignValue === "start");

                // Explicit intent should be enforced even without a detected border container.
                if (alignIntent === "right") {
                    if (!isRightish) {
                        diagnostics.warn({
                            code: "TEXT.ALIGNMENT_EXPECT_RIGHT",
                            message: "该文本声明了 data-ui-align=\"right\"，但 computed text-align 不是 right/end。",
                            target: target,
                            evidence: { text: normalizedTextContent, text_align: textAlignValue },
                            fix: { kind: "manual", suggestion: "为该元素设置 text-align:right;（必要时让元素占据可对齐宽度，例如设定宽度或在 flex 容器中用 flex:1）。" }
                        });
                    }
                } else {
                    // Find nearest border container on stack (excluding current element itself).
                    var containerRect = null;
                    for (var si = _ancestorStack.length - 2; si >= 0; si--) {
                        var anc = _ancestorStack[si];
                        if (anc && anc.hasBorder && anc.rect) {
                            containerRect = anc.rect;
                            break;
                        }
                    }
                    if (containerRect) {
                        var containerRight = containerRect.left + containerRect.width;
                        var elementRight = left + width;
                        var distToRight = containerRight - elementRight;
                        var isShortLabel = normalizedTextContent.length <= 20 && width <= 260;
                        if (isLeftish && isShortLabel && isFinite(distToRight) && distToRight >= 0 && distToRight <= 80) {
                            diagnostics.warn({
                                code: "TEXT.ALIGNMENT_SUGGEST_RIGHT",
                                message: "文本靠近右边框但仍为左对齐：建议改为右对齐以贴合边界（减少人工遗漏）。",
                                target: target,
                                evidence: { text: normalizedTextContent, text_align: textAlignValue, dist_to_container_right: distToRight },
                                fix: { kind: "manual", suggestion: "给该元素加 text-align:right; 或加 data-ui-align=\"right\" 并配合 CSS 落地。若确实不需要，设置 data-ui-align-ok=\"1\" 忽略该条。" }
                            });
                        }
                    }
                }
            }
        }

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

        var elementBaseZIndex = elementIndex * 10 + _parseFlatZBiasFromElementInfo(elementInfo);

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

        var commonSource = {
            tagName: tagName,
            id: elementInfo.id || null,
            className: elementInfo.className || null,
            attributes: elementInfo.attributes || null,
            dataLabel: dataLabel || "",
            elementIndex: elementIndex,
            depth: elementInfo.depth || 0,
            rect: {
                left: left,
                top: top,
                width: width,
                height: height
            },
            innerRect: {
                left: left + borderLeftWidth,
                top: top + borderTopWidth,
                width: Math.max(0, width - borderLeftWidth - borderRightWidth),
                height: Math.max(0, height - borderTopWidth - borderBottomWidth)
            },
            padding: {
                top: padding.top,
                right: padding.right,
                bottom: padding.bottom,
                left: padding.left
            },
            styleHints: {
                backgroundColor: rawBackgroundColor,
                borderRadius: styles.borderRadius || "",
                boxShadow: styles.boxShadow || "",
                color: styles.color || "",
                fontSize: styles.fontSize || "",
                fontWeight: styles.fontWeight || "",
                textAlign: styles.textAlign || "",
                display: styles.display || "",
                visibility: styles.visibility || "",
                opacity: styles.opacity || "",
                justifyContent: styles.justifyContent || "",
                alignItems: styles.alignItems || ""
            },
            textContent: (elementInfo.textContent || ""),
            fullTextContent: (elementInfo.fullTextContent || "")
        };

        // 若按钮本体“视觉为空”，补一个专用锚点层，确保导出能创建按钮的“道具展示”控件。
        // 典型场景：button 本体透明，底色/边框/文字放在子层（多状态互斥）。
        if (isButtonLike && isTransparentBackground && !hasBorder && !hasShadow && !hasVisibleText && !hasDeclaredExportText) {
            layerList.push({
                kind: "button_anchor",
                rect: { left: left, top: top, width: width, height: height },
                z: elementBaseZIndex,
                source: commonSource
            });
            elementIndex += 1;
            continue;
        }

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
            for (var sIndex = 0; sIndex < shadowRects.length; sIndex++) {
                var sr = shadowRects[sIndex];
                layerList.push({
                    kind: "shadow",
                    z: shadowZIndex,
                    rect: {
                        left: sr.left,
                        top: sr.top,
                        width: Math.max(0, sr.width),
                        height: Math.max(0, sr.height)
                    },
                    backgroundColor: shadow.color,
                    debugLabel: "shadow-" + elementIndex + (sIndex > 0 ? ("-cutout-" + sIndex) : ""),
                    source: commonSource
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

            var borderColorInfo = collectBorderColors(borders);
            var canUseUnifiedBorder = !isTransparentBackground && borderColorInfo.firstColor && borderColorInfo.distinctCount === 1;

            if (canUseUnifiedBorder) {
                var unifiedBorderMapping = mapRectFillColorForPalette(borderColorInfo.firstColor || "", { diagnostics: diagnostics, target: target, context: "border" });
                var unifiedBorderColor = unifiedBorderMapping.colorText || (borderColorInfo.firstColor || "");
                var borderBaseRect = { left: left, top: top, width: Math.max(0, width), height: Math.max(0, height) };
                var borderRects = shouldApplyCutouts ? _subtractRectByCutouts(borderBaseRect, effectiveCutouts) : [borderBaseRect];
                for (var bIndex = 0; bIndex < borderRects.length; bIndex++) {
                    var br = borderRects[bIndex];
                    layerList.push({
                        kind: "border",
                        z: borderZIndex,
                        rect: {
                            left: br.left,
                            top: br.top,
                            width: Math.max(0, br.width),
                            height: Math.max(0, br.height)
                        },
                        backgroundColor: unifiedBorderColor,
                        debugLabel: "border-" + elementIndex + "-unified" + (bIndex > 0 ? ("-cutout-" + bIndex) : ""),
                        borderSegment: "unified",
                        source: commonSource
                    });
                }

                if (unifiedBorderMapping.needsShadeOverlay) {
                    var unifiedShadeZIndex = borderZIndex + 1;
                    for (var ubIndex = 0; ubIndex < borderRects.length; ubIndex++) {
                        var ubs = borderRects[ubIndex];
                        layerList.push({
                            kind: "shadow",
                            z: unifiedShadeZIndex,
                            rect: {
                                left: ubs.left,
                                top: ubs.top,
                                width: Math.max(0, ubs.width),
                                height: Math.max(0, ubs.height)
                            },
                            backgroundColor: PALETTE_SHADE_OVERLAY_RGBA,
                            debugLabel: "shade-border-" + elementIndex + "-unified" + (ubIndex > 0 ? ("-cutout-" + ubIndex) : ""),
                            source: commonSource
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
                        var sr = segmentRects[segIndex];
                        layerList.push({
                            kind: "border",
                            z: borderZIndex,
                            rect: {
                                left: sr.left,
                                top: sr.top,
                                width: Math.max(0, sr.width),
                                height: Math.max(0, sr.height)
                            },
                            backgroundColor: mappedSegmentColor,
                            debugLabel: "border-" + elementIndex + "-" + segmentLabel + (segIndex > 0 ? ("-cutout-" + segIndex) : ""),
                            borderSegment: segmentLabel,
                            source: commonSource
                        });
                    }

                    if (segmentMapping.needsShadeOverlay) {
                        var shadeZIndex = borderZIndex + 1;
                        for (var segShadeIndex = 0; segShadeIndex < segmentRects.length; segShadeIndex++) {
                            var ssr = segmentRects[segShadeIndex];
                            layerList.push({
                                kind: "shadow",
                                z: shadeZIndex,
                                rect: {
                                    left: ssr.left,
                                    top: ssr.top,
                                    width: Math.max(0, ssr.width),
                                    height: Math.max(0, ssr.height)
                                },
                                backgroundColor: PALETTE_SHADE_OVERLAY_RGBA,
                                debugLabel: "shade-border-" + elementIndex + "-" + segmentLabel + (segShadeIndex > 0 ? ("-cutout-" + segShadeIndex) : ""),
                                source: commonSource
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

        if (!isTransparentBackground) {
            var elementZIndex = elementBaseZIndex + 5;
            var elementBaseRect = { left: innerLeft, top: innerTop, width: innerWidth, height: innerHeight };
            var elementRects = shouldApplyCutouts ? _subtractRectByCutouts(elementBaseRect, effectiveCutouts) : [elementBaseRect];
            for (var segIndex = 0; segIndex < elementRects.length; segIndex++) {
                var segRect = elementRects[segIndex];
                layerList.push({
                    kind: "element",
                    z: elementZIndex,
                    rect: {
                        left: segRect.left,
                        top: segRect.top,
                        width: Math.max(0, segRect.width),
                        height: Math.max(0, segRect.height)
                    },
                    backgroundColor: backgroundColor,
                    debugLabel: (dataLabel || "") + (segIndex > 0 ? ("-cutout-" + segIndex) : ""),
                    source: commonSource
                });
            }

            if (shadeOverlayCountForBackground > 0) {
                var shadeZIndexBase = elementBaseZIndex + 6;
                for (var shadeLayer = 0; shadeLayer < shadeOverlayCountForBackground; shadeLayer++) {
                    var shadeZIndex = shadeZIndexBase + shadeLayer;
                    var shadeLabelPrefix = (shadeLayer === 0) ? "shade-" : ("shade" + String(shadeLayer + 1) + "-");
                    for (var shadeSegIndex = 0; shadeSegIndex < elementRects.length; shadeSegIndex++) {
                        var shadeRect = elementRects[shadeSegIndex];
                        layerList.push({
                            kind: "shadow",
                            z: shadeZIndex,
                            rect: {
                                left: shadeRect.left,
                                top: shadeRect.top,
                                width: Math.max(0, shadeRect.width),
                                height: Math.max(0, shadeRect.height)
                            },
                            backgroundColor: shadeOverlayRgbaForBackground,
                            debugLabel: shadeLabelPrefix + (dataLabel || "") + (shadeSegIndex > 0 ? ("-cutout-" + shadeSegIndex) : ""),
                            source: commonSource
                        });
                    }
                }
            }
        }

        var textContent = normalizedTextContent;
        if (textContent || hasDeclaredExportText) {
            var textZIndex = elementBaseZIndex + 8;
            var fontFamilyText = String(styles.fontFamily || "sans-serif").replace(/"/g, "'");

            // 关键：若上层容器使用 transform: scale(...)（例如 --ui-scale 响应式缩放），
            // rect 已是缩放后的屏幕坐标，但 computed fontSize 仍是未缩放值。
            // 不做补偿会导致导出到 GIL 后“盒子小、字号大” -> 1600x900 等分辨率下文字溢出/叠字。
            var effScale = _resolveEffectiveScaleFromStyles(styles);
            var textStyles = styles;
            if (Math.abs(effScale - 1) > 1e-6) {
                textStyles = Object.assign({}, styles, {
                    fontSize: _scalePxText(styles.fontSize || "16px", effScale),
                    lineHeight: _scaleLineHeightText(styles.lineHeight || "normal", effScale),
                });
            }

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
            // 与 flatten_divs.js 保持一致：
            // - 文本层扁平化统一用 display:flex 承载；
            // - 若源元素本身不是 flex 容器，但高度被布局（如 flex:1）拉大，默认居中会导致文字垂直漂移；
            //   因此非 flex 容器默认采用 flex-start（顶对齐）。
            var alignItemsValue = isFlexContainerForText ? "center" : "flex-start";
            if (isFlexContainerForText) {
                var computedAlign = String(styles.alignItems || "").trim();
                if (computedAlign && computedAlign !== "normal") {
                    alignItemsValue = computedAlign;
                }
            }

            // 显式覆盖（优先级最高）：与 flatten_divs.js 保持一致，避免 preview DOM 的 text layer 与导出推断口径分叉。
            var explicit = _resolveExplicitTextAlignOverrides(elementInfo);
            var applied = _applyExplicitTextAlignToFlex(
                explicit.h,
                explicit.v,
                textAlignValue,
                justifyContentValue,
                alignItemsValue
            );
            textAlignValue = applied.textAlignValue;
            justifyContentValue = applied.justifyContentValue;
            alignItemsValue = applied.alignItemsValue;

            // 额外兜底（按钮文本）：span.btn-text 在按钮内默认垂直居中（仅在未显式声明且当前仍为 flex-start 时启用）。
            if (alignItemsValue === "flex-start" && elementInfo && elementInfo.inButton === true) {
                var cls0 = elementInfo.className ? String(elementInfo.className || "") : "";
                if (cls0 && cls0.split(/\s+/).indexOf("btn-text") >= 0) {
                    alignItemsValue = "center";
                }
            }

            var renderTextRect = computeExpandedTextRect(innerLeft, innerTop, innerWidth, innerHeight, textStyles, alignItemsValue);
            var hitTextRect = computeExpandedTextHitRect(renderTextRect, textStyles, justifyContentValue);

            // 与 flatten_divs.js 保持一致：把 text-shadow 拆成多个“阴影文本层”
            var textShadowList = parseTextShadow(styles.textShadow || "");
            if (textShadowList && textShadowList.length > 0) {
                for (var tsi = 0; tsi < textShadowList.length; tsi++) {
                    var ts = textShadowList[tsi];
                    if (!ts) continue;
                    layerList.push({
                        kind: "text",
                        z: textZIndex - 1,
                        rect: {
                            left: hitTextRect.left,
                            top: hitTextRect.top,
                            width: hitTextRect.width,
                            height: hitTextRect.height
                        },
                        renderRect: {
                            left: renderTextRect.left,
                            top: renderTextRect.top,
                            width: renderTextRect.width,
                            height: renderTextRect.height
                        },
                        text: textContent,
                        // 仅用于调试/对齐：实际渲染层在 HTML 里用 color=transparent + 单条 text-shadow
                        color: "transparent",
                        effectiveScale: effScale,
                        fontSize: (styles.fontSize || "16px"),
                        fontWeight: (styles.fontWeight || "400"),
                        fontFamily: fontFamilyText,
                        lineHeight: (styles.lineHeight || "normal"),
                        padding: {
                            top: padding.top,
                            right: padding.right,
                            bottom: padding.bottom,
                            left: padding.left
                        },
                        textAlign: textAlignValue,
                        justifyContent: justifyContentValue,
                        alignItems: alignItemsValue,
                        textTransform: styles.textTransform || "none",
                        whiteSpace: styles.whiteSpace || "normal",
                        overflow: styles.overflow || "visible",
                        textOverflow: styles.textOverflow || "clip",
                        wordBreak: styles.wordBreak || "normal",
                        wordWrap: styles.wordWrap || "normal",
                        letterSpacing: styles.letterSpacing || "normal",
                        textShadow: (String(ts.offsetX || 0) + "px " + String(ts.offsetY || 0) + "px " + String(ts.blur || 0) + "px " + String(ts.color || "")),
                        debugLabel: "text-shadow-" + (textLabelBase || "") + "-" + String(tsi),
                        source: commonSource
                    });
                }
            }

            layerList.push({
                kind: "text",
                z: textZIndex,
                rect: {
                    left: hitTextRect.left,
                    top: hitTextRect.top,
                    width: hitTextRect.width,
                    height: hitTextRect.height
                },
                renderRect: {
                    left: renderTextRect.left,
                    top: renderTextRect.top,
                    width: renderTextRect.width,
                    height: renderTextRect.height
                },
                text: textContent,
                color: (styles.color || "#000000"),
                effectiveScale: effScale,
                fontSize: (styles.fontSize || "16px"),
                fontWeight: (styles.fontWeight || "400"),
                fontFamily: fontFamilyText,
                lineHeight: (styles.lineHeight || "normal"),
                padding: {
                    top: padding.top,
                    right: padding.right,
                    bottom: padding.bottom,
                    left: padding.left
                },
                textAlign: textAlignValue,
                justifyContent: justifyContentValue,
                alignItems: alignItemsValue,
                textTransform: styles.textTransform || "none",
                whiteSpace: styles.whiteSpace || "normal",
                overflow: styles.overflow || "visible",
                textOverflow: styles.textOverflow || "clip",
                wordBreak: styles.wordBreak || "normal",
                wordWrap: styles.wordWrap || "normal",
                letterSpacing: styles.letterSpacing || "normal",
                // 主文本层不再自带 text-shadow（已拆到独立阴影层）；无法解析则保留原值
                textShadow: (textShadowList && textShadowList.length > 0) ? "none" : (styles.textShadow || "none"),
                debugLabel: "text-" + (textLabelBase || ""),
                source: commonSource
            });
        }

        elementIndex += 1;
    }

    layerList.sort(function (leftItem, rightItem) {
        return leftItem.z - rightItem.z;
    });

    var options = arguments.length >= 2 ? arguments[1] : null;
    var opts = options || {};
    var debugShowAll = !!opts.debug_show_all_controls;

    // 扁平化阶段默认剔除“完全被覆盖”的碎片（按“组”剔除；阴影/文本不参与遮挡判定）
    return debugShowAll ? layerList : _pruneFullyOccludedGroups(layerList);
}

