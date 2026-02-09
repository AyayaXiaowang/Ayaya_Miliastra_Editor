import { getCanvasSizeByKey, PREVIEW_VARIANT_FLATTENED, PREVIEW_VARIANT_SOURCE } from "../config.js";
import { waitForNextFrame } from "../utils.js";
import { extractDisplayElementsData, buildFlattenedLayerData } from "../flatten.js";
import { createFlattenGroupTreeController } from "../workbench_main/group_tree.js";
import * as preview from "../preview/index.js";
import {
  dom,
  setExportStatusText,
  setFlattenGroupTreeEmptyTip,
  setFlattenGroupTreeStatusText,
  setLeftBottomTabMode,
  setSelectedFileText,
  setStatusText,
  setSubtitle,
  setExportWidgetListEmptyTip,
  setExportWidgetListStatusText,
  setFlattenGroupTreeController,
  flattenGroupTreeController,
  state,
  updateSelectedBaseGilUi,
} from "./context.js";
import { refreshStatus } from "./api.js";
import { restoreBaseGilFromBestEffortCache, saveBaseGilToBestEffortCache } from "./base_gil_cache.js";
import { setCatalogCallbacks, refreshCatalog, renderFileList } from "./catalog.js";
import {
  decodeSelectionKey,
  loadCheckedFilesFromStorage,
  loadExportUiStateFullGroupsFromStorage,
  pickDefaultSelectableItem,
  saveExportUiStateFullGroupsToStorage
} from "./storage.js";
import { selectFile } from "./selection.js";
import { updateExportGiaButtonEnabled, updateExportGilButtonEnabled, updateImportVariableDefaultsButtonEnabled, updateVariantButtons } from "./buttons.js";
import { renderUiStateSelectorsFromCatalog, resetAllUiStatePreviewOverrides, syncUiStatePreviewUiAndApply } from "./ui_state_preview.js";
import { renderPreview } from "./preview_render.js";
import { exportGiaForCurrentSelection, exportGilForCheckedSelections, exportGilForCurrentSelection, setBaseGilFile, setBaseGilPath } from "./export_actions.js";
import { importVariableDefaultsForCurrentSelection } from "./import_variable_defaults.js";
import { refreshExportWidgetListForCurrentSelectionIfNeeded } from "./export_widgets_part2.js";
import { handlePreviewSelectionChangedForLeftBottomPanels } from "./export_widgets_part3b.js";
import { renderExportWidgetPreviewHtml } from "./export_widgets_model.js";
import { getCheckedSelectionsInCatalogOrder } from "./storage.js";

function _scrollExportWidgetIntoView(widgetId) {
  var wid = String(widgetId || "").trim();
  if (!wid) return;
  if (!dom.exportWidgetListContainer) return;
  var node = dom.exportWidgetListContainer.querySelector('[data-export-widget="1"][data-widget-id="' + (window.CSS && CSS.escape ? CSS.escape(wid) : wid) + '"]');
  if (!node || !node.scrollIntoView) return;
  node.scrollIntoView({ block: "center" });
}

function _rerenderExportWidgetList() {
  if (dom.exportWidgetListContainer && state.exportWidgetPreviewModel) {
    dom.exportWidgetListContainer.innerHTML = renderExportWidgetPreviewHtml(state.exportWidgetPreviewModel);
  }
}

function _bindPreviewSizeButtons() {
  var buttons = document.querySelectorAll("button[data-size-key]");
  for (var i = 0; i < buttons.length; i++) {
    (function () {
      var btn = buttons[i];
      if (!btn) return;
      btn.addEventListener("click", async function () {
        var k = String(btn.getAttribute("data-size-key") || "").trim();
        if (!k) return;
        state.canvasSizeKey = k;
        preview.setSelectedCanvasSize(k);
        // 画布变更后：重绘预览（保持当前变体），并刷新导出控件列表（依赖 canvas size）
        await renderPreview();
        await refreshExportWidgetListForCurrentSelectionIfNeeded(true);
      });
    })();
  }
}

function _bindExportWidgetListInteractions() {
  if (!dom.exportWidgetListContainer) return;

  dom.exportWidgetListContainer.addEventListener("click", async function (ev) {
    var el = ev && ev.target ? ev.target : null;
    if (!el) return;

    // 1) toggle actions: widget/group eye/trash
    var toggle = el.closest ? el.closest(".wb-tree-toggle[data-toggle-kind]") : null;
    if (toggle && toggle.dataset) {
      var kind = String(toggle.dataset.toggleKind || "");
      var action = String(toggle.dataset.toggleAction || "hide");

      // group toggle: apply to all widgets in that group by flat_layer_key
      if (kind === "group") {
        var gk = String(toggle.dataset.groupKey || "").trim();
        if (!gk || !state.exportWidgetPreviewModel) return;

        if (action === "exclude") {
          if (typeof window !== "undefined" && state.exportWidgetPreviewModel) {
            // group-level exclude uses controller's group exclusion set (same key space)
            if (state.exportWidgetPreviewModel && state.exportWidgetPreviewModel.groups) {
              // use controller method if exists
              // note: group_tree controller uses groupKey for exclusion
            }
          }
          if (state.exportWidgetPreviewModel && flattenGroupTreeController && flattenGroupTreeController.setGroupExcluded && flattenGroupTreeController.isGroupExcluded) {
            flattenGroupTreeController.setGroupExcluded(gk, !flattenGroupTreeController.isGroupExcluded(gk));
          }
          _rerenderExportWidgetList();
          ev.preventDefault();
          ev.stopPropagation();
          return;
        }

        // ensure flattened preview before toggles take effect visually
        if (state.currentVariant !== PREVIEW_VARIANT_FLATTENED) {
          state.currentVariant = PREVIEW_VARIANT_FLATTENED;
          updateVariantButtons();
          await renderPreview();
          setStatusText("预览：扁平化");
        }

        // 关键：显隐判定与归一化依赖“当前预览 DOM 索引”，必须在 toggle 前刷新一次。
        if (flattenGroupTreeController && flattenGroupTreeController.indexFlattenedPreviewElements) {
          flattenGroupTreeController.indexFlattenedPreviewElements();
        }

        // hide/show: compute desired from any layer hidden state
        var targetGroup = null;
        var groupsG = state.exportWidgetPreviewModel.groups || [];
        for (var gi = 0; gi < groupsG.length; gi++) {
          if (String((groupsG[gi] || {}).group_key || "").trim() === gk) {
            targetGroup = groupsG[gi];
            break;
          }
        }
        if (!targetGroup) return;
        var ws = targetGroup.widgets || [];
        var layerKeys = [];
        for (var wi = 0; wi < ws.length; wi++) {
          var lk = String((ws[wi] || {}).flat_layer_key || "").trim();
          if (lk) layerKeys.push(lk);
        }
        if (flattenGroupTreeController && flattenGroupTreeController.setLayersHidden) {
          var wantHidden = true;
          if (flattenGroupTreeController.isLayerHidden && layerKeys.length > 0) {
            var allHidden = true;
            for (var li = 0; li < layerKeys.length; li++) {
              if (!flattenGroupTreeController.isLayerHidden(layerKeys[li])) {
                allHidden = false;
                break;
              }
            }
            wantHidden = !allHidden;
          }
          flattenGroupTreeController.setLayersHidden(layerKeys, wantHidden);
          _rerenderExportWidgetList();
        }
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }

      if (kind === "widget") {
        var row = toggle.closest ? toggle.closest('[data-export-widget="1"][data-widget-id]') : null;
        var bestKey = row && row.dataset ? String(row.dataset.flatLayerKey || "").trim() : "";
        if (!bestKey) {
          setExportStatusText("[显隐/排除] 当前条目缺少 data-flat-layer-key：已拒绝执行。");
          ev.preventDefault();
          ev.stopPropagation();
          return;
        }

        // ensure flattened preview before toggles take effect visually
        if (state.currentVariant !== PREVIEW_VARIANT_FLATTENED) {
          state.currentVariant = PREVIEW_VARIANT_FLATTENED;
          updateVariantButtons();
          await renderPreview();
          setStatusText("预览：扁平化");
        }

        if (!flattenGroupTreeController) return;
        if (flattenGroupTreeController.indexFlattenedPreviewElements) {
          flattenGroupTreeController.indexFlattenedPreviewElements();
        }
        if (action === "exclude") {
          if (flattenGroupTreeController.setLayerExcluded && flattenGroupTreeController.isLayerExcluded) {
            flattenGroupTreeController.setLayerExcluded(bestKey, !flattenGroupTreeController.isLayerExcluded(bestKey));
          }
        } else {
          if (flattenGroupTreeController.setLayerHidden && flattenGroupTreeController.isLayerHidden) {
            flattenGroupTreeController.setLayerHidden(bestKey, !flattenGroupTreeController.isLayerHidden(bestKey));
          }
        }
        _rerenderExportWidgetList();
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
    }

    // 2) row click: select corresponding flat layer in preview
    var btn = el.closest ? el.closest("[data-export-widget='1']") : null;
    if (!btn) return;
    var wid = String(btn.dataset && btn.dataset.widgetId ? btn.dataset.widgetId : "").trim();
    var layerKey = String(btn.dataset && btn.dataset.flatLayerKey ? btn.dataset.flatLayerKey : "").trim();
    if (!wid || !layerKey) return;

    state.suppressNextExportWidgetAutoScroll = true;
    state.exportSelectedWidgetId = wid;
    _rerenderExportWidgetList();

    // ensure flattened preview
    if (state.currentVariant !== PREVIEW_VARIANT_FLATTENED) {
      state.currentVariant = PREVIEW_VARIANT_FLATTENED;
      updateVariantButtons();
      await renderPreview();
      setStatusText("预览：扁平化");
    }

    if (flattenGroupTreeController && flattenGroupTreeController.indexFlattenedPreviewElements) {
      flattenGroupTreeController.indexFlattenedPreviewElements();
    }
    var target = flattenGroupTreeController && flattenGroupTreeController.findPreviewElementByLayerKey
      ? flattenGroupTreeController.findPreviewElementByLayerKey(layerKey)
      : null;
    if (target) {
      preview.selectPreviewElement(target);
    }
    ev.preventDefault();
    ev.stopPropagation();
  });
}

function _bindEvents() {
  if (dom.searchInput) {
    dom.searchInput.addEventListener("input", function () {
      renderFileList();
    });
  }

  if (dom.leftBottomSearchButton) {
    dom.leftBottomSearchButton.addEventListener("click", function () {
      state.leftBottomFilterText = String((dom.leftBottomSearchInput && dom.leftBottomSearchInput.value) || "").trim();
      if (state.leftBottomTabMode === "export_widgets") {
        _rerenderExportWidgetList();
      } else if (flattenGroupTreeController && flattenGroupTreeController.setFilterText) {
        flattenGroupTreeController.setFilterText(state.leftBottomFilterText);
      }
    });
  }
  if (dom.leftBottomSearchInput) {
    dom.leftBottomSearchInput.addEventListener("keydown", function (ev) {
      if (String(ev && ev.key || "") === "Enter") {
        if (dom.leftBottomSearchButton) dom.leftBottomSearchButton.click();
      }
    });
  }

  if (dom.leftBottomTabExportWidgetsButton) {
    dom.leftBottomTabExportWidgetsButton.addEventListener("click", function () {
      setLeftBottomTabMode("export_widgets");
      if (state.pendingScrollExportWidgetId) {
        _scrollExportWidgetIntoView(state.pendingScrollExportWidgetId);
        state.pendingScrollExportWidgetId = "";
      }
    });
  }
  if (dom.leftBottomTabFlattenGroupsButton) {
    dom.leftBottomTabFlattenGroupsButton.addEventListener("click", function () {
      setLeftBottomTabMode("flatten_groups");
    });
  }

  // 扁平分组树交互（眼睛/垃圾桶/选中定位）：
  // 统一复用 group_tree.js 的 handleTreeClick，并在需要时自动切到“扁平化预览”，
  // 避免出现“列表图标变了但画布没变化”的错觉。
  if (dom.flattenGroupTreeContainer) {
    dom.flattenGroupTreeContainer.addEventListener("click", async function (ev) {
      if (!flattenGroupTreeController || !flattenGroupTreeController.handleTreeClick) {
        return;
      }
      await flattenGroupTreeController.handleTreeClick(ev, {
        previewVariant: preview,
        previewVariantFlattened: PREVIEW_VARIANT_FLATTENED,
        ensureFlattened: async function () {
          state.currentVariant = PREVIEW_VARIANT_FLATTENED;
          updateVariantButtons();
          await renderPreview();
          setStatusText("预览：扁平化");
        }
      });
    });
  }

  if (dom.previewVariantFlattenedButton) {
    dom.previewVariantFlattenedButton.addEventListener("click", async function () {
      state.currentVariant = PREVIEW_VARIANT_FLATTENED;
      updateVariantButtons();
      await renderPreview();
      setStatusText("预览：扁平化");
    });
  }
  if (dom.previewVariantSourceButton) {
    dom.previewVariantSourceButton.addEventListener("click", async function () {
      state.currentVariant = PREVIEW_VARIANT_SOURCE;
      updateVariantButtons();
      await renderPreview();
      setStatusText("预览：原稿");
    });
  }

  if (dom.dynamicTextPreviewCheckbox) {
    dom.dynamicTextPreviewCheckbox.addEventListener("change", async function () {
      preview.setDynamicTextPreviewEnabled(!!dom.dynamicTextPreviewCheckbox.checked);
      await renderPreview();
    });
  }

  if (dom.exportUiStateFullGroupsCheckbox) {
    dom.exportUiStateFullGroupsCheckbox.addEventListener("change", function () {
      state.exportUiStateFullGroups = !!dom.exportUiStateFullGroupsCheckbox.checked;
      saveExportUiStateFullGroupsToStorage();
      // 该开关会改变 bundle/导出控件列表的结构：清空缓存，避免 UI 误导。
      state.exportWidgetPreviewCache = {};
      state.exportWidgetPreviewModel = null;
      state.exportWidgetIdByLayerKey = {};
      setExportWidgetListStatusText("未生成");
    });
  }

  if (dom.uiStateGroupSelect) {
    dom.uiStateGroupSelect.addEventListener("change", function () {
      state.uiStatePreview.group = String(dom.uiStateGroupSelect.value || "");
      state.uiStatePreview.state = "";
      syncUiStatePreviewUiAndApply();
    });
  }
  if (dom.uiStateValueSelect) {
    dom.uiStateValueSelect.addEventListener("change", function () {
      state.uiStatePreview.state = String(dom.uiStateValueSelect.value || "");
      syncUiStatePreviewUiAndApply();
    });
  }
  if (dom.uiStateResetButton) {
    dom.uiStateResetButton.addEventListener("click", function () {
      state.uiStatePreview.group = "";
      state.uiStatePreview.state = "";
      var doc0 = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
      if (doc0) resetAllUiStatePreviewOverrides(doc0);
      syncUiStatePreviewUiAndApply();
    });
  }

  if (dom.selectBaseGilButton && dom.baseGilFileInput) {
    dom.selectBaseGilButton.addEventListener("click", function () {
      dom.baseGilFileInput.click();
    });
    dom.baseGilFileInput.addEventListener("change", async function () {
      var f = dom.baseGilFileInput.files && dom.baseGilFileInput.files.length > 0 ? dom.baseGilFileInput.files[0] : null;
      if (!f) return;
      setBaseGilFile(f);
      await saveBaseGilToBestEffortCache(f);
      updateExportGilButtonEnabled();
    });
  }

  if (dom.useCurrentBaseGilButton) {
    dom.useCurrentBaseGilButton.addEventListener("click", function () {
      var p = String(state.suggestedBaseGilPath || "").trim();
      if (!p) return;
      setBaseGilPath(p);
      updateExportGilButtonEnabled();
    });
  }

  if (dom.exportGiaButton) {
    dom.exportGiaButton.addEventListener("click", function () {
      exportGiaForCurrentSelection();
    });
  }
  if (dom.exportGilButton) {
    dom.exportGilButton.addEventListener("click", function () {
      var checked = getCheckedSelectionsInCatalogOrder();
      if (checked && checked.length > 0) {
        exportGilForCheckedSelections(checked);
      } else {
        exportGilForCurrentSelection();
      }
    });
  }
  if (dom.importVariableDefaultsButton) {
    dom.importVariableDefaultsButton.addEventListener("click", function () {
      importVariableDefaultsForCurrentSelection();
    });
  }

  if (dom.refreshButton) {
    dom.refreshButton.addEventListener("click", async function () {
      await refreshStatus();
      updateExportGiaButtonEnabled();
      updateExportGilButtonEnabled();
      updateImportVariableDefaultsButtonEnabled();
      await refreshCatalog();
    });
  }

  window.addEventListener("resize", function () {
    preview.handleWindowResize();
  });
}

export async function main() {
  preview.initializePreviewUi();
  preview.setSelectedCanvasSize(state.canvasSizeKey);
  updateVariantButtons();
  updateExportGiaButtonEnabled();
  updateExportGilButtonEnabled();
  updateImportVariableDefaultsButtonEnabled();
  updateSelectedBaseGilUi();
  renderUiStateSelectorsFromCatalog({ groups: [] });
  setLeftBottomTabMode(state.leftBottomTabMode);
  loadCheckedFilesFromStorage();
  loadExportUiStateFullGroupsFromStorage();
  if (dom.exportUiStateFullGroupsCheckbox) {
    dom.exportUiStateFullGroupsCheckbox.checked = !!state.exportUiStateFullGroups;
  }

  // group tree controller
  var controller = createFlattenGroupTreeController({
    preview: preview,
    getHtmlText: function () {
      return state.selected ? String(state.selected.source_html || "") : "";
    },
    waitForNextFrame: waitForNextFrame,
    getCanvasSizeByKey: getCanvasSizeByKey,
    extractDisplayElementsData: extractDisplayElementsData,
    buildFlattenedLayerData: buildFlattenedLayerData,
    enable_visibility_toggles: true,
    enable_export_exclude_toggles: true,
  });
  setFlattenGroupTreeController(controller);

  preview.setSelectionChangedCallback(function (payload) {
    if (!controller) return;
    if (controller.indexFlattenedPreviewElements) {
      controller.indexFlattenedPreviewElements();
    }
    controller.handlePreviewSelectionChanged(payload);
    handlePreviewSelectionChangedForLeftBottomPanels(payload);
  });

  setCatalogCallbacks({
    selectFile: selectFile,
    onCheckedFilesChanged: function () {
      updateExportGilButtonEnabled();
    }
  });

  _bindPreviewSizeButtons();
  _bindExportWidgetListInteractions();
  _bindEvents();

  await refreshStatus();
  updateExportGiaButtonEnabled();
  updateExportGilButtonEnabled();
  updateImportVariableDefaultsButtonEnabled();

  // 恢复“上次选择的基底 GIL”（若存在）
  await restoreBaseGilFromBestEffortCache();
  updateExportGilButtonEnabled();

  // 若未恢复到文件，但后端给了“当前 GIL”，则默认使用它
  if (!state.baseGilFile && !String(state.baseGilPath || "").trim() && String(state.suggestedBaseGilPath || "").trim()) {
    state.baseGilPath = String(state.suggestedBaseGilPath || "").trim();
    updateSelectedBaseGilUi();
    updateExportGilButtonEnabled();
  }

  await refreshCatalog();

  // 初始行为：自动打开“上次选中的文件”；否则选第一个可用文件。
  var items = state.items || [];
  var last = decodeSelectionKey(window.localStorage.getItem("ui_preview:last_selected"));
  var target = null;
  if (last && last.file_name) {
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      var fn = String(it.file_name || it.fileName || "");
      var sc = String(it.scope || "project");
      if (fn && fn === String(last.file_name) && sc === String(last.scope || "project")) {
        target = { scope: sc, file_name: fn };
        break;
      }
    }
  }
  if (!target) {
    target = pickDefaultSelectableItem(items);
  }
  if (target && target.file_name) {
    await selectFile(target.scope, target.file_name);
    return;
  }

  await renderPreview();
  setStatusText("就绪（未找到 UI源码 文件）");
  setFlattenGroupTreeStatusText("未生成");
  setFlattenGroupTreeEmptyTip("未找到任何 UI源码 文件。");
  setExportWidgetListStatusText("未生成");
  setExportWidgetListEmptyTip("未找到任何 UI源码 文件。");
  setExportStatusText("提示：请先选择一个 UI源码 文件。");
}

