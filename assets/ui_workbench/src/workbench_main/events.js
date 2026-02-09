import { dom } from "../dom_refs.js";

export function bindWorkbenchDomEvents(opts) {
    var o = opts || {};

    var uiState = o.uiState;
    var preview = o.preview;
    var previewVariantSwitcher = o.previewVariantSwitcher;
    var PREVIEW_VARIANT_SOURCE = o.PREVIEW_VARIANT_SOURCE;
    var PREVIEW_VARIANT_FLATTENED = o.PREVIEW_VARIANT_FLATTENED;
    var groupTreeController = o.groupTreeController;

    var uiSources = o.uiSources;
    var variables = o.variables;

    var setLeftTab = o.setLeftTab;
    var getLeftTabKey = o.getLeftTabKey;
    var setInspectorTab = o.setInspectorTab;

    var refreshAppContextStatus = o.refreshAppContextStatus;
    var handleValidateAndRender = o.handleValidateAndRender;
    var handleAutoFixAndRender = o.handleAutoFixAndRender;
    var handleGenerateFlattened = o.handleGenerateFlattened;
    var handleExportUiControlGroupJson = o.handleExportUiControlGroupJson;
    var handleImportIntoApp = o.handleImportIntoApp;
    var handleExportGilFromWorkbench = o.handleExportGilFromWorkbench;
    var handleExportGiaFromWorkbench = o.handleExportGiaFromWorkbench;
    var handleOpenFlattenedPreview = o.handleOpenFlattenedPreview;
    var handleClearInput = o.handleClearInput;
    var handleHtmlFileInputChange = o.handleHtmlFileInputChange;
    var handleEditorSourceChanged = o.handleEditorSourceChanged;
    var handleCopyAiFixPack = o.handleCopyAiFixPack;
    var handleCopyDiagnosticsErrors = o.handleCopyDiagnosticsErrors;
    var handleCopyDiagnosticsWarnings = o.handleCopyDiagnosticsWarnings;
    var handleCopyDiagnosticsInfos = o.handleCopyDiagnosticsInfos;

    var copyTextToClipboard = o.copyTextToClipboard;
    var setExportGilStatusText = o.setExportGilStatusText;
    var setExportGiaStatusText = o.setExportGiaStatusText;

    function refreshExportGilBaseGilFileNameText() {
        if (!dom.exportGilBaseGilFileNameTextElement) {
            return;
        }
        if (uiState && uiState.selectedBaseGilFile && uiState.selectedBaseGilFile.name) {
            dom.exportGilBaseGilFileNameTextElement.textContent = "已选择基底存档：" + String(uiState.selectedBaseGilFile.name);
            return;
        }
        dom.exportGilBaseGilFileNameTextElement.textContent = "未选择（默认使用内置样本）。";
    }

    // left tabs
    if (dom.leftTabEditorButtonElement) {
        dom.leftTabEditorButtonElement.addEventListener("click", function () {
            setLeftTab("editor");
        });
    }
    if (dom.leftTabUiSourcesButtonElement) {
        dom.leftTabUiSourcesButtonElement.addEventListener("click", function () {
            setLeftTab("ui_sources");
            uiSources.refreshUiSourceCatalog();
        });
    }
    if (dom.leftTabVariablesButtonElement) {
        dom.leftTabVariablesButtonElement.addEventListener("click", function () {
            setLeftTab("variables");
            variables.refreshVariableCatalog();
        });
    }
    if (dom.leftTabRefreshButtonElement) {
        dom.leftTabRefreshButtonElement.addEventListener("click", function () {
            if (getLeftTabKey && getLeftTabKey() === "ui_sources") {
                uiSources.refreshUiSourceCatalog();
                return;
            }
            if (getLeftTabKey && getLeftTabKey() === "variables") {
                variables.refreshVariableCatalog();
                return;
            }
            refreshAppContextStatus();
        });
    }

    if (dom.uiSourceSearchInputElement) {
        dom.uiSourceSearchInputElement.addEventListener("input", function () {
            uiSources.renderUiSourceList();
        });
    }
    if (dom.uiSourceNewButtonElement) {
        dom.uiSourceNewButtonElement.addEventListener("click", async function () {
            var name = String(prompt("新建 UI源码 文件名（项目）：", "新页面.html") || "").trim();
            if (!name) return;
            if (!/\.html?$/i.test(name)) name = name + ".html";

            var skeleton = [
                "<!DOCTYPE html>",
                "<html lang=\"zh-CN\">",
                "<head>",
                "  <meta charset=\"UTF-8\" />",
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
                "  <title>" + name.replace(/\.html?$/i, "") + "</title>",
                "  <style>",
                "    /* 静态展示稿：不要写 JS；不要出现滚动条 */",
                "    html, body { height: 100%; margin: 0; overflow: hidden; }",
                "    body { background: #1F1F1F; color: #E2DBCE; font-family: \"Microsoft YaHei\", Arial, sans-serif; }",
                "  </style>",
                "</head>",
                "<body>",
                "  <div style=\"position:absolute; left:40px; top:40px; right:40px; bottom:40px;\">",
                "    <div style=\"font-size:28px; font-weight:700;\">示例 UI 页面</div>",
                "    <div style=\"margin-top:12px; color:#B9B2A9;\">可插入占位符：{{lv.变量名}} / {{ps.变量名}}</div>",
                "  </div>",
                "</body>",
                "</html>",
                ""
            ].join("\n");

            if (dom.inputHtmlTextAreaElement) {
                dom.inputHtmlTextAreaElement.value = skeleton;
            }
            uiSources.setCurrentUiSourceSelection({ scope: "project", rel_path: name, file_name: name, is_shared: false });
            uiSources.setUiSourceCurrentFileText("项目：" + name);
            await uiSources.saveCurrentEditorToProjectUiSource();
        });
    }
    if (dom.uiSourceSaveButtonElement) {
        dom.uiSourceSaveButtonElement.addEventListener("click", function () {
            uiSources.saveCurrentEditorToProjectUiSource();
        });
    }
    if (dom.variableSearchInputElement) {
        dom.variableSearchInputElement.addEventListener("input", function () {
            variables.renderVariableList();
        });
    }

    // main actions
    if (dom.validateAndRenderButtonElement) {
        dom.validateAndRenderButtonElement.addEventListener("click", function () {
            handleValidateAndRender();
        });
    }
    if (dom.validateAndRenderButtonInlineElement) {
        dom.validateAndRenderButtonInlineElement.addEventListener("click", function () {
            handleValidateAndRender();
        });
    }
    if (dom.autoFixAndRenderButtonInlineElement) {
        dom.autoFixAndRenderButtonInlineElement.addEventListener("click", function () {
            handleAutoFixAndRender();
        });
    }
    if (dom.generateFlattenedButtonElement) {
        dom.generateFlattenedButtonElement.addEventListener("click", function () {
            handleGenerateFlattened();
        });
    }
    if (dom.generateFlattenedButtonInlineElement) {
        dom.generateFlattenedButtonInlineElement.addEventListener("click", function () {
            handleGenerateFlattened();
        });
    }
    if (dom.exportUiControlGroupJsonButtonElement) {
        dom.exportUiControlGroupJsonButtonElement.addEventListener("click", function () {
            handleExportUiControlGroupJson();
        });
    }
    if (dom.exportUiControlGroupJsonButtonInlineElement) {
        dom.exportUiControlGroupJsonButtonInlineElement.addEventListener("click", function () {
            handleExportUiControlGroupJson();
        });
    }

    if (dom.importToAppButtonInlineElement) {
        dom.importToAppButtonInlineElement.addEventListener("click", function () {
            handleImportIntoApp();
        });
    }
    if (dom.importLayoutNameInputElement) {
        dom.importLayoutNameInputElement.addEventListener("input", function () {
            if (uiState && uiState.importLayoutNameProgrammaticUpdate) {
                return;
            }
            var v = String(dom.importLayoutNameInputElement.value || "").trim();
            if (uiState) {
                uiState.importLayoutNameUserEdited = !!v;
            }
        });
    }

    if (dom.exportGilButtonInlineElement) {
        dom.exportGilButtonInlineElement.addEventListener("click", function () {
            handleExportGilFromWorkbench();
        });
    }
    if (dom.exportGilDownloadLinkElement) {
        dom.exportGilDownloadLinkElement.addEventListener("click", function () {
            var outputPath = String(dom.exportGilDownloadLinkElement.dataset.outputPath || "").trim();
            if (!outputPath) {
                return;
            }
            copyTextToClipboard(outputPath);
            setExportGilStatusText((dom.exportGilStatusTextElement ? dom.exportGilStatusTextElement.textContent : "") + "\n已复制输出路径。");
        });
    }

    if (dom.exportGiaButtonInlineElement) {
        dom.exportGiaButtonInlineElement.addEventListener("click", function () {
            handleExportGiaFromWorkbench();
        });
    }
    if (dom.exportGiaButtonInlineTopElement) {
        dom.exportGiaButtonInlineTopElement.addEventListener("click", function () {
            handleExportGiaFromWorkbench();
        });
    }
    if (dom.exportGiaDownloadLinkElement) {
        dom.exportGiaDownloadLinkElement.addEventListener("click", function () {
            var outputPath = String(dom.exportGiaDownloadLinkElement.dataset.outputPath || "").trim();
            if (!outputPath) {
                return;
            }
            copyTextToClipboard(outputPath);
            setExportGiaStatusText((dom.exportGiaStatusTextElement ? dom.exportGiaStatusTextElement.textContent : "") + "\n已复制输出路径。");
        });
    }
    if (dom.openFlattenedPreviewButtonElement) {
        dom.openFlattenedPreviewButtonElement.addEventListener("click", function () {
            handleOpenFlattenedPreview();
        });
    }
    if (dom.clearInputButtonElement) {
        dom.clearInputButtonElement.addEventListener("click", function () {
            handleClearInput();
        });
    }
    if (dom.htmlFileInputElement) {
        dom.htmlFileInputElement.addEventListener("change", function () {
            handleHtmlFileInputChange();
        });
    }

    // export gil base file
    if (dom.exportGilPickBaseGilButtonElement && dom.exportGilBaseGilFileInputElement) {
        dom.exportGilPickBaseGilButtonElement.addEventListener("click", function () {
            dom.exportGilBaseGilFileInputElement.click();
        });
    }
    if (dom.exportGilBaseGilFileInputElement) {
        dom.exportGilBaseGilFileInputElement.addEventListener("change", function () {
            var file = dom.exportGilBaseGilFileInputElement.files && dom.exportGilBaseGilFileInputElement.files.length > 0
                ? dom.exportGilBaseGilFileInputElement.files[0]
                : null;
            if (uiState) {
                uiState.selectedBaseGilFile = file;
            }
            refreshExportGilBaseGilFileNameText();
        });
    }
    if (dom.exportGilClearBaseGilButtonElement) {
        dom.exportGilClearBaseGilButtonElement.addEventListener("click", function () {
            if (uiState) {
                uiState.selectedBaseGilFile = null;
            }
            if (dom.exportGilBaseGilFileInputElement) {
                dom.exportGilBaseGilFileInputElement.value = "";
            }
            refreshExportGilBaseGilFileNameText();
        });
    }
    refreshExportGilBaseGilFileNameText();

    // canvas size buttons
    var sizeButtonList = document.querySelectorAll("button[data-size-key]");
    if (sizeButtonList && sizeButtonList.length > 0) {
        for (var sizeIndex = 0; sizeIndex < sizeButtonList.length; sizeIndex++) {
            var sizeButton = sizeButtonList[sizeIndex];
            if (!sizeButton) {
                continue;
            }
            sizeButton.addEventListener("click", function (event) {
                var target = event && event.currentTarget ? event.currentTarget : null;
                var sizeKey = target && target.dataset ? String(target.dataset.sizeKey || "").trim() : "";
                if (!sizeKey) {
                    return;
                }
                preview.setSelectedCanvasSize(sizeKey);
                if (groupTreeController) {
                    groupTreeController.refresh();
                }
            });
        }
    }

    if (dom.togglePreviewOnlyModeButtonElement) {
        dom.togglePreviewOnlyModeButtonElement.addEventListener("click", function () {
            preview.setPreviewOnlyModeEnabled(!preview.getPreviewOnlyModeEnabled());
        });
    }
    if (dom.previewVariantSourceButtonElement) {
        dom.previewVariantSourceButtonElement.addEventListener("click", function () {
            previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_SOURCE);
        });
    }
    if (dom.previewVariantFlattenedButtonElement) {
        dom.previewVariantFlattenedButtonElement.addEventListener("click", function () {
            previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_FLATTENED);
            if (groupTreeController) {
                groupTreeController.refresh();
            }
        });
    }

    if (dom.dynamicTextPreviewCheckboxElement) {
        dom.dynamicTextPreviewCheckboxElement.addEventListener("change", function () {
            preview.setDynamicTextPreviewEnabled(!!dom.dynamicTextPreviewCheckboxElement.checked);
            // 仅影响预览：直接按当前变体重渲染即可
            previewVariantSwitcher.requestPreviewVariantSwitch(previewVariantSwitcher.getCurrentPreviewVariant());
        });
    }

    if (dom.inspectorTabInfoButtonElement) {
        dom.inspectorTabInfoButtonElement.addEventListener("click", function () {
            setInspectorTab("info");
        });
    }
    if (dom.inspectorTabGroupButtonElement) {
        dom.inspectorTabGroupButtonElement.addEventListener("click", function () {
            setInspectorTab("group");
        });
    }

    if (dom.flattenGroupTreeContainerElement && groupTreeController) {
        dom.flattenGroupTreeContainerElement.addEventListener("click", async function (event) {
            await groupTreeController.handleTreeClick(event, {
                previewVariant: previewVariantSwitcher,
                previewVariantFlattened: PREVIEW_VARIANT_FLATTENED,
                ensureFlattened: function () {
                    return previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_FLATTENED);
                }
            });
        });
    }

    if (dom.flattenDebugShowAllCheckboxElement) {
        dom.flattenDebugShowAllCheckboxElement.addEventListener("change", async function () {
            // Debug flags affect flattened output => explicitly re-generate (heavy op),
            // but keep preview variant switching as pure display.
            if (previewVariantSwitcher.getCurrentPreviewVariant() === PREVIEW_VARIANT_FLATTENED) {
                await handleGenerateFlattened();
                await previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_FLATTENED);
            }
        });
    }
    if (dom.flattenDebugShowGroupsCheckboxElement) {
        dom.flattenDebugShowGroupsCheckboxElement.addEventListener("change", async function () {
            if (previewVariantSwitcher.getCurrentPreviewVariant() === PREVIEW_VARIANT_FLATTENED) {
                await handleGenerateFlattened();
                await previewVariantSwitcher.requestPreviewVariantSwitch(PREVIEW_VARIANT_FLATTENED);
            }
        });
    }

    if (dom.refreshPreviewButtonElement) {
        dom.refreshPreviewButtonElement.addEventListener("click", function () {
            preview.refreshPreviewToRestoreDeletedElements();
            if (groupTreeController) {
                groupTreeController.refresh();
            }
        });
    }
    if (dom.deleteSelectionButtonElement) {
        dom.deleteSelectionButtonElement.addEventListener("click", function () {
            preview.deleteSelectedPreviewElements();
        });
    }
    if (dom.toggleShadowInspectButtonElement) {
        dom.toggleShadowInspectButtonElement.addEventListener("click", function () {
            preview.setShadowInspectModeEnabled(!preview.getShadowInspectModeEnabled());
        });
    }

    if (dom.refreshFlattenGroupTreeButtonElement && groupTreeController) {
        dom.refreshFlattenGroupTreeButtonElement.addEventListener("click", function () {
            groupTreeController.refresh();
        });
    }

    if (dom.copyValidationErrorsButtonElement && dom.validationErrorsTextAreaElement) {
        dom.copyValidationErrorsButtonElement.addEventListener("click", function () {
            copyTextToClipboard(dom.validationErrorsTextAreaElement.value || "");
        });
    }
    if (dom.copyAiFixPackButtonElement) {
        dom.copyAiFixPackButtonElement.addEventListener("click", function () {
            if (handleCopyAiFixPack) {
                handleCopyAiFixPack();
            }
        });
    }
    if (dom.copyDiagnosticsErrorsButtonElement) {
        dom.copyDiagnosticsErrorsButtonElement.addEventListener("click", function () {
            if (handleCopyDiagnosticsErrors) {
                handleCopyDiagnosticsErrors();
            }
        });
    }
    if (dom.copyDiagnosticsWarningsButtonElement) {
        dom.copyDiagnosticsWarningsButtonElement.addEventListener("click", function () {
            if (handleCopyDiagnosticsWarnings) {
                handleCopyDiagnosticsWarnings();
            }
        });
    }
    if (dom.copyDiagnosticsInfosButtonElement) {
        dom.copyDiagnosticsInfosButtonElement.addEventListener("click", function () {
            if (handleCopyDiagnosticsInfos) {
                handleCopyDiagnosticsInfos();
            }
        });
    }
    if (dom.copyFlattenedOutputButtonElement && dom.flattenedOutputTextAreaElement) {
        dom.copyFlattenedOutputButtonElement.addEventListener("click", function () {
            copyTextToClipboard(dom.flattenedOutputTextAreaElement.value || "");
        });
    }
    if (dom.copyUiControlGroupJsonOutputButtonElement && dom.uiControlGroupJsonOutputTextAreaElement) {
        dom.copyUiControlGroupJsonOutputButtonElement.addEventListener("click", function () {
            copyTextToClipboard(dom.uiControlGroupJsonOutputTextAreaElement.value || "");
        });
    }
    if (dom.copyInspectorButtonElement) {
        dom.copyInspectorButtonElement.addEventListener("click", function () {
            var importantText = dom.inspectorImportantTextAreaElement ? dom.inspectorImportantTextAreaElement.value || "" : "";
            var detailsText = dom.inspectorDetailsTextAreaElement ? dom.inspectorDetailsTextAreaElement.value || "" : "";
            var combinedText = [
                "【常用信息】",
                importantText,
                "",
                "【详细信息】",
                detailsText
            ].join("\n");
            copyTextToClipboard(combinedText);
        });
    }

    if (dom.inputHtmlTextAreaElement) {
        dom.inputHtmlTextAreaElement.addEventListener("input", function () {
            if (handleEditorSourceChanged) {
                handleEditorSourceChanged("源码已修改。");
            }
        });
        dom.inputHtmlTextAreaElement.addEventListener("keydown", function (event) {
            if (!event) {
                return;
            }
            var key = event.key || "";
            var isEnterKey = key === "Enter";
            if (!isEnterKey) {
                return;
            }
            if (!event.ctrlKey) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            if (event.shiftKey) {
                handleGenerateFlattened();
            } else {
                handleValidateAndRender();
            }
        });
    }

    if (dom.reverseRegionCheckboxElement) {
        dom.reverseRegionCheckboxElement.addEventListener("change", function () {
            preview.setReverseRegionModeEnabled(!!dom.reverseRegionCheckboxElement.checked);
        });
    }

    window.addEventListener("resize", function () {
        preview.handleWindowResize();
    });
    window.addEventListener("keydown", function (event) {
        preview.handleDeleteShortcutKeyDown(event);
    }, true);
}

