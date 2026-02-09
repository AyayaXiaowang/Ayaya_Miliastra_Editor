import { CANVAS_SIZE_CATALOG, getCanvasSizeByKey } from "../config.js";
import { waitForNextFrame } from "../utils.js";
import { extractDisplayElementsData, buildFlattenedLayerData } from "../flatten.js";
import { validateTextFontSizeUniformAcrossCanvasSizes } from "../validation.js";
import { createDiagnosticsCollector, formatIssuesAsText, splitIssuesBySeverity } from "../diagnostics.js";
import { buildUiLayoutBundleFromFlattenedLayers } from "../ui_control_group_export.js";
import * as preview from "../preview/index.js";
import { state } from "./context.js";
import { removeHtmlExt } from "./helpers.js";
import { collectUniformTextFontSizeByElementIndexFromComputePreview } from "./flattening.js";
import { extractVariableDefaultsFromHtmlText } from "./variable_defaults.js";

function _deriveLayoutNameFromSelectedFile() {
  if (!state.selected) return "HTML导出_界面布局";
  var base = String(state.selected.base_file_name || state.selected.file_name || "").trim();
  var stem = removeHtmlExt(base);
  return stem || "HTML导出_界面布局";
}

export async function buildBundlePayloadForCurrentSelection() {
  if (!state.selected) {
    return { ok: false, error: "未选择任何 UI源码 文件。" };
  }
  var sourceHtmlText = String(state.selected.source_html || "");
  if (!String(sourceHtmlText || "").trim()) {
    return { ok: false, error: "当前源码为空：无法导出。" };
  }

  var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(sourceHtmlText);
  if (!isComputeReady) {
    return { ok: false, error: "compute iframe 未就绪：无法导出" };
  }
  var computeDoc = preview.getComputePreviewDocument();
  if (!computeDoc) {
    return { ok: false, error: "compute 文档为空：无法导出" };
  }

  var selectedCanvasSizeKey = preview.getCurrentSelectedCanvasSizeKey();
  var selectedCanvasSizeOption = getCanvasSizeByKey(selectedCanvasSizeKey);
  preview.setComputePreviewCanvasSize(selectedCanvasSizeOption);
  preview.applyCanvasSizeToPreviewDocument(computeDoc, selectedCanvasSizeOption);
  await waitForNextFrame();
  await waitForNextFrame();

  var elementsData = extractDisplayElementsData(computeDoc);
  // 导出路径：开启“强制校验”收集。若出现 error（例如不透明纯黑 #000），直接阻断导出并给出明确提示。
  var exportDiagnostics = createDiagnosticsCollector();
  var layerList = buildFlattenedLayerData(elementsData, { diagnostics: exportDiagnostics });
  var split = splitIssuesBySeverity(exportDiagnostics.issues);
  if (split && split.errors && split.errors.length > 0) {
    var text = formatIssuesAsText(exportDiagnostics.issues, { title: "导出前校验（阻断）" });
    return {
      ok: false,
      error: "导出被阻断：检测到不支持/高风险的写回规则。\n\n" + text
    };
  }

  // Hard requirement: font-size must be uniform across all supported canvas sizes.
  var fontIssues = await validateTextFontSizeUniformAcrossCanvasSizes(preview, CANVAS_SIZE_CATALOG, waitForNextFrame);
  var fontSplit = splitIssuesBySeverity(fontIssues);
  if (fontSplit && fontSplit.errors && fontSplit.errors.length > 0) {
    var fontText = formatIssuesAsText(fontIssues, { title: "导出前校验（字号一致性，阻断）" });
    return {
      ok: false,
      error: "导出被阻断：检测到文字字号随画布尺寸变化（硬性禁止）。\n\n" + fontText
    };
  }
  var uniformTextFontSizeByElementIndex = await collectUniformTextFontSizeByElementIndexFromComputePreview(sourceHtmlText);

  var uiKeyPrefix = String(state.selected.base_file_name || state.selected.file_name || "").trim();
  if (!uiKeyPrefix) {
    uiKeyPrefix = _deriveLayoutNameFromSelectedFile();
  }
  var layoutName = _deriveLayoutNameFromSelectedFile();

  var exportResult = buildUiLayoutBundleFromFlattenedLayers(layerList, {
    template_id: "template_html_import_" + String(Date.now()),
    template_name: "HTML导入_UI控件组_" + String(selectedCanvasSizeOption.label || selectedCanvasSizeKey),
    layout_id: "layout_html_import_" + String(Date.now()),
    layout_name: layoutName,
    layout_description: "由 ui_app_ui_preview 导出。尺寸: " + String(selectedCanvasSizeOption.label || selectedCanvasSizeKey),
    ui_key_prefix: uiKeyPrefix,
    group_width: elementsData.bodySize ? elementsData.bodySize.width : selectedCanvasSizeOption.width,
    group_height: elementsData.bodySize ? elementsData.bodySize.height : selectedCanvasSizeOption.height,
    canvas_size_key: selectedCanvasSizeKey,
    canvas_size_label: String(selectedCanvasSizeOption.label || selectedCanvasSizeKey),
    // UI 多状态策略：
    // - full_state_groups：整态打组（每个 state 独立组件组；用于规避游戏侧层级/底色异常）
    // - minimal_redundancy：组件内合并（最小冗余；会提升跨状态共享控件）
    ui_state_consolidation_mode: state.exportUiStateFullGroups ? "full_state_groups" : "minimal_redundancy",
    description: "由 ui_app_ui_preview 导出。",
    uniform_text_font_size_by_element_index: uniformTextFontSizeByElementIndex
  });
  var bundlePayload = exportResult && exportResult.bundle ? exportResult.bundle : null;
  if (!bundlePayload) {
    return { ok: false, error: "bundle 生成失败：空结果（内部错误）。" };
  }

  // 默认值映射：用于写回端“自动创建实体自定义变量”时写入默认值（支持标量与字典）。
  var variableDefaults = extractVariableDefaultsFromHtmlText(sourceHtmlText);
  bundlePayload.variable_defaults = variableDefaults;
  bundlePayload.variable_defaults_total = (Object.keys(variableDefaults || {}).length || 0);

  return {
    ok: true,
    layoutName: layoutName,
    bundlePayload: bundlePayload,
    selectedCanvasSizeKey: selectedCanvasSizeKey,
    selectedCanvasSizeOption: selectedCanvasSizeOption,
  };
}

