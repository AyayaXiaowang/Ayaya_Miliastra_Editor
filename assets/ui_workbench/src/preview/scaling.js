import { dom } from "../dom_refs.js";
import { getCanvasSizeByKey } from "../config.js";
import { state } from "./state.js";
import { updateInspectorForElement, updateInspectorForGroup } from "./inspector.js";
import { updatePreviewSelectionOverlayForElement, updatePreviewSelectionOverlayForGroup } from "./overlays.js";

var previewIframeElement = dom.previewIframeElement;
var previewFrameContainerElement = dom.previewFrameContainerElement;
var previewStageElement = dom.previewStageElement;

function updateCanvasSizeButtonActiveState(canvasSizeKey) {
    var buttonList = document.querySelectorAll("button[data-size-key]");
    if (!buttonList || buttonList.length <= 0) {
        return;
    }
    for (var index = 0; index < buttonList.length; index++) {
        var button = buttonList[index];
        if (!button || !button.dataset) {
            continue;
        }
        var key = String(button.dataset.sizeKey || "");
        button.classList.toggle("active", key === canvasSizeKey);
    }
}

export function applyCanvasSizeToPreviewDocument(targetDocument, canvasSizeOption) {
    if (!targetDocument || !targetDocument.documentElement) {
        return;
    }

    var isCompactMode = Number(canvasSizeOption.height || 0) <= 750;
    targetDocument.documentElement.style.setProperty("--canvas-width", canvasSizeOption.width + "px");
    targetDocument.documentElement.style.setProperty("--canvas-height", canvasSizeOption.height + "px");
    targetDocument.documentElement.style.setProperty("--content-width", canvasSizeOption.width + "px");
    // 兼容：大量 UI HTML 依赖 `--ui-scale` 进行响应式尺寸计算。
    // 但纯 CSS 想从 `--canvas-width/--canvas-height` 推导“无单位比例”会触发 length/length 除法，
    // 在部分浏览器实现下会导致 `var(--ui-scale)` 参与 calc 时整体失效，从而出现“空 div 高度=0 被扁平化跳过”的问题。
    //
    // 因此 Workbench 侧在应用画布尺寸时同步注入一个确定性的数值 scale，作为预览/扁平化/导出链路的稳定真源。
    var w = Number(canvasSizeOption.width || 0);
    var h = Number(canvasSizeOption.height || 0);
    var sx = w > 0 ? (w / 1920.0) : 1;
    var sy = h > 0 ? (h / 1080.0) : 1;
    var s = Math.min(sx, sy);
    if (!isFinite(s) || s <= 0) {
        s = 1;
    }
    if (s < 0.75) {
        s = 0.75;
    }
    // 用更短的小数文本，避免写入过长导致 diff 噪音（也更易读）。
    targetDocument.documentElement.style.setProperty("--ui-scale", String(Math.round(s * 10000) / 10000));
    if (targetDocument.body) {
        targetDocument.body.setAttribute("data-size-mode", isCompactMode ? "compact" : "standard");
        targetDocument.body.style.overflow = "hidden";
    }

    // If current preview content is a flattened page, show the area for current size.
    var flatAreaNodeList = targetDocument.querySelectorAll ? targetDocument.querySelectorAll(".flat-display-area") : [];
    if (flatAreaNodeList && flatAreaNodeList.length > 0) {
        for (var areaIndex = 0; areaIndex < flatAreaNodeList.length; areaIndex++) {
            var flatAreaElement = flatAreaNodeList[areaIndex];
            if (!flatAreaElement || !flatAreaElement.dataset) {
                continue;
            }
            var areaSizeKey = String(flatAreaElement.dataset.sizeKey || "");
            if (areaSizeKey) {
                flatAreaElement.style.display = areaSizeKey === canvasSizeOption.key ? "block" : "none";
                continue;
            }
            var areaSizeLabel = String(flatAreaElement.dataset.size || "");
            flatAreaElement.style.display = areaSizeLabel === String(canvasSizeOption.label || "") ? "block" : "none";
        }
    }
}

export function updatePreviewStageScale(canvasSizeOption) {
    if (!previewFrameContainerElement || !previewIframeElement || !previewStageElement) {
        return;
    }

    var containerWidth = previewFrameContainerElement.clientWidth;
    var containerHeight = previewFrameContainerElement.clientHeight;
    if (containerWidth <= 0 || containerHeight <= 0) {
        return;
    }

    var scaleX = containerWidth / canvasSizeOption.width;
    var scaleY = containerHeight / canvasSizeOption.height;
    var scale = Math.min(scaleX, scaleY);
    if (!isFinite(scale) || scale <= 0) {
        scale = 1;
    }
    if (scale > 1) {
        scale = 1;
    }
    state.currentPreviewScale = scale;

    var stageWidth = canvasSizeOption.width * scale;
    var stageHeight = canvasSizeOption.height * scale;
    previewStageElement.style.width = stageWidth.toFixed(2) + "px";
    previewStageElement.style.height = stageHeight.toFixed(2) + "px";

    previewIframeElement.style.width = canvasSizeOption.width + "px";
    previewIframeElement.style.height = canvasSizeOption.height + "px";
    previewIframeElement.style.transformOrigin = "0 0";
    previewIframeElement.style.transform = "scale(" + scale.toFixed(5) + ")";

    if (state.previewDocument && state.currentSelectedPreviewElement) {
        updatePreviewSelectionOverlayForElement(state.previewDocument, state.currentSelectedPreviewElement);
    }
    if (state.previewDocument && state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
        updatePreviewSelectionOverlayForGroup(state.previewDocument, state.currentSelectedPreviewGroup);
    }
}

export function handleWindowResize() {
    updatePreviewStageScale(getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
}

export function setSelectedCanvasSize(canvasSizeKey) {
    var key = String(canvasSizeKey || "").trim();
    if (!key) {
        return;
    }

    state.currentSelectedCanvasSizeKey = key;
    updateCanvasSizeButtonActiveState(key);

    var canvasSizeOption = getCanvasSizeByKey(key);
    updatePreviewStageScale(canvasSizeOption);

    if (state.previewDocument) {
        applyCanvasSizeToPreviewDocument(state.previewDocument, canvasSizeOption);
        updatePreviewStageScale(canvasSizeOption);
        if (state.currentSelectedPreviewElement) {
            updatePreviewSelectionOverlayForElement(state.previewDocument, state.currentSelectedPreviewElement);
            updateInspectorForElement(state.previewDocument, state.currentSelectedPreviewElement);
        }
        if (state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
            updatePreviewSelectionOverlayForGroup(state.previewDocument, state.currentSelectedPreviewGroup);
            updateInspectorForGroup(state.previewDocument, state.currentSelectedPreviewGroup);
        }
    }
}

