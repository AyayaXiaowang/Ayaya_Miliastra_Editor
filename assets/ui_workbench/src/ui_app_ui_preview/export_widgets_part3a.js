import * as preview from "../preview/index.js";
import { flattenGroupTreeController, state } from "./context.js";
import { parseLayerKey } from "../layer_key.js";
import { getFlatRectFromElementStyle, parseZIndexFromFlatElementStyle, scoreWidgetMatchForFlatSelection } from "../geometry/rect_match.js";

export function normalizeExportWidgetPreviewModelFlatLayerKeysByPreviewDom(model) {
  // 目的：让导出控件列表里的 flat_layer_key 与“真实扁平化预览 DOM”一致。
  //
  // 该归一化只作用于“预览页的列表模型”，不影响导出 payload。
  if (!model || !model.groups) return;
  if (!flattenGroupTreeController || typeof flattenGroupTreeController.indexFlattenedPreviewElements !== "function") return;
  if (typeof flattenGroupTreeController.findPreviewElementByLayerKey !== "function") return;

  // 确保 dataset.layerKey 已写入（find 依赖该索引）
  flattenGroupTreeController.indexFlattenedPreviewElements();

  var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
  if (!doc || !doc.querySelector) return;
  var sizeKey = String(preview.getCurrentSelectedCanvasSizeKey ? preview.getCurrentSelectedCanvasSizeKey() : "");
  var area = sizeKey ? doc.querySelector('.flat-display-area[data-size-key="' + String(sizeKey) + '"]') : null;
  if (!area) area = doc.querySelector(".flat-display-area");
  if (!area) return;

  var groups = model.groups || [];

  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var lk = String(w.flat_layer_key || "").trim();
      if (!lk) continue;

      // 1) 先尝试直接 find（可处理轻微 z/舍入差异）
      var el = flattenGroupTreeController.findPreviewElementByLayerKey(lk);
      var actual = (el && el.dataset) ? String(el.dataset.layerKey || "").trim() : "";
      if (actual && actual !== lk) {
        w.flat_layer_key = actual;
        continue;
      }
      if (actual) {
        continue;
      }
      // 2) find 失败：保持原 key，不做“按 rect/z 猜测”的强行归一化。
      // 原因：猜测会把多个 widget 错映射到同一个 layerKey，进而导致：
      // - 隐藏一个条目，其他无关条目也显示为隐藏
      // - 点击隐藏无效果（实际隐藏的不是该条目对应的真实层）
      // 这里选择“严格一致性优先”：宁可保持原 key 并在定位时显示明确失败提示，也不做错误归一化。
    }
  }
}

export function rebuildExportWidgetIdByLayerKeyIndex() {
  var model = state.exportWidgetPreviewModel;
  if (!model) {
    state.exportWidgetIdByLayerKey = {};
    return;
  }
  var groups = model.groups || [];
  var map = {}; // layerKey -> { widget_id, score }

  function consider(layerKey, widgetId, selectedRect, selectedZ, widgetRect, widgetZ, boost) {
    var lk = String(layerKey || "").trim();
    var wid = String(widgetId || "").trim();
    if (!lk || !wid) return;
    var score = scoreWidgetMatchForFlatSelection(selectedRect, selectedZ, widgetRect, widgetZ);
    if (!score) return;
    // "boost" is used to prefer explicit __flat_layer_key mapping.
    if (boost === true) {
      score.ratio = score.ratio + 10.0;
    }
    if (!map[lk]) {
      map[lk] = { widget_id: wid, score: score };
      return;
    }
    var cur = map[lk];
    var best = cur.score;
    var s = score;
    // Same tuple compare as selection-time matcher
    if (s.ratio > best.ratio + 1e-9) {
      map[lk] = { widget_id: wid, score: s };
      return;
    }
    if (Math.abs(s.ratio - best.ratio) <= 1e-9) {
      if (s.zDist < best.zDist - 1e-9) {
        map[lk] = { widget_id: wid, score: s };
        return;
      }
      if (Math.abs(s.zDist - best.zDist) <= 1e-9) {
        if (s.areaDist < best.areaDist - 1e-6) {
          map[lk] = { widget_id: wid, score: s };
          return;
        }
        if (Math.abs(s.areaDist - best.areaDist) <= 1e-6) {
          if (s.inter > best.inter + 1e-6) {
            map[lk] = { widget_id: wid, score: s };
            return;
          }
          if (Math.abs(s.inter - best.inter) <= 1e-6) {
            if (s.areaWid < best.areaWid - 1e-6) {
              map[lk] = { widget_id: wid, score: s };
              return;
            }
          }
        }
      }
    }
  }

  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var wid0 = String(w.widget_id || "").trim();
      if (!wid0 || !w.rect) continue;
      var widgetRect = w.rect;
      var widgetZ = (w.layer_index !== undefined) ? Number(w.layer_index || 0) : 0;
      if (!isFinite(widgetZ)) widgetZ = 0;

      // Explicit layer key from export pipeline
      var explicit = String(w.flat_layer_key || "").trim();
      if (explicit) {
        var parsed = parseLayerKey(explicit);
        if (parsed && parsed.rect) {
          consider(explicit, wid0, parsed.rect, parsed.z, widgetRect, widgetZ, true);
        }
      }
    }
  }

  var out = {};
  for (var k in map) {
    if (!Object.prototype.hasOwnProperty.call(map, k)) continue;
    out[k] = String(map[k].widget_id || "");
  }
  state.exportWidgetIdByLayerKey = out;
  // 供自动化回归/现场排障：暴露“当前实际生效”的反向索引与模型快照（只读观察，不参与业务逻辑）。
  if (typeof window !== "undefined") {
    window.__wb_export_widget_id_by_layer_key = out;
    window.__wb_export_widget_preview_model = state.exportWidgetPreviewModel;
  }
}

export const __export_widgets_match = {
  getFlatRectFromElementStyle: getFlatRectFromElementStyle,
  parseZIndexFromFlatElementStyle: parseZIndexFromFlatElementStyle,
  scoreWidgetMatchForFlatSelection: scoreWidgetMatchForFlatSelection,
};

