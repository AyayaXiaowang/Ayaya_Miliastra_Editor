import { hashTextFNV1a32Hex } from "../utils.js";
import * as preview from "../preview/index.js";
import { dom, setExportWidgetListEmptyTip, setExportWidgetListStatusText, state } from "./context.js";
import { buildBundlePayloadForCurrentSelection } from "./bundle.js";
import { buildExportWidgetPreviewModelFromBundle, renderExportWidgetPreviewHtml } from "./export_widgets_model.js";
import { normalizeExportWidgetPreviewModelFlatLayerKeysByPreviewDom, rebuildExportWidgetIdByLayerKeyIndex } from "./export_widgets_part3a.js";

export async function refreshExportWidgetListForCurrentSelectionIfNeeded(force) {
  if (!state.selected) {
    setExportWidgetListStatusText("未生成");
    setExportWidgetListEmptyTip("请选择左侧文件以生成“导出控件”列表。");
    state.exportWidgetPreviewModel = null;
    state.exportWidgetIdByLayerKey = {};
    return;
  }

  var sourceHtmlText = String(state.selected.source_html || "");
  var scope = String(state.selected.scope || "project");
  var fileName = String(state.selected.file_name || "");
  var canvasKey = String(preview.getCurrentSelectedCanvasSizeKey ? preview.getCurrentSelectedCanvasSizeKey() : state.canvasSizeKey);
  var hash = hashTextFNV1a32Hex(sourceHtmlText);
  var cacheKey = scope + ":" + fileName + ":" + canvasKey + ":" + hash;
  if (!force && state.exportWidgetPreviewCache && state.exportWidgetPreviewCache[cacheKey]) {
    var cached = state.exportWidgetPreviewCache[cacheKey];
    if (cached && cached.html) {
      setExportWidgetListStatusText("已生成");
      if (dom.exportWidgetListContainer) dom.exportWidgetListContainer.innerHTML = String(cached.html || "");
      state.exportWidgetPreviewModel = cached.model || null;
      rebuildExportWidgetIdByLayerKeyIndex();
      return;
    }
  }

  setExportWidgetListStatusText("生成中…");
  if (dom.exportWidgetListContainer) {
    dom.exportWidgetListContainer.innerHTML = '<div class="wb-tree-empty">生成中…（从扁平层推导 bundle 并汇总控件）</div>';
  }

  var built = await buildBundlePayloadForCurrentSelection();
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
  var html = renderExportWidgetPreviewHtml(model);

  state.exportWidgetPreviewCache[cacheKey] = { model: model, html: html };
  state.exportWidgetPreviewModel = model;
  rebuildExportWidgetIdByLayerKeyIndex();
  setExportWidgetListStatusText("已生成");
  if (dom.exportWidgetListContainer) dom.exportWidgetListContainer.innerHTML = html;
}

