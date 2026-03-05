import { dom, state, updateSelectedBaseGilUi } from "./context.js";

// --------------------------------------------------------------------- persist base gil (ux)
// 目标：用户选择一次“基底 .gil”，下次打开页面自动恢复，避免每次重复选择。
// 说明：浏览器无法程序化回填 <input type="file">，因此这里缓存的是“文件内容”，并在内存里恢复为 File 对象供导出使用。
// 重要：
// - 浏览器侧缓存（IndexedDB/localStorage）按 origin（含端口）隔离；
// - 插件静态服务端口通常是随机端口，导致“看起来缓存了但下次端口变了就恢复失败”；
// - 因此：有后端 /api 时，优先把基底 GIL 缓存在后端（磁盘），保证跨端口稳定恢复；
//   离线静态打开时，仍保留 IndexedDB 缓存作为兜底。
var BASE_GIL_DB_NAME = "ui_preview_cache_db";
var BASE_GIL_STORE_NAME = "kv";
var BASE_GIL_RECORD_KEY = "base_gil";
var BASE_GIL_MAX_BYTES = 60 * 1024 * 1024; // 60MB hard cap
var BASE_GIL_BACKEND_CACHE_URL = "/api/ui_converter/base_gil_cache";
var BASE_GIL_BACKEND_HEADER_NAME_B64 = "X-Ui-Base-Gil-Name-B64";
var BASE_GIL_BACKEND_HEADER_LAST_MODIFIED = "X-Ui-Base-Gil-Last-Modified";

function _utf8ToB64(text) {
  // btoa 仅支持 latin1：这里用 encodeURIComponent 做 UTF-8 桥接
  var s = String(text || "");
  return btoa(unescape(encodeURIComponent(s)));
}

function _b64ToUtf8(b64) {
  var s = String(b64 || "");
  if (!s) return "";
  return decodeURIComponent(escape(atob(s)));
}

function _isIndexedDbAvailable() {
  return !!(window && window.indexedDB);
}

function _openBaseGilDb() {
  return new Promise(function (resolve) {
    if (!_isIndexedDbAvailable()) {
      resolve(null);
      return;
    }
    var req = window.indexedDB.open(BASE_GIL_DB_NAME, 1);
    req.onupgradeneeded = function (ev) {
      var db = ev.target.result;
      if (!db) return;
      if (!db.objectStoreNames.contains(BASE_GIL_STORE_NAME)) {
        db.createObjectStore(BASE_GIL_STORE_NAME, { keyPath: "key" });
      }
    };
    req.onsuccess = function (ev) {
      resolve(ev.target.result || null);
    };
    req.onerror = function () {
      // 缓存失败不应阻断主流程：直接当作“不可用”处理
      resolve(null);
    };
  });
}

function _idbGet(db, key) {
  return new Promise(function (resolve) {
    if (!db) {
      resolve(null);
      return;
    }
    var tx = db.transaction([BASE_GIL_STORE_NAME], "readonly");
    var store = tx.objectStore(BASE_GIL_STORE_NAME);
    var req = store.get(String(key || ""));
    req.onsuccess = function () {
      resolve(req.result || null);
    };
    req.onerror = function () {
      resolve(null);
    };
  });
}

function _idbPut(db, obj) {
  return new Promise(function (resolve) {
    if (!db) {
      resolve(false);
      return;
    }
    var tx = db.transaction([BASE_GIL_STORE_NAME], "readwrite");
    var store = tx.objectStore(BASE_GIL_STORE_NAME);
    var req = store.put(obj);
    req.onsuccess = function () {
      resolve(true);
    };
    req.onerror = function () {
      resolve(false);
    };
  });
}

function _readFileAsArrayBuffer(file) {
  var f = file || null;
  if (!f) {
    return Promise.resolve(null);
  }
  if (typeof f.arrayBuffer === "function") {
    return f.arrayBuffer();
  }
  return new Promise(function (resolve, reject) {
    var reader = new FileReader();
    reader.onload = function () {
      resolve(reader.result || null);
    };
    reader.onerror = function () {
      reject(new Error("读取文件失败"));
    };
    reader.readAsArrayBuffer(f);
  });
}

export async function saveBaseGilToCache(file) {
  if (!file || !file.name) {
    return;
  }
  var buf = await _readFileAsArrayBuffer(file);
  if (!buf) {
    throw new Error("基底 GIL 读取为空");
  }
  var bytes = buf instanceof ArrayBuffer ? buf : (buf.buffer || null);
  if (!bytes) {
    throw new Error("基底 GIL 读取结果不是 ArrayBuffer");
  }
  if (bytes.byteLength > BASE_GIL_MAX_BYTES) {
    throw new Error("基底 GIL 过大，已拒绝缓存（" + String(bytes.byteLength) + " bytes）");
  }
  var db = await _openBaseGilDb();
  await _idbPut(db, {
    key: BASE_GIL_RECORD_KEY,
    name: String(file.name || "base.gil"),
    last_modified: Number(file.lastModified || Date.now()),
    mime: String(file.type || "application/octet-stream"),
    bytes: bytes,
    bytes_len: Number(bytes.byteLength || 0),
    saved_at: Date.now(),
  });
}

export async function restoreBaseGilFromCache() {
  var db = await _openBaseGilDb();
  var rec = await _idbGet(db, BASE_GIL_RECORD_KEY);
  if (!rec) {
    return false;
  }
  var bytes = rec.bytes || null;
  var name = String(rec.name || "base.gil");
  if (!(bytes instanceof ArrayBuffer) && !(bytes && bytes.byteLength !== undefined)) {
    return false;
  }
  // 兼容：部分浏览器可能返回 Uint8Array/Blob 等；统一转成 Blob part
  var part = bytes;
  var mime = String(rec.mime || "application/octet-stream");
  var lm = Number(rec.last_modified || Date.now());
  state.baseGilFile = new File([part], name, { type: mime, lastModified: lm });
  updateSelectedBaseGilUi();
  return true;
}

export async function saveBaseGilToBackendCache(file) {
  if (!file || !file.name) {
    return;
  }
  if (!state.apiConnected) {
    return;
  }
  var buf = await _readFileAsArrayBuffer(file);
  if (!buf) {
    throw new Error("基底 GIL 读取为空");
  }
  var bytes = buf instanceof ArrayBuffer ? buf : (buf.buffer || null);
  if (!bytes) {
    throw new Error("基底 GIL 读取结果不是 ArrayBuffer");
  }
  if (bytes.byteLength > BASE_GIL_MAX_BYTES) {
    throw new Error("基底 GIL 过大，已拒绝缓存（" + String(bytes.byteLength) + " bytes）");
  }
  var resp = await fetch(BASE_GIL_BACKEND_CACHE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
      // header 需 ASCII：使用 base64(utf8) 传递文件名（可包含中文）
      "X-Ui-Base-Gil-Name-B64": _utf8ToB64(String(file.name || "base.gil")),
      "X-Ui-Base-Gil-Last-Modified": String(Number(file.lastModified || Date.now())),
    },
    body: bytes,
  });
  if (!resp || !resp.ok) {
    throw new Error("后端缓存基底 GIL 失败（" + String(resp ? resp.status : "no_resp") + "）");
  }
}

export async function restoreBaseGilFromBackendCache() {
  if (!state.apiConnected) {
    return false;
  }
  var resp = await fetch(BASE_GIL_BACKEND_CACHE_URL, { cache: "no-store" });
  if (!resp || !resp.ok) {
    return false;
  }
  var nameB64 = String(resp.headers && resp.headers.get ? (resp.headers.get(BASE_GIL_BACKEND_HEADER_NAME_B64) || "") : "");
  var lmText = String(resp.headers && resp.headers.get ? (resp.headers.get(BASE_GIL_BACKEND_HEADER_LAST_MODIFIED) || "") : "");
  var name = _b64ToUtf8(nameB64) || "base.gil";
  var lm = lmText && String(lmText).trim().match(/^\d+$/) ? Number(lmText) : Date.now();
  var bytes = await resp.arrayBuffer();
  if (!bytes) {
    return false;
  }
  state.baseGilFile = new File([bytes], name, { type: "application/octet-stream", lastModified: lm });
  updateSelectedBaseGilUi();
  return true;
}

export async function saveBaseGilToBestEffortCache(file) {
  // 有后端优先后端；同时保留 IndexedDB 作为离线/兜底（同 origin 下仍可用）
  await saveBaseGilToBackendCache(file);
  await saveBaseGilToCache(file);
}

export async function restoreBaseGilFromBestEffortCache() {
  var ok = await restoreBaseGilFromBackendCache();
  if (ok) return true;
  return await restoreBaseGilFromCache();
}

export function updateUseCurrentBaseGilButtonEnabled() {
  if (!dom.useCurrentBaseGilButton) return;
  dom.useCurrentBaseGilButton.disabled = !String(state.suggestedBaseGilPath || "").trim();
}

