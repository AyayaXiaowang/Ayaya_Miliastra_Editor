import { setExportStatusText, state } from "./context.js";
import { extractVariableDefaultsFromHtmlText } from "./variable_defaults.js";

function _jsonStringify(obj) {
  // 不 try/catch：失败直接抛出（便于定位循环引用等问题）
  return JSON.stringify(obj);
}

export async function importVariableDefaultsForCurrentSelection() {
  setExportStatusText("");
  if (!state.apiConnected) {
    setExportStatusText("未连接主程序：无法导入变量默认值。");
    return;
  }
  if (!state.selected) {
    setExportStatusText("未选择任何 UI源码 文件。");
    return;
  }
  var sourceHtmlText = String(state.selected.source_html || "");
  if (!String(sourceHtmlText || "").trim()) {
    setExportStatusText("当前源码为空：无法导入变量默认值。");
    return;
  }

  var variableDefaults = extractVariableDefaultsFromHtmlText(sourceHtmlText);
  var total = Object.keys(variableDefaults || {}).length || 0;
  if (total <= 0) {
    setExportStatusText("未检测到 data-ui-variable-defaults：无需导入。");
    return;
  }

  setExportStatusText("导入中：写入 lv/ps 变量默认值到当前项目…");
  var resp = await fetch("/api/ui_converter/import_variable_defaults", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: _jsonStringify({
      source_rel_path: String(state.selected.file_name || state.selected.base_file_name || ""),
      variable_defaults: variableDefaults
    })
  });
  var contentType = String((resp.headers && resp.headers.get("content-type")) || "").toLowerCase();
  if (contentType.indexOf("application/json") === -1) {
    var rawText = await resp.text();
    setExportStatusText([
      "导入失败：后端未返回 JSON（可能未连接主程序 / 进程未重启 / 旧版后端缺少该 API）。",
      "- http_status: " + String(resp.status),
      "- content_type: " + contentType,
      "",
      String(rawText || "").slice(0, 2000)
    ].join("\n"));
    return;
  }
  var data = await resp.json();
  if (data && data.ok) {
    // 只展示高信号摘要，避免刷屏；详细 report 仍可复制查看。
    var lv = data.lv || {};
    var ps = data.ps || {};
    var lvCreated = (lv.created && lv.created.length) ? lv.created.length : 0;
    var lvUpdated = (lv.updated && lv.updated.length) ? lv.updated.length : 0;
    var psCreated = (ps.created && ps.created.length) ? ps.created.length : 0;
    var psUpdated = (ps.updated && ps.updated.length) ? ps.updated.length : 0;
    var psTplUpdated = (ps.player_templates_updated && ps.player_templates_updated.length) ? ps.player_templates_updated.length : 0;
    setExportStatusText([
      "导入完成：",
      "- variable_defaults_total: " + String(total),
      "- lv: created " + String(lvCreated) + " / updated " + String(lvUpdated),
      "- ps: created " + String(psCreated) + " / updated " + String(psUpdated) + " / player_templates_updated " + String(psTplUpdated),
      "",
      "report:",
      _jsonStringify(data)
    ].join("\n"));
    return;
  }
  var errText = data && data.error ? String(data.error || "") : "";
  setExportStatusText(errText ? ("导入失败：\n" + errText) : ("导入失败：" + _jsonStringify(data || {})));
}

