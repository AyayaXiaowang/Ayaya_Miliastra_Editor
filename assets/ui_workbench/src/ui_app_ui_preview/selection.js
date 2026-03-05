import { PREVIEW_VARIANT_FLATTENED } from "../config.js";
import { autoFixHtmlSource } from "../validation.js";
import { dom, flattenGroupTreeController, setExportWidgetListEmptyTip, setExportWidgetListStatusText, setFlattenGroupTreeStatusText, setSelectedFileText, setStatusText, state } from "./context.js";
import { isDerivedHtmlFileName, pickFlattenedCandidate, removeHtmlExt } from "./helpers.js";
import { encodeSelectionKey, STORAGE_KEY_LAST_SELECTED } from "./storage.js";
import { readUiSourceContent } from "./api.js";
import { updateExportGiaButtonEnabled, updateExportGilButtonEnabled, updateVariantButtons } from "./buttons.js";
import { renderFileList } from "./catalog.js";
import { renderPreview, autotestSelectOneIfEnabled } from "./preview_render.js";
import { refreshExportWidgetListForCurrentSelectionIfNeeded } from "./export_widgets_part2.js";
import { hashTextFNV1a32Hex } from "../utils.js";

export async function selectFile(scope, fileName) {
  var items = state.items || [];
  var baseFileName = String(fileName || "");
  var flattenedFileName = null;

  // 关键：切换文件时先清掉左下“导出控件”的旧状态，避免出现“已生成但实际上还是上一页”的错觉，
  // 同时为自动化提供稳定同步点（后续 refresh 完成会切回“已生成”）。
  setExportWidgetListStatusText("生成中…");
  setExportWidgetListEmptyTip("生成中…");
  state.exportWidgetPreviewModel = null;
  state.exportWidgetIdByLayerKey = {};

  if (!isDerivedHtmlFileName(baseFileName)) {
    flattenedFileName = pickFlattenedCandidate(baseFileName, items);
  } else {
    flattenedFileName = baseFileName;
    // 重要：派生物不是真源；导出/GIL 写回必须使用对应的源 HTML（同名 .html，且通常位于父目录）。
    var stem = removeHtmlExt(baseFileName).replace(/\.autofix\.flattened$/i, "").replace(/\.flattened$/i, "");
    // 若位于 __workbench_out__ 子目录，则回到父目录：a/__workbench_out__/b -> a/b
    stem = stem.replace(/(^|[\\/])__workbench_out__([\\/])/i, "$1");
    baseFileName = stem + ".html";
  }

  setStatusText("读取 HTML…");
  var rawSourceHtml = await readUiSourceContent(scope, baseFileName);

  // 与 Workbench 一致：先做一次安全自动修正（禁滚动/标准化 html/body 等）
  var fixResult = autoFixHtmlSource(rawSourceHtml);
  var fixedHtmlText = fixResult && fixResult.fixed_html_text !== undefined ? String(fixResult.fixed_html_text || "") : rawSourceHtml;
  if (!String(fixedHtmlText || "").trim()) {
    fixedHtmlText = rawSourceHtml;
  }

  // 不在“选中文件”时强制生成扁平化：
  // - 扁平化产物属于“纯显示”，只应在用户切到扁平化预览时按需生成；
  // - 统一入口：renderPreview()（避免与任何“强制扁平化”/其它链路产生逻辑分叉）。
  var sourceHash = hashTextFNV1a32Hex(fixedHtmlText);
  var cacheKey = String(scope || "project") + ":" + String(fileName || "");
  var cached = cacheKey && state.flattened_cache ? state.flattened_cache[cacheKey] : null;
  var cachedOk = !!(cached && cached.flattened_html && cached.source_hash && String(cached.source_hash) === String(sourceHash));
  var flattenedHtml = cachedOk ? String(cached.flattened_html || "") : "";

  state.selected = {
    scope: String(scope || "project"),
    file_name: String(fileName || ""),
    base_file_name: baseFileName,
    flattened_file_name: flattenedFileName,
    source_html: fixedHtmlText,
    flattened_html: flattenedHtml,
    flattened_source_hash: String(sourceHash || ""),
  };
  state.exportSelectedWidgetId = "";
  window.localStorage.setItem(STORAGE_KEY_LAST_SELECTED, encodeSelectionKey(state.selected.scope, state.selected.file_name));

  // 关键：避免上一次“隐藏层”状态误伤新页面（例如只剩文字层）。
  // renderPreview() 会在渲染后索引扁平 DOM，并按 hidden set 应用 display:none；
  // 因此必须在渲染前清空 hidden set，保证新预览默认完整显示。
  if (flattenGroupTreeController && flattenGroupTreeController.resetVisibilityToggles) {
    flattenGroupTreeController.resetVisibilityToggles();
  }
  if (flattenGroupTreeController && flattenGroupTreeController.setUiKeyPrefix) {
    flattenGroupTreeController.setUiKeyPrefix(baseFileName);
  }

  // 先更新 UI 与预览，再生成左下列表：
  // - 预览的“真实扁平 DOM（data-layer-key）”是导出控件列表 flat_layer_key 归一化的真源；
  // - 若先生成列表再渲染预览，会导致列表缓存持有“扁平化前/未归一化”的 key，进而与实际游戏/扁平预览不一致。
  updateVariantButtons();
  updateExportGiaButtonEnabled();
  updateExportGilButtonEnabled();
  renderFileList();
  setSelectedFileText(state.selected.scope + ":" + state.selected.file_name);

  await renderPreview();
  setStatusText(state.currentVariant === PREVIEW_VARIANT_FLATTENED ? "预览：扁平化" : "预览：原稿");

  // 左下“扁平分组”：复用 Workbench 的分组树（分组 key 与写回端一致）
  if (flattenGroupTreeController) {
    setFlattenGroupTreeStatusText("生成中…");
    await flattenGroupTreeController.refresh();
  }

  // 左下“导出控件”：直接展示“如果导出 GIL”将会生成的控件列表（由 bundle 推导）
  await refreshExportWidgetListForCurrentSelectionIfNeeded(true);

  // Dev autotest: validate "select works" without manual iframe clicking.
  await autotestSelectOneIfEnabled();
}

