import { escapeHtmlText } from "../utils.js";
import { buildStableHtmlComponentKeyWithPrefix } from "../ui_export/keys.js";

function _hashHueFromText(text) {
    var s = String(text || "");
    var h = 0;
    for (var i = 0; i < s.length; i++) {
        h = (h * 31 + s.charCodeAt(i)) >>> 0;
    }
    return Number(h % 360);
}

function _inferAtomicGroupKeyForDebug(source, uiKeyPrefix) {
    // 目标：让 Workbench 的“分组标注”与导出/写回端完全一致，避免复制式一致性。
    return buildStableHtmlComponentKeyWithPrefix(source, uiKeyPrefix);
}

export function buildFlattenedGroupDebugOverlayHtml(sortedItems, sizeKey, uiKeyPrefix) {
    var items = sortedItems || [];
    if (!items || items.length <= 0) {
        return "";
    }
    var prefixText = String(uiKeyPrefix || "").trim();

    // groupKey -> { left, top, right, bottom, count }
    var groupBounds = new Map();
    for (var i = 0; i < items.length; i++) {
        var it = items[i];
        if (!it || !it.rect) {
            continue;
        }
        var gk = _inferAtomicGroupKeyForDebug(it.source || null, prefixText);
        if (!gk) {
            continue;
        }
        var left = Number(it.rect.left || 0);
        var top = Number(it.rect.top || 0);
        var right = left + Number(it.rect.width || 0);
        var bottom = top + Number(it.rect.height || 0);
        var prev = groupBounds.get(gk);
        if (!prev) {
            groupBounds.set(gk, { left: left, top: top, right: right, bottom: bottom, count: 1 });
        } else {
            prev.left = Math.min(prev.left, left);
            prev.top = Math.min(prev.top, top);
            prev.right = Math.max(prev.right, right);
            prev.bottom = Math.max(prev.bottom, bottom);
            prev.count = (prev.count || 0) + 1;
        }
    }

    var overlayList = [];

    // 1) 每个 layer 的小框（显示属于哪个 groupKey）
    for (var j = 0; j < items.length; j++) {
        var item = items[j];
        if (!item || !item.rect) {
            continue;
        }
        var groupKey = _inferAtomicGroupKeyForDebug(item.source || null, prefixText);
        var label = (String(item.kind || "") || "layer") + " | " + (groupKey || "(no-group)");
        var hue = _hashHueFromText(groupKey || String(item.kind || ""));
        var color = "hsl(" + String(hue) + ", 80%, 55%)";
        var z = Number(item.z || 0);
        var boxZ = 100000 + z;
        overlayList.push(
            '<div class="flat-debug-box debug-target size-' + String(sizeKey || "") + '" style="' +
            [
                "left: " + Number(item.rect.left || 0).toFixed(2) + "px",
                "top: " + Number(item.rect.top || 0).toFixed(2) + "px",
                "width: " + Math.max(0, Number(item.rect.width || 0)).toFixed(2) + "px",
                "height: " + Math.max(0, Number(item.rect.height || 0)).toFixed(2) + "px",
                "border-color: " + color,
                "z-index: " + boxZ
            ].join("; ") + ';" data-debug-label="dbg-layer">' +
            '<div class="flat-debug-label" style="background:' + color + ';">' + escapeHtmlText(label) + "</div>" +
            "</div>"
        );
    }

    // 2) 每个 group 的包围盒（只画 count>=2 的组，避免噪声）
    groupBounds.forEach(function (b, gk) {
        if (!b || (b.count || 0) < 2) {
            return;
        }
        var hue = _hashHueFromText(gk);
        var color = "hsl(" + String(hue) + ", 80%, 65%)";
        overlayList.push(
            '<div class="flat-debug-group-box debug-target size-' + String(sizeKey || "") + '" style="' +
            [
                "left: " + Number(b.left || 0).toFixed(2) + "px",
                "top: " + Number(b.top || 0).toFixed(2) + "px",
                "width: " + Math.max(0, Number((b.right || 0) - (b.left || 0))).toFixed(2) + "px",
                "height: " + Math.max(0, Number((b.bottom || 0) - (b.top || 0))).toFixed(2) + "px",
                "outline-color: " + color,
                "z-index: 200000"
            ].join("; ") + ';" data-debug-label="dbg-group">' +
            '<div class="flat-debug-label flat-debug-group-label" style="background:' + color + ';">' +
            escapeHtmlText("GROUP(" + String(b.count || 0) + "): " + String(gk || "")) +
            "</div>" +
            "</div>"
        );
    });

    return overlayList.join("\n");
}

