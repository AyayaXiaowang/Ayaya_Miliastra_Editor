import { dom, state } from "./context.js";
import { renderExportWidgetPreviewHtml } from "./export_widgets_model.js";
import { scrollExportWidgetRowIntoView, updateExportWidgetListSelectionDom } from "./export_widget_list_dom.js";

let _scheduledSeq = 0;

function _applySelectionAndPendingScrollAfterRerender() {
  // 说明：
  // - 任何一次 innerHTML 重绘都会丢失选中样式与 details.open；
  // - 预览点选可能发生在“列表尚未渲染/正在重绘”的时序中；
  // - 因此这里统一在重绘后做一次“选中恢复 + 可选滚动”补强。
  var selectedId = String(state.exportSelectedWidgetId || "").trim();
  if (selectedId) {
    updateExportWidgetListSelectionDom(selectedId);
  }

  // pendingScroll：只在当前 Tab=导出控件 且未被 suppress 时尝试滚动；
  // 若滚动失败（DOM 尚未有该行），保留 pendingScroll 供后续重绘/切 Tab 消费。
  if (state.leftBottomTabMode !== "export_widgets") {
    return;
  }
  if (state.suppressNextExportWidgetAutoScroll) {
    return;
  }
  var pendingId = String(state.pendingScrollExportWidgetId || "").trim();
  if (!pendingId) {
    return;
  }
  var ok = scrollExportWidgetRowIntoView(pendingId);
  if (ok) {
    state.pendingScrollExportWidgetId = "";
  }
}

export function rerenderExportWidgetListFromModelNow(model) {
  if (!dom.exportWidgetListContainer) {
    return false;
  }
  var m = model || state.exportWidgetPreviewModel;
  if (!m) {
    return false;
  }
  dom.exportWidgetListContainer.innerHTML = renderExportWidgetPreviewHtml(m);
  _applySelectionAndPendingScrollAfterRerender();
  return true;
}

export function rerenderExportWidgetListFromCurrentModelNow() {
  return rerenderExportWidgetListFromModelNow(state.exportWidgetPreviewModel);
}

export function scheduleRerenderExportWidgetListFromCurrentModel() {
  var seq = (_scheduledSeq += 1);
  // requestAnimationFrame：避免在 click 栈内同步 innerHTML 重绘导致 element detached（Playwright/浏览器更稳）。
  window.requestAnimationFrame(function () {
    if (seq !== _scheduledSeq) return;
    rerenderExportWidgetListFromCurrentModelNow();
  });
}

