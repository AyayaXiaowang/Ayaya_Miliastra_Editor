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
  pickDefaultSelectableItem
} from "./storage.js";
import { selectFile } from "./selection.js";
import { updateExportGiaButtonEnabled, updateExportGilButtonEnabled, updateImportVariableDefaultsButtonEnabled, updateVariantButtons } from "./buttons.js";
import { renderUiStateSelectorsFromCatalog, resetAllUiStatePreviewOverrides, syncUiStatePreviewUiAndApply } from "./ui_state_preview.js";
import { renderPreview } from "./preview_render.js";
import { exportGiaForCurrentSelection, exportGilForCheckedSelections, exportGilForCurrentSelection, setBaseGilFile, setBaseGilPath } from "./export_actions.js";
import { importVariableDefaultsForCurrentSelection } from "./import_variable_defaults.js";
import { refreshExportWidgetListForCurrentSelectionIfNeeded, refreshExportWidgetModelForCurrentSelectionInPlace } from "./export_widgets_part2.js";
import { handlePreviewSelectionChangedForLeftBottomPanels } from "./export_widgets_part3b.js";
import { updateExportWidgetListSelectionDom } from "./export_widget_list_dom.js";
import { scheduleRerenderExportWidgetListFromCurrentModel } from "./export_widget_list_render.js";
import { getCheckedSelectionsInCatalogOrder } from "./storage.js";

function _syncEyeToggleButtonUi(buttonEl, isHidden) {
  var btn = buttonEl || null;
  if (!btn) return;
  var icon = btn.querySelector ? btn.querySelector(".wb-eye-icon") : null;
  if (icon) {
    if (isHidden) icon.setAttribute("data-hidden", "1");
    else icon.removeAttribute("data-hidden");
  }
  if (btn.setAttribute) btn.setAttribute("aria-label", isHidden ? "显示" : "隐藏");
  if (btn.title !== undefined) btn.title = isHidden ? "点击显示" : "点击隐藏";
}

function _syncTrashToggleButtonUi(buttonEl, isExcluded) {
  var btn = buttonEl || null;
  if (!btn) return;
  var icon = btn.querySelector ? btn.querySelector(".wb-trash-icon") : null;
  if (icon) {
    if (isExcluded) icon.setAttribute("data-excluded", "1");
    else icon.removeAttribute("data-excluded");
  }
  if (btn.setAttribute) btn.setAttribute("aria-label", isExcluded ? "取消排除" : "排除导出");
  if (btn.title !== undefined) btn.title = isExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）";
}

function _refreshExportWidgetListVisibilityIconsInDetails(detailsEl) {
  var details = detailsEl || null;
  if (!details || !details.querySelectorAll) return;
  if (!flattenGroupTreeController || !flattenGroupTreeController.isLayerHidden) return;

  var rows = details.querySelectorAll('[data-export-widget="1"][data-widget-id]');
  var layerKeys = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (!row || !row.dataset) continue;
    var lk = String(row.dataset.flatLayerKey || "").trim();
    if (lk) layerKeys.push(lk);
    var widgetEyeBtn = row.querySelector ? row.querySelector('.wb-tree-toggle.wb-tree-eye[data-toggle-kind="widget"]') : null;
    _syncEyeToggleButtonUi(widgetEyeBtn, !!(lk && flattenGroupTreeController.isLayerHidden(lk)));
  }

  var groupEyeBtn = details.querySelector ? details.querySelector('summary .wb-tree-toggle.wb-tree-eye[data-toggle-kind="group"]') : null;
  if (groupEyeBtn) {
    var allHidden = false;
    if (layerKeys.length > 0) {
      allHidden = true;
      for (var j = 0; j < layerKeys.length; j++) {
        if (!flattenGroupTreeController.isLayerHidden(layerKeys[j])) {
          allHidden = false;
          break;
        }
      }
    }
    _syncEyeToggleButtonUi(groupEyeBtn, allHidden);
  }
}

function _refreshExportWidgetListExcludeIconsInDetails(detailsEl) {
  var details = detailsEl || null;
  if (!details || !details.querySelectorAll) return;
  if (!flattenGroupTreeController || !flattenGroupTreeController.isLayerExcluded || !flattenGroupTreeController.isGroupExcluded) return;

  var groupKey = details.dataset ? String(details.dataset.groupKey || "").trim() : "";
  var isGroupExcluded = !!(groupKey && flattenGroupTreeController.isGroupExcluded(groupKey));
  var groupTrashBtn = details.querySelector ? details.querySelector('summary .wb-tree-toggle.wb-tree-trash[data-toggle-kind="group"]') : null;
  _syncTrashToggleButtonUi(groupTrashBtn, isGroupExcluded);

  var rows = details.querySelectorAll('[data-export-widget="1"][data-widget-id]');
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (!row || !row.dataset) continue;
    var lk = String(row.dataset.flatLayerKey || "").trim();
    var isExcluded = isGroupExcluded || !!(lk && flattenGroupTreeController.isLayerExcluded(lk));
    var widgetTrashBtn = row.querySelector ? row.querySelector('.wb-tree-toggle.wb-tree-trash[data-toggle-kind="widget"]') : null;
    _syncTrashToggleButtonUi(widgetTrashBtn, isExcluded);
  }
}

var _isFlattenedTimelapseRunning = false;
var _isSourceTimelapseRunning = false;
var _FLATTENED_TIMELAPSE_STEP_MS = 100;
var _SOURCE_TIMELAPSE_STEP_MS = 100;

function _sleepMs(ms) {
  var wait = Number(ms);
  if (!isFinite(wait) || wait < 0) wait = 0;
  return new Promise(function (resolve) {
    window.setTimeout(resolve, wait);
  });
}

function _setFlattenedTimelapseButtonRunning(isRunning) {
  if (!dom.flattenedTimelapseRevealButton) return;
  dom.flattenedTimelapseRevealButton.disabled = !!isRunning;
  dom.flattenedTimelapseRevealButton.textContent = isRunning ? "播放中…" : "延时摄影";
}

function _collectVisibleFlattenedElementsForCurrentCanvas() {
  var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
  if (!doc || !doc.querySelector) return [];
  var sizeKey = String(preview.getCurrentSelectedCanvasSizeKey ? (preview.getCurrentSelectedCanvasSizeKey() || "") : (state.canvasSizeKey || "")).trim();
  var area = null;
  if (sizeKey) {
    area = doc.querySelector('.flat-display-area[data-size-key="' + sizeKey + '"]');
  }
  if (!area) {
    area = doc.querySelector(".flat-display-area");
  }
  if (!area || !area.querySelectorAll || !doc.defaultView || !doc.defaultView.getComputedStyle) {
    return [];
  }
  var nodeList = area.querySelectorAll(".flat-shadow, .flat-border, .flat-element, .flat-text, .flat-button-anchor");
  var out = [];
  for (var i = 0; i < nodeList.length; i++) {
    var el = nodeList[i];
    if (!el || !el.style || !el.getBoundingClientRect) continue;
    var cs = doc.defaultView.getComputedStyle(el);
    if (!cs) continue;
    if (String(cs.display || "") === "none") continue;
    if (String(cs.visibility || "") === "hidden") continue;
    var opacityValue = Number(cs.opacity);
    if (isFinite(opacityValue) && opacityValue <= 0.0001) continue;
    var rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) continue;
    out.push({
      el: el,
      visibility: String(el.style.visibility || ""),
    });
  }
  return out;
}

function _hasVisibleColor(colorText) {
  var text = String(colorText || "").trim().toLowerCase();
  if (!text || text === "transparent") {
    return false;
  }
  if (text.indexOf("rgba(") === 0) {
    var start = text.indexOf("(");
    var end = text.lastIndexOf(")");
    if (start >= 0 && end > start) {
      var parts = text.slice(start + 1, end).split(",");
      if (parts.length >= 4) {
        var alpha = Number(String(parts[3] || "").trim());
        if (isFinite(alpha)) {
          return alpha > 0.0001;
        }
      }
    }
    return true;
  }
  if (text.indexOf("#") === 0) {
    if (text.length === 5) {
      var a4 = parseInt(text.slice(4, 5) + text.slice(4, 5), 16);
      if (isFinite(a4)) {
        return a4 > 0;
      }
    }
    if (text.length === 9) {
      var a8 = parseInt(text.slice(7, 9), 16);
      if (isFinite(a8)) {
        return a8 > 0;
      }
    }
    return true;
  }
  return text !== "rgba(0, 0, 0, 0)" && text !== "rgba(0,0,0,0)";
}

function _hasDirectTextNodeContent(el) {
  if (!el || !el.childNodes || el.childNodes.length <= 0) {
    return false;
  }
  for (var i = 0; i < el.childNodes.length; i++) {
    var node = el.childNodes[i];
    if (!node || node.nodeType !== 3) continue;
    if (String(node.textContent || "").trim()) {
      return true;
    }
  }
  return false;
}

function _hasVisibleBorder(cs) {
  if (!cs) return false;
  var borderWidths = [cs.borderTopWidth, cs.borderRightWidth, cs.borderBottomWidth, cs.borderLeftWidth];
  var borderColors = [cs.borderTopColor, cs.borderRightColor, cs.borderBottomColor, cs.borderLeftColor];
  for (var i = 0; i < borderWidths.length; i++) {
    var width = Number(parseFloat(String(borderWidths[i] || "0")));
    if (!isFinite(width) || width <= 0.0001) continue;
    if (_hasVisibleColor(borderColors[i])) {
      return true;
    }
  }
  return false;
}

function _isSourceIntrinsicVisualTag(tagName) {
  return tagName === "img"
    || tagName === "svg"
    || tagName === "canvas"
    || tagName === "video"
    || tagName === "picture"
    || tagName === "input"
    || tagName === "select"
    || tagName === "textarea"
    || tagName === "progress"
    || tagName === "meter";
}

function _isSourceTimelapseRevealCandidate(el, cs) {
  if (!el || !cs) return false;
  var tagName = String(el.tagName || "").toLowerCase();
  if (!tagName) return false;
  if (tagName === "script" || tagName === "style" || tagName === "link" || tagName === "meta" || tagName === "head" || tagName === "title") {
    return false;
  }
  if (_isSourceIntrinsicVisualTag(tagName)) {
    return true;
  }
  if (_hasDirectTextNodeContent(el)) {
    return true;
  }
  var bgColor = String(cs.backgroundColor || "").trim();
  if (_hasVisibleColor(bgColor)) {
    return true;
  }
  var bgImage = String(cs.backgroundImage || "").trim().toLowerCase();
  if (bgImage && bgImage !== "none") {
    return true;
  }
  var boxShadow = String(cs.boxShadow || "").trim().toLowerCase();
  if (boxShadow && boxShadow !== "none") {
    return true;
  }
  if (_hasVisibleBorder(cs)) {
    return true;
  }
  var outlineWidth = Number(parseFloat(String(cs.outlineWidth || "0")));
  if (isFinite(outlineWidth) && outlineWidth > 0.0001 && _hasVisibleColor(cs.outlineColor)) {
    return true;
  }
  if (el.hasAttribute && (el.hasAttribute("data-ui-role") || el.hasAttribute("data-ui-key") || el.hasAttribute("data-ui-action"))) {
    return true;
  }
  return false;
}

function _collectVisibleSourceElementsForCurrentCanvas() {
  var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
  if (!doc || !doc.body || !doc.body.querySelectorAll || !doc.defaultView || !doc.defaultView.getComputedStyle) {
    return [];
  }
  var viewportWidth = Number(doc.documentElement ? (doc.documentElement.clientWidth || 0) : 0);
  var viewportHeight = Number(doc.documentElement ? (doc.documentElement.clientHeight || 0) : 0);
  var nodeList = doc.body.querySelectorAll("*");
  var out = [];
  for (var i = 0; i < nodeList.length; i++) {
    var el = nodeList[i];
    if (!el || !el.style || !el.getBoundingClientRect) continue;
    var cs = doc.defaultView.getComputedStyle(el);
    if (!cs) continue;
    if (String(cs.display || "") === "none") continue;
    if (String(cs.visibility || "") === "hidden") continue;
    var opacityValue = Number(cs.opacity);
    if (isFinite(opacityValue) && opacityValue <= 0.0001) continue;
    var rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) continue;
    if (viewportWidth > 0 && viewportHeight > 0) {
      if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= viewportWidth || rect.top >= viewportHeight) {
        continue;
      }
    }
    if (!_isSourceTimelapseRevealCandidate(el, cs)) continue;
    out.push({
      el: el,
      display: String(el.style.display || ""),
    });
  }
  // 关键：不要只保留最外层候选。
  // 原稿有大量“父容器 + 子组件（flex item）”同时可见的结构，
  // 若只播放父容器会出现“整块一起出现”，看不到逐个组件重排。
  return out;
}

async function _playFlattenedInitialVisibleTimelapse() {
  if (_isFlattenedTimelapseRunning) return;
  if (!state.selected || !String((state.selected && state.selected.source_html) || "").trim()) {
    setStatusText("延时摄影：请先选择一个可预览的 UI 源码文件。");
    return;
  }
  _isFlattenedTimelapseRunning = true;
  _setFlattenedTimelapseButtonRunning(true);
  var revealItems = [];
  try {
    if (state.currentVariant !== PREVIEW_VARIANT_FLATTENED) {
      state.currentVariant = PREVIEW_VARIANT_FLATTENED;
      updateVariantButtons();
      await renderPreview();
      setStatusText("预览：扁平化");
    }
    if (flattenGroupTreeController && flattenGroupTreeController.indexFlattenedPreviewElements) {
      flattenGroupTreeController.indexFlattenedPreviewElements();
    }
    revealItems = _collectVisibleFlattenedElementsForCurrentCanvas();
    if (!revealItems || revealItems.length <= 0) {
      setStatusText("延时摄影：当前画面没有可播放的扁平可见层。");
      return;
    }

    setStatusText("延时摄影：准备播放（" + String(revealItems.length) + " 层）…");
    for (var hideIndex = 0; hideIndex < revealItems.length; hideIndex++) {
      var hideItem = revealItems[hideIndex];
      if (!hideItem || !hideItem.el || !hideItem.el.style) continue;
      hideItem.el.style.visibility = "hidden";
    }

    for (var i = 0; i < revealItems.length; i++) {
      await _sleepMs(_FLATTENED_TIMELAPSE_STEP_MS);
      var item = revealItems[i];
      if (!item || !item.el || !item.el.style) continue;
      item.el.style.visibility = item.visibility;
    }
    setStatusText("延时摄影：播放完成（" + String(revealItems.length) + " 层）。");
  } catch (error) {
    for (var restoreIndex = 0; restoreIndex < revealItems.length; restoreIndex++) {
      var restoreItem = revealItems[restoreIndex];
      if (!restoreItem || !restoreItem.el || !restoreItem.el.style) continue;
      restoreItem.el.style.visibility = restoreItem.visibility;
    }
    var msg = error && error.message ? String(error.message) : String(error || "unknown error");
    setStatusText("延时摄影执行失败：" + msg);
  } finally {
    _isFlattenedTimelapseRunning = false;
    _setFlattenedTimelapseButtonRunning(false);
  }
}

async function _playSourceInitialVisibleTimelapse() {
  if (_isSourceTimelapseRunning || _isFlattenedTimelapseRunning) return;
  if (!state.selected || !String((state.selected && state.selected.source_html) || "").trim()) {
    setStatusText("延时摄影：请先选择一个可预览的 UI 源码文件。");
    return;
  }
  if (state.currentVariant !== PREVIEW_VARIANT_SOURCE) {
    setStatusText("延时摄影（原稿）：请先切换到“原稿”预览。");
    return;
  }
  var revealItems = _collectVisibleSourceElementsForCurrentCanvas();
  if (!revealItems || revealItems.length <= 0) {
    setStatusText("延时摄影（原稿）：当前画面没有可播放的可见元素。");
    return;
  }

  _isSourceTimelapseRunning = true;
  _setFlattenedTimelapseButtonRunning(true);
  setStatusText("延时摄影（原稿）：准备播放（" + String(revealItems.length) + " 层）…");
  return Promise.resolve().then(async function () {
    for (var hideIndex = 0; hideIndex < revealItems.length; hideIndex++) {
      var hideItem = revealItems[hideIndex];
      if (!hideItem || !hideItem.el || !hideItem.el.style) continue;
      hideItem.el.style.display = "none";
    }
    for (var i = 0; i < revealItems.length; i++) {
      await _sleepMs(_SOURCE_TIMELAPSE_STEP_MS);
      var item = revealItems[i];
      if (!item || !item.el || !item.el.style) continue;
      item.el.style.display = String(item.display || "");
    }
    setStatusText("延时摄影（原稿）：播放完成（" + String(revealItems.length) + " 层）。");
  }).finally(function () {
    _isSourceTimelapseRunning = false;
    _setFlattenedTimelapseButtonRunning(false);
  });
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
        // 点击“当前已选中的画布尺寸”应为幂等：避免重复渲染/重复生成 bundle 导致列表抖动与自动化不稳定。
        if (String(state.canvasSizeKey || "").trim() === k) {
          preview.setSelectedCanvasSize(k);
          return;
        }
        state.canvasSizeKey = k;
        preview.setSelectedCanvasSize(k);
        // 画布变更后：无需重绘 iframe（扁平化输出已包含 4 档尺寸；原稿模式只依赖 CSS 变量）。
        // 这里仅原地同步导出控件行的 flat_layer_key 映射（不重建列表 DOM），并保持蓝色选中框不闪断。
        await refreshExportWidgetModelForCurrentSelectionInPlace(false);
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
          if (state.exportWidgetPreviewModel && flattenGroupTreeController && flattenGroupTreeController.setGroupExcluded && flattenGroupTreeController.isGroupExcluded) {
            flattenGroupTreeController.setGroupExcluded(gk, !flattenGroupTreeController.isGroupExcluded(gk));
          }
          var details0 = toggle.closest ? toggle.closest("details") : null;
          _refreshExportWidgetListExcludeIconsInDetails(details0);
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
          var details1 = toggle.closest ? toggle.closest("details") : null;
          _refreshExportWidgetListVisibilityIconsInDetails(details1);
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
          var groupKey0 = row && row.dataset ? String(row.dataset.groupKey || "").trim() : "";
          var isExcluded0 = false;
          if (flattenGroupTreeController.isGroupExcluded && groupKey0 && flattenGroupTreeController.isGroupExcluded(groupKey0)) {
            isExcluded0 = true;
          } else if (flattenGroupTreeController.isLayerExcluded) {
            isExcluded0 = !!flattenGroupTreeController.isLayerExcluded(bestKey);
          }
          _syncTrashToggleButtonUi(toggle, isExcluded0);
        } else {
          if (flattenGroupTreeController.setLayerHidden && flattenGroupTreeController.isLayerHidden) {
            flattenGroupTreeController.setLayerHidden(bestKey, !flattenGroupTreeController.isLayerHidden(bestKey));
          }
          var isHidden0 = !!(flattenGroupTreeController.isLayerHidden && flattenGroupTreeController.isLayerHidden(bestKey));
          _syncEyeToggleButtonUi(toggle, isHidden0);
          var details2 = row && row.closest ? row.closest("details") : null;
          _refreshExportWidgetListVisibilityIconsInDetails(details2);
        }
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
    var uiKey = String(btn.dataset && btn.dataset.uiKey ? btn.dataset.uiKey : "").trim();
    if (!wid) return;
    if (!layerKey) {
      // 严格口径：缺少 flat_layer_key 则无法在画布中做确定性定位；必须明确拒绝而不是猜测。
      setExportStatusText(
        "[定位] 当前条目缺少 data-flat-layer-key（导出端未写入 __flat_layer_key/flat_layer_key），已拒绝定位。\n" +
        "- widget_id: " + String(wid || "") + (uiKey ? ("\n- ui_key: " + String(uiKey || "")) : "")
      );
      ev.preventDefault();
      ev.stopPropagation();
      return;
    }

    state.suppressNextExportWidgetAutoScroll = true;
    state.exportSelectedWidgetId = wid;
    updateExportWidgetListSelectionDom(wid);

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
        scheduleRerenderExportWidgetListFromCurrentModel();
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
      // Tab 切换后需要对“导出控件列表”做一次重绘：
      // - 应用共享 filter（leftBottomFilterText）
      // - 同步眼睛/垃圾桶图标状态（依赖 flattenGroupTreeController 当前隐藏/排除集合）
      // - 若存在 pendingScroll，则在 DOM 就绪后消费它
      scheduleRerenderExportWidgetListFromCurrentModel();
    });
  }
  if (dom.leftBottomTabFlattenGroupsButton) {
    dom.leftBottomTabFlattenGroupsButton.addEventListener("click", function () {
      setLeftBottomTabMode("flatten_groups");
    });
  }

  if (dom.refreshExportWidgetListButton) {
    dom.refreshExportWidgetListButton.addEventListener("click", async function () {
      await refreshExportWidgetListForCurrentSelectionIfNeeded(true);
    });
  }
  if (dom.refreshFlattenGroupTreeButton) {
    dom.refreshFlattenGroupTreeButton.addEventListener("click", async function () {
      if (!flattenGroupTreeController || !flattenGroupTreeController.refresh) return;
      setFlattenGroupTreeStatusText("生成中…");
      await flattenGroupTreeController.refresh();
    });
  }
  if (dom.resetFlattenGroupTreeVisibilityButton) {
    dom.resetFlattenGroupTreeVisibilityButton.addEventListener("click", function () {
      if (!flattenGroupTreeController || !flattenGroupTreeController.resetVisibilityToggles) return;
      flattenGroupTreeController.resetVisibilityToggles();
      // 共享“隐藏集合”：重置后导出控件列表也需要刷新图标状态（避免“图标还在隐藏态”的错觉）
      scheduleRerenderExportWidgetListFromCurrentModel();
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
  if (dom.flattenedTimelapseRevealButton) {
    dom.flattenedTimelapseRevealButton.addEventListener("click", function () {
      if (state.currentVariant === PREVIEW_VARIANT_SOURCE) {
        _playSourceInitialVisibleTimelapse();
        return;
      }
      _playFlattenedInitialVisibleTimelapse();
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

