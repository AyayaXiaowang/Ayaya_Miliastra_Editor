import { CANVAS_SIZE_CATALOG, PREVIEW_VARIANT_FLATTENED, PREVIEW_VARIANT_SOURCE } from "../config.js";
import { dom, flattenGroupTreeController, state, setStatusText } from "./context.js";
import { isAutotestSelectEnabled } from "./helpers.js";
import { resolveCurrentHtmlText, updateVariantButtons } from "./buttons.js";
import { syncUiStatePreviewUiAndApply } from "./ui_state_preview.js";
import * as preview from "../preview/index.js";
import { hashTextFNV1a32Hex } from "../utils.js";
import { generateFlattenedHtmlFromSourceHtml } from "./flattening.js";

function _captureCurrentSelectionSnapshot() {
  // 约定：只做确定性恢复（不猜测）。
  // 扁平化预览下，layerKey 是最稳定的定位身份（由 dom_index 基于 inline style 构建）。
  // 但切换画布尺寸后，同一语义控件的 rect 会变化，layerKey 可能变化；
  // 因此额外记录 debug-label（去掉 __r... 矩形后缀）作为跨尺寸的稳定身份，用于恢复选中框（蓝框）。
  var el = preview.getCurrentSelectedPreviewElement ? preview.getCurrentSelectedPreviewElement() : null;
  if (!el || !el.getAttribute) {
    return null;
  }
  var dbg = "";
  if (el.dataset && String(el.dataset.debugLabel || "").trim()) {
    dbg = String(el.dataset.debugLabel || "").trim();
  } else {
    dbg = String(el.getAttribute("data-debug-label") || "").trim();
  }
  function _normalizeDebugLabelBase(raw) {
    var s = String(raw || "").trim();
    if (!s) return "";
    var i = s.indexOf("__r");
    if (i > 0) s = s.slice(0, i);
    return s;
  }
  var debugLabelBase = _normalizeDebugLabelBase(dbg);
  var preferredKind = "";
  if (el.classList) {
    if (el.classList.contains("flat-text")) preferredKind = "flat-text";
    else if (el.classList.contains("flat-element")) preferredKind = "flat-element";
    else if (el.classList.contains("flat-border")) preferredKind = "flat-border";
    else if (el.classList.contains("flat-shadow")) preferredKind = "flat-shadow";
    else if (el.classList.contains("flat-button-anchor")) preferredKind = "flat-button-anchor";
  }
  var lk = "";
  if (el.dataset && String(el.dataset.layerKey || "").trim()) {
    lk = String(el.dataset.layerKey || "").trim();
  } else {
    lk = String(el.getAttribute("data-layer-key") || "").trim();
  }
  if (!lk && !debugLabelBase) {
    return null;
  }
  return { kind: "element", layerKey: lk, debugLabelBase: debugLabelBase, preferredKind: preferredKind };
}

function _restoreSelectionFromSnapshot(snapshot) {
  var snap = snapshot || null;
  if (!snap || snap.kind !== "element") {
    return;
  }
  if (state.currentVariant !== PREVIEW_VARIANT_FLATTENED) {
    return;
  }
  if (!flattenGroupTreeController || !flattenGroupTreeController.indexFlattenedPreviewElements || !flattenGroupTreeController.findPreviewElementByLayerKey) {
    return;
  }
  // 确保 index 最新（renderPreview 内部也会做一次，但这里保持幂等）
  flattenGroupTreeController.indexFlattenedPreviewElements();
  var lk = String(snap.layerKey || "").trim();
  if (lk) {
    var target = flattenGroupTreeController.findPreviewElementByLayerKey(lk);
    if (target) {
      preview.selectPreviewElement(target);
      return;
    }
  }

  // 兜底：跨分辨率 rect 变化时 layerKey 可能变化；用 debug-label(base) 恢复同一语义控件。
  var dbgBase = String(snap.debugLabelBase || "").trim();
  if (dbgBase) {
    var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
    var sizeKey = String(state.canvasSizeKey || "").trim();
    if (doc && doc.querySelectorAll && doc.defaultView && doc.defaultView.getComputedStyle) {
      var area = null;
      if (sizeKey && doc.querySelector) {
        area = doc.querySelector('.flat-display-area[data-size-key="' + sizeKey + '"]');
      }
      if (!area && doc.querySelector) {
        area = doc.querySelector(".flat-display-area");
      }
      var root = area || doc;
      var nodes = root.querySelectorAll("[data-debug-label]");
      var preferred = String(snap.preferredKind || "").trim();
      var firstVisible = null;
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        if (!el || !el.getAttribute || !el.getBoundingClientRect) continue;
        var dbg2 = String(el.getAttribute("data-debug-label") || "").trim();
        var j = dbg2.indexOf("__r");
        if (j > 0) dbg2 = dbg2.slice(0, j);
        if (dbg2 !== dbgBase) continue;
        var cs = doc.defaultView.getComputedStyle(el);
        if (!cs) continue;
        if (String(cs.display || "") === "none") continue;
        if (String(cs.visibility || "") === "hidden") continue;
        var op = Number(cs.opacity);
        if (isFinite(op) && op <= 0.0001) continue;
        var r = el.getBoundingClientRect();
        if (!r || r.width <= 0 || r.height <= 0) continue;
        if (!firstVisible) firstVisible = el;
        if (preferred && el.classList && el.classList.contains(preferred)) {
          preview.selectPreviewElement(el);
          return;
        }
      }
      if (firstVisible) {
        preview.selectPreviewElement(firstVisible);
        return;
      }
    }
  }
  // 若无法恢复，则必须清空，避免检查器残留旧信息造成“切分辨率不变”的错觉。
  if (preview.clearCurrentSelection) {
    preview.clearCurrentSelection();
  }
}

export async function renderPreview() {
  var selectionSnapshot = _captureCurrentSelectionSnapshot();
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
  _restoreSelectionFromSnapshot(selectionSnapshot);
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

