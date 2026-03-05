import { dom } from "../dom_refs.js";

export const uiSourceState = {
    catalogItems: [],
    currentSelection: null, // { scope, rel_path, file_name, is_shared }
    lastSelectedHtmlFileStem: "",
    flattenedStatusByKey: {},
    onlyShowFlattened: false
};

var _callbacks = {
    setLeftTab: null,
    onFileStemChanged: null,
    onSelectionChanging: null,
    onFileOpened: null,
    onCatalogRefreshed: null,
};

var uiSourceSearchInputElement = dom.uiSourceSearchInputElement;
var uiSourceListContainerElement = dom.uiSourceListContainerElement;
var uiSourceCurrentFileTextElement = dom.uiSourceCurrentFileTextElement;
var uiSourceHintTextElement = dom.uiSourceHintTextElement;
var inputHtmlTextAreaElement = dom.inputHtmlTextAreaElement;
var uiSourceBatchImportButtonElement = dom.uiSourceBatchImportButtonElement;

var _batchImportRunning = false;

export function getBatchImportRunning() {
    return !!_batchImportRunning;
}

export function initUiSourceBrowser(options) {
    var opts = options || {};
    _callbacks.setLeftTab = typeof opts.setLeftTab === "function" ? opts.setLeftTab : null;
    _callbacks.onFileStemChanged = typeof opts.onFileStemChanged === "function" ? opts.onFileStemChanged : null;
    _callbacks.onSelectionChanging = typeof opts.onSelectionChanging === "function" ? opts.onSelectionChanging : null;
    _callbacks.onFileOpened = typeof opts.onFileOpened === "function" ? opts.onFileOpened : null;
    _callbacks.onCatalogRefreshed = typeof opts.onCatalogRefreshed === "function" ? opts.onCatalogRefreshed : null;

    if (uiSourceBatchImportButtonElement && uiSourceBatchImportButtonElement.addEventListener) {
        uiSourceBatchImportButtonElement.addEventListener("click", async function () {
            await batchProcessProjectUiSources();
        });
    }
}

function _buildFlattenedStatusKey(scope, relPath) {
    var s = String(scope || "project");
    var rp = String(relPath || "");
    if (!rp) {
        return "";
    }
    return s + "::" + rp;
}

export function setUiSourceOnlyShowFlattened(enabled) {
    uiSourceState.onlyShowFlattened = !!enabled;
    renderUiSourceList();
}

export function clearUiSourceFlattenedStatus() {
    uiSourceState.flattenedStatusByKey = {};
}

export function setUiSourceFlattenedStatus(scope, relPath, ready, options) {
    var key = _buildFlattenedStatusKey(scope, relPath);
    if (!key) {
        return;
    }
    uiSourceState.flattenedStatusByKey[key] = !!ready;
    var opts = options || {};
    if (!opts.silent) {
        renderUiSourceList();
    }
}

function _isUiSourceFlattenedReady(scope, relPath) {
    var key = _buildFlattenedStatusKey(scope, relPath);
    if (!key) {
        return false;
    }
    return !!uiSourceState.flattenedStatusByKey[key];
}

export function setUiSourceCurrentFileText(text) {
    if (!uiSourceCurrentFileTextElement) return;
    uiSourceCurrentFileTextElement.textContent = String(text || "未选择");
}

export function setUiSourceHintText(text) {
    if (!uiSourceHintTextElement) return;
    uiSourceHintTextElement.textContent = String(text || "");
}

export function renderUiSourceList() {
    if (!uiSourceListContainerElement) return;
    var q = String((uiSourceSearchInputElement && uiSourceSearchInputElement.value) || "").trim().toLowerCase();
    uiSourceListContainerElement.innerHTML = "";

    var items = uiSourceState.catalogItems || [];
    for (var i = 0; i < items.length; i++) {
        var it = items[i] || {};
        var fileName = String(it.file_name || it.fileName || "");
        var relPath = String(it.rel_path || it.relPath || "");
        var scope = String(it.scope || "project");
        var isShared = Boolean(it.is_shared || it.isShared);

        if (q && fileName.toLowerCase().indexOf(q) === -1) {
            continue;
        }
        if (uiSourceState.onlyShowFlattened && !isShared) {
            if (!_isUiSourceFlattenedReady(scope, relPath)) {
                continue;
            }
        }

        var row = document.createElement("div");
        row.className = "wb-list-item";
        row.dataset.scope = scope;
        row.dataset.relPath = relPath;
        row.dataset.fileName = fileName;
        row.dataset.isShared = isShared ? "1" : "0";

        var badge = document.createElement("span");
        badge.className = "wb-badge" + (isShared ? " shared" : "");
        badge.textContent = isShared ? "共享" : "项目";

        var title = document.createElement("div");
        title.style.flex = "1";
        title.textContent = fileName;

        row.appendChild(badge);
        row.appendChild(title);
        row.addEventListener("click", async function (ev) {
            var target = ev.currentTarget;
            var s = String(target.dataset.scope || "project");
            var rp = String(target.dataset.relPath || "");
            if (!rp) return;
            await openUiSourceToEditor(s, rp);
        });

        uiSourceListContainerElement.appendChild(row);
    }
}

export async function refreshUiSourceCatalog() {
    setUiSourceHintText("正在刷新 UI源码清单...");
    var resp = await fetch("/api/ui_converter/ui_source_catalog");
    var contentType = String((resp.headers && resp.headers.get("content-type")) || "").toLowerCase();
    if (contentType.indexOf("application/json") === -1) {
        setUiSourceHintText("未连接主程序（无法读取 UI源码清单）。");
        uiSourceState.catalogItems = [];
        renderUiSourceList();
        return;
    }
    var data = await resp.json();
    if (!data || !data.ok) {
        setUiSourceHintText("刷新失败：" + String((data && data.error) || resp.statusText || "unknown"));
        uiSourceState.catalogItems = [];
        renderUiSourceList();
        return;
    }
    uiSourceState.catalogItems = data.items || [];
    setUiSourceHintText("已加载：" + String(uiSourceState.catalogItems.length) + " 个文件（项目 + 共享）。");
    if (_callbacks.onCatalogRefreshed) {
        var handled = await _callbacks.onCatalogRefreshed(uiSourceState.catalogItems);
        if (handled) {
            return;
        }
    }
    renderUiSourceList();
}

export async function openUiSourceToEditor(scope, relPath) {
    var s = String(scope || "project");
    var rp = String(relPath || "");
    // Update selection immediately (before await fetch) so that:
    // - browse pipeline can detect selection change and stop early
    // - workbench can cancel in-flight heavy ops ASAP
    var stubFileName = rp ? String(rp).split("/").pop().split("\\").pop() : "";
    uiSourceState.currentSelection = {
        scope: s,
        rel_path: rp,
        file_name: stubFileName || rp,
        is_shared: false
    };
    setUiSourceCurrentFileText("加载中：" + String(uiSourceState.currentSelection.file_name || rp));

    uiSourceState.lastSelectedHtmlFileStem = String(uiSourceState.currentSelection.file_name || "").replace(/\.html?$/i, "");
    if (_callbacks.onFileStemChanged) {
        _callbacks.onFileStemChanged(uiSourceState.lastSelectedHtmlFileStem);
    }
    if (_callbacks.onSelectionChanging) {
        _callbacks.onSelectionChanging(uiSourceState.currentSelection);
    }
    var url = "/api/ui_converter/ui_source?scope=" + encodeURIComponent(s) + "&rel_path=" + encodeURIComponent(rp);
    var resp = await fetch(url);
    var contentType = String((resp.headers && resp.headers.get("content-type")) || "").toLowerCase();
    if (contentType.indexOf("application/json") === -1) {
        setUiSourceHintText("未连接主程序（无法打开 UI源码）。");
        return;
    }
    var data = await resp.json();
    if (!data || !data.ok) {
        setUiSourceHintText("打开失败：" + String((data && data.error) || resp.statusText || "unknown"));
        return;
    }
    uiSourceState.currentSelection = {
        scope: String(data.scope || s),
        rel_path: String(data.rel_path || rp),
        file_name: String(data.file_name || rp),
        is_shared: Boolean(data.is_shared)
    };
    setUiSourceCurrentFileText((uiSourceState.currentSelection.is_shared ? "共享：" : "项目：") + uiSourceState.currentSelection.file_name);

    if (inputHtmlTextAreaElement) {
        inputHtmlTextAreaElement.value = String(data.content || "");
    }

    uiSourceState.lastSelectedHtmlFileStem = String(uiSourceState.currentSelection.file_name || "").replace(/\.html?$/i, "");
    if (_callbacks.onFileStemChanged) {
        _callbacks.onFileStemChanged(uiSourceState.lastSelectedHtmlFileStem);
    }
    // browse 模式：保持在“UI源码”列表，不强制切到“编辑”
    var isBrowseMode = !!(document && document.body && document.body.dataset && document.body.dataset.workbenchMode === "browse");
    if (_callbacks.setLeftTab) {
        _callbacks.setLeftTab(isBrowseMode ? "ui_sources" : "editor");
    }
    if (_callbacks.onFileOpened) {
        await _callbacks.onFileOpened(uiSourceState.currentSelection);
    }
}

export async function batchProcessProjectUiSources() {
    if (_batchImportRunning) {
        setUiSourceHintText("批处理正在进行中，请稍候…");
        return;
    }
    _batchImportRunning = true;

    await refreshUiSourceCatalog();
    var items = uiSourceState.catalogItems || [];
    var projectItems = [];
    for (var i = 0; i < items.length; i++) {
        var it = items[i] || {};
        var scope = String(it.scope || "project");
        var relPath = String(it.rel_path || it.relPath || "");
        var fileName = String(it.file_name || it.fileName || relPath);
        if (scope !== "project") {
            continue;
        }
        if (!relPath) {
            continue;
        }
        projectItems.push({ rel_path: relPath, file_name: fileName });
    }

    if (!projectItems.length) {
        setUiSourceHintText("项目 UI源码 为空：无需批处理。");
        _batchImportRunning = false;
        return;
    }

    setUiSourceHintText("开始批处理：将依次打开每个项目 HTML 并自动扁平化/导出/导入…");
    for (var j = 0; j < projectItems.length; j++) {
        var p = projectItems[j];
        setUiSourceHintText("批处理中…[" + String(j + 1) + "/" + String(projectItems.length) + "] " + String(p.file_name || p.rel_path || ""));
        await openUiSourceToEditor("project", String(p.rel_path || ""));
    }
    setUiSourceHintText("批处理完成：已依次处理项目 UI源码（具体成功/失败见导入状态区）。");
    _batchImportRunning = false;
}

export function setCurrentUiSourceSelection(selection) {
    uiSourceState.currentSelection = selection || null;
    if (uiSourceState.currentSelection && uiSourceState.currentSelection.file_name) {
        uiSourceState.lastSelectedHtmlFileStem = String(uiSourceState.currentSelection.file_name || "").replace(/\.html?$/i, "");
        if (_callbacks.onFileStemChanged) {
            _callbacks.onFileStemChanged(uiSourceState.lastSelectedHtmlFileStem);
        }
    }
}

export async function saveCurrentEditorToProjectUiSource() {
    if (!inputHtmlTextAreaElement) {
        setUiSourceHintText("没有可保存的 HTML 文本框。");
        return;
    }
    var content = String(inputHtmlTextAreaElement.value || "");
    var relPath = "";
    if (uiSourceState.currentSelection && uiSourceState.currentSelection.scope === "project" && uiSourceState.currentSelection.rel_path) {
        relPath = String(uiSourceState.currentSelection.rel_path);
    } else {
        var defaultName = (uiSourceState.lastSelectedHtmlFileStem ? uiSourceState.lastSelectedHtmlFileStem : "新页面") + ".html";
        relPath = String(prompt("保存为（项目 UI源码 文件名）：", defaultName) || "").trim();
    }
    if (!relPath) return;
    if (!/\.html?$/i.test(relPath)) relPath = relPath + ".html";

    var resp = await fetch("/api/ui_converter/ui_source", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rel_path: relPath, content: content })
    });
    var contentType = String((resp.headers && resp.headers.get("content-type")) || "").toLowerCase();
    if (contentType.indexOf("application/json") === -1) {
        setUiSourceHintText("未连接主程序（无法保存 UI源码）。");
        return;
    }
    var data = await resp.json();
    if (!data || !data.ok) {
        setUiSourceHintText("保存失败：" + String((data && data.error) || resp.statusText || "unknown"));
        return;
    }
    uiSourceState.currentSelection = { scope: "project", rel_path: relPath, file_name: String(data.file_name || relPath), is_shared: false };
    setUiSourceCurrentFileText("项目：" + uiSourceState.currentSelection.file_name);
    setUiSourceHintText("已保存到项目 UI源码：" + uiSourceState.currentSelection.file_name);
    uiSourceState.lastSelectedHtmlFileStem = String(uiSourceState.currentSelection.file_name || "").replace(/\.html?$/i, "");
    if (_callbacks.onFileStemChanged) {
        _callbacks.onFileStemChanged(uiSourceState.lastSelectedHtmlFileStem);
    }
    await refreshUiSourceCatalog();
}

