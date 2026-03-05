import { dom } from "../../dom_refs.js";
import { rectIntersectionArea } from "../../geometry/rect_match.js";
import { createFlattenGroupTreeStore } from "./store.js";
import { createFlattenedPreviewDomIndex } from "./dom_index.js";
import { renderFlattenGroupTree } from "./render.js";
import { createFlattenGroupTreeEventHandlers } from "./events.js";
import {
  canFallbackToVisiblePreviewDocument,
  extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback,
} from "../compute_fallback.js";

export function createFlattenGroupTreeController(opts) {
  var o = opts || {};

  var preview = o.preview;
  var getHtmlText = o.getHtmlText;
  var waitForNextFrame = o.waitForNextFrame;
  var getCanvasSizeByKey = o.getCanvasSizeByKey;
  var extractDisplayElementsData = o.extractDisplayElementsData;
  var buildFlattenedLayerData = o.buildFlattenedLayerData;
  var enableVisibilityToggles = !!o.enable_visibility_toggles;
  var enableExportExcludeToggles = !!o.enable_export_exclude_toggles;

  var flattenGroupTreeContainerElement = dom.flattenGroupTreeContainerElement;
  var flattenGroupTreeStatusTextElement = dom.flattenGroupTreeStatusTextElement;

  var store = createFlattenGroupTreeStore();
  var domIndex = createFlattenedPreviewDomIndex({
    preview: preview,
    enableVisibilityToggles: enableVisibilityToggles,
  });

  function setUiKeyPrefix(prefix) {
    store.uiKeyPrefix = String(prefix || "");
  }

  function _resolveLayerKeyToIndexedDomKey(layerKey) {
    return domIndex.resolveLayerKeyToIndexedDomKey(layerKey);
  }

  function _deleteHiddenLayerKeyWithNormalization(layerKey) {
    var raw = String(layerKey || "");
    if (!raw) return;
    store.hiddenLayerKeySet.delete(raw);
    var normalized = _resolveLayerKeyToIndexedDomKey(raw);
    if (normalized && normalized !== raw) {
      store.hiddenLayerKeySet.delete(normalized);
    }
  }

  function _isLayerHidden(layerKey) {
    var lk = String(layerKey || "");
    if (!lk) return false;
    if (store.hiddenLayerKeySet.has(lk)) return true;
    var normalized = _resolveLayerKeyToIndexedDomKey(lk);
    if (normalized && normalized !== lk && store.hiddenLayerKeySet.has(normalized)) return true;
    return false;
  }

  function _isAllLayerKeysHidden(layerKeys) {
    var keys = Array.isArray(layerKeys) ? layerKeys : [];
    if (!keys || keys.length <= 0) return false;
    for (var i = 0; i < keys.length; i++) {
      var k = String(keys[i] || "");
      if (!k) return false;
      if (!_isLayerHidden(k)) return false;
    }
    return true;
  }

  function _normalizeHiddenLayerKeysToIndexedPreviewElements() {
    if (!enableVisibilityToggles) return;
    if (!store.hiddenLayerKeySet || store.hiddenLayerKeySet.size <= 0) return;
    if (!domIndex.elementByLayerKey || domIndex.elementByLayerKey.size <= 0) return;
    var normalized = new Set();
    store.hiddenLayerKeySet.forEach(function (rawKey) {
      var key = String(rawKey || "");
      if (!key) return;
      var el = domIndex.findPreviewElementByLayerKey(key);
      if (el && el.dataset && String(el.dataset.layerKey || "")) {
        normalized.add(String(el.dataset.layerKey || ""));
        return;
      }
      normalized.add(key);
    });
    store.hiddenLayerKeySet.clear();
    normalized.forEach(function (k) {
      store.hiddenLayerKeySet.add(k);
    });
  }

  function _applyHiddenStateToPreviewElements() {
    if (!enableVisibilityToggles) return;
    domIndex.forEachIndexedElement(function (el, layerKey) {
      if (!el || !el.style) return;
      el.style.display = _isLayerHidden(layerKey) ? "none" : "";
    });
  }

  function _setLayersHiddenInternal(layerKeys, hidden) {
    var keys = Array.isArray(layerKeys) ? layerKeys : [];
    for (var i = 0; i < keys.length; i++) {
      var k = String(keys[i] || "");
      if (!k) continue;
      if (hidden) {
        store.hiddenLayerKeySet.add(_resolveLayerKeyToIndexedDomKey(k));
      } else {
        _deleteHiddenLayerKeyWithNormalization(k);
      }
    }
  }

  function _getGroupLayerKeys(groupKey) {
    var gk = String(groupKey || "").trim();
    if (!gk) return [];
    var entries = store.layerEntriesByGroupKey.has(gk) ? store.layerEntriesByGroupKey.get(gk) : null;
    if (!entries || entries.length <= 0) return [];
    var out = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (!e || !e.layerKey) continue;
      out.push(String(e.layerKey || ""));
    }
    return out;
  }

  function _isLayerExcluded(layerKey) {
    var lk = String(layerKey || "");
    if (!lk) return false;
    if (store.excludedLayerKeySet.has(lk)) return true;
    var gk = store.groupKeyByLayerKey.has(lk) ? String(store.groupKeyByLayerKey.get(lk) || "") : "";
    if (gk && store.excludedGroupKeySet.has(gk)) return true;
    return false;
  }

  function indexFlattenedPreviewElements() {
    domIndex.indexFlattenedPreviewElements({
      groupKeyByLayerKey: store.groupKeyByLayerKey,
    });
    _normalizeHiddenLayerKeysToIndexedPreviewElements();
    _applyHiddenStateToPreviewElements();
  }

  function _toggleLayerExcluded(layerKey) {
    if (!enableExportExcludeToggles) return;
    var key = String(layerKey || "");
    if (!key) return;
    if (store.excludedLayerKeySet.has(key)) store.excludedLayerKeySet.delete(key);
    else store.excludedLayerKeySet.add(key);
  }

  function _toggleGroupExcluded(groupKey) {
    if (!enableExportExcludeToggles) return;
    var key = String(groupKey || "");
    if (!key) return;
    if (store.excludedGroupKeySet.has(key)) store.excludedGroupKeySet.delete(key);
    else store.excludedGroupKeySet.add(key);
  }

  function _toggleLayerHidden(layerKey) {
    if (!enableVisibilityToggles) return;
    indexFlattenedPreviewElements();
    var key = String(layerKey || "");
    if (!key) return;
    var domKey = _resolveLayerKeyToIndexedDomKey(key);
    if (store.hiddenLayerKeySet.has(domKey) || store.hiddenLayerKeySet.has(key)) {
      _deleteHiddenLayerKeyWithNormalization(key);
    } else {
      store.hiddenLayerKeySet.add(domKey);
    }
    if ((store.selectedLayerKey === key || store.selectedLayerKey === domKey) && _isLayerHidden(domKey)) {
      if (preview && preview.clearCurrentSelection) preview.clearCurrentSelection();
      _clearTreeSelectionHighlight();
    }
    _normalizeHiddenLayerKeysToIndexedPreviewElements();
    _applyHiddenStateToPreviewElements();
  }

  function _toggleGroupHidden(groupKey) {
    if (!enableVisibilityToggles) return;
    indexFlattenedPreviewElements();
    var key = String(groupKey || "").trim();
    if (!key) return;
    var keys = _getGroupLayerKeys(key);
    var wantHidden = !_isAllLayerKeysHidden(keys);
    _setLayersHiddenInternal(keys, wantHidden);
    if (store.selectedLayerKey && _isLayerHidden(store.selectedLayerKey)) {
      if (preview && preview.clearCurrentSelection) preview.clearCurrentSelection();
      _clearTreeSelectionHighlight();
    }
    _normalizeHiddenLayerKeysToIndexedPreviewElements();
    _applyHiddenStateToPreviewElements();
  }

  function resetVisibilityToggles() {
    if (!enableVisibilityToggles) return;
    store.hiddenLayerKeySet.clear();
    _applyHiddenStateToPreviewElements();
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function resetExportExcludeToggles() {
    if (!enableExportExcludeToggles) return;
    store.excludedLayerKeySet.clear();
    store.excludedGroupKeySet.clear();
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function isGroupHidden(groupKey) {
    if (!enableVisibilityToggles) return false;
    var key = String(groupKey || "").trim();
    if (!key) return false;
    return _isAllLayerKeysHidden(_getGroupLayerKeys(key));
  }

  function isLayerHidden(layerKey) {
    if (!enableVisibilityToggles) return false;
    return _isLayerHidden(layerKey);
  }

  function isGroupExcluded(groupKey) {
    if (!enableExportExcludeToggles) return false;
    var key = String(groupKey || "");
    if (!key) return false;
    return store.excludedGroupKeySet.has(key);
  }

  function isLayerExcluded(layerKey) {
    if (!enableExportExcludeToggles) return false;
    return _isLayerExcluded(layerKey);
  }

  function setGroupHidden(groupKey, hidden) {
    if (!enableVisibilityToggles) return;
    var key = String(groupKey || "").trim();
    if (!key) return;
    _setLayersHiddenInternal(_getGroupLayerKeys(key), !!hidden);
    if (store.selectedLayerKey && _isLayerHidden(store.selectedLayerKey)) {
      if (preview && preview.clearCurrentSelection) preview.clearCurrentSelection();
      _clearTreeSelectionHighlight();
    }
    _normalizeHiddenLayerKeysToIndexedPreviewElements();
    _applyHiddenStateToPreviewElements();
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function setLayerHidden(layerKey, hidden) {
    if (!enableVisibilityToggles) return;
    indexFlattenedPreviewElements();
    var key = String(layerKey || "");
    if (!key) return;
    var domKey = _resolveLayerKeyToIndexedDomKey(key);
    if (hidden) {
      store.hiddenLayerKeySet.add(domKey);
    } else {
      _deleteHiddenLayerKeyWithNormalization(key);
    }
    if ((store.selectedLayerKey === key || store.selectedLayerKey === domKey) && _isLayerHidden(domKey)) {
      if (preview && preview.clearCurrentSelection) preview.clearCurrentSelection();
      _clearTreeSelectionHighlight();
    }
    _normalizeHiddenLayerKeysToIndexedPreviewElements();
    _applyHiddenStateToPreviewElements();
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function setLayersHidden(layerKeys, hidden) {
    if (!enableVisibilityToggles) return;
    indexFlattenedPreviewElements();
    _setLayersHiddenInternal(layerKeys, !!hidden);
    if (store.selectedLayerKey && _isLayerHidden(store.selectedLayerKey)) {
      if (preview && preview.clearCurrentSelection) preview.clearCurrentSelection();
      _clearTreeSelectionHighlight();
    }
    _normalizeHiddenLayerKeysToIndexedPreviewElements();
    _applyHiddenStateToPreviewElements();
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function setGroupExcluded(groupKey, excluded) {
    if (!enableExportExcludeToggles) return;
    var key = String(groupKey || "");
    if (!key) return;
    if (excluded) store.excludedGroupKeySet.add(key);
    else store.excludedGroupKeySet.delete(key);
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function setLayerExcluded(layerKey, excluded) {
    if (!enableExportExcludeToggles) return;
    var key = String(layerKey || "");
    if (!key) return;
    if (excluded) store.excludedLayerKeySet.add(key);
    else store.excludedLayerKeySet.delete(key);
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function setLayersExcluded(layerKeys, excluded) {
    if (!enableExportExcludeToggles) return;
    var keys = Array.isArray(layerKeys) ? layerKeys : [];
    for (var i = 0; i < keys.length; i++) {
      var k = String(keys[i] || "");
      if (!k) continue;
      if (excluded) store.excludedLayerKeySet.add(k);
      else store.excludedLayerKeySet.delete(k);
    }
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function getLayerKeysForGroupRect(groupKey, rect) {
    var gk = String(groupKey || "").trim();
    if (!gk) return [];
    var entries = store.layerEntriesByGroupKey.has(gk) ? store.layerEntriesByGroupKey.get(gk) : null;
    if (!entries || entries.length <= 0) return [];
    var r = rect || null;
    if (!r) return entries.map(function (x) { return x.layerKey; });
    var out = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (!e || !e.layerKey || !e.rect) continue;
      if (rectIntersectionArea(e.rect, r) > 0) {
        out.push(String(e.layerKey || ""));
      }
    }
    return out;
  }

  function findPreviewElementByLayerKey(layerKey) {
    return domIndex.findPreviewElementByLayerKey(layerKey);
  }

  function _clearTreeSelectionHighlight() {
    if (!flattenGroupTreeContainerElement) return;
    var prevKey = String(store.selectedLayerKey || "");
    if (prevKey) {
      var prev = null;
      var nodes = flattenGroupTreeContainerElement.querySelectorAll("[data-layer-key]");
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (!n || !n.getAttribute) continue;
        if (String(n.getAttribute("data-layer-key") || "") === prevKey) {
          prev = n;
          break;
        }
      }
      if (prev && prev.classList) {
        prev.classList.remove("selected");
      }
    }
    store.selectedLayerKey = "";
  }

  function _clearGroupSelectionHighlight() {
    if (!flattenGroupTreeContainerElement) return;
    var prev = String(store.selectedGroupKey || "");
    if (!prev) return;
    var node = flattenGroupTreeContainerElement.querySelector('details[data-group-key="' + prev + '"]');
    if (node && node.classList) {
      node.classList.remove("wb-tree-group-selected");
    }
    store.selectedGroupKey = "";
  }

  function _highlightTreeGroupByGroupKey(groupKey) {
    if (!flattenGroupTreeContainerElement) return;
    var gk = String(groupKey || "").trim();
    if (!gk) {
      _clearGroupSelectionHighlight();
      return;
    }
    if (store.selectedGroupKey === gk) return;
    _clearGroupSelectionHighlight();
    var node = flattenGroupTreeContainerElement.querySelector('details[data-group-key="' + gk + '"]');
    if (!node) return;
    if (node.classList) node.classList.add("wb-tree-group-selected");
    store.selectedGroupKey = gk;
  }

  function _isElementEffectivelyHidden(el) {
    var node = el || null;
    if (!node) return true;
    if (node.style) {
      if (String(node.style.display || "") === "none") return true;
      if (String(node.style.visibility || "") === "hidden") return true;
    }
    var doc = node.ownerDocument || null;
    var win = doc && doc.defaultView ? doc.defaultView : null;
    if (win && win.getComputedStyle) {
      var cs = win.getComputedStyle(node);
      if (cs) {
        if (String(cs.display || "") === "none") return true;
        if (String(cs.visibility || "") === "hidden") return true;
      }
    }
    return false;
  }

  function _highlightTreeItemByLayerKey(layerKey, opts2) {
    if (!flattenGroupTreeContainerElement) return;
    var options = opts2 || {};
    var shouldScrollIntoView = options.scroll_into_view === true;
    var key = String(layerKey || "");
    if (!key) {
      _clearTreeSelectionHighlight();
      return;
    }
    if (store.selectedLayerKey === key) return;
    _clearTreeSelectionHighlight();
    var node = null;
    var nodes = flattenGroupTreeContainerElement.querySelectorAll("[data-layer-key]");
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!n || !n.getAttribute) continue;
      if (String(n.getAttribute("data-layer-key") || "") === key) {
        node = n;
        break;
      }
    }
    if (!node) return;
    if (node.classList) node.classList.add("selected");
    store.selectedLayerKey = key;
    _clearGroupSelectionHighlight();

    var parent = node.parentElement;
    while (parent) {
      if (parent.tagName && String(parent.tagName).toLowerCase() === "details") {
        parent.open = true;
        break;
      }
      parent = parent.parentElement;
    }
    // 关键：当树容器不可见（例如在 ui_app_ui_preview 中当前处于“导出控件”Tab），
    // 避免 scrollIntoView() 造成外层滚动容器抖动，从而影响其它列表的点击稳定性。
    if (shouldScrollIntoView && !_isElementEffectivelyHidden(flattenGroupTreeContainerElement) && node.scrollIntoView) {
      node.scrollIntoView({ block: "center" });
    }
  }

  function scrollSelectionIntoView() {
    if (!flattenGroupTreeContainerElement) return;
    if (_isElementEffectivelyHidden(flattenGroupTreeContainerElement)) return;
    var key = String(store.selectedLayerKey || "");
    if (!key) return;
    var node = flattenGroupTreeContainerElement.querySelector('[data-layer-key="' + key + '"]');
    if (!node) return;
    var prevSelected = flattenGroupTreeContainerElement.querySelectorAll(".wb-tree-item.selected");
    for (var i = 0; i < prevSelected.length; i++) {
      var p0 = prevSelected[i];
      if (p0 && p0.classList) p0.classList.remove("selected");
    }
    if (node.classList) node.classList.add("selected");
    var parent = node.parentElement;
    while (parent) {
      if (parent.tagName && String(parent.tagName).toLowerCase() === "details") {
        parent.open = true;
        break;
      }
      parent = parent.parentElement;
    }
    if (node.scrollIntoView) node.scrollIntoView({ block: "center" });
  }

  function ensureExpandedStateFromDom(target) {
    var details = target && target.closest ? target.closest("details") : null;
    if (!details) return;
    var gk = details.dataset ? String(details.dataset.groupKey || "") : "";
    var isUngrouped = !gk;
    var willOpen = !details.open;
    details.open = willOpen;
    if (isUngrouped) {
      store.expandedUngrouped = willOpen;
      return;
    }
    if (willOpen) store.expandedGroupKeySet.add(gk);
    else store.expandedGroupKeySet.delete(gk);
  }

  function _renderFlattenGroupTree(layerList, canvasSizeKey) {
    renderFlattenGroupTree({
      store: store,
      layerList: layerList,
      canvasSizeKey: canvasSizeKey,
      containerElement: flattenGroupTreeContainerElement,
      statusTextElement: flattenGroupTreeStatusTextElement,
      enableVisibilityToggles: enableVisibilityToggles,
      enableExportExcludeToggles: enableExportExcludeToggles,
      isGroupHidden: isGroupHidden,
      isLayerHidden: isLayerHidden,
      isLayerExcluded: isLayerExcluded,
    });
  }

  function rerenderFromLastLayerList() {
    if (!store.lastLayerList) return;
    _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
    indexFlattenedPreviewElements();
  }

  async function refresh() {
    if (!getHtmlText) return;
    var htmlText = String(getHtmlText() || "");
    if (!String(htmlText || "").trim()) {
      if (flattenGroupTreeContainerElement) flattenGroupTreeContainerElement.innerHTML = "";
      if (flattenGroupTreeStatusTextElement) flattenGroupTreeStatusTextElement.textContent = "空输入";
      return;
    }

    var isComputeReady = preview && preview.ensureComputePreviewIsReadyForHtml ? await preview.ensureComputePreviewIsReadyForHtml(htmlText) : false;
    if (!isComputeReady) {
      if (flattenGroupTreeStatusTextElement) {
        flattenGroupTreeStatusTextElement.textContent = "计算预览未就绪（compute 文档为空）";
      }
      return;
    }

    var selectedCanvasSizeKey = preview && preview.getCurrentSelectedCanvasSizeKey ? preview.getCurrentSelectedCanvasSizeKey() : "";
    var selectedCanvasSizeOption = getCanvasSizeByKey ? getCanvasSizeByKey(selectedCanvasSizeKey) : null;

    if (preview && preview.updatePreviewStageScale) {
      preview.updatePreviewStageScale(selectedCanvasSizeOption);
    }
    if (preview && preview.getPreviewDocument && preview.applyCanvasSizeToPreviewDocument) {
      var visibleDoc = preview.getPreviewDocument();
      if (visibleDoc) {
        preview.applyCanvasSizeToPreviewDocument(visibleDoc, selectedCanvasSizeOption);
      }
    }

    var computeDoc = preview && preview.getComputePreviewDocument ? preview.getComputePreviewDocument() : null;
    if (!computeDoc || !computeDoc.body) {
      if (flattenGroupTreeStatusTextElement) flattenGroupTreeStatusTextElement.textContent = "计算预览为空（请刷新页面重试）";
      _renderFlattenGroupTree([], selectedCanvasSizeKey);
      indexFlattenedPreviewElements();
      return;
    }

    function _applyCanvasSizeToComputeDocStable() {
      if (preview && preview.setComputePreviewCanvasSize) {
        preview.setComputePreviewCanvasSize(selectedCanvasSizeOption);
      }
      if (preview && preview.applyCanvasSizeToPreviewDocument) {
        preview.applyCanvasSizeToPreviewDocument(computeDoc, selectedCanvasSizeOption);
      }
    }

    async function _ensureComputeDocStableOrNull() {
      computeDoc = preview && preview.getComputePreviewDocument ? preview.getComputePreviewDocument() : null;
      if (!computeDoc || !computeDoc.body) return null;
      _applyCanvasSizeToComputeDocStable();
      if (waitForNextFrame) {
        await waitForNextFrame();
        await waitForNextFrame();
      }
      var currentDoc = preview && preview.getComputePreviewDocument ? preview.getComputePreviewDocument() : null;
      if (currentDoc && currentDoc !== computeDoc) {
        computeDoc = currentDoc;
        if (!computeDoc || !computeDoc.body) return null;
        _applyCanvasSizeToComputeDocStable();
        if (waitForNextFrame) {
          await waitForNextFrame();
          await waitForNextFrame();
        }
      }
      if (computeDoc && computeDoc.body) {
        computeDoc.body.getBoundingClientRect();
        void computeDoc.body.offsetHeight;
      }
      return computeDoc;
    }

    var didHardResetCompute = false;
    var stableComputeDoc = await _ensureComputeDocStableOrNull();
    if (!stableComputeDoc) {
      if (flattenGroupTreeStatusTextElement) flattenGroupTreeStatusTextElement.textContent = "计算预览为空（请刷新页面重试）";
      _renderFlattenGroupTree([], selectedCanvasSizeKey);
      indexFlattenedPreviewElements();
      return;
    }

    var elementsData = extractDisplayElementsData ? extractDisplayElementsData(stableComputeDoc) : null;
    if (!elementsData || !elementsData.elements || elementsData.elements.length <= 0) {
      if (waitForNextFrame) {
        await waitForNextFrame();
        await waitForNextFrame();
        await waitForNextFrame();
        await waitForNextFrame();
      }
      stableComputeDoc = await _ensureComputeDocStableOrNull();
      if (stableComputeDoc && extractDisplayElementsData) {
        elementsData = extractDisplayElementsData(stableComputeDoc);
      }
    }

    if ((!elementsData || !elementsData.elements || elementsData.elements.length <= 0) && !didHardResetCompute && preview && preview.resetComputePreviewHard) {
      var diag0 = elementsData && elementsData.diagnostics ? elementsData.diagnostics : null;
      var bodyW0 = diag0 && diag0.bodyRect ? Number(diag0.bodyRect.width || 0) : 0;
      var bodyH0 = diag0 && diag0.bodyRect ? Number(diag0.bodyRect.height || 0) : 0;
      var hasView0 = !!(stableComputeDoc && stableComputeDoc.defaultView && stableComputeDoc.defaultView.getComputedStyle);
      var shouldHardReset = (!hasView0) || (bodyW0 <= 1) || (bodyH0 <= 1);
      if (shouldHardReset) {
        didHardResetCompute = true;
        preview.resetComputePreviewHard();
        var ready2 = preview.ensureComputePreviewIsReadyForHtml ? await preview.ensureComputePreviewIsReadyForHtml(htmlText) : false;
        if (ready2) {
          stableComputeDoc = await _ensureComputeDocStableOrNull();
          if (stableComputeDoc && extractDisplayElementsData) {
            elementsData = extractDisplayElementsData(stableComputeDoc);
          }
        }
      }
    }

    var allowFallbackToPreviewDoc = canFallbackToVisiblePreviewDocument(preview, selectedCanvasSizeKey);
    var previewDocForFallback = (allowFallbackToPreviewDoc && preview && preview.getPreviewDocument) ? preview.getPreviewDocument() : null;
    var r0 = await extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback({
      extractDisplayElementsData: extractDisplayElementsData,
      computeDoc: stableComputeDoc,
      initialComputeElementsData: elementsData,
      previewDoc: previewDocForFallback,
      allowFallback: allowFallbackToPreviewDoc,
    });
    elementsData = r0.elementsData;

    var layerList = buildFlattenedLayerData ? buildFlattenedLayerData(elementsData, {
      debug_show_all_controls: !!(dom.flattenDebugShowAllCheckboxElement && dom.flattenDebugShowAllCheckboxElement.checked),
    }) : [];

    store.lastLayerList = layerList;
    store.lastCanvasSizeKey = selectedCanvasSizeKey;
    _renderFlattenGroupTree(layerList, selectedCanvasSizeKey);
    indexFlattenedPreviewElements();
  }

  var eventHandlers = createFlattenGroupTreeEventHandlers({
    store: store,
    preview: preview,
    domIndex: domIndex,
    containerElement: flattenGroupTreeContainerElement,
    enableVisibilityToggles: enableVisibilityToggles,
    enableExportExcludeToggles: enableExportExcludeToggles,
    ensureExpandedStateFromDom: ensureExpandedStateFromDom,
    indexFlattenedPreviewElements: indexFlattenedPreviewElements,
    rerenderFromLastLayerList: rerenderFromLastLayerList,
    toggleGroupExcluded: _toggleGroupExcluded,
    toggleLayerExcluded: _toggleLayerExcluded,
    toggleGroupHidden: _toggleGroupHidden,
    toggleLayerHidden: _toggleLayerHidden,
    isLayerHidden: isLayerHidden,
    highlightTreeGroupByGroupKey: _highlightTreeGroupByGroupKey,
    highlightTreeItemByLayerKey: _highlightTreeItemByLayerKey,
    clearTreeSelectionHighlight: _clearTreeSelectionHighlight,
  });

  async function handleTreeClick(event, opts2) {
    if (!eventHandlers || typeof eventHandlers.handleTreeClick !== "function") return;
    return await eventHandlers.handleTreeClick(event, opts2);
  }

  function handlePreviewSelectionChanged(payload) {
    if (!eventHandlers || typeof eventHandlers.handlePreviewSelectionChanged !== "function") return;
    eventHandlers.handlePreviewSelectionChanged(payload);
  }

  function setFilterText(text) {
    store.treeFilterText = String(text || "").trim();
    if (store.lastLayerList) {
      _renderFlattenGroupTree(store.lastLayerList, store.lastCanvasSizeKey);
      indexFlattenedPreviewElements();
    }
  }

  function getGroupDisplayName(groupKey) {
    var gk = String(groupKey || "").trim();
    if (!gk) return "";
    return store.groupDisplayNameByKey.has(gk) ? String(store.groupDisplayNameByKey.get(gk) || "") : "";
  }

  return {
    setUiKeyPrefix: setUiKeyPrefix,
    refresh: refresh,
    handleTreeClick: handleTreeClick,
    handlePreviewSelectionChanged: handlePreviewSelectionChanged,
    indexFlattenedPreviewElements: indexFlattenedPreviewElements,
    findPreviewElementByLayerKey: findPreviewElementByLayerKey,
    resetVisibilityToggles: resetVisibilityToggles,
    resetExportExcludeToggles: resetExportExcludeToggles,
    isGroupHidden: isGroupHidden,
    isLayerHidden: isLayerHidden,
    setGroupHidden: setGroupHidden,
    setLayerHidden: setLayerHidden,
    setLayersHidden: setLayersHidden,
    isGroupExcluded: isGroupExcluded,
    isLayerExcluded: isLayerExcluded,
    setGroupExcluded: setGroupExcluded,
    setLayerExcluded: setLayerExcluded,
    setLayersExcluded: setLayersExcluded,
    getLayerKeysForGroupRect: getLayerKeysForGroupRect,
    setFilterText: setFilterText,
    getGroupDisplayName: getGroupDisplayName,
    scrollSelectionIntoView: scrollSelectionIntoView,
  };
}

