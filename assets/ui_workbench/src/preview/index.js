import { PREVIEW_VARIANT_SOURCE } from "../config.js";
import { state } from "./state.js";
import { dom } from "../dom_refs.js";

export { formatColorTextAsHex } from "./color.js";
export { setPreviewOnlyModeEnabled, getPreviewOnlyModeEnabled } from "./ui.js";
export { setShadowInspectModeEnabled, getShadowInspectModeEnabled } from "./shadow_inspect.js";
export { applyCanvasSizeToPreviewDocument, updatePreviewStageScale, handleWindowResize, setSelectedCanvasSize } from "./scaling.js";
export { clearCurrentSelection, deleteSelectedPreviewElements, handleDeleteShortcutKeyDown, mountPreviewClickInspector, setReverseRegionModeEnabled, selectPreviewElement } from "./selection.js";
export { buildEmptyInputPlaceholderHtml, buildStatusPlaceholderHtml, ensurePreviewIsReadyForHtml, ensureComputePreviewIsReadyForHtml, refreshPreviewToRestoreDeletedElements, renderHtmlIntoPreview, renderHtmlIntoComputePreview, setComputePreviewCanvasSize, normalizeHtmlForSandboxedPreviewSrcDoc, resetComputePreviewHard } from "./render.js";

import { setPreviewOnlyModeEnabled, updatePreviewVariantButtonActiveState } from "./ui.js";
import { setShadowInspectModeEnabled } from "./shadow_inspect.js";
import { setSelectedCanvasSize } from "./scaling.js";
import { initializeTextAlignInspectorUi } from "./inspector.js";

export function getPreviewDocument() {
    if (state.previewDocument) {
        return state.previewDocument;
    }
    // 兜底：某些情况下 state.previewDocument 可能因“极快切换 srcdoc / load 时序”短暂为空，
    // 但 iframe.contentDocument 已就绪。这里做一次按需恢复，避免外层（分组树/列表选中）失效。
    var iframe = dom ? dom.previewIframeElement : null;
    var doc = iframe ? iframe.contentDocument : null;
    if (doc) {
        state.previewDocument = doc;
        return doc;
    }
    return null;
}

export function setDynamicTextPreviewEnabled(enabled) {
    state.isDynamicTextPreviewEnabled = !!enabled;
}

export function getDynamicTextPreviewEnabled() {
    return !!state.isDynamicTextPreviewEnabled;
}

export function getComputePreviewDocument() {
    return state.computePreviewDocument;
}

export function getPreviewLoadSequence() {
    return state.previewLoadSequence;
}

export function getCurrentSelectedCanvasSizeKey() {
    return state.currentSelectedCanvasSizeKey;
}

export function getLastRenderedHtmlText() {
    return state.lastRenderedHtmlText;
}

export function getLastRenderedSourceHtmlText() {
    return state.lastRenderedSourceHtmlText;
}

export function getCurrentPreviewVariant() {
    return state.currentPreviewVariant;
}

export function getCurrentSelectedPreviewElement() {
    return state.currentSelectedPreviewElement;
}

export function getCurrentSelectedPreviewGroup() {
    return state.currentSelectedPreviewGroup;
}

export function getReverseRegionModeEnabled() {
    return state.isReverseRegionModeEnabled;
}

export function setSelectionChangedCallback(callback) {
    state.onSelectionChanged = typeof callback === "function" ? callback : null;
}

export function initializePreviewUi() {
    // 入口初始化时，默认按钮态与内部状态保持一致
    state.currentPreviewVariant = PREVIEW_VARIANT_SOURCE;
    updatePreviewVariantButtonActiveState(PREVIEW_VARIANT_SOURCE);
    setSelectedCanvasSize(state.currentSelectedCanvasSizeKey);
    setPreviewOnlyModeEnabled(false);
    setShadowInspectModeEnabled(false);
    initializeTextAlignInspectorUi();
}


