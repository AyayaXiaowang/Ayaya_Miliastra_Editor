import { hashTextFNV1a32Hex } from "../utils.js";
import { canFallbackToVisiblePreviewDocument, extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback } from "./compute_fallback.js";

var EXPORT_TEMPLATE_ID_PREFIX = "template_html_import_";
var EXPORT_LAYOUT_ID_PREFIX = "layout_html_import_";
var EXPORT_ID_SEED_PREFIX = "ui_bundle_export_v1";
var EXPORT_ID_SEP = "|";

function _buildDeterministicExportIdHash(parts) {
    var list = Array.isArray(parts) ? parts : [];
    var normalized = [];
    for (var i = 0; i < list.length; i++) {
        var s = String(list[i] !== undefined ? list[i] : "").trim();
        normalized.push(s);
    }
    var seed = normalized.join(EXPORT_ID_SEP);
    return hashTextFNV1a32Hex(seed);
}

export function createFlatteningController(opts) {
    var o = opts || {};

    var CANVAS_SIZE_CATALOG = o.CANVAS_SIZE_CATALOG;
    var preview = o.preview;
    var uiSources = o.uiSources;
    var getCanvasSizeByKey = o.getCanvasSizeByKey;
    var waitForNextFrame = o.waitForNextFrame;

    var extractDisplayElementsData = o.extractDisplayElementsData;
    var buildFlattenedLayerData = o.buildFlattenedLayerData;
    var generateFlattenedDivs = o.generateFlattenedDivs;
    var buildFlattenedInjectionHtml = o.buildFlattenedInjectionHtml;
    var injectContentIntoBody = o.injectContentIntoBody;
    var replaceBodyInnerHtml = o.replaceBodyInnerHtml;
    var normalizeSizeKeyForCssClass = o.normalizeSizeKeyForCssClass;
    var rewriteResourcePathsForFlattenedOutput = o.rewriteResourcePathsForFlattenedOutput;
    var rewritePageSwitchLinksForFlattenedOutput = o.rewritePageSwitchLinksForFlattenedOutput;

    var buildUiLayoutBundleFromFlattenedLayers = o.buildUiLayoutBundleFromFlattenedLayers;

    var inputHtmlTextAreaElement = o.inputHtmlTextAreaElement;
    var flattenedOutputTextAreaElement = o.flattenedOutputTextAreaElement;
    var uiControlGroupJsonOutputTextAreaElement = o.uiControlGroupJsonOutputTextAreaElement;
    var importLayoutNameInputElement = o.importLayoutNameInputElement;
    var outputToFlattenedDirCheckboxElement = o.outputToFlattenedDirCheckboxElement;
    var flattenDebugShowAllCheckboxElement = o.flattenDebugShowAllCheckboxElement;
    var flattenDebugShowGroupsCheckboxElement = o.flattenDebugShowGroupsCheckboxElement;

    var setLastGeneratedFlattenedHtmlText = o.setLastGeneratedFlattenedHtmlText;
    var setLastFlattenedSourceHash = o.setLastFlattenedSourceHash;
    var setLastFlattenedErrorText = o.setLastFlattenedErrorText;
    var getLastRenderedSourceHtmlText = o.getLastRenderedSourceHtmlText;
    var getLastGeneratedFlattenedHtmlText = o.getLastGeneratedFlattenedHtmlText;
    var getLastFlattenedSourceHash = o.getLastFlattenedSourceHash;

    var setLastGeneratedUiControlGroupJsonText = o.setLastGeneratedUiControlGroupJsonText;
    var setLastUiControlGroupSourceHtmlText = o.setLastUiControlGroupSourceHtmlText;

    var setFlattenGroupUiKeyPrefix = o.setFlattenGroupUiKeyPrefix;

    // Optional diagnostics callbacks (latest run issues)
    var setLastFlattenDowngradeIssues = o.setLastFlattenDowngradeIssues;
    var setLastExportDowngradeIssues = o.setLastExportDowngradeIssues;

    // NOTE:
    // Workbench 的“重操作”（校验/扁平/导出/导入/导出GIL/GIA）统一走 workbench_main/run_queue.js，
    // 并以 runQueue token 作为唯一的取消/并发控制模型（latest-wins + coalesce + session key）。
    //
    // 因此 flatteningController 不再维护第二套内部 token；这里只接受外部 token，并在关键 await 点检查是否仍 active。
    function _isExternalTokenActive(externalToken) {
        var t = externalToken || null;
        if (!t) return true;
        if (typeof t.isActive !== "function") return true;
        return !!t.isActive();
    }

    function parsePxNumber(valueText) {
        var trimmed = String(valueText || "").trim();
        if (!trimmed) {
            return null;
        }
        var match = /^([+-]?\d+(\.\d+)?)(px)?$/i.exec(trimmed);
        if (!match) {
            return null;
        }
        var numberValue = Number(match[1]);
        if (!isFinite(numberValue)) {
            return null;
        }
        return numberValue;
    }

    function _extractVariableDefaultsFromHtmlText(htmlText) {
        // 从“源码文本”提取 data-ui-variable-defaults（避免 compute iframe / autofix 序列化导致属性丢失的极端情况）
        //
        // 约定：任意元素可声明：
        //   data-ui-variable-defaults='{"关卡.foo":1,"lv.level_01_name":"第一关"}'
        //
        // 多个声明会按 DOM 顺序合并，后者覆盖前者同名 key。
        var raw = String(htmlText || "");
        if (!raw.trim()) {
            return {};
        }
        if (typeof DOMParser === "undefined") {
            return {};
        }
        var parser = new DOMParser();
        var doc = parser.parseFromString(raw, "text/html");
        if (!doc || !doc.querySelectorAll) {
            return {};
        }
        var nodes = doc.querySelectorAll("[data-ui-variable-defaults]");
        if (!nodes || nodes.length <= 0) {
            return {};
        }
        var out = {};
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el || !el.getAttribute) {
                continue;
            }
            var text = String(el.getAttribute("data-ui-variable-defaults") || "").trim();
            if (!text) {
                continue;
            }
            var parsed = JSON.parse(text);
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                throw new Error("data-ui-variable-defaults 必须是 JSON object，例如 {\"关卡.hp\":100}。");
            }
            for (var k in parsed) {
                if (!Object.prototype.hasOwnProperty.call(parsed, k)) {
                    continue;
                }
                var key = String(k || "").trim();
                if (!key) {
                    continue;
                }
                out[key] = parsed[k];
            }
        }
        return out;
    }

    async function collectUniformTextFontSizeByElementIndexFromPreview(externalToken) {
        // 需求：只有“4 分辨率字号一致”的文本，才允许通过 `<size=XX>` 在 text_content 里精确表达字号（不限制 XX）。
        var sizeKeyList = [];
        var mapsBySizeKey = {}; // sizeKey -> { elementIndexText -> fontSizeInt }
        for (var i = 0; i < CANVAS_SIZE_CATALOG.length; i++) {
            var it = CANVAS_SIZE_CATALOG[i];
            if (it && it.key) {
                sizeKeyList.push(String(it.key));
            }
        }

        var computeDoc = preview.getComputePreviewDocument ? preview.getComputePreviewDocument() : null;
        if (!computeDoc) {
            return {};
        }

        for (var sizeIndex = 0; sizeIndex < CANVAS_SIZE_CATALOG.length; sizeIndex++) {
            if (!_isExternalTokenActive(externalToken)) {
                return null;
            }
            var canvasSizeOption = CANVAS_SIZE_CATALOG[sizeIndex];
            if (preview.setComputePreviewCanvasSize) {
                preview.setComputePreviewCanvasSize(canvasSizeOption);
            }
            preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
            await waitForNextFrame();
            await waitForNextFrame();
            if (!_isExternalTokenActive(externalToken)) {
                return null;
            }

            var elementsData = extractDisplayElementsData(computeDoc);
            var allowFallbackToPreviewDoc = canFallbackToVisiblePreviewDocument(preview, canvasSizeOption.key);
            var previewDocForFallback = (allowFallbackToPreviewDoc && preview.getPreviewDocument) ? preview.getPreviewDocument() : null;
            var r0 = await extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback({
                extractDisplayElementsData: extractDisplayElementsData,
                computeDoc: computeDoc,
                initialComputeElementsData: elementsData,
                previewDoc: previewDocForFallback,
                allowFallback: allowFallbackToPreviewDoc
            });
            elementsData = r0.elementsData;
            var layerList = buildFlattenedLayerData(elementsData);
            var map = {};

            for (var li = 0; li < (layerList ? layerList.length : 0); li++) {
                var layer = layerList[li];
                if (!layer || String(layer.kind || "") !== "text") {
                    continue;
                }
                var src = layer.source || null;
                if (!src || !Number.isFinite(src.elementIndex)) {
                    continue;
                }
                var fontPx = parsePxNumber(layer.fontSize || "");
                if (fontPx === null || !isFinite(fontPx) || fontPx <= 0) {
                    continue;
                }
                var fontInt = Math.max(1, Math.round(fontPx));
                map[String(Math.trunc(src.elementIndex))] = fontInt;
            }

            mapsBySizeKey[String(canvasSizeOption.key)] = map;
        }

        // 计算 uniform：必须 4 个尺寸都存在且完全一致
        var candidateKeys = new Set();
        for (var sk = 0; sk < sizeKeyList.length; sk++) {
            var sizeKey = sizeKeyList[sk];
            var m = mapsBySizeKey[sizeKey] || {};
            Object.keys(m).forEach(function (k) { candidateKeys.add(String(k)); });
        }

        var uniform = {};
        for (var elementIndexText of candidateKeys) {
            var expected = null;
            for (var sk2 = 0; sk2 < sizeKeyList.length; sk2++) {
                if (!_isExternalTokenActive(externalToken)) {
                    return null;
                }
                var sizeKey2 = sizeKeyList[sk2];
                var m2 = mapsBySizeKey[sizeKey2] || {};
                if (m2[elementIndexText] === undefined) {
                    expected = null;
                    break;
                }
                var n = Number(m2[elementIndexText]);
                if (!isFinite(n) || n <= 0) {
                    expected = null;
                    break;
                }
                if (expected === null) {
                    expected = Math.round(n);
                } else if (Math.round(n) !== expected) {
                    expected = null;
                    break;
                }
            }
            if (expected !== null) {
                uniform[elementIndexText] = expected;
            }
        }

        return uniform;
    }

    async function handleGenerateFlattened(htmlTextOverride, sourceHashOverride, externalToken, options) {
        var callOptions = options || {};
        var shouldUpdateUi = !callOptions.silent;
        if (!inputHtmlTextAreaElement || !flattenedOutputTextAreaElement) {
            return;
        }
        if (shouldUpdateUi) {
            setLastFlattenedErrorText("");
        }
        var originalHtmlText = htmlTextOverride !== undefined ? String(htmlTextOverride || "") : (inputHtmlTextAreaElement.value || "");
        var trimmedOriginalHtmlText = String(originalHtmlText || "").trim();
        if (!trimmedOriginalHtmlText) {
            var placeholderHtmlText = preview.buildEmptyInputPlaceholderHtml();
            if (shouldUpdateUi) {
                setLastGeneratedFlattenedHtmlText(placeholderHtmlText);
                if (setLastFlattenedSourceHash) {
                    setLastFlattenedSourceHash("");
                }
                setLastFlattenedErrorText("");
                flattenedOutputTextAreaElement.value = placeholderHtmlText;
            }
            return {
                flattenedHtmlText: "",
                errorText: "",
                sourceHash: ""
            };
        }

        var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(originalHtmlText);
        if (!isComputeReady) {
            return;
        }
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        var computeDoc = preview.getComputePreviewDocument();
        if (!computeDoc) {
            return;
        }
        var normalizedForHash = preview && preview.normalizeHtmlForSandboxedPreviewSrcDoc
            ? preview.normalizeHtmlForSandboxedPreviewSrcDoc(originalHtmlText)
            : originalHtmlText;
        var sourceHashForCacheKey = sourceHashOverride !== undefined
            ? String(sourceHashOverride || "")
            : hashTextFNV1a32Hex(normalizedForHash);

        // Diagnostics: collect downgrade warnings during flattening.
        var diagnosticsCollector = null;
        if (o && o.createDiagnosticsCollector) {
            diagnosticsCollector = o.createDiagnosticsCollector();
        }

        // 与“导出 UI Bundle”保持一致：用于分组标注/分组列表的页面前缀必须与导出/写回一致。
        var preferredLayoutName = importLayoutNameInputElement ? String(importLayoutNameInputElement.value || "").trim() : "";
        if (!preferredLayoutName) {
            preferredLayoutName = "HTML导入_界面布局";
        }
        var uiKeyPrefix = "";
        if (uiSources.uiSourceState.currentSelection && uiSources.uiSourceState.currentSelection.rel_path) {
            uiKeyPrefix = String(uiSources.uiSourceState.currentSelection.rel_path || "").trim();
        }
        if (!uiKeyPrefix) {
            uiKeyPrefix = String(uiSources.uiSourceState.lastSelectedHtmlFileStem || "").trim();
        }
        if (!uiKeyPrefix) {
            uiKeyPrefix = preferredLayoutName;
        }
        if (setFlattenGroupUiKeyPrefix) {
            setFlattenGroupUiKeyPrefix(uiKeyPrefix);
        }

        var shouldRewriteResources = !!(outputToFlattenedDirCheckboxElement && outputToFlattenedDirCheckboxElement.checked);
        var htmlTextForOutput = shouldRewriteResources ? rewriteResourcePathsForFlattenedOutput(originalHtmlText) : originalHtmlText;
        htmlTextForOutput = rewritePageSwitchLinksForFlattenedOutput(htmlTextForOutput);

        var flatAreaList = [];
        var didEnsurePreviewForFallback = false;
        for (var sizeIndex = 0; sizeIndex < CANVAS_SIZE_CATALOG.length; sizeIndex++) {
            if (!_isExternalTokenActive(externalToken)) {
                return;
            }
            var canvasSizeOption = CANVAS_SIZE_CATALOG[sizeIndex];
            // compute iframe：切换视口尺寸用于 vw/vh/clamp() 计算（不影响可视预览 iframe）
            preview.setComputePreviewCanvasSize(canvasSizeOption);
            preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
            await waitForNextFrame();
            await waitForNextFrame();
            if (!_isExternalTokenActive(externalToken)) {
                return;
            }

            var elementsData = extractDisplayElementsData(computeDoc);
            var allowFallbackToPreviewDoc2 = canFallbackToVisiblePreviewDocument(preview, canvasSizeOption.key);
            var previewDocForFallback2 = (allowFallbackToPreviewDoc2 && preview.getPreviewDocument) ? preview.getPreviewDocument() : null;
            var ensurePreviewForFallback2 = null;
            if (allowFallbackToPreviewDoc2 && shouldUpdateUi && preview.ensurePreviewIsReadyForHtml && !didEnsurePreviewForFallback) {
                ensurePreviewForFallback2 = async function () {
                    didEnsurePreviewForFallback = true;
                    var previewReady = await preview.ensurePreviewIsReadyForHtml(originalHtmlText);
                    if (!previewReady || !preview.getPreviewDocument) {
                        return null;
                    }
                    return preview.getPreviewDocument();
                };
            }
            var r1 = await extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback({
                extractDisplayElementsData: extractDisplayElementsData,
                computeDoc: computeDoc,
                initialComputeElementsData: elementsData,
                previewDoc: previewDocForFallback2,
                allowFallback: allowFallbackToPreviewDoc2,
                ensurePreviewForFallback: ensurePreviewForFallback2,
                forceEnsurePreviewForFallback: true
            });
            elementsData = r1.elementsData;
            var safeKey = normalizeSizeKeyForCssClass(canvasSizeOption.label);
            var divsHtml = generateFlattenedDivs(elementsData, safeKey, {
                debug_show_all_controls: !!(flattenDebugShowAllCheckboxElement && flattenDebugShowAllCheckboxElement.checked),
                debug_show_groups: !!(flattenDebugShowGroupsCheckboxElement && flattenDebugShowGroupsCheckboxElement.checked),
                ui_key_prefix: uiKeyPrefix,
                diagnostics: diagnosticsCollector
            });
            flatAreaList.push({
                safeKey: safeKey,
                sizeKey: canvasSizeOption.key,
                divs: divsHtml,
                width: elementsData.bodySize.width,
                height: elementsData.bodySize.height,
                label: canvasSizeOption.label,
                isDefault: canvasSizeOption.key === preview.getCurrentSelectedCanvasSizeKey()
            });
        }

        var injectedContentHtml = buildFlattenedInjectionHtml(flatAreaList);
        var flattenedHtmlText = replaceBodyInnerHtml
            ? replaceBodyInnerHtml(htmlTextForOutput, injectedContentHtml)
            : injectContentIntoBody(htmlTextForOutput, injectedContentHtml);
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        var flattenedErrorText = "";
        if (!flattenedHtmlText) {
            var err = "扁平化失败：找不到 <body></body>，无法替换 body 内容。请确保输入是完整 HTML 文档。";
            flattenedErrorText = err;
            if (shouldUpdateUi) {
                setLastFlattenedErrorText(err);
                setLastGeneratedFlattenedHtmlText("");
                if (setLastFlattenedSourceHash) {
                    setLastFlattenedSourceHash(sourceHashForCacheKey);
                }
                if (_isExternalTokenActive(externalToken)) {
                    flattenedOutputTextAreaElement.value = err;
                }
            }
        } else {
            flattenedErrorText = "";
            if (shouldUpdateUi) {
                setLastFlattenedErrorText("");
                setLastGeneratedFlattenedHtmlText(flattenedHtmlText);
                if (setLastFlattenedSourceHash) {
                    setLastFlattenedSourceHash(sourceHashForCacheKey);
                }
                if (_isExternalTokenActive(externalToken)) {
                    flattenedOutputTextAreaElement.value = flattenedHtmlText;
                }
            }
        }

        if (shouldUpdateUi && _isExternalTokenActive(externalToken) && setLastFlattenDowngradeIssues && diagnosticsCollector && diagnosticsCollector.issues) {
            setLastFlattenDowngradeIssues(diagnosticsCollector.issues);
        }

        // 还原 compute iframe 尺寸
        var restoreCanvasSizeOption = getCanvasSizeByKey(preview.getCurrentSelectedCanvasSizeKey());
        preview.setComputePreviewCanvasSize(restoreCanvasSizeOption);
        preview.applyCanvasSizeToPreviewDocument(computeDoc, restoreCanvasSizeOption);

        return {
            flattenedHtmlText: flattenedHtmlText || "",
            errorText: flattenedErrorText,
            sourceHash: sourceHashForCacheKey,
            downgradeIssues: diagnosticsCollector && diagnosticsCollector.issues ? diagnosticsCollector.issues : []
        };
    }

    async function handleExportUiControlGroupJson(htmlTextOverride, externalToken) {
        if (!inputHtmlTextAreaElement || !uiControlGroupJsonOutputTextAreaElement) {
            return;
        }
        var originalHtmlText = htmlTextOverride !== undefined ? String(htmlTextOverride || "") : (inputHtmlTextAreaElement.value || "");
        var trimmedOriginalHtmlText = String(originalHtmlText || "").trim();
        if (!trimmedOriginalHtmlText) {
            setLastGeneratedUiControlGroupJsonText("");
            setLastUiControlGroupSourceHtmlText(originalHtmlText);
            uiControlGroupJsonOutputTextAreaElement.value = "";
            return {
                bundleObj: null,
                jsonText: "",
                sourceHtmlText: originalHtmlText,
                templateCount: 0,
                widgetCount: 0
            };
        }

        var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(originalHtmlText);
        if (!isComputeReady) {
            return;
        }
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }

        var selectedCanvasSizeKey = preview.getCurrentSelectedCanvasSizeKey();
        var selectedCanvasSizeOption = getCanvasSizeByKey(selectedCanvasSizeKey);
        var computeDoc = preview.getComputePreviewDocument();
        if (!computeDoc) {
            return;
        }
        // 导出前也要确保 compute iframe 视口与尺寸一致，避免 vw/vh 计算按旧尺寸
        preview.setComputePreviewCanvasSize(selectedCanvasSizeOption);
        preview.applyCanvasSizeToPreviewDocument(computeDoc, selectedCanvasSizeOption);
        await waitForNextFrame();
        await waitForNextFrame();
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }

        var elementsData = extractDisplayElementsData(computeDoc);
        // 某些环境下（尤其是无头/隐藏 iframe），computeDoc 可能提取为空（所有 rect=0，导致 elements 为空）。
        // 为避免导出 bundle 变成“空 widgets”，这里在满足条件时回退到可视预览文档提取（与字号采样保持一致的口径）。
        var allowFallbackToPreviewDoc3 = canFallbackToVisiblePreviewDocument(preview, selectedCanvasSizeKey);
        var previewDocForFallback3 = (allowFallbackToPreviewDoc3 && preview.getPreviewDocument) ? preview.getPreviewDocument() : null;
        var r2 = await extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback({
            extractDisplayElementsData: extractDisplayElementsData,
            computeDoc: computeDoc,
            initialComputeElementsData: elementsData,
            previewDoc: previewDocForFallback3,
            allowFallback: allowFallbackToPreviewDoc3
        });
        elementsData = r2.elementsData;
        var variableDefaults = _extractVariableDefaultsFromHtmlText(originalHtmlText);
        // Diagnostics: collect downgrade warnings during layer build (export path).
        var diagnosticsCollector = null;
        if (o && o.createDiagnosticsCollector) {
            diagnosticsCollector = o.createDiagnosticsCollector();
        }
        var layerList = buildFlattenedLayerData(elementsData, { diagnostics: diagnosticsCollector });

        // 关键：采样 4 个尺寸的文本字号一致性（用于决定是否允许 `<size=XX>` 任意字号）
        var uniformTextFontSizeByElementIndex = await collectUniformTextFontSizeByElementIndexFromPreview(externalToken);
        if (!_isExternalTokenActive(externalToken)) {
            return;
        }
        if (uniformTextFontSizeByElementIndex === null) {
            return;
        }

        var preferredLayoutName = importLayoutNameInputElement ? String(importLayoutNameInputElement.value || "").trim() : "";
        if (!preferredLayoutName) {
            preferredLayoutName = "HTML导入_界面布局";
        }

        // 工程化：为导出的 ui_key 生成一个尽量稳定的“页面前缀”
        var uiKeyPrefix = "";
        if (uiSources.uiSourceState.currentSelection && uiSources.uiSourceState.currentSelection.rel_path) {
            uiKeyPrefix = String(uiSources.uiSourceState.currentSelection.rel_path || "").trim();
        }
        if (!uiKeyPrefix) {
            uiKeyPrefix = String(uiSources.uiSourceState.lastSelectedHtmlFileStem || "").trim();
        }
        if (!uiKeyPrefix) {
            uiKeyPrefix = preferredLayoutName;
        }
        if (setFlattenGroupUiKeyPrefix) {
            setFlattenGroupUiKeyPrefix(uiKeyPrefix);
        }

        // 稳定导出：避免 Date.now() 导致同一源码重复导出产生噪声 diff（layout_id/template_id 漂移）。
        // 该 ID 仅用于 bundle 内部引用与导入/写回的映射 key；最终 `.gil` 的 guid 由写回端决定。
        var normalizedForIdHash = preview && preview.normalizeHtmlForSandboxedPreviewSrcDoc
            ? preview.normalizeHtmlForSandboxedPreviewSrcDoc(originalHtmlText)
            : originalHtmlText;
        var sourceHashForExportIds = hashTextFNV1a32Hex(normalizedForIdHash);
        var templateId = EXPORT_TEMPLATE_ID_PREFIX + _buildDeterministicExportIdHash([
            EXPORT_ID_SEED_PREFIX,
            "template",
            uiKeyPrefix,
            preferredLayoutName,
            selectedCanvasSizeKey,
            sourceHashForExportIds
        ]);
        var layoutId = EXPORT_LAYOUT_ID_PREFIX + _buildDeterministicExportIdHash([
            EXPORT_ID_SEED_PREFIX,
            "layout",
            uiKeyPrefix,
            preferredLayoutName,
            selectedCanvasSizeKey,
            sourceHashForExportIds
        ]);

        var exportResult = buildUiLayoutBundleFromFlattenedLayers(layerList, {
            template_id: templateId,
            template_name: "HTML导入_UI控件组_" + String(selectedCanvasSizeOption.label || selectedCanvasSizeKey),
            layout_id: layoutId,
            layout_name: preferredLayoutName,
            layout_description: "由 ui_html_workbench 导出。尺寸: " + String(selectedCanvasSizeOption.label || selectedCanvasSizeKey),
            ui_key_prefix: uiKeyPrefix,
            group_width: elementsData.bodySize ? elementsData.bodySize.width : selectedCanvasSizeOption.width,
            group_height: elementsData.bodySize ? elementsData.bodySize.height : selectedCanvasSizeOption.height,
            canvas_size_key: selectedCanvasSizeKey,
            canvas_size_label: String(selectedCanvasSizeOption.label || selectedCanvasSizeKey),
            // UI 多状态策略：强制整态打组（与导出中心/预览工具保持一致）
            ui_state_consolidation_mode: "full_state_groups",
            description: "由 ui_html_workbench 导出。",
            uniform_text_font_size_by_element_index: uniformTextFontSizeByElementIndex,
            // 透传：供下游在未显式传入 id 时也能生成确定性 id
            source_hash: sourceHashForExportIds,
            deterministic_timestamps: true
        });

        var bundlePayload = exportResult && exportResult.bundle ? exportResult.bundle : null;
        var warnings = exportResult && exportResult.warnings ? exportResult.warnings : [];
        if (bundlePayload && warnings && warnings.length > 0) {
            bundlePayload._export_warnings = warnings;
        }
        if (bundlePayload && variableDefaults && Object.keys(variableDefaults || {}).length > 0) {
            bundlePayload.variable_defaults = variableDefaults;
            bundlePayload.variable_defaults_total = (Object.keys(variableDefaults || {}).length || 0);
        }

        if (_isExternalTokenActive(externalToken) && setLastExportDowngradeIssues && diagnosticsCollector && diagnosticsCollector.issues) {
            setLastExportDowngradeIssues(diagnosticsCollector.issues);
        }

        var jsonText = JSON.stringify(bundlePayload || {}, null, 2);
        if (_isExternalTokenActive(externalToken)) {
            setLastGeneratedUiControlGroupJsonText(jsonText);
            setLastUiControlGroupSourceHtmlText(originalHtmlText);
            uiControlGroupJsonOutputTextAreaElement.value = jsonText;
        }

        // 还原 compute iframe 尺寸
        var restoreCanvasSizeOption2 = getCanvasSizeByKey(preview.getCurrentSelectedCanvasSizeKey());
        preview.setComputePreviewCanvasSize(restoreCanvasSizeOption2);
        preview.applyCanvasSizeToPreviewDocument(computeDoc, restoreCanvasSizeOption2);

        var templateCount = Array.isArray(bundlePayload && bundlePayload.templates) ? bundlePayload.templates.length : 0;
        var widgetCount = 0;
        if (Array.isArray(bundlePayload && bundlePayload.templates)) {
            for (var wi = 0; wi < bundlePayload.templates.length; wi++) {
                var tpl = bundlePayload.templates[wi] || {};
                if (Array.isArray(tpl.widgets)) {
                    widgetCount += tpl.widgets.length;
                }
            }
        }
        return {
            bundleObj: bundlePayload || null,
            jsonText: jsonText,
            sourceHtmlText: originalHtmlText,
            templateCount: templateCount,
            widgetCount: widgetCount,
            downgradeIssues: diagnosticsCollector && diagnosticsCollector.issues ? diagnosticsCollector.issues : []
        };
    }

    async function ensureBundleJsonUpToDate() {
        if (!inputHtmlTextAreaElement || !uiControlGroupJsonOutputTextAreaElement) {
            return;
        }
        var originalHtmlText = inputHtmlTextAreaElement.value || "";
        var trimmedOriginalHtmlText = String(originalHtmlText || "").trim();
        if (!trimmedOriginalHtmlText) {
            return;
        }
        await handleExportUiControlGroupJson();
    }

    return {
        handleGenerateFlattened: handleGenerateFlattened,
        handleExportUiControlGroupJson: handleExportUiControlGroupJson,
        ensureBundleJsonUpToDate: ensureBundleJsonUpToDate
    };
}

