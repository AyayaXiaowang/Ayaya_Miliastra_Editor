export function rectRight(rect) {
    return Number(rect && rect.left ? rect.left : 0) + Number(rect && rect.width ? rect.width : 0);
}

export function rectBottom(rect) {
    return Number(rect && rect.top ? rect.top : 0) + Number(rect && rect.height ? rect.height : 0);
}

export function rectIntersects(a, b) {
    if (!a || !b) {
        return false;
    }
    return rectRight(a) > b.left && a.left < rectRight(b) && rectBottom(a) > b.top && a.top < rectBottom(b);
}

export function rectContainsPoint(rect, px, py) {
    if (!rect) {
        return false;
    }
    var left = Number(rect.left || 0);
    var top = Number(rect.top || 0);
    var width = Number(rect.width || 0);
    var height = Number(rect.height || 0);
    if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height)) {
        return false;
    }
    if (width <= 0.001 || height <= 0.001) {
        return false;
    }
    return (px >= left) && (px <= left + width) && (py >= top) && (py <= top + height);
}

export function buildSamplePointsForRect(rect) {
    if (!rect) {
        return [];
    }
    var left = Number(rect.left || 0);
    var top = Number(rect.top || 0);
    var width = Number(rect.width || 0);
    var height = Number(rect.height || 0);
    if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height)) {
        return [];
    }
    if (width <= 0.001 || height <= 0.001) {
        return [];
    }
    var insetX = Math.min(6, width * 0.25);
    var insetY = Math.min(6, height * 0.25);
    if (!isFinite(insetX) || insetX < 0) insetX = 0;
    if (!isFinite(insetY) || insetY < 0) insetY = 0;
    var cx = left + width / 2;
    var cy = top + height / 2;
    return [
        { x: cx, y: cy },
        { x: left + insetX, y: top + insetY },
        { x: left + width - insetX, y: top + insetY },
        { x: left + insetX, y: top + height - insetY },
        { x: left + width - insetX, y: top + height - insetY }
    ];
}

export function buildDenseSamplePointsForRect(rect) {
    // 目标：避免“5点采样”误判（例如中间被盖住但边角可见）。
    // 策略：对大矩形用 3x3 网格采样；对小矩形仍用 5 点。
    if (!rect) {
        return [];
    }
    var left = Number(rect.left || 0);
    var top = Number(rect.top || 0);
    var width = Number(rect.width || 0);
    var height = Number(rect.height || 0);
    if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height)) {
        return [];
    }
    if (width <= 0.001 || height <= 0.001) {
        return [];
    }
    if (width < 40 || height < 40) {
        return buildSamplePointsForRect(rect);
    }
    var insetX = Math.min(6, width * 0.15);
    var insetY = Math.min(6, height * 0.15);
    if (!isFinite(insetX) || insetX < 0) insetX = 0;
    if (!isFinite(insetY) || insetY < 0) insetY = 0;
    var x0 = left + insetX;
    var x2 = left + width - insetX;
    var y0 = top + insetY;
    var y2 = top + height - insetY;
    var x1 = (x0 + x2) / 2;
    var y1 = (y0 + y2) / 2;
    return [
        { x: x0, y: y0 }, { x: x1, y: y0 }, { x: x2, y: y0 },
        { x: x0, y: y1 }, { x: x1, y: y1 }, { x: x2, y: y1 },
        { x: x0, y: y2 }, { x: x1, y: y2 }, { x: x2, y: y2 }
    ];
}

export function uniqueSortedNumbers(items) {
    var map = new Map();
    for (var i = 0; i < items.length; i++) {
        var v = Number(items[i]);
        if (!isFinite(v)) {
            continue;
        }
        var key = v.toFixed(6);
        if (!map.has(key)) {
            map.set(key, v);
        }
    }
    var list = Array.from(map.values());
    list.sort(function (a, b) { return a - b; });
    return list;
}

export function rectCellKey(rect) {
    return rect.left.toFixed(6) + "," + rect.top.toFixed(6) + "," + rect.width.toFixed(6) + "," + rect.height.toFixed(6);
}

