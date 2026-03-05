import { buildLayerKey, buildPosKey, parseLayerKey } from "../../layer_key.js";

export function createFlattenedPreviewDomIndex(opts) {
  var o = opts || {};
  var preview = o.preview;
  var enableVisibilityToggles = !!o.enableVisibilityToggles;

  var elementByLayerKey = new Map(); // layerKey -> Element
  var elementsByPosKey = new Map(); // posKey (no z) -> Array<{ el, z }>

  function buildLayerKeyFromDomElement(element) {
    if (!element) return "";
    if (!element.classList) return "";
    if (
      !element.classList.contains("flat-shadow") &&
      !element.classList.contains("flat-border") &&
      !element.classList.contains("flat-element") &&
      !element.classList.contains("flat-text") &&
      !element.classList.contains("flat-button-anchor")
    ) {
      return "";
    }

    var kind = "";
    if (element.classList.contains("flat-button-anchor")) kind = "button_anchor";
    else if (element.classList.contains("flat-shadow")) kind = "shadow";
    else if (element.classList.contains("flat-border")) kind = "border";
    else if (element.classList.contains("flat-element")) kind = "element";
    else if (element.classList.contains("flat-text")) kind = "text";

    var left = parseFloat(String(element.style.left || "").replace("px", "")) || 0;
    var top = parseFloat(String(element.style.top || "").replace("px", "")) || 0;
    var width = parseFloat(String(element.style.width || "").replace("px", "")) || 0;
    var height = parseFloat(String(element.style.height || "").replace("px", "")) || 0;
    var z = parseFloat(String(element.style.zIndex || "").trim()) || 0;
    return buildLayerKey(kind, left, top, width, height, z);
  }

  function getDomLayerSnapshotForMatch(element) {
    if (!element || !element.style) return null;
    var kind = "";
    if (element.classList && element.classList.contains("flat-button-anchor")) kind = "button_anchor";
    else if (element.classList && element.classList.contains("flat-shadow")) kind = "shadow";
    else if (element.classList && element.classList.contains("flat-border")) kind = "border";
    else if (element.classList && element.classList.contains("flat-element")) kind = "element";
    else if (element.classList && element.classList.contains("flat-text")) kind = "text";
    if (!kind) return null;
    var left = parseFloat(String(element.style.left || "").replace("px", "")) || 0;
    var top = parseFloat(String(element.style.top || "").replace("px", "")) || 0;
    var width = parseFloat(String(element.style.width || "").replace("px", "")) || 0;
    var height = parseFloat(String(element.style.height || "").replace("px", "")) || 0;
    var z = parseFloat(String(element.style.zIndex || "").trim()) || 0;
    return { kind: kind, left: left, top: top, width: width, height: height, z: z };
  }

  function indexFlattenedPreviewElements(opts2) {
    var x = opts2 || {};
    var groupKeyByLayerKey = x.groupKeyByLayerKey;

    elementByLayerKey.clear();
    elementsByPosKey.clear();

    if (!preview) return;
    var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
    if (!doc) return;
    var selectedCanvasSizeKey = preview.getCurrentSelectedCanvasSizeKey ? preview.getCurrentSelectedCanvasSizeKey() : "";
    var flatArea = doc.querySelector('.flat-display-area[data-size-key="' + String(selectedCanvasSizeKey || "") + '"]');
    if (!flatArea) return;
    var nodes = flatArea.querySelectorAll(".flat-shadow, .flat-border, .flat-element, .flat-text, .flat-button-anchor");
    if (!nodes || nodes.length <= 0) return;

    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el) continue;
      var key = buildLayerKeyFromDomElement(el);
      if (!key) continue;
      el.dataset.layerKey = key;
      if (enableVisibilityToggles && groupKeyByLayerKey && groupKeyByLayerKey.has(key)) {
        var gk = String(groupKeyByLayerKey.get(key) || "");
        if (gk) {
          el.dataset.groupKey = gk;
        }
      }
      if (!elementByLayerKey.has(key)) {
        elementByLayerKey.set(key, el);
      }

      // extra index: ignore z, used for tolerant matching
      var snap = getDomLayerSnapshotForMatch(el);
      if (snap) {
        var posKey = buildPosKey(snap.kind, snap.left, snap.top, snap.width, snap.height);
        if (posKey) {
          var arr = elementsByPosKey.has(posKey) ? elementsByPosKey.get(posKey) : null;
          if (!arr) {
            arr = [];
            elementsByPosKey.set(posKey, arr);
          }
          arr.push({ el: el, z: snap.z });
        }
      }
    }
  }

  function findPreviewElementByLayerKey(layerKey) {
    var key = String(layerKey || "");
    if (!key) return null;

    var direct = elementByLayerKey.get(key);
    if (direct) return direct;

    var parsed = parseLayerKey(key);
    if (!parsed) return null;

    // 1) posKey exact (ignore z)
    var posKey = buildPosKey(parsed.kind, parsed.left, parsed.top, parsed.width, parsed.height);
    var candidates = posKey && elementsByPosKey.has(posKey) ? elementsByPosKey.get(posKey) : null;
    if (candidates && candidates.length > 0) {
      var best = null;
      var bestScore = Infinity;
      for (var i = 0; i < candidates.length; i++) {
        var c = candidates[i];
        if (!c || !c.el) continue;
        var dz = Math.abs(Number(c.z || 0) - parsed.z);
        if (dz < bestScore) {
          bestScore = dz;
          best = c.el;
        }
      }
      if (best) return best;
    }

    // 2) fallback: epsilon match scan
    var eps = 0.6; // px
    var bestEl = null;
    var bestMetric = Infinity;
    elementByLayerKey.forEach(function (el) {
      if (!el) return;
      var snap = getDomLayerSnapshotForMatch(el);
      if (!snap) return;
      if (snap.kind !== parsed.kind) return;
      if (Math.abs(snap.left - parsed.left) > eps) return;
      if (Math.abs(snap.top - parsed.top) > eps) return;
      if (Math.abs(snap.width - parsed.width) > eps) return;
      if (Math.abs(snap.height - parsed.height) > eps) return;
      var metric = Math.abs(snap.z - parsed.z);
      if (metric < bestMetric) {
        bestMetric = metric;
        bestEl = el;
      }
    });
    return bestEl;
  }

  function resolveLayerKeyToIndexedDomKey(layerKey) {
    var key = String(layerKey || "");
    if (!key) return "";
    if (elementByLayerKey.has(key)) return key;
    var el = findPreviewElementByLayerKey(key);
    if (el && el.dataset && String(el.dataset.layerKey || "")) {
      return String(el.dataset.layerKey || "");
    }
    return key;
  }

  function forEachIndexedElement(cb) {
    elementByLayerKey.forEach(function (el, key) {
      cb(el, key);
    });
  }

  return {
    elementByLayerKey: elementByLayerKey,
    elementsByPosKey: elementsByPosKey,
    indexFlattenedPreviewElements: indexFlattenedPreviewElements,
    findPreviewElementByLayerKey: findPreviewElementByLayerKey,
    resolveLayerKeyToIndexedDomKey: resolveLayerKeyToIndexedDomKey,
    buildLayerKeyFromDomElement: buildLayerKeyFromDomElement,
    getDomLayerSnapshotForMatch: getDomLayerSnapshotForMatch,
    forEachIndexedElement: forEachIndexedElement,
  };
}

