import { buildLayerKey, parseLayerKey } from "../../layer_key.js";

function _buildLayerKeyFromLayer(layer) {
  if (!layer || !layer.rect) return "";
  return buildLayerKey(
    layer.kind,
    layer.rect.left,
    layer.rect.top,
    layer.rect.width,
    layer.rect.height,
    layer.z
  );
}

export function createFlattenGroupTreeEventHandlers(ctx) {
  var c = ctx || {};
  var store = c.store;
  var preview = c.preview;
  var domIndex = c.domIndex;
  var containerElement = c.containerElement;

  var enableVisibilityToggles = !!c.enableVisibilityToggles;
  var enableExportExcludeToggles = !!c.enableExportExcludeToggles;

  function handleTreeClick(event, opts) {
    var options = opts || {};
    var ensureFlattened = options.ensureFlattened;
    var previewVariant = options.previewVariant;
    var previewVariantFlattened = options.previewVariantFlattened;

    var target = event && event.target ? event.target : null;
    if (!target) return;

    // explicit expander: keep expanded state stable across re-render
    var expander = target.closest ? target.closest(".wb-tree-expander[data-expander]") : null;
    if (expander) {
      if (typeof c.ensureExpandedStateFromDom === "function") {
        c.ensureExpandedStateFromDom(expander);
      }
      if (event && event.preventDefault) event.preventDefault();
      if (event && event.stopPropagation) event.stopPropagation();
      return;
    }

    var toggleNode = target.closest ? target.closest(".wb-tree-toggle[data-toggle-kind]") : null;
    if (toggleNode && toggleNode.dataset) {
      var toggleAction = String(toggleNode.dataset.toggleAction || "hide");
      var toggleKind = String(toggleNode.dataset.toggleKind || "");

      if (toggleAction === "exclude") {
        if (ensureFlattened) {
          if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
            return ensureFlattened().then(function () {
              return handleTreeClick(event, opts);
            });
          }
        }
        if (toggleKind === "group") {
          var gkEx = String(toggleNode.dataset.groupKey || "");
          if (typeof c.toggleGroupExcluded === "function") c.toggleGroupExcluded(gkEx);
        } else if (toggleKind === "layer") {
          var lkEx = String(toggleNode.dataset.layerKey || "");
          if (typeof c.toggleLayerExcluded === "function") c.toggleLayerExcluded(lkEx);
        }
        if (typeof c.rerenderFromLastLayerList === "function") c.rerenderFromLastLayerList();
        if (event && event.preventDefault) event.preventDefault();
        if (event && event.stopPropagation) event.stopPropagation();
        return;
      }

      if (enableVisibilityToggles) {
        if (ensureFlattened) {
          if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
            return ensureFlattened().then(function () {
              return handleTreeClick(event, opts);
            });
          }
        }
        if (toggleKind === "group") {
          var gk = String(toggleNode.dataset.groupKey || "");
          if (typeof c.toggleGroupHidden === "function") c.toggleGroupHidden(gk);
          if (typeof c.rerenderFromLastLayerList === "function") c.rerenderFromLastLayerList();
        } else if (toggleKind === "layer") {
          var lk = String(toggleNode.dataset.layerKey || "");
          if (typeof c.toggleLayerHidden === "function") c.toggleLayerHidden(lk);
          if (typeof c.rerenderFromLastLayerList === "function") c.rerenderFromLastLayerList();
        }
        if (event && event.preventDefault) event.preventDefault();
        if (event && event.stopPropagation) event.stopPropagation();
        return;
      }
    }

    // group selection: click summary (excluding toggles/expander)
    var summary = target.closest ? target.closest("summary") : null;
    if (summary) {
      var detailsNode = summary.parentElement;
      if (detailsNode && detailsNode.dataset) {
        var gkSel = String(detailsNode.dataset.groupKey || "").trim();
        if (gkSel) {
          if (ensureFlattened) {
            if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
              return ensureFlattened().then(function () {
                return handleTreeClick(event, opts);
              });
            }
          }
          if (typeof c.indexFlattenedPreviewElements === "function") c.indexFlattenedPreviewElements();
          var entries = store && store.layerEntriesByGroupKey && store.layerEntriesByGroupKey.has(gkSel) ? store.layerEntriesByGroupKey.get(gkSel) : null;
          var picked = null;
          if (entries && entries.length > 0) {
            for (var i = 0; i < entries.length; i++) {
              var lk0 = String(entries[i].layerKey || "");
              if (!lk0) continue;
              if (enableVisibilityToggles && typeof c.isLayerHidden === "function" && c.isLayerHidden(lk0)) continue;
              picked = lk0;
              break;
            }
            if (!picked) {
              picked = String(entries[0].layerKey || "");
            }
          }
          if (picked) {
            var el0 = domIndex && typeof domIndex.findPreviewElementByLayerKey === "function" ? domIndex.findPreviewElementByLayerKey(picked) : null;
            if (el0 && preview && preview.selectPreviewElement) {
              preview.selectPreviewElement(el0);
              if (typeof c.highlightTreeGroupByGroupKey === "function") c.highlightTreeGroupByGroupKey(gkSel);
              if (typeof c.highlightTreeItemByLayerKey === "function") c.highlightTreeItemByLayerKey(picked, { scroll_into_view: false });
            }
          } else {
            if (typeof c.highlightTreeGroupByGroupKey === "function") c.highlightTreeGroupByGroupKey(gkSel);
          }
          if (event && event.preventDefault) event.preventDefault();
          if (event && event.stopPropagation) event.stopPropagation();
          return;
        }
      }
    }

    var node = target.closest ? target.closest(".wb-tree-item[data-layer-key]") : null;
    if (!node) return;
    var key = node.dataset ? String(node.dataset.layerKey || "") : "";
    if (!key) return;

    if (ensureFlattened) {
      if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
        return ensureFlattened().then(function () {
          return handleTreeClick(event, opts);
        });
      }
    }

    if (typeof c.indexFlattenedPreviewElements === "function") c.indexFlattenedPreviewElements();
    var el = domIndex && typeof domIndex.findPreviewElementByLayerKey === "function" ? domIndex.findPreviewElementByLayerKey(key) : null;
    if (!el) return;
    if (preview && preview.selectPreviewElement) preview.selectPreviewElement(el);
    if (typeof c.highlightTreeItemByLayerKey === "function") c.highlightTreeItemByLayerKey(key, { scroll_into_view: false });
  }

  function handlePreviewSelectionChanged(payload) {
    var p = payload || {};
    var kind = String(p.kind || "");
    if (kind !== "element") {
      if (typeof c.clearTreeSelectionHighlight === "function") c.clearTreeSelectionHighlight();
      return;
    }
    var el = p.element || null;
    if (!el) {
      if (typeof c.clearTreeSelectionHighlight === "function") c.clearTreeSelectionHighlight();
      return;
    }

    var key = el.dataset && el.dataset.layerKey ? String(el.dataset.layerKey || "") : "";
    if (!key && domIndex && typeof domIndex.buildLayerKeyFromDomElement === "function") {
      key = domIndex.buildLayerKeyFromDomElement(el);
    }
    if (!key) {
      if (typeof c.clearTreeSelectionHighlight === "function") c.clearTreeSelectionHighlight();
      return;
    }

    function _findTreeNodeByLayerKeySafe(lk) {
      if (!containerElement) return null;
      var k = String(lk || "");
      if (!k) return null;
      var ns = containerElement.querySelectorAll("[data-layer-key]");
      for (var i = 0; i < ns.length; i++) {
        var n = ns[i];
        if (!n || !n.getAttribute) continue;
        if (String(n.getAttribute("data-layer-key") || "") === k) return n;
      }
      return null;
    }

    function _pickNearestTreeKeyByRect(snap, requireSameKind) {
      if (!containerElement || !snap) return "";
      var nodes = containerElement.querySelectorAll(".wb-tree-item[data-layer-key]");
      if (!nodes || nodes.length <= 0) return "";
      var bestKey = "";
      var bestMetric = Number.POSITIVE_INFINITY;
      for (var ni = 0; ni < nodes.length; ni++) {
        var n = nodes[ni];
        if (!n || !n.dataset) continue;
        var lk2 = String(n.dataset.layerKey || "");
        if (!lk2) continue;
        var parsed2 = parseLayerKey(lk2);
        if (!parsed2) continue;
        if (requireSameKind && String(parsed2.kind || "") !== String(snap.kind || "")) continue;
        var dx = Math.abs(Number(parsed2.left || 0) - Number(snap.left || 0));
        var dy = Math.abs(Number(parsed2.top || 0) - Number(snap.top || 0));
        var dw = Math.abs(Number(parsed2.width || 0) - Number(snap.width || 0));
        var dh = Math.abs(Number(parsed2.height || 0) - Number(snap.height || 0));
        var z0 = Number(snap.z || 0);
        var z1 = Number(parsed2.z || 0);
        if (!isFinite(z0)) z0 = 0;
        if (!isFinite(z1)) z1 = 0;
        var dz = Math.abs(z1 - z0);
        var metric = dx + dy + dw + dh + dz * 0.01;
        if (metric < bestMetric) {
          bestMetric = metric;
          bestKey = lk2;
        }
      }
      return String(bestKey || "").trim();
    }

    function _normalizeDebugLabelBase(raw) {
      var s = String(raw || "").trim();
      if (!s) return "";
      var i = s.indexOf("__r");
      if (i > 0) {
        s = s.slice(0, i);
      }
      return s;
    }

    function _pickNearestTreeKeyByRectWithDebugLabel(snap, requireSameKind, debugLabelBase) {
      if (!containerElement || !snap) return "";
      var dbg = String(debugLabelBase || "").trim();
      if (!dbg) return "";
      var nodes = containerElement.querySelectorAll(".wb-tree-item[data-layer-key]");
      if (!nodes || nodes.length <= 0) return "";
      var bestKey = "";
      var bestMetric = Number.POSITIVE_INFINITY;
      for (var ni = 0; ni < nodes.length; ni++) {
        var n = nodes[ni];
        if (!n || !n.dataset) continue;
        var text = String(n.textContent || "");
        if (text.indexOf(dbg) < 0) continue;
        var lk2 = String(n.dataset.layerKey || "");
        if (!lk2) continue;
        var parsed2 = parseLayerKey(lk2);
        if (!parsed2) continue;
        if (requireSameKind && String(parsed2.kind || "") !== String(snap.kind || "")) continue;
        var dx = Math.abs(Number(parsed2.left || 0) - Number(snap.left || 0));
        var dy = Math.abs(Number(parsed2.top || 0) - Number(snap.top || 0));
        var dw = Math.abs(Number(parsed2.width || 0) - Number(snap.width || 0));
        var dh = Math.abs(Number(parsed2.height || 0) - Number(snap.height || 0));
        var z0 = Number(snap.z || 0);
        var z1 = Number(parsed2.z || 0);
        if (!isFinite(z0)) z0 = 0;
        if (!isFinite(z1)) z1 = 0;
        var dz = Math.abs(z1 - z0);
        var metric = dx + dy + dw + dh + dz * 0.01;
        if (metric < bestMetric) {
          bestMetric = metric;
          bestKey = lk2;
        }
      }
      return String(bestKey || "").trim();
    }

    function _pickNearestTreeKeyByRectWithDebugLabelAndText(snap, requireSameKind, debugLabelBase, textNeedle) {
      if (!containerElement || !snap) return "";
      var dbg = String(debugLabelBase || "").trim();
      if (!dbg) return "";
      var needle = String(textNeedle || "").trim();
      if (!needle) return "";
      if (needle.length > 64) needle = needle.slice(0, 64);
      var nodes = containerElement.querySelectorAll(".wb-tree-item[data-layer-key]");
      if (!nodes || nodes.length <= 0) return "";
      var bestKey = "";
      var bestMetric = Number.POSITIVE_INFINITY;
      for (var ni = 0; ni < nodes.length; ni++) {
        var n = nodes[ni];
        if (!n || !n.dataset) continue;
        var text = String(n.textContent || "");
        if (text.indexOf(dbg) < 0) continue;
        if (text.indexOf(needle) < 0) continue;
        var lk2 = String(n.dataset.layerKey || "");
        if (!lk2) continue;
        var parsed2 = parseLayerKey(lk2);
        if (!parsed2) continue;
        if (requireSameKind && String(parsed2.kind || "") !== String(snap.kind || "")) continue;
        var dx = Math.abs(Number(parsed2.left || 0) - Number(snap.left || 0));
        var dy = Math.abs(Number(parsed2.top || 0) - Number(snap.top || 0));
        var dw = Math.abs(Number(parsed2.width || 0) - Number(snap.width || 0));
        var dh = Math.abs(Number(parsed2.height || 0) - Number(snap.height || 0));
        var z0 = Number(snap.z || 0);
        var z1 = Number(parsed2.z || 0);
        if (!isFinite(z0)) z0 = 0;
        if (!isFinite(z1)) z1 = 0;
        var dz = Math.abs(z1 - z0);
        var metric = dx + dy + dw + dh + dz * 0.01;
        if (metric < bestMetric) {
          bestMetric = metric;
          bestKey = lk2;
        }
      }
      return String(bestKey || "").trim();
    }

    // tolerant mapping: preview layerKey -> tree row key
    if (containerElement) {
      var directNode = _findTreeNodeByLayerKeySafe(key);
      if (!directNode) {
        var snap = domIndex && typeof domIndex.getDomLayerSnapshotForMatch === "function" ? domIndex.getDomLayerSnapshotForMatch(el) : null;
        if (snap && store && Array.isArray(store.lastLayerList) && store.lastLayerList.length > 0) {
          var eps = 0.6;
          var bestKey0 = "";
          var bestMetric0 = Number.POSITIVE_INFINITY;
          for (var i = 0; i < store.lastLayerList.length; i++) {
            var layer = store.lastLayerList[i];
            if (!layer || !layer.rect) continue;
            var lkKind = String(layer.kind || "");
            if (lkKind !== String(snap.kind || "")) continue;
            var r = layer.rect;
            if (Math.abs(Number(r.left || 0) - Number(snap.left || 0)) > eps) continue;
            if (Math.abs(Number(r.top || 0) - Number(snap.top || 0)) > eps) continue;
            if (Math.abs(Number(r.width || 0) - Number(snap.width || 0)) > eps) continue;
            if (Math.abs(Number(r.height || 0) - Number(snap.height || 0)) > eps) continue;
            var z0 = Number(snap.z || 0);
            var z1 = Number(layer.z || 0);
            if (!isFinite(z0)) z0 = 0;
            if (!isFinite(z1)) z1 = 0;
            var dz = Math.abs(z1 - z0);
            if (dz < bestMetric0) {
              bestMetric0 = dz;
              bestKey0 = _buildLayerKeyFromLayer(layer);
            }
          }
          if (bestKey0) {
            key = bestKey0;
          }
        }

        var stillMissing = _findTreeNodeByLayerKeySafe(key);
        if (!stillMissing) {
          var snap2 = domIndex && typeof domIndex.getDomLayerSnapshotForMatch === "function" ? domIndex.getDomLayerSnapshotForMatch(el) : null;
          if (snap2) {
            var dbg0 = "";
            if (el && el.dataset && (el.dataset.debugLabel || el.dataset.debug_label)) {
              dbg0 = String(el.dataset.debugLabel || el.dataset.debug_label || "");
            } else if (el && el.getAttribute) {
              dbg0 = String(el.getAttribute("data-debug-label") || "");
            }
            var dbg = _normalizeDebugLabelBase(dbg0);
            var elText = "";
            if (el && el.classList && el.classList.contains("flat-text")) {
              elText = el.textContent ? String(el.textContent || "").trim() : "";
            }

            var bestKey2 = (dbg && elText) ? _pickNearestTreeKeyByRectWithDebugLabelAndText(snap2, true, dbg, elText) : "";
            if (!bestKey2) bestKey2 = dbg ? _pickNearestTreeKeyByRectWithDebugLabel(snap2, true, dbg) : "";
            if (!bestKey2) bestKey2 = _pickNearestTreeKeyByRect(snap2, true);
            if (!bestKey2 && dbg && elText) bestKey2 = _pickNearestTreeKeyByRectWithDebugLabelAndText(snap2, false, dbg, elText);
            if (!bestKey2 && dbg) bestKey2 = _pickNearestTreeKeyByRectWithDebugLabel(snap2, false, dbg);
            if (!bestKey2) bestKey2 = _pickNearestTreeKeyByRect(snap2, false);
            if (bestKey2) {
              key = bestKey2;
            }
          }
        }
      }
    }

    if (typeof c.highlightTreeItemByLayerKey === "function") {
      c.highlightTreeItemByLayerKey(key, { scroll_into_view: true });
    }
  }

  return {
    handleTreeClick: handleTreeClick,
    handlePreviewSelectionChanged: handlePreviewSelectionChanged,
  };
}

