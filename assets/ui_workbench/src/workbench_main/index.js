import { dom } from "../dom_refs.js";
import { CANVAS_SIZE_CATALOG, PREVIEW_VARIANT_FLATTENED, PREVIEW_VARIANT_SOURCE, getCanvasSizeByKey } from "../config.js";
import { buildFlattenedInjectionHtml, buildFlattenedLayerData, extractDisplayElementsData, generateFlattenedDivs, injectContentIntoBody, normalizeSizeKeyForCssClass, replaceBodyInnerHtml, rewritePageSwitchLinksForFlattenedOutput, rewriteResourcePathsForFlattenedOutput } from "../flatten.js";
import { buildUiLayoutBundleFromFlattenedLayers } from "../ui_control_group_export.js";
import * as preview from "../preview/index.js";
import * as uiSources from "../workbench/ui_sources.js";
import * as variables from "../workbench/variables.js";
import { autoFixHtmlSource, validateHtmlSource, validatePreviewComputedRules, validateTextFontSizeUniformAcrossCanvasSizes } from "../validation.js";
import { buildAiFixPack, concatIssues, createDiagnosticsCollector, createIssue, dedupeIssues, formatIssuesAsText, splitIssuesBySeverity, summarizeIssues } from "../diagnostics.js";
import { copyTextToClipboard, ensureSuccessBeepAudioUnlocked, hashTextFNV1a32Hex, waitForNextFrame } from "../utils.js";
import { runAutoTestIfRequested } from "./autotest.js";
import { createPreviewVariantSwitcher } from "./preview_variant_switch.js";
import { createFlatteningController } from "./flattening.js";
import { createAppApiController } from "./app_api.js";
import { createFlattenGroupTreeController } from "./group_tree.js";
import { createRunQueue } from "./run_queue.js";
import { bindWorkbenchDomEvents } from "./events.js";

export function initializeWorkbench() {
    var inputHtmlTextAreaElement = dom.inputHtmlTextAreaElement;
    var validationErrorsTextAreaElement = dom.validationErrorsTextAreaElement;
    var flattenedOutputTextAreaElement = dom.flattenedOutputTextAreaElement;
    var uiControlGroupJsonOutputTextAreaElement = dom.uiControlGroupJsonOutputTextAreaElement;
    var inspectorImportantTextAreaElement = dom.inspectorImportantTextAreaElement;
    var inspectorDetailsTextAreaElement = dom.inspectorDetailsTextAreaElement;
    var workbenchWorkflowStatusTextElement = dom.workbenchWorkflowStatusTextElement;
    var autoImportToAppCheckboxElement = dom.autoImportToAppCheckboxElement;

    var _workflowPrimaryStatusText = "就绪";
    var _workflowOperationStatusText = "";

    function _renderWorkflowStatusText() {
        if (!workbenchWorkflowStatusTextElement) {
            return;
        }
        var primary = String(_workflowPrimaryStatusText || "").trim();
        var op = String(_workflowOperationStatusText || "").trim();
        var combined = "";
        if (primary && op) {
            combined = primary + " | " + op;
        } else if (primary) {
            combined = primary;
        } else {
            combined = op;
        }
        workbenchWorkflowStatusTextElement.textContent = combined;
    }

    function setWorkflowStatusText(text) {
        _workflowPrimaryStatusText = String(text || "");
        _renderWorkflowStatusText();
    }

    function setOperationStatusText(text) {
        _workflowOperationStatusText = String(text || "");
        _renderWorkflowStatusText();
    }

    // Global single-channel queue for heavy ops.
    // Any operation that writes shared resources (compute iframe / caches / panels / bundleState) must go through this queue.
    var runQueue = createRunQueue({
        onStatus: function (text) {
            // Queue status is "operation-level"; do not overwrite primary workflow status (browse/prompt).
            setOperationStatusText(text);
        },
        onDebug: function (_text) {
            // Intentionally quiet in UI; keep hook for future debugging.
        }
    });

    var lastGeneratedFlattenedHtmlText = "";
    var lastFlattenedSourceHash = "";
    var lastFlattenedErrorText = "";
    var lastValidationIssues = [];
    var lastValidatedSourceHash = "";
    var validationIsUpToDate = false;
    var lastFlattenDowngradeIssues = [];
    var lastExportDowngradeIssues = [];
    var lastExportStringWarningIssues = [];
    var lastGeneratedUiControlGroupJsonText = "";
    var lastUiControlGroupSourceHtmlText = "";
    var flattenCacheByUiSourceKey = new Map();
    var _uiCatalogPrefetchFirstRun = true;

    function _buildUiSourceCacheKey(scope, relPath) {
        var s = String(scope || "project");
        var rp = String(relPath || "");
        if (!rp) {
            return "";
        }
        return s + "::" + rp;
    }

    function _getCurrentUiSourceCacheKey() {
        var sel = uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.currentSelection : null;
        if (!sel || !sel.scope || !sel.rel_path) {
            return "";
        }
        return _buildUiSourceCacheKey(sel.scope, sel.rel_path);
    }

    function _getFlattenCacheEntryByKey(cacheKey) {
        if (!cacheKey) {
            return null;
        }
        return flattenCacheByUiSourceKey.has(cacheKey) ? flattenCacheByUiSourceKey.get(cacheKey) : null;
    }

    function _getFlattenCacheEntryForCurrentSelection() {
        return _getFlattenCacheEntryByKey(_getCurrentUiSourceCacheKey());
    }

    function _setFlattenCacheEntry(cacheKey, entry, options) {
        if (!cacheKey) {
            return;
        }
        if (!entry) {
            flattenCacheByUiSourceKey.delete(cacheKey);
            return;
        }
        flattenCacheByUiSourceKey.set(cacheKey, entry);
        var opts = options || {};
        if (uiSources && uiSources.setUiSourceFlattenedStatus && entry.scope && entry.rel_path) {
            var ready = !!(entry.flattenedHtmlText && entry.sourceHash) && !entry.errorText;
            uiSources.setUiSourceFlattenedStatus(entry.scope, entry.rel_path, ready, { silent: !!opts.silent });
        }
    }

    function _invalidateFlattenCacheForSelection(selection) {
        if (!selection || !selection.scope || !selection.rel_path) {
            return;
        }
        var cacheKey = _buildUiSourceCacheKey(selection.scope, selection.rel_path);
        if (!cacheKey) {
            return;
        }
        flattenCacheByUiSourceKey.delete(cacheKey);
        if (uiSources && uiSources.setUiSourceFlattenedStatus) {
            uiSources.setUiSourceFlattenedStatus(selection.scope, selection.rel_path, false);
        }
    }

    function _hydrateFlattenCacheForSelection(selection) {
        if (!selection || !selection.scope || !selection.rel_path) {
            return false;
        }
        var cacheKey = _buildUiSourceCacheKey(selection.scope, selection.rel_path);
        var entry = _getFlattenCacheEntryByKey(cacheKey);
        if (!entry || !entry.sourceHash || !entry.flattenedHtmlText) {
            return false;
        }
        var currentHash = _getCurrentSourceHash();
        if (String(entry.sourceHash || "") !== String(currentHash || "")) {
            return false;
        }
        lastGeneratedFlattenedHtmlText = String(entry.flattenedHtmlText || "");
        lastFlattenedSourceHash = String(entry.sourceHash || "");
        lastFlattenedErrorText = String(entry.errorText || "");
        return true;
    }

    function _scheduleImmediateFlattenIfMissing(selection) {
        if (!selection || !selection.scope || !selection.rel_path) {
            return;
        }
        var cacheKey = _buildUiSourceCacheKey(selection.scope, selection.rel_path);
        var entry = _getFlattenCacheEntryByKey(cacheKey);
        if (entry && entry.sourceHash && entry.flattenedHtmlText && !entry.errorText) {
            return;
        }
        handleGenerateFlattened();
    }

    function _computeSourceHashFromHtmlText(htmlText) {
        var raw = String(htmlText || "");
        var canonical = preview && preview.normalizeHtmlForSandboxedPreviewSrcDoc
            ? preview.normalizeHtmlForSandboxedPreviewSrcDoc(raw)
            : raw;
        return hashTextFNV1a32Hex(canonical);
    }

    function _getCurrentSourceHash() {
        var raw = inputHtmlTextAreaElement ? String(inputHtmlTextAreaElement.value || "") : "";
        return _computeSourceHashFromHtmlText(raw);
    }

    function _getCurrentSourceSessionKeyPrefix() {
        var sel = uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.currentSelection : null;
        if (sel && sel.scope && sel.rel_path) {
            return "ui_source:" + String(sel.scope) + ":" + String(sel.rel_path);
        }
        return "editor";
    }

    function _syncRunQueueSessionKeyToCurrentSource() {
        if (!runQueue || typeof runQueue.setSessionKey !== "function") {
            return;
        }
        var sessionKey = _getCurrentSourceSessionKeyPrefix() + ":" + _getCurrentSourceHash();
        runQueue.setSessionKey(sessionKey);
    }

    function _resetDiagnosticsToUnvalidated(reasonText) {
        validationIsUpToDate = false;
        lastValidatedSourceHash = "";
        lastValidationIssues = [];
        lastFlattenDowngradeIssues = [];
        lastExportDowngradeIssues = [];
        lastExportStringWarningIssues = [];
        if (validationErrorsTextAreaElement) {
            var msg = String(reasonText || "").trim();
            if (!msg) {
                msg = "未校验：内容已变更。";
            }
            validationErrorsTextAreaElement.value = [
                "【未校验】",
                msg,
                "",
                "下一步：",
                "- 点击“校验并渲染”（Ctrl+Enter）或“自动修正并校验”",
                "- 校验通过后会自动预生成扁平缓存；切到“扁平模式”将变为纯显示",
                ""
            ].join("\n");
        }
        setValidationBadgeToUnvalidated();
    }

    function _resetDerivedOutputsForSourceChange() {
        // Flatten cache + output
        lastGeneratedFlattenedHtmlText = "";
        lastFlattenedSourceHash = "";
        lastFlattenedErrorText = "";
        if (flattenedOutputTextAreaElement) {
            flattenedOutputTextAreaElement.value = "";
        }

        // Bundle cache + output
        if (bundleState) {
            bundleState.bundleObj = null;
            bundleState.jsonText = "";
            bundleState.sourceHash = "";
            bundleState.templateCount = 0;
            bundleState.widgetCount = 0;
            bundleState.updatedAtMs = 0;
        }
        if (uiControlGroupJsonOutputTextAreaElement) {
            uiControlGroupJsonOutputTextAreaElement.value = "";
        }
    }

    function _buildExportStringWarningIssuesFromBundle(bundleObj) {
        var out = [];
        if (!bundleObj || !bundleObj._export_warnings || !Array.isArray(bundleObj._export_warnings)) {
            return out;
        }
        var wList = bundleObj._export_warnings;
        for (var wi = 0; wi < wList.length; wi++) {
            var w = String(wList[wi] || "").trim();
            if (!w) continue;
            out.push(createIssue({
                code: "EXPORT.WARNING",
                severity: "warning",
                message: w,
                fix: { kind: "downgrade", suggestion: "这是导出阶段的降级/归一化提示；通常可忽略，但建议在 HTML/布局上减少差异。" }
            }));
        }
        return out;
    }

    function _getDiagnosticsState() {
        var validation = Array.isArray(lastValidationIssues) ? lastValidationIssues : [];
        var flattenDowngrades = Array.isArray(lastFlattenDowngradeIssues) ? lastFlattenDowngradeIssues : [];
        var exportDowngrades = Array.isArray(lastExportDowngradeIssues) ? lastExportDowngradeIssues : [];
        var exportWarnings = Array.isArray(lastExportStringWarningIssues) ? lastExportStringWarningIssues : [];
        var all = dedupeIssues(concatIssues(validation, flattenDowngrades, exportDowngrades, exportWarnings));
        return {
            validation: validation,
            flatten: flattenDowngrades,
            export: exportDowngrades,
            export_warnings: exportWarnings,
            all: all,
            buckets: splitIssuesBySeverity(all),
        };
    }

    function _renderDiagnosticsPanel(titleText) {
        var diag = _getDiagnosticsState();
        if (validationErrorsTextAreaElement) {
            var title = String(titleText || "").trim();
            var lines = [];
            if (title) {
                lines.push("【" + title + "】");
                lines.push("");
            }
            // Keep semantics separated to avoid "校验通过但一堆降级提示"造成错觉。
            if (!validationIsUpToDate) {
                lines.push("【校验（结构/运行态）】");
                lines.push("未校验：请点击“校验并渲染”（Ctrl+Enter）或“自动修正并校验”。");
            } else {
                lines.push(formatIssuesAsText(diag.validation, { title: "校验（结构/运行态）" }));
            }
            lines.push("");
            lines.push(formatIssuesAsText(diag.flatten, { title: "扁平化（降级/近似/归一化提示）" }));
            lines.push("");
            lines.push(formatIssuesAsText(concatIssues(diag.export, diag.export_warnings), { title: "导出（降级/归一化提示）" }));
            validationErrorsTextAreaElement.value = lines.join("\n");
        }
    }

    function _setValidationIssues(issues, titleText, validatedSourceHash) {
        var list = Array.isArray(issues) ? issues : [];
        list = dedupeIssues(list);
        lastValidationIssues = list;
        validationIsUpToDate = true;
        lastValidatedSourceHash = String(validatedSourceHash || _getCurrentSourceHash() || "");
        _renderDiagnosticsPanel(titleText || "");
        setValidationBadge(list);
    }

    function _appendValidationIssue(issue) {
        var it = issue || null;
        if (!it) return;
        lastValidationIssues = dedupeIssues(concatIssues(lastValidationIssues, [it]));
        validationIsUpToDate = true;
        lastValidatedSourceHash = _getCurrentSourceHash();
        _renderDiagnosticsPanel("校验结果");
        setValidationBadge(lastValidationIssues);
    }

    function _getValidationSummary() {
        if (!validationIsUpToDate) {
            return { error: 1, warning: 0, info: 0, total: 1 };
        }
        return summarizeIssues(lastValidationIssues);
    }

    var bundleState = {
        bundleObj: null,
        jsonText: "",
        sourceHash: "",
        templateCount: 0,
        widgetCount: 0,
        updatedAtMs: 0,
    };

    function _getQueryParam(key) {
        var k = String(key || "").trim();
        if (!k) return "";
        var q = String((window && window.location && window.location.search) || "");
        if (!q) return "";
        if (q.indexOf("?") === 0) q = q.slice(1);
        var parts = q.split("&");
        for (var i = 0; i < parts.length; i++) {
            var p = parts[i] || "";
            if (p.indexOf("=") < 0) continue;
            var kv = p.split("=", 2);
            if (decodeURIComponent(kv[0] || "") === k) {
                return decodeURIComponent(kv[1] || "");
            }
        }
        return "";
    }

    function _applyWorkbenchMode(modeKey) {
        var m = String(modeKey || "").trim();
        if (!m) m = "browse";
        if (document && document.body && document.body.dataset) {
            document.body.dataset.workbenchMode = m;
        }
    }

    var uiState = {
        leftTabKey: "editor",
        inspectorTabKey: "info",
        importLayoutNameUserEdited: false,
        importLayoutNameProgrammaticUpdate: false,
        selectedBaseGilFile: null,
    };

    function setLeftTab(tabKey) {
        var key = String(tabKey || "editor");
        uiState.leftTabKey = key;

        if (dom.leftTabEditorButtonElement) dom.leftTabEditorButtonElement.classList.toggle("active", key === "editor");
        if (dom.leftTabUiSourcesButtonElement) dom.leftTabUiSourcesButtonElement.classList.toggle("active", key === "ui_sources");
        if (dom.leftTabVariablesButtonElement) dom.leftTabVariablesButtonElement.classList.toggle("active", key === "variables");

        if (dom.leftPaneEditorElement) dom.leftPaneEditorElement.style.display = key === "editor" ? "" : "none";
        if (dom.leftPaneUiSourcesElement) dom.leftPaneUiSourcesElement.style.display = key === "ui_sources" ? "" : "none";
        if (dom.leftPaneVariablesElement) dom.leftPaneVariablesElement.style.display = key === "variables" ? "" : "none";
    }

    function getLeftTabKey() {
        return uiState.leftTabKey;
    }

    function setInspectorTab(tabKey) {
        var key = tabKey === "group" ? "group" : "info";
        uiState.inspectorTabKey = key;
        if (dom.inspectorTabInfoButtonElement && dom.inspectorTabInfoButtonElement.classList) {
            dom.inspectorTabInfoButtonElement.classList.toggle("active", key === "info");
        }
        if (dom.inspectorTabGroupButtonElement && dom.inspectorTabGroupButtonElement.classList) {
            dom.inspectorTabGroupButtonElement.classList.toggle("active", key === "group");
        }
        if (dom.inspectorTabInfoPaneElement) {
            dom.inspectorTabInfoPaneElement.style.display = key === "info" ? "" : "none";
        }
        if (dom.inspectorTabGroupPaneElement) {
            dom.inspectorTabGroupPaneElement.style.display = key === "group" ? "" : "none";
        }
        if (key === "group") {
            flattenGroupTreeController.refresh();
        }
    }

    var _browsePipelineInProgress = false;
    var _pendingBrowseSelection = null;

    function _isSameUiSourceSelection(a, b) {
        var aScope = a ? String(a.scope || "") : "";
        var aRel = a ? String(a.rel_path || "") : "";
        var bScope = b ? String(b.scope || "") : "";
        var bRel = b ? String(b.rel_path || "") : "";
        return !!(aScope && aRel && aScope === bScope && aRel === bRel);
    }

    function _isSelectionStillCurrent(selection) {
        return _isSameUiSourceSelection(selection, uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.currentSelection : null);
    }

    function _shouldAutoImportInBrowse() {
        var enabledByCheckbox = !!(autoImportToAppCheckboxElement && autoImportToAppCheckboxElement.checked);
        var enabledByBatch = !!(uiSources && typeof uiSources.getBatchImportRunning === "function" && uiSources.getBatchImportRunning());
        return enabledByCheckbox || enabledByBatch;
    }

    async function _runBrowsePipelineOnce(selection) {
        var fileLabel = selection ? String(selection.file_name || selection.rel_path || "").trim() : "";

        setWorkflowStatusText(fileLabel ? ("Browse：处理中 - " + fileLabel) : "Browse：处理中…");
        await handleAutoFixAndRender();
        if (!_isSelectionStillCurrent(selection)) {
            setWorkflowStatusText("Browse：已取消（选择已变化）");
            return;
        }
        var vSummary = _getValidationSummary();
        if (vSummary && vSummary.error > 0) {
            setWorkflowStatusText("Browse：校验未通过（errors=" + String(vSummary.error) + "），已停止。可点右侧“复制 AI 修复包”。");
            return;
        }

        setWorkflowStatusText("Browse：生成扁平化…");
        await handleGenerateFlattened();
        if (!_isSelectionStillCurrent(selection)) {
            setWorkflowStatusText("Browse：已取消（选择已变化）");
            return;
        }

        setWorkflowStatusText("Browse：导出 UI布局 Bundle…");
        await handleExportUiControlGroupJson();
        if (!_isSelectionStillCurrent(selection)) {
            setWorkflowStatusText("Browse：已取消（选择已变化）");
            return;
        }

        if (_shouldAutoImportInBrowse()) {
            setWorkflowStatusText("Browse：导入到项目存档…");
            // 若未连接主程序（/api 404）或未选择项目 HTML，则 importIntoApp 会自行提示/退出。
            await handleImportIntoApp();
        } else {
            if (appApiController && typeof appApiController.setImportStatusText === "function") {
                appApiController.setImportStatusText("Browse 自动导入已关闭：仅生成/预览，不写回项目存档。");
            }
        }
        if (!_isSelectionStillCurrent(selection)) {
            setWorkflowStatusText("Browse：已取消（选择已变化）");
            return;
        }

        // browse 流水线不再强制切换预览变体：预览切换属于“纯显示”，由用户按钮决定。
        setWorkflowStatusText("就绪");
    }

    async function scheduleBrowsePipeline(selection) {
        _pendingBrowseSelection = selection || null;
        if (_browsePipelineInProgress) {
            return;
        }
        _browsePipelineInProgress = true;
        while (_pendingBrowseSelection) {
            var sel = _pendingBrowseSelection;
            _pendingBrowseSelection = null;
            await _runBrowsePipelineOnce(sel);
        }
        _browsePipelineInProgress = false;
    }

    function _isBrowseModeEnabled() {
        return !!(document && document.body && document.body.dataset && document.body.dataset.workbenchMode === "browse");
    }

    async function _fetchUiSourceContent(scope, relPath) {
        var s = String(scope || "project");
        var rp = String(relPath || "");
        if (!rp) {
            return null;
        }
        var url = "/api/ui_converter/ui_source?scope=" + encodeURIComponent(s) + "&rel_path=" + encodeURIComponent(rp);
        var resp = await fetch(url);
        var contentType = String((resp.headers && resp.headers.get("content-type")) || "").toLowerCase();
        if (contentType.indexOf("application/json") === -1) {
            return null;
        }
        var data = await resp.json();
        if (!data || !data.ok) {
            return null;
        }
        return {
            scope: String(data.scope || s),
            rel_path: String(data.rel_path || rp),
            file_name: String(data.file_name || rp),
            is_shared: Boolean(data.is_shared),
            content: String(data.content || "")
        };
    }

    async function _runPreflattenProjectUiSources(catalogItems, externalToken, reasonText) {
        if (!_isBrowseModeEnabled()) {
            return;
        }
        var items = Array.isArray(catalogItems) ? catalogItems : (uiSources.uiSourceState ? uiSources.uiSourceState.catalogItems : []);
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
            projectItems.push({ scope: scope, rel_path: relPath, file_name: fileName });
        }

        if (uiSources && uiSources.setUiSourceOnlyShowFlattened) {
            uiSources.setUiSourceOnlyShowFlattened(true);
        }
        if (uiSources && uiSources.clearUiSourceFlattenedStatus) {
            uiSources.clearUiSourceFlattenedStatus();
        }
        if (uiSources && uiSources.renderUiSourceList) {
            uiSources.renderUiSourceList();
        }

        if (!projectItems.length) {
            if (uiSources && uiSources.setUiSourceHintText) {
                uiSources.setUiSourceHintText("项目 UI源码 为空：无需预生成扁平化。");
            }
            return;
        }

        var reason = String(reasonText || "自动预生成").trim();
        if (uiSources && uiSources.setUiSourceHintText) {
            uiSources.setUiSourceHintText(reason + "：准备扁平化 " + String(projectItems.length) + " 个项目页面…");
        }

        for (var j = 0; j < projectItems.length; j++) {
            if (externalToken && typeof externalToken.isActive === "function" && !externalToken.isActive()) {
                return;
            }
            var item = projectItems[j];
            if (uiSources && uiSources.setUiSourceHintText) {
                uiSources.setUiSourceHintText(
                    reason + "：扁平化中 [" + String(j + 1) + "/" + String(projectItems.length) + "] " + String(item.file_name || item.rel_path || "")
                );
            }

            var contentResult = await _fetchUiSourceContent(item.scope, item.rel_path);
            if (!contentResult || !String(contentResult.content || "").trim()) {
                if (uiSources && uiSources.setUiSourceFlattenedStatus) {
                    uiSources.setUiSourceFlattenedStatus(item.scope, item.rel_path, false, { silent: true });
                }
                continue;
            }
            var htmlText = String(contentResult.content || "");
            var sourceHash = _computeSourceHashFromHtmlText(htmlText);
            var cacheKey = _buildUiSourceCacheKey(item.scope, item.rel_path);
            var cached = _getFlattenCacheEntryByKey(cacheKey);
            if (cached && cached.sourceHash === sourceHash && cached.flattenedHtmlText && !cached.errorText) {
                if (uiSources && uiSources.setUiSourceFlattenedStatus) {
                    uiSources.setUiSourceFlattenedStatus(item.scope, item.rel_path, true, { silent: true });
                }
                continue;
            }

            var result = await flatteningController.handleGenerateFlattened(htmlText, sourceHash, externalToken || null, { silent: true });
            if (externalToken && typeof externalToken.isActive === "function" && !externalToken.isActive()) {
                return;
            }
            if (!result) {
                if (uiSources && uiSources.setUiSourceFlattenedStatus) {
                    uiSources.setUiSourceFlattenedStatus(item.scope, item.rel_path, false, { silent: true });
                }
                continue;
            }
            _setFlattenCacheEntry(cacheKey, {
                scope: String(item.scope || "project"),
                rel_path: String(item.rel_path || ""),
                sourceHash: String(result.sourceHash || sourceHash || ""),
                flattenedHtmlText: String(result.flattenedHtmlText || ""),
                errorText: String(result.errorText || ""),
                updatedAtMs: Date.now()
            }, { silent: true });
        }

        if (uiSources && uiSources.renderUiSourceList) {
            uiSources.renderUiSourceList();
        }
        if (uiSources && uiSources.setUiSourceHintText) {
            uiSources.setUiSourceHintText(reason + "：扁平化完成（项目：" + String(projectItems.length) + " 个）。");
        }
    }

    async function schedulePreflattenProjectUiSources(catalogItems, reasonText) {
        return runQueue.enqueue({
            coalesceKey: "preflatten_all",
            label: "预生成全部扁平化",
            action: async function (ctx) {
                await _runPreflattenProjectUiSources(catalogItems, ctx ? ctx.token : null, reasonText);
            }
        });
    }

    var flattenGroupTreeController = createFlattenGroupTreeController({
        preview: preview,
        getHtmlText: function () {
            return inputHtmlTextAreaElement ? String(inputHtmlTextAreaElement.value || "") : "";
        },
        waitForNextFrame: waitForNextFrame,
        getCanvasSizeByKey: getCanvasSizeByKey,
        extractDisplayElementsData: extractDisplayElementsData,
        buildFlattenedLayerData: buildFlattenedLayerData,
    });

    var flatteningController = createFlatteningController({
        CANVAS_SIZE_CATALOG: CANVAS_SIZE_CATALOG,
        preview: preview,
        uiSources: uiSources,
        getCanvasSizeByKey: getCanvasSizeByKey,
        waitForNextFrame: waitForNextFrame,

        extractDisplayElementsData: extractDisplayElementsData,
        buildFlattenedLayerData: buildFlattenedLayerData,
        generateFlattenedDivs: generateFlattenedDivs,
        buildFlattenedInjectionHtml: buildFlattenedInjectionHtml,
        injectContentIntoBody: injectContentIntoBody,
        replaceBodyInnerHtml: replaceBodyInnerHtml,
        normalizeSizeKeyForCssClass: normalizeSizeKeyForCssClass,
        rewriteResourcePathsForFlattenedOutput: rewriteResourcePathsForFlattenedOutput,
        rewritePageSwitchLinksForFlattenedOutput: rewritePageSwitchLinksForFlattenedOutput,
        buildUiLayoutBundleFromFlattenedLayers: buildUiLayoutBundleFromFlattenedLayers,

        inputHtmlTextAreaElement: inputHtmlTextAreaElement,
        flattenedOutputTextAreaElement: flattenedOutputTextAreaElement,
        uiControlGroupJsonOutputTextAreaElement: uiControlGroupJsonOutputTextAreaElement,
        importLayoutNameInputElement: dom.importLayoutNameInputElement,
        outputToFlattenedDirCheckboxElement: dom.outputToFlattenedDirCheckboxElement,
        flattenDebugShowAllCheckboxElement: dom.flattenDebugShowAllCheckboxElement,
        flattenDebugShowGroupsCheckboxElement: dom.flattenDebugShowGroupsCheckboxElement,

        setLastGeneratedFlattenedHtmlText: function (t) { lastGeneratedFlattenedHtmlText = String(t || ""); },
        setLastFlattenedSourceHash: function (t) { lastFlattenedSourceHash = String(t || ""); },
        setLastFlattenedErrorText: function (t) { lastFlattenedErrorText = String(t || ""); },
        getLastRenderedSourceHtmlText: function () { return preview.getLastRenderedSourceHtmlText() || ""; },
        getLastGeneratedFlattenedHtmlText: function () { return lastGeneratedFlattenedHtmlText; },
        getLastFlattenedSourceHash: function () { return lastFlattenedSourceHash; },

        setLastGeneratedUiControlGroupJsonText: function (t) { lastGeneratedUiControlGroupJsonText = String(t || ""); },
        setLastUiControlGroupSourceHtmlText: function (t) { lastUiControlGroupSourceHtmlText = String(t || ""); },

        setFlattenGroupUiKeyPrefix: function (prefix) { flattenGroupTreeController.setUiKeyPrefix(prefix); },

        // Diagnostics hooks
        createDiagnosticsCollector: function () { return createDiagnosticsCollector(); },
        setLastFlattenDowngradeIssues: function (issues) {
            lastFlattenDowngradeIssues = Array.isArray(issues) ? issues : [];
            _renderDiagnosticsPanel("校验结果");
        },
        setLastExportDowngradeIssues: function (issues) {
            lastExportDowngradeIssues = Array.isArray(issues) ? issues : [];
            _renderDiagnosticsPanel("校验结果");
        }
    });

    async function ensureBundleStateUpToDate(externalToken) {
        var currentHash = _getCurrentSourceHash();
        if (bundleState && bundleState.bundleObj && bundleState.jsonText && bundleState.sourceHash === currentHash) {
            return;
        }
        await _exportUiControlGroupJsonNow(undefined, externalToken || null);
    }

    var appApiController = createAppApiController({
        appContextTextElement: dom.appContextTextElement,
        importToAppButtonInlineElement: dom.importToAppButtonInlineElement,
        exportGilButtonInlineElement: dom.exportGilButtonInlineElement,
        exportGiaButtonInlineElement: dom.exportGiaButtonInlineElement,
        exportGiaButtonInlineTopElement: dom.exportGiaButtonInlineTopElement,
        importLayoutNameInputElement: dom.importLayoutNameInputElement,
        importStatusTextElement: dom.importStatusTextElement,
        exportGilStatusTextElement: dom.exportGilStatusTextElement,
        exportGilDownloadLinkElement: dom.exportGilDownloadLinkElement,
        exportGiaStatusTextElement: dom.exportGiaStatusTextElement,
        exportGiaDownloadLinkElement: dom.exportGiaDownloadLinkElement,
        exportGilVerifyCheckboxElement: dom.exportGilVerifyCheckboxElement,
        exportGilTargetLayoutGuidInputElement: dom.exportGilTargetLayoutGuidInputElement,
        uiSources: uiSources,
        preview: preview,
        getCanvasSizeByKey: getCanvasSizeByKey,
        getCurrentEditorHtmlText: function () {
            return inputHtmlTextAreaElement ? String(inputHtmlTextAreaElement.value || "") : "";
        },
        getCurrentSourceHash: function () {
            return _getCurrentSourceHash();
        },
        getSelectedBaseGilFile: function () { return uiState.selectedBaseGilFile; },
        getBundleState: function () { return bundleState; },
        ensureBundleState: ensureBundleStateUpToDate
    });

    var previewVariantSwitcher = createPreviewVariantSwitcher({
        PREVIEW_VARIANT_SOURCE: PREVIEW_VARIANT_SOURCE,
        PREVIEW_VARIANT_FLATTENED: PREVIEW_VARIANT_FLATTENED,
        preview: preview,
        getSourceHtmlText: function () {
            return inputHtmlTextAreaElement ? (inputHtmlTextAreaElement.value || "") : "";
        },
        getSourceHash: function () {
            return _getCurrentSourceHash();
        },
        getLastRenderedSourceHtmlText: function () {
            return preview.getLastRenderedSourceHtmlText();
        },
        getLastGeneratedFlattenedHtmlText: function () {
            var cached = _getFlattenCacheEntryForCurrentSelection();
            if (cached && cached.flattenedHtmlText) {
                return cached.flattenedHtmlText;
            }
            return lastGeneratedFlattenedHtmlText;
        },
        getLastFlattenedSourceHtmlText: function () {
            return "";
        },
        getLastFlattenedSourceHash: function () {
            var cached = _getFlattenCacheEntryForCurrentSelection();
            if (cached && cached.sourceHash) {
                return cached.sourceHash;
            }
            return lastFlattenedSourceHash;
        },
        getLastFlattenedErrorText: function () {
            var cached = _getFlattenCacheEntryForCurrentSelection();
            if (cached && cached.errorText) {
                return cached.errorText;
            }
            return lastFlattenedErrorText;
        },
        onFlattenCacheMiss: handleFlattenCacheMiss,
        setFlattenedErrorText: function (t) {
            lastFlattenedErrorText = String(t || "");
        },
        setLastGeneratedFlattenedHtmlText: function (t) {
            lastGeneratedFlattenedHtmlText = String(t || "");
        },
        setLastFlattenedSourceHash: function (t) {
            lastFlattenedSourceHash = String(t || "");
        },
        handleGenerateFlattened: async function (htmlTextOverride) {
            // Must go through global runQueue to avoid concurrent writes.
            await handleGenerateFlattened(htmlTextOverride);
        },
        onFlattenedRendered: function () {
            flattenGroupTreeController.indexFlattenedPreviewElements();
        },
        reportFlattenedError: function (errText) {
            var err = String(errText || "");
            if (!err) {
                return;
            }
            _appendValidationIssue(createIssue({
                code: "FLATTEN.FAILED",
                severity: "error",
                message: "扁平化失败：" + err,
                fix: { kind: "manual", suggestion: "根据错误提示修复 HTML（通常是缺少 <body> 或存在非法脚本/导航）。" }
            }));
            if (inspectorImportantTextAreaElement) {
                inspectorImportantTextAreaElement.value = err;
            }
        }
    });

    // UI source browser needs previewVariantSwitcher (for stable visible preview refresh without flicker).
    uiSources.initUiSourceBrowser({
        setLeftTab: setLeftTab,
        onFileStemChanged: function (stem) {
            if (!uiState.importLayoutNameUserEdited && dom.importLayoutNameInputElement && stem) {
                uiState.importLayoutNameProgrammaticUpdate = true;
                dom.importLayoutNameInputElement.value = String(stem || "");
                uiState.importLayoutNameProgrammaticUpdate = false;
            }
        },
        onCatalogRefreshed: async function (items) {
            if (!_isBrowseModeEnabled()) {
                return false;
            }
            var reason = _uiCatalogPrefetchFirstRun ? "打开后自动预生成" : "刷新后自动预生成";
            _uiCatalogPrefetchFirstRun = false;
            await schedulePreflattenProjectUiSources(items, reason);
            return true;
        },
        onSelectionChanging: function (selection) {
            // Immediately invalidate any in-flight/pending heavy ops when user switches files.
            var scope = selection ? String(selection.scope || "") : "";
            var relPath = selection ? String(selection.rel_path || "") : "";
            if (runQueue && typeof runQueue.setSessionKey === "function") {
                var k = "ui_source:" + (scope || "project") + ":" + relPath + ":loading:" + String(Date.now());
                runQueue.setSessionKey(k);
            }
            _resetDerivedOutputsForSourceChange();
            _resetDiagnosticsToUnvalidated("已切换文件：将加载 " + (relPath ? relPath : "（未知）") + "。");
        },
        onFileOpened: async function (_selection) {
            // 打开文件时，先把可视预览切到“源码模式”展示新文件，避免显示旧的扁平结果造成误解。
            // 真正的 computedStyle 采样/扁平化/导出都在隐藏 compute iframe 中执行，不会再导致可视预览来回闪。
            _syncRunQueueSessionKeyToCurrentSource();
            _resetDerivedOutputsForSourceChange();
            _resetDiagnosticsToUnvalidated("已打开文件：" + String((_selection && (_selection.file_name || _selection.rel_path)) || "").trim());
            _hydrateFlattenCacheForSelection(_selection);
            var preferredVariant = previewVariantSwitcher.getCurrentPreviewVariant();
            await previewVariantSwitcher.requestPreviewVariantSwitch(preferredVariant);
            if (document && document.body && document.body.dataset && document.body.dataset.workbenchMode === "browse") {
                _scheduleImmediateFlattenIfMissing(_selection);
                await scheduleBrowsePipeline(_selection);
            }
        },
    });

    async function refreshAppContextStatus() {
        return appApiController.refreshAppContextStatus();
    }

    function setValidationBadge(issueList) {
        if (!dom.validationStatusBadgeElement) {
            return;
        }
        var summary = summarizeIssues(issueList);
        var hasErrors = !!(summary && summary.error > 0);
        if (hasErrors) {
            dom.validationStatusBadgeElement.textContent = "未通过（" + String(summary.error) + "）";
            dom.validationStatusBadgeElement.classList.remove("ok");
            dom.validationStatusBadgeElement.classList.add("bad");
        } else {
            if (summary && summary.warning > 0) {
                dom.validationStatusBadgeElement.textContent = "通过（警告 " + String(summary.warning) + "）";
            } else {
                dom.validationStatusBadgeElement.textContent = "通过";
            }
            dom.validationStatusBadgeElement.classList.remove("bad");
            dom.validationStatusBadgeElement.classList.add("ok");
        }
    }

    function setValidationBadgeToUnvalidated() {
        if (!dom.validationStatusBadgeElement) {
            return;
        }
        dom.validationStatusBadgeElement.textContent = "未校验";
        dom.validationStatusBadgeElement.classList.remove("ok");
        dom.validationStatusBadgeElement.classList.add("bad");
    }

    async function handleValidateAndRender() {
        _syncRunQueueSessionKeyToCurrentSource();
        return runQueue.enqueue({
            coalesceKey: "validate",
            label: "校验并渲染",
            action: async function (ctx) {
                if (!inputHtmlTextAreaElement) {
                    return;
                }
                var htmlText = inputHtmlTextAreaElement.value || "";
                var issues = validateHtmlSource(htmlText);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                // 校验使用 compute iframe：避免为了 computedStyle 而打断用户当前预览视图（源码/扁平来回闪）。
                var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(htmlText);
                if (!isComputeReady) {
                    return;
                }
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                var computedIssues = validatePreviewComputedRules(preview.getComputePreviewDocument());
                issues = concatIssues(issues, computedIssues);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                var fontIssues = await validateTextFontSizeUniformAcrossCanvasSizes(preview, CANVAS_SIZE_CATALOG, waitForNextFrame);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                issues = concatIssues(issues, fontIssues);
                var validatedHash = _computeSourceHashFromHtmlText(htmlText);
                _setValidationIssues(issues, "校验结果", validatedHash);

                // 体验：校验通过后，提前把“扁平化”算出来并缓存。
                // 这样“源码/扁平”切换尽量变成纯显示切换，而不是每次切换都触发重计算。
                var summary = summarizeIssues(issues);
                if (summary && summary.error <= 0) {
                    if (ctx && ctx.token && !ctx.token.isActive()) {
                        return;
                    }
                    var result = await flatteningController.handleGenerateFlattened(htmlText, validatedHash, ctx ? ctx.token : null);
                    if (ctx && ctx.token && !ctx.token.isActive()) {
                        return;
                    }
                    await flattenGroupTreeController.refresh();
                    _renderDiagnosticsPanel("校验结果");
                }

                // “校验并渲染”必须更新可视预览 iframe（渲染=展示）。
                // 使用 previewVariantSwitcher（纯显示）来避免与 compute iframe 打架。
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                await previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_SOURCE);
            }
        });
    }

    async function handleAutoFixAndRender() {
        _syncRunQueueSessionKeyToCurrentSource();
        return runQueue.enqueue({
            coalesceKey: "validate",
            label: "自动修正并校验",
            action: async function (ctx) {
                if (!inputHtmlTextAreaElement) {
                    return;
                }
                var originalHtmlText = inputHtmlTextAreaElement.value || "";
                var fixResult = autoFixHtmlSource(originalHtmlText);
                var fixedHtmlText = fixResult && fixResult.fixed_html_text !== undefined ? String(fixResult.fixed_html_text || "") : originalHtmlText;
                var appliedFixes = fixResult && fixResult.applied_fixes ? fixResult.applied_fixes : [];
                if (fixedHtmlText !== originalHtmlText) {
                    inputHtmlTextAreaElement.value = fixedHtmlText;
                    _resetDiagnosticsToUnvalidated("已自动修正源码，将重新校验。");
                }
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                // Inline validate (do NOT call handleValidateAndRender here, to avoid nested queue usage).
                var htmlText = inputHtmlTextAreaElement.value || "";
                var issues = validateHtmlSource(htmlText);
                var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(htmlText);
                if (!isComputeReady) {
                    return;
                }
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                var computedIssues = validatePreviewComputedRules(preview.getComputePreviewDocument());
                issues = concatIssues(issues, computedIssues);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                var fontIssues = await validateTextFontSizeUniformAcrossCanvasSizes(preview, CANVAS_SIZE_CATALOG, waitForNextFrame);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                issues = concatIssues(issues, fontIssues);
                var validatedHash2 = _computeSourceHashFromHtmlText(htmlText);
                _setValidationIssues(issues, "校验结果", validatedHash2);
                if (appliedFixes && appliedFixes.length > 0) {
                    _setValidationIssues(concatIssues(appliedFixes, lastValidationIssues), "校验结果（含自动修正）", validatedHash2);
                }

                // Pre-flatten on pass (same behavior as validate).
                var summary = summarizeIssues(issues);
                if (summary && summary.error <= 0) {
                    if (ctx && ctx.token && !ctx.token.isActive()) {
                        return;
                    }
                    var result = await flatteningController.handleGenerateFlattened(htmlText, validatedHash2, ctx ? ctx.token : null);
                    if (ctx && ctx.token && !ctx.token.isActive()) {
                        return;
                    }
                    await flattenGroupTreeController.refresh();
                    _renderDiagnosticsPanel("校验结果");
                }

                // “自动修正并校验”同样需要更新可视预览（展示修正后的源码）。
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                await previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_SOURCE);
            }
        });
    }

    function handleCopyAiFixPack() {
        var htmlText = inputHtmlTextAreaElement ? String(inputHtmlTextAreaElement.value || "") : "";
        var pack = buildAiFixPack({
            title: "UI HTML Workbench - AI 修复包",
            html_text: htmlText,
            issues: lastValidationIssues
        });
        copyTextToClipboard(pack);
        setWorkflowStatusText("已复制 AI 修复包（含 Diagnostics JSON + HTML）。");
    }

    function handleEditorSourceChanged(reasonText) {
        _syncRunQueueSessionKeyToCurrentSource();
        _resetDiagnosticsToUnvalidated(String(reasonText || "").trim() || "源码已修改。");
        if (uiSources && uiSources.uiSourceState) {
            _invalidateFlattenCacheForSelection(uiSources.uiSourceState.currentSelection);
        }
    }

    function _copyDiagnosticsIssuesByBucket(bucketKey) {
        var diag = _getDiagnosticsState();
        var k = String(bucketKey || "").trim().toLowerCase();
        var list = [];
        var title = "Diagnostics";
        if (k === "error" || k === "errors") {
            list = diag.buckets.errors;
            title = "仅错误（Errors）";
        } else if (k === "warning" || k === "warnings") {
            list = diag.buckets.warnings;
            title = "仅警告（Warnings）";
        } else if (k === "info" || k === "infos") {
            list = diag.buckets.infos;
            title = "仅信息（Info）";
        } else {
            list = diag.all;
            title = "全部（All）";
        }
        var text = formatIssuesAsText(list, { title: title });
        copyTextToClipboard(text);
        setWorkflowStatusText("已复制：" + title);
    }

    function handleCopyDiagnosticsErrors() {
        _copyDiagnosticsIssuesByBucket("errors");
    }
    function handleCopyDiagnosticsWarnings() {
        _copyDiagnosticsIssuesByBucket("warnings");
    }
    function handleCopyDiagnosticsInfos() {
        _copyDiagnosticsIssuesByBucket("infos");
    }

    async function handleGenerateFlattened(htmlTextOverride) {
        _syncRunQueueSessionKeyToCurrentSource();
        return runQueue.enqueue({
            coalesceKey: "flatten",
            label: "生成扁平化",
            action: async function (ctx) {
                var cacheKey = _getCurrentUiSourceCacheKey();
                var selection = uiSources && uiSources.uiSourceState ? uiSources.uiSourceState.currentSelection : null;
                var sourceHashForFlatten = htmlTextOverride !== undefined
                    ? _computeSourceHashFromHtmlText(String(htmlTextOverride || ""))
                    : _getCurrentSourceHash();
                var result = await flatteningController.handleGenerateFlattened(htmlTextOverride, sourceHashForFlatten, ctx ? ctx.token : null);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                if (result && cacheKey && selection && selection.scope && selection.rel_path) {
                    _setFlattenCacheEntry(cacheKey, {
                        scope: String(selection.scope || "project"),
                        rel_path: String(selection.rel_path || ""),
                        sourceHash: String(result.sourceHash || sourceHashForFlatten || ""),
                        flattenedHtmlText: String(result.flattenedHtmlText || ""),
                        errorText: String(result.errorText || ""),
                        updatedAtMs: Date.now()
                    });
                }
                await flattenGroupTreeController.refresh();
                _renderDiagnosticsPanel("校验结果");

                // 若用户当前正在看“扁平模式”，生成完成后应立刻刷新预览显示最新扁平缓存（纯显示，不走重算）。
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
                if (previewVariantSwitcher.getCurrentPreviewVariant() === PREVIEW_VARIANT_FLATTENED) {
                    await previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_FLATTENED);
                }
                return result;
            }
        });
    }

    function handleFlattenCacheMiss() {
        if (!inputHtmlTextAreaElement) {
            return false;
        }
        var htmlText = String(inputHtmlTextAreaElement.value || "");
        if (!String(htmlText || "").trim()) {
            return false;
        }
        handleGenerateFlattened();
        return true;
    }

    async function _exportUiControlGroupJsonNow(htmlTextOverride, externalToken) {
        var token = externalToken || null;
        var result = await flatteningController.handleExportUiControlGroupJson(htmlTextOverride, token);
        if (!result) {
            return;
        }
        if (token && typeof token.isActive === "function" && !token.isActive()) {
            return;
        }

        // 以“结构化 bundle”为单一真源；textarea 仅用于展示/复制。
        bundleState.jsonText = String(result.jsonText || "");
        bundleState.sourceHash = _computeSourceHashFromHtmlText(String(result.sourceHtmlText || ""));
        bundleState.updatedAtMs = Date.now();

        var bundleObj = result.bundleObj || null;
        if (!bundleObj && bundleState.jsonText) {
            bundleObj = JSON.parse(bundleState.jsonText);
        }
        bundleState.bundleObj = bundleObj;
        bundleState.templateCount = Number(result.templateCount || 0);
        bundleState.widgetCount = Number(result.widgetCount || 0);

        // Export string warnings (ui_export) should not be merged into "校验问题" list;
        // store separately and render as a dedicated section.
        lastExportStringWarningIssues = _buildExportStringWarningIssuesFromBundle(bundleState.bundleObj);
        _renderDiagnosticsPanel("校验结果");
        return result;
    }

    async function handleExportUiControlGroupJson(htmlTextOverride) {
        _syncRunQueueSessionKeyToCurrentSource();
        return runQueue.enqueue({
            coalesceKey: "export_bundle",
            label: "导出 UI布局 Bundle",
            action: async function (ctx) {
                return await _exportUiControlGroupJsonNow(htmlTextOverride, ctx ? ctx.token : null);
            }
        });
    }

    function handleOpenFlattenedPreview() {
        return previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_FLATTENED);
    }

    function handleClearInput() {
        if (inputHtmlTextAreaElement) {
            inputHtmlTextAreaElement.value = "";
        }
        if (validationErrorsTextAreaElement) {
            validationErrorsTextAreaElement.value = "";
        }
        if (flattenedOutputTextAreaElement) {
            flattenedOutputTextAreaElement.value = "";
        }
        if (uiControlGroupJsonOutputTextAreaElement) {
            uiControlGroupJsonOutputTextAreaElement.value = "";
        }
        if (inspectorImportantTextAreaElement) {
            inspectorImportantTextAreaElement.value = "";
        }
        if (inspectorDetailsTextAreaElement) {
            inspectorDetailsTextAreaElement.value = "";
        }
        bundleState.bundleObj = null;
        bundleState.jsonText = "";
        bundleState.sourceHash = "";
        bundleState.templateCount = 0;
        bundleState.widgetCount = 0;
        bundleState.updatedAtMs = 0;
        _resetDiagnosticsToUnvalidated("未输入源码。");
        if (uiSources && uiSources.uiSourceState) {
            _invalidateFlattenCacheForSelection(uiSources.uiSourceState.currentSelection);
        }
        setWorkflowStatusText("就绪");
    }

    function handleHtmlFileInputChange() {
        if (!dom.htmlFileInputElement || !inputHtmlTextAreaElement) {
            return;
        }
        var selectedFile = dom.htmlFileInputElement.files && dom.htmlFileInputElement.files.length > 0 ? dom.htmlFileInputElement.files[0] : null;
        if (!selectedFile) {
            return;
        }

        if (selectedFile.name) {
            var nameText = String(selectedFile.name || "");
            var withoutExt = nameText.replace(/\.[^/.]+$/, "");
            uiSources.uiSourceState.lastSelectedHtmlFileStem = withoutExt;
            if (dom.importLayoutNameInputElement && withoutExt && !uiState.importLayoutNameUserEdited) {
                uiState.importLayoutNameProgrammaticUpdate = true;
                dom.importLayoutNameInputElement.value = withoutExt;
                uiState.importLayoutNameProgrammaticUpdate = false;
            }
        }

        var fileReader = new FileReader();
        fileReader.onload = function () {
            inputHtmlTextAreaElement.value = String(fileReader.result || "");
            _resetDerivedOutputsForSourceChange();
            handleEditorSourceChanged("已从文件读取源码。");
        };
        fileReader.readAsText(selectedFile, "utf-8");
    }

    async function handleImportIntoApp() {
        _syncRunQueueSessionKeyToCurrentSource();
        return runQueue.enqueue({
            coalesceKey: "import_app",
            label: "导入到项目存档",
            action: async function (ctx) {
                await appApiController.importIntoApp(ctx ? ctx.token : null);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
            }
        });
    }

    async function handleExportGilFromWorkbench() {
        _syncRunQueueSessionKeyToCurrentSource();
        // Unlock audio early (user gesture), so we can beep on success even after async work.
        ensureSuccessBeepAudioUnlocked();
        return runQueue.enqueue({
            coalesceKey: "export_gil",
            label: "生成 GIL",
            action: async function (ctx) {
                await appApiController.exportGilFromWorkbench(ctx ? ctx.token : null);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
            }
        });
    }

    async function handleExportGiaFromWorkbench() {
        _syncRunQueueSessionKeyToCurrentSource();
        return runQueue.enqueue({
            coalesceKey: "export_gia",
            label: "生成 GIA",
            action: async function (ctx) {
                await appApiController.exportGiaFromWorkbench(ctx ? ctx.token : null);
                if (ctx && ctx.token && !ctx.token.isActive()) {
                    return;
                }
            }
        });
    }

    function setExportGilStatusText(text) {
        if (!dom.exportGilStatusTextElement) {
            return;
        }
        dom.exportGilStatusTextElement.textContent = String(text || "");
    }

    function setExportGiaStatusText(text) {
        if (!dom.exportGiaStatusTextElement) {
            return;
        }
        dom.exportGiaStatusTextElement.textContent = String(text || "");
    }

    bindWorkbenchDomEvents({
        uiState: uiState,
        preview: preview,
        previewVariantSwitcher: previewVariantSwitcher,
        PREVIEW_VARIANT_SOURCE: PREVIEW_VARIANT_SOURCE,
        PREVIEW_VARIANT_FLATTENED: PREVIEW_VARIANT_FLATTENED,
        groupTreeController: flattenGroupTreeController,

        uiSources: uiSources,
        variables: variables,

        setLeftTab: setLeftTab,
        getLeftTabKey: getLeftTabKey,
        setInspectorTab: setInspectorTab,

        refreshAppContextStatus: refreshAppContextStatus,
        handleValidateAndRender: handleValidateAndRender,
        handleAutoFixAndRender: handleAutoFixAndRender,
        handleGenerateFlattened: handleGenerateFlattened,
        handleExportUiControlGroupJson: handleExportUiControlGroupJson,
        handleCopyAiFixPack: handleCopyAiFixPack,
        handleCopyDiagnosticsErrors: handleCopyDiagnosticsErrors,
        handleCopyDiagnosticsWarnings: handleCopyDiagnosticsWarnings,
        handleCopyDiagnosticsInfos: handleCopyDiagnosticsInfos,
        handleImportIntoApp: handleImportIntoApp,
        handleExportGilFromWorkbench: handleExportGilFromWorkbench,
        handleExportGiaFromWorkbench: handleExportGiaFromWorkbench,
        handleOpenFlattenedPreview: handleOpenFlattenedPreview,
        handleClearInput: handleClearInput,
        handleHtmlFileInputChange: handleHtmlFileInputChange,
        handleEditorSourceChanged: handleEditorSourceChanged,

        copyTextToClipboard: copyTextToClipboard,
        setExportGilStatusText: setExportGilStatusText,
        setExportGiaStatusText: setExportGiaStatusText,
    });

    // mode:
    // - mode=browse: 左侧文件列表为主，选中文件自动生成扁平化并默认预览扁平化结果
    // - mode=editor: 保持旧的“粘贴/按钮驱动”流程
    var forcedMode = String(_getQueryParam("mode") || "").trim();
    _applyWorkbenchMode(forcedMode || "browse");

    setInspectorTab("info");
    setLeftTab(document && document.body && document.body.dataset && document.body.dataset.workbenchMode === "browse" ? "ui_sources" : "editor");
    uiSources.setUiSourceCurrentFileText("未选择");
    uiSources.setUiSourceHintText("提示：切到「UI源码」可浏览项目+共享目录；切到「变量」可一键插入占位符。");
    variables.setVariableCatalogStatusText("未加载");
    _syncRunQueueSessionKeyToCurrentSource();
    _resetDiagnosticsToUnvalidated("未输入源码。");
    setWorkflowStatusText("就绪");
    if (autoImportToAppCheckboxElement) {
        autoImportToAppCheckboxElement.checked = false;
    }
    preview.initializePreviewUi();
    preview.setSelectionChangedCallback(function (payload) {
        flattenGroupTreeController.handlePreviewSelectionChanged(payload);
    });

    refreshAppContextStatus();
    if (document && document.body && document.body.dataset && document.body.dataset.workbenchMode === "browse") {
        uiSources.refreshUiSourceCatalog();
        // browse 默认不强制切到“扁平模式”：
        // - 避免用户一打开页面就处于扁平视图（更像“我还没选文件就被转换了”）
        // - 也避免后续校验/扁平化为了拿 computedStyle 而导致可视 iframe 来回闪
        preview.renderHtmlIntoPreview(preview.buildEmptyInputPlaceholderHtml(), PREVIEW_VARIANT_SOURCE);
    }

    runAutoTestIfRequested({
        inputHtmlTextAreaElement: inputHtmlTextAreaElement,
        preview: preview,
        handleValidateAndRender: handleValidateAndRender,
        handleGenerateFlattened: handleGenerateFlattened,
        switchToFlattened: function () {
            return previewVariantSwitcher.switchPreviewVariantTo(PREVIEW_VARIANT_FLATTENED);
        },
        waitForNextFrame: waitForNextFrame
    });
}

