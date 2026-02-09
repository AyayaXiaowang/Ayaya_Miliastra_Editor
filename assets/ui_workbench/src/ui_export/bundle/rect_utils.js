export function rectFromWidget(widget) {
    var pos = widget && widget.position ? widget.position : [0, 0];
    var size = widget && widget.size ? widget.size : [0, 0];
    var x = Number(pos[0] || 0);
    var y = Number(pos[1] || 0);
    var w = Number(size[0] || 0);
    var h = Number(size[1] || 0);
    return { x: x, y: y, w: w, h: h };
}

export function rectArea(rect) {
    if (!rect) {
        return 0;
    }
    var w = Number(rect.w || 0);
    var h = Number(rect.h || 0);
    if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
        return 0;
    }
    return w * h;
}

export function rectIntersectionArea(a, b) {
    if (!a || !b) {
        return 0;
    }
    var left = Math.max(a.x, b.x);
    var top = Math.max(a.y, b.y);
    var right = Math.min(a.x + a.w, b.x + b.w);
    var bottom = Math.min(a.y + a.h, b.y + b.h);
    var iw = right - left;
    var ih = bottom - top;
    if (iw <= 0 || ih <= 0) {
        return 0;
    }
    return iw * ih;
}

export function rectContainsPoint(rect, px, py) {
    if (!rect) {
        return false;
    }
    return (px >= rect.x) && (py >= rect.y) && (px <= rect.x + rect.w) && (py <= rect.y + rect.h);
}

export function rectCenter(rect) {
    return { x: rect.x + rect.w / 2.0, y: rect.y + rect.h / 2.0 };
}

export function boundsOfWidgets(widgetList) {
    var minX = null;
    var minY = null;
    var maxX = null;
    var maxY = null;
    for (var i = 0; i < widgetList.length; i++) {
        var rect = rectFromWidget(widgetList[i]);
        if (minX === null || rect.x < minX) {
            minX = rect.x;
        }
        if (minY === null || rect.y < minY) {
            minY = rect.y;
        }
        if (maxX === null || (rect.x + rect.w) > maxX) {
            maxX = rect.x + rect.w;
        }
        if (maxY === null || (rect.y + rect.h) > maxY) {
            maxY = rect.y + rect.h;
        }
    }
    if (minX === null || minY === null || maxX === null || maxY === null) {
        return { x: 0, y: 0, w: 0, h: 0 };
    }
    return {
        x: minX,
        y: minY,
        w: Math.max(0, maxX - minX),
        h: Math.max(0, maxY - minY)
    };
}

