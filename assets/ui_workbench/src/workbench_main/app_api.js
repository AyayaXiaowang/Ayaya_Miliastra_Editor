import { copyTextToClipboard, getBasenameFromPath, playSuccessBeep } from "../utils.js";

export function createAppApiController(opts) {
    var o = opts || {};

    var appContextTextElement = o.appContextTextElement;
    var importToAppButtonInlineElement = o.importToAppButtonInlineElement;
    var exportGilButtonInlineElement = o.exportGilButtonInlineElement;
    var exportGiaButtonInlineElement = o.exportGiaButtonInlineElement;
    var exportGiaButtonInlineTopElement = o.exportGiaButtonInlineTopElement;
    var importLayoutNameInputElement = o.importLayoutNameInputElement;
    var importStatusTextElement = o.importStatusTextElement;
    var exportGilStatusTextElement = o.exportGilStatusTextElement;
    var exportGilDownloadLinkElement = o.exportGilDownloadLinkElement;
    var exportGiaStatusTextElement = o.exportGiaStatusTextElement;
    var exportGiaDownloadLinkElement = o.exportGiaDownloadLinkElement;
    var exportGilVerifyCheckboxElement = o.exportGilVerifyCheckboxElement;
    var exportGilTargetLayoutGuidInputElement = o.exportGilTargetLayoutGuidInputElement;
    var uiSources = o.uiSources;
    var preview = o.preview;
    var getSelectedBaseGilFile = o.getSelectedBaseGilFile;
    var getCurrentSourceHash = o.getCurrentSourceHash;
    var getBundleState = o.getBundleState;
    var ensureBundleState = o.ensureBundleState;

    function _isExternalTokenActive(externalToken) {
        var t = externalToken || null;
        if (!t) return true;
        if (typeof t.isActive !== "function") return true;
        return !!t.isActive();
    }

    function setAppContextText(text) {
        if (!appContextTextElement) {
            return;
        }
        appContextTextElement.textContent = String(text || "");
    }

    function setImportStatusText(text) {
        if (!importStatusTextElement) {
            return;
        }
        importStatusTextElement.textContent = String(text || "");
    }

    function setExportGilStatusText(text) {
        if (!exportGilStatusTextElement) {
            return;
        }
        exportGilStatusTextElement.textContent = String(text || "");
    }

    function setExportGiaStatusText(text) {
        if (!exportGiaStatusTextElement) {
            return;
        }
        exportGiaStatusTextElement.textContent = String(text || "");
    }

    function setImportButtonEnabled(enabled) {
        if (!importToAppButtonInlineElement) {
            return;
        }
        importToAppButtonInlineElement.disabled = !enabled;
    }

    function setExportGilButtonEnabled(enabled) {
        if (!exportGilButtonInlineElement) {
            return;
        }
        exportGilButtonInlineElement.disabled = !enabled;
    }

    function setExportGiaButtonEnabled(enabled) {
        if (!exportGiaButtonInlineElement) {
            if (exportGiaButtonInlineTopElement) {
                exportGiaButtonInlineTopElement.disabled = !enabled;
            }
            return;
        }
        exportGiaButtonInlineElement.disabled = !enabled;
        if (exportGiaButtonInlineTopElement) {
            exportGiaButtonInlineTopElement.disabled = !enabled;
        }
    }

    function setExportGilDownloadLink(outputPath, fileName) {
        if (!exportGilDownloadLinkElement) {
            return;
        }
        var p = String(outputPath || "").trim();
        if (!p) {
            exportGilDownloadLinkElement.style.display = "none";
            exportGilDownloadLinkElement.textContent = "复制输出路径";
            exportGilDownloadLinkElement.dataset.outputPath = "";
            return;
        }
        exportGilDownloadLinkElement.style.display = "";
        exportGilDownloadLinkElement.dataset.outputPath = p;
        exportGilDownloadLinkElement.textContent = fileName ? ("复制输出路径：" + String(fileName)) : "复制输出路径";
    }

    function setExportGiaDownloadLink(outputPath, fileName) {
        if (!exportGiaDownloadLinkElement) {
            return;
        }
        var p = String(outputPath || "").trim();
        if (!p) {
            exportGiaDownloadLinkElement.style.display = "none";
            exportGiaDownloadLinkElement.textContent = "复制输出路径";
            exportGiaDownloadLinkElement.dataset.outputPath = "";
            return;
        }
        exportGiaDownloadLinkElement.style.display = "";
        exportGiaDownloadLinkElement.dataset.outputPath = p;
        exportGiaDownloadLinkElement.textContent = fileName ? ("复制输出路径：" + String(fileName)) : "复制输出路径";
    }

    function readFileAsDataUrl(file) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function () {
                resolve(String(reader.result || ""));
            };
            reader.onerror = function () {
                reject(new Error("读取文件失败"));
            };
            reader.readAsDataURL(file);
        });
    }

    async function refreshAppContextStatus(externalToken) {
        if (!appContextTextElement) {
            return;
        }
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        var url = "/api/ui_converter/status";
        var resp = await fetch(url, { cache: "no-store" });
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        if (!resp || !resp.ok) {
            // 独立打开 Workbench（无主程序 /api）时，浏览器会返回 404 HTML；
            // 这里必须视为“未连接主程序”，而不是让 resp.json() 抛异常中断初始化。
            setAppContextText("未连接主程序（请从主程序打开 UI预览）。");
            setImportButtonEnabled(false);
            setExportGilButtonEnabled(false);
            setExportGiaButtonEnabled(false);
            return;
        }
        var contentType = String(resp.headers && resp.headers.get ? (resp.headers.get("content-type") || "") : "");
        if (contentType.toLowerCase().indexOf("application/json") < 0) {
            setAppContextText("未连接主程序（请从主程序打开 UI预览）。");
            setImportButtonEnabled(false);
            setExportGilButtonEnabled(false);
            setExportGiaButtonEnabled(false);
            return;
        }
        var data = await resp.json();
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        if (!data || !data.ok || !data.connected) {
            setAppContextText("未连接主程序（请从主程序打开 UI预览）。");
            setImportButtonEnabled(false);
            setExportGilButtonEnabled(false);
            setExportGiaButtonEnabled(false);
            return;
        }
        var packageId = String(data.current_package_id || "");
        var packageName = String(data.current_package_name || "");
        if (data.is_global_view) {
            setAppContextText("当前在 <共享资源>：可生成 GIL，但无法导入到项目存档。");
            setImportButtonEnabled(false);
            setExportGilButtonEnabled(true);
            setExportGiaButtonEnabled(true);
            return;
        }
        if (!packageId) {
            setAppContextText("未选择项目存档：可生成 GIL，但无法导入到项目存档。");
            setImportButtonEnabled(false);
            setExportGilButtonEnabled(true);
            setExportGiaButtonEnabled(true);
            return;
        }
        setAppContextText("当前项目存档：" + (packageName ? packageName : packageId));
        setImportButtonEnabled(true);
        setExportGilButtonEnabled(true);
        setExportGiaButtonEnabled(true);
    }

    async function importIntoApp(externalToken) {
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        setImportStatusText("");
        await refreshAppContextStatus(externalToken);
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }

        if (!importToAppButtonInlineElement || importToAppButtonInlineElement.disabled) {
            return;
        }

        var sel = uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.currentSelection : null;
        var sourceRelPath = sel && sel.scope === "project" ? String(sel.rel_path || "").trim() : "";
        var useUiPageImport = !!sourceRelPath;

        var layoutName = importLayoutNameInputElement ? String(importLayoutNameInputElement.value || "").trim() : "";
        if (!layoutName) {
            layoutName = String(uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.lastSelectedHtmlFileStem : "").trim() || "HTML导入_界面布局";
        }

        if (ensureBundleState) {
            await ensureBundleState(externalToken);
        }
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        var state = getBundleState ? getBundleState() : null;
        var currentHash = getCurrentSourceHash ? String(getCurrentSourceHash() || "") : "";
        if (state && state.sourceHash !== undefined && String(state.sourceHash || "") !== currentHash) {
            setImportStatusText("当前 bundle 已过期或导出被打断：请先重新导出 UI布局 Bundle JSON，再执行导入。");
            return;
        }
        var bundleObj = state && state.bundleObj ? state.bundleObj : null;
        if (!bundleObj) {
            setImportStatusText("请先导出 UI布局 Bundle JSON（确保输入 HTML 非空）。");
            return;
        }
        var templatesList = bundleObj && bundleObj.templates;
        var templateCount = Array.isArray(templatesList) ? templatesList.length : 0;
        if (templateCount <= 0) {
            setImportStatusText(
                "导入跳过：bundle.templates 为空（未识别到可导入的控件模板）。\n" +
                "说明：这不影响“源码/扁平”预览切换；但在当前导入规则下，templates 为空会导致后端拒绝导入。"
            );
            return;
        }

        var apiUrl = useUiPageImport ? "/api/ui_converter/import_ui_page" : "/api/ui_converter/import_layout";
        var postBody = {
            layout_name: layoutName,
            bundle: bundleObj
        };
        if (useUiPageImport) {
            postBody.source_rel_path = sourceRelPath;
        }

        var resp = await fetch(apiUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(postBody)
        });
        var respData = await resp.json();
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        if (respData && respData.ok) {
            setImportStatusText([
                "导入成功：",
                useUiPageImport ? ("- HTML：" + String(respData.source_html_relpath || sourceRelPath)) : "- HTML：未绑定（使用旧导入接口）",
                "- 布局：" + String(respData.layout_name || "") + " (" + String(respData.layout_id || "") + ")",
                "- 模板数：" + String(respData.template_count || 0),
                "- 控件数：" + String(respData.widget_count || 0)
            ].join("\n"));
            return;
        }
        var errText = respData && respData.error ? String(respData.error || "") : "";
        setImportStatusText(errText ? ("导入失败：\n" + errText) : ("导入失败：" + JSON.stringify(respData || {})));
    }

    async function exportGilFromWorkbench(externalToken) {
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        setExportGilStatusText("");
        setExportGilDownloadLink("", "");
        await refreshAppContextStatus(externalToken);
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }

        if (!exportGilButtonInlineElement || exportGilButtonInlineElement.disabled) {
            return;
        }

        var layoutName = importLayoutNameInputElement ? String(importLayoutNameInputElement.value || "").trim() : "";
        if (!layoutName) {
            layoutName = String(uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.lastSelectedHtmlFileStem : "").trim() || "HTML导出_界面布局";
        }

        var state = getBundleState ? getBundleState() : null;
        if (!state || !state.bundleObj) {
            if (ensureBundleState) {
                await ensureBundleState(externalToken);
            }
            state = getBundleState ? getBundleState() : null;
        }
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        var currentHash = getCurrentSourceHash ? String(getCurrentSourceHash() || "") : "";
        if (state && state.sourceHash !== undefined && String(state.sourceHash || "") !== currentHash) {
            setExportGilStatusText("当前 bundle 已过期或导出被打断：请先重新导出 UI布局 Bundle JSON，再生成 GIL。");
            return;
        }
        if (!state || !state.bundleObj) {
            setExportGilStatusText("请先导出 UI布局 Bundle JSON（确保输入 HTML 非空）。");
            return;
        }

        var bundleObj = state.bundleObj;

        var verifyWithDllDump = exportGilVerifyCheckboxElement ? !!exportGilVerifyCheckboxElement.checked : true;
        var targetLayoutGuid = null;
        if (exportGilTargetLayoutGuidInputElement) {
            var parsedLayoutGuid = Number(String(exportGilTargetLayoutGuidInputElement.value || "").trim());
            if (isFinite(parsedLayoutGuid) && parsedLayoutGuid > 0) {
                targetLayoutGuid = Math.trunc(parsedLayoutGuid);
            }
        }

        // IMPORTANT: 生成 GIL 时必须传递“当前导出所依据的 PC 画布尺寸”。
        var selectedCanvasSizeOption = o.getCanvasSizeByKey(preview.getCurrentSelectedCanvasSizeKey());
        var pcCanvasSizePayload = selectedCanvasSizeOption
            ? { x: Number(selectedCanvasSizeOption.width || 1600), y: Number(selectedCanvasSizeOption.height || 900) }
            : { x: 1600, y: 900 };

        var reqBody = {
            layout_name: layoutName,
            bundle: bundleObj,
            verify_with_dll_dump: verifyWithDllDump,
            target_layout_guid: targetLayoutGuid,
            pc_canvas_size: pcCanvasSizePayload
        };

        var selectedBaseGilFile = getSelectedBaseGilFile ? getSelectedBaseGilFile() : null;
        if (selectedBaseGilFile) {
            var dataUrl = await readFileAsDataUrl(selectedBaseGilFile);
            if (!_isExternalTokenActive(externalToken)) {
                return;
            }
            var base64 = "";
            if (dataUrl.indexOf(",") >= 0) {
                base64 = String(dataUrl.split(",", 2)[1] || "");
            }
            if (!base64) {
                throw new Error("base_gil_upload 为空（可能读取失败）");
            }
            reqBody.base_gil_upload = {
                file_name: String(selectedBaseGilFile.name || "base.gil"),
                content_base64: base64
            };
        }

        var resp = await fetch("/api/ui_converter/export_gil", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(reqBody)
        });
        var respData = await resp.json();
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        if (respData && respData.ok) {
            var report = respData.report || {};
            var result = report && report.result ? report.result : {};
            var referencedVariablesTotal = report && report.referenced_variables_total !== undefined ? Number(report.referenced_variables_total || 0) : 0;
            var skippedTotal = result && result.skipped_widgets_total !== undefined ? Number(result.skipped_widgets_total || 0) : 0;
            var skippedList = report && Array.isArray(report.skipped_widgets) ? report.skipped_widgets : [];
            var skippedHintLines = [];
            if (isFinite(skippedTotal) && skippedTotal > 0 && skippedList && skippedList.length > 0) {
                var maxHint = Math.min(3, skippedList.length);
                for (var si = 0; si < maxHint; si++) {
                    var it = skippedList[si] || {};
                    var t = String(it.widget_type || "");
                    var rid = String(it.widget_id || it.ui_key || "");
                    var reason = String(it.reason || "");
                    skippedHintLines.push("  - " + (t ? ("[" + t + "] ") : "") + (rid ? (rid + "：") : "") + reason);
                }
                if (skippedList.length > maxHint) {
                    skippedHintLines.push("  - ...（仅展示前 " + String(maxHint) + " 条）");
                }
            }
            var statusText = [
                "生成成功：",
                "- output: " + String(respData.output_gil_path || ""),
                "- imported_progressbars: " + String(result.imported_progressbars_total || 0),
                "- imported_textboxes: " + String(result.imported_textboxes_total || 0),
                "- imported_item_displays: " + String(result.imported_item_displays_total || 0),
                "- skipped_widgets: " + String(isFinite(skippedTotal) ? Math.trunc(skippedTotal) : 0),
                "- referenced_variables: " + String(isFinite(referencedVariablesTotal) ? Math.trunc(referencedVariablesTotal) : 0),
                "提示：进度条是作为【布局控件】写回的，不会写进【控件模板库】；请在布局 children/界面布局中查看。",
                (skippedHintLines.length > 0 ? ("skipped 详情（采样）：\n" + skippedHintLines.join("\n")) : "")
            ].filter(function (x) { return String(x || "").trim() !== ""; }).join("\n");

            setExportGilStatusText(statusText);

            var outputPath = String(respData.output_gil_path || "");
            var fileName = String(respData.output_file_name || "");
            setExportGilDownloadLink(outputPath, fileName);

            playSuccessBeep();

            var nameToCopy = String(fileName || "").trim() || getBasenameFromPath(outputPath);
            if (nameToCopy) {
                copyTextToClipboard(nameToCopy)
                    .then(function () {
                        setExportGilStatusText(statusText + "\n\n已复制文件名到剪贴板：" + nameToCopy);
                    })
                    .catch(function (err) {
                        setExportGilStatusText(
                            statusText +
                                "\n\n自动复制失败（可能被浏览器权限拦截）：\n- file_name: " +
                                nameToCopy +
                                "\n- error: " +
                                String(err || "")
                        );
                    });
            }
            return;
        }

        var errText = respData && respData.error ? String(respData.error || "") : "";
        setExportGilStatusText(errText ? ("生成失败：\n" + errText) : ("生成失败：" + JSON.stringify(respData || {})));
    }

    async function exportGiaFromWorkbench(externalToken) {
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        setExportGiaStatusText("");
        setExportGiaDownloadLink("", "");
        await refreshAppContextStatus(externalToken);
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }

        if (!exportGiaButtonInlineElement || exportGiaButtonInlineElement.disabled) {
            return;
        }

        var layoutName = importLayoutNameInputElement ? String(importLayoutNameInputElement.value || "").trim() : "";
        if (!layoutName) {
            layoutName = String(uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.lastSelectedHtmlFileStem : "").trim() || "HTML导出_界面布局";
        }

        var state = getBundleState ? getBundleState() : null;
        if (!state || !state.bundleObj) {
            if (ensureBundleState) {
                await ensureBundleState(externalToken);
            }
            state = getBundleState ? getBundleState() : null;
        }
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        var currentHash = getCurrentSourceHash ? String(getCurrentSourceHash() || "") : "";
        if (state && state.sourceHash !== undefined && String(state.sourceHash || "") !== currentHash) {
            setExportGiaStatusText("当前 bundle 已过期或导出被打断：请先重新导出 UI布局 Bundle JSON，再生成 GIA。");
            return;
        }
        if (!state || !state.bundleObj) {
            setExportGiaStatusText("请先导出 UI布局 Bundle JSON（确保输入 HTML 非空）。");
            return;
        }

        var bundleObj = state.bundleObj;

        var verifyWithDllDump = exportGilVerifyCheckboxElement ? !!exportGilVerifyCheckboxElement.checked : true;
        var targetLayoutGuid = null;
        if (exportGilTargetLayoutGuidInputElement) {
            var parsedLayoutGuid = Number(String(exportGilTargetLayoutGuidInputElement.value || "").trim());
            if (isFinite(parsedLayoutGuid) && parsedLayoutGuid > 0) {
                targetLayoutGuid = Math.trunc(parsedLayoutGuid);
            }
        }

        var selectedCanvasSizeOption = o.getCanvasSizeByKey(preview.getCurrentSelectedCanvasSizeKey());
        var pcCanvasSizePayload = selectedCanvasSizeOption
            ? { x: Number(selectedCanvasSizeOption.width || 1600), y: Number(selectedCanvasSizeOption.height || 900) }
            : { x: 1600, y: 900 };

        var reqBody = {
            layout_name: layoutName,
            bundle: bundleObj,
            verify_with_dll_dump: verifyWithDllDump,
            target_layout_guid: targetLayoutGuid,
            pc_canvas_size: pcCanvasSizePayload
        };

        var selectedBaseGilFile = getSelectedBaseGilFile ? getSelectedBaseGilFile() : null;
        if (selectedBaseGilFile) {
            var dataUrl = await readFileAsDataUrl(selectedBaseGilFile);
            if (!_isExternalTokenActive(externalToken)) {
                return;
            }
            var base64 = "";
            if (dataUrl.indexOf(",") >= 0) {
                base64 = String(dataUrl.split(",", 2)[1] || "");
            }
            if (!base64) {
                throw new Error("base_gil_upload 为空（可能读取失败）");
            }
            reqBody.base_gil_upload = {
                file_name: String(selectedBaseGilFile.name || "base.gil"),
                content_base64: base64
            };
        }

        var resp = await fetch("/api/ui_converter/export_gia", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(reqBody)
        });
        var respData = await resp.json();
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        if (respData && respData.ok) {
            setExportGiaStatusText([
                "生成成功：",
                "- output_gia: " + String(respData.output_gia_path || ""),
                "- output_gil: " + String(respData.output_gil_path || "")
            ].join("\n"));
            var outputPath = String(respData.output_gia_path || "");
            var fileName = String(respData.output_file_name || "");
            setExportGiaDownloadLink(outputPath, fileName);
            return;
        }

        var errText = respData && respData.error ? String(respData.error || "") : "";
        setExportGiaStatusText(errText ? ("生成失败：\n" + errText) : ("生成失败：" + JSON.stringify(respData || {})));
    }

    return {
        refreshAppContextStatus: refreshAppContextStatus,
        importIntoApp: importIntoApp,
        exportGilFromWorkbench: exportGilFromWorkbench,
        exportGiaFromWorkbench: exportGiaFromWorkbench,
        setExportGilDownloadLink: setExportGilDownloadLink,
        setExportGilStatusText: setExportGilStatusText,
        setExportGiaDownloadLink: setExportGiaDownloadLink,
        setExportGiaStatusText: setExportGiaStatusText,
        setImportStatusText: setImportStatusText
    };
}

