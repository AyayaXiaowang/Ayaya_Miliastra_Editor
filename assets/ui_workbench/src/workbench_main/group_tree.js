import { dom } from "../dom_refs.js";
import { buildLayerKey, buildPosKey, parseLayerKey } from "../layer_key.js";
import { buildStableHtmlComponentKeyWithPrefix } from "../ui_export/keys.js";
import { canFallbackToVisiblePreviewDocument, extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback } from "./compute_fallback.js";

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

    var _flatPreviewElementByLayerKey = new Map(); // layerKey -> Element
    var _flatPreviewElementsByPosKey = new Map(); // posKey (no z) -> Array<{ el, z }>
    var _selectedLayerKey = "";
    var _selectedGroupKey = "";
    var _uiKeyPrefix = "";
    // 可见性真源：仅 layerKey 级别。
    // 组级显隐由“该组下的 layerKeys 是否全部隐藏”推导，不再维护独立的 group hidden set，
    // 避免出现“选中/定位按 layerKey，但显隐按 groupKey”导致的分叉与误伤。
    var _hiddenLayerKeySet = new Set(); // layerKey -> hidden
    var _excludedLayerKeySet = new Set(); // layerKey -> excluded-from-export
    var _excludedGroupKeySet = new Set(); // groupKey -> excluded-from-export
    var _groupKeyByLayerKey = new Map(); // layerKey -> groupKey
    var _expandedGroupKeySet = new Set(); // groupKey -> expanded (open)
    var _expandedUngrouped = true;
    var _layerEntriesByGroupKey = new Map(); // groupKey -> Array<{ layerKey, rect }>
    var _groupDisplayNameByKey = new Map(); // groupKey -> displayName (used by other views)
    var _treeFilterText = "";
    var _lastLayerList = null;
    var _lastCanvasSizeKey = "";

    function setUiKeyPrefix(prefix) {
        _uiKeyPrefix = String(prefix || "");
    }

    function _rectIntersectionArea(a, b) {
        if (!a || !b) return 0;
        var left = Math.max(Number(a.left || 0), Number(b.left || 0));
        var top = Math.max(Number(a.top || 0), Number(b.top || 0));
        var right = Math.min(Number(a.left || 0) + Number(a.width || 0), Number(b.left || 0) + Number(b.width || 0));
        var bottom = Math.min(Number(a.top || 0) + Number(a.height || 0), Number(b.top || 0) + Number(b.height || 0));
        var w = right - left;
        var h = bottom - top;
        if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return 0;
        return w * h;
    }

    function _isLayerHidden(layerKey) {
        var lk = String(layerKey || "");
        if (!lk) {
            return false;
        }
        if (_hiddenLayerKeySet.has(lk)) {
            return true;
        }
        // 兼容：hidden set 的真源是“已索引到的预览 DOM layerKey”。
        // 当调用方传入的是 compute/导出侧的 key（可能存在 z/舍入差异）时，也应能正确判定为隐藏，
        // 否则会出现“隐藏后无法再显示（toggle 总是认为未隐藏）”的症状。
        var normalized = _resolveLayerKeyToIndexedDomKey(lk);
        if (normalized && normalized !== lk && _hiddenLayerKeySet.has(normalized)) {
            return true;
        }
        return false;
    }

    function _isAllLayerKeysHidden(layerKeys) {
        var keys = Array.isArray(layerKeys) ? layerKeys : [];
        if (!keys || keys.length <= 0) {
            return false;
        }
        for (var i = 0; i < keys.length; i++) {
            var k = String(keys[i] || "");
            // 空 key 视为“不可判定为隐藏”：避免出现“组内 layerKey 异常为空 -> 被误判为全部隐藏”的误伤。
            if (!k) {
                return false;
            }
            if (!_isLayerHidden(k)) {
                return false;
            }
        }
        return true;
    }

    function _resolveLayerKeyToIndexedDomKey(layerKey) {
        // 把“外部传入的 layerKey”（可能来自 compute 提取/导出控件/点选反推）尽量映射为
        // 当前可视预览 iframe 已索引到的真实 DOM key（el.dataset.layerKey）。
        // 目的：让显隐的真源稳定落到“画布上真实存在的元素”。
        var key = String(layerKey || "");
        if (!key) {
            return "";
        }
        if (_flatPreviewElementByLayerKey && _flatPreviewElementByLayerKey.has(key)) {
            return key;
        }
        var el = _findPreviewElementByLayerKey(key);
        if (el && el.dataset && String(el.dataset.layerKey || "")) {
            return String(el.dataset.layerKey || "");
        }
        return key;
    }

    function _deleteHiddenLayerKeyWithNormalization(layerKey) {
        var raw = String(layerKey || "");
        if (!raw) {
            return;
        }
        // 同时删除 raw 与其归一化后的 domKey，避免“集合里存的是 domKey，但取消隐藏传入 rawKey”导致无法取消。
        if (_hiddenLayerKeySet) {
            _hiddenLayerKeySet.delete(raw);
            var normalized = _resolveLayerKeyToIndexedDomKey(raw);
            if (normalized && normalized !== raw) {
                _hiddenLayerKeySet.delete(normalized);
            }
        }
    }

    function _setLayersHiddenInternal(layerKeys, hidden) {
        var keys = Array.isArray(layerKeys) ? layerKeys : [];
        for (var i = 0; i < keys.length; i++) {
            var k = String(keys[i] || "");
            if (!k) continue;
            if (hidden) {
                _hiddenLayerKeySet.add(_resolveLayerKeyToIndexedDomKey(k));
            } else {
                _deleteHiddenLayerKeyWithNormalization(k);
            }
        }
    }

    function _getGroupLayerKeys(groupKey) {
        var gk = String(groupKey || "").trim();
        if (!gk) {
            return [];
        }
        var entries = _layerEntriesByGroupKey.has(gk) ? _layerEntriesByGroupKey.get(gk) : null;
        if (!entries || entries.length <= 0) {
            return [];
        }
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
        if (!lk) {
            return false;
        }
        if (_excludedLayerKeySet.has(lk)) {
            return true;
        }
        var gk = _groupKeyByLayerKey.has(lk) ? String(_groupKeyByLayerKey.get(lk) || "") : "";
        if (gk && _excludedGroupKeySet.has(gk)) {
            return true;
        }
        return false;
    }

    function _applyHiddenStateToPreviewElements() {
        if (!enableVisibilityToggles) {
            return;
        }
        _flatPreviewElementByLayerKey.forEach(function (el, layerKey) {
            if (!el || !el.style) {
                return;
            }
            el.style.display = _isLayerHidden(layerKey) ? "none" : "";
        });
    }

    function _normalizeHiddenLayerKeysToIndexedPreviewElements() {
        // 关键：隐藏/显示的入参 layerKey 可能来自不同链路（分组树 layerList / 导出控件 flat_layer_key / 画布点选），
        // 它们在 z-index 或 toFixed 精度上可能出现轻微差异。
        //
        // 画布真正要隐藏的是“已索引到的预览 DOM 元素”；因此这里把 hidden set 归一化为“真实 DOM layerKey”，
        // 避免出现“列表状态已切换，但画布无变化”的错觉。
        if (!enableVisibilityToggles) {
            return;
        }
        if (!_hiddenLayerKeySet || _hiddenLayerKeySet.size <= 0) {
            return;
        }
        if (!_flatPreviewElementByLayerKey || _flatPreviewElementByLayerKey.size <= 0) {
            return;
        }
        var normalized = new Set();
        _hiddenLayerKeySet.forEach(function (rawKey) {
            var key = String(rawKey || "");
            if (!key) return;
            var el = _findPreviewElementByLayerKey(key);
            if (el && el.dataset && String(el.dataset.layerKey || "")) {
                normalized.add(String(el.dataset.layerKey || ""));
                return;
            }
            // 兜底：找不到对应 DOM（例如当前 sizeKey 下不存在），保留原 key 以便未来切换 sizeKey 时仍能生效。
            normalized.add(key);
        });
        _hiddenLayerKeySet = normalized;
    }

    function _toggleLayerExcluded(layerKey) {
        if (!enableExportExcludeToggles) {
            return;
        }
        var key = String(layerKey || "");
        if (!key) {
            return;
        }
        if (_excludedLayerKeySet.has(key)) {
            _excludedLayerKeySet.delete(key);
        } else {
            _excludedLayerKeySet.add(key);
        }
    }

    function _toggleGroupExcluded(groupKey) {
        if (!enableExportExcludeToggles) {
            return;
        }
        var key = String(groupKey || "");
        if (!key) {
            return;
        }
        if (_excludedGroupKeySet.has(key)) {
            _excludedGroupKeySet.delete(key);
        } else {
            _excludedGroupKeySet.add(key);
        }
    }

    function _toggleLayerHidden(layerKey) {
        if (!enableVisibilityToggles) {
            return;
        }
        // 关键：显隐必须作用在“当前可视预览 iframe 的真实 DOM 元素”上。
        // 在某些链路下（例如预览刚重渲染/切换尺寸/切换文件），外部可能直接调用 setLayerHidden，
        // 但分组树未刷新导致 _flatPreviewElementByLayerKey 仍指向旧 document 的元素引用。
        // 因此这里先强制重建索引，避免“列表图标变了但画布无变化”的错觉。
        _indexFlattenedPreviewElements();
        var key = String(layerKey || "");
        if (!key) {
            return;
        }
        var domKey = _resolveLayerKeyToIndexedDomKey(key);
        if (_hiddenLayerKeySet.has(domKey) || _hiddenLayerKeySet.has(key)) {
            _deleteHiddenLayerKeyWithNormalization(key);
        } else {
            _hiddenLayerKeySet.add(domKey);
        }
        // 选中清理：同时兼容 rawKey 与 domKey
        if ((_selectedLayerKey === key || _selectedLayerKey === domKey) && _isLayerHidden(domKey)) {
            preview.clearCurrentSelection();
            _clearTreeSelectionHighlight();
        }
        _normalizeHiddenLayerKeysToIndexedPreviewElements();
        _applyHiddenStateToPreviewElements();
    }

    function _toggleGroupHidden(groupKey) {
        if (!enableVisibilityToggles) {
            return;
        }
        _indexFlattenedPreviewElements();
        var key = String(groupKey || "").trim();
        if (!key) {
            return;
        }
        var keys = _getGroupLayerKeys(key);
        var wantHidden = !_isAllLayerKeysHidden(keys);
        _setLayersHiddenInternal(keys, wantHidden);
        if (_selectedLayerKey && _isLayerHidden(_selectedLayerKey)) {
            preview.clearCurrentSelection();
            _clearTreeSelectionHighlight();
        }
        _normalizeHiddenLayerKeysToIndexedPreviewElements();
        _applyHiddenStateToPreviewElements();
    }

    function resetVisibilityToggles() {
        if (!enableVisibilityToggles) {
            return;
        }
        _hiddenLayerKeySet.clear();
        _applyHiddenStateToPreviewElements();
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function resetExportExcludeToggles() {
        if (!enableExportExcludeToggles) {
            return;
        }
        _excludedLayerKeySet.clear();
        _excludedGroupKeySet.clear();
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function isGroupHidden(groupKey) {
        if (!enableVisibilityToggles) {
            return false;
        }
        var key = String(groupKey || "").trim();
        if (!key) {
            return false;
        }
        return _isAllLayerKeysHidden(_getGroupLayerKeys(key));
    }

    function isLayerHidden(layerKey) {
        if (!enableVisibilityToggles) {
            return false;
        }
        return _isLayerHidden(layerKey);
    }

    function isGroupExcluded(groupKey) {
        if (!enableExportExcludeToggles) {
            return false;
        }
        var key = String(groupKey || "");
        if (!key) {
            return false;
        }
        return _excludedGroupKeySet.has(key);
    }

    function isLayerExcluded(layerKey) {
        if (!enableExportExcludeToggles) {
            return false;
        }
        return _isLayerExcluded(layerKey);
    }

    function setGroupHidden(groupKey, hidden) {
        if (!enableVisibilityToggles) {
            return;
        }
        var key = String(groupKey || "").trim();
        if (!key) {
            return;
        }
        _setLayersHiddenInternal(_getGroupLayerKeys(key), !!hidden);
        if (_selectedLayerKey && _isLayerHidden(_selectedLayerKey)) {
            preview.clearCurrentSelection();
            _clearTreeSelectionHighlight();
        }
        _normalizeHiddenLayerKeysToIndexedPreviewElements();
        _applyHiddenStateToPreviewElements();
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function setLayerHidden(layerKey, hidden) {
        if (!enableVisibilityToggles) {
            return;
        }
        _indexFlattenedPreviewElements();
        var key = String(layerKey || "");
        if (!key) {
            return;
        }
        var domKey = _resolveLayerKeyToIndexedDomKey(key);
        if (hidden) {
            _hiddenLayerKeySet.add(domKey);
        } else {
            _deleteHiddenLayerKeyWithNormalization(key);
        }
        if ((_selectedLayerKey === key || _selectedLayerKey === domKey) && _isLayerHidden(domKey)) {
            preview.clearCurrentSelection();
            _clearTreeSelectionHighlight();
        }
        _normalizeHiddenLayerKeysToIndexedPreviewElements();
        _applyHiddenStateToPreviewElements();
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function setLayersHidden(layerKeys, hidden) {
        if (!enableVisibilityToggles) {
            return;
        }
        _indexFlattenedPreviewElements();
        _setLayersHiddenInternal(layerKeys, !!hidden);
        if (_selectedLayerKey && _isLayerHidden(_selectedLayerKey)) {
            preview.clearCurrentSelection();
            _clearTreeSelectionHighlight();
        }
        _normalizeHiddenLayerKeysToIndexedPreviewElements();
        _applyHiddenStateToPreviewElements();
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function setGroupExcluded(groupKey, excluded) {
        if (!enableExportExcludeToggles) {
            return;
        }
        var key = String(groupKey || "");
        if (!key) {
            return;
        }
        if (excluded) {
            _excludedGroupKeySet.add(key);
        } else {
            _excludedGroupKeySet.delete(key);
        }
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function setLayerExcluded(layerKey, excluded) {
        if (!enableExportExcludeToggles) {
            return;
        }
        var key = String(layerKey || "");
        if (!key) {
            return;
        }
        if (excluded) {
            _excludedLayerKeySet.add(key);
        } else {
            _excludedLayerKeySet.delete(key);
        }
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function setLayersExcluded(layerKeys, excluded) {
        if (!enableExportExcludeToggles) {
            return;
        }
        var keys = Array.isArray(layerKeys) ? layerKeys : [];
        for (var i = 0; i < keys.length; i++) {
            var k = String(keys[i] || "");
            if (!k) continue;
            if (excluded) _excludedLayerKeySet.add(k);
            else _excludedLayerKeySet.delete(k);
        }
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function getLayerKeysForGroupRect(groupKey, rect) {
        var gk = String(groupKey || "").trim();
        if (!gk) {
            return [];
        }
        var entries = _layerEntriesByGroupKey.has(gk) ? _layerEntriesByGroupKey.get(gk) : null;
        if (!entries || entries.length <= 0) {
            return [];
        }
        var r = rect || null;
        if (!r) {
            return entries.map(function (x) { return x.layerKey; });
        }
        var out = [];
        for (var i = 0; i < entries.length; i++) {
            var e = entries[i];
            if (!e || !e.layerKey || !e.rect) continue;
            if (_rectIntersectionArea(e.rect, r) > 0) {
                out.push(String(e.layerKey || ""));
            }
        }
        return out;
    }

    function _buildLayerKeyFromLayer(layer) {
        if (!layer || !layer.rect) {
            return "";
        }
        return buildLayerKey(
            layer.kind,
            layer.rect.left,
            layer.rect.top,
            layer.rect.width,
            layer.rect.height,
            layer.z
        );
    }

    function _buildLayerKeyFromDomElement(element) {
        if (!element) {
            return "";
        }
        if (!element.classList) {
            return "";
        }
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

    function _getDomLayerSnapshotForMatch(element) {
        if (!element || !element.style) {
            return null;
        }
        var kind = "";
        if (element.classList && element.classList.contains("flat-button-anchor")) kind = "button_anchor";
        else if (element.classList && element.classList.contains("flat-shadow")) kind = "shadow";
        else if (element.classList && element.classList.contains("flat-border")) kind = "border";
        else if (element.classList && element.classList.contains("flat-element")) kind = "element";
        else if (element.classList && element.classList.contains("flat-text")) kind = "text";
        if (!kind) {
            return null;
        }
        var left = parseFloat(String(element.style.left || "").replace("px", "")) || 0;
        var top = parseFloat(String(element.style.top || "").replace("px", "")) || 0;
        var width = parseFloat(String(element.style.width || "").replace("px", "")) || 0;
        var height = parseFloat(String(element.style.height || "").replace("px", "")) || 0;
        var z = parseFloat(String(element.style.zIndex || "").trim()) || 0;
        return { kind: kind, left: left, top: top, width: width, height: height, z: z };
    }

    function _indexFlattenedPreviewElements() {
        _flatPreviewElementByLayerKey = new Map();
        _flatPreviewElementsByPosKey = new Map();
        var doc = preview.getPreviewDocument();
        if (!doc) {
            return;
        }
        var selectedCanvasSizeKey = preview.getCurrentSelectedCanvasSizeKey();
        var flatArea = doc.querySelector('.flat-display-area[data-size-key="' + String(selectedCanvasSizeKey || "") + '"]');
        if (!flatArea) {
            return;
        }
        var nodes = flatArea.querySelectorAll(".flat-shadow, .flat-border, .flat-element, .flat-text, .flat-button-anchor");
        if (!nodes || nodes.length <= 0) {
            return;
        }
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el) {
                continue;
            }
            var key = _buildLayerKeyFromDomElement(el);
            if (!key) {
                continue;
            }
            el.dataset.layerKey = key;
            if (enableVisibilityToggles) {
                var gk = _groupKeyByLayerKey.has(key) ? String(_groupKeyByLayerKey.get(key) || "") : "";
                if (gk) {
                    el.dataset.groupKey = gk;
                }
            }
            if (!_flatPreviewElementByLayerKey.has(key)) {
                _flatPreviewElementByLayerKey.set(key, el);
            }

            // 额外索引：忽略 z-index 的位置键，用于修复“layerKey 精确匹配失败导致点击无反应”的场景。
            // 背景：某些链路下 list 的 layerKey 与预览 DOM 的 layerKey 可能因 z/舍入差异而不一致，
            // 但几何位置/类别仍一致，允许用“近似匹配”恢复联动。
            var snap = _getDomLayerSnapshotForMatch(el);
            if (snap) {
                var posKey = buildPosKey(snap.kind, snap.left, snap.top, snap.width, snap.height);
                if (posKey) {
                    var arr = _flatPreviewElementsByPosKey.has(posKey) ? _flatPreviewElementsByPosKey.get(posKey) : null;
                    if (!arr) {
                        arr = [];
                        _flatPreviewElementsByPosKey.set(posKey, arr);
                    }
                    arr.push({ el: el, z: snap.z });
                }
            }
        }
        _normalizeHiddenLayerKeysToIndexedPreviewElements();
        _applyHiddenStateToPreviewElements();
    }

    function _findPreviewElementByLayerKey(layerKey) {
        var key = String(layerKey || "");
        if (!key) {
            return null;
        }

        var direct = _flatPreviewElementByLayerKey.get(key);
        if (direct) {
            return direct;
        }

        var parsed = parseLayerKey(key);
        if (!parsed) {
            return null;
        }

        // 1) 快速路径：posKey 精确命中（忽略 z）
        var posKey = buildPosKey(parsed.kind, parsed.left, parsed.top, parsed.width, parsed.height);
        var candidates = posKey && _flatPreviewElementsByPosKey.has(posKey) ? _flatPreviewElementsByPosKey.get(posKey) : null;
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
            if (best) {
                return best;
            }
        }

        // 2) 兜底：对所有已索引层做“容差匹配”（主要防止浮点舍入/极端链路导致 posKey 也对不上）
        // 注意：只在 direct/posKey 失败时执行，避免不必要的 O(N)。
        var eps = 0.6; // px 级容差：足够覆盖 0.01~0.5 的舍入/布局误差，但不会跨控件误命中太多
        var bestEl = null;
        var bestMetric = Infinity;
        _flatPreviewElementByLayerKey.forEach(function (el) {
            if (!el) return;
            var snap = _getDomLayerSnapshotForMatch(el);
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

    function findPreviewElementByLayerKey(layerKey) {
        // 对外暴露：供其它视图（例如导出控件列表）做“layerKey -> 预览 DOM 元素”定位。
        // 该函数包含：
        // - 精确 layerKey 命中
        // - 忽略 z-index 的 posKey 命中
        // - px 容差兜底（避免浮点舍入/极端链路导致点击无反应）
        return _findPreviewElementByLayerKey(layerKey);
    }

    function _clearTreeSelectionHighlight() {
        if (!flattenGroupTreeContainerElement) {
            return;
        }
        var prevKey = String(_selectedLayerKey || "");
        if (prevKey) {
            // 不使用 querySelector 拼接属性选择器：layerKey 可能包含需要转义的字符（极端情况下会导致匹配失败）
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
        _selectedLayerKey = "";
    }

    function _clearGroupSelectionHighlight() {
        if (!flattenGroupTreeContainerElement) {
            return;
        }
        var prev = String(_selectedGroupKey || "");
        if (!prev) {
            return;
        }
        var node = flattenGroupTreeContainerElement.querySelector('details[data-group-key="' + prev + '"]');
        if (node && node.classList) {
            node.classList.remove("wb-tree-group-selected");
        }
        _selectedGroupKey = "";
    }

    function _highlightTreeGroupByGroupKey(groupKey) {
        if (!flattenGroupTreeContainerElement) {
            return;
        }
        var gk = String(groupKey || "").trim();
        if (!gk) {
            _clearGroupSelectionHighlight();
            return;
        }
        if (_selectedGroupKey === gk) {
            return;
        }
        _clearGroupSelectionHighlight();
        var node = flattenGroupTreeContainerElement.querySelector('details[data-group-key="' + gk + '"]');
        if (!node) {
            return;
        }
        if (node.classList) {
            node.classList.add("wb-tree-group-selected");
        }
        _selectedGroupKey = gk;
    }

    function _highlightTreeItemByLayerKey(layerKey, opts) {
        if (!flattenGroupTreeContainerElement) {
            return;
        }
        var options = opts || {};
        var shouldScrollIntoView = options.scroll_into_view === true;
        var key = String(layerKey || "");
        if (!key) {
            _clearTreeSelectionHighlight();
            return;
        }
        if (_selectedLayerKey === key) {
            return;
        }
        _clearTreeSelectionHighlight();
        // 不使用 querySelector 拼接属性选择器：layerKey 可能包含需要转义的字符（极端情况下会导致匹配失败）
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
        if (!node) {
            return;
        }
        if (node.classList) {
            node.classList.add("selected");
        }
        _selectedLayerKey = key;
        _clearGroupSelectionHighlight();

        // 确保父 details 展开，再滚动到可见
        var parent = node.parentElement;
        while (parent) {
            if (parent.tagName && String(parent.tagName).toLowerCase() === "details") {
                parent.open = true;
                break;
            }
            parent = parent.parentElement;
        }
        if (shouldScrollIntoView && node.scrollIntoView) {
            node.scrollIntoView({ block: "center" });
        }
    }

    function scrollSelectionIntoView() {
        // 对外暴露：用于“Tab 切换后”把当前选中项滚到可见位置（容器此前可能 display:none）。
        if (!flattenGroupTreeContainerElement) {
            return;
        }
        var key = String(_selectedLayerKey || "");
        if (!key) {
            return;
        }
        var node = flattenGroupTreeContainerElement.querySelector('[data-layer-key="' + key + '"]');
        if (!node) {
            return;
        }
        // 可能刚刚发生过重渲染（filter/refresh），DOM 里的 selected class 会丢失。
        // 这里强制重置并重新高亮，保证“切回 Tab 立即看到高亮”。
        var prevSelected = flattenGroupTreeContainerElement.querySelectorAll(".wb-tree-item.selected");
        for (var i = 0; i < prevSelected.length; i++) {
            var p = prevSelected[i];
            if (p && p.classList) {
                p.classList.remove("selected");
            }
        }
        if (node.classList) {
            node.classList.add("selected");
        }
        // 确保父 details 展开
        var parent = node.parentElement;
        while (parent) {
            if (parent.tagName && String(parent.tagName).toLowerCase() === "details") {
                parent.open = true;
                break;
            }
            parent = parent.parentElement;
        }
        if (node.scrollIntoView) {
            node.scrollIntoView({ block: "center" });
        }
    }

    function _sanitizeTreeText(raw) {
        var s = String(raw || "").trim();
        if (!s) {
            return "";
        }
        if (s.length > 140) {
            return s.slice(0, 140) + "...";
        }
        return s;
    }

    function _normalizeInlineText(raw) {
        var s = String(raw || "").trim().replace(/\s+/g, " ");
        if (!s) return "";
        if (s.length > 40) {
            s = s.slice(0, 40) + "...";
        }
        return s;
    }

    function _isButtonLikeSource(source) {
        if (!source) return false;
        // 工程约定：大量“按钮外观”使用 `.btn` 容器（非原生 <button>），这里也视作按钮类组件。
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
        // 兜底：真实 <button data-ui-key="...">
        var tag = String(source.tagName || "").trim().toLowerCase();
        if (tag === "button" && String(attrs.dataUiKey || "").trim()) return true;
        return false;
    }

    function _inferAtomicGroupKeyForTree(source) {
        // 关键：分组树的 groupKey 必须与导出/写回端完全一致，避免“树里看到的组 key ≠ 写回端按 __html_component_key 分组”。
        // 统一复用导出侧 `ui_export/keys.js` 的规则实现，避免复制式一致性。
        return buildStableHtmlComponentKeyWithPrefix(source, _uiKeyPrefix);
    }

    function _inferDisplayNameForTree(source) {
        if (!source) {
            return "";
        }
        var attrs = source.attributes || null;
        // 关键：按钮/按钮组件优先用“按钮文本”作为可读名（比 e30 / id 更直观）。
        // - componentOwnerDataDebugLabel 在 dom_extract 中会对 `.btn` 无显式 key 的场景用 owner.textContent 兜底生成。
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
        // 常见命名：btn_exit / __btn_exit / button_xxx
        return gk.indexOf("btn_") >= 0 || gk.indexOf("__btn") >= 0 || gk.indexOf("button") >= 0;
    }

    function _deriveGroupDisplayTitle(groupEntry) {
        if (!groupEntry) return "";
        var base = String(groupEntry.name || groupEntry.key || "").trim();
        var items = groupEntry.items || [];

        function isBadCandidate(text) {
            var s = String(text || "");
            if (!s) return true;
            // 过滤模板变量/占位符等噪音
            if (s.indexOf("{{") >= 0) return true;
            if (s.indexOf("}}") >= 0) return true;
            return false;
        }

        function scoreCandidate(text) {
            var s = String(text || "");
            if (!s) return -1;
            // 倾向短标签：按钮文字/页签名通常比较短
            if (s.length > 18) return -1;
            if (isBadCandidate(s)) return -1;
            var cjk = (s.match(/[\u4e00-\u9fff]/g) || []).length;
            // 分数：优先中文，其次长度
            return cjk * 10 + Math.min(18, s.length);
        }

        // 从组内各层尝试抽取“可读短文本”（优先 text layer 的 fullTextContent）
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
            // textSnippet 作为备选（已截断）
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

        // 更强触发：看起来像按钮组 key 时，即便较长也允许（例如“开始挑战”）
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
        // Inline SVG: eye + optional slash. Keep tiny to avoid layout jitter.
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

    function _ensureExpandedStateFromDom(target) {
        var details = target && target.closest ? target.closest("details") : null;
        if (!details) return;
        var gk = details.dataset ? String(details.dataset.groupKey || "") : "";
        var isUngrouped = !gk;
        var willOpen = !details.open;
        details.open = willOpen;
        if (isUngrouped) {
            _expandedUngrouped = willOpen;
            return;
        }
        if (willOpen) _expandedGroupKeySet.add(gk);
        else _expandedGroupKeySet.delete(gk);
    }

    function _renderFlattenGroupTree(layerList, canvasSizeKey) {
        if (!flattenGroupTreeContainerElement) {
            return;
        }
        var layers = layerList || [];
        if (!layers || layers.length <= 0) {
            // UX：不要让“空”看起来像正常状态，否则用户会误以为扁平化成功但只是“没东西”。
            // 这里给出明确提示：分组树依赖扁平化提取得到的 layerList；若为空通常表示提取失败或被误判剔除。
            flattenGroupTreeContainerElement.innerHTML = [
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
            if (flattenGroupTreeStatusTextElement) {
                flattenGroupTreeStatusTextElement.textContent = "空";
            }
            return;
        }

        _groupKeyByLayerKey = new Map();
        _layerEntriesByGroupKey = new Map();
        _groupDisplayNameByKey = new Map();
        var groups = new Map(); // groupKey -> { key, name, items: [], bounds: {minX,minY,maxX,maxY} }
        var singletons = []; // items without groupKey

        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            if (!layer || !layer.rect) {
                continue;
            }
            var src = layer.source || null;
            var gk = _inferAtomicGroupKeyForTree(src);
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
                    if (String(layer.kind || "") !== "text") {
                        return "";
                    }
                    var src2 = layer.source || null;
                    var raw = src2 && src2.textContent ? String(src2.textContent || "").trim() : "";
                    if (!raw) {
                        return "";
                    }
                    raw = raw.replace(/\s+/g, " ");
                    if (raw.length > 30) {
                        raw = raw.slice(0, 30) + "...";
                    }
                    return raw;
                })(),
            };
            if (enableVisibilityToggles && item.layerKey && gk) {
                _groupKeyByLayerKey.set(String(item.layerKey || ""), String(gk || ""));
                var arr = _layerEntriesByGroupKey.has(String(gk || "")) ? _layerEntriesByGroupKey.get(String(gk || "")) : null;
                if (!arr) {
                    arr = [];
                    _layerEntriesByGroupKey.set(String(gk || ""), arr);
                }
                arr.push({ layerKey: String(item.layerKey || ""), rect: item.rect });
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
                    bounds: { minX: left, minY: top, maxX: right, maxY: bottom }
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
            // 视觉顺序：先按 top，再按 left
            if (a.bounds.minY !== b.bounds.minY) return a.bounds.minY - b.bounds.minY;
            return a.bounds.minX - b.bounds.minX;
        });

        groupList.forEach(function (g) {
            g.items.sort(function (a, b) {
                // 组内：z 越大越靠上
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

        var q = String(_treeFilterText || "").trim().toLowerCase();
        function _matchText(s) {
            if (!q) return true;
            return String(s || "").toLowerCase().indexOf(q) >= 0;
        }

        for (var gi = 0; gi < groupList.length; gi++) {
            var g0 = groupList[gi];
            var count = g0.items.length;
            var willGroup = count >= 2;
            var tagHtml = willGroup ? '<span class="tag">组</span>' : '<span class="tag warn">单项</span>';
            var derivedTitle = _deriveGroupDisplayTitle(g0);
            var title = _sanitizeTreeText(derivedTitle || g0.name || g0.key);
            _groupDisplayNameByKey.set(String(g0.key || ""), String(title || ""));
            // 注意：不要命名为 isGroupHidden（会遮蔽同名函数，导致运行时 TypeError）
            var groupIsHidden = enableVisibilityToggles && isGroupHidden(String(g0.key || ""));
            // filter: keep group if group title matches, or any item matches
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
                    if (!anyHit) {
                        continue;
                    }
                }
            }

            // 单项：不要使用“组块(details)”包裹，直接渲染为一个普通条目
            if (!willGroup) {
                var it0 = g0.items && g0.items.length > 0 ? g0.items[0] : null;
                if (!it0 || !it0.layerKey) {
                    continue;
                }
                var isHidden0 = enableVisibilityToggles && _isLayerHidden(it0.layerKey);
                var isExcluded0 = enableExportExcludeToggles && _isLayerExcluded(it0.layerKey);
                var toggle0 = enableVisibilityToggles
                    ? (
                        '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="layer" data-layer-key="' + _escapeHtml(String(it0.layerKey || "")) + '" aria-label="' + (isHidden0 ? "显示" : "隐藏") + '" title="' + (isHidden0 ? "点击显示" : "点击隐藏") + '">' +
                        _buildEyeIconHtml(isHidden0) +
                        "</button>"
                    )
                    : "";
                var trash0 = enableExportExcludeToggles
                    ? (
                        '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="layer" data-toggle-action="exclude" data-layer-key="' + _escapeHtml(String(it0.layerKey || "")) + '" aria-label="' + (isExcluded0 ? "取消排除" : "排除导出") + '" title="' + (isExcluded0 ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
                        _buildTrashIconHtml(isExcluded0) +
                        "</button>"
                    )
                    : "";
                var label0 = (it0.debugLabel ? it0.debugLabel : it0.kind);
                if (String(it0.kind || "") === "text" && it0.textSnippet) {
                    label0 = label0 + " 「" + String(it0.textSnippet || "") + "」";
                }
                if (q && !_matchText(label0) && !_matchText(it0.displayName) && !_matchText(it0.kind) && !_matchText(it0.textSnippet) && !_matchText(title)) {
                    continue;
                }
                htmlParts.push(
                    '<div class="wb-tree-item" role="button" tabindex="0" data-layer-key="' + _escapeHtml(String(it0.layerKey || "")) + '">' +
                    toggle0 +
                    trash0 +
                    '<span class="wb-tree-item-main">' +
                    '<span class="muted">[' + _escapeHtml(String(it0.kind || "")) + " z" + String(Math.round(it0.z)) + "]</span> " +
                    _escapeHtml(_sanitizeTreeText(title || label0)) +
                    "</span>" +
                    "</div>"
                );
                continue;
            }

            var shouldOpen = _expandedGroupKeySet.has(String(g0.key || "")) ? true : willGroup;
            var groupEyeHtml = enableVisibilityToggles
                ? (
                    '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="group" data-group-key="' + _escapeHtml(String(g0.key || "")) + '" aria-label="' + (groupIsHidden ? "显示" : "隐藏") + '" title="' + (groupIsHidden ? "点击显示" : "点击隐藏") + '">' +
                    _buildEyeIconHtml(groupIsHidden) +
                    "</button>"
                )
                : "";
            var isGroupExcluded = enableExportExcludeToggles && _excludedGroupKeySet.has(String(g0.key || ""));
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
            htmlParts.push('<details ' + (shouldOpen ? "open" : "") + ' data-group-key="' + _escapeHtml(String(g0.key || "")) + '"' + (_selectedGroupKey === String(g0.key || "") ? ' class="wb-tree-group-selected"' : "") + '>');
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
                var isLayerHidden = enableVisibilityToggles && _isLayerHidden(it.layerKey);
                var isLayerExcluded = enableExportExcludeToggles && _isLayerExcluded(it.layerKey);
                var toggleHtml = enableVisibilityToggles
                    ? (
                        '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="layer" data-layer-key="' + _escapeHtml(String(it.layerKey || "")) + '" aria-label="' + (isLayerHidden ? "显示" : "隐藏") + '" title="' + (isLayerHidden ? "点击显示" : "点击隐藏") + '">' +
                        _buildEyeIconHtml(isLayerHidden) +
                        "</button>"
                    )
                    : "";
                var trashHtml = enableExportExcludeToggles
                    ? (
                        '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="layer" data-toggle-action="exclude" data-layer-key="' + _escapeHtml(String(it.layerKey || "")) + '" aria-label="' + (isLayerExcluded ? "取消排除" : "排除导出") + '" title="' + (isLayerExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
                        _buildTrashIconHtml(isLayerExcluded) +
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
            htmlParts.push('<details ' + (_expandedUngrouped ? "open" : "") + ">");
            var expander2 = '<button type="button" class="wb-tree-expander" data-expander="1" aria-label="展开/折叠" title="展开/折叠"></button>';
            htmlParts.push('<summary><span class="wb-tree-row">' + expander2 + '<span class="tag warn">未归组</span> <span class="wb-tree-meta">(' + String(singletons.length) + ")</span></span></summary>");
            htmlParts.push('<div class="wb-tree-children">');
            for (var si = 0; si < singletons.length; si++) {
                var sIt = singletons[si];
                var sHidden = enableVisibilityToggles && _isLayerHidden(sIt.layerKey);
                var sExcluded = enableExportExcludeToggles && _isLayerExcluded(sIt.layerKey);
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

        flattenGroupTreeContainerElement.innerHTML = htmlParts.join("\n");
        if (flattenGroupTreeStatusTextElement) {
            flattenGroupTreeStatusTextElement.textContent = "已生成";
        }
    }

    async function refresh() {
        if (!getHtmlText) {
            return;
        }
        var htmlText = String(getHtmlText() || "");
        if (!String(htmlText || "").trim()) {
            if (flattenGroupTreeContainerElement) {
                flattenGroupTreeContainerElement.innerHTML = "";
            }
            if (flattenGroupTreeStatusTextElement) {
                flattenGroupTreeStatusTextElement.textContent = "空输入";
            }
            return;
        }

        // IMPORTANT:
        // Group tree refresh must NOT mutate visible preview variant (source/flattened).
        // Use compute iframe for layer extraction to avoid "click flattened -> refresh -> forced back to source".
        var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(htmlText);
        if (!isComputeReady) {
            if (flattenGroupTreeStatusTextElement) {
                flattenGroupTreeStatusTextElement.textContent = "计算预览未就绪（compute 文档为空）";
            }
            return;
        }

        var selectedCanvasSizeKey = preview.getCurrentSelectedCanvasSizeKey();
        var selectedCanvasSizeOption = getCanvasSizeByKey(selectedCanvasSizeKey);
        // Keep visible stage scale aligned (selection overlay depends on it), but do not re-render srcdoc.
        preview.updatePreviewStageScale(selectedCanvasSizeOption);
        if (preview.getPreviewDocument()) {
            preview.applyCanvasSizeToPreviewDocument(preview.getPreviewDocument(), selectedCanvasSizeOption);
        }

        // Compute iframe: must apply canvas size for vw/vh/clamp() etc.
        var computeDoc = preview.getComputePreviewDocument();
        if (!computeDoc || !computeDoc.body) {
            if (flattenGroupTreeStatusTextElement) {
                flattenGroupTreeStatusTextElement.textContent = "计算预览为空（请刷新页面重试）";
            }
            _renderFlattenGroupTree([], selectedCanvasSizeKey);
            _indexFlattenedPreviewElements();
            return;
        }
        if (preview.setComputePreviewCanvasSize) {
            preview.setComputePreviewCanvasSize(selectedCanvasSizeOption);
        }
        preview.applyCanvasSizeToPreviewDocument(computeDoc, selectedCanvasSizeOption);
        await waitForNextFrame();
        await waitForNextFrame();

        var elementsData = extractDisplayElementsData(computeDoc);
        var allowFallbackToPreviewDoc = canFallbackToVisiblePreviewDocument(preview, selectedCanvasSizeKey);
        var previewDocForFallback = (allowFallbackToPreviewDoc && preview.getPreviewDocument) ? preview.getPreviewDocument() : null;
        var r0 = await extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback({
            extractDisplayElementsData: extractDisplayElementsData,
            computeDoc: computeDoc,
            initialComputeElementsData: elementsData,
            previewDoc: previewDocForFallback,
            allowFallback: allowFallbackToPreviewDoc
        });
        elementsData = r0.elementsData;
        var layerList = buildFlattenedLayerData(elementsData, {
            debug_show_all_controls: !!(dom.flattenDebugShowAllCheckboxElement && dom.flattenDebugShowAllCheckboxElement.checked),
        });
        _lastLayerList = layerList;
        _lastCanvasSizeKey = selectedCanvasSizeKey;
        _renderFlattenGroupTree(layerList, selectedCanvasSizeKey);
        _indexFlattenedPreviewElements();
    }

    async function handleTreeClick(event, opts) {
        var options = opts || {};
        var ensureFlattened = options.ensureFlattened;
        var previewVariant = options.previewVariant;
        var previewVariantFlattened = options.previewVariantFlattened;

        var target = event && event.target ? event.target : null;
        if (!target) {
            return;
        }

        // explicit expander: keep expanded state stable across re-render
        var expander = target.closest ? target.closest(".wb-tree-expander[data-expander]") : null;
        if (expander) {
            _ensureExpandedStateFromDom(expander);
            if (event && event.preventDefault) event.preventDefault();
            if (event && event.stopPropagation) event.stopPropagation();
            return;
        }

        var toggleNode = target.closest ? target.closest(".wb-tree-toggle[data-toggle-kind]") : null;
        if (toggleNode && toggleNode.dataset) {
            var toggleAction = String(toggleNode.dataset.toggleAction || "hide");
            var toggleKind = String(toggleNode.dataset.toggleKind || "");
            if (toggleAction === "exclude") {
                // 说明：分组树的显隐/排除开关只对“扁平化预览层（.flat-*)”生效。
                // 若用户当前停留在“原稿预览”，这里必须先切到扁平化，否则会出现：
                // - 列表里的眼睛/垃圾桶图标状态变了
                // - 但画布没有任何变化（因为预览文档没有 .flat-display-area/.flat-* 可操作）
                if (ensureFlattened) {
                    if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
                        await ensureFlattened();
                    }
                }
                if (toggleKind === "group") {
                    var gkEx = String(toggleNode.dataset.groupKey || "");
                    _toggleGroupExcluded(gkEx);
                } else if (toggleKind === "layer") {
                    var lkEx = String(toggleNode.dataset.layerKey || "");
                    _toggleLayerExcluded(lkEx);
                }
                if (_lastLayerList) {
                    _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
                    _indexFlattenedPreviewElements();
                }
                if (event && event.preventDefault) event.preventDefault();
                if (event && event.stopPropagation) event.stopPropagation();
                return;
            }
            if (enableVisibilityToggles) {
                if (ensureFlattened) {
                    if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
                        await ensureFlattened();
                    }
                }
                if (toggleKind === "group") {
                    var gk = String(toggleNode.dataset.groupKey || "");
                    _toggleGroupHidden(gk);
                    if (_lastLayerList) {
                        _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
                        _indexFlattenedPreviewElements();
                    }
                } else if (toggleKind === "layer") {
                    var lk = String(toggleNode.dataset.layerKey || "");
                    _toggleLayerHidden(lk);
                    if (_lastLayerList) {
                        _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
                        _indexFlattenedPreviewElements();
                    }
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
                            await ensureFlattened();
                        }
                    }
                    _indexFlattenedPreviewElements();
                    var entries = _layerEntriesByGroupKey.has(gkSel) ? _layerEntriesByGroupKey.get(gkSel) : null;
                    var picked = null;
                    if (entries && entries.length > 0) {
                        for (var i = 0; i < entries.length; i++) {
                            var lk = String(entries[i].layerKey || "");
                            if (!lk) continue;
                            if (enableVisibilityToggles && _isLayerHidden(lk)) continue;
                            picked = lk;
                            break;
                        }
                        if (!picked) {
                            picked = String(entries[0].layerKey || "");
                        }
                    }
                    if (picked) {
                        var el = _findPreviewElementByLayerKey(picked);
                        if (el) {
                            preview.selectPreviewElement(el);
                            _highlightTreeGroupByGroupKey(gkSel);
                            _highlightTreeItemByLayerKey(picked, { scroll_into_view: false });
                        }
                    } else {
                        _highlightTreeGroupByGroupKey(gkSel);
                    }
                    if (event && event.preventDefault) event.preventDefault();
                    if (event && event.stopPropagation) event.stopPropagation();
                    return;
                }
            }
        }
        var node = target.closest ? target.closest(".wb-tree-item[data-layer-key]") : null;
        if (!node) {
            return;
        }
        var key = node.dataset ? String(node.dataset.layerKey || "") : "";
        if (!key) {
            return;
        }

        if (ensureFlattened) {
            if (previewVariant && previewVariantFlattened && previewVariant.getCurrentPreviewVariant() !== previewVariantFlattened) {
                await ensureFlattened();
            }
        }

        _indexFlattenedPreviewElements();
        var el = _findPreviewElementByLayerKey(key);
        if (!el) {
            return;
        }
        preview.selectPreviewElement(el);
        // 列表点击：只高亮，不做“把条目滚到列表中间”
        _highlightTreeItemByLayerKey(key, { scroll_into_view: false });
    }

    function handlePreviewSelectionChanged(payload) {
        var p = payload || {};
        var kind = String(p.kind || "");
        if (kind !== "element") {
            _clearTreeSelectionHighlight();
            return;
        }
        var el = p.element || null;
        if (!el) {
            _clearTreeSelectionHighlight();
            return;
        }
        var key = el.dataset && el.dataset.layerKey ? String(el.dataset.layerKey || "") : "";
        if (!key) {
            key = _buildLayerKeyFromDomElement(el);
        }
        if (!key) {
            _clearTreeSelectionHighlight();
            return;
        }
        function _findTreeNodeByLayerKeySafe(lk) {
            if (!flattenGroupTreeContainerElement) return null;
            var k = String(lk || "");
            if (!k) return null;
            var ns = flattenGroupTreeContainerElement.querySelectorAll("[data-layer-key]");
            for (var i = 0; i < ns.length; i++) {
                var n = ns[i];
                if (!n || !n.getAttribute) continue;
                if (String(n.getAttribute("data-layer-key") || "") === k) {
                    return n;
                }
            }
            return null;
        }
        function _pickNearestTreeKeyByRect(snap, requireSameKind) {
            if (!flattenGroupTreeContainerElement || !snap) return "";
            var nodes = flattenGroupTreeContainerElement.querySelectorAll(".wb-tree-item[data-layer-key]");
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
            if (!flattenGroupTreeContainerElement || !snap) return "";
            var dbg = String(debugLabelBase || "").trim();
            if (!dbg) return "";
            var nodes = flattenGroupTreeContainerElement.querySelectorAll(".wb-tree-item[data-layer-key]");
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
            // 目的：当同一 debug label 出现多次（例如多个“text-level-name”），仅靠 rect 最近邻可能会错匹配。
            // 这里额外要求“树条目文本包含该层的 textContent（例如 第4关）”，优先保证语义一致性。
            if (!flattenGroupTreeContainerElement || !snap) return "";
            var dbg = String(debugLabelBase || "").trim();
            if (!dbg) return "";
            var needle = String(textNeedle || "").trim();
            if (!needle) return "";
            // 避免极端长文本导致 contains 过慢/误命中；这里只用于短标签类文本（关卡名/按钮字）。
            if (needle.length > 64) {
                needle = needle.slice(0, 64);
            }
            var nodes = flattenGroupTreeContainerElement.querySelectorAll(".wb-tree-item[data-layer-key]");
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
        // 兼容：在少数链路下，“画布点选的 layerKey”可能与“分组树 layerList 渲染出来的 data-layer-key”
        // 出现轻微漂移（例如不同管线的舍入/偏移口径不一致）。
        // 若直接 key 在树里找不到，则按 kind+rect 做一次受控匹配，尽量命中“最接近的条目”，避免出现：
        // - 检查器已更新（说明点选成功）
        // - 但左下分组树不高亮/不滚动（体验上等价于联动失效）
        if (flattenGroupTreeContainerElement) {
            var directNode = _findTreeNodeByLayerKeySafe(key);
            if (!directNode) {
                var snap = _getDomLayerSnapshotForMatch(el);
                if (snap && _lastLayerList && Array.isArray(_lastLayerList) && _lastLayerList.length > 0) {
                    var eps = 0.6; // 与 _findPreviewElementByLayerKey 的容差对齐（px）
                    var bestKey = "";
                    var bestMetric = Number.POSITIVE_INFINITY;
                    for (var i = 0; i < _lastLayerList.length; i++) {
                        var layer = _lastLayerList[i];
                        if (!layer || !layer.rect) continue;
                        var lk = String(layer.kind || "");
                        if (lk !== String(snap.kind || "")) continue;
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
                        if (dz < bestMetric) {
                            bestMetric = dz;
                            bestKey = _buildLayerKeyFromLayer(layer);
                        }
                    }
                    if (bestKey) {
                        key = bestKey;
                    }
                }
                // 兜底：若 layerList 口径仍无法对齐（极端情况下 compute 与预览的 rect 口径漂移），
                // 在“树 DOM”里做最近邻匹配：
                // - 优先同 kind（text/element/border/shadow...）
                // - 若同 kind 找不到（例如树里没有 text 层、但画布点到 text），允许降级到“不限 kind”的最近邻，
                //   仍保证用户能看到“跳转高亮”（对应内容不至于完全无响应）。
                var stillMissing = _findTreeNodeByLayerKeySafe(key);
                if (!stillMissing) {
                    var snap2 = snap ? snap : _getDomLayerSnapshotForMatch(el);
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

                        // 1) 同 kind + debug label + textContent（用于区分重复 label：多个 level-name）
                        var bestKey2 = (dbg && elText) ? _pickNearestTreeKeyByRectWithDebugLabelAndText(snap2, true, dbg, elText) : "";
                        // 2) 同 kind + debug label（用于区分重叠文本：name vs author）
                        if (!bestKey2) bestKey2 = dbg ? _pickNearestTreeKeyByRectWithDebugLabel(snap2, true, dbg) : "";
                        // 2) 同 kind（无 label 或 label 不存在于树文本）
                        if (!bestKey2) bestKey2 = _pickNearestTreeKeyByRect(snap2, true);
                        // 3) 不限 kind + debug label + textContent
                        if (!bestKey2 && dbg && elText) bestKey2 = _pickNearestTreeKeyByRectWithDebugLabelAndText(snap2, false, dbg, elText);
                        // 4) 不限 kind + debug label
                        if (!bestKey2 && dbg) bestKey2 = _pickNearestTreeKeyByRectWithDebugLabel(snap2, false, dbg);
                        // 4) 不限 kind（最后兜底）
                        if (!bestKey2) bestKey2 = _pickNearestTreeKeyByRect(snap2, false);
                        if (bestKey2) {
                            key = bestKey2;
                        }
                    }
                }
            }
        }
        // 画布点击：让列表跟随并居中（方便定位）
        _highlightTreeItemByLayerKey(key, { scroll_into_view: true });
    }

    function indexFlattenedPreviewElements() {
        _indexFlattenedPreviewElements();
    }

    function setFilterText(text) {
        _treeFilterText = String(text || "").trim();
        if (_lastLayerList) {
            _renderFlattenGroupTree(_lastLayerList, _lastCanvasSizeKey);
            _indexFlattenedPreviewElements();
        }
    }

    function getGroupDisplayName(groupKey) {
        var gk = String(groupKey || "").trim();
        if (!gk) return "";
        return _groupDisplayNameByKey.has(gk) ? String(_groupDisplayNameByKey.get(gk) || "") : "";
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

