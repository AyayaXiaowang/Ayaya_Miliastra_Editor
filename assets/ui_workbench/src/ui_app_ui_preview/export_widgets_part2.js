import { hashTextFNV1a32Hex } from "../utils.js";
import * as preview from "../preview/index.js";
import { dom, setExportWidgetListEmptyTip, setExportWidgetListStatusText, state } from "./context.js";
import { buildBundlePayloadForCurrentSelection } from "./bundle.js";
import { buildExportWidgetPreviewModelFromBundle } from "./export_widgets_model.js";
import { normalizeExportWidgetPreviewModelFlatLayerKeysByPreviewDom, rebuildExportWidgetIdByLayerKeyIndex } from "./export_widgets_part3a.js";
import { applyExportWidgetRowFlatLayerKeysFromModel } from "./export_widget_list_dom.js";
import { rerenderExportWidgetListFromModelNow } from "./export_widget_list_render.js";

var _refreshExportWidgetListSeq = 0;

function _makeExportWidgetCacheKey() {
  if (!state.selected) return "";
  var sourceHtmlText = String(state.selected.source_html || "");
  var scope = String(state.selected.scope || "project");
  var fileName = String(state.selected.file_name || "");
  var canvasKey = String(preview.getCurrentSelectedCanvasSizeKey ? preview.getCurrentSelectedCanvasSizeKey() : state.canvasSizeKey);
  var hash = hashTextFNV1a32Hex(sourceHtmlText);
  return scope + ":" + fileName + ":" + canvasKey + ":" + hash;
}

function _buildUiKeyToFlatLayerKeyMap(model) {
  var m = model || null;
  if (!m || !m.groups) return {};
  var out = {};
  var groups = m.groups || [];
  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var uiKey = String(w.ui_key || "").trim();
      if (!uiKey) continue;
      var lk = String(w.flat_layer_key || "").trim();
      if (!lk) continue;
      out[uiKey] = lk;
    }
  }
  return out;
}

function _applyUiKeyToFlatLayerKeyMapToExistingModel(existingModel, uiKeyToKey) {
  var m = existingModel || null;
  var map = uiKeyToKey || null;
  if (!m || !m.groups || !map) return 0;
  var updated = 0;
  var groups = m.groups || [];
  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var ws = g.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var uiKey = String(w.ui_key || "").trim();
      if (!uiKey) continue;
      var lk = map[uiKey] ? String(map[uiKey] || "").trim() : "";
      if (!lk) continue;
      if (String(w.flat_layer_key || "") !== lk) {
        w.flat_layer_key = lk;
        updated += 1;
      }
    }
  }
  return updated;
}

export async function refreshExportWidgetListForCurrentSelectionIfNeeded(force) {
  var seq = (_refreshExportWidgetListSeq += 1);
  var selectedRef = state.selected;

  if (!state.selected) {
    setExportWidgetListStatusText("未生成");
    setExportWidgetListEmptyTip("请选择左侧文件以生成“导出控件”列表。");
    state.exportWidgetPreviewModel = null;
    state.exportWidgetIdByLayerKey = {};
    return;
  }

  function _isStale() {
    // 仅允许“最后一次调用”落盘（避免并发刷新导致列表抖动 / widget_id 变化引发自动化不稳定）
    if (seq !== _refreshExportWidgetListSeq) return true;
    if (state.selected !== selectedRef) return true;
    return false;
  }

  var cacheKey = _makeExportWidgetCacheKey();
  if (!force && state.exportWidgetPreviewCache && state.exportWidgetPreviewCache[cacheKey]) {
    var cached = state.exportWidgetPreviewCache[cacheKey];
    if (cached && cached.model) {
      setExportWidgetListStatusText("已生成");
      state.exportWidgetPreviewModel = cached.model || null;
      rebuildExportWidgetIdByLayerKeyIndex();
      rerenderExportWidgetListFromModelNow(state.exportWidgetPreviewModel);
      return;
    }
  }

  setExportWidgetListStatusText("生成中…");
  if (dom.exportWidgetListContainer) {
    dom.exportWidgetListContainer.innerHTML = '<div class="wb-tree-empty">生成中…（从扁平层推导 bundle 并汇总控件）</div>';
  }

  var built = await buildBundlePayloadForCurrentSelection();
  if (_isStale()) return;
  if (!built || built.ok !== true) {
    setExportWidgetListStatusText("生成失败");
    setExportWidgetListEmptyTip("生成失败：\n" + String((built && built.error) ? built.error : "未知错误"));
    state.exportWidgetPreviewModel = null;
    state.exportWidgetIdByLayerKey = {};
    return;
  }
  var bundlePayload = built.bundlePayload;
  var model = buildExportWidgetPreviewModelFromBundle(bundlePayload);
  normalizeExportWidgetPreviewModelFlatLayerKeysByPreviewDom(model);

  if (_isStale()) return;
  state.exportWidgetPreviewCache[cacheKey] = { model: model };
  state.exportWidgetPreviewModel = model;
  rebuildExportWidgetIdByLayerKeyIndex();
  setExportWidgetListStatusText("已生成");
  rerenderExportWidgetListFromModelNow(model);
}

export async function refreshExportWidgetModelForCurrentSelectionInPlace(force) {
  var seq = (_refreshExportWidgetListSeq += 1);
  var selectedRef = state.selected;

  if (!state.selected) {
    setExportWidgetListStatusText("未生成");
    setExportWidgetListEmptyTip("请选择左侧文件以生成“导出控件”列表。");
    state.exportWidgetPreviewModel = null;
    state.exportWidgetIdByLayerKey = {};
    return;
  }

  function _isStale() {
    if (seq !== _refreshExportWidgetListSeq) return true;
    if (state.selected !== selectedRef) return true;
    return false;
  }

  // 关键：切尺寸“原地同步”不得替换 exportWidgetPreviewModel（widget_id 不稳定，替换会导致列表行与模型脱钩）。
  // 我们只用新尺寸的 bundle 结果生成 ui_key -> flat_layer_key 的映射，然后回填到“现有模型”中。
  var existing = state.exportWidgetPreviewModel;
  if (!existing) {
    // 若列表尚未生成，则回退为常规全量生成（允许重绘 DOM）。
    await refreshExportWidgetListForCurrentSelectionIfNeeded(true);
    return;
  }

  var cacheKey = _makeExportWidgetCacheKey();

  var cached = (!force && state.exportWidgetPreviewCache && state.exportWidgetPreviewCache[cacheKey])
    ? state.exportWidgetPreviewCache[cacheKey]
    : null;
  var uiKeyMap = (cached && cached.ui_key_to_flat_layer_key) ? cached.ui_key_to_flat_layer_key : null;
  if (!uiKeyMap) {
    var built = await buildBundlePayloadForCurrentSelection();
    if (_isStale()) return;
    if (!built || built.ok !== true) {
      // fail-fast（不吞错/不降级清空）：保留旧映射，让列表仍可用；错误通过状态区可见。
      setExportWidgetListStatusText("生成失败");
      return;
    }
    var bundlePayload = built.bundlePayload;
    var modelNew = buildExportWidgetPreviewModelFromBundle(bundlePayload);
    normalizeExportWidgetPreviewModelFlatLayerKeysByPreviewDom(modelNew);
    if (_isStale()) return;
    uiKeyMap = _buildUiKeyToFlatLayerKeyMap(modelNew);
    state.exportWidgetPreviewCache[cacheKey] = { ui_key_to_flat_layer_key: uiKeyMap };
  }

  _applyUiKeyToFlatLayerKeyMapToExistingModel(existing, uiKeyMap);
  rebuildExportWidgetIdByLayerKeyIndex();
  setExportWidgetListStatusText("已生成");
  applyExportWidgetRowFlatLayerKeysFromModel(existing);
}
