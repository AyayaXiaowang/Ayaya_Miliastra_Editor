// Geometry helpers in "canvas coordinates" (relative to preview document body).

export function computeCanvasRectFromElement(targetDocument, targetElement) {
    if (!targetDocument || !targetDocument.body || !targetElement || !targetElement.getBoundingClientRect) {
        return null;
    }
    var bodyRect = targetDocument.body.getBoundingClientRect();
    if (!bodyRect) {
        return null;
    }
    var r = targetElement.getBoundingClientRect();
    var left = Number(r.left - bodyRect.left);
    var top = Number(r.top - bodyRect.top);
    var width = Number(r.width || 0);
    var height = Number(r.height || 0);
    if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height)) {
        return null;
    }
    return {
        left: left,
        top: top,
        width: Math.max(0, width),
        height: Math.max(0, height),
    };
}

export function computeGroupCanvasRect(targetDocument, elementList) {
    if (!targetDocument || !elementList || elementList.length === 0) {
        return null;
    }
    var minX = null;
    var minY = null;
    var maxX = null;
    var maxY = null;
    for (var i = 0; i < elementList.length; i++) {
        var el = elementList[i];
        if (!el) {
            continue;
        }
        var r = computeCanvasRectFromElement(targetDocument, el);
        if (!r) {
            continue;
        }
        var x1 = r.left;
        var y1 = r.top;
        var x2 = r.left + r.width;
        var y2 = r.top + r.height;
        if (minX === null || x1 < minX) minX = x1;
        if (minY === null || y1 < minY) minY = y1;
        if (maxX === null || x2 > maxX) maxX = x2;
        if (maxY === null || y2 > maxY) maxY = y2;
    }
    if (minX === null || minY === null || maxX === null || maxY === null) {
        return null;
    }
    return {
        left: minX,
        top: minY,
        width: Math.max(0, maxX - minX),
        height: Math.max(0, maxY - minY),
    };
}

