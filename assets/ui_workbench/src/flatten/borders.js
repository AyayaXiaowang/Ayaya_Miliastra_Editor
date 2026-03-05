export function parseBorder(borderText) {
    var borderValue = String(borderText || "").trim();
    if (!borderValue || borderValue === "none" || borderValue === "0px none") {
        return null;
    }
    var parts = borderValue.split(/\s+/).filter(function (part) { return part.trim().length > 0; });
    if (parts.length < 2) {
        return null;
    }
    var widthText = parts[0];
    var widthNumber = Number(String(widthText).replace("px", "").trim());
    if (!isFinite(widthNumber) || widthNumber <= 0) {
        return null;
    }
    var styleValue = parts[1] || "solid";
    if (styleValue === "none") {
        return null;
    }
    var colorValue = parts.length > 2 ? parts.slice(2).join(" ") : "#000000";
    return {
        width: widthNumber,
        style: styleValue,
        color: colorValue
    };
}

function _normalizeColorKey(colorText) {
    var trimmed = String(colorText || "").trim().toLowerCase();
    if (!trimmed) {
        return "";
    }
    return trimmed.replace(/\s+/g, "");
}

export function collectBorderColors(borders) {
    var sides = ["top", "right", "bottom", "left"];
    var rawFirst = null;
    var distinctKeys = [];

    for (var i = 0; i < sides.length; i++) {
        var side = sides[i];
        var info = borders ? borders[side] : null;
        if (!info || !info.width || info.width <= 0) {
            continue;
        }
        var raw = String(info.color || "").trim();
        if (!raw) {
            continue;
        }
        if (!rawFirst) {
            rawFirst = raw;
        }
        var key = _normalizeColorKey(raw);
        if (!key) {
            continue;
        }
        var exists = false;
        for (var k = 0; k < distinctKeys.length; k++) {
            if (distinctKeys[k] === key) {
                exists = true;
                break;
            }
        }
        if (!exists) {
            distinctKeys.push(key);
        }
    }

    return {
        firstColor: rawFirst,
        distinctCount: distinctKeys.length
    };
}

