import { setStableUiKeyPrefix, sanitizeIdPart, buildStableUiKeyBase } from "./keys.js";
import { applyUiStateMetaToPayload } from "./ui_state.js";
import { getShadowOverlayAlpha, isShadowOverlayColor, parsePxNumber } from "./color_font.js";
import { buildItemDisplayWidget, buildProgressBarWidget, buildTextBoxWidget, buildWidgetId, isButtonLikeSource, normalizeIconAndTextLayer, pickIconSeatRect } from "./widgets.js";
import { buildLayerKeyFromRect } from "../layer_key.js";

function nowIsoText() {
    return new Date().toISOString();
}

function _parseBorderWidthPx(styles, sideName) {
    // source.styles.* 可能是 "1px" / "0px" / "" / undefined
    if (!styles) {
        return 0;
    }
    var key = "border" + String(sideName || "") + "Width";
    var raw = String(styles[key] || "").trim();
    var n = parsePxNumber(raw);
    if (n === null || !isFinite(n) || n <= 0) {
        return 0;
    }
    return Math.max(0, Number(n));
}

function _rectWithoutBorderFromSource(source) {
    // 目的：导出尺寸与“去掉边框后的内容区域(innerRect)”一致。
    // 背景：source.rect 来自 DOM 的 getBoundingClientRect()（border-box），若忽略 border 但仍希望内容变小，
    // 则必须在导出时显式扣除 border 宽度。
    if (!source || !source.rect) {
        return null;
    }
    var r = source.rect;
    var left = Number(r.left || 0);
    var top = Number(r.top || 0);
    var width = Number(r.width || 0);
    var height = Number(r.height || 0);
    if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height)) {
        return null;
    }
    var styles = source.styles || null;
    var bwTop = _parseBorderWidthPx(styles, "Top");
    var bwRight = _parseBorderWidthPx(styles, "Right");
    var bwBottom = _parseBorderWidthPx(styles, "Bottom");
    var bwLeft = _parseBorderWidthPx(styles, "Left");
    var innerLeft = left + bwLeft;
    var innerTop = top + bwTop;
    var innerWidth = Math.max(0, width - bwLeft - bwRight);
    var innerHeight = Math.max(0, height - bwTop - bwBottom);
    return { left: innerLeft, top: innerTop, width: innerWidth, height: innerHeight };
}

function _parseFlatZBiasFromSource(source) {
    // `data-flat-z-bias` 语义：作为“局部 stacking context 的整体抬升”。
    //
    // 说明：
    // - layer_data.js 会把 bias（含祖先继承）写入 source.attributes.dataFlatZBias，并在 layer.z 中叠加；
    // - 这里对“按钮语义派生控件（btn_item/btn_fill）”必须复用同一口径，否则会出现：
    //   按钮位于高层级容器（例如新手指引卡片 data-flat-z-bias=1000100）内时，
    //   btn_fill 的 layer_index 变成很小的值，从而被面板底色覆盖（表现为“按钮底色跑到最底下看不见”）。
    var attrs = (source && source.attributes) ? source.attributes : null;
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

function layerKey(layer) {
    var z = Number.isFinite(layer.z) ? Math.trunc(layer.z) : 0;
    var src = layer.source || {};
    var elementIndex = Number.isFinite(src.elementIndex) ? Math.trunc(src.elementIndex) : -1;
    var kind = String(layer.kind || "");
    return kind + ":" + elementIndex + ":" + z;
}

function flatLayerKeyForPreview(layer) {
    // IMPORTANT:
    // - 该 key 必须与 `src/workbench_main/group_tree.js` 的 layerKey 构造方式一致（由 `src/layer_key.js` 统一实现），
    //   否则“导出控件面板隐藏单控件”无法精确对应到“扁平分组”里的同一条目。
    // - format: kind__left__top__width__height__round(z)，并对 rect 使用 toFixed(2)。
    if (!layer || !layer.rect) {
        return "";
    }
    var kind = String(layer.kind || "").trim() || "layer";
    return buildLayerKeyFromRect(kind, layer.rect, layer.z);
}

function layerRectArea(rect) {
    if (!rect) {
        return 0;
    }
    var w = Number(rect.width || 0);
    var h = Number(rect.height || 0);
    if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
        return 0;
    }
    return w * h;
}

function layerRectCenter(rect) {
    if (!rect) {
        return { x: 0, y: 0 };
    }
    return { x: Number(rect.left || 0) + Number(rect.width || 0) / 2.0, y: Number(rect.top || 0) + Number(rect.height || 0) / 2.0 };
}

function layerRectContainsPoint(rect, px, py) {
    if (!rect) {
        return false;
    }
    var left = Number(rect.left || 0);
    var top = Number(rect.top || 0);
    var w = Number(rect.width || 0);
    var h = Number(rect.height || 0);
    return (px >= left) && (py >= top) && (px <= left + w) && (py <= top + h);
}

function layerRectIntersectionArea(a, b) {
    if (!a || !b) {
        return 0;
    }
    var left = Math.max(Number(a.left || 0), Number(b.left || 0));
    var top = Math.max(Number(a.top || 0), Number(b.top || 0));
    var right = Math.min(Number(a.left || 0) + Number(a.width || 0), Number(b.left || 0) + Number(b.width || 0));
    var bottom = Math.min(Number(a.top || 0) + Number(a.height || 0), Number(b.top || 0) + Number(b.height || 0));
    var iw = right - left;
    var ih = bottom - top;
    if (!isFinite(iw) || !isFinite(ih) || iw <= 0 || ih <= 0) {
        return 0;
    }
    return iw * ih;
}

export function buildUiControlGroupTemplateFromFlattenedLayers(layerList, options) {
    options = options || {};
    var templateName = String(options.template_name || "HTML导入_UI控件组");
    var templateId = String(options.template_id || ("template_html_import_" + String(Date.now())));
    var idPrefix = sanitizeIdPart(options.id_prefix || templateId) || templateId;
    setStableUiKeyPrefix(options.ui_key_prefix || "");

    var warnings = [];
    var widgets = [];
    var usedWidgetIds = new Set();
    var usedUiKeys = new Set();

    function buildRectSuffixFromWidget(widget) {
        // 同一个 HTML 元素在遇到 game-cutout 等“切分”时，会产出多个碎片层；
        // 这些碎片的 source 相同（同 elementIndex / id），若 ui_key 相同，写回 .gil 时会被当作“同一控件重复更新”，
        // 导致只剩 1 个碎片，其他全部“消失且列表里找不到”。
        if (!widget) {
            return "";
        }
        var pos = widget.position || null;
        var size = widget.size || null;
        if (!pos || !size || pos.length !== 2 || size.length !== 2) {
            return "";
        }
        var x = Number(pos[0]);
        var y = Number(pos[1]);
        var w = Number(size[0]);
        var h = Number(size[1]);
        if (!isFinite(x) || !isFinite(y) || !isFinite(w) || !isFinite(h)) {
            return "";
        }
        var ix = Math.round(x);
        var iy = Math.round(y);
        var iw = Math.round(w);
        var ih = Math.round(h);
        return "r" + String(ix) + "_" + String(iy) + "_" + String(iw) + "_" + String(ih);
    }

    function pushWidget(widget) {
        if (!widget) {
            return;
        }
        var widgetId = String(widget.widget_id || "");
        if (!widgetId) {
            return;
        }
        var uniqueId = widgetId;
        var counter = 2;
        while (usedWidgetIds.has(uniqueId)) {
            uniqueId = widgetId + "_" + counter;
            counter += 1;
        }
        widget.widget_id = uniqueId;
        usedWidgetIds.add(uniqueId);

        // ui_key 必须全局唯一（至少在一次导出内唯一），否则写回阶段会被“复用同 GUID”吞掉。
        var uiKeyRaw = String(widget.ui_key || "").trim();
        if (uiKeyRaw) {
            var uiKeyUnique = uiKeyRaw;
            if (usedUiKeys.has(uiKeyUnique)) {
                var rectSuffix = buildRectSuffixFromWidget(widget);
                if (rectSuffix) {
                    uiKeyUnique = uiKeyRaw + "__" + rectSuffix;
                } else {
                    uiKeyUnique = uiKeyRaw + "__dup";
                }
                var uiCounter = 2;
                while (usedUiKeys.has(uiKeyUnique)) {
                    uiKeyUnique = uiKeyRaw + "__" + (rectSuffix ? rectSuffix : "dup") + "_" + String(uiCounter);
                    uiCounter += 1;
                }
                widget.ui_key = uiKeyUnique;
            }
            usedUiKeys.add(String(widget.ui_key || uiKeyRaw));
        }

        widgets.push(widget);
    }

    var consumedElementLayerKey = new Set();
    var consumedTextLayerKey = new Set();

    // ---------------------------------------------------------------------
    // 性能优化（导出侧）：过滤“小字号 text-shadow 拆层”
    //
    // 背景：
    // - 扁平化会把 text-shadow 拆成独立 text 层（color=transparent + textShadow=...）
    // - 导出到 GIL 时会变成额外的 TextBox（数量几乎翻倍），在复杂页面会显著增加游戏侧 UI widget 数
    //
    // 策略：
    // - 默认只保留“较大字号”的阴影文本层（例如标题/大数字），小字号阴影层直接不导出
    // - 不影响预览扁平化画面（仅影响导出 bundle/GIL）
    //
    // 可配置：
    // - options.min_text_shadow_font_size：最小字号阈值（px），默认 18；设为 0 表示不过滤
    function shouldExportTextShadowLayer(layerItem) {
        if (!layerItem) {
            return true;
        }
        // layer_data.js 约定：text-shadow 层为 kind="text"，color="transparent"，且 textShadow 非 "none"
        var isShadowText = (String(layerItem.color || "").trim().toLowerCase() === "transparent") && (String(layerItem.textShadow || "").trim().toLowerCase() !== "none");
        if (!isShadowText) {
            return true;
        }
        var threshold = Number(options.min_text_shadow_font_size);
        if (!isFinite(threshold)) {
            threshold = 18;
        }
        if (threshold <= 0) {
            return true;
        }
        var fontSizeNumber = parsePxNumber(String(layerItem.fontSize || ""));
        if (fontSizeNumber === null) {
            fontSizeNumber = 16;
        }
        return fontSizeNumber >= threshold;
    }

    // 1) 先处理按钮：为每个 <button> 创建底层“道具展示” + 中层“进度条背景”
    var buttonSourceIndexSet = new Set();
    for (var i = 0; i < layerList.length; i++) {
        var layer = layerList[i];
        if (!layer || !layer.source) {
            continue;
        }
        if (!isButtonLikeSource(layer.source)) {
            continue;
        }
        if (!Number.isFinite(layer.source.elementIndex)) {
            continue;
        }
        buttonSourceIndexSet.add(Math.trunc(layer.source.elementIndex));
    }

    buttonSourceIndexSet.forEach(function (buttonElementIndex) {
        // 找到该 button 的 source（任意一层即可）
        var sampleLayer = null;
        for (var j = 0; j < layerList.length; j++) {
            var candidate = layerList[j];
            if (!candidate || !candidate.source) {
                continue;
            }
            if (!isButtonLikeSource(candidate.source)) {
                continue;
            }
            if (Math.trunc(candidate.source.elementIndex) === buttonElementIndex) {
                sampleLayer = candidate;
                break;
            }
        }
        if (!sampleLayer) {
            return;
        }
        var source = sampleLayer.source;
        var attrsForButton = (source && source.attributes) ? source.attributes : null;
        var exportAsForButton = attrsForButton ? String(attrsForButton.dataUiExportAs || attrsForButton.componentOwnerDataUiExportAs || "").trim().toLowerCase() : "";
        // 约定：data-ui-export-as="decor" 表示“保留可见/可分组，但导出阶段不要把它当按钮锚点”，
        // 即：不生成“道具展示(可交互)”按钮锚点控件。
        var skipButtonItemDisplay = exportAsForButton === "decor";
        // IMPORTANT:
        // - button 的“基础 rect”必须使用去掉边框后的 innerRect（扣除 border 宽度），否则会出现：
        //   扁平化预览/层数据已按 innerRect 变小，但导出 GIL 仍按 border-box 变大（用户体感：只有视觉变了，GIL 没变）。
        var baseRect = _rectWithoutBorderFromSource(source);
        if (!baseRect) {
            return;
        }
        var baseZ = buttonElementIndex * 10 + _parseFlatZBiasFromSource(source);
        var itemZ = baseZ + 1;
        var fillZ = baseZ + 5;

        // button_anchor：当按钮本体视觉为空时，layer_data.js 会产出 kind="button_anchor" 的专用层。
        // 若存在该层，则 btn_item（道具展示按钮锚点）应 1:1 绑定到它，避免预览侧靠 rect 猜导致“点 A 高亮 B”。
        var buttonAnchorLayer = null;
        for (var ba = 0; ba < layerList.length; ba++) {
            var c0 = layerList[ba];
            if (!c0 || !c0.source || !c0.rect) continue;
            if (String(c0.kind || "") !== "button_anchor") continue;
            if (!Number.isFinite(c0.source.elementIndex)) continue;
            if (Math.trunc(c0.source.elementIndex) === buttonElementIndex) {
                buttonAnchorLayer = c0;
                break;
            }
        }

        // 背景色来自 button 的 element 层（innerRect + backgroundColor）
        var elementLayer = null;
        for (var k = 0; k < layerList.length; k++) {
            var candidateLayer = layerList[k];
            if (!candidateLayer || !candidateLayer.source) {
                continue;
            }
            if (String(candidateLayer.kind || "") !== "element") {
                continue;
            }
            if (!isButtonLikeSource(candidateLayer.source)) {
                continue;
            }
            if (Math.trunc(candidateLayer.source.elementIndex) === buttonElementIndex) {
                elementLayer = candidateLayer;
                break;
            }
        }

        // 按钮锚点策略：如果按钮与“单 ICON 文本层”重叠，则视作该 ICON 本身就是按钮（不再额外创建一个按钮锚点）。
        var anchorRect = (elementLayer && elementLayer.rect) ? elementLayer.rect : baseRect;
        var bestIconLayer = null;
        var bestIconOverlap = 0;
        for (var t = 0; t < layerList.length; t++) {
            var textLayer = layerList[t];
            if (!textLayer || String(textLayer.kind || "") !== "text" || !textLayer.rect) {
                continue;
            }
            if (consumedTextLayerKey.has(layerKey(textLayer))) {
                continue;
            }
            var textRaw = String(textLayer.text || "");
            var a = normalizeIconAndTextLayer(textRaw, textLayer, warnings);
            if (a.kind !== "single_icon_only") {
                continue;
            }
            var iconCenter = layerRectCenter(textLayer.rect);
            if (!layerRectContainsPoint(baseRect, iconCenter.x, iconCenter.y)) {
                continue;
            }
            var overlap = layerRectIntersectionArea(textLayer.rect, baseRect);
            if (overlap <= 0) {
                continue;
            }
            if (overlap > bestIconOverlap) {
                bestIconOverlap = overlap;
                bestIconLayer = textLayer;
            }
        }

        if (!skipButtonItemDisplay) {
            var itemId = buildWidgetId(idPrefix, "btn_item", source, itemZ);
            var itemName = "按钮_道具展示_" + (source.id || (source.attributes && source.attributes.dataDebugLabel) || ("e" + buttonElementIndex));

            // DEPRECATED:
            // - data-ui-selected-highlight / data-ui-selected-default 已废弃（容易和 data-ui-state-* 概念混淆）。
            // - 请在 HTML 中显式写出高亮底板 DOM，并用 data-ui-state-group / data-ui-state / data-ui-state-default 表达互斥状态；
            //   由节点图通过 ui_key 切换显隐。
            var attrs0 = (source && source.attributes) ? source.attributes : null;
            var enableSelectedHighlightText = attrs0 ? String(attrs0.dataUiSelectedHighlight || "").trim() : "";
            var enableSelectedDefaultText = attrs0 ? String(attrs0.dataUiSelectedDefault || "").trim() : "";
            if (enableSelectedHighlightText || enableSelectedDefaultText) {
                if (warnings) {
                    warnings.push(
                        "已废弃：检测到 data-ui-selected-highlight/data-ui-selected-default（请迁移到显式 DOM + data-ui-state-*）：[" +
                        String(itemName || "") +
                        "]"
                    );
                }
            }
            if (bestIconLayer && bestIconLayer.source) {
                var iconSource = bestIconLayer.source;
                var iconConfigVar = iconSource && iconSource.attributes ? (iconSource.attributes.dataInventoryItemId || null) : null;
                var buttonConfigVar = source && source.attributes ? (source.attributes.dataInventoryItemId || null) : null;
                var configVar = iconConfigVar || buttonConfigVar || null;
                var iconAsButtonSettings = {
                    can_interact: true,
                    display_type: "模板道具",
                    use_count_enabled: false,
                    hide_when_empty_count: false,
                    show_quantity: false,
                    hide_when_zero: false
                };
                if (configVar) {
                    iconAsButtonSettings.config_id_variable = String(configVar || "").trim();
                }
                var btnItem0 = buildItemDisplayWidget(itemId, itemName, anchorRect, itemZ, source, { settings: iconAsButtonSettings }, "btn_item");
                // icon-as-button：将按钮锚点明确绑定到该 icon text layer，保证预览/分组树可精确定位。
                btnItem0.__flat_layer_key = flatLayerKeyForPreview(bestIconLayer);
                pushWidget(btnItem0);
                consumedTextLayerKey.add(layerKey(bestIconLayer));
            } else {
                var btnItem1 = buildItemDisplayWidget(itemId, itemName, anchorRect, itemZ, source, null, "btn_item");
                // 绑定策略（从强到弱）：
                // 1) button_anchor（视觉为空的按钮专用锚点层）
                // 2) elementLayer（按钮底色层）
                // 3) sampleLayer（兜底：该按钮任意一层；确保有 key 可用于精确定位）
                if (buttonAnchorLayer) {
                    btnItem1.__flat_layer_key = flatLayerKeyForPreview(buttonAnchorLayer);
                } else if (elementLayer) {
                    btnItem1.__flat_layer_key = flatLayerKeyForPreview(elementLayer);
                } else if (sampleLayer) {
                    btnItem1.__flat_layer_key = flatLayerKeyForPreview(sampleLayer);
                }
                pushWidget(btnItem1);
            }
        }

        if (elementLayer && elementLayer.rect) {
            var fillId = buildWidgetId(idPrefix, "btn_fill", elementLayer.source, fillZ);
            var fillName = "按钮_底色_" + (source.id || (source.attributes && source.attributes.dataDebugLabel) || ("e" + buttonElementIndex));
            var btnFill = buildProgressBarWidget(
                fillId,
                fillName,
                elementLayer.rect,
                fillZ,
                elementLayer.backgroundColor,
                100,
                warnings,
                elementLayer.source,
                "btn_fill"
            );
            btnFill.__flat_layer_key = flatLayerKeyForPreview(elementLayer);
            pushWidget(btnFill);
            consumedElementLayerKey.add(layerKey(elementLayer));
        }
    });

    // 2) 普通层：shadow/border/element/text → 控件
    for (var index = 0; index < layerList.length; index++) {
        var layerItem = layerList[index];
        if (!layerItem || !layerItem.kind || !layerItem.rect) {
            continue;
        }

        var key = layerKey(layerItem);
        if (consumedElementLayerKey.has(key) || consumedTextLayerKey.has(key)) {
            continue;
        }

        var kind = String(layerItem.kind || "");
        var source0 = layerItem.source || null;
        var zIndex = layerItem.z;

        function _bestNameSuffixForLayer(layer, source) {
            // 目标：导出控件列表里不要出现大量“text-btn-text / tone-3-stripe”这种跨按钮重复的弱标签，
            // 否则用户会误以为“别的按钮内容被打进一个组”。
            //
            // 约定：
            // - 若 layer 本身有 debugLabel（通常来自 data-debug-label / data-ui-key），直接用它；
            // - 否则若元素自身有 data-ui-key / data-debug-label，用自身；
            // - 否则若存在 componentOwner（按钮根），优先把 owner 的 data-ui-key / data-debug-label 作为前缀，
            //   并拼上当前元素的 dataLabel（类画像），形成 “owner:leaf” 的可读标签。
            // - 最后才回退到 dataLabel。
            if (layer && String(layer.debugLabel || "").trim()) {
                return String(layer.debugLabel || "").trim();
            }
            var a = source && source.attributes ? source.attributes : null;
            var selfKey = a ? String(a.dataUiKey || "").trim() : "";
            if (selfKey) {
                return selfKey;
            }
            var selfDbg = a ? String(a.dataDebugLabel || "").trim() : "";
            if (selfDbg) {
                return selfDbg;
            }
            var leaf = source && source.dataLabel ? String(source.dataLabel || "").trim() : "";
            var ownerKey = a ? String(a.componentOwnerDataUiKey || "").trim() : "";
            var ownerDbg = a ? String(a.componentOwnerDataDebugLabel || "").trim() : "";
            var owner = ownerDbg || ownerKey;
            if (owner && leaf) {
                return owner + ":" + leaf;
            }
            if (owner) {
                return owner;
            }
            if (leaf) {
                return leaf;
            }
            return "";
        }

        if (kind === "shadow") {
            var shadowId = buildWidgetId(idPrefix, "shadow", source0, zIndex);
            var shadowSuffix = _bestNameSuffixForLayer(layerItem, source0) || shadowId;
            var shadowName = "阴影_" + shadowSuffix;
            var overlayAlpha = getShadowOverlayAlpha(layerItem.backgroundColor);
            if (overlayAlpha !== null) {
                // 盖色阴影（25%/45%）：
                // - 25%：用 TextBox 才能表达半透明盖色（更“浅”）
                // - 45%：用 ProgressBar（0% 空条）表达更“深”的压暗效果
                var isLightOverlay = Math.abs(Number(overlayAlpha) - 0.25) <= 0.03;
                if (isLightOverlay) {
                    var bgHex = "#0E0E0E40";
                    var wShadowTextBox = buildTextBoxWidget(shadowId, shadowName, layerItem.rect, zIndex, "", layerItem, warnings, options, "shadow", bgHex);
                    wShadowTextBox.__flat_layer_key = flatLayerKeyForPreview(layerItem);
                    wShadowTextBox._html_color_source = String(layerItem.backgroundColor || "");
                    pushWidget(wShadowTextBox);
                } else {
                    // 说明：
                    // - 进度条颜色枚举仅支持五色；这里固定使用白色（#E2DBCE）以避免颜色映射 warning。
                    // - 原始 rgba(14,14,14,0.45) 仍保留到 `_html_color_source`，便于排障与对照。
                    var wShadowOverlay = buildProgressBarWidget(shadowId, shadowName, layerItem.rect, zIndex, "#E2DBCE", 0, warnings, source0, "shadow");
                    wShadowOverlay.__flat_layer_key = flatLayerKeyForPreview(layerItem);
                    wShadowOverlay._html_color_source = String(layerItem.backgroundColor || "");
                    pushWidget(wShadowOverlay);
                }
            } else {
                var wShadow = buildProgressBarWidget(shadowId, shadowName, layerItem.rect, zIndex, layerItem.backgroundColor, 0, warnings, source0, "shadow");
                wShadow.__flat_layer_key = flatLayerKeyForPreview(layerItem);
                pushWidget(wShadow);
            }
            continue;
        }
        if (kind === "border") {
            var borderId = buildWidgetId(idPrefix, "border", source0, zIndex);
            var borderSuffix = _bestNameSuffixForLayer(layerItem, source0) || borderId;
            var borderName = "边框_" + borderSuffix;
            var wBorder = buildProgressBarWidget(borderId, borderName, layerItem.rect, zIndex, layerItem.backgroundColor, 100, warnings, source0, "border");
            wBorder.__flat_layer_key = flatLayerKeyForPreview(layerItem);
            pushWidget(wBorder);
            continue;
        }
        if (kind === "element") {
            // button（或 .btn） 的 element 层已在按钮处理阶段转为 btn_fill；这里避免重复
            if (source0 && isButtonLikeSource(source0)) {
                continue;
            }
            var elementId = buildWidgetId(idPrefix, "rect", source0, zIndex);
            var elementSuffix = _bestNameSuffixForLayer(layerItem, source0) || elementId;
            var elementName = "色块_" + elementSuffix;
            // 约定：`data-ui-key="*_highlight"` 作为“选中高亮底板”矩形（由节点图切换显隐）。
            // 为了能被按钮打组逻辑吸附到按钮模板里（减少模板数量），这里将其命名为 `高亮底板_*`。
            var baseKey0 = buildStableUiKeyBase(source0);
            if (baseKey0 && (baseKey0.indexOf("_highlight__") >= 0 || /_highlight$/.test(baseKey0))) {
                elementName = "高亮底板_" + baseKey0;
            }
            // 特例：如果“色块”本身就是阴影盖色（rgba(14,14,14,0.45/0.25)），
            // 需要保留 alpha：导出为“空文本框 + 半透明黑底”（而不是进度条），降低心智负担并避免写回后变深。
            var rectOverlayAlpha = getShadowOverlayAlpha(layerItem.backgroundColor);
            if (rectOverlayAlpha !== null) {
                var rectBgHex = (Math.abs(Number(rectOverlayAlpha) - 0.25) <= 0.03) ? "#0E0E0E40" : "#0E0E0E73";
                var wRectShadowTextBox = buildTextBoxWidget(elementId, elementName, layerItem.rect, zIndex, "", layerItem, warnings, options, "rect_shadow", rectBgHex);
                wRectShadowTextBox.__flat_layer_key = flatLayerKeyForPreview(layerItem);
                wRectShadowTextBox._html_color_source = String(layerItem.backgroundColor || "");
                pushWidget(wRectShadowTextBox);
            } else {
                var wRect = buildProgressBarWidget(elementId, elementName, layerItem.rect, zIndex, layerItem.backgroundColor, 100, warnings, source0, "rect");
                wRect.__flat_layer_key = flatLayerKeyForPreview(layerItem);
                pushWidget(wRect);
            }
            continue;
        }
        if (kind === "text") {
            if (!shouldExportTextShadowLayer(layerItem)) {
                continue;
            }
            var rawText = String(layerItem.text || "");
            var normalized = normalizeIconAndTextLayer(rawText, layerItem, warnings);
            if (normalized.kind === "single_icon_only") {
                // 单字符/emoji ICON 不再自动转换为“道具展示”控件。
                // 只有在 HTML 中显式声明 `data-ui-role="item_display"` 时，才允许转换为“道具展示(ICON)”。
                var attrsText0 = (source0 && source0.attributes) ? source0.attributes : null;
                var uiRoleText0 = attrsText0 ? String(attrsText0.dataUiRole || "").trim().toLowerCase() : "";
                var allowItemDisplayForIcon = uiRoleText0 === "item_display";
                if (allowItemDisplayForIcon) {
                    var iconId = buildWidgetId(idPrefix, "icon", source0, zIndex);
                    var iconSuffix = _bestNameSuffixForLayer(layerItem, source0) || iconId;
                    var iconName = "图标_" + iconSuffix;
                    var seatRect = pickIconSeatRect(layerItem, layerList) || layerItem.rect;
                    var configVar = source0 && source0.attributes ? (source0.attributes.dataInventoryItemId || null) : null;
                    var iconSettings = {
                        can_interact: false,
                        display_type: "模板道具",
                        // 尽量把“道具展示”变为纯展示：不映射按键、不显示次数/数量
                        keybind_kbm_code: 0,
                        keybind_gamepad_code: 0,
                        use_count_enabled: false,
                        hide_when_empty_count: false,
                        show_quantity: false,
                        hide_when_zero: false
                    };
                    if (configVar) {
                        iconSettings.config_id_variable = String(configVar || "").trim();
                    }
                    var wIcon = buildItemDisplayWidget(iconId, iconName, seatRect, zIndex, source0, { settings: iconSettings }, "icon");
                    wIcon.__flat_layer_key = flatLayerKeyForPreview(layerItem);
                    pushWidget(wIcon);
                    continue;
                }
            }
            var cleaned = String(normalized.text || "").trim();
            if (!cleaned) {
                continue;
            }
            var textId = buildWidgetId(idPrefix, "text", source0, zIndex);
            var textSuffix = _bestNameSuffixForLayer(layerItem, source0);
            if (!textSuffix) {
                textSuffix = textId;
            }
            // 如果文本来自按钮内通用 class（例如 .btn-text），进一步把具体文本内容拼进去，减少“跨按钮同名”错觉
            if (source0 && source0.attributes) {
                var selfUiKey = String(source0.attributes.dataUiKey || "").trim();
                var ownerUiKey = String(source0.attributes.componentOwnerDataUiKey || "").trim();
                if (!selfUiKey && ownerUiKey && String(source0.dataLabel || "").trim() === "btn-text") {
                    textSuffix = ownerUiKey + ":" + cleaned;
                }
            }
            var textName = "文本_" + textSuffix;
            var wText = buildTextBoxWidget(textId, textName, layerItem.rect, zIndex, cleaned, layerItem, warnings, options, "text");
            wText.__flat_layer_key = flatLayerKeyForPreview(layerItem);
            pushWidget(wText);
            continue;
        }
    }

    // group_size 仅做“编辑器画布上的组合框”参考；默认用导出时的画布尺寸（若提供）
    var groupWidth = Number(options.group_width || 0);
    var groupHeight = Number(options.group_height || 0);
    if (!isFinite(groupWidth) || groupWidth <= 0) {
        groupWidth = 100;
    }
    if (!isFinite(groupHeight) || groupHeight <= 0) {
        groupHeight = 100;
    }

    var now = nowIsoText();
    return {
        template: applyUiStateMetaToPayload({
            template_id: templateId,
            template_name: templateName,
            is_combination: true,
            widgets: widgets,
            group_position: [0, 0],
            group_size: [groupWidth, groupHeight],
            supports_layout_visibility_override: true,
            description: String(options.description || "由 ui_html_workbench 自动导出。"),
            created_at: now,
            updated_at: now
        }, null),
        warnings: warnings
    };
}

