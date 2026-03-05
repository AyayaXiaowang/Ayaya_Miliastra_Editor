import { dom } from "../dom_refs.js";
import { getCanvasSizeByKey } from "../config.js";
import { state } from "./state.js";
import { formatColorTextAsHex } from "./color.js";
import { computeCanvasRectFromElement, computeGroupCanvasRect } from "./geometry.js";
import { resolvePreviewElementLabel } from "./labels.js";

var inspectorImportantTextAreaElement = dom.inspectorImportantTextAreaElement;
var inspectorDetailsTextAreaElement = dom.inspectorDetailsTextAreaElement;
var textAlignInspectorBlockElement = dom.textAlignInspectorBlockElement;
var textAlignGridElement = dom.textAlignGridElement;
var textAlignHintElement = dom.textAlignHintElement;

var _textAlignInspectorInitialized = false;
var _textAlignInspectorAutoRefreshTimerId = 0;

function _normalizeTextAlignHValue(value) {
    var v = String(value || "").trim().toLowerCase();
    if (v === "start") {
        return "left";
    }
    if (v === "end") {
        return "right";
    }
    if (v === "left" || v === "center" || v === "right") {
        return v;
    }
    return "";
}

function _normalizeTextAlignVValue(value) {
    var v = String(value || "").trim().toLowerCase();
    // 约定：与 HTML 标注保持一致：top/middle/bottom
    if (v === "center") {
        return "middle";
    }
    if (v === "top" || v === "middle" || v === "bottom") {
        return v;
    }
    return "";
}

function _looksLikeFlexDisplay(displayValue) {
    var v = String(displayValue || "").trim().toLowerCase();
    if (!v) {
        return false;
    }
    return v.indexOf("flex") >= 0;
}

function _inferTextAlignHFromJustifyContent(justifyContentValue) {
    var v = String(justifyContentValue || "").trim().toLowerCase();
    if (!v || v === "normal") {
        return "";
    }
    if (v === "flex-start" || v === "start" || v === "left") {
        return "left";
    }
    if (v === "center") {
        return "center";
    }
    if (v === "flex-end" || v === "end" || v === "right") {
        return "right";
    }
    return "";
}

function _inferTextAlignVFromAlignItems(alignItemsValue) {
    var v = String(alignItemsValue || "").trim().toLowerCase();
    if (!v || v === "normal") {
        return "";
    }
    if (v === "flex-start" || v === "start" || v === "stretch") {
        return "top";
    }
    if (v === "center") {
        return "middle";
    }
    if (v === "flex-end" || v === "end" || v === "baseline") {
        return "bottom";
    }
    return "";
}

function _resolveTextAlignProbeElement(targetElement) {
    if (!targetElement || !targetElement.ownerDocument) {
        return targetElement;
    }
    // 扁平化文字层：对齐样式写在 `.flat-text-inner` 上；
    // 但 selection 逻辑会把 `.flat-text-inner` 提升为外层 `.flat-text` 进行选中。
    // 因此检查器需要回到 inner 节点，才能展示“扁平化后的真实对齐锚点”。
    if (targetElement.classList && targetElement.classList.contains("flat-text-inner")) {
        return targetElement;
    }
    if (targetElement.classList && targetElement.classList.contains("flat-text")) {
        var inner = targetElement.querySelector ? targetElement.querySelector(".flat-text-inner") : null;
        if (inner && inner.ownerDocument === targetElement.ownerDocument) {
            return inner;
        }
    }
    if (targetElement.closest) {
        var outer = targetElement.closest(".flat-text");
        if (outer && outer.ownerDocument === targetElement.ownerDocument) {
            var inner2 = outer.querySelector ? outer.querySelector(".flat-text-inner") : null;
            if (inner2 && inner2.ownerDocument === outer.ownerDocument) {
                return inner2;
            }
        }
    }
    return targetElement;
}

function _inferIsTextLikeElement(targetElement) {
    if (!targetElement) {
        return false;
    }
    // 优先信任语义标注
    if (targetElement.dataset) {
        var role = String(targetElement.dataset.uiRole || "").trim().toLowerCase();
        if (role === "label") {
            return true;
        }
        if (String(targetElement.dataset.uiText || "").trim()) {
            return true;
        }
    }
    // 兜底：有可见文本的普通元素也视为“文本类”
    var txt = targetElement.textContent ? String(targetElement.textContent || "").trim() : "";
    if (!txt) {
        return false;
    }
    var tag = String(targetElement.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return false;
    }
    return true;
}

function _getTextAlignState(targetDocument, targetElement) {
    var h = "";
    var v = "";
    var probe = _resolveTextAlignProbeElement(targetElement);

    // 优先使用显式标注（HTML 语义约定）
    if (probe && probe.getAttribute) {
        h =
            _normalizeTextAlignHValue(probe.getAttribute("data-ui-text-align")) ||
            _normalizeTextAlignHValue(probe.getAttribute("data-ui-text-align-h"));
        v =
            _normalizeTextAlignVValue(probe.getAttribute("data-ui-text-valign")) ||
            _normalizeTextAlignVValue(probe.getAttribute("data-ui-text-align-v"));
    }

    // 兜底：从 computedStyle 推断（用于扁平化产物：flex 对齐写在 style 上）
    if ((!h || !v) && targetDocument && targetDocument.defaultView && targetDocument.defaultView.getComputedStyle && probe) {
        var cs = targetDocument.defaultView.getComputedStyle(probe);
        var isFlex = _looksLikeFlexDisplay(cs && cs.display ? cs.display : "");

        if (!h) {
            if (isFlex) {
                h = _normalizeTextAlignHValue(_inferTextAlignHFromJustifyContent(cs.justifyContent));
            }
            if (!h) {
                h = _normalizeTextAlignHValue(cs && cs.textAlign ? cs.textAlign : "");
            }
        }
        if (!v) {
            if (isFlex) {
                v = _normalizeTextAlignVValue(_inferTextAlignVFromAlignItems(cs && cs.alignItems ? cs.alignItems : ""));
            }
            if (!v) {
                v = _normalizeTextAlignVValue(cs && cs.verticalAlign ? cs.verticalAlign : "");
            }
        }
    }
    if (!h) {
        h = "center";
    }
    if (!v) {
        v = "middle";
    }
    return { h: h, v: v };
}

function _setTextAlignInspectorVisible(visible) {
    if (!textAlignInspectorBlockElement) {
        return;
    }
    textAlignInspectorBlockElement.style.display = visible ? "" : "none";
}

function _updateTextAlignInspectorUi(targetDocument, targetElement) {
    if (!textAlignInspectorBlockElement || !textAlignGridElement) {
        return;
    }
    if (targetElement && targetElement.ownerDocument && targetDocument && targetElement.ownerDocument !== targetDocument) {
        _setTextAlignInspectorVisible(false);
        return;
    }
    if (!targetDocument || !targetElement || !_inferIsTextLikeElement(targetElement)) {
        _setTextAlignInspectorVisible(false);
        return;
    }

    _setTextAlignInspectorVisible(true);
    var st = _getTextAlignState(targetDocument, targetElement);

    var buttons = textAlignGridElement.querySelectorAll("button[data-h][data-v]");
    for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        if (!btn || !btn.getAttribute || !btn.classList) {
            continue;
        }
        var bh = _normalizeTextAlignHValue(btn.getAttribute("data-h"));
        var bv = _normalizeTextAlignVValue(btn.getAttribute("data-v"));
        var active = bh === st.h && bv === st.v;
        if (active) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    }

    if (textAlignHintElement) {
        var hText = st.h === "left" ? "左" : st.h === "center" ? "中" : "右";
        var vText = st.v === "top" ? "上" : st.v === "middle" ? "中" : "下";
        textAlignHintElement.textContent = "当前：" + hText + vText + "（" + st.h + " / " + st.v + "）";
    }
}

function _autoRefreshTextAlignInspectorUi() {
    var doc = state.previewDocument;
    if (!doc) {
        _setTextAlignInspectorVisible(false);
        return;
    }
    // 多选时只展示 group 检查，不展示文本对齐锚点
    if (state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
        _setTextAlignInspectorVisible(false);
        return;
    }
    var el = state.currentSelectedPreviewElement;
    if (!el) {
        _setTextAlignInspectorVisible(false);
        return;
    }
    _updateTextAlignInspectorUi(doc, el);
}

export function initializeTextAlignInspectorUi() {
    if (_textAlignInspectorInitialized) {
        return;
    }
    _textAlignInspectorInitialized = true;

    // 只读展示：不允许用户点击修改对齐。
    // 但为了“实时更新”体验，这里用轻量轮询在选中元素变化/属性变化时刷新 3×3 高亮。
    if (!_textAlignInspectorAutoRefreshTimerId) {
        _textAlignInspectorAutoRefreshTimerId = setInterval(function () {
            _autoRefreshTextAlignInspectorUi();
        }, 120);
    }
}

export function clearTextAlignInspectorUi() {
    _setTextAlignInspectorVisible(false);
    if (textAlignHintElement) {
        textAlignHintElement.textContent = "当前：-";
    }
    if (textAlignGridElement) {
        var buttons = textAlignGridElement.querySelectorAll("button.active");
        for (var i = 0; i < buttons.length; i++) {
            if (buttons[i] && buttons[i].classList) {
                buttons[i].classList.remove("active");
            }
        }
    }
}

export function buildElementInspectorText(targetDocument, targetElement) {
    if (!targetDocument || !targetElement || !targetElement.getBoundingClientRect) {
        return { importantText: "", detailsText: "" };
    }

    var bodyRect = targetDocument.body ? targetDocument.body.getBoundingClientRect() : null;
    if (!bodyRect) {
        return { importantText: "", detailsText: "" };
    }

    var elementRect = targetElement.getBoundingClientRect();
    var centerXInViewport = elementRect.left + elementRect.width / 2;
    var centerYInViewport = elementRect.top + elementRect.height / 2;

    var centerXLocal = centerXInViewport - bodyRect.left;
    var centerYLocalFromBottom = bodyRect.bottom - centerYInViewport;

    var computedStyle = targetDocument.defaultView ? targetDocument.defaultView.getComputedStyle(targetElement) : null;
    var labelName = resolvePreviewElementLabel(targetElement);

    var previewScale = Number(state.currentPreviewScale || 1);
    if (!isFinite(previewScale) || previewScale <= 0) {
        previewScale = 1;
    }

    var importantLines = [];
    var detailLines = [];
    var canvasSizeOption = getCanvasSizeByKey(state.currentSelectedCanvasSizeKey);
    if (canvasSizeOption) {
        importantLines.push("画布：" + String(canvasSizeOption.label || canvasSizeOption.key || ""));
    }
    // 注意：这里的缩放有两类：
    // - 舞台缩放（previewScale）：父页面为了把 iframe 画布塞进容器而施加的 transform: scale(...)，可能长期为 1（容器足够大）。
    // - UI缩放（--ui-scale）：Workbench 注入到预览文档的 CSS 变量，用于作者的响应式布局（若页面使用它，则元素 rect 会随之变化）。
    var uiScaleText = "";
    if (targetDocument && targetDocument.defaultView && targetDocument.defaultView.getComputedStyle && targetDocument.documentElement) {
        var csRoot = targetDocument.defaultView.getComputedStyle(targetDocument.documentElement);
        var rawUiScale = csRoot ? String(csRoot.getPropertyValue("--ui-scale") || "").trim() : "";
        if (rawUiScale) {
            var uiScaleNum = Number(rawUiScale);
            if (isFinite(uiScaleNum) && uiScaleNum > 0) {
                uiScaleText = String(Math.round(uiScaleNum * 1000) / 1000);
            } else {
                uiScaleText = rawUiScale;
            }
        }
    }
    if (uiScaleText) {
        importantLines.push("UI缩放：--ui-scale×" + uiScaleText);
    }
    importantLines.push("组件：" + labelName);
    importantLines.push(
        "尺寸：宽 " + Math.round(elementRect.width) + " 高 " + Math.round(elementRect.height) +
        "（预览显示：宽 " + Math.round(elementRect.width * previewScale) + " 高 " + Math.round(elementRect.height * previewScale) + "；舞台缩放×" + (Math.round(previewScale * 1000) / 1000) + "）"
    );
    importantLines.push(
        "坐标：中心(左下)=(" + Math.round(centerXLocal) + ", " + Math.round(centerYLocalFromBottom) + ")" +
        "（预览显示=(" + Math.round(centerXLocal * previewScale) + ", " + Math.round(centerYLocalFromBottom * previewScale) + ")）"
    );

    if (computedStyle) {
        importantLines.push("文字颜色：" + (formatColorTextAsHex(computedStyle.color) || String(computedStyle.color || "")));
        importantLines.push("字号：" + String(computedStyle.fontSize || ""));

        detailLines.push("标签：" + String(targetElement.tagName || "").toLowerCase());
        detailLines.push("边界：left " + Math.round(elementRect.left - bodyRect.left) + " top " + Math.round(elementRect.top - bodyRect.top));
        detailLines.push("背景：" + String(computedStyle.backgroundColor || ""));
        detailLines.push("层级：z-index " + String(computedStyle.zIndex || ""));
        detailLines.push("行高：" + String(computedStyle.lineHeight || ""));
        detailLines.push("内边距：" + [computedStyle.paddingTop, computedStyle.paddingRight, computedStyle.paddingBottom, computedStyle.paddingLeft].join(" "));
        detailLines.push("描边宽度：" + [computedStyle.borderTopWidth, computedStyle.borderRightWidth, computedStyle.borderBottomWidth, computedStyle.borderLeftWidth].join(" "));
        detailLines.push("阴影：" + String(computedStyle.boxShadow || ""));
        detailLines.push("透明度：" + String(computedStyle.opacity || "") + " 变换：" + String(computedStyle.transform || ""));
        detailLines.push("裁剪：" + String(computedStyle.overflow || "") + " / " + String(computedStyle.textOverflow || "") + " / " + String(computedStyle.whiteSpace || ""));
    }

    var elementTextContent = targetElement.textContent ? String(targetElement.textContent || "").trim() : "";
    if (elementTextContent) {
        importantLines.push("文本：" + elementTextContent);
    }

    return {
        importantText: importantLines.join("\n"),
        detailsText: detailLines.join("\n"),
    };
}

export function buildReverseRegionInfoLines(selectionRect, canvasSizeOption) {
    var resultLines = [];
    if (!selectionRect || !canvasSizeOption) {
        return resultLines;
    }
    var canvasWidth = Number(canvasSizeOption.width || 0);
    var canvasHeight = Number(canvasSizeOption.height || 0);

    function pushRectInfo(label, rect) {
        var centerX = rect.left + rect.width / 2;
        var centerYFromBottom = canvasHeight - (rect.top + rect.height / 2);
        resultLines.push(
            label + "：宽 " + Math.round(rect.width) + " 高 " + Math.round(rect.height) + " 中心(左下)=(" + Math.round(centerX) + ", " + Math.round(centerYFromBottom) + ")"
        );
    }

    var topRect = { left: 0, top: 0, width: canvasWidth, height: Math.max(0, selectionRect.top) };
    var bottomRect = {
        left: 0,
        top: Math.max(0, selectionRect.top + selectionRect.height),
        width: canvasWidth,
        height: Math.max(0, canvasHeight - (selectionRect.top + selectionRect.height)),
    };
    var leftRect = { left: 0, top: 0, width: Math.max(0, selectionRect.left), height: canvasHeight };
    var rightRect = {
        left: Math.max(0, selectionRect.left + selectionRect.width),
        top: 0,
        width: Math.max(0, canvasWidth - (selectionRect.left + selectionRect.width)),
        height: canvasHeight,
    };

    pushRectInfo("上方区域", topRect);
    pushRectInfo("下方区域", bottomRect);
    pushRectInfo("左侧区域", leftRect);
    pushRectInfo("右侧区域", rightRect);
    return resultLines;
}

export function updateInspectorForElement(targetDocument, targetElement) {
    if (!inspectorImportantTextAreaElement || !inspectorDetailsTextAreaElement) {
        return;
    }
    if (!targetDocument || !targetElement) {
        inspectorImportantTextAreaElement.value = "";
        inspectorDetailsTextAreaElement.value = "";
        clearTextAlignInspectorUi();
        return;
    }

    var inspectorData = buildElementInspectorText(targetDocument, targetElement);
    inspectorImportantTextAreaElement.value = inspectorData.importantText;
    inspectorDetailsTextAreaElement.value = inspectorData.detailsText;
    _updateTextAlignInspectorUi(targetDocument, targetElement);

    if (!state.isReverseRegionModeEnabled) {
        return;
    }

    var canvasRect = computeCanvasRectFromElement(targetDocument, targetElement);
    if (!canvasRect) {
        return;
    }
    var canvasSizeOption = getCanvasSizeByKey(state.currentSelectedCanvasSizeKey);
    var reverseInfoLines = buildReverseRegionInfoLines(canvasRect, canvasSizeOption);
    var mergedDetails = inspectorDetailsTextAreaElement.value ? inspectorDetailsTextAreaElement.value.split("\n") : [];
    mergedDetails.push("");
    mergedDetails.push("--- 反向区域 ---");
    for (var reverseIndex = 0; reverseIndex < reverseInfoLines.length; reverseIndex++) {
        mergedDetails.push(reverseInfoLines[reverseIndex]);
    }
    inspectorDetailsTextAreaElement.value = mergedDetails.join("\n");
}

export function updateInspectorForGroup(targetDocument, elementList) {
    if (!inspectorImportantTextAreaElement || !inspectorDetailsTextAreaElement) {
        return;
    }
    if (!targetDocument || !targetDocument.body || !elementList || elementList.length === 0) {
        inspectorImportantTextAreaElement.value = "";
        inspectorDetailsTextAreaElement.value = "";
        clearTextAlignInspectorUi();
        return;
    }

    var groupRect = computeGroupCanvasRect(targetDocument, elementList);
    if (!groupRect) {
        inspectorImportantTextAreaElement.value = "";
        inspectorDetailsTextAreaElement.value = "";
        return;
    }

    var canvasSizeOption = getCanvasSizeByKey(state.currentSelectedCanvasSizeKey);
    var canvasHeight = Number(canvasSizeOption.height || 0);

    var centerX = groupRect.left + groupRect.width / 2;
    var centerYFromBottom = canvasHeight - (groupRect.top + groupRect.height / 2);

    var previewScale = Number(state.currentPreviewScale || 1);
    if (!isFinite(previewScale) || previewScale <= 0) {
        previewScale = 1;
    }

    var importantLines = [];
    importantLines.push("画布：" + String(canvasSizeOption.label || canvasSizeOption.key || ""));
    var uiScaleText = "";
    if (targetDocument && targetDocument.defaultView && targetDocument.defaultView.getComputedStyle && targetDocument.documentElement) {
        var csRoot = targetDocument.defaultView.getComputedStyle(targetDocument.documentElement);
        var rawUiScale = csRoot ? String(csRoot.getPropertyValue("--ui-scale") || "").trim() : "";
        if (rawUiScale) {
            var uiScaleNum = Number(rawUiScale);
            if (isFinite(uiScaleNum) && uiScaleNum > 0) {
                uiScaleText = String(Math.round(uiScaleNum * 1000) / 1000);
            } else {
                uiScaleText = rawUiScale;
            }
        }
    }
    if (uiScaleText) {
        importantLines.push("UI缩放：--ui-scale×" + uiScaleText);
    }
    importantLines.push("组件：多选（" + elementList.length + "个）");
    importantLines.push(
        "整体尺寸：宽 " + Math.round(groupRect.width) + " 高 " + Math.round(groupRect.height) +
        "（预览显示：宽 " + Math.round(groupRect.width * previewScale) + " 高 " + Math.round(groupRect.height * previewScale) + "；舞台缩放×" + (Math.round(previewScale * 1000) / 1000) + "）"
    );
    importantLines.push(
        "整体坐标：中心(左下)=(" + Math.round(centerX) + ", " + Math.round(centerYFromBottom) + ")" +
        "（预览显示=(" + Math.round(centerX * previewScale) + ", " + Math.round(centerYFromBottom * previewScale) + ")）"
    );

    var detailLines = [];
    detailLines.push("说明：以上为所选组件整体包围框数据。");
    detailLines.push("所选组件：");

    var maxListCount = 30;
    for (var index = 0; index < elementList.length && index < maxListCount; index++) {
        detailLines.push("- " + resolvePreviewElementLabel(elementList[index]));
    }
    if (elementList.length > maxListCount) {
        detailLines.push("...（其余 " + (elementList.length - maxListCount) + " 个未展开）");
    }

    if (state.isReverseRegionModeEnabled) {
        var reverseInfoLines = buildReverseRegionInfoLines(groupRect, canvasSizeOption);
        detailLines.push("");
        detailLines.push("--- 反向区域 ---");
        for (var reverseIndex = 0; reverseIndex < reverseInfoLines.length; reverseIndex++) {
            detailLines.push(reverseInfoLines[reverseIndex]);
        }
    }

    inspectorImportantTextAreaElement.value = importantLines.join("\n");
    inspectorDetailsTextAreaElement.value = detailLines.join("\n");
    clearTextAlignInspectorUi();
}

