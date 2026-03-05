function _rectArea(rect) {
    if (!rect) {
        return 0;
    }
    var w = Number(rect.width || 0);
    var h = Number(rect.height || 0);
    if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
        return 0;
    }
    return w * h;
}

function _rectCenter(rect) {
    if (!rect) {
        return { x: 0, y: 0 };
    }
    return { x: Number(rect.left || 0) + Number(rect.width || 0) / 2.0, y: Number(rect.top || 0) + Number(rect.height || 0) / 2.0 };
}

function _rectContainsPoint(rect, px, py) {
    if (!rect) {
        return false;
    }
    var left = Number(rect.left || 0);
    var top = Number(rect.top || 0);
    var w = Number(rect.width || 0);
    var h = Number(rect.height || 0);
    return (px >= left) && (py >= top) && (px <= left + w) && (py <= top + h);
}

export function pickIconSeatRect(iconLayer, layerList) {
    if (!iconLayer || !iconLayer.rect) {
        return iconLayer && iconLayer.rect ? iconLayer.rect : null;
    }
    var iconRect = iconLayer.rect;
    var iconArea = _rectArea(iconRect);
    if (iconArea <= 0) {
        return iconRect;
    }
    var iconZ = Number.isFinite(iconLayer.z) ? Math.trunc(iconLayer.z) : 0;
    var center = _rectCenter(iconRect);

    var bestRect = null;
    var bestArea = null;
    for (var i = 0; i < layerList.length; i++) {
        var candidate = layerList[i];
        if (!candidate || !candidate.rect) {
            continue;
        }
        var kind = String(candidate.kind || "");
        if (kind !== "element" && kind !== "border") {
            continue;
        }
        var candZ = Number.isFinite(candidate.z) ? Math.trunc(candidate.z) : 0;
        // “座位背景矩形”必须在 icon 下面（更低层级）
        if (candZ >= iconZ) {
            continue;
        }
        var candRect = candidate.rect;
        if (!_rectContainsPoint(candRect, center.x, center.y)) {
            continue;
        }
        var candArea = _rectArea(candRect);
        if (candArea <= 0) {
            continue;
        }
        // 避免误吸附到整页大容器：背景块通常不会比 icon 大几十倍
        if (candArea > iconArea * 25.0) {
            continue;
        }
        if (bestArea === null || candArea < bestArea) {
            bestArea = candArea;
            bestRect = candRect;
        }
    }
    return bestRect || iconRect;
}

