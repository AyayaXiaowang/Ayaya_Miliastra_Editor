import { dom, setExportStatusText, state } from "./context.js";
import { renderExportWidgetPreviewHtml } from "./export_widgets_model.js";

function _cssEscapeText(text) {
  var raw = String(text || "");
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(raw);
  }
  return raw.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function _scrollExportWidgetIntoView(widgetId) {
  var wid = String(widgetId || "").trim();
  if (!wid) return;
  if (!dom.exportWidgetListContainer) return;
  var node = dom.exportWidgetListContainer.querySelector('[data-export-widget="1"][data-widget-id="' + _cssEscapeText(wid) + '"]');
  if (!node || !node.scrollIntoView) return;
  node.scrollIntoView({ block: "center" });
}

function _normalizeDebugLabelBase(raw) {
  var s = String(raw || "").trim();
  if (!s) return "";
  // 常见形式：text-xxx__r123_456_78_90（去重后附加矩形后缀）
  var i = s.indexOf("__r");
  if (i > 0) {
    s = s.slice(0, i);
  }
  return s;
}

function _getFlatRectFromElementStyle(el) {
  if (!el || !el.style) return null;
  function _parsePx(text) {
    var raw = String(text || "").trim().toLowerCase();
    if (!raw) return null;
    if (raw.endsWith("px")) raw = raw.slice(0, -2);
    var n = Number(raw);
    return isFinite(n) ? n : null;
  }
  var left = _parsePx(el.style.left);
  var top = _parsePx(el.style.top);
  var width = _parsePx(el.style.width);
  var height = _parsePx(el.style.height);
  if (left === null || top === null || width === null || height === null) return null;
  if (width <= 0 || height <= 0) return null;
  return { left: Number(left), top: Number(top), width: Number(width), height: Number(height) };
}

function _parseZIndexFromFlatElementStyle(el) {
  if (!el || !el.style) return 0;
  var raw = String(el.style.zIndex || "").trim().toLowerCase();
  if (!raw || raw === "auto") return 0;
  var n = Number(raw);
  if (!isFinite(n)) return 0;
  return Math.trunc(n);
}

function _rectIntersectionArea(a, b) {
  if (!a || !b) return 0;
  var left = Math.max(Number(a.left || 0), Number(b.left || 0));
  var top = Math.max(Number(a.top || 0), Number(b.top || 0));
  var right = Math.min(Number(a.left || 0) + Number(a.width || 0), Number(b.left || 0) + Number(b.width || 0));
  var bottom = Math.min(Number(a.top || 0) + Number(a.height || 0), Number(b.top || 0) + Number(b.height || 0));
  var w = right - left;
  var h = bottom - top;
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return 0;
  return w * h;
}

function _areaOfRect(r) {
  if (!r) return 0;
  var w = Number(r.width || 0);
  var h = Number(r.height || 0);
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return 0;
  return w * h;
}

function _findWidgetById(model, widgetId) {
  var wid = String(widgetId || "").trim();
  if (!wid) return null;
  var m = model || null;
  if (!m || !m.groups) return null;
  var groups = m.groups || [];
  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      if (String(w.widget_id || "").trim() === wid) {
        return w;
      }
    }
  }
  return null;
}

function _findBestWidgetIdByDebugLabelAndRect(model, debugLabelBase, selectedRect, selectedZ) {
  var m = model || null;
  var key = String(debugLabelBase || "").trim();
  if (!m || !m.groups || !key || !selectedRect) return "";

  var groups = m.groups || [];
  var bestWid = "";
  var bestRatio = -1;
  var bestZDist = Number.POSITIVE_INFINITY;
  var bestAreaDist = Number.POSITIVE_INFINITY;

  var aSel = _areaOfRect(selectedRect);
  var z0 = Number(selectedZ || 0);
  if (!isFinite(z0)) z0 = 0;

  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var wid = String(w.widget_id || "").trim();
      if (!wid) continue;
      var wn = String(w.widget_name || "");
      // 关键：优先用 widget_name 做确定性筛选（例如 “文本_text-level-name”）
      if (wn.indexOf(key) < 0 && wn.indexOf("文本_" + key) < 0 && wn.indexOf("_" + key) < 0) {
        // 兜底：有些命名可能为 “文本_<debug_label>...”，这里用 includes 即可
        if (wn.indexOf(key) < 0) {
          continue;
        }
      }
      var wr = w.rect || null;
      if (!wr) continue;
      var inter = _rectIntersectionArea(selectedRect, wr);
      if (!(inter > 0)) continue;
      var aWid = _areaOfRect(wr);
      if (!(aSel > 0) || !(aWid > 0)) continue;
      var ratio = inter / Math.min(aSel, aWid);
      var z1 = Number(w.layer_index !== undefined ? w.layer_index : 0);
      if (!isFinite(z1)) z1 = 0;
      var zDist = Math.abs(z1 - z0);
      var areaDist = Math.abs(aWid - aSel);

      if (ratio > bestRatio + 1e-9) {
        bestRatio = ratio;
        bestZDist = zDist;
        bestAreaDist = areaDist;
        bestWid = wid;
        continue;
      }
      if (Math.abs(ratio - bestRatio) <= 1e-9) {
        if (zDist < bestZDist - 1e-9) {
          bestZDist = zDist;
          bestAreaDist = areaDist;
          bestWid = wid;
          continue;
        }
        if (Math.abs(zDist - bestZDist) <= 1e-9) {
          if (areaDist < bestAreaDist - 1e-6) {
            bestAreaDist = areaDist;
            bestWid = wid;
            continue;
          }
        }
      }
    }
  }
  return String(bestWid || "").trim();
}

function _findBestWidgetIdByRectOnly(model, selectedRect, selectedZ) {
  var m = model || null;
  if (!m || !m.groups || !selectedRect) return "";
  var groups = m.groups || [];

  var aSel = _areaOfRect(selectedRect);
  if (!(aSel > 0)) return "";
  var z0 = Number(selectedZ || 0);
  if (!isFinite(z0)) z0 = 0;

  var bestWid = "";
  var bestRatio = -1;
  var bestZDist = Number.POSITIVE_INFINITY;
  var bestAreaDist = Number.POSITIVE_INFINITY;

  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var wid = String(w.widget_id || "").trim();
      if (!wid) continue;
      var wr = w.rect || null;
      if (!wr) continue;
      var inter = _rectIntersectionArea(selectedRect, wr);
      if (!(inter > 0)) continue;
      var aWid = _areaOfRect(wr);
      if (!(aWid > 0)) continue;
      var ratio = inter / Math.min(aSel, aWid);
      // 极保守：至少 90% 覆盖才认为是“同一控件”
      if (ratio < 0.9) continue;

      var z1 = Number(w.layer_index !== undefined ? w.layer_index : 0);
      if (!isFinite(z1)) z1 = 0;
      var zDist = Math.abs(z1 - z0);
      var areaDist = Math.abs(aWid - aSel);

      if (ratio > bestRatio + 1e-9) {
        bestRatio = ratio;
        bestZDist = zDist;
        bestAreaDist = areaDist;
        bestWid = wid;
        continue;
      }
      if (Math.abs(ratio - bestRatio) <= 1e-9) {
        if (zDist < bestZDist - 1e-9) {
          bestZDist = zDist;
          bestAreaDist = areaDist;
          bestWid = wid;
          continue;
        }
        if (Math.abs(zDist - bestZDist) <= 1e-9) {
          if (areaDist < bestAreaDist - 1e-6) {
            bestAreaDist = areaDist;
            bestWid = wid;
            continue;
          }
        }
      }
    }
  }
  return String(bestWid || "").trim();
}

function _findWidgetIdByExactFlatLayerKey(layerKey) {
  var lk = String(layerKey || "").trim();
  if (!lk) return "";
  var model = state.exportWidgetPreviewModel;
  if (!model) return "";
  var groups = model.groups || [];
  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      if (String(w.flat_layer_key || "").trim() === lk) {
        return String(w.widget_id || "").trim();
      }
    }
  }
  return "";
}

function _applyExportWidgetSelectionFromPreviewElement(flatEl) {
  var selectedLayerKey = String((flatEl && flatEl.dataset && flatEl.dataset.layerKey) ? flatEl.dataset.layerKey : "").trim();
  if (!selectedLayerKey) {
    return;
  }
  var selectedDebugLabel = _normalizeDebugLabelBase(
    String(
      (flatEl && flatEl.dataset && (flatEl.dataset.debugLabel || flatEl.dataset.debug_label)) ? (flatEl.dataset.debugLabel || flatEl.dataset.debug_label) :
      (flatEl && flatEl.getAttribute ? (flatEl.getAttribute("data-debug-label") || "") : "")
    )
  );
  var selectedRect = _getFlatRectFromElementStyle(flatEl);
  var selectedZ = _parseZIndexFromFlatElementStyle(flatEl);

  var wid = "";
  if (state.exportWidgetIdByLayerKey) {
    var direct = state.exportWidgetIdByLayerKey[selectedLayerKey];
    if (direct) {
      wid = String(direct || "").trim();
    }
  }
  // 双保险：直接扫描 model 做 exact flat_layer_key 匹配（即便 index 因缓存/时序没更新也能命中）
  if (!wid) {
    wid = _findWidgetIdByExactFlatLayerKey(selectedLayerKey);
  }
  // 补强：当“画布点选的 flat 层”本身不是 widget.flat_layer_key（常见：点到 element 主体层/装饰层），
  // 仍尝试用 debug_label + rect 或（极保守）rect-only 反推一个最可能的 widget。
  if (!wid && selectedRect) {
    var modelX = state.exportWidgetPreviewModel;
    if (selectedDebugLabel) {
      wid = _findBestWidgetIdByDebugLabelAndRect(modelX, selectedDebugLabel, selectedRect, selectedZ);
    }
    if (!wid) {
      wid = _findBestWidgetIdByRectOnly(modelX, selectedRect, selectedZ);
    }
  }
  // 防回归：当“layerKey -> widgetId”因归一化/重叠导致误映射时，用 debug_label + rect 做一次受控纠正。
  // 典型：点击 text-level-name 却跳到 text-level-author。
  if (wid && selectedDebugLabel && selectedRect) {
    var model0 = state.exportWidgetPreviewModel;
    var chosen = _findWidgetById(model0, wid);
    var wn0 = chosen ? String(chosen.widget_name || "") : "";
    if (wn0 && wn0.indexOf(selectedDebugLabel) < 0) {
      var fallbackWid = _findBestWidgetIdByDebugLabelAndRect(model0, selectedDebugLabel, selectedRect, selectedZ);
      if (fallbackWid && fallbackWid !== wid) {
        wid = fallbackWid;
      }
    }
  }

  if (!wid) {
    if (state.exportSelectedWidgetId) {
      state.exportSelectedWidgetId = "";
      state.pendingScrollExportWidgetId = "";
      if (dom.exportWidgetListContainer && state.exportWidgetPreviewModel) {
        dom.exportWidgetListContainer.innerHTML = renderExportWidgetPreviewHtml(state.exportWidgetPreviewModel);
      }
    }
    setExportStatusText([
      "[选中映射] 该扁平层无对应导出控件（不回退）。",
      "说明：并非所有扁平层都会生成导出控件（装饰层/附属层/被合并层通常无映射）。",
      "- layer_key: " + String(selectedLayerKey || ""),
    ].join("\n"));
    if (typeof window !== "undefined") {
      window.__wb_last_selection_mapping_error = {
        kind: "flat_layer_has_no_export_widget_mapping",
        layer_key: String(selectedLayerKey || ""),
      };
    }
    return;
  }

  state.exportSelectedWidgetId = String(wid || "");
  state.pendingScrollExportWidgetId = String(wid || "");
  if (dom.exportWidgetListContainer && state.exportWidgetPreviewModel) {
    dom.exportWidgetListContainer.innerHTML = renderExportWidgetPreviewHtml(state.exportWidgetPreviewModel);
  }
  if (state.leftBottomTabMode === "export_widgets") {
    if (!state.suppressNextExportWidgetAutoScroll) {
      _scrollExportWidgetIntoView(wid);
    }
    state.pendingScrollExportWidgetId = "";
  }
  // 只抑制一次（用于“列表点击 -> 画布高亮 -> selection_changed 回流”）
  state.suppressNextExportWidgetAutoScroll = false;
}

export function handlePreviewSelectionChangedForLeftBottomPanels(payload) {
  var p = payload || {};
  if (String(p.kind || "") !== "element") {
    return;
  }
  var el = p.element || null;
  if (!el) return;

  // 仅扁平层才有稳定 rect/groupKey（导出控件列表也只对齐扁平坐标系）。
  // 注意：预览 click 选中时可能落在 flat 层内部子节点（例如图标/文字子节点），
  // 此时 payload.element 不一定自带 flat-* class；这里把它规整到最近的 flat 层容器，
  // 否则会出现“画布能选中，但左下导出控件不跳转”的体验问题。
  if (el && !el.classList && el.nodeType === 1) {
    // 极端情况下：某些元素没有 classList（老环境/异常节点），直接拒绝。
  }
  if (el && el.classList && typeof el.closest === "function") {
    if (
      !el.classList.contains("flat-shadow") &&
      !el.classList.contains("flat-border") &&
      !el.classList.contains("flat-element") &&
      !el.classList.contains("flat-text") &&
      !el.classList.contains("flat-button-anchor")
    ) {
      var parentFlat = el.closest(".flat-shadow, .flat-border, .flat-element, .flat-text, .flat-button-anchor");
      if (parentFlat) {
        el = parentFlat;
      }
    }
  }
  if (!el || !el.classList) return;
  if (
    !el.classList.contains("flat-shadow") &&
    !el.classList.contains("flat-border") &&
    !el.classList.contains("flat-element") &&
    !el.classList.contains("flat-text") &&
    !el.classList.contains("flat-button-anchor")
  ) return;

  _applyExportWidgetSelectionFromPreviewElement(el);
}

