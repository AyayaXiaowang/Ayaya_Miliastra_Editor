import { dom, state, setSubtitle } from "./context.js";
import { updateUseCurrentBaseGilButtonEnabled } from "./base_gil_cache.js";

export async function fetchJson(url) {
  var resp = await fetch(url, { cache: "no-store" });
  var ct = String((resp.headers && resp.headers.get && resp.headers.get("content-type")) || "").toLowerCase();
  if (ct.indexOf("application/json") < 0) {
    throw new Error("接口未返回 JSON：" + url);
  }
  return await resp.json();
}

export async function refreshStatus() {
  var resp = await fetch("/api/ui_converter/status", { cache: "no-store" });
  if (!resp || !resp.ok) {
    state.apiConnected = false;
    state.suggestedBaseGilPath = "";
    updateUseCurrentBaseGilButtonEnabled();
    setSubtitle("（未连接主程序）");
    return;
  }
  var contentType = String(resp.headers && resp.headers.get ? (resp.headers.get("content-type") || "") : "").toLowerCase();
  if (contentType.indexOf("application/json") < 0) {
    state.apiConnected = false;
    state.suggestedBaseGilPath = "";
    updateUseCurrentBaseGilButtonEnabled();
    setSubtitle("（未连接主程序）");
    return;
  }
  var data = await resp.json();
  if (data && data.ok && data.connected) {
    state.apiConnected = true;
    state.suggestedBaseGilPath = String(data.suggested_base_gil_path || "").trim();
    updateUseCurrentBaseGilButtonEnabled();
    if (data.is_global_view) {
      setSubtitle("（当前：<共享资源>）");
    } else {
      var name = String(data.current_package_name || "");
      var pid = String(data.current_package_id || "");
      setSubtitle("（当前项目存档：" + (name ? name : pid) + "）");
    }
    return;
  }
  state.apiConnected = false;
  state.suggestedBaseGilPath = "";
  updateUseCurrentBaseGilButtonEnabled();
  setSubtitle("（未连接主程序）");
}

export function buildUiSourceGetUrl(scope, fileName) {
  return "/api/ui_converter/ui_source?scope=" + encodeURIComponent(String(scope || "project")) + "&rel_path=" + encodeURIComponent(String(fileName || ""));
}

export function buildUiSourceRawUrl(scope, fileName) {
  return "/api/ui_converter/ui_source_raw?scope=" + encodeURIComponent(String(scope || "project")) + "&rel_path=" + encodeURIComponent(String(fileName || ""));
}

export async function readUiSourceContent(scope, fileName) {
  var url = buildUiSourceGetUrl(scope, fileName);
  var data = await fetchJson(url);
  if (!data || !data.ok) {
    throw new Error(String((data && data.error) || "读取 UI 源码失败"));
  }
  return String(data.content || "");
}

