import { copyTextToClipboard, ensureSuccessBeepAudioUnlocked, getBasenameFromPath, playSuccessBeep } from "../utils.js";
import { getCanvasSizeByKey } from "../config.js";
import { dom, setExportStatusText, setStatusText, state, updateSelectedBaseGilUi } from "./context.js";
import { applyExportExcludesToBundlePayload } from "./export_widgets_model.js";
import { buildBundlePayloadForCurrentSelection } from "./bundle.js";
import { getCheckedSelectionsInCatalogOrder } from "./storage.js";
import { selectFile } from "./selection.js";

function _jsonStringify(obj) {
  // 不 try/catch：失败直接抛出（便于定位循环引用等问题）
  return JSON.stringify(obj);
}

function _readFileAsDataUrl(file) {
  return new Promise(function (resolve, reject) {
    var f = file;
    if (!f) {
      reject(new Error("file is required"));
      return;
    }
    var fr = new FileReader();
    fr.onload = function () {
      resolve(String(fr.result || ""));
    };
    fr.onerror = function () {
      reject(new Error("读取文件失败：" + String((f && f.name) || "")));
    };
    fr.readAsDataURL(f);
  });
}

function _buildPcCanvasSizePayloadFromBundle(bundlePayload, fallbackCanvasSizeOption) {
  var key = bundlePayload ? String(bundlePayload.canvas_size_key || "").trim() : "";
  var opt = key ? getCanvasSizeByKey(key) : null;
  if (opt && Number.isFinite(Number(opt.width)) && Number.isFinite(Number(opt.height)) && Number(opt.width) > 0 && Number(opt.height) > 0) {
    return { x: Number(opt.width), y: Number(opt.height) };
  }
  // 兜底：使用本次 bundle 构建时的选择项（防止 UI state 与 bundle 不一致）
  if (fallbackCanvasSizeOption && Number.isFinite(Number(fallbackCanvasSizeOption.width)) && Number.isFinite(Number(fallbackCanvasSizeOption.height))) {
    var fw = Number(fallbackCanvasSizeOption.width || 1600);
    var fh = Number(fallbackCanvasSizeOption.height || 900);
    if (fw > 0 && fh > 0) {
      return { x: fw, y: fh };
    }
  }
  return { x: 1600, y: 900 };
}

export async function exportGiaForCurrentSelection() {
  setExportStatusText("");
  if (!state.selected) {
    setExportStatusText("未选择任何 UI源码 文件。");
    return;
  }
  if (!state.apiConnected) {
    setExportStatusText("未连接主程序：无法导出 GIA（请从主程序打开该页面）。");
    return;
  }
  var sourceHtmlText = String(state.selected.source_html || "");
  if (!String(sourceHtmlText || "").trim()) {
    setExportStatusText("当前源码为空：无法导出。");
    return;
  }

  setExportStatusText("生成 bundle…");
  var built = await buildBundlePayloadForCurrentSelection();
  if (!built || built.ok !== true) {
    setExportStatusText(String((built && built.error) ? built.error : "生成 bundle 失败：未知错误"));
    return;
  }
  var layoutName = built.layoutName;
  var bundlePayload = built.bundlePayload;
  var selectedCanvasSizeOption = built.selectedCanvasSizeOption;
  var filteredBundlePayload = applyExportExcludesToBundlePayload(bundlePayload);
  if (!filteredBundlePayload || !Array.isArray(filteredBundlePayload.templates) || filteredBundlePayload.templates.length <= 0) {
    setExportStatusText("已全部标记为“排除导出”，本次导出取消。");
    return;
  }

  setExportStatusText("请求后端生成 GIA…");
  var pcCanvasSizePayload = _buildPcCanvasSizePayloadFromBundle(filteredBundlePayload, selectedCanvasSizeOption);

  var resp = await fetch("/api/ui_converter/export_gia", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: _jsonStringify({
      layout_name: layoutName,
      bundle: filteredBundlePayload,
      verify_with_dll_dump: true,
      pc_canvas_size: pcCanvasSizePayload
    })
  });
  var respData = await resp.json();
  if (respData && respData.ok) {
    var outputGia = String(respData.output_gia_path || "");
    var outputGil = String(respData.output_gil_path || "");
    setExportStatusText([
      "生成成功：",
      "- output_gia: " + outputGia,
      "- output_gil: " + outputGil
    ].join("\n"));
    await ensureSuccessBeepAudioUnlocked();
    playSuccessBeep();
    if (outputGia) {
      copyTextToClipboard(getBasenameFromPath(outputGia));
    }
    return;
  }
  var errText = respData && respData.error ? String(respData.error || "") : "";
  setExportStatusText(errText ? ("生成失败：\n" + errText) : ("生成失败：" + _jsonStringify(respData || {})));
}

export async function exportGilForCurrentSelection() {
  setExportStatusText("");
  if (!state.selected) {
    setExportStatusText("未选择任何 UI源码 文件。");
    return;
  }
  if (!state.apiConnected) {
    setExportStatusText("未连接主程序：无法导出 GIL（请从主程序打开该页面）。");
    return;
  }
  var sourceHtmlText = String(state.selected.source_html || "");
  if (!String(sourceHtmlText || "").trim()) {
    setExportStatusText("当前源码为空：无法导出。");
    return;
  }
  var hasBaseGil = !!(
    (state.baseGilFile && state.baseGilFile.name) ||
    String(state.baseGilPath || "").trim()
  );
  if (!hasBaseGil) {
    setExportStatusText("请先选择一个基底存档（.gil），再导出 GIL。");
    return;
  }

  setExportStatusText("生成 bundle…");
  var built = await buildBundlePayloadForCurrentSelection();
  if (!built || built.ok !== true) {
    setExportStatusText(String((built && built.error) ? built.error : "生成 bundle 失败：未知错误"));
    return;
  }
  var layoutName = built.layoutName;
  var bundlePayload = built.bundlePayload;
  var selectedCanvasSizeOption = built.selectedCanvasSizeOption;

  var filteredBundlePayload = applyExportExcludesToBundlePayload(bundlePayload);
  if (!filteredBundlePayload || !Array.isArray(filteredBundlePayload.templates) || filteredBundlePayload.templates.length <= 0) {
    setExportStatusText("已全部标记为“排除导出”，本次导出取消。");
    return;
  }

  var reqBaseGilUpload = null;
  var reqBaseGilPath = String(state.baseGilPath || "").trim();
  if (state.baseGilFile && state.baseGilFile.name) {
    setExportStatusText("读取基底 GIL…");
    var dataUrl = await _readFileAsDataUrl(state.baseGilFile);
    var base64 = "";
    if (String(dataUrl || "").indexOf(",") >= 0) {
      base64 = String(String(dataUrl || "").split(",", 2)[1] || "");
    }
    if (!base64) {
      throw new Error("base_gil_upload 为空（可能读取失败）");
    }
    reqBaseGilUpload = {
      file_name: String(state.baseGilFile.name || "base.gil"),
      content_base64: base64
    };
    reqBaseGilPath = "";
  } else if (!reqBaseGilPath) {
    setExportStatusText("基底 GIL 为空：请重新选择（文件或“用当前 GIL”）。");
    return;
  }

  setExportStatusText("请求后端生成 GIL…");
  var pcCanvasSizePayload = _buildPcCanvasSizePayloadFromBundle(filteredBundlePayload, selectedCanvasSizeOption);

  var saveCustomTemplatesCheckbox = document.getElementById("exportGilSaveCustomTemplatesCheckbox");
  var saveButtonGroupsAsCustomTemplates = saveCustomTemplatesCheckbox ? !!saveCustomTemplatesCheckbox.checked : false;

  var resp = await fetch("/api/ui_converter/export_gil", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: _jsonStringify({
      layout_name: layoutName,
      bundle: filteredBundlePayload,
      verify_with_dll_dump: true,
      pc_canvas_size: pcCanvasSizePayload,
      base_gil_upload: reqBaseGilUpload,
      base_gil_path: reqBaseGilPath,
      save_button_groups_as_custom_templates: saveButtonGroupsAsCustomTemplates
    })
  });
  var respData = await resp.json();
  if (respData && respData.ok) {
    var outputGil = String(respData.output_gil_path || "");
    var outputFileName = String(respData.output_file_name || "");
    setExportStatusText([
      "生成成功：",
      "- output_gil: " + outputGil,
      (outputFileName ? ("- output_file_name: " + outputFileName) : "")
    ].filter(Boolean).join("\n"));
    await ensureSuccessBeepAudioUnlocked();
    playSuccessBeep();
    if (outputFileName) {
      copyTextToClipboard(outputFileName);
    } else if (outputGil) {
      copyTextToClipboard(getBasenameFromPath(outputGil));
    }
    return;
  }
  var errText = respData && respData.error ? String(respData.error || "") : "";
  setExportStatusText(errText ? ("生成失败：\n" + errText) : ("生成失败：" + _jsonStringify(respData || {})));
}

export async function exportGilForCheckedSelections(checkedSelections) {
  setExportStatusText("");
  if (!state.apiConnected) {
    setExportStatusText("未连接主程序：无法导出 GIL（请从主程序打开该页面）。");
    return;
  }

  var list = Array.isArray(checkedSelections) ? checkedSelections : getCheckedSelectionsInCatalogOrder();
  if (!list || list.length <= 0) {
    setExportStatusText("未勾选任何页面：无法批量导出。");
    return;
  }

  var hasBaseGil = !!(
    (state.baseGilFile && state.baseGilFile.name) ||
    String(state.baseGilPath || "").trim()
  );
  if (!hasBaseGil) {
    setExportStatusText("请先选择一个基底存档（.gil），再导出 GIL。");
    return;
  }

  // 读取基底 gil（一次；批量导出共用）
  var reqBaseGilUpload = null;
  var reqBaseGilPath = String(state.baseGilPath || "").trim();
  if (state.baseGilFile && state.baseGilFile.name) {
    setExportStatusText("读取基底 GIL…");
    var dataUrl = await _readFileAsDataUrl(state.baseGilFile);
    var base64 = "";
    if (String(dataUrl || "").indexOf(",") >= 0) {
      base64 = String(String(dataUrl || "").split(",", 2)[1] || "");
    }
    if (!base64) {
      throw new Error("base_gil_upload 为空（可能读取失败）");
    }
    reqBaseGilUpload = {
      file_name: String(state.baseGilFile.name || "base.gil"),
      content_base64: base64
    };
    reqBaseGilPath = "";
  } else if (!reqBaseGilPath) {
    setExportStatusText("基底 GIL 为空：请重新选择（文件或“用当前 GIL”）。");
    return;
  }

  // 记录当前选中，批量导出会临时切换页面
  var original = state.selected ? { scope: String(state.selected.scope || "project"), file_name: String(state.selected.file_name || "") } : null;

  var bundles = [];
  for (var i = 0; i < list.length; i++) {
    var it = list[i] || {};
    var scope = String(it.scope || "project");
    var fileName = String(it.file_name || "");
    if (!fileName) continue;

    setExportStatusText("生成 bundle（" + String(i + 1) + "/" + String(list.length) + "）： " + scope + ":" + fileName);
    await selectFile(scope, fileName);

    var built = await buildBundlePayloadForCurrentSelection();
    if (!built || built.ok !== true) {
      throw new Error("生成 bundle 失败：" + String((built && built.error) ? built.error : "未知错误"));
    }
    var filteredBundlePayload = applyExportExcludesToBundlePayload(built.bundlePayload);
    if (!filteredBundlePayload || !Array.isArray(filteredBundlePayload.templates) || filteredBundlePayload.templates.length <= 0) {
      // 全部被排除：跳过该页
      continue;
    }
    var pcCanvasSizePayload = _buildPcCanvasSizePayloadFromBundle(filteredBundlePayload, built.selectedCanvasSizeOption);

    bundles.push({
      layout_name: String(built.layoutName || ""),
      bundle: filteredBundlePayload,
      pc_canvas_size: pcCanvasSizePayload,
    });
  }

  if (!bundles || bundles.length <= 0) {
    setExportStatusText("已全部标记为“排除导出”，本次批量导出取消。");
    if (original && original.file_name) {
      await selectFile(original.scope, original.file_name);
    }
    return;
  }

  setExportStatusText("请求后端批量生成 GIL…（" + String(bundles.length) + " 页）");
  var saveCustomTemplatesCheckbox = document.getElementById("exportGilSaveCustomTemplatesCheckbox");
  var saveButtonGroupsAsCustomTemplates = saveCustomTemplatesCheckbox ? !!saveCustomTemplatesCheckbox.checked : false;

  var resp = await fetch("/api/ui_converter/export_gil", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: _jsonStringify({
      bundles: bundles,
      verify_with_dll_dump: true,
      base_gil_upload: reqBaseGilUpload,
      base_gil_path: reqBaseGilPath,
      save_button_groups_as_custom_templates: saveButtonGroupsAsCustomTemplates
    })
  });
  var respData = await resp.json();
  if (respData && respData.ok) {
    var outputGil = String(respData.output_gil_path || "");
    var outputFileName = String(respData.output_file_name || "");
    setExportStatusText([
      "生成成功：",
      "- output_gil: " + outputGil,
      (outputFileName ? ("- output_file_name: " + outputFileName) : ""),
      "- exported_bundles_total: " + String((respData.report && respData.report.exported_bundles_total) ? respData.report.exported_bundles_total : ""),
      "- skipped_bundles_total: " + String((respData.report && respData.report.skipped_bundles_total) ? respData.report.skipped_bundles_total : ""),
    ].filter(Boolean).join("\n"));
    await ensureSuccessBeepAudioUnlocked();
    playSuccessBeep();
    if (outputFileName) {
      copyTextToClipboard(outputFileName);
    } else if (outputGil) {
      copyTextToClipboard(getBasenameFromPath(outputGil));
    }
  } else {
    var errText = respData && respData.error ? String(respData.error || "") : "";
    setExportStatusText(errText ? ("生成失败：\n" + errText) : ("生成失败：" + _jsonStringify(respData || {})));
  }

  // 恢复原选择（避免用户导出完还停留在最后一页）
  if (original && original.file_name) {
    setStatusText("恢复原选择…");
    await selectFile(original.scope, original.file_name);
    setStatusText("就绪");
  }
}

export function setBaseGilFile(file) {
  state.baseGilFile = file || null;
  updateSelectedBaseGilUi();
}

export function setBaseGilPath(pathText) {
  state.baseGilPath = String(pathText || "").trim();
  updateSelectedBaseGilUi();
}

