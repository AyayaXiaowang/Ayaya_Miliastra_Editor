import { dom } from "../dom_refs.js";
import { getCanvasSizeByKey } from "../config.js";
import { state } from "./state.js";
import { updateInspectorForElement, updateInspectorForGroup } from "./inspector.js";
import { updatePreviewSelectionOverlayForElement, updatePreviewSelectionOverlayForGroup } from "./overlays.js";
import { clearCurrentSelection } from "./selection.js";

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
        _refreshSelectionAfterCanvasSizeChange(state.previewDocument, canvasSizeOption);
    }
}

function _inferFlatKindPreferenceFromElement(el) {
    if (!el || !el.classList) {
        return "";
    }
    if (el.classList.contains("flat-text")) return "flat-text";
    if (el.classList.contains("flat-element")) return "flat-element";
    if (el.classList.contains("flat-border")) return "flat-border";
    if (el.classList.contains("flat-shadow")) return "flat-shadow";
    if (el.classList.contains("flat-button-anchor")) return "flat-button-anchor";
    return "";
}

function _isEffectivelyVisibleElement(targetDocument, el) {
    if (!targetDocument || !targetDocument.defaultView || !targetDocument.defaultView.getComputedStyle) {
        return false;
    }
    if (!el || !el.getBoundingClientRect) {
        return false;
    }
    var cs = targetDocument.defaultView.getComputedStyle(el);
    if (!cs) {
        return false;
    }
    if (String(cs.display || "") === "none") return false;
    if (String(cs.visibility || "") === "hidden") return false;
    var op = Number(cs.opacity);
    if (isFinite(op) && op <= 0.0001) return false;
    var r = el.getBoundingClientRect();
    if (!r || r.width <= 0 || r.height <= 0) return false;
    return true;
}

function _pickFlatElementByDebugLabel(areaElement, debugLabel, preferredKind, targetDocument) {
    if (!areaElement || !areaElement.querySelectorAll) {
        return null;
    }
    var dbg = String(debugLabel || "").trim();
    if (!dbg) {
        return null;
    }
    var preferred = String(preferredKind || "").trim();

    // 先收集所有同 debug-label 的候选
    var candidates = areaElement.querySelectorAll("[data-debug-label]");
    var matched = [];
    for (var i = 0; i < candidates.length; i++) {
        var el = candidates[i];
        if (!el) continue;
        var dbg2 = el.getAttribute ? String(el.getAttribute("data-debug-label") || "").trim() : "";
        if (dbg2 !== dbg) continue;
        if (!_isEffectivelyVisibleElement(targetDocument, el)) continue;
        matched.push(el);
    }
    if (matched.length <= 0) {
        return null;
    }
    if (!preferred) {
        return matched[0];
    }
    // 同一 debug-label 下优先保持“同类层”（例如 text->text）
    for (var j = 0; j < matched.length; j++) {
        var el2 = matched[j];
        if (el2 && el2.classList && el2.classList.contains(preferred)) {
            return el2;
        }
    }
    return matched[0];
}

function _resolveCurrentFlatDisplayArea(targetDocument, canvasSizeOption) {
    if (!targetDocument || !targetDocument.querySelector) {
        return null;
    }
    var key = String(canvasSizeOption && canvasSizeOption.key ? canvasSizeOption.key : "").trim();
    if (key) {
        var areaByKey = targetDocument.querySelector('.flat-display-area[data-size-key="' + key + '"]');
        if (areaByKey) {
            return areaByKey;
        }
    }
    return targetDocument.querySelector(".flat-display-area");
}

function _refreshSingleSelectionAfterCanvasSizeChange(targetDocument, canvasSizeOption) {
    var selected = state.currentSelectedPreviewElement;
    if (!selected) {
        return true;
    }
    // 非扁平化预览：保持引用即可（同一份 document），不做重定位。
    if (String(state.currentPreviewVariant || "") !== "flattened") {
        updatePreviewSelectionOverlayForElement(targetDocument, selected);
        updateInspectorForElement(targetDocument, selected);
        return true;
    }
    var dbg = selected && selected.getAttribute ? String(selected.getAttribute("data-debug-label") || "").trim() : "";
    if (!dbg) {
        return false;
    }
    var area = _resolveCurrentFlatDisplayArea(targetDocument, canvasSizeOption);
    if (!area) {
        return false;
    }
    var preferredKind = _inferFlatKindPreferenceFromElement(selected);
    var picked = _pickFlatElementByDebugLabel(area, dbg, preferredKind, targetDocument);
    if (!picked) {
        return false;
    }
    state.currentSelectedPreviewElement = picked;
    updatePreviewSelectionOverlayForElement(targetDocument, picked);
    updateInspectorForElement(targetDocument, picked);
    return true;
}

function _refreshGroupSelectionAfterCanvasSizeChange(targetDocument, canvasSizeOption) {
    var group = state.currentSelectedPreviewGroup;
    if (!group || group.length <= 0) {
        return true;
    }
    // 非扁平化预览：保持原集合引用（同一 document）。
    if (String(state.currentPreviewVariant || "") !== "flattened") {
        updatePreviewSelectionOverlayForGroup(targetDocument, group);
        updateInspectorForGroup(targetDocument, group);
        return true;
    }
    var area = _resolveCurrentFlatDisplayArea(targetDocument, canvasSizeOption);
    if (!area) {
        return false;
    }
    var next = [];
    for (var i = 0; i < group.length; i++) {
        var el = group[i];
        var dbg = el && el.getAttribute ? String(el.getAttribute("data-debug-label") || "").trim() : "";
        if (!dbg) {
            return false;
        }
        var preferredKind = _inferFlatKindPreferenceFromElement(el);
        var picked = _pickFlatElementByDebugLabel(area, dbg, preferredKind, targetDocument);
        if (!picked) {
            return false;
        }
        next.push(picked);
    }
    state.currentSelectedPreviewGroup = next;
    updatePreviewSelectionOverlayForGroup(targetDocument, next);
    updateInspectorForGroup(targetDocument, next);
    return true;
}

function _refreshSelectionAfterCanvasSizeChange(targetDocument, canvasSizeOption) {
    if (!targetDocument || !canvasSizeOption) {
        return;
    }
    var hasGroup = !!(state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0);
    if (hasGroup) {
        if (_refreshGroupSelectionAfterCanvasSizeChange(targetDocument, canvasSizeOption)) {
            return;
        }
        clearCurrentSelection();
        return;
    }
    if (_refreshSingleSelectionAfterCanvasSizeChange(targetDocument, canvasSizeOption)) {
        return;
    }
    clearCurrentSelection();
}

