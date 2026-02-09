import { dom } from "../dom_refs.js";
import { PREVIEW_VARIANT_FLATTENED, PREVIEW_VARIANT_SOURCE } from "../config.js";
import { state } from "./state.js";
import { updatePreviewStageScale } from "./scaling.js";
import { getCanvasSizeByKey } from "../config.js";

var previewVariantSourceButtonElement = dom.previewVariantSourceButtonElement;
var previewVariantFlattenedButtonElement = dom.previewVariantFlattenedButtonElement;
var togglePreviewOnlyModeButtonElement = dom.togglePreviewOnlyModeButtonElement;

// NOTE:
// 专注模式只影响“Workbench 外层面板”的可见性，不应复用 workbenchMode（browse/editor）。
// 因此使用独立的 data-preview-only="1" 作为 UI 展示状态。

export function updatePreviewVariantButtonActiveState(previewVariant) {
  var key = previewVariant === PREVIEW_VARIANT_FLATTENED ? PREVIEW_VARIANT_FLATTENED : PREVIEW_VARIANT_SOURCE;
  if (previewVariantSourceButtonElement && previewVariantSourceButtonElement.classList) {
    previewVariantSourceButtonElement.classList.toggle("active", key === PREVIEW_VARIANT_SOURCE);
  }
  if (previewVariantFlattenedButtonElement && previewVariantFlattenedButtonElement.classList) {
    previewVariantFlattenedButtonElement.classList.toggle("active", key === PREVIEW_VARIANT_FLATTENED);
  }
}

export function setPreviewOnlyModeEnabled(enabled) {
  var flag = !!enabled;
  var wasEnabled = !!state.isPreviewOnlyModeEnabled;
  if (flag === wasEnabled) {
    return;
  }
  state.isPreviewOnlyModeEnabled = flag;
  if (document && document.body && document.body.dataset) {
    if (flag) {
      document.body.dataset.previewOnly = "1";
    } else {
      delete document.body.dataset.previewOnly;
    }
  }
  if (togglePreviewOnlyModeButtonElement) {
    togglePreviewOnlyModeButtonElement.title = flag ? "退出专注模式" : "专注模式 (隐藏面板)";
  }
  window.requestAnimationFrame(function () {
    updatePreviewStageScale(getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
  });
}

export function getPreviewOnlyModeEnabled() {
  return !!state.isPreviewOnlyModeEnabled;
}
