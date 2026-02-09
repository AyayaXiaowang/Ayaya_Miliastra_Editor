import { PREVIEW_VARIANT_FLATTENED, PREVIEW_VARIANT_SOURCE } from "../config.js";
import { dom, state } from "./context.js";
import { getCheckedSelectionsInCatalogOrder } from "./storage.js";

export function resolveCurrentHtmlText() {
  if (!state.selected) return "";
  if (state.currentVariant === PREVIEW_VARIANT_SOURCE) {
    return String(state.selected.source_html || "");
  }
  // 扁平化预览：只允许渲染扁平化产物（由 renderPreview 统一确保已生成/缓存）。
  return String(state.selected.flattened_html || "");
}

export function canShowFlattened() {
  return !!(state.selected && state.selected.flattened_html);
}

export function updateVariantButtons() {
  if (!dom.previewVariantFlattenedButton) return;
  dom.previewVariantFlattenedButton.classList.toggle("active", state.currentVariant === PREVIEW_VARIANT_FLATTENED);
  if (dom.previewVariantSourceButton) {
    dom.previewVariantSourceButton.classList.toggle("active", state.currentVariant === PREVIEW_VARIANT_SOURCE);
  }
}

export function updateExportGiaButtonEnabled() {
  if (!dom.exportGiaButton) return;
  dom.exportGiaButton.disabled = !(state.apiConnected && state.selected && String(state.selected.source_html || "").trim());
}

export function updateExportGilButtonEnabled() {
  if (!dom.exportGilButton) return;
  var hasBaseGil = !!(
    (state.baseGilFile && state.baseGilFile.name) ||
    String(state.baseGilPath || "").trim()
  );
  var checkedSelections = getCheckedSelectionsInCatalogOrder();
  var canExportByChecked = checkedSelections && checkedSelections.length > 0;
  var canExportByCurrent = !!(state.selected && String(state.selected.source_html || "").trim());
  dom.exportGilButton.disabled = !(state.apiConnected && hasBaseGil && (canExportByChecked || canExportByCurrent));
}

export function updateImportVariableDefaultsButtonEnabled() {
  if (!dom.importVariableDefaultsButton) return;
  // 该动作不依赖基底 GIL。
  // 交互体验约定：即便未连接主程序，也允许点击按钮，并在右侧输出区给出明确原因；
  // 因此这里只按“是否选中且有源码”决定 enable，避免用户产生“点了没反应”的误解。
  dom.importVariableDefaultsButton.disabled = !(state.selected && String(state.selected.source_html || "").trim());
}

