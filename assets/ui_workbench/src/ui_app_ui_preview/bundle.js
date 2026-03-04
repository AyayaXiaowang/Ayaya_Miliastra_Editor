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

async function _ensureStableComputeDocForCanvasOrNull(sourceHtmlText, canvasSizeOption) {
  var html = String(sourceHtmlText || "").trim();
  if (!html) return null;
  var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(html);
  if (!isComputeReady) return null;
  var computeDoc = preview.getComputePreviewDocument();
  if (!computeDoc || !computeDoc.body) return null;

  if (preview.setComputePreviewCanvasSize) {
    preview.setComputePreviewCanvasSize(canvasSizeOption);
  }
  preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
  await waitForNextFrame();
  await waitForNextFrame();

  // compute iframe 可能在等待帧期间被其它链路重渲染（document 对象切换），此时旧引用会变“脱离窗口”，rect=0。
  var currentDoc = preview.getComputePreviewDocument();
  if (currentDoc && currentDoc !== computeDoc) {
    computeDoc = currentDoc;
    if (!computeDoc || !computeDoc.body) return null;
    if (preview.setComputePreviewCanvasSize) {
      preview.setComputePreviewCanvasSize(canvasSizeOption);
    }
    preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
    await waitForNextFrame();
    await waitForNextFrame();
  }

  // 强制 reflow：确保 bodyRect/元素 rect 可用（避免 headless/早期时序下 rect=0）。
  if (computeDoc && computeDoc.body) {
    computeDoc.body.getBoundingClientRect();
    void computeDoc.body.offsetHeight;
  }
  return computeDoc;
}

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

  var selectedCanvasSizeKey = preview.getCurrentSelectedCanvasSizeKey();
  var selectedCanvasSizeOption = getCanvasSizeByKey(selectedCanvasSizeKey);
  var didHardResetCompute = false;
  var computeDoc = await _ensureStableComputeDocForCanvasOrNull(sourceHtmlText, selectedCanvasSizeOption);
  if (!computeDoc) {
    return { ok: false, error: "compute iframe 未就绪/文档为空：无法导出" };
  }
  var elementsData = extractDisplayElementsData(computeDoc);
  // 经验修复：首轮提取可能为空（布局/字体/样式未稳定），额外等待 + 重试一次。
  if (!elementsData || !elementsData.elements || elementsData.elements.length <= 0) {
    await waitForNextFrame();
    await waitForNextFrame();
    await waitForNextFrame();
    await waitForNextFrame();
    computeDoc = await _ensureStableComputeDocForCanvasOrNull(sourceHtmlText, selectedCanvasSizeOption);
    if (computeDoc) {
      elementsData = extractDisplayElementsData(computeDoc);
    }
  }
  // Hard reset：若 compute 处于“defaultView=null / rect=0”的卡死状态，重建 iframe 后重试一次。
  if (
    (!elementsData || !elementsData.elements || elementsData.elements.length <= 0) &&
    !didHardResetCompute &&
    preview.resetComputePreviewHard
  ) {
    var diag0 = elementsData && elementsData.diagnostics ? elementsData.diagnostics : null;
    var bodyW0 = diag0 && diag0.bodyRect ? Number(diag0.bodyRect.width || 0) : 0;
    var bodyH0 = diag0 && diag0.bodyRect ? Number(diag0.bodyRect.height || 0) : 0;
    var hasView0 = !!(computeDoc && computeDoc.defaultView && computeDoc.defaultView.getComputedStyle);
    if ((!hasView0) || bodyW0 <= 1 || bodyH0 <= 1) {
      didHardResetCompute = true;
      preview.resetComputePreviewHard();
      computeDoc = await _ensureStableComputeDocForCanvasOrNull(sourceHtmlText, selectedCanvasSizeOption);
      if (computeDoc) {
        elementsData = extractDisplayElementsData(computeDoc);
      }
    }
  }

  // 尺寸一致性：bundle 导出/控件列表的 flat_layer_key 必须与“当前画布尺寸”的扁平预览一致。
  // 若 compute iframe 的 bodyRect 未切到目标尺寸（偶发时序/优化），即便 elementsData 非空也会导致 layerKey 全面错位。
  function _isBodyRectSizeOk(data, canvasOpt) {
    var d = data && data.diagnostics ? data.diagnostics : null;
    var br = d && d.bodyRect ? d.bodyRect : null;
    if (!br) return false;
    var bw = Number(br.width || 0);
    var bh = Number(br.height || 0);
    var ew = Number(canvasOpt && canvasOpt.width || 0);
    var eh = Number(canvasOpt && canvasOpt.height || 0);
    if (!(bw > 1) || !(bh > 1) || !(ew > 1) || !(eh > 1)) return false;
    // 允许 1px 级误差（不同平台/缩放下可能有极小浮动）
    return (Math.abs(bw - ew) <= 1.5) && (Math.abs(bh - eh) <= 1.5);
  }

  if (!_isBodyRectSizeOk(elementsData, selectedCanvasSizeOption) && preview.resetComputePreviewHard && !didHardResetCompute) {
    didHardResetCompute = true;
    preview.resetComputePreviewHard();
    computeDoc = await _ensureStableComputeDocForCanvasOrNull(sourceHtmlText, selectedCanvasSizeOption);
    if (computeDoc) {
      elementsData = extractDisplayElementsData(computeDoc);
    }
  }

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
    // UI 多状态策略：强制整态打组（与导出中心/CLI 口径一致）
    ui_state_consolidation_mode: "full_state_groups",
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

