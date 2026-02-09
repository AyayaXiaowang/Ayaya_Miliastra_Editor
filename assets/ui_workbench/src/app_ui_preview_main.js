import { copyTextToClipboard } from "./utils.js";

var refreshAppUiCatalogButton = document.getElementById("refreshAppUiCatalogButton");
var appUiLayoutSelect = document.getElementById("appUiLayoutSelect");
var loadAppUiLayoutButton = document.getElementById("loadAppUiLayoutButton");
var appUiTemplateSelect = document.getElementById("appUiTemplateSelect");
var loadAppUiTemplateButton = document.getElementById("loadAppUiTemplateButton");
var appUiLoadStatusText = document.getElementById("appUiLoadStatusText");
var selectedWidgetJsonTextArea = document.getElementById("selectedWidgetJsonTextArea");
var copySelectedWidgetJsonButton = document.getElementById("copySelectedWidgetJsonButton");

var leftTabLayoutButton = document.getElementById("leftTabLayoutButton");
var leftTabTemplateButton = document.getElementById("leftTabTemplateButton");
var layoutLibraryPane = document.getElementById("layoutLibraryPane");
var templateLibraryPane = document.getElementById("templateLibraryPane");

var layoutBuiltinCountText = document.getElementById("layoutBuiltinCountText");
var layoutCustomCountText = document.getElementById("layoutCustomCountText");
var layoutDetailsTree = document.getElementById("layoutDetailsTree");

function setStatus(text) {
  if (!appUiLoadStatusText) return;
  appUiLoadStatusText.textContent = String(text || "");
}

function setJsonText(obj) {
  if (!selectedWidgetJsonTextArea) return;
  selectedWidgetJsonTextArea.value = JSON.stringify(obj || {}, null, 2);
}

function setTab(key) {
  var isLayout = String(key || "") === "layout";
  if (leftTabLayoutButton && leftTabLayoutButton.classList) leftTabLayoutButton.classList.toggle("active", isLayout);
  if (leftTabTemplateButton && leftTabTemplateButton.classList) leftTabTemplateButton.classList.toggle("active", !isLayout);
  if (layoutLibraryPane) layoutLibraryPane.style.display = isLayout ? "" : "none";
  if (templateLibraryPane) templateLibraryPane.style.display = isLayout ? "none" : "";
}

function fillSelect(selectEl, items, getKey, getLabel) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  var list = items || [];
  for (var i = 0; i < list.length; i++) {
    var it = list[i] || {};
    var opt = document.createElement("option");
    opt.value = String(getKey(it));
    opt.textContent = String(getLabel(it));
    selectEl.appendChild(opt);
  }
}

async function refreshCatalog() {
  setStatus("正在刷新 catalog...");
  var resp = await fetch("/api/ui_converter/ui_catalog", { cache: "no-store" });
  var data = await resp.json();
  if (!data || !data.ok) {
    setStatus("刷新失败：" + String((data && data.error) || resp.statusText || "unknown"));
    return;
  }
  fillSelect(appUiLayoutSelect, data.layouts || [], function (it) { return it.layout_id || ""; }, function (it) {
    return String(it.layout_name || it.layout_id || "") + " (builtin=" + String(it.builtin_count || 0) + ", custom=" + String(it.custom_count || 0) + ")";
  });
  fillSelect(appUiTemplateSelect, data.templates || [], function (it) { return it.template_id || ""; }, function (it) {
    return String(it.template_name || it.template_id || "") + " (widgets=" + String(it.widget_count || 0) + ")";
  });
  setStatus("已刷新。当前项目：" + String(data.current_package_id || ""));
}

async function loadLayout() {
  if (!appUiLayoutSelect) return;
  var layoutId = String(appUiLayoutSelect.value || "").trim();
  if (!layoutId) return;
  setStatus("正在加载 layout: " + layoutId);
  var resp = await fetch("/api/ui_converter/ui_layout?layout_id=" + encodeURIComponent(layoutId), { cache: "no-store" });
  var data = await resp.json();
  if (!data || !data.ok) {
    setStatus("加载失败：" + String((data && data.error) || resp.statusText || "unknown"));
    return;
  }
  var layout = data.layout || {};
  setJsonText(layout);

  var builtin = layout.builtin_widgets || [];
  var custom = layout.custom_groups || [];
  if (layoutBuiltinCountText) layoutBuiltinCountText.textContent = String(Array.isArray(builtin) ? builtin.length : 0);
  if (layoutCustomCountText) layoutCustomCountText.textContent = String(Array.isArray(custom) ? custom.length : 0);
  if (layoutDetailsTree) {
    layoutDetailsTree.textContent = "layout_id=" + layoutId + " / name=" + String(layout.layout_name || layout.name || "");
  }

  setStatus("已加载 layout: " + layoutId);
}

async function loadTemplate() {
  if (!appUiTemplateSelect) return;
  var templateId = String(appUiTemplateSelect.value || "").trim();
  if (!templateId) return;
  setStatus("正在加载 template: " + templateId);
  var resp = await fetch("/api/ui_converter/ui_template?template_id=" + encodeURIComponent(templateId), { cache: "no-store" });
  var data = await resp.json();
  if (!data || !data.ok) {
    setStatus("加载失败：" + String((data && data.error) || resp.statusText || "unknown"));
    return;
  }
  setJsonText(data.template || {});
  setStatus("已加载 template: " + templateId);
}

function bind() {
  if (refreshAppUiCatalogButton) refreshAppUiCatalogButton.addEventListener("click", function () { refreshCatalog(); });
  if (loadAppUiLayoutButton) loadAppUiLayoutButton.addEventListener("click", function () { loadLayout(); });
  if (loadAppUiTemplateButton) loadAppUiTemplateButton.addEventListener("click", function () { loadTemplate(); });
  if (leftTabLayoutButton) leftTabLayoutButton.addEventListener("click", function () { setTab("layout"); });
  if (leftTabTemplateButton) leftTabTemplateButton.addEventListener("click", function () { setTab("template"); });
  if (copySelectedWidgetJsonButton && selectedWidgetJsonTextArea) {
    copySelectedWidgetJsonButton.addEventListener("click", function () {
      copyTextToClipboard(selectedWidgetJsonTextArea.value || "");
      setStatus(String(appUiLoadStatusText ? appUiLoadStatusText.textContent : "") + "（已复制）");
    });
  }
}

bind();
setTab("layout");
refreshCatalog();

