import { dom } from "../dom_refs.js";
import { getCanvasSizeByKey } from "../config.js";
import { state } from "./state.js";
import { computeCanvasRectFromElement, computeGroupCanvasRect } from "./geometry.js";
import { resolvePreviewElementLabel } from "./labels.js";

var previewSelectionOverlayElement = dom.previewSelectionOverlayElement;
var previewSelectionBoxElement = dom.previewSelectionBoxElement;
var previewSelectionLabelElement = dom.previewSelectionLabelElement;
var previewDragSelectBoxElement = dom.previewDragSelectBoxElement;
var previewReverseTopElement = dom.previewReverseTopElement;
var previewReverseBottomElement = dom.previewReverseBottomElement;
var previewReverseLeftElement = dom.previewReverseLeftElement;
var previewReverseRightElement = dom.previewReverseRightElement;

export function hidePreviewSelectionOverlay() {
    if (previewSelectionBoxElement) {
        previewSelectionBoxElement.style.display = "none";
    }
    if (previewSelectionLabelElement) {
        previewSelectionLabelElement.style.display = "none";
    }
    if (previewDragSelectBoxElement) {
        previewDragSelectBoxElement.style.display = "none";
    }
    hideReverseRegionOverlays();
}

export function hideReverseRegionOverlays() {
    var reverseElementList = [
        previewReverseTopElement,
        previewReverseBottomElement,
        previewReverseLeftElement,
        previewReverseRightElement,
    ];
    for (var index = 0; index < reverseElementList.length; index++) {
        var element = reverseElementList[index];
        if (!element) {
            continue;
        }
        element.style.display = "none";
    }
}

export function renderOverlayBoxForCanvasRect(targetElement, canvasRect) {
    if (!targetElement || !canvasRect) {
        return;
    }
    var scale = Number(state.currentPreviewScale || 1);
    if (!isFinite(scale) || scale <= 0) {
        scale = 1;
    }
    var leftInStagePixels = canvasRect.left * scale;
    var topInStagePixels = canvasRect.top * scale;
    var widthInStagePixels = canvasRect.width * scale;
    var heightInStagePixels = canvasRect.height * scale;

    targetElement.style.left = leftInStagePixels.toFixed(2) + "px";
    targetElement.style.top = topInStagePixels.toFixed(2) + "px";
    targetElement.style.width = Math.max(0, widthInStagePixels).toFixed(2) + "px";
    targetElement.style.height = Math.max(0, heightInStagePixels).toFixed(2) + "px";
    targetElement.style.display = "block";
}

function updateReverseRegionOverlays(canvasRect) {
    if (!state.previewDocument) {
        hideReverseRegionOverlays();
        return;
    }
    if (!state.isReverseRegionModeEnabled || !canvasRect) {
        hideReverseRegionOverlays();
        return;
    }

    var canvasSizeOption = getCanvasSizeByKey(state.currentSelectedCanvasSizeKey);
    var canvasWidth = Number(canvasSizeOption.width || 0);
    var canvasHeight = Number(canvasSizeOption.height || 0);

    var topRect = {
        left: 0,
        top: 0,
        width: canvasWidth,
        height: Math.max(0, canvasRect.top),
    };
    var bottomRect = {
        left: 0,
        top: Math.max(0, canvasRect.top + canvasRect.height),
        width: canvasWidth,
        height: Math.max(0, canvasHeight - (canvasRect.top + canvasRect.height)),
    };
    var leftRect = {
        left: 0,
        top: 0,
        width: Math.max(0, canvasRect.left),
        height: canvasHeight,
    };
    var rightRect = {
        left: Math.max(0, canvasRect.left + canvasRect.width),
        top: 0,
        width: Math.max(0, canvasWidth - (canvasRect.left + canvasRect.width)),
        height: canvasHeight,
    };

    if (previewReverseTopElement) {
        renderOverlayBoxForCanvasRect(previewReverseTopElement, topRect);
    }
    if (previewReverseBottomElement) {
        renderOverlayBoxForCanvasRect(previewReverseBottomElement, bottomRect);
    }
    if (previewReverseLeftElement) {
        renderOverlayBoxForCanvasRect(previewReverseLeftElement, leftRect);
    }
    if (previewReverseRightElement) {
        renderOverlayBoxForCanvasRect(previewReverseRightElement, rightRect);
    }
}

export function updatePreviewSelectionOverlayForElement(targetDocument, targetElement) {
    if (!previewSelectionOverlayElement || !previewSelectionBoxElement || !previewSelectionLabelElement) {
        return;
    }
    if (!targetDocument || !targetElement || !targetElement.getBoundingClientRect) {
        hidePreviewSelectionOverlay();
        return;
    }
    if (!targetDocument.body) {
        hidePreviewSelectionOverlay();
        return;
    }

    function _parsePx(text) {
        var raw = String(text || "").trim().toLowerCase();
        if (!raw) return null;
        if (raw.endsWith("px")) raw = raw.slice(0, -2);
        var n = Number(raw);
        return isFinite(n) ? n : null;
    }

    function _computeFallbackCanvasRectFromFlattenedStyle(doc, el) {
        // When flattened layers are hidden via display:none, getBoundingClientRect() becomes zero.
        // For `.flat-*` layers we can still recover the intended rectangle from inline styles:
        // left/top/width/height are written as px in flattened output and share the same coordinate system
        // as the body (or `.flat-display-area` container if it has an offset).
        if (!doc || !doc.body || !el || !el.classList || !el.style) {
            return null;
        }
        if (
            !el.classList.contains("flat-shadow") &&
            !el.classList.contains("flat-border") &&
            !el.classList.contains("flat-element") &&
            !el.classList.contains("flat-text") &&
            !el.classList.contains("flat-button-anchor")
        ) {
            return null;
        }
        var left = _parsePx(el.style.left);
        var top = _parsePx(el.style.top);
        var width = _parsePx(el.style.width);
        var height = _parsePx(el.style.height);
        if (left === null || top === null || width === null || height === null) {
            return null;
        }
        if (!(width > 0) || !(height > 0)) {
            return null;
        }

        var baseLeft = 0;
        var baseTop = 0;
        var area = el.closest ? el.closest(".flat-display-area") : null;
        if (area && area.getBoundingClientRect) {
            var bodyRect = doc.body.getBoundingClientRect();
            var areaRect = area.getBoundingClientRect();
            if (bodyRect && areaRect) {
                baseLeft = Number(areaRect.left - bodyRect.left);
                baseTop = Number(areaRect.top - bodyRect.top);
                if (!isFinite(baseLeft)) baseLeft = 0;
                if (!isFinite(baseTop)) baseTop = 0;
            }
        }
        return {
            left: baseLeft + left,
            top: baseTop + top,
            width: Math.max(0, width),
            height: Math.max(0, height),
        };
    }

    var canvasRect = computeCanvasRectFromElement(targetDocument, targetElement);
    if (!canvasRect || !(canvasRect.width > 0) || !(canvasRect.height > 0)) {
        // Fallback for hidden flattened layers.
        canvasRect = _computeFallbackCanvasRectFromFlattenedStyle(targetDocument, targetElement);
    }
    if (!canvasRect) {
        hidePreviewSelectionOverlay();
        return;
    }
    renderOverlayBoxForCanvasRect(previewSelectionBoxElement, canvasRect);

    var labelText = resolvePreviewElementLabel(targetElement);
    previewSelectionLabelElement.textContent = labelText;

    var scale = Number(state.currentPreviewScale || 1);
    if (!isFinite(scale) || scale <= 0) {
        scale = 1;
    }

    var labelLeft = canvasRect.left * scale + 4;
    var labelTop = canvasRect.top * scale - 22;
    if (labelTop < 0) {
        labelTop = canvasRect.top * scale + 4;
    }
    if (labelLeft < 0) {
        labelLeft = 0;
    }
    if (labelTop < 0) {
        labelTop = 0;
    }

    previewSelectionLabelElement.style.left = labelLeft.toFixed(2) + "px";
    previewSelectionLabelElement.style.top = labelTop.toFixed(2) + "px";
    previewSelectionLabelElement.style.display = "block";

    updateReverseRegionOverlays(canvasRect);
}

export function updatePreviewSelectionOverlayForGroup(targetDocument, elementList) {
    if (!previewSelectionOverlayElement || !previewSelectionBoxElement || !previewSelectionLabelElement) {
        return;
    }
    var groupRect = computeGroupCanvasRect(targetDocument, elementList);
    if (!groupRect) {
        hidePreviewSelectionOverlay();
        return;
    }

    renderOverlayBoxForCanvasRect(previewSelectionBoxElement, groupRect);
    previewSelectionLabelElement.textContent = "多选（" + elementList.length + "个）";

    var scale = Number(state.currentPreviewScale || 1);
    if (!isFinite(scale) || scale <= 0) {
        scale = 1;
    }

    previewSelectionLabelElement.style.left = (groupRect.left * scale + 4).toFixed(2) + "px";
    var labelTop = groupRect.top * scale - 22;
    if (labelTop < 0) {
        labelTop = groupRect.top * scale + 4;
    }
    previewSelectionLabelElement.style.top = labelTop.toFixed(2) + "px";
    previewSelectionLabelElement.style.display = "block";

    updateReverseRegionOverlays(groupRect);
}
