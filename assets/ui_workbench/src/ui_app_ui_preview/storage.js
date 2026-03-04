import { state } from "./context.js";
import { isDerivedHtmlFileName } from "./helpers.js";

// --------------------------------------------------------------------- persist selection (ux)
// 目标：避免用户打开页面看到空白，以为“控件没导出/底部看不到”。
export var STORAGE_KEY_LAST_SELECTED = "ui_preview:last_selected";
export var STORAGE_KEY_CHECKED_FILES = "ui_preview:checked_files_v1";

export function encodeSelectionKey(scope, fileName) {
  return String(scope || "project") + ":" + String(fileName || "");
}

export function decodeSelectionKey(text) {
  var raw = String(text || "");
  if (!raw) return null;
  var idx = raw.indexOf(":");
  if (idx < 0) return null;
  return { scope: raw.slice(0, idx) || "project", file_name: raw.slice(idx + 1) };
}

export function loadCheckedFilesFromStorage() {
  // 注意：不使用 JSON.parse（避免历史脏值导致初始化抛错）。
  // 存储格式：每行一个 selectionKey（scope:fileName）。
  var raw = String((window && window.localStorage ? (window.localStorage.getItem(STORAGE_KEY_CHECKED_FILES) || "") : "") || "");
  var out = {};
  if (raw) {
    var lines = raw.split("\n");
    for (var i = 0; i < lines.length; i++) {
      var k = String(lines[i] || "").trim();
      if (!k) continue;
      out[k] = true;
    }
  }
  state.checked_files = out;
}

export function saveCheckedFilesToStorage() {
  if (!window || !window.localStorage) return;
  var keys = [];
  var cur = state.checked_files || {};
  for (var k in cur) {
    if (!Object.prototype.hasOwnProperty.call(cur, k)) continue;
    if (cur[k]) keys.push(String(k));
  }
  keys.sort();
  window.localStorage.setItem(STORAGE_KEY_CHECKED_FILES, keys.join("\n"));
}

export function isFileChecked(scope, fileName) {
  var key = encodeSelectionKey(scope, fileName);
  if (!key) return false;
  return !!(state.checked_files && state.checked_files[key]);
}

export function setFileChecked(scope, fileName, checked) {
  var key = encodeSelectionKey(scope, fileName);
  if (!key) return;
  if (!state.checked_files) state.checked_files = {};
  if (checked) {
    state.checked_files[key] = true;
  } else {
    delete state.checked_files[key];
  }
  saveCheckedFilesToStorage();
}

export function pruneCheckedFilesByCatalogItems(items) {
  var list = Array.isArray(items) ? items : [];
  var allowed = {};
  for (var i = 0; i < list.length; i++) {
    var it = list[i] || {};
    var fileName = String(it.file_name || it.fileName || "");
    var scope = String(it.scope || "project");
    if (!fileName) continue;
    if (isDerivedHtmlFileName(fileName)) continue;
    allowed[encodeSelectionKey(scope, fileName)] = true;
  }
  var changed = false;
  var cur = state.checked_files || {};
  for (var k in cur) {
    if (!Object.prototype.hasOwnProperty.call(cur, k)) continue;
    if (!allowed[k]) {
      delete cur[k];
      changed = true;
    }
  }
  if (changed) {
    state.checked_files = cur;
    saveCheckedFilesToStorage();
  }
}

export function getCheckedSelectionsInCatalogOrder() {
  var out = [];
  var items = state.items || [];
  for (var i = 0; i < items.length; i++) {
    var it = items[i] || {};
    var fileName = String(it.file_name || it.fileName || "");
    var scope = String(it.scope || "project");
    if (!fileName) continue;
    if (isDerivedHtmlFileName(fileName)) continue;
    if (isFileChecked(scope, fileName)) {
      out.push({ scope: scope, file_name: fileName });
    }
  }
  return out;
}

export function pickDefaultSelectableItem(items) {
  // 选择策略：
  // 1) 优先：项目 scope 的“原稿 HTML”（非 *.flattened.html）
  // 2) 其次：任意 scope 的“原稿 HTML”
  // 3) 最后：列表第一个（即便是派生）
  var i;
  for (i = 0; i < items.length; i++) {
    var it = items[i] || {};
    var fileName = String(it.file_name || it.fileName || "");
    var scope = String(it.scope || "project");
    if (!fileName) continue;
    if (scope !== "project") continue;
    if (isDerivedHtmlFileName(fileName)) continue;
    return { scope: scope, file_name: fileName };
  }
  for (i = 0; i < items.length; i++) {
    var it2 = items[i] || {};
    var fileName2 = String(it2.file_name || it2.fileName || "");
    var scope2 = String(it2.scope || "project");
    if (!fileName2) continue;
    if (isDerivedHtmlFileName(fileName2)) continue;
    return { scope: scope2, file_name: fileName2 };
  }
  if (items.length > 0) {
    var it3 = items[0] || {};
    var fileName3 = String(it3.file_name || it3.fileName || "");
    var scope3 = String(it3.scope || "project");
    if (fileName3) return { scope: scope3, file_name: fileName3 };
  }
  return null;
}

