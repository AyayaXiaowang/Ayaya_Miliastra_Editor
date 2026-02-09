import { isTransparentColor } from "../colors.js";
import { buildDenseSamplePointsForRect, rectContainsPoint } from "./rects.js";

function _parseOpacityValue(styleValue) {
    var raw = String(styleValue || "").trim();
    if (!raw) {
        return 1;
    }
    var num = Number(raw);
    if (!isFinite(num)) {
        return 1;
    }
    return num;
}

function _extractColorTokenFromBorderText(borderText) {
    var raw = String(borderText || "").trim();
    if (!raw) {
        return "";
    }
    var match = raw.match(/(rgba?\([^)]+\)|hsla?\([^)]+\)|#[0-9a-fA-F]{3,8}|transparent)$/i);
    if (match && match[1]) {
        return String(match[1]);
    }
    return "";
}

function _resolveBorderColor(styles, sideName) {
    if (!styles) {
        return "";
    }
    var keyColor = "border" + sideName + "Color";
    var directColor = styles[keyColor];
    if (directColor) {
        return String(directColor || "");
    }
    var keyText = "border" + sideName;
    return _extractColorTokenFromBorderText(styles[keyText] || "");
}

function _hasVisibleBorderColor(styles) {
    if (!styles) {
        return false;
    }
    var sides = ["Top", "Right", "Bottom", "Left"];
    for (var i = 0; i < sides.length; i++) {
        var side = sides[i];
        var widthValue = Number(String(styles["border" + side + "Width"] || "0").replace("px", ""));
        if (!isFinite(widthValue) || widthValue <= 0) {
            continue;
        }
        var colorText = _resolveBorderColor(styles, side);
        if (!isTransparentColor(colorText || "transparent")) {
            return true;
        }
    }
    return false;
}

function _hasVisibleBackground(styles) {
    if (!styles) {
        return false;
    }
    var backgroundColor = styles.backgroundColor || "transparent";
    var backgroundImage = String(styles.backgroundImage || "").trim();
    if (!isTransparentColor(backgroundColor)) {
        return true;
    }
    if (backgroundImage && backgroundImage !== "none") {
        return true;
    }
    return false;
}

function _isOpaqueOccluderItem(item) {
    // 规则（按需求）：
    // - 阴影为半透明：不能盖住任何东西 -> 不参与遮挡判定
    // - 文本同理：不应被视为“遮挡体”
    // - 只有“实体矩形”（element/border）才作为遮挡体
    // - 需要考虑可见性/透明度，避免“透明容器误遮挡”
    if (!item) {
        return false;
    }
    var kind = String(item.kind || "");
    if (kind !== "element" && kind !== "border") {
        return false;
    }
    var source = item.source || null;
    var styles = source ? (source.styles || null) : null;
    if (!styles) {
        return true;
    }
    var opacity = _parseOpacityValue(styles.opacity);
    if (opacity <= 0.01) {
        return false;
    }
    var visibility = String(styles.visibility || "").trim().toLowerCase();
    if (visibility === "hidden") {
        return false;
    }
    if (kind === "border") {
        return _hasVisibleBorderColor(styles);
    }
    return _hasVisibleBackground(styles);
}

function _buildGroupKey(item) {
    // 组内元素（本体/边框/阴影/文本）必须视作一个整体，不允许相互剔除。
    // groupKey 以 elementIndex 为主；缺失则回退为空（不做组级剔除）。
    if (!item) {
        return "";
    }
    var k = String(item.groupKey || "");
    if (k) {
        return k;
    }
    if (item.source && Number.isFinite(item.source.elementIndex)) {
        return "e" + String(Math.trunc(item.source.elementIndex));
    }
    return "";
}

function _isUiStateItem(item) {
    if (!item) {
        return false;
    }
    var source = item.source || null;
    var attrs = source ? (source.attributes || null) : null;
    if (!attrs) {
        return false;
    }
    var group = String(attrs.dataUiStateGroup || "").trim();
    if (group) {
        return true;
    }
    var state = String(attrs.dataUiState || "").trim();
    if (state) {
        return true;
    }
    return false;
}

function _pickLargestOccluder(sortedItems, startIndexExclusive, rect, selfGroupKey) {
    if (!rect) {
        return null;
    }
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var best = null;
    var bestArea = -1;
    for (var j = startIndexExclusive; j < sortedItems.length; j++) {
        var upper = sortedItems[j];
        if (!upper || !upper.rect) {
            continue;
        }
        if (!_isOpaqueOccluderItem(upper)) {
            continue;
        }
        var upperGroupKey = _buildGroupKey(upper);
        if (selfGroupKey && upperGroupKey && upperGroupKey === selfGroupKey) {
            continue;
        }
        if (rectContainsPoint(upper.rect, cx, cy)) {
            var area = Number(upper.rect.width || 0) * Number(upper.rect.height || 0);
            if (isFinite(area) && area > bestArea) {
                bestArea = area;
                best = upper;
            }
        }
    }
    return best;
}

function _isRectFullyCoveredByOccluders(sortedItems, startIndexExclusive, rect, selfGroupKey) {
    var samples = buildDenseSamplePointsForRect(rect);
    if (samples.length <= 0) {
        return false;
    }
    for (var sp = 0; sp < samples.length; sp++) {
        var p = samples[sp];
        var covered = false;
        for (var j = startIndexExclusive; j < sortedItems.length; j++) {
            var upper = sortedItems[j];
            if (!upper || !upper.rect) {
                continue;
            }
            if (!_isOpaqueOccluderItem(upper)) {
                continue;
            }
            var upperGroupKey = _buildGroupKey(upper);
            if (selfGroupKey && upperGroupKey && upperGroupKey === selfGroupKey) {
                continue; // 组内不互相遮挡判定
            }
            if (rectContainsPoint(upper.rect, p.x, p.y)) {
                covered = true;
                break;
            }
        }
        if (!covered) {
            return false;
        }
    }
    return true;
}

export function pruneFullyOccludedGroups(sortedItems) {
    // 注意：按产品策略 **彻底禁用遮挡剔除**。
    // 遮挡剔除属于“降噪优化”，但会对交互语义锚点（button_anchor）与多状态层（data-ui-state-group）
    // 造成灾难性副作用（导出丢交互/丢非默认态模板）。正确性优先，这里恒等返回。
    return sortedItems || [];

    // 先把 item 归组：同一 elementIndex 的 shadow/border/element/text 视为整体。
    var itemsByGroup = new Map(); // groupKey -> [{ item, index }]
    var protectedGroupKeySet = new Set(); // groupKey -> never drop (semantic anchors / ui-state variants)
    for (var i = 0; i < input.length; i++) {
        var it = input[i];
        if (!it || !it.rect) {
            continue;
        }
        var gk = _buildGroupKey(it);
        if (!gk) {
            // 无 groupKey：不参与组级剔除，直接保留
            continue;
        }
        // 关键：这些组不允许被遮挡剔除（即使视觉上被完全覆盖）：
        // - button_anchor：按钮语义锚点（交互语义必须保留）
        // - ui-state 变体意味着“同一控件的多状态（normal/selected/disabled...）”，必须保留
        //   否则导出会丢失非默认态模板，后续状态切换无从谈起。
        if (String(it.kind || "") === "button_anchor" || _isUiStateItem(it)) {
            protectedGroupKeySet.add(gk);
        }
        var bucket = itemsByGroup.get(gk);
        if (!bucket) {
            bucket = [];
            itemsByGroup.set(gk, bucket);
        }
        bucket.push({ item: it, index: i });
    }

    var droppedGroupKeySet = new Set();
    var droppedInfoList = [];
    itemsByGroup.forEach(function (bucket, groupKey) {
        if (protectedGroupKeySet.has(groupKey)) {
            return;
        }
        // 判定：只有当“该组内所有矩形层”都被上层其它组的实体矩形完全覆盖，才丢弃整组。
        // 这样保证“本体/边框/阴影/文字是一个整体，不相互剔除”。
        var allItemsCovered = true;
        var sampleOccluder = null;
        var sampleRect = null;
        for (var bi = 0; bi < bucket.length; bi++) {
            var entry = bucket[bi];
            var item = entry.item;
            var idx = entry.index;
            if (!_isRectFullyCoveredByOccluders(input, idx + 1, item.rect, groupKey)) {
                allItemsCovered = false;
                break;
            }
            if (!sampleRect && item && item.rect) {
                sampleRect = item.rect;
            }
            if (!sampleOccluder) {
                sampleOccluder = _pickLargestOccluder(input, idx + 1, item.rect, groupKey);
            }
        }
        if (allItemsCovered) {
            droppedGroupKeySet.add(String(groupKey || ""));
            droppedInfoList.push({
                groupKey: String(groupKey || ""),
                sampleRect: sampleRect || null,
                occluder: sampleOccluder ? {
                    groupKey: _buildGroupKey(sampleOccluder),
                    rect: sampleOccluder.rect || null,
                    kind: String(sampleOccluder.kind || ""),
                    tag: sampleOccluder.source ? String(sampleOccluder.source.tagName || "") : "",
                    className: sampleOccluder.source ? String(sampleOccluder.source.className || "") : "",
                    id: sampleOccluder.source ? String(sampleOccluder.source.id || "") : ""
                } : null
            });
        }
    });

    if (debugInfo) {
        debugInfo.inputCount = input.length;
        debugInfo.groupCount = itemsByGroup.size;
        debugInfo.droppedGroups = droppedInfoList;
    }
    if (droppedGroupKeySet.size <= 0) {
        return input;
    }
    var kept = [];
    for (var k = 0; k < input.length; k++) {
        var item = input[k];
        if (!item || !item.rect) {
            continue;
        }
        var gk = _buildGroupKey(item);
        if (gk && droppedGroupKeySet.has(gk)) {
            continue;
        }
        kept.push(item);
    }
    // 兜底：若遮挡剔除导致全空，则视为误判并回退为“不剔除”。
    // 典型根因：z-index/舍入差异或异常 layer 顺序导致“上层遮挡体判定”被放大。
    if (kept.length <= 0) {
        if (debugInfo) {
            debugInfo.allPruned = true;
            debugInfo.note = "all pruned by occlusion; fallback to keep all input";
        }
        return input;
    }
    return kept;
}

