import { dom } from "./context.js";

function _escapeAttrValueForSelector(text) {
  var raw = String(text || "");
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(raw);
  }
  // Fallback：用于属性选择器的双引号包裹场景
  return raw.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

export function findExportWidgetRowElementByWidgetId(widgetId) {
  var wid = String(widgetId || "").trim();
  if (!wid) return null;
  if (!dom.exportWidgetListContainer || !dom.exportWidgetListContainer.querySelector) return null;
  return dom.exportWidgetListContainer.querySelector(
    '[data-export-widget="1"][data-widget-id="' + _escapeAttrValueForSelector(wid) + '"]'
  );
}

export function clearExportWidgetListSelectionDom() {
  if (!dom.exportWidgetListContainer || !dom.exportWidgetListContainer.querySelectorAll) return;
  var selected = dom.exportWidgetListContainer.querySelectorAll(".wb-tree-item.selected");
  for (var i = 0; i < selected.length; i++) {
    if (selected[i] && selected[i].classList) {
      selected[i].classList.remove("selected");
    }
  }
}

export function updateExportWidgetListSelectionDom(widgetId) {
  clearExportWidgetListSelectionDom();
  var row = findExportWidgetRowElementByWidgetId(widgetId);
  if (!row) return null;
  if (row.classList) row.classList.add("selected");
  var details = row.closest ? row.closest("details") : null;
  if (details) details.open = true;
  return row;
}

export function scrollExportWidgetRowIntoView(widgetId) {
  var row = findExportWidgetRowElementByWidgetId(widgetId);
  if (!row) return false;
  var details = row.closest ? row.closest("details") : null;
  if (details) details.open = true;
  if (!row.scrollIntoView) return false;
  row.scrollIntoView({ block: "center" });
  return true;
}

export function applyExportWidgetRowFlatLayerKeysFromModel(model) {
  var m = model || null;
  if (!m || !m.groups) return 0;
  if (!dom.exportWidgetListContainer || !dom.exportWidgetListContainer.querySelectorAll) return 0;

  var widToKey = {};
  var uiKeyToKey = {};
  var groups = m.groups || [];
  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var wid = String(w.widget_id || "").trim();
      if (!wid) continue;
      widToKey[wid] = String(w.flat_layer_key || "").trim();
      var uiKey = String(w.ui_key || "").trim();
      if (uiKey) {
        uiKeyToKey[uiKey] = String(w.flat_layer_key || "").trim();
      }
    }
  }

  var rows = dom.exportWidgetListContainer.querySelectorAll('[data-export-widget="1"][data-widget-id]');
  var updated = 0;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (!row || !row.getAttribute) continue;
    // 优先使用稳定身份 ui_key（跨刷新/跨尺寸更稳定）；无 ui_key 时再回退 widget_id。
    var uiKey0 = String(row.getAttribute("data-ui-key") || "").trim();
    var wid0 = String(row.getAttribute("data-widget-id") || "").trim();
    if (!uiKey0 && !wid0) continue;
    var nextKey = "";
    if (uiKey0 && uiKeyToKey[uiKey0] !== undefined) {
      nextKey = String(uiKeyToKey[uiKey0] || "");
    } else if (wid0 && widToKey[wid0] !== undefined) {
      nextKey = String(widToKey[wid0] || "");
    }
    // 只更新关键字段：避免 innerHTML 重绘导致 scroll/details.open/选中样式丢失。
    row.setAttribute("data-flat-layer-key", nextKey);
    updated += 1;
  }
  return updated;
}
