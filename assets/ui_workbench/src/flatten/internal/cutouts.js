import { GAME_CUTOUT_CLASS, GAME_CUTOUT_NAME_ATTR } from "../../config.js";
import { rectBottom, rectCellKey, rectIntersects, rectRight, uniqueSortedNumbers } from "./rects.js";

function _normalizeClassToken(token) {
    return String(token || "").trim();
}

function _splitClassTokens(classNameText) {
    var raw = String(classNameText || "");
    if (!raw) {
        return [];
    }
    return raw.split(/\s+/).map(_normalizeClassToken).filter(function (t) { return !!t; });
}

function _elementInfoHasClass(elementInfo, classToken) {
    var token = _normalizeClassToken(classToken);
    if (!token) {
        return false;
    }
    var classNameText = elementInfo && elementInfo.className ? String(elementInfo.className) : "";
    var tokens = _splitClassTokens(classNameText);
    for (var i = 0; i < tokens.length; i++) {
        if (tokens[i] === token) {
            return true;
        }
    }
    return false;
}

function _parseZIndexValue(rawText) {
    var raw = String(rawText || "").trim().toLowerCase();
    if (!raw || raw === "auto") {
        return 0;
    }
    var n = Number(raw);
    if (!isFinite(n)) {
        return 0;
    }
    return n;
}

export function isGameCutoutElementInfo(elementInfo) {
    return _elementInfoHasClass(elementInfo, GAME_CUTOUT_CLASS);
}

export function collectGameCutoutRects(elements) {
    var cutouts = [];
    for (var i = 0; i < (elements ? elements.length : 0); i++) {
        var elementInfo = elements[i];
        if (!isGameCutoutElementInfo(elementInfo)) {
            continue;
        }
        var rect = elementInfo && elementInfo.rect ? elementInfo.rect : null;
        if (!rect) {
            continue;
        }
        var w = Number(rect.width || 0);
        var h = Number(rect.height || 0);
        if (!isFinite(w) || !isFinite(h) || w <= 0.001 || h <= 0.001) {
            continue;
        }
        cutouts.push({
            left: Number(rect.left || 0),
            top: Number(rect.top || 0),
            width: w,
            height: h,
            name: elementInfo && elementInfo.attributes && elementInfo.attributes.dataGameAreaName ? String(elementInfo.attributes.dataGameAreaName || "") : "",
            // 元素抽取序号（dom_extract 的 DFS 先序遍历），用于“只裁下层，不裁上层”的判定。
            sourceElementIndex: i,
            // z-index（用于覆盖 DOM 顺序的显式置顶覆盖层场景）
            zIndex: _parseZIndexValue(elementInfo && elementInfo.styles ? elementInfo.styles.zIndex : 0),
            // 用于“只裁底层，不裁上层 UI”的判定：
            // 约定：ownerIndex 越小越靠前（更底层），越大越靠后（更上层/后绘制）。
            // 该值来自 dom_extract 的 componentOwnerElementIndex（原子组件根的稳定遍历序号）。
            ownerIndex: (function () {
                var raw = elementInfo && elementInfo.attributes ? (elementInfo.attributes.componentOwnerElementIndex || "") : "";
                var n = Number(raw);
                if (!isFinite(n)) {
                    return 0;
                }
                return n;
            })()
        });
    }
    return cutouts;
}

export function filterCutoutsForElement(elementInfo, elementExtractIndex, cutoutRects) {
    // 语义：`.game-cutout` 是“游戏视口挖空”标记——它应该只影响“在其下方绘制”的矩形层，
    // 不能把在其之上的覆盖层（菜单/提示/高亮等）也裁掉。
    //
    // 判定策略（启发式，稳定优先）：
    // - 先用“原子组件根”的 ownerIndex 近似表达跨组件的层级顺序（更贴近 UI 语义）。
    // - ownerIndex 相同（同一组件内）时，用 dom_extract 的先序 elementExtractIndex 进一步判定上下关系。
    //
    // 注意：`flatten_divs.js` 仍会对 `elementInfo.inGameCutout` 做保护（cutout 内部元素不再二次被 cutout 裁切）。
    var all = cutoutRects || [];
    if (!all.length) {
        return all;
    }
    var elementIndex = isFinite(Number(elementExtractIndex)) ? Number(elementExtractIndex) : 0;
    var elementOwnerIndex = (function () {
        var raw = elementInfo && elementInfo.attributes ? (elementInfo.attributes.componentOwnerElementIndex || "") : "";
        var n = Number(raw);
        if (!isFinite(n)) {
            return elementIndex;
        }
        return n;
    })();
    var elementZIndex = _parseZIndexValue(elementInfo && elementInfo.styles ? elementInfo.styles.zIndex : 0);

    var filtered = [];
    for (var i = 0; i < all.length; i++) {
        var c = all[i];
        if (!c) {
            continue;
        }
        var cutOwner = isFinite(Number(c.ownerIndex)) ? Number(c.ownerIndex) : Number(c.sourceElementIndex || 0);
        var cutIndex = isFinite(Number(c.sourceElementIndex)) ? Number(c.sourceElementIndex) : 0;
        var cutZIndex = isFinite(Number(c.zIndex)) ? Number(c.zIndex) : 0;
        // 显式的 z-index 置顶覆盖层：不应该被 cutout 裁剪。
        //
        // 关键修正：
        // 不能仅凭 “elementZIndex > cutZIndex” 就跳过裁剪——容器（如 preview-stage）常用 z-index 做局部层级，
        // 但其 background 仍在子元素（cutout）之下，应当被 cutout 挖空。
        // 因此这里要求“层级与绘制顺序”同时表明该元素在 cutout 之上，才跳过裁剪。
        var isElementAboveCutoutByOrder =
            (elementOwnerIndex > cutOwner) ||
            (elementOwnerIndex === cutOwner && elementIndex > cutIndex);
        if (elementZIndex > cutZIndex && isElementAboveCutoutByOrder) {
            continue;
        }
        if (elementOwnerIndex < cutOwner) {
            filtered.push(c);
            continue;
        }
        if (elementOwnerIndex === cutOwner && elementIndex < cutIndex) {
            filtered.push(c);
            continue;
        }
    }
    return filtered;
}

export function subtractRectByCutouts(baseRect, cutoutRects) {
    if (!baseRect || !isFinite(baseRect.width) || !isFinite(baseRect.height) || baseRect.width <= 0.001 || baseRect.height <= 0.001) {
        return [];
    }
    var base = {
        left: Number(baseRect.left || 0),
        top: Number(baseRect.top || 0),
        width: Number(baseRect.width || 0),
        height: Number(baseRect.height || 0)
    };
    if (!isFinite(base.left) || !isFinite(base.top) || !isFinite(base.width) || !isFinite(base.height) || base.width <= 0.001 || base.height <= 0.001) {
        return [];
    }

    var intersected = [];
    for (var i = 0; i < (cutoutRects ? cutoutRects.length : 0); i++) {
        var c = cutoutRects[i];
        if (!c) {
            continue;
        }
        var cut = { left: Number(c.left || 0), top: Number(c.top || 0), width: Number(c.width || 0), height: Number(c.height || 0) };
        if (!isFinite(cut.width) || !isFinite(cut.height) || cut.width <= 0.001 || cut.height <= 0.001) {
            continue;
        }
        if (!rectIntersects(base, cut)) {
            continue;
        }
        var interLeft = Math.max(base.left, cut.left);
        var interTop = Math.max(base.top, cut.top);
        var interRight = Math.min(rectRight(base), rectRight(cut));
        var interBottom = Math.min(rectBottom(base), rectBottom(cut));
        if (interRight - interLeft <= 0.001 || interBottom - interTop <= 0.001) {
            continue;
        }
        intersected.push({ left: interLeft, top: interTop, width: interRight - interLeft, height: interBottom - interTop });
    }
    if (intersected.length <= 0) {
        return [base];
    }

    var xEdges = [base.left, rectRight(base)];
    var yEdges = [base.top, rectBottom(base)];
    for (var ci = 0; ci < intersected.length; ci++) {
        var r = intersected[ci];
        xEdges.push(r.left);
        xEdges.push(rectRight(r));
        yEdges.push(r.top);
        yEdges.push(rectBottom(r));
    }
    var xs = uniqueSortedNumbers(xEdges);
    var ys = uniqueSortedNumbers(yEdges);
    if (xs.length < 2 || ys.length < 2) {
        return [base];
    }

    var keptCells = [];
    var keptCellSet = new Set();
    for (var yi = 0; yi < ys.length - 1; yi++) {
        var y0 = ys[yi];
        var y1 = ys[yi + 1];
        var h = y1 - y0;
        if (h <= 0.001) {
            continue;
        }
        for (var xi = 0; xi < xs.length - 1; xi++) {
            var x0 = xs[xi];
            var x1 = xs[xi + 1];
            var w = x1 - x0;
            if (w <= 0.001) {
                continue;
            }
            var cx = (x0 + x1) / 2;
            var cy = (y0 + y1) / 2;

            var insideAnyCutout = false;
            for (var ck = 0; ck < intersected.length; ck++) {
                var cutRect = intersected[ck];
                if (cx > cutRect.left && cx < rectRight(cutRect) && cy > cutRect.top && cy < rectBottom(cutRect)) {
                    insideAnyCutout = true;
                    break;
                }
            }
            if (insideAnyCutout) {
                continue;
            }
            var cell = { left: x0, top: y0, width: w, height: h };
            var key = rectCellKey(cell);
            if (!keptCellSet.has(key)) {
                keptCellSet.add(key);
                keptCells.push(cell);
            }
        }
    }
    if (keptCells.length <= 0) {
        return [];
    }

    // 先按行合并水平相邻 cell，再按列合并垂直相邻 rect，尽量减少碎片数量
    var rowBuckets = new Map(); // "y0,y1" -> rects[]
    for (var k = 0; k < keptCells.length; k++) {
        var c0 = keptCells[k];
        var rowKey = c0.top.toFixed(6) + "," + rectBottom(c0).toFixed(6);
        var bucket = rowBuckets.get(rowKey);
        if (!bucket) {
            bucket = [];
            rowBuckets.set(rowKey, bucket);
        }
        bucket.push(c0);
    }
    var mergedRows = [];
    rowBuckets.forEach(function (bucket) {
        bucket.sort(function (a, b) { return a.left - b.left; });
        var current = null;
        for (var i2 = 0; i2 < bucket.length; i2++) {
            var r0 = bucket[i2];
            if (!current) {
                current = { left: r0.left, top: r0.top, width: r0.width, height: r0.height };
                continue;
            }
            var currentRight = rectRight(current);
            if (Math.abs(r0.top - current.top) <= 0.001 && Math.abs(r0.height - current.height) <= 0.001 && Math.abs(r0.left - currentRight) <= 0.001) {
                current.width += r0.width;
            } else {
                mergedRows.push(current);
                current = { left: r0.left, top: r0.top, width: r0.width, height: r0.height };
            }
        }
        if (current) {
            mergedRows.push(current);
        }
    });

    mergedRows.sort(function (a, b) {
        if (a.left !== b.left) {
            return a.left - b.left;
        }
        if (a.width !== b.width) {
            return a.width - b.width;
        }
        return a.top - b.top;
    });

    var mergedFinal = [];
    for (var mi = 0; mi < mergedRows.length; mi++) {
        var r1 = mergedRows[mi];
        var merged = false;
        for (var mj = 0; mj < mergedFinal.length; mj++) {
            var existing = mergedFinal[mj];
            if (Math.abs(existing.left - r1.left) <= 0.001 && Math.abs(existing.width - r1.width) <= 0.001) {
                var existingBottom = rectBottom(existing);
                if (Math.abs(r1.top - existingBottom) <= 0.001) {
                    existing.height += r1.height;
                    merged = true;
                    break;
                }
            }
        }
        if (!merged) {
            mergedFinal.push({ left: r1.left, top: r1.top, width: r1.width, height: r1.height });
        }
    }
    return mergedFinal;
}

