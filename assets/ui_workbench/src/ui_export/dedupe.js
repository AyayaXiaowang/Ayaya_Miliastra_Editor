import { sanitizeIdPart } from "./keys.js";

function buildStableRectSuffixFromWidget(widget) {
    if (!widget) {
        return "";
    }
    var pos = widget.position || null;
    var size = widget.size || null;
    if (!pos || !size || pos.length !== 2 || size.length !== 2) {
        return "";
    }
    var x = Number(pos[0]);
    var y = Number(pos[1]);
    var w = Number(size[0]);
    var h = Number(size[1]);
    if (!isFinite(x) || !isFinite(y) || !isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
        return "";
    }
    var ix = Math.round(x);
    var iy = Math.round(y);
    var iw = Math.round(w);
    var ih = Math.round(h);
    return "r" + String(ix) + "_" + String(iy) + "_" + String(iw) + "_" + String(ih);
}

function inferUiStateSuffixForUiKey(widget) {
    if (!widget) {
        return "";
    }
    var group = String(widget.__ui_state_group || "").trim();
    if (!group) {
        return "";
    }
    var state = String(widget.__ui_state || "").trim();
    var groupPart = sanitizeIdPart(group) || "state_group";
    var statePart = sanitizeIdPart(state) || "state";
    return "state_" + groupPart + "_" + statePart;
}

export function ensureUniqueUiKeysInWidgetList(widgetList, usedUiKeys) {
    if (!widgetList || widgetList.length <= 0) {
        return 0;
    }
    if (!usedUiKeys) {
        usedUiKeys = new Set();
    }
    var fixed = 0;
    for (var i = 0; i < widgetList.length; i++) {
        var w = widgetList[i] || null;
        if (!w) {
            continue;
        }
        var raw = String(w.ui_key || "").trim();
        if (!raw) {
            continue;
        }
        var key = raw;
        if (usedUiKeys.has(key)) {
            var rectSuffix = buildStableRectSuffixFromWidget(w);
            var stateSuffix = inferUiStateSuffixForUiKey(w);
            if (stateSuffix) {
                key = raw + "__" + stateSuffix + (rectSuffix ? ("__" + rectSuffix) : "");
            } else if (rectSuffix) {
                key = raw + "__" + rectSuffix;
            } else {
                key = raw + "__dup";
            }
            var counter = 2;
            while (usedUiKeys.has(key)) {
                key = (stateSuffix ? (raw + "__" + stateSuffix) : raw) + "__" + (rectSuffix ? rectSuffix : "dup") + "_" + String(counter);
                counter += 1;
            }
            w.ui_key = key;
            fixed += 1;
        }
        usedUiKeys.add(String(w.ui_key || raw));
    }
    return fixed;
}

