import { CANVAS_SIZE_CATALOG, PREVIEW_VARIANT_FLATTENED, PREVIEW_VARIANT_SOURCE } from "../config.js";
import { dom, flattenGroupTreeController, state, setStatusText } from "./context.js";
import { isAutotestSelectEnabled } from "./helpers.js";
import { resolveCurrentHtmlText, updateVariantButtons } from "./buttons.js";
import { syncUiStatePreviewUiAndApply } from "./ui_state_preview.js";
import * as preview from "../preview/index.js";
import { hashTextFNV1a32Hex } from "../utils.js";
import { generateFlattenedHtmlFromSourceHtml } from "./flattening.js";

export async function renderPreview() {
  // 始终先确保 preview 的画布尺寸为当前选择（避免后续生成/索引使用旧 sizeKey）。
  preview.setSelectedCanvasSize(state.canvasSizeKey);

  // 扁平化变体：统一入口生成扁平化（按 source hash 缓存），避免出现“切换/隐藏/强制扁平化”多入口分叉。
  if (state.currentVariant === PREVIEW_VARIANT_FLATTENED && state.selected) {
    var sourceHtmlText = String(state.selected.source_html || "");
    if (String(sourceHtmlText || "").trim()) {
      var sourceHash = hashTextFNV1a32Hex(sourceHtmlText);
      var cacheKey = String(state.selected.scope || "project") + ":" + String(state.selected.file_name || "");
      var cached = cacheKey && state.flattened_cache ? state.flattened_cache[cacheKey] : null;
      var cachedOk = !!(cached && cached.flattened_html && cached.source_hash && String(cached.source_hash) === String(sourceHash));
      var selectedOk = !!(state.selected.flattened_html && state.selected.flattened_source_hash && String(state.selected.flattened_source_hash) === String(sourceHash));

      if (!selectedOk) {
        if (cachedOk) {
          state.selected.flattened_html = String(cached.flattened_html || "");
          state.selected.flattened_source_hash = String(sourceHash || "");
        } else {
          // 生成（唯一入口）：compute iframe -> 4 分辨率扁平化输出
          setStatusText("生成扁平化…");
          var uiKeyPrefix = String(state.selected.base_file_name || state.selected.file_name || "").trim();
          var flattenedHtml = await generateFlattenedHtmlFromSourceHtml(sourceHtmlText, uiKeyPrefix);
          state.selected.flattened_html = String(flattenedHtml || "");
          state.selected.flattened_source_hash = String(sourceHash || "");
          if (!state.flattened_cache) {
            state.flattened_cache = {};
          }
          state.flattened_cache[cacheKey] = { source_hash: String(sourceHash || ""), flattened_html: String(flattenedHtml || "") };
        }
      }
    }
  }

  var htmlText = resolveCurrentHtmlText();
  if (!String(htmlText || "").trim()) {
    var placeholder = preview.buildEmptyInputPlaceholderHtml();
    // 空输入占位页：作为“原稿”渲染即可（只是占位文档，不影响当前模式语义）
    await preview.renderHtmlIntoPreview(placeholder, PREVIEW_VARIANT_SOURCE);
    if (flattenGroupTreeController) flattenGroupTreeController.indexFlattenedPreviewElements();
    syncUiStatePreviewUiAndApply();
    return;
  }
  await preview.renderHtmlIntoPreview(htmlText, state.currentVariant);
  _autotestAssertFlattenedDomShapeIfNeeded();
  if (flattenGroupTreeController) flattenGroupTreeController.indexFlattenedPreviewElements();
  syncUiStatePreviewUiAndApply();
}

function _autotestAssertFlattenedDomShapeIfNeeded() {
  // 内置自测：扁平化预览应是“替换 <body> 内容”的纯扁平层页面，
  // 不应残留原稿 DOM（例如 ceshi.html 的 .preview-stage）。
  if (state.currentVariant !== PREVIEW_VARIANT_FLATTENED) {
    return;
  }
  var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
  if (!doc || !doc.querySelector) {
    return;
  }
  var hasFlatArea = !!doc.querySelector(".flat-display-area");
  if (!hasFlatArea) {
    setStatusText("扁平化自检失败：缺少 .flat-display-area（可能未生成/未渲染扁平层）");
    return;
  }
  var leakedPreviewStage = doc.querySelector(".preview-stage");
  if (leakedPreviewStage) {
    setStatusText("扁平化自检失败：检测到原稿 DOM 泄漏（.preview-stage 仍存在）");
    return;
  }
}

export async function autotestSelectOneIfEnabled() {
  if (!isAutotestSelectEnabled()) {
    return;
  }
  if (!state.selected) {
    console.log("[AUTOTEST_SELECT] skipped: no selected file");
    return;
  }
  // 强制切到扁平化再选：覆盖“画布/分组树点选”的核心链路
  state.currentVariant = PREVIEW_VARIANT_FLATTENED;
  updateVariantButtons();
  await renderPreview();

  var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
  if (!doc || !doc.querySelector) {
    console.log("[AUTOTEST_SELECT] failed: preview document unavailable");
    return;
  }
  console.log("[AUTOTEST_SELECT] info:", {
    variant: String(preview.getCurrentPreviewVariant ? preview.getCurrentPreviewVariant() : state.currentVariant || ""),
    canvas: String(preview.getCurrentSelectedCanvasSizeKey ? preview.getCurrentSelectedCanvasSizeKey() : ""),
  });
  var area = doc.querySelector('.flat-display-area[data-size-key="' + String(preview.getCurrentSelectedCanvasSizeKey() || "") + '"]');
  if (!area) {
    console.log("[AUTOTEST_SELECT] warn: no flat-display-area for current size; fallback to source element selection");
    // 兜底：至少验证“选中/覆盖层/检查器”链路本身可用（即便扁平化输出为空而回退到原稿）
    var any = doc.querySelector("body *");
    if (!any) {
      console.log("[AUTOTEST_SELECT] failed: no selectable element in source document");
      return;
    }
    preview.selectPreviewElement(any);
    console.log("[AUTOTEST_SELECT] ok(source): selected one element", (any.tagName || "") + (any.className ? ("." + any.className) : ""));
    return;
  }
  var el = area.querySelector(".flat-text, .flat-element, .flat-border, .flat-shadow");
  if (!el) {
    console.log("[AUTOTEST_SELECT] failed: no .flat-* elements");
    return;
  }
  preview.selectPreviewElement(el);
  console.log("[AUTOTEST_SELECT] ok: selected one element", el.className || "");
}

