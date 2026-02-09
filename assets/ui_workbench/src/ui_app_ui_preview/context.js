import { PREVIEW_VARIANT_FLATTENED } from "../config.js";

export const dom = {
  appSubtitle: document.getElementById("appSubtitle"),
  refreshButton: document.getElementById("refreshButton"),
  exportGiaButton: document.getElementById("exportGiaButton"),
  exportGilButton: document.getElementById("exportGilButton"),
  importVariableDefaultsButton: document.getElementById("importVariableDefaultsButton"),
  exportUiStateFullGroupsCheckbox: document.getElementById("exportUiStateFullGroupsCheckbox"),

  baseGilFileInput: document.getElementById("baseGilFileInput"),
  selectBaseGilButton: document.getElementById("selectBaseGilButton"),
  useCurrentBaseGilButton: document.getElementById("useCurrentBaseGilButton"),
  selectedBaseGilFileText: document.getElementById("selectedBaseGilFileText"),
  selectedBaseGilPathText: document.getElementById("selectedBaseGilPathText"),

  searchInput: document.getElementById("searchInput"),
  fileCountText: document.getElementById("fileCountText"),
  fileList: document.getElementById("fileList"),

  previewVariantFlattenedButton: document.getElementById("previewVariantFlattenedButton"),
  previewVariantSourceButton: document.getElementById("previewVariantSourceButton"),

  uiStateGroupSelect: document.getElementById("uiStateGroupSelect"),
  uiStateValueSelect: document.getElementById("uiStateValueSelect"),
  uiStateResetButton: document.getElementById("uiStateResetButton"),
  dynamicTextPreviewCheckbox: document.getElementById("dynamicTextPreviewCheckbox"),

  statusText: document.getElementById("statusText"),
  selectedFileText: document.getElementById("selectedFileText"),
  exportStatusTextArea: document.getElementById("exportStatusTextArea"),

  leftBottomTabExportWidgetsButton: document.getElementById("leftBottomTabExportWidgetsButton"),
  leftBottomTabFlattenGroupsButton: document.getElementById("leftBottomTabFlattenGroupsButton"),

  exportWidgetListStatusText: document.getElementById("exportWidgetListStatusText"),
  refreshExportWidgetListButton: document.getElementById("refreshExportWidgetListButton"),
  exportWidgetListContainer: document.getElementById("exportWidgetListContainer"),

  flattenGroupTreeStatusText: document.getElementById("flattenGroupTreeStatusText"),
  refreshFlattenGroupTreeButton: document.getElementById("refreshFlattenGroupTreeButton"),
  resetFlattenGroupTreeVisibilityButton: document.getElementById("resetFlattenGroupTreeVisibilityButton"),
  flattenGroupTreeContainer: document.getElementById("flattenGroupTreeContainer"),

  leftBottomSearchInput: document.getElementById("leftBottomSearchInput"),
  leftBottomSearchButton: document.getElementById("leftBottomSearchButton"),
};

export const state = {
  items: [],
  selected: null, // { scope, file_name, base_file_name, flattened_file_name, source_html, flattened_html, flattened_source_hash }
  checked_files: {}, // selectionKey -> true (用于批量导出 GIL；不影响当前预览 selected)
  // cacheKey -> { source_hash, flattened_html }
  // 注意：扁平化输出为“纯显示”产物；只在用户处于“扁平化预览”时按需生成/缓存。
  flattened_cache: {},
  currentVariant: PREVIEW_VARIANT_FLATTENED,
  canvasSizeKey: "1600x900",
  apiConnected: false,
  baseGilFile: null,
  baseGilPath: "",
  suggestedBaseGilPath: "",
  // 多状态导出策略：true=整态打组（不做组件内合并）；false=组件内合并（最小冗余）
  exportUiStateFullGroups: true,
  uiStatePreview: { group: "", state: "" },
  leftBottomTabMode: "export_widgets",
  exportWidgetPreviewCache: {}, // cacheKey -> { model, html }
  exportWidgetPreviewModel: null, // last model for click -> selection
  exportWidgetIdByLayerKey: {}, // flat layerKey -> widget_id (用于“画布点选 -> 导出控件”确定性映射)
  exportSelectedWidgetId: "", // export widgets list selection highlight
  pendingScrollExportWidgetId: "", // 画布点选时记录；若当前不在“导出控件”Tab，则在切回时滚动定位
  suppressNextExportWidgetAutoScroll: false, // 列表点击触发画布选中后会回流 selection_changed；用该标记避免列表自己跳动
  leftBottomFilterText: "",
};

export let flattenGroupTreeController = null;
export function setFlattenGroupTreeController(v) {
  flattenGroupTreeController = v || null;
}

export function setSubtitle(text) {
  if (!dom.appSubtitle) return;
  dom.appSubtitle.textContent = String(text || "");
}

export function setStatusText(text) {
  if (!dom.statusText) return;
  dom.statusText.textContent = String(text || "");
}

export function setSelectedFileText(text) {
  if (!dom.selectedFileText) return;
  dom.selectedFileText.textContent = String(text || "");
}

export function setExportStatusText(text) {
  if (!dom.exportStatusTextArea) return;
  dom.exportStatusTextArea.value = String(text || "");
}

export function setSelectedBaseGilFileText(text) {
  if (!dom.selectedBaseGilFileText) return;
  dom.selectedBaseGilFileText.textContent = String(text || "");
  dom.selectedBaseGilFileText.title = String(text || "");
}

export function setSelectedBaseGilPathText(text) {
  if (!dom.selectedBaseGilPathText) return;
  dom.selectedBaseGilPathText.textContent = String(text || "");
  dom.selectedBaseGilPathText.title = String(text || "");
}

export function setFlattenGroupTreeStatusText(text) {
  if (!dom.flattenGroupTreeStatusText) return;
  dom.flattenGroupTreeStatusText.textContent = String(text || "");
}

export function setExportWidgetListStatusText(text) {
  if (!dom.exportWidgetListStatusText) return;
  dom.exportWidgetListStatusText.textContent = String(text || "");
}

export function setFlattenGroupTreeEmptyTip(text) {
  if (!dom.flattenGroupTreeContainer) return;
  dom.flattenGroupTreeContainer.innerHTML = '<div class="wb-tree-empty">' + String(text || "") + "</div>";
}

export function setExportWidgetListEmptyTip(text) {
  if (!dom.exportWidgetListContainer) return;
  dom.exportWidgetListContainer.innerHTML = '<div class="wb-tree-empty">' + String(text || "") + "</div>";
}

export function updateSelectedBaseGilUi() {
  var f = state.baseGilFile;
  if (f && f.name) {
    setSelectedBaseGilFileText("基底文件：" + String(f.name || ""));
  } else {
    setSelectedBaseGilFileText("基底文件：<未选择>");
  }
  var p = String(state.baseGilPath || "").trim();
  if (p) {
    setSelectedBaseGilPathText("基底路径：" + p);
  } else {
    setSelectedBaseGilPathText("基底路径：<未设置>");
  }
}

export function setLeftBottomTabMode(mode) {
  var m = String(mode || "").trim();
  if (m !== "export_widgets" && m !== "flatten_groups") {
    m = "export_widgets";
  }
  state.leftBottomTabMode = m;

  if (dom.leftBottomTabExportWidgetsButton) dom.leftBottomTabExportWidgetsButton.classList.toggle("active", m === "export_widgets");
  if (dom.leftBottomTabFlattenGroupsButton) dom.leftBottomTabFlattenGroupsButton.classList.toggle("active", m === "flatten_groups");

  if (dom.exportWidgetListContainer) dom.exportWidgetListContainer.style.display = (m === "export_widgets") ? "" : "none";
  if (dom.flattenGroupTreeContainer) dom.flattenGroupTreeContainer.style.display = (m === "flatten_groups") ? "" : "none";

  if (dom.exportWidgetListStatusText) dom.exportWidgetListStatusText.style.display = (m === "export_widgets") ? "" : "none";
  if (dom.refreshExportWidgetListButton) dom.refreshExportWidgetListButton.style.display = (m === "export_widgets") ? "" : "none";

  if (dom.flattenGroupTreeStatusText) dom.flattenGroupTreeStatusText.style.display = (m === "flatten_groups") ? "" : "none";
  // “显示全部”影响同一套隐藏状态：两种视图都可用
  if (dom.resetFlattenGroupTreeVisibilityButton) dom.resetFlattenGroupTreeVisibilityButton.style.display = "";
  if (dom.refreshFlattenGroupTreeButton) dom.refreshFlattenGroupTreeButton.style.display = (m === "flatten_groups") ? "" : "none";
}

