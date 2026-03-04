import { buildLayerKey } from "../../layer_key.js";
import { buildStableHtmlComponentKeyWithPrefix } from "../../ui_export/keys.js";

function _sanitizeTreeText(raw) {
  var s = String(raw || "").trim();
  if (!s) return "";
  if (s.length > 140) return s.slice(0, 140) + "...";
  return s;
}

function _normalizeInlineText(raw) {
  var s = String(raw || "").trim().replace(/\s+/g, " ");
  if (!s) return "";
  if (s.length > 40) s = s.slice(0, 40) + "...";
  return s;
}

function _isButtonLikeSource(source) {
  if (!source) return false;
  var cls = String(source.className || "");
  if (cls && /(^|\s)btn(\s|$)/i.test(cls)) return true;
  if (source.inButton === true) return true;
  var attrs = source.attributes || null;
  if (!attrs) return false;
  var uiRole = String(attrs.dataUiRole || "").trim().toLowerCase();
  if (uiRole === "button") return true;
  var ariaRole = String(attrs.role || "").trim().toLowerCase();
  if (ariaRole === "button") return true;
  if (String(attrs.dataUiInteractKey || "").trim()) return true;
  if (String(attrs.dataUiAction || "").trim()) return true;
  var tag = String(source.tagName || "").trim().toLowerCase();
  if (tag === "button" && String(attrs.dataUiKey || "").trim()) return true;
  return false;
}

function _inferAtomicGroupKeyForTree(source, uiKeyPrefix) {
  return buildStableHtmlComponentKeyWithPrefix(source, uiKeyPrefix);
}

function _inferDisplayNameForTree(source) {
  if (!source) return "";
  var attrs = source.attributes || null;
  if (_isButtonLikeSource(source)) {
    var ownerDbg0 = attrs ? String(attrs.componentOwnerDataDebugLabel || "").trim() : "";
    var ownerLabel = _normalizeInlineText(ownerDbg0);
    if (ownerLabel) return ownerLabel;
    var full = _normalizeInlineText(source.fullTextContent || source.textContent || "");
    if (full) return full;
  }

  var ownerUiKey = attrs ? String(attrs.componentOwnerDataUiKey || "").trim() : "";
  if (ownerUiKey) return ownerUiKey;
  var ownerId = attrs ? String(attrs.componentOwnerId || "").trim() : "";
  if (ownerId) return ownerId;
  var ownerDbg = attrs ? String(attrs.componentOwnerDataDebugLabel || "").trim() : "";
  if (ownerDbg) return ownerDbg;
  var ownerElementIndexText = attrs ? String(attrs.componentOwnerElementIndex || "").trim() : "";
  if (ownerElementIndexText && /^\d+$/.test(ownerElementIndexText)) return "e" + String(Math.trunc(Number(ownerElementIndexText)));

  var dataUiKey = attrs ? String(attrs.dataUiKey || "").trim() : "";
  if (dataUiKey) return dataUiKey;
  var idPart = source.id ? String(source.id || "").trim() : "";
  if (idPart) return idPart;
  var dbg = attrs ? String(attrs.dataDebugLabel || "").trim() : "";
  if (dbg) return dbg;
  if (Number.isFinite(source.elementIndex)) return "e" + String(Math.trunc(source.elementIndex));
  return "";
}

function _looksLikeButtonGroupKey(groupKey) {
  var gk = String(groupKey || "").trim().toLowerCase();
  if (!gk) return false;
  return gk.indexOf("btn_") >= 0 || gk.indexOf("__btn") >= 0 || gk.indexOf("button") >= 0;
}

function _deriveGroupDisplayTitle(groupEntry) {
  if (!groupEntry) return "";
  var base = String(groupEntry.name || groupEntry.key || "").trim();
  var items = groupEntry.items || [];

  function isBadCandidate(text) {
    var s = String(text || "");
    if (!s) return true;
    if (s.indexOf("{{") >= 0) return true;
    if (s.indexOf("}}") >= 0) return true;
    return false;
  }

  function scoreCandidate(text) {
    var s = String(text || "");
    if (!s) return -1;
    if (s.length > 18) return -1;
    if (isBadCandidate(s)) return -1;
    var cjk = (s.match(/[\u4e00-\u9fff]/g) || []).length;
    return cjk * 10 + Math.min(18, s.length);
  }

  var best = "";
  var bestScore = -1;
  for (var i = 0; i < items.length; i++) {
    var it = items[i] || null;
    if (!it) continue;
    var src = it.source || null;
    var c1 = "";
    if (src) {
      c1 = _normalizeInlineText(src.fullTextContent || src.textContent || "");
    }
    var c2 = _normalizeInlineText(it.textSnippet || "");
    var s1 = scoreCandidate(c1);
    if (s1 > bestScore) {
      bestScore = s1;
      best = c1;
    }
    var s2 = scoreCandidate(c2);
    if (s2 > bestScore) {
      bestScore = s2;
      best = c2;
    }
  }

  if (!best && _looksLikeButtonGroupKey(groupEntry.key)) {
    for (var j = 0; j < items.length; j++) {
      var it2 = items[j] || null;
      var src2 = it2 ? (it2.source || null) : null;
      if (!src2) continue;
      var c = _normalizeInlineText(src2.fullTextContent || src2.textContent || "");
      if (c && !isBadCandidate(c) && c.length <= 40) {
        best = c;
        break;
      }
    }
  }

  return best ? best : base;
}

function _escapeHtml(text) {
  var s = String(text || "");
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function _buildEyeIconHtml(isHidden) {
  var hiddenAttr = isHidden ? ' data-hidden="1"' : "";
  return (
    '<span class="wb-eye-icon"' + hiddenAttr + ' aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" width="14" height="14" focusable="false">' +
    '<path class="wb-eye-shape" d="M12 5c5.6 0 9.7 4.5 10.6 6.1.2.3.2.5 0 .8C21.7 13.5 17.6 18 12 18S2.3 13.5 1.4 11.9c-.2-.3-.2-.5 0-.8C2.3 9.5 6.4 5 12 5Zm0 2C7.8 7 4.4 10.2 3.5 11.5 4.4 12.8 7.8 16 12 16s7.6-3.2 8.5-4.5C19.6 10.2 16.2 7 12 7Zm0 2.2A2.8 2.8 0 1 1 12 15a2.8 2.8 0 0 1 0-5.6Zm0 1.8a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z"></path>' +
    '<path class="wb-eye-slash" d="M4 4l16 16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"></path>' +
    "</svg>" +
    "</span>"
  );
}

function _buildTrashIconHtml(isExcluded) {
  var excludedAttr = isExcluded ? ' data-excluded="1"' : "";
  return (
    '<span class="wb-trash-icon"' + excludedAttr + ' aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" width="14" height="14" focusable="false">' +
    '<path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1.2 6h1.6v9h-1.6V9Zm4 0h1.6v9h-1.6V9ZM6.8 9h1.6v9H6.8V9ZM7 21h10a2 2 0 0 0 2-2V7H5v12a2 2 0 0 0 2 2Z" fill="currentColor"></path>' +
    "</svg>" +
    "</span>"
  );
}

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

export function renderFlattenGroupTree(opts) {
  var o = opts || {};
  var store = o.store;
  var layerList = o.layerList || [];
  var canvasSizeKey = o.canvasSizeKey;
  var containerElement = o.containerElement;
  var statusTextElement = o.statusTextElement;
  var uiKeyPrefix = store ? String(store.uiKeyPrefix || "") : "";

  var enableVisibilityToggles = !!o.enableVisibilityToggles;
  var enableExportExcludeToggles = !!o.enableExportExcludeToggles;

  var isGroupHidden = o.isGroupHidden;
  var isLayerHidden = o.isLayerHidden;
  var isLayerExcluded = o.isLayerExcluded;

  if (!store || !containerElement) return;

  var layers = Array.isArray(layerList) ? layerList : [];
  if (!layers || layers.length <= 0) {
    containerElement.innerHTML = [
      '<div class="wb-tree-empty">',
      "扁平分组为空：没有提取到任何可用层。",
      "<br/>",
      "常见原因：",
      "<br/>- compute iframe 提取到的元素为 0（页面未正确渲染/画布尺寸未生效）",
      "<br/>- 页面全部处于不可见态（display:none / visibility:hidden 且非多状态容器）",
      "<br/>- 极端情况下遮挡剔除误判（已做兜底回退，但仍建议检查控制台诊断）",
      "<br/><br/>",
      "建议：点击左上角“原稿”确认页面正常 → 再点“刷新”重试；如仍为空，请打开浏览器控制台查看报错/诊断。",
      "</div>",
    ].join("");
    if (statusTextElement) {
      statusTextElement.textContent = "空";
    }
    return;
  }

  // reset derived maps (keep references stable)
  store.groupKeyByLayerKey.clear();
  store.layerEntriesByGroupKey.clear();
  store.groupDisplayNameByKey.clear();

  var groups = new Map(); // groupKey -> { key, name, items: [], bounds }
  var singletons = [];

  for (var i = 0; i < layers.length; i++) {
    var layer = layers[i];
    if (!layer || !layer.rect) continue;
    var src = layer.source || null;
    var gk = _inferAtomicGroupKeyForTree(src, uiKeyPrefix);
    var name = _inferDisplayNameForTree(src);
    var left = Number(layer.rect.left || 0);
    var top = Number(layer.rect.top || 0);
    var right = left + Number(layer.rect.width || 0);
    var bottom = top + Number(layer.rect.height || 0);

    var item = {
      kind: String(layer.kind || ""),
      z: Number(layer.z || 0),
      debugLabel: String(layer.debugLabel || ""),
      rect: { left: left, top: top, width: Number(layer.rect.width || 0), height: Number(layer.rect.height || 0) },
      displayName: name,
      groupKey: gk,
      layerKey: _buildLayerKeyFromLayer(layer),
      source: src,
      textSnippet: (function () {
        if (String(layer.kind || "") !== "text") return "";
        var src2 = layer.source || null;
        var raw = src2 && src2.textContent ? String(src2.textContent || "").trim() : "";
        if (!raw) return "";
        raw = raw.replace(/\s+/g, " ");
        if (raw.length > 30) raw = raw.slice(0, 30) + "...";
        return raw;
      })(),
    };

    if (enableVisibilityToggles && item.layerKey && gk) {
      store.groupKeyByLayerKey.set(String(item.layerKey || ""), String(gk || ""));
      var arr0 = store.layerEntriesByGroupKey.has(String(gk || "")) ? store.layerEntriesByGroupKey.get(String(gk || "")) : null;
      if (!arr0) {
        arr0 = [];
        store.layerEntriesByGroupKey.set(String(gk || ""), arr0);
      }
      arr0.push({ layerKey: String(item.layerKey || ""), rect: item.rect });
    }

    if (!gk) {
      singletons.push(item);
      continue;
    }
    var entry = groups.get(gk);
    if (!entry) {
      entry = {
        key: gk,
        name: name,
        items: [],
        bounds: { minX: left, minY: top, maxX: right, maxY: bottom },
      };
      groups.set(gk, entry);
    }
    entry.items.push(item);
    entry.bounds.minX = Math.min(entry.bounds.minX, left);
    entry.bounds.minY = Math.min(entry.bounds.minY, top);
    entry.bounds.maxX = Math.max(entry.bounds.maxX, right);
    entry.bounds.maxY = Math.max(entry.bounds.maxY, bottom);
  }

  var groupList = [];
  groups.forEach(function (g) { groupList.push(g); });
  groupList.sort(function (a, b) {
    if (a.bounds.minY !== b.bounds.minY) return a.bounds.minY - b.bounds.minY;
    return a.bounds.minX - b.bounds.minX;
  });

  groupList.forEach(function (g) {
    g.items.sort(function (a, b) {
      if (a.z !== b.z) return b.z - a.z;
      return String(a.kind || "").localeCompare(String(b.kind || ""));
    });
  });
  singletons.sort(function (a, b) {
    if (a.rect.top !== b.rect.top) return a.rect.top - b.rect.top;
    return a.rect.left - b.rect.left;
  });

  var htmlParts = [];
  htmlParts.push('<div class="wb-tree-meta">画布：' + _escapeHtml(String(canvasSizeKey || "")) + " | 组数：" + String(groupList.length) + " | 层数：" + String(layers.length) + "</div>");

  var q = String(store.treeFilterText || "").trim().toLowerCase();
  function _matchText(s) {
    if (!q) return true;
    return String(s || "").toLowerCase().indexOf(q) >= 0;
  }

  for (var gi = 0; gi < groupList.length; gi++) {
    var g0 = groupList[gi];
    var count = g0.items.length;
    var isMultiItemGroup = count >= 2;
    var tagHtml = isMultiItemGroup ? '<span class="tag">组</span>' : '<span class="tag warn">单项</span>';
    var derivedTitle = _deriveGroupDisplayTitle(g0);
    var title = _sanitizeTreeText(derivedTitle || g0.name || g0.key);
    store.groupDisplayNameByKey.set(String(g0.key || ""), String(title || ""));

    var groupIsHidden = enableVisibilityToggles && typeof isGroupHidden === "function" ? !!isGroupHidden(String(g0.key || "")) : false;

    if (q) {
      var groupHit = _matchText(g0.key) || _matchText(g0.name);
      if (!groupHit) {
        var anyHit = false;
        for (var hi = 0; hi < g0.items.length; hi++) {
          var itH = g0.items[hi] || {};
          if (_matchText(itH.displayName) || _matchText(itH.debugLabel) || _matchText(itH.kind) || _matchText(itH.textSnippet)) {
            anyHit = true;
            break;
          }
        }
        if (!anyHit) continue;
      }
    }

    var shouldOpen = store.expandedGroupKeySet.has(String(g0.key || "")) ? true : isMultiItemGroup;
    var groupEyeHtml = enableVisibilityToggles
      ? (
        '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="group" data-group-key="' + _escapeHtml(String(g0.key || "")) + '" aria-label="' + (groupIsHidden ? "显示" : "隐藏") + '" title="' + (groupIsHidden ? "点击显示" : "点击隐藏") + '">' +
        _buildEyeIconHtml(groupIsHidden) +
        "</button>"
      )
      : "";
    var isGroupExcluded = enableExportExcludeToggles && store.excludedGroupKeySet.has(String(g0.key || ""));
    var groupTrashHtml = enableExportExcludeToggles
      ? (
        '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="group" data-toggle-action="exclude" data-group-key="' + _escapeHtml(String(g0.key || "")) + '" aria-label="' + (isGroupExcluded ? "取消排除" : "排除导出") + '" title="' + (isGroupExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
        _buildTrashIconHtml(isGroupExcluded) +
        "</button>"
      )
      : "";
    var expanderHtml = '<button type="button" class="wb-tree-expander" data-expander="1" aria-label="展开/折叠" title="展开/折叠"></button>';
    var summaryText =
      '<span class="wb-tree-row">' +
      groupEyeHtml +
      groupTrashHtml +
      expanderHtml +
      tagHtml +
      '<span class="wb-tree-title">' + _escapeHtml(title) + "</span>" +
      ' <span class="wb-tree-meta">(' + String(count) + ")</span>" +
      "</span>";
    htmlParts.push('<details ' + (shouldOpen ? "open" : "") + ' data-group-key="' + _escapeHtml(String(g0.key || "")) + '"' + (store.selectedGroupKey === String(g0.key || "") ? ' class="wb-tree-group-selected"' : "") + '>');
    htmlParts.push("<summary>" + summaryText + "</summary>");
    htmlParts.push('<div class="wb-tree-children">');

    for (var ii = 0; ii < g0.items.length; ii++) {
      var it = g0.items[ii];
      var label = (it.debugLabel ? it.debugLabel : it.kind);
      if (String(it.kind || "") === "text" && it.textSnippet) {
        label = label + " 「" + String(it.textSnippet || "") + "」";
      }
      if (q && !_matchText(label) && !_matchText(it.displayName) && !_matchText(it.kind) && !_matchText(it.textSnippet)) {
        continue;
      }
      var layerIsHidden = enableVisibilityToggles && typeof isLayerHidden === "function" ? !!isLayerHidden(it.layerKey) : false;
      var layerIsExcluded = enableExportExcludeToggles && typeof isLayerExcluded === "function" ? !!isLayerExcluded(it.layerKey) : false;

      var toggleHtml = enableVisibilityToggles
        ? (
          '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="layer" data-layer-key="' + _escapeHtml(String(it.layerKey || "")) + '" aria-label="' + (layerIsHidden ? "显示" : "隐藏") + '" title="' + (layerIsHidden ? "点击显示" : "点击隐藏") + '">' +
          _buildEyeIconHtml(layerIsHidden) +
          "</button>"
        )
        : "";
      var trashHtml = enableExportExcludeToggles
        ? (
          '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="layer" data-toggle-action="exclude" data-layer-key="' + _escapeHtml(String(it.layerKey || "")) + '" aria-label="' + (layerIsExcluded ? "取消排除" : "排除导出") + '" title="' + (layerIsExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
          _buildTrashIconHtml(layerIsExcluded) +
          "</button>"
        )
        : "";
      htmlParts.push(
        '<div class="wb-tree-item" role="button" tabindex="0" data-layer-key="' + _escapeHtml(String(it.layerKey || "")) + '">' +
        toggleHtml +
        trashHtml +
        '<span class="wb-tree-item-main">' +
        '<span class="muted">[' + _escapeHtml(String(it.kind || "")) + " z" + String(Math.round(it.z)) + "]</span> " +
        _escapeHtml(_sanitizeTreeText(label)) +
        "</span>" +
        "</div>"
      );
    }
    htmlParts.push("</div>");
    htmlParts.push("</details>");
  }

  if (singletons.length > 0) {
    htmlParts.push('<details ' + (store.expandedUngrouped ? "open" : "") + ">");
    var expander2 = '<button type="button" class="wb-tree-expander" data-expander="1" aria-label="展开/折叠" title="展开/折叠"></button>';
    htmlParts.push('<summary><span class="wb-tree-row">' + expander2 + '<span class="tag warn">未归组</span> <span class="wb-tree-meta">(' + String(singletons.length) + ")</span></span></summary>");
    htmlParts.push('<div class="wb-tree-children">');
    for (var si = 0; si < singletons.length; si++) {
      var sIt = singletons[si];
      var sHidden = enableVisibilityToggles && typeof isLayerHidden === "function" ? !!isLayerHidden(sIt.layerKey) : false;
      var sExcluded = enableExportExcludeToggles && typeof isLayerExcluded === "function" ? !!isLayerExcluded(sIt.layerKey) : false;
      var sToggleHtml = enableVisibilityToggles
        ? (
          '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="layer" data-layer-key="' + _escapeHtml(String(sIt.layerKey || "")) + '" aria-label="' + (sHidden ? "显示" : "隐藏") + '" title="' + (sHidden ? "点击显示" : "点击隐藏") + '">' +
          _buildEyeIconHtml(sHidden) +
          "</button>"
        )
        : "";
      var sTrashHtml = enableExportExcludeToggles
        ? (
          '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="layer" data-toggle-action="exclude" data-layer-key="' + _escapeHtml(String(sIt.layerKey || "")) + '" aria-label="' + (sExcluded ? "取消排除" : "排除导出") + '" title="' + (sExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
          _buildTrashIconHtml(sExcluded) +
          "</button>"
        )
        : "";
      if (q && !_matchText(sIt.debugLabel) && !_matchText(sIt.kind) && !_matchText(sIt.textSnippet)) {
        continue;
      }
      htmlParts.push(
        '<div class="wb-tree-item" role="button" tabindex="0" data-layer-key="' + _escapeHtml(String(sIt.layerKey || "")) + '">' +
        sToggleHtml +
        sTrashHtml +
        '<span class="wb-tree-item-main">' +
        '<span class="muted">[' + _escapeHtml(String(sIt.kind || "")) + " z" + String(Math.round(sIt.z)) + "]</span> " +
        _escapeHtml(_sanitizeTreeText(sIt.debugLabel || sIt.kind)) +
        "</span>" +
        "</div>"
      );
    }
    htmlParts.push("</div>");
    htmlParts.push("</details>");
  }

  containerElement.innerHTML = htmlParts.join("\n");
  if (statusTextElement) {
    statusTextElement.textContent = "已生成";
  }
}

