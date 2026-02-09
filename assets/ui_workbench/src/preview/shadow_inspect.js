import { dom } from "../dom_refs.js";
import { state } from "./state.js";

var toggleShadowInspectButtonElement = dom.toggleShadowInspectButtonElement;

function ensureShadowInspectStyle(targetDocument) {
    if (!targetDocument || !targetDocument.head) {
        return;
    }
    var styleId = "ui-html-workbench-shadow-inspect";
    var existing = targetDocument.getElementById(styleId);
    if (existing) {
        return;
    }
    var styleElement = targetDocument.createElement("style");
    styleElement.id = styleId;
    styleElement.textContent = [
        "/* injected by ui_html_workbench: shadow inspect */",
        ".flat-element, .flat-border, .flat-text {",
        "  display: none !important;",
        "}",
        ".flat-shadow {",
        "  outline: 1px solid rgba(55, 148, 255, 0.55) !important;",
        "  background-color: rgba(14,14,14,0.65) !important;",
        "}",
    ].join("\n");
    targetDocument.head.appendChild(styleElement);
}

export function applyShadowInspectModeToPreviewDocument(targetDocument) {
    if (!targetDocument) {
        return;
    }
    var styleId = "ui-html-workbench-shadow-inspect";
    var existing = targetDocument.getElementById ? targetDocument.getElementById(styleId) : null;
    if (state.isShadowInspectModeEnabled) {
        ensureShadowInspectStyle(targetDocument);
        return;
    }
    if (existing && existing.parentNode) {
        existing.parentNode.removeChild(existing);
    }
}

export function setShadowInspectModeEnabled(enabled) {
    state.isShadowInspectModeEnabled = !!enabled;
    if (toggleShadowInspectButtonElement) {
        toggleShadowInspectButtonElement.textContent = "阴影检查：" + (state.isShadowInspectModeEnabled ? "开" : "关");
    }
    if (state.previewDocument) {
        applyShadowInspectModeToPreviewDocument(state.previewDocument);
    }
}

export function getShadowInspectModeEnabled() {
    return !!state.isShadowInspectModeEnabled;
}

